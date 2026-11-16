"""Run the mobile atlas hooks with the original OBB and standard mod PNGs."""

from argparse import ArgumentParser
from io import BytesIO
from math import isclose
import re
from struct import pack, unpack, unpack_from
from zipfile import ZipFile
from zlib import decompress

from elftools.elf.elffile import ELFFile
from PIL import Image
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_CPSR, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R5, UC_ARM_REG_R6,
    UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R11, UC_ARM_REG_SP,
)

from patch_profile import (
    GRANT_ICON_HOOK, LIBRARY, MATERIAL_DUPLICATE_BRANCHES, MENU_ATLAS_HOOK, NATIVE_ATLAS_IMPORTS, NATIVE_ATLAS_STATE,
    SPRITE_REPLACEMENT_IMPORTS,
)
from verify_composite_resize import read_coordinates
from verify_native_sprite_replacements import rgba4444


BASE = 0x10000000
ARENA = 0x20000000
STACK = ARENA + 0x1000
RENDERER = ARENA + 0x2000
BITMAP = ARENA + 0x3000
PACKED = ARENA + 0x3100
SOURCE = ARENA + 0x3300
SOURCE_ROWS = ARENA + 0x4000
SOURCE_PIXELS = ARENA + 0x10000
HEAP = ARENA + 0x1800000
BASE_PIXELS = ARENA + 0x2000000
PACKED_PIXELS = ARENA + 0x6000000
FRAME_DIRECTIONS = ((0, 1), (0, -1), (-1, 0), (1, 0))


def sprite_records(materials):
    pattern = r"^[^\S\n]*BEGIN[^\S\n]+(?:Toolbar)?Sprite\s+(.*?)\bEND\b"
    for match in re.finditer(pattern, materials, re.M | re.S):
        fields = match[1].split()
        values = dict(zip(fields[::2], fields[1::2]))
        if all(key in values for key in ("x", "y", "w", "h")):
            yield (*(int(values[key]) for key in ("x", "y", "w", "h")), int(values.get("RotateType", 0)))


