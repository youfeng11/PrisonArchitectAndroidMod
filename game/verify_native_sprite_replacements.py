"""Execute the APK's native replacement loader against unmodified mod ZIPs."""

import math
import re
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from struct import pack, unpack, unpack_from
from zipfile import ZipFile
from zlib import decompress

from elftools.elf.elffile import ELFFile
from PIL import Image
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_CPSR, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
    UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_SP,
)

from patch_profile import (
    CALLOUT_ICON_HOOK, CALLOUT_LABEL_HOOK, LIBRARY, LOAD_HOOK, LOAD_SPRITE_BANK, MATERIAL_SPRITE_HOOKS,
    NATIVE_ATLAS_IMPORTS, NATIVE_PREVIEW_HOOKS, SPRITE_REPLACEMENT_IMPORTS, SPRITE_ROOT_COMPARE_HOOKS,
    SQUAD_DRAWABLE_HOOK, SQUAD_ICON_NAME_HOOK, TOOLBAR_ICON_HOOK, branch,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x10000000
ARENA = 0x20000000
STACK = ARENA + 0x2000
BANK, IMAGE, BITMAP, APP, MODS = (ARENA + offset for offset in range(0x3000, 0x8000, 0x1000))
DIR_ENTRY, READER, VTABLE = (ARENA + offset for offset in (0x9000, 0xA000, 0xB000))
SOURCE_ROWS, SOURCE_PIXELS, ATLAS_PIXELS = (ARENA + offset for offset in (0xC000, 0x100000, 0x200000))
FILESYSTEM = ARENA + 0xD000
READER_DESTROY = ARENA + 0xE000
OBJECT, DRAWABLE, STOCK_TEXTURE, LIVE_TEXTURE = (ARENA + offset for offset in (0xF000, 0x10000, 0x11000, 0x12000))
UI_NAME = ARENA + 0x13000
CALLOUT, CALLOUT_NAME, CALLOUT_BLOCK, CALLOUT_FRAME, MATERIALS, LANGUAGE, TRANSLATION = (
    ARENA + i for i in range(0x14000, 0x1B000, 0x1000)
)
INTERFACE_NAMES = ARENA + 0x1B000
SPRITE_RECORDS, SPRITE_POINTERS, PRESENT, HEAP = (ARENA + offset for offset in (0x20000, 0x30000, 0x31000, 0x40000))
PREFIX = "data/sprite_replacement/default/default_"


BAYER_8 = (
    (0, 48, 12, 60, 3, 51, 15, 63),
    (32, 16, 44, 28, 35, 19, 47, 31),
    (8, 56, 4, 52, 11, 59, 7, 55),
    (40, 24, 36, 20, 43, 27, 39, 23),
    (2, 50, 14, 62, 1, 49, 13, 61),
    (34, 18, 46, 30, 33, 17, 45, 29),
    (10, 58, 6, 54, 9, 57, 5, 53),
    (42, 26, 38, 22, 41, 25, 37, 21),
)


def rgba4444(pixels, width=1, *, x=0, top=0):
    """Reference conversion for bottom-first native bitmap rows."""
    output = bytearray(len(pixels) // 2)
    height = len(pixels) // (width * 4)
    for i, (r, g, b, a) in enumerate(zip(*[iter(pixels)] * 4)):
        row, column = divmod(i, width)
        bias = (BAYER_8[(top + height - 1 - row) % 8][(x + column) % 8] * 17 + 8) // 64
        color = 0 if (r, g, b) == (255, 0, 255) or a < 9 else (
            ((r + bias) // 17) << 12 | ((g + bias) // 17) << 8 |
            ((b + bias) // 17) << 4 | ((a + 8) // 17))
        output[i * 2:i * 2 + 2] = pack("<H", color)
    return output


def verify(apk, obb, mod, variants):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    with ZipFile(obb) as archive:
        composite = archive.read("data/tablet/composite.csimage")
        stock_bank = archive.read("data/objects.spritebank").decode()
    width, height, format_id = unpack_from("<3I", composite, 8)
    assert format_id == 4
    top_first = decompress(composite[40:])
    stride = width * 2
    stock = b"".join(top_first[y:y + stride] for y in range(len(top_first) - stride, -1, -stride))

    pngs = {}
    with ZipFile(mod) as archive:
        for name in archive.namelist():
            if name.startswith(PREFIX) and name.endswith(".png"):
                pngs[name[len(PREFIX):-4]] = Image.open(BytesIO(archive.read(name))).convert("RGBA")
        if variants:
            # The explicit file must win over row two of default_Guard.png,
            # even when the directory lists it first.
            guard = pngs["Guard"]
            pngs["Guard2"] = Image.new("RGBA", (guard.width, guard.height // variants["Guard"]),
                                       (32, 240, 176, 255))
            pngs = {"Guard2": pngs.pop("Guard2"), **pngs}

    records = {match[2].strip('"'): (int(match[1]), *map(int, match.groups()[2:]))
               for match in re.finditer(r'BEGIN "\[i (\d+)\]"\s+Name ("[^"]+"|\S+)\s+x (\d+)\s+y (\d+)'
                                        r'\s+w (\d+)\s+h (\d+)\s+RotateType (\d+)', stock_bank.split("BEGIN Markers")[0])}
    regions = {}
    for line in (ROOT / "fixtures/native/native-regions.tsv").read_text(encoding="utf-8").splitlines():
        _, name, rects = line.split("\t")
        regions[name] = [tuple(map(int, rect.split(","))) for rect in rects.split(";")]

    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for segment in elf.iter_segments(type="PT_LOAD"):
        start = segment["p_vaddr"] & ~4095
        end = (segment["p_vaddr"] + segment["p_memsz"] + 4095) & ~4095
        arm.mem_map(BASE + start, end - start)
        arm.mem_write(BASE + segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x4000000)
    arm.mem_write(ATLAS_PIXELS, stock)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def put(address, *words):
        arm.mem_write(address, pack(f"<{len(words)}I", *words))

    def word(address):
        return unpack("<I", arm.mem_read(address, 4))[0]

    def c_string(address):
        value = bytearray()
        while len(value) < 1024:
            size = min(1024 - len(value), 4096 - address % 4096)
            chunk, separator, _ = arm.mem_read(address, size).partition(b"\0")
            value.extend(chunk)
            if separator:
                return value.decode()
            address += size
        raise AssertionError("Unterminated C string")

    def game_string(address):
        return c_string(word(address + 8) if arm.mem_read(address, 1)[0] & 1 else address + 1)

    def set_game_string(address, value):
        encoded = value.encode()
        if len(encoded) <= 10:
            arm.mem_write(address, (bytes([len(encoded) * 2]) + encoded).ljust(12, b"\0"))
        else:
            put(address, 65, len(encoded), address + 12)
            arm.mem_write(address + 12, encoded + b"\0")

    def set_call(address, *args):
        for reg, arg in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args[:4], strict=True):
            arm.reg_write(reg, arg)
        put(STACK, *args[4:])
        arm.reg_write(UC_ARM_REG_SP, STACK)
        arm.emu_start(BASE + address, BASE + address + 4, count=100_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + address + 4
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    put(BANK, IMAGE)
    put(IMAGE, BITMAP, 42)
    put(IMAGE + 0x18, width, height)
    arm.mem_write(IMAGE + 9, b"\x01")
    put(BITMAP, 0x8033, width, height, 0, ATLAS_PIXELS, 0)
    put(APP, MODS, 2, 2)
    put(BASE + 0xED0200, APP + 0x100)
    put(APP + 0x100, APP)
    put(BASE + 0xED0D4C, APP + 0x104)
    put(APP + 0x104, FILESYSTEM)
    put(READER, VTABLE)
    put(VTABLE + 4, READER_DESTROY)
    put(BANK + 0x18, len(records), SPRITE_POINTERS, PRESENT)
    for (hook, _, _), (actual, expected) in zip(
        SPRITE_ROOT_COMPARE_HOOKS, ((UC_ARM_REG_R2, UC_ARM_REG_R1), (UC_ARM_REG_R6, UC_ARM_REG_R7)), strict=True
    ):
        for value, canonical, equal in ((b"D", b"d", True), (b"A", b"a", True),
                                        (b"/", b"/", True), (b"B", b"d", False)):
            arm.reg_write(actual, value[0])
            arm.reg_write(expected, canonical[0])
            arm.reg_write(UC_ARM_REG_LR, ARENA)
            arm.reg_write(UC_ARM_REG_SP, STACK)
            arm.emu_start(BASE + hook, BASE + hook + 4, count=10)
            assert arm.reg_read(UC_ARM_REG_PC) == BASE + hook + 4
            assert arm.reg_read(UC_ARM_REG_LR) == ARENA
            assert bool(arm.reg_read(UC_ARM_REG_CPSR) & (1 << 30)) == equal
    for record in records.values():
        sprite_id, *rect = record
        address = SPRITE_RECORDS + sprite_id * 64
        put(address, 0, 0, 0, *rect, 0)
        put(SPRITE_POINTERS + sprite_id * 4, address)
        arm.mem_write(PRESENT + sprite_id, b"\x01")
    for index, path in enumerate((b"/other/", b"/fixture/")):
        arm.mem_write(MODS + index * 108, bytes([len(path) * 2]) + path + b"\0")

    imported = {BASE + addr: name for name, addr in SPRITE_REPLACEMENT_IMPORTS.items() if name != "sprite_rect"}
    imported.update({BASE + NATIVE_ATLAS_IMPORTS[name]: name for name in
                     ("copy_bytes", "bitmap_destroy", "debug_log", "new_array", "new_object", "delete_array",
                      "delete_object", "zero_bytes")})
    imported.update({BASE + LOAD_SPRITE_BANK: "load_bank", READER_DESTROY: "close_reader",
                     BASE + 0x3CBAC8: "acosf", BASE + 0x3B0A8C: "fmodf"})
    fixture_folder = "/fixture/Data/Sprite_Replacement/Default/"
    mixed_name = next(name for name in pngs if name in records and name != "Guard2")
    filenames = {f"default_{name}.png": name for name in pngs if name != mixed_name}
    filenames[f"DEFAULT_{mixed_name}.PNG"] = mixed_name
    directories = {
        "/fixture": ["Data"],
        "/fixture/Data": ["Sprite_Replacement"],
        "/fixture/Data/Sprite_Replacement": ["Default"],
        fixture_folder: ["default_unknown.png", "readme.txt", *filenames],
        fixture_folder.rstrip("/"): ["default_unknown.png", "readme.txt", *filenames],
    }
    pending = {}
    selected = None
    opened, logged, uploaded = [], [], []
    drawn = []
    fitted_sizes = []
    heap = HEAP
    has_inline = True
    inline_key = "Sprite"
    coordinates = {"x": 4, "y": 0, "w": 2.5, "h": 3}
    material_coordinates = (2, 0, 2, 2, 1)
    sheet_path = "/fixture/data/sprites.png"
    sheet_header = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + pack(">2I", 320, 128)
    sheet_offset = (80, 60)
    phrases = set()
    looked_up = []
    sprite_registered = []

    def import_call(uc, address, _size, _data):
        nonlocal selected, heap
        name = imported[address]
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        sp = uc.reg_read(UC_ARM_REG_SP)
        assert sp % 8 == 0
        result = 0
        if name == "load_bank":
            assert a == BANK
            put(BANK + 0x18, len(records))
        elif name == "opendir":
            path = c_string(a)
            opened.append(path)
            if path in directories:
                result = DIR_ENTRY + len(opened) * 4
                pending[result] = iter(directories[path])
        elif name == "readdir":
            file = next(pending[a], None)
            if file:
                arm.mem_write(DIR_ENTRY + 19, file.encode() + b"\0")
                result = DIR_ENTRY
        elif name == "closedir":
            del pending[a]
        elif name == "lookup_sprite":
            assert a == BANK
            record = records.get(game_string(b))
            if record:
                result = SPRITE_RECORDS + record[0] * 64
        elif name == "get_binary_reader":
            assert a == FILESYSTEM and c == 0
            path = game_string(b)
            assert path.startswith(fixture_folder)
            selected = filenames[path.removeprefix(fixture_folder)]
            result = READER
        elif name == "decode_bitmap":
            assert b == READER and game_string(c) == "png"
            png = pngs[selected]
            arm.mem_write(SOURCE_PIXELS, png.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes())
            put(SOURCE_ROWS, *(SOURCE_PIXELS + 4 * png.width * y for y in range(png.height)))
            put(a, 0x1401, png.width, png.height, 0, SOURCE_PIXELS, SOURCE_ROWS)
        elif name == "close_reader":
            assert a == READER
        elif name == "copy_bytes":
            arm.mem_write(a, bytes(arm.mem_read(b, c)))
        elif name in ("new_array", "new_object"):
            result = heap
            heap += (a + 15) & ~15
        elif name == "zero_bytes":
            arm.mem_write(a, b"\0" * b)
        elif name == "strlen":
            result = len(c_string(a).encode())
        elif name in ("strcmp", "strncmp", "strcasecmp", "strncasecmp"):
            lhs, rhs = c_string(a), c_string(b)
            if name in ("strcasecmp", "strncasecmp"):
                lhs, rhs = lhs.lower(), rhs.lower()
            result = int((lhs[:c] != rhs[:c]) if name in ("strncmp", "strncasecmp") else (lhs != rhs))
        elif name == "memcmp":
            result = int(arm.mem_read(a, c) != arm.mem_read(b, c))
        elif name.startswith("__aeabi_uidiv"):
            result, rest = divmod(a, b)
            uc.reg_write(UC_ARM_REG_R1, rest)
        elif name in ("acosf", "fmodf"):
            x, y = unpack("<ff", pack("<II", a, b))
            value = math.acos(max(-1, min(1, x))) if name == "acosf" else math.fmod(x, y)
            result, = unpack("<I", pack("<f", value))
        elif name == "debug_log":
            logged.append(c_string(b))
        elif name == "upload_bitmap":
            uploaded.append((a, b, c, d))
        elif name == "get_object_template":
            assert a == 13
            result = OBJECT
        elif name == "get_callout_template":
            assert a in (1, 6)
            result = CALLOUT if a == 6 else CALLOUT_NAME + 256
        elif name == "copy_game_string":
            set_game_string(a, game_string(b))
            result = a
        elif name == "directory_child":
            assert a == CALLOUT_BLOCK and game_string(b) == inline_key
            result = CALLOUT_FRAME if has_inline else 0
        elif name == "directory_number":
            assert a == CALLOUT_FRAME
            result, high = unpack("<2I", pack("<d", coordinates[game_string(b)]))
            uc.reg_write(UC_ARM_REG_R1, high)
        elif name == "read_sprite_definition":
            assert b == CALLOUT_BLOCK and arm.mem_read(a, 36) == bytes(36)
            arm.mem_write(a + 12, pack("<5i", *material_coordinates))
        elif name == "disk_file_exists":
            assert game_string(a) == sheet_path
            result = 1
        elif name == "fopen":
            assert c_string(a) == sheet_path and c_string(b) == "rb"
            result = FILESYSTEM
        elif name == "fread":
            assert (b, c, d) == (1, len(sheet_header), FILESYSTEM)
            arm.mem_write(a, sheet_header)
            result = c
        elif name == "fclose":
            assert a == FILESYSTEM
        elif name == "get_mod_sprite_offset":
            assert (b, c) == (APP + 784, MATERIALS)
            assert game_string(c) == "/fixture/Data/Materials.TXT"
            put(a, *sheet_offset)
        elif name == "add_user_defined_sprite":
            assert (a, b, c, d) == (OBJECT, MATERIALS, CALLOUT_BLOCK, CALLOUT_NAME)
            sprite_registered.append(game_string(b))
            result = 734
        elif name == "language_has_phrase":
            assert a == LANGUAGE
            result = int(game_string(b) in phrases)
        elif name == "language_lookup":
            assert a == LANGUAGE
            looked_up.append(game_string(b))
            result = TRANSLATION
        elif name == "create_ui_texture":
            put(a, LIVE_TEXTURE)
        elif name == "build_ui_texture":
            assert (a, word(b), word(b + 4)) == (LIVE_TEXTURE, width, height)
        elif name == "make_texture_drawable":
            assert a == DRAWABLE and word(b) == LIVE_TEXTURE and c == 0xAA
            arm.mem_write(DRAWABLE + 0x14, bytes(arm.mem_read(d, 16)))
            result = a
        elif name == "make_atlas_drawable":
            assert (a, b, c, d, word(sp), word(sp + 4)) == (DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0)
            drawn.append(name)
            result = a
        elif name == "draw_sprite_bank_box":
            assert (word(sp + 4), word(sp + 8), word(sp + 12), word(sp + 16)) == (BANK, DRAWABLE + 0x14, 0xAA, 1)
            fitted_sizes.append(unpack("<2f", uc.mem_read(c, 8)))
            drawn.append(name)
        elif name == "draw_texture_box":
            assert (word(sp + 4), word(sp + 8), word(sp + 12)) == (STOCK_TEXTURE, 0xAA, 1)
            drawn.append(name)
        else:
            assert name in ("closedir", "bitmap_destroy", "delete_array", "delete_object"), name
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for address in imported:
        arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address)
    arm.reg_write(UC_ARM_REG_SP, STACK)
    arm.reg_write(UC_ARM_REG_R0, BANK)
    arm.emu_start(BASE + LOAD_HOOK, BASE + LOAD_HOOK + 4, count=100_000_000)
    assert arm.reg_read(UC_ARM_REG_PC) == BASE + LOAD_HOOK + 4
    assert uploaded == [(BITMAP, 1, 42, 0)]
    expected_opened = ["/other/data/sprite_replacement/default/", "/other",
                       "/fixture/data/sprite_replacement/default/", *list(directories)[:3], fixture_folder]
    if mixed_name[-1].isdigit():
        expected_opened.extend((fixture_folder, fixture_folder.rstrip("/")))
    else:
        expected_opened.extend((fixture_folder.rstrip("/"), fixture_folder))
    assert opened == expected_opened
    assert set(logged) == pngs.keys() & records.keys()

    expected = bytearray(stock)
    replacements = 0
    for name in sorted(pngs, key=lambda name: name[-1].isdigit()):
        png = pngs[name]
        if name not in records:
            continue
        _, _, _, _, sprite_h, _ = records[name]
        count = variants.get(name, 1)
        for i in range(count):
            frames = regions[name if i == 0 else name + str(i + 1)]
            left, top = min(frame[0] for frame in frames), min(frame[1] for frame in frames)
            frame_w = frames[0][2]
            frames = [*frames, (left + frame_w * 3, top, frame_w, frames[0][3])]
            for x, y, w, h in frames:
                source_x, source_y = x - left, y - top + i * sprite_h * 32
                crop = png.crop((source_x, source_y, source_x + w, source_y + h))
                pixels = rgba4444(crop.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes(), w,
                                  x=source_x, top=source_y)
                for row in range(h):
                    start = ((height - y - h + row) * width + x) * 2
                    expected[start:start + w * 2] = pixels[row * w * 2:(row + 1) * w * 2]
            replacements += 1
    assert arm.mem_read(ATLAS_PIXELS, len(expected)) == expected
    assert expected != stock
    print(f"{mod.name}: {len(logged)} replacement PNGs, {replacements} sprite rows; all other pixels unchanged")

    # The menu uses a generated sprite ID for an overridden guard, while the
    # stock texture has no coordinates for its generated name.
    preview_hook, draw_hook = (hook[0] for hook in NATIVE_PREVIEW_HOOKS)
    added_id = len(records)
    address = SPRITE_RECORDS + added_id * 64
    put(address, 0, 0, 0, 4, 7, 1, 2, 0, 0)
    put(BANK + 0x18, added_id + 1)
    put(SPRITE_POINTERS + added_id * 4, address)
    arm.mem_write(PRESENT + added_id, b"\x01")
    put(OBJECT + 100, added_id, 0, 0, 0xFFFFFFFF)
    arm.mem_write(UI_NAME, b"\x12Guard_999\0")
    arm.reg_write(UC_ARM_REG_R10, 13)
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 8)
    crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
    for actual, target in zip(crop, (128.5 / width, 224.5 / height, 31.0 / width, 63.0 / height), strict=True):
        assert math.isclose(actual, target, rel_tol=1e-6)
    put(DRAWABLE, LIVE_TEXTURE, 0)
    arm.reg_write(UC_ARM_REG_R7, DRAWABLE + 4)
    draw_size = LIVE_TEXTURE + 0x100
    arm.mem_write(draw_size, pack("<2f", 64.0, 64.0))
    set_call(draw_hook, 1, 2, draw_size, 4, 0, DRAWABLE, 0xAA, 1)
    assert fitted_sizes == [(32.0, 64.0)]
    arm.mem_write(DRAWABLE + 0x14, pack("<4f", 0, 0, 63.0 / width, 31.0 / height))
    set_call(draw_hook, 1, 2, draw_size, 4, 0, DRAWABLE, 0xAA, 1)
    assert fitted_sizes[-1] == (64.0, 32.0)
    arm.mem_write(DRAWABLE + 0x14, pack("<4f", 0, 0, 31.0 / width, 31.0 / height))
    set_call(draw_hook, 1, 2, draw_size, 4, 0, DRAWABLE, 0xAA, 1)
    assert fitted_sizes[-1] == (64.0, 64.0)

    put(OBJECT + 100, records["Guard"][0])
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 8)
    set_call(draw_hook, 1, 2, 3, 4, 0, STOCK_TEXTURE, 0xAA, 1)
    assert drawn == ["draw_sprite_bank_box"] * 3 + ["make_atlas_drawable", "draw_texture_box"]
    print("Tall, wide, and square mod thumbnails preserve their pixel aspect ratio on the composite atlas.")

    stock_call = branch(CALLOUT_ICON_HOOK, SPRITE_REPLACEMENT_IMPORTS["copy_game_string"], True)
    if word(BASE + CALLOUT_ICON_HOOK) == stock_call:
        return
    set_game_string(MATERIALS, "/fixture/Data/Materials.TXT")
    set_game_string(CALLOUT_NAME, "call_batman")
    assert records["Nothing"][0] == 457
    for hook in MATERIAL_SPRITE_HOOKS:
        sheet_offset = (80, 60)
        material_coordinates = (2, 0, 2, 2, 1)
        set_call(hook, OBJECT, MATERIALS, CALLOUT_BLOCK, CALLOUT_NAME)
        assert arm.reg_read(UC_ARM_REG_R0) == 734
        material_coordinates = (0, 0, 2, 2, 0)
        set_call(hook, OBJECT, MATERIALS, CALLOUT_BLOCK, CALLOUT_NAME)
        assert arm.reg_read(UC_ARM_REG_R0) == 734
        material_coordinates = (6, 0, 2, 2, 1)
        set_call(hook, OBJECT, MATERIALS, CALLOUT_BLOCK, CALLOUT_NAME)
        assert arm.reg_read(UC_ARM_REG_R0) == records["Nothing"][0]
        sheet_offset = (0, 0)
        set_call(hook, OBJECT, MATERIALS, CALLOUT_BLOCK, CALLOUT_NAME)
        assert arm.reg_read(UC_ARM_REG_R0) == records["Nothing"][0]
    assert sprite_registered == ["/fixture/Data/Materials.TXT"] * (2 * len(MATERIAL_SPRITE_HOOKS))
    sheet_offset = (80, 60)
    set_game_string(CALLOUT_NAME + 256, "FireEngine")
    put(STACK + 0x1A4, MATERIALS)
    put(STACK + 0x1AC, CALLOUT_BLOCK)
    # Register a different icon first so the next callout uses a nonempty list.
    set_game_string(CALLOUT_NAME, "call_first")
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    set_game_string(CALLOUT_NAME, "call_batman")
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    arm.reg_write(UC_ARM_REG_R10, 6)
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
    for actual, target in zip(crop, (2688.5 / width, 1920.5 / height, 79.0 / width, 95.0 / height), strict=True):
        assert math.isclose(actual, target, rel_tol=1e-6), crop
    batman_crop = crop
    # Replacing another icon must preserve the second callout's custom crop.
    set_game_string(CALLOUT_NAME, "call_first")
    coordinates["x"] = 2
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    first_crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
    assert first_crop != batman_crop and first_crop[0] == 2624.5 / width
    set_game_string(CALLOUT, "call_batman")
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    assert unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16)) == batman_crop
    coordinates["x"] = 4
    set_game_string(CALLOUT_NAME, "call_batman")
    if word(BASE + SQUAD_ICON_NAME_HOOK) != 0xE0810081:
        put(BASE + 0xED3180, INTERFACE_NAMES)
        put(INTERFACE_NAMES, INTERFACE_NAMES + 12, 1, 1)
        set_game_string(INTERFACE_NAMES + 12, "Blank")
        arm.reg_write(UC_ARM_REG_R1, 6)
        arm.emu_start(BASE + SQUAD_ICON_NAME_HOOK, BASE + 0x4B9454, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + 0x4B9454
        assert arm.reg_read(UC_ARM_REG_SP) == STACK
        assert game_string(STACK + 0x28) == "Blank"
        assert word(STACK + 0x34) == 6
        arm.mem_write(DRAWABLE + 0x14, b"\0" * 16)
        set_call(SQUAD_DRAWABLE_HOOK, DRAWABLE, STOCK_TEXTURE, 0xBB, STACK + 0x28, 0xAA, 0)
        assert unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16)) == crop
    arm.reg_write(UC_ARM_REG_R10, 1)
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    assert drawn[-1] == "make_atlas_drawable"
    # Model a callout parsed from a mod: named like the icon key, summoning OBJECT.
    set_game_string(CALLOUT, "FireEngine")
    put(CALLOUT + 24, 13)
    put(OBJECT + 100, added_id)
    has_inline = False
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    arm.reg_write(UC_ARM_REG_R10, 6)
    drawn.clear()
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    # A callout parsed from a mod without its own icon draws the summoned unit.
    assert drawn == []
    crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
    assert crop[2] > 0 and crop[3] > 0
    # A later layer can add the custom icon again after an icon-free definition.
    has_inline = True
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    assert unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16)) == batman_crop
    coordinates["x"] = 8
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    drawn.clear()
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    assert drawn == []
    coordinates["x"] = 4
    sheet_offset = (0, 0)
    set_call(CALLOUT_ICON_HOOK, CALLOUT, CALLOUT_NAME, 0, 0)
    drawn.clear()
    set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 13)
    assert drawn == []

    label = "interfacecallout_call_batman"
    desktop_label = "interfacecallout_batman"
    set_game_string(UI_NAME, label)
    phrases.update((label, desktop_label))
    set_call(CALLOUT_LABEL_HOOK, LANGUAGE, UI_NAME, 0, 0)
    phrases.remove(label)
    set_call(CALLOUT_LABEL_HOOK, LANGUAGE, UI_NAME, 0, 0)
    phrases.clear()
    set_call(CALLOUT_LABEL_HOOK, LANGUAGE, UI_NAME, 0, 0)
    assert looked_up == [label, desktop_label, label]
    print("Inline callout icons retain fractional tiles, and desktop labels resolve after exact keys.")

    if word(BASE + TOOLBAR_ICON_HOOK) != branch(TOOLBAR_ICON_HOOK, SPRITE_REPLACEMENT_IMPORTS["copy_game_string"], True):
        inline_key = "ToolbarSprite"
        with ZipFile(ROOT / "fixtures/mods/mods_Office_Chair.zip") as archive:
            materials = archive.read("data/materials.txt").decode()
        toolbar = materials.split("BEGIN ToolbarSprite", 1)[1].split("END", 1)[0]
        coordinates = {field: float(value) for field, value in re.findall(r"(?m)^\s*([xywh])\s+(\S+)", toolbar)}
        assert coordinates == {"x": 1, "y": 2, "w": 2, "h": 2}
        sheet_offset = (80, 60)
        set_game_string(CALLOUT_NAME, "OfficeChair")
        set_call(TOOLBAR_ICON_HOOK, OBJECT, CALLOUT_NAME, 0, 0)
        put(OBJECT + 100, added_id)
        set_game_string(UI_NAME, "OfficeChair")
        arm.reg_write(UC_ARM_REG_R10, 13)
        set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 5)
        crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
        assert crop == (2592.5 / width, 1984.5 / height, 63.0 / width, 63.0 / height)
        has_inline = False
        set_call(TOOLBAR_ICON_HOOK, OBJECT, CALLOUT_NAME, 0, 0)
        set_call(preview_hook, DRAWABLE, STOCK_TEXTURE, 0xBB, UI_NAME, 0xAA, 0, 0, 0, 0, 5)
        crop = unpack("<4f", arm.mem_read(DRAWABLE + 0x14, 16))
        assert crop == (128.5 / width, 224.5 / height, 31.0 / width, 63.0 / height)
        print("Office Chair uses its declared ToolbarSprite crop and falls back to the object sprite if removed.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    args = parser.parse_args()
    obb = ROOT / "com.paradoxplaza.prisonarchitect/main.49.com.paradoxplaza.prisonarchitect.obb"
    verify(args.apk, obb, ROOT / "fixtures/mods/mods_Additional_Guard_Sprites.zip", {})
    verify(args.apk, obb, ROOT / "fixtures/mods/mods_2010s_Chinese_style_Prison_Mod.zip",
           dict.fromkeys(("ArmedGuard", "DogHandler", "Guard", "Prisoner", "Sniper"), 4))