def verify(apk, obb, mods):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    with ZipFile(obb) as archive:
        data = archive.read("data/tablet/composite.csimage")
    width, height, stock_pixels = composite_pixels(data)
    sheets = {}
    for i, mod in enumerate(mods):
        with ZipFile(mod) as archive:
            name = next(name for name in archive.namelist() if name.endswith("data/sprites.png"))
            sheet = Image.open(BytesIO(archive.read(name))).convert("RGBA")
            materials = archive.read(name.removesuffix("sprites.png") + "materials.txt").decode("utf-8-sig")
        sheets[f"mod{i}"] = (sheet, materials)

    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(segment["p_vaddr"] + segment["p_memsz"] for segment in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x10000000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def put(address, *words):
        arm.mem_write(address, pack(f"<{len(words)}I", *words))

    def words(address, n=1):
        return unpack(f"<{n}I", arm.mem_read(address, n * 4))

    def sprite_frames(x, y, w, h, rotate_type):
        sprite, direction, output = (ARENA + offset for offset in (0x3600, 0x3640, 0x3650))
        put(sprite + 12, x, y, w, h, rotate_type)
        for dx, dy in FRAME_DIRECTIONS:
            arm.mem_write(direction, pack("<2f", dx, dy))
            put(output + 20, w, h)
            put(STACK, *(output + offset for offset in range(8, 28, 4)))
            for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                                       (sprite, direction, output, output + 4)):
                arm.reg_write(register, value)
            arm.reg_write(UC_ARM_REG_LR, ARENA)
            arm.emu_start(BASE + 0x8CB358, ARENA, count=200)
            assert arm.reg_read(UC_ARM_REG_PC) == ARENA
            yield words(output + 4, 4)

    # Resolve inter-library calls and the sort callbacks used by the stock packer.
    plt = elf.get_section_by_name(".plt")
    rel = elf.get_section_by_name(".rel.plt")
    symbols = elf.get_section(rel["sh_link"])
    plt_symbols = {
        plt["sh_addr"] + 20 + i * 12: symbols.get_symbol(entry["r_info_sym"])
        for i, entry in enumerate(rel.iter_relocations())
    }
    put(BASE + 0xED01BC, ARENA)
    put(BASE + 0xED3164, BASE + 0x8C7664, BASE + 0x8C768C)
    heap = HEAP

    def stock_import(uc, address, _size, _data):
        nonlocal heap
        symbol = plt_symbols[address - BASE]
        a, b, c = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if symbol.name in ("_Znaj", "_Znwj"):
            uc.reg_write(UC_ARM_REG_R0, heap)
            heap += (a + 7) & ~7
            assert heap < BASE_PIXELS
        elif symbol.name.startswith(("__aeabi_memcpy", "__aeabi_memmove")) or symbol.name in ("memcpy", "memmove"):
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
        elif symbol.name == "_Z16AppReleaseAssertbPKcz":
            assert a, bytes(uc.mem_read(b, 120)).split(b"\0")[0]
        elif symbol.name not in ("_ZdlPv", "_ZdaPv", "_Z11AppDebugOutPKcz"):
            assert symbol["st_value"], symbol.name
            uc.reg_write(UC_ARM_REG_PC, BASE + symbol["st_value"])
            return
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    put(BITMAP, 0x8033, width, height, 0, BASE_PIXELS, 0)
    arm.mem_write(BASE_PIXELS, stock_pixels)
    arm.reg_write(UC_ARM_REG_SP, STACK)
    put(BASE + 0xED0200, ARENA + 0x3F00, 0)
    packer_result = 0
    texture_limit = 8192
    in_stock_packer = False
    calls = []
    grant_icons = []

    def imported(uc, address, _size, _data):
        if in_stock_packer:
            return
        name = imports[address - BASE]
        r0, r1, r2 = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        calls.append(name)
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
        if name == "gl_get_integer":
            assert r0 == 0x0D33
            put(r1, texture_limit)
        elif name == "load_user_sprite_images":
            assert r0 == RENDERER
            assert words(BASE + NATIVE_ATLAS_STATE, 2) == (BITMAP, 8192)
            uc.reg_write(UC_ARM_REG_R0, packer_result)
        elif name == "erase_sprite_offset_tree":
            assert (r0, r1) == (RENDERER + 0x288, stale_offset)
        elif name == "new_object":
            assert r0 == 24
            uc.reg_write(UC_ARM_REG_R0, PACKED)
        elif name == "new_array":
            assert r0 == width * packed_height * 2
            uc.reg_write(UC_ARM_REG_R0, PACKED_PIXELS)
        elif name == "zero_bytes":
            assert (r0, r1) == (PACKED_PIXELS, width * (packed_height - height) * 2)
            uc.mem_write(r0, b"\0" * r1)
        elif name == "copy_bytes":
            assert r1 == BASE_PIXELS and r2 == len(stock_pixels)
            uc.mem_write(r0, bytes(uc.mem_read(r1, r2)))
        elif name in ("bitmap_destroy", "delete_object"):
            assert r0 == BITMAP
        elif name == "set_drawable_id":
            assert r0 == STACK + 0x800 - 0xBC
            length = uc.mem_read(r1, 1)[0] // 2
            grant_icons.append(bytes(uc.mem_read(r1 + 1, length)))
        else:
            raise AssertionError(f"Unexpected call to {name}")
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    active_imports = ("gl_get_integer", "load_user_sprite_images", "erase_sprite_offset_tree", "new_object", "new_array",
                      "zero_bytes", "copy_bytes", "bitmap_destroy", "delete_object", "set_drawable_id")
    imports = {NATIVE_ATLAS_IMPORTS[name]: name for name in active_imports}
    for address in imports:
        arm.hook_add(UC_HOOK_CODE, imported, begin=BASE + address, end=BASE + address)
    def execute(start, end, count=1000):
        arm.emu_start(BASE + start, BASE + end, count=count)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + end
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    for branch, _, symbol in MATERIAL_DUPLICATE_BRANCHES:
        material_kind = symbol.removeprefix("check_duplicate_")
        for file_index, action in ((0, "skip"), (1, "apply"), (2, "apply")):
            put(STACK + 0x170, file_index)
            arm.reg_write(UC_ARM_REG_CPSR, arm.reg_read(UC_ARM_REG_CPSR) & ~(1 << 30))
            execute(branch, NATIVE_ATLAS_IMPORTS[f"{action}_{material_kind}_definition"])

    icon_entry = ARENA + 0x3600
    arm.mem_write(icon_entry + 0x14, b"\x08Lock\0")
    arm.reg_write(UC_ARM_REG_R11, STACK + 0x800)
    for entry in (icon_entry, 0, icon_entry):
        arm.reg_write(UC_ARM_REG_R0, entry)
        execute(GRANT_ICON_HOOK, GRANT_ICON_HOOK + 12)
    assert grant_icons == [b"Lock", b"IconGrants", b"Lock"]
    calls.clear()

    arm.reg_write(UC_ARM_REG_R7, BITMAP)
    arm.reg_write(UC_ARM_REG_R9, RENDERER)
    stale_offset = ARENA + 0x3C00
    put(RENDERER + 0x288, stale_offset, stale_offset, 1)
    execute(0x8D26A4, 0x8D26A8)
    assert calls == ["erase_sprite_offset_tree", "gl_get_integer", "load_user_sprite_images"]
    assert words(RENDERER + 0x288, 3) == (RENDERER + 0x28C, 0, 0)
    assert arm.reg_read(UC_ARM_REG_R7) == BITMAP
    assert arm.reg_read(UC_ARM_REG_R8) == width
    calls.clear()
    put(RENDERER + 0x288, stale_offset, stale_offset, 1)
    texture_limit = height
    execute(0x8D26A4, 0x8D26A8)
    assert calls == ["erase_sprite_offset_tree", "gl_get_integer"]
    assert words(RENDERER + 0x288, 3) == (RENDERER + 0x28C, 0, 0)
    texture_limit = 8192

    def encode_rectangle(name, x, y, w, h):
        return (bytes([len(name) * 2]) + name.encode()).ljust(12, b"\0") + pack("<4I", x, y, w, h)

    free_list, packed_list, input_list = (STACK + offset for offset in (0x6C, 0x60, 0x94))
    rect_size = 28
    rect_data = ARENA + 0x2800
    for i, (name, (sheet, _)) in enumerate(sheets.items()):
        w, h = ((size + 31) // 32 * 32 for size in sheet.size)
        arm.mem_write(rect_data + i * rect_size, encode_rectangle(name, 0, 0, w, h))
    put(input_list, rect_data, len(sheets), len(sheets))
    put(BASE + NATIVE_ATLAS_STATE, BITMAP, 8192)
    in_stock_packer = True
    stock_hook = arm.hook_add(UC_HOOK_CODE, stock_import, begin=BASE + min(plt_symbols), end=BASE + max(plt_symbols))
    arm.reg_write(UC_ARM_REG_R2, free_list)
    execute(0x8D38C4, 0x8D38C8, count=10000)
    free_rect, _, count = words(free_list, 3)
    assert count == 1 and words(free_rect, 7) == (0, 0, 0, 0, height, width, 8192 - height)
    for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                               (free_list, input_list, packed_list, 32)):
        arm.reg_write(register, value)
    execute(0x8D3900, 0x8D3904, count=100000)
    arm.hook_del(stock_hook)
    in_stock_packer = False
    assert arm.reg_read(UC_ARM_REG_R0) == 1
    packed_data, _, count = words(packed_list, 3)
    assert count == len(sheets)
    placements = {}
    packed_records = {}
    for i in range(count):
        entry = packed_data + i * rect_size
        length = arm.mem_read(entry, 1)[0] // 2
        name = bytes(arm.mem_read(entry + 1, length)).decode()
        placements[name] = words(entry + 12, 4)
        packed_records[name] = entry
    assert placements.keys() == sheets.keys()
    packed_height = max(y + h for _, y, _, h in placements.values())
    assert packed_height <= 8192
    execute(0x8D3B78, NATIVE_ATLAS_IMPORTS["clear_old_sprite_offsets"])
    assert calls[-4:] == ["new_object", "new_array", "zero_bytes", "copy_bytes"]
    assert words(PACKED, 6) == (0x8033, width, packed_height, 0, PACKED_PIXELS, 0)
    assert words(STACK + 0x3c) == (PACKED,)

    expected = bytearray(width * (packed_height - height) * 2)
    uv_rectangles = set()
    for name, (sheet, materials) in sheets.items():
        sheet_w, sheet_h = sheet.size
        x, y, w, h = placements[name]
        assert height <= y and x + w <= width and sheet_w <= w and sheet_h <= h
        for other, (ox, oy, ow, oh) in placements.items():
            if other != name:
                assert x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y
        assert x % 32 == y % 32 == 0
        pixels = sheet.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
        arm.mem_write(SOURCE_PIXELS, pixels)
        put(SOURCE, 0x1401, sheet_w, sheet_h, 0, SOURCE_PIXELS, SOURCE_ROWS)
        put(SOURCE_ROWS, *(SOURCE_PIXELS + row * sheet_w * 4 for row in range(sheet_h)))
        # The original call passes the aligned rectangle's bottom edge and
        # retains its record in r5. Pixel expectations use the top edge.
        put(STACK, sheet_h, SOURCE, x, packed_height - y - h, sheet_w, sheet_h, 0)
        arm.reg_write(UC_ARM_REG_R5, packed_records[name])
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                                   (PACKED, 0, 0, sheet_w)):
            arm.reg_write(register, value)
        execute(0x8D3CD4, 0x8D3CD8, count=100 * sheet_w * sheet_h + 30 * sheet_h + 100)

        converted = rgba4444(pixels, sheet_w)
        stride = sheet_w * 2
        # Native Blit anchors PNG pixels to the bottom of the aligned rectangle.
        # For a 300px sheet in a 320px slot the 20 empty rows precede the PNG
        # in top-origin sprite coordinates, as expected by desktop mod frames.
        dst_y = packed_height - y - h
        for row in range(sheet_h):
            offset = ((row + dst_y) * width + x) * 2
            expected[offset:offset + stride] = converted[row * stride:(row + 1) * stride]
        sprites = list(sprite_records(materials))
        assert sprites, f"No sprite records found in {name}"
        for sprite in sprites:
            for sx, sy, sw, sh in sprite_frames(*sprite):
                assert (sx + sw) * 32 <= sheet_w and (sy + sh) * 32 <= sheet_h, (name, sprite, sx, sy, sw, sh)
                uv_rectangles.add((x // 32 + sx, y // 32 + sy, sw, sh))
    assert arm.mem_read(PACKED_PIXELS, len(expected)) == expected
    assert arm.mem_read(PACKED_PIXELS + (packed_height - height) * width * 2, len(stock_pixels)) == stock_pixels
    uv_rectangles = sorted(uv_rectangles)
    for rect, actual in zip(uv_rectangles, read_coordinates(apk, width, packed_height, uv_rectangles)):
        x, y, w, h = rect
        wanted = (x * 32 + .5, y * 32 + .5, w * 32 - 1, h * 32 - 1)
        assert all(isclose(a, b, abs_tol=.001) for a, b in zip(actual, wanted)), (rect, actual)

    x = width - 1
    y = packed_height - 1
    sample, = unpack("<H", stock_pixels[-2:])
    rgba = bytes(((sample >> shift) & 15) * 17 for shift in (12, 8, 4, 0))
    arm.reg_write(UC_ARM_REG_R1, x)
    arm.reg_write(UC_ARM_REG_R5, PACKED)
    arm.reg_write(UC_ARM_REG_R6, y)
    execute(0x91F730, NATIVE_ATLAS_IMPORTS["store_portrait_pixel"])
    assert arm.reg_read(UC_ARM_REG_R3) == unpack("<I", rgba)[0]
    image = ARENA + 0x3500
    put(image, PACKED)
    arm.reg_write(UC_ARM_REG_R0, image)
    arm.reg_write(UC_ARM_REG_R1, x)
    arm.reg_write(UC_ARM_REG_R2, y)
    arm.reg_write(UC_ARM_REG_LR, ARENA)
    arm.emu_start(BASE + 0xB42400, ARENA, count=100)
    assert arm.reg_read(UC_ARM_REG_PC) == ARENA
    assert arm.reg_read(UC_ARM_REG_SP) == STACK
    assert arm.reg_read(UC_ARM_REG_R0) == unpack("<I", rgba)[0]

    packer_result = PACKED
    calls.clear()
    execute(0x8D26A4, 0x8D26A8)
    assert calls == ["gl_get_integer", "load_user_sprite_images", "bitmap_destroy", "delete_object"]
    assert arm.reg_read(UC_ARM_REG_R7) == PACKED
    assert arm.reg_read(UC_ARM_REG_R8) == width
    print(f"{', '.join(mods)}: stock packer placed {len(sheets)} PNGs in a {width}x{packed_height} atlas;"
          f" {len(uv_rectangles)} directional frame UVs checked; original RGBA4444 bytes preserved.")


def composite_pixels(data):
    width, height, format_id = unpack_from("<3I", data, 8)
    assert format_id == 4
    pixels = decompress(data[40:])
    stride = width * 2
    assert len(pixels) == stride * height
    return width, height, b"".join(pixels[y:y + stride] for y in range(len(pixels) - stride, -1, -stride))


def verify_full_sheets(apk, obb, mod, complaints=None):
    coordinates = {"objects": (0, 0), "people": (0, 2048), "special-entities": (2048, 0)}
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    with ZipFile(obb) as archive, ZipFile(mod) as fixture:
        width, height, stock_pixels = composite_pixels(archive.read("data/tablet/composite.csimage"))
        images = {
            f"{prefix}data/{name}.png": Image.open(z.open(f"data/{name}.png")).convert("RGBA")
            for z, prefix in ((archive, ""), (fixture, "/mod/")) for name in coordinates
        }
        tileset_atlas = "data/tileset.csimage"
        tileset_bitmap = composite_pixels(archive.read(tileset_atlas))
        tileset_png = "data/tileset.png"
        tileset = Image.open(archive.open(tileset_png)).convert("RGBA")
        images[tileset_png] = tileset
        tileset_mod = "/mod/" + tileset_png
        images[tileset_mod] = tileset.copy()
        tile_edits = [(37, 113, (255, 224, 32, 255)), (1023, 513, (0, 0, 0, 0))]
        for x, y, pixel in tile_edits:
            original_pixel = tileset.getpixel((x, y))
            assert original_pixel[3] and original_pixel != pixel
            images[tileset_mod].putpixel((x, y), pixel)
        effects_atlas = "data/effects.csimage"
        effects_bitmap = composite_pixels(archive.read(effects_atlas))
        effects_path = "data/effects.bmp"
        assert effects_path.encode() in archive.read("data/mod_types.txt")
        bmp = archive.read(effects_path)
        raster, = unpack_from("<I", bmp, 10)
        effects_size = effects_bitmap[:2]
        assert bmp[:2] == b"BM" and unpack_from("<iiH", bmp, 18) == (*effects_size, 1)
        assert unpack_from("<HI", bmp, 28) == (32, 0)
        # The game's BMP reader retains the alpha bytes of the 32-bit BGRA bitmap.
        effects = Image.frombytes("RGBA", effects_size, bmp[raster:], "raw", "BGRA", 0, -1)
        images[effects_path] = effects
        lower_effects, wrong_effects, upper_effects = (
            f"/{folder}/{effects_path}" for folder in ("lower", "wrong", "upper")
        )
        lower_edits = [(47, 0, (255, 128, 0, 128)), (94, 0, (0, 255, 128, 96))]
        upper_edits = [(47, 0, (96, 0, 255, 192)), (141, 0, (0, 0, 0, 0))]
        for path, edits in ((lower_effects, lower_edits), (upper_effects, upper_edits)):
            images[path] = effects.copy()
            for x, y, pixel in edits:
                assert effects.getpixel((x, y))[3] and effects.getpixel((x, y)) != pixel
                images[path].putpixel((x, y), pixel)
        images[wrong_effects] = effects.crop((0, 0, 32, 32))
        title_atlas = "data/tablet/TextureAtlasses/TextureAtlasses.ui.csimage"
        title_width, title_height, title_pixels = composite_pixels(archive.read(title_atlas))
        title_bank = archive.read(title_atlas.replace(".csimage", ".spritebank"))
        assert b"Name LogoPAPauseMenu \tx 1 \ty 457 \tw 615 \th 254" in title_bank
        logo_path = "/mod/data/PAlogo.png"
        logo = fixture.read("data/PAlogo.png")
        images[logo_path] = Image.open(BytesIO(logo)).convert("RGBA")
        if complaints:
            complaint_atlas = "data/complaints.csimage"
            complaint_bank = "data/complaints.spritebank"
            complaint_png = "/mod/data/complaints.png"
            complaint_bitmap = composite_pixels(archive.read(complaint_atlas))
            pattern = rb"Name\s+(\w+)\s+x\s+(\d+)\s+y\s+0\s+w\s+1\s+h\s+1"
            stock_icons = [(name, int(x)) for name, x in re.findall(pattern, archive.read(complaint_bank))]
            with ZipFile(complaints) as fixture_icons:
                icon_png = fixture_icons.read("data/complaints.png")
                images[complaint_png] = Image.open(BytesIO(icon_png)).convert("RGBA")
                mod_icons = dict((name, int(x)) for name, x in re.findall(pattern, fixture_icons.read(complaint_bank)))
            ui_bank = title_atlas.replace(".csimage", ".spritebank")
            ui_icons = [(name, int(x), int(y), int(w), int(h)) for name, x, y, w, h in re.findall(
                rb"Name\s+(IconNeeds\w+)\s+x\s+(\d+)\s+y\s+(\d+)\s+w\s+(\d+)\s+h\s+(\d+)", title_bank
            )]
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(segment["p_vaddr"] + segment["p_memsz"] for segment in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x10000000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    app, app_slot, filesystem, reader, vtable, close, files = (ARENA + i * 0x100 for i in range(1, 8))
    baseline_rows = SOURCE_ROWS
    baseline_pixels = SOURCE_PIXELS
    mod_rows = ARENA + 0x1100000
    mod_pixels = ARENA + 0x1110000
    packed_pixels = PACKED_PIXELS
    selected = ""
    csimage = (title_width, title_height, title_pixels)
    effect_layers = ()
    png_headers = {logo_path: logo[:24]}
    header_file = None
    applied = []
    banks = {}

    def put(address, *values):
        arm.mem_write(address, pack(f"<{len(values)}I", *values))

    def c_string(at):
        value = bytearray()
        while len(value) < 1024:
            size = min(1024 - len(value), 4096 - at % 4096)
            chunk, terminator, _ = arm.mem_read(at, size).partition(b"\0")
            value.extend(chunk)
            if terminator:
                return value.decode()
            at += size
        raise AssertionError("Unterminated C string")

    def game_string(at):
        flags, _, data = unpack("<3I", arm.mem_read(at, 12))
        return c_string(data if flags & 1 else at + 1)

    imports = {BASE + NATIVE_ATLAS_IMPORTS[n]: n for n in (
        "get_mod_file_paths", "bitmap_destroy", "debug_log", "copy_bytes", "gl_get_integer"
    )}
    imports.update({BASE + SPRITE_REPLACEMENT_IMPORTS[n]: n for n in (
        "get_binary_reader", "decode_bitmap", "destroy_file_paths", "strlen", "strcmp", "strncmp",
        "fopen", "fread", "fclose", "memcmp", "__aeabi_uidiv"
    )})
    imports[BASE + NATIVE_ATLAS_IMPORTS["zero_bytes"]] = "zero_bytes"
    imports[close] = "close_reader"
    if complaints:
        png_headers[complaint_png] = icon_png[:24]
        imports.update({BASE + SPRITE_REPLACEMENT_IMPORTS[n]: n for n in
                        ("construct_sprite_bank", "destroy_sprite_bank", "load_sprite_bank_path", "lookup_sprite")})

    def intercept(uc, at, _size, _data):
        nonlocal selected, header_file
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = imports[at]
        result = 0
        if name == "get_mod_file_paths":
            logical = game_string(b)
            if logical == effects_path:
                assert a == app and d == 0
                put(c, files if effect_layers else 0, len(effect_layers), len(effect_layers))
                for index, path in enumerate(effect_layers):
                    value = files + 48 + index * 48
                    put(files + index * 12, 97, len(path), value)
                    uc.mem_write(value, path.encode() + b"\0")
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                return
            path = "/mod/" + logical
            storage = files
            if complaints and path in (complaint_png, "/mod/" + complaint_bank):
                assert unpack("<3I", uc.mem_read(a, 12)) == (0, 1, 1)
                if path.endswith(".spritebank"):
                    storage = files + 0x80
                    if not with_complaints:
                        put(c, 0, 0, 0)
                        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                        return
            else:
                assert a == app and path in images
            assert d == 0
            put(c, storage, 1, 1)
            put(storage, 97, len(path), storage + 12)
            uc.mem_write(storage + 12, path.encode() + b"\0")
        elif name == "get_binary_reader":
            selected = game_string(b)
            # The engine resolves a searched path to the mod's own file first,
            # which is why the stock baseline must be opened without searching.
            if not selected.startswith("/") and c and "/mod/" + selected in images:
                selected = "/mod/" + selected
            assert a == filesystem and selected in images
            result = reader
        elif name == "decode_bitmap":
            assert b == reader
            if game_string(c) == "csimage":
                w, h, pixels = csimage
                put(a, 0x8033, w, h, 0, packed_pixels, 0)
                uc.mem_write(packed_pixels, pixels)
            else:
                assert game_string(c) == selected.rsplit(".", 1)[-1]
                image = images[selected]
                w, h = image.size
                rows, pixels = (mod_rows, mod_pixels) if selected.startswith("/") else (baseline_rows, baseline_pixels)
                uc.mem_write(pixels, image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes())
                put(rows, *(pixels + 4 * w * row for row in range(h)))
                put(a, 0x1401, w, h, 0, pixels, rows)
        elif name == "copy_bytes":
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
        elif name == "strlen":
            result = len(c_string(a))
        elif name == "strcmp":
            result = int(c_string(a) != c_string(b))
        elif name == "strncmp":
            result = int(c_string(a)[:c] != c_string(b)[:c])
        elif name == "memcmp":
            result = int(uc.mem_read(a, c) != uc.mem_read(b, c))
        elif name == "fopen":
            assert c_string(a) in png_headers and c_string(b) == "rb"
            header_file = c_string(a)
            result = reader
        elif name == "fread":
            assert (b, c, d) == (1, 24, reader)
            uc.mem_write(a, png_headers[header_file])
            result = c
        elif name == "fclose":
            assert a == reader
        elif name == "__aeabi_uidiv":
            result = a // b
        elif name == "construct_sprite_bank":
            assert a not in banks
            banks[a] = {}
        elif name == "destroy_sprite_bank":
            del banks[a]
        elif name == "load_sprite_bank_path":
            filename = game_string(b)
            assert filename in (complaint_bank, "/mod/" + complaint_bank, ui_bank)
            if filename == ui_bank:
                entries = ui_icons
            else:
                icons = stock_icons if filename == complaint_bank else mod_icons.items()
                entries = [(label, x, 0, 1, 1) for label, x in icons]
            records = ARENA + (0x16000 if filename == "/mod/" + complaint_bank else 0x15000)
            addresses = [records + i * 64 for i in range(len(entries))]
            banks[a] = dict(zip((entry[0] for entry in entries), addresses, strict=True))
            for (label, x, y, w, h), address in zip(entries, addresses, strict=True):
                if len(label) <= 10:
                    uc.mem_write(address, (bytes([len(label) * 2]) + label).ljust(12, b"\0"))
                else:
                    put(address, 33, len(label), address + 32)
                    uc.mem_write(address + 32, label + b"\0")
                put(address + 12, x, y, w, h, 0)
            pointers = addresses[0] - 0x100
            flags = pointers + 128
            put(pointers, *addresses)
            uc.mem_write(flags, bytes([1] * len(entries)))
            put(a + 24, len(entries), pointers, flags)
        elif name == "lookup_sprite":
            result = banks[a].get(game_string(b).encode(), 0)
        elif name == "zero_bytes":
            uc.mem_write(a, bytes(b))
        elif name == "debug_log":
            assert c_string(a) in ("PATools atlas sheet: %s\n", "PATools image: %s\n",
                                   "PATools atlas sheet has incompatible dimensions: %s\n",
                                   "PATools menu title: %s\n", "PATools complaint icons: %s\n",
                                   "PATools needs panel icons: %s\n")
            applied.append(c_string(b))
        elif name == "gl_get_integer":
            put(b, height)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    with_complaints = False
    put(BASE + 0xED0200, app_slot)
    put(app_slot, app)
    put(app, 0, 1, 1)
    put(reader, vtable)
    put(vtable + 4, close)
    put(BITMAP, 0x8033, width, height, 0, packed_pixels, 0)
    arm.mem_write(packed_pixels, stock_pixels)
    for address in imports:
        arm.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address)
    arm.reg_write(UC_ARM_REG_R5, filesystem)
    arm.reg_write(UC_ARM_REG_R7, BITMAP)
    arm.reg_write(UC_ARM_REG_R9, RENDERER)
    arm.reg_write(UC_ARM_REG_SP, STACK)
    arm.emu_start(BASE + 0x8D26A4, BASE + 0x8D26A8, count=300_000_000)
    assert arm.reg_read(UC_ARM_REG_PC) == BASE + 0x8D26A8
    assert arm.reg_read(UC_ARM_REG_R5) == filesystem
    assert applied == [f"/mod/data/{name}.png" for name in coordinates]

    expected = bytearray(stock_pixels)
    for name, (x, y) in coordinates.items():
        original = images[f"data/{name}.png"].transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
        source = images[f"/mod/data/{name}.png"].transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
        converted = rgba4444(source, 2048)
        changed = 0
        for i, (old, new) in enumerate(zip(memoryview(original).cast("I"), memoryview(source).cast("I"))):
            if old != new and (old | new) >> 24:
                row, col = divmod(i, 2048)
                offset = ((height - y - 2048 + row) * width + x + col) * 2
                expected[offset:offset + 2] = converted[i * 2:i * 2 + 2]
                changed += 1
        assert changed > 0
        print(f"{name}.png: verified {changed} edited pixels in its corresponding quadrant")
    assert arm.mem_read(packed_pixels, len(expected)) == expected

    filesystem_slot, path, extension = (ARENA + i * 0x100 for i in range(8, 11))
    put(BASE + 0xED0D4C, filesystem_slot)
    put(filesystem_slot, filesystem)
    arm.mem_write(extension, b"\x0ecsimage\0")
    csimage = tileset_bitmap
    tile_width, tile_height, tile_pixels = tileset_bitmap
    tile_expected = bytearray(tile_pixels)
    for x, y, pixel in tile_edits:
        offset = 2 * ((tile_height - 1 - y) * tile_width + x)
        tile_expected[offset:offset + 2] = rgba4444(bytes(pixel), x=x, top=y)
    assert tile_expected != tile_pixels
    for filename in (tileset_atlas, tileset_atlas.removeprefix("data/")):
        put(path, 97, len(filename), path + 12)
        arm.mem_write(path + 12, filename.encode() + b"\0")
        for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, reader),
                           (UC_ARM_REG_R2, extension), (UC_ARM_REG_R7, path), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MENU_ATLAS_HOOK, BASE + MENU_ATLAS_HOOK + 4, count=100_000_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MENU_ATLAS_HOOK + 4
        assert applied[-1] == tileset_mod
        assert arm.mem_read(packed_pixels, len(tile_pixels)) == tile_expected
    print("Tileset PNG edits use the original map atlas coordinates and preserve every untouched pixel.")
    csimage = effects_bitmap
    effects_width, effects_height, effects_pixels = effects_bitmap
    effects_expected = bytearray(effects_pixels)
    for x, y, pixel in (*lower_edits, *upper_edits):
        offset = 2 * ((effects_height - 1 - y) * effects_width + x)
        effects_expected[offset:offset + 2] = rgba4444(bytes(pixel), x=x, top=y)
    assert effects_expected != effects_pixels
    for filename, effect_layers, expected in (
        (effects_atlas.removeprefix("data/"), (lower_effects, wrong_effects, upper_effects), effects_expected),
        (effects_atlas, (lower_effects, upper_effects), effects_expected),
        (effects_atlas, (wrong_effects,), effects_pixels),
        (effects_atlas, (), effects_pixels),
    ):
        put(path, 97, len(filename), path + 12)
        arm.mem_write(path + 12, filename.encode() + b"\0")
        for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, reader),
                           (UC_ARM_REG_R2, extension), (UC_ARM_REG_R7, path), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MENU_ATLAS_HOOK, BASE + MENU_ATLAS_HOOK + 4, count=100_000_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MENU_ATLAS_HOOK + 4
        assert arm.mem_read(packed_pixels, len(effects_pixels)) == expected
    print("Effects BMP edits honor mod priority and preserve stock pixels outside the changed locations.")
    csimage = (title_width, title_height, title_pixels)
    put(path, 97, len(title_atlas), path + 12)
    arm.mem_write(path + 12, title_atlas.encode() + b"\0")
    for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, reader),
                       (UC_ARM_REG_R2, extension), (UC_ARM_REG_R7, path), (UC_ARM_REG_SP, STACK)):
        arm.reg_write(reg, value)
    arm.emu_start(BASE + MENU_ATLAS_HOOK, BASE + MENU_ATLAS_HOOK + 4, count=100_000_000)
    assert arm.reg_read(UC_ARM_REG_PC) == BASE + MENU_ATLAS_HOOK + 4
    assert applied[-2:] == [logo_path, title_atlas]
    resized = arm.mem_read(packed_pixels, len(title_pixels))
    original = memoryview(title_pixels)
    bounds = []
    for y in range(title_height):
        start = y * title_width * 2
        end = start + title_width * 2
        in_frame = title_height - 457 - 254 <= y < title_height - 457
        if in_frame:
            assert resized[start:start + 2] == original[start:start + 2]
            assert resized[start + 616 * 2:end] == original[start + 616 * 2:end]
            colors = memoryview(resized)[start + 2:start + 616 * 2].cast("H")
            bounds.extend((x, y) for x, color in enumerate(colors) if color & 15)
        else:
            assert resized[start:end] == original[start:end]
    w = max(x for x, _ in bounds) - min(x for x, _ in bounds) + 1
    h = max(y for _, y in bounds) - min(y for _, y in bounds) + 1
    assert 5.0 < w / h < 5.5
    print("The desktop title keeps its aspect ratio and all pixels outside the tablet title frame are preserved.")
    if complaints:
        with_complaints = True
        csimage = complaint_bitmap
        put(path, 97, len(complaint_atlas), path + 12)
        arm.mem_write(path + 12, complaint_atlas.encode() + b"\0")
        for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, reader),
                           (UC_ARM_REG_R2, extension), (UC_ARM_REG_R7, path), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MENU_ATLAS_HOOK, BASE + MENU_ATLAS_HOOK + 4, count=100_000_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MENU_ATLAS_HOOK + 4
        assert not banks and applied[-2:] == [complaint_png, "/mod/" + complaint_bank]
        w, tile, pixels = complaint_bitmap
        expected = bytearray(pixels)
        source = images[complaint_png].transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        for label, dest in stock_icons:
            x = mod_icons[label] * tile
            icon = rgba4444(source.crop((x, 0, x + tile, tile)).tobytes(), tile)
            for y in range(tile):
                start = (y * w + dest * tile) * 2
                expected[start:start + tile * 2] = icon[y * tile * 2:(y + 1) * tile * 2]
        assert expected != pixels and arm.mem_read(packed_pixels, len(expected)) == expected
        print(f"Clearer Needs Icons: {len(stock_icons)} matching icons replaced with stock IDs and unrelated pixels preserved.")
        csimage = (title_width, title_height, title_pixels)
        put(path, 97, len(title_atlas), path + 12)
        arm.mem_write(path + 12, title_atlas.encode() + b"\0")
        for reg, value in ((UC_ARM_REG_R0, BITMAP), (UC_ARM_REG_R1, reader),
                           (UC_ARM_REG_R2, extension), (UC_ARM_REG_R7, path), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MENU_ATLAS_HOOK, BASE + MENU_ATLAS_HOOK + 4, count=100_000_000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MENU_ATLAS_HOOK + 4
        assert not banks and applied[-4:] == [complaint_png, "/mod/" + complaint_bank, logo_path, title_atlas]
        updated = arm.mem_read(packed_pixels, len(title_pixels))
        corrected = {b"Cloathing": b"Clothing", b"Enviroment": b"Environment"}
        expected = bytearray(resized)
        matched = 0
        for name, x, y, w, h in ui_icons:
            key = name.removeprefix(b"IconNeeds")
            if corrected.get(key, key) not in mod_icons:
                continue
            interval = ((title_height - y - h) * title_width + x) * 2
            assert any(updated[interval + row * title_width * 2:interval + row * title_width * 2 + w * 2] !=
                       resized[interval + row * title_width * 2:interval + row * title_width * 2 + w * 2] for row in range(h))
            for row in range(h):
                start = interval + row * title_width * 2
                expected[start:start + w * 2] = updated[start:start + w * 2]
            matched += 1
        assert matched == 18 and updated == expected
        print("Clearer Needs Icons: 18 matching tablet UI icons replaced, retaining all other atlas pixels.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("apk")
    parser.add_argument("obb")
    parser.add_argument("mods", nargs="+")
    parser.add_argument("--full-sheets", action="store_true")
    parser.add_argument("--complaints")
    args = parser.parse_args()
    if args.full_sheets:
        mod, = args.mods
        verify_full_sheets(args.apk, args.obb, mod, args.complaints)
    else:
        verify(args.apk, args.obb, args.mods)
