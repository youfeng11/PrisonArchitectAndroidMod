"""Exercise the v49 cold-start mod hook with a relocated ARM image."""

from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from re import MULTILINE, findall
from struct import pack, unpack
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_CPSR, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_SP,
)

from patch_profile import (
    BIOGRAPHY_READER_HOOK, CAMPAIGN_MAP_READER_HOOKS, DIALOG_READER_HOOK, DSP_EFFECTS_READER_HOOK,
    FRAGMENT_SHADER_READER_HOOK, GALLERY_IMAGE_HOOK, IMAGE_READER_HOOK, PRISONER_RECORDS_READER_HOOK,
    VERTEX_SHADER_READER_HOOK,
    EVENTS_LOAD_HOOK, EVENT_ENTRY_HOOK, EVENT_OVERLAY, JOB_ENTRY_HOOK, JOB_PATHS_HOOK,
    PREFAB_ENTRY_HOOK, PREFAB_PATHS_HOOK,
    FAST_LIST_INSERT, INITIALISE_MODS, INITIALISE_RENDERER, LIBRARY, LOAD_LANGUAGE_STRUCTURE, MOD_FILE_PATH_HOOKS,
    LANGUAGE_DUPLICATE_BRANCH, LANGUAGE_LABELS_HOOK, LANGUAGE_OVERLAY, MOD_LANGUAGE_HOOK, MOD_SELECTION_HOOK,
    MOD_FONT_LOAD_HOOK, NATIVE_ATLAS_IMPORTS, SUPPORTED_LOCALES_HOOK,
    READ_MOD_TYPES, SCRIPT_LIST_HOOK, SCRIPT_READER_HOOKS, SOUND_EVENT_HOOK, SOUND_GROUP_HOOK, SOUND_PATHS_HOOKS, SOUND_SAMPLE_HOOK,
    READER_EXTENSION_HOOKS, SOUND_EXTENSION_COMPARE_HOOKS,
    SPRITE_REPLACEMENT_IMPORTS, STARTUP_MOD_HOOK, branch,
)


def verify(apk, obb=None, mod_fixtures=True):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    base = 0x10000000
    app = 0x20000000
    renderer = app + 0x310
    stack = app + 0x3000
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(segment["p_vaddr"] + segment["p_memsz"] for segment in segments)
    arm.mem_map(base, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(base + segment["p_vaddr"], segment.data())
    arm.mem_map(app, 0x4000)
    arm.reg_write(UC_ARM_REG_R0, renderer)
    arm.reg_write(UC_ARM_REG_R4, app)
    arm.reg_write(UC_ARM_REG_SP, stack)
    calls = []

    def record_call(uc, address, _size, _data):
        calls.append((address - base, uc.reg_read(UC_ARM_REG_R0)))
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for target in (READ_MOD_TYPES, INITIALISE_MODS, INITIALISE_RENDERER):
        arm.hook_add(UC_HOOK_CODE, record_call, begin=base + target, end=base + target)
    resume = base + STARTUP_MOD_HOOK + 4
    arm.emu_start(base + STARTUP_MOD_HOOK, resume, count=200)
    assert calls == [(READ_MOD_TYPES, app), (INITIALISE_MODS, app), (INITIALISE_RENDERER, renderer)]
    assert arm.reg_read(UC_ARM_REG_PC) == resume
    assert arm.reg_read(UC_ARM_REG_SP) == stack
    if arm.mem_read(base + MOD_SELECTION_HOOK, 4) != pack("<I", branch(
        MOD_SELECTION_HOOK, SPRITE_REPLACEMENT_IMPORTS["split_game_string"], True
    )):
        verify_selection(arm, base, app, stack)
    if arm.mem_read(base + MOD_FILE_PATH_HOOKS[0], 4) != pack("<I", branch(
        MOD_FILE_PATH_HOOKS[0], SPRITE_REPLACEMENT_IMPORTS["concat_game_string"], True
    )):
        verify_script_paths(arm, base, app, stack, mod_fixtures)
    verify_font_priority(arm, base, app, stack)
    if mod_fixtures and arm.mem_read(base + SOUND_SAMPLE_HOOK, 4) != pack("<I", branch(
        SOUND_SAMPLE_HOOK, SPRITE_REPLACEMENT_IMPORTS["get_binary_reader"], True
    )):
        verify_asset_readers(arm, base, app, stack)
    if arm.mem_read(base + READER_EXTENSION_HOOKS[0], 4) != pack("<I", branch(
        READER_EXTENSION_HOOKS[0], 0x3B4668, True
    )):
        verify_sound_file_types(arm, base, app, stack)
    if arm.mem_read(base + SCRIPT_LIST_HOOK, 4) != pack("<I", branch(
        SCRIPT_LIST_HOOK, SPRITE_REPLACEMENT_IMPORTS["list_archive"], True
    )):
        verify_campaign_listing(arm, base, app, stack)
    if mod_fixtures and arm.mem_read(base + MOD_LANGUAGE_HOOK, 4) != pack("<I", branch(
        MOD_LANGUAGE_HOOK, LOAD_LANGUAGE_STRUCTURE, True
    )):
        verify_language_layers(arm, base, app, stack)
    has_chinese_picker = arm.mem_read(base + SUPPORTED_LOCALES_HOOK, 4) != pack("<I", branch(
        SUPPORTED_LOCALES_HOOK, SPRITE_REPLACEMENT_IMPORTS["set_supported_locales"], True
    ))
    if obb is not None:
        assert has_chinese_picker, "The APK is missing the Simplified Chinese picker entry."
        verify_chinese_resources(obb)
    if has_chinese_picker:
        verify_chinese_picker(arm, base, app, stack)
    if arm.mem_read(base + SOUND_EVENT_HOOK, 4) != pack("<I", branch(
        SOUND_EVENT_HOOK, SPRITE_REPLACEMENT_IMPORTS["clear_sound_event"], True
    )):
        verify_sound_definitions(arm, base, app, stack)
    if arm.mem_read(base + EVENTS_LOAD_HOOK, 4) != pack("<I", branch(
        EVENTS_LOAD_HOOK, SPRITE_REPLACEMENT_IMPORTS["load_events"], True
    )):
        verify_template_layers(arm, base, app, stack)


CHINESE_LABEL = "简体中文"


def verify_font_priority(arm, base, app, stack):
    # Run the original FontLoader from the first mod lookup to the success path.
    start = base + MOD_FONT_LOAD_HOOK - 8
    done = base + 0x78A150
    font_set, mods, records, mod_slot, items, strings = (
        app + offset for offset in (0x100, 0x180, 0x200, 0x350, 0x408, 0x580)
    )
    canary = app + 0x358
    arm.mem_write(base + 0xED01BC, pack("<I", canary))
    arm.mem_write(canary, pack("<I", 0xC0FFEE))
    arm.mem_write(base + 0xED0200, pack("<I", mod_slot))
    arm.mem_write(mod_slot, pack("<I", mods))
    roots = (b"/older/", b"/middle/", b"/newest/")
    arm.mem_write(mods, pack("<3I", records, len(roots), len(roots)))

    def read_game_string(address):
        _, size, data = unpack("<3I", arm.mem_read(address, 12))
        return bytes(arm.mem_read(data, size))

    def write_game_string(address, data, value):
        arm.mem_write(address, pack("<3I", (len(value) + 2) | 1, len(value), data))
        arm.mem_write(data, value + b"\0")

    def list_paths(uc, *_):
        assert uc.reg_read(UC_ARM_REG_R3) == 0
        layer, name, result = (
            uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)
        )
        requested = read_game_string(name)
        assert requested in (fnt, bmp)
        if layer == mods:
            candidates = roots
        else:
            record, capacity, count = unpack("<3I", uc.mem_read(layer, 12))
            index, remainder = divmod(record - records, 108)
            assert capacity == count == 1 and remainder == 0 and 0 <= index < len(roots)
            candidates = (roots[index],)
        assert bytes(uc.mem_read(result, 12)) == bytes(12)
        matching = [root + requested for root in candidates if root + requested in present]
        searched.extend(root + requested for root in candidates)
        if matching:
            uc.mem_write(result, pack("<3I", items, len(matching), len(matching)))
            uc.mem_write(items - 4, pack("<I", len(matching)))
            for index, candidate in enumerate(matching):
                write_game_string(items + index * 12, strings + index * 128, candidate)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def load_font(uc, *_):
        assert uc.reg_read(UC_ARM_REG_R0) == font_set
        assert uc.reg_read(UC_ARM_REG_R2) == uc.reg_read(UC_ARM_REG_R3) == 0
        candidate = read_game_string(uc.reg_read(UC_ARM_REG_R1))
        attempts.append(candidate)
        uc.reg_write(UC_ARM_REG_R0, int(candidate in usable))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def delete_paths(uc, *_):
        result = uc.reg_read(UC_ARM_REG_R0)
        data, capacity, count = unpack("<3I", uc.mem_read(result, 12))
        assert capacity == count
        if count:
            assert data == items and count == 1
            freed.append(read_game_string(data))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def return_to_caller(uc, *_):
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [
        arm.hook_add(UC_HOOK_CODE, callback, begin=base + offset, end=base + offset)
        for callback, offset in (
            (list_paths, NATIVE_ATLAS_IMPORTS["get_mod_file_paths"]),
            (load_font, SPRITE_REPLACEMENT_IMPORTS["load_bitmap_font"]),
            (delete_paths, SPRITE_REPLACEMENT_IMPORTS["destroy_file_paths"]),
            (return_to_caller, NATIVE_ATLAS_IMPORTS["delete_object"]),
            (return_to_caller, NATIVE_ATLAS_IMPORTS["delete_array"]),
        )
    ]
    fnt = b"data/fonts/cjk.fnt"
    bmp = b"data/fonts/cjk.bmp"
    older_fnt, middle_fnt, newest_fnt = (root + fnt for root in roots)
    newest_bmp = roots[-1] + bmp
    write_game_string(stack, app + 0x1100, fnt)
    write_game_string(stack + 12, app + 0x1180, bmp)
    try:
        for present, usable, expected, lookups in (
            ({older_fnt, newest_fnt, newest_bmp}, {older_fnt, newest_fnt, newest_bmp}, [newest_fnt], 1),
            ({older_fnt, newest_bmp}, {older_fnt, newest_bmp}, [newest_bmp], 2),
            ({older_fnt, newest_fnt, newest_bmp}, {older_fnt, newest_bmp}, [newest_fnt, newest_bmp], 2),
            ({middle_fnt, newest_fnt}, {middle_fnt}, [newest_fnt, middle_fnt], 3),
            ({newest_fnt}, {fnt}, [newest_fnt, fnt], 6),
            (set(), {bmp}, [fnt, bmp], 6),
        ):
            attempts, searched, freed = [], [], []
            arm.reg_write(UC_ARM_REG_R6, font_set)
            arm.reg_write(UC_ARM_REG_SP, stack)
            arm.emu_start(start, done, count=4000)
            assert arm.reg_read(UC_ARM_REG_PC) == done
            assert arm.reg_read(UC_ARM_REG_SP) == stack
            assert attempts == expected, (attempts, expected)
            assert len(searched) == lookups and len(set(searched)) == lookups
            assert freed == [name for name in attempts if name in present]
    finally:
        for hook in hooks:
            arm.hook_del(hook)
    print("Font overrides honor mod priority across FNT and BMP and retain the original fallback.")


def verify_chinese_resources(obb):
    with ZipFile(obb) as archive:
        locale = "data/language/simplifiedchinese/"
        for filename in ("base-language.txt", "fullgame.txt", "tablets.txt"):
            translation = archive.read(locale + filename).decode("utf-8-sig")
            has_chinese = any("\u4e00" <= character <= "\u9fff" for character in translation)
            if filename == "tablets.txt" and not has_chinese:
                # Some OBBs keep the tablet translation in the shared table.
                shared = archive.read("data/language/tablets.txt").decode("utf-8-sig")
                has_chinese = any("\u4e00" <= character <= "\u9fff" for character in shared)
            assert has_chinese, filename

        font = archive.read("data/fonts/cjk.fnt").decode("ascii")
        pages = dict(findall(r'^page id=(\d+) file="([^"]+)"', font, flags=MULTILINE))
        glyphs = dict(findall(r"^char +id=(\d+) +.*?\bpage=(\d+)", font, flags=MULTILINE))
        for character in CHINESE_LABEL:
            page = pages[glyphs[str(ord(character))]]
            assert archive.getinfo(f"data/fonts/{page}").file_size > 0, page
    print("The OBB includes Simplified Chinese base, fullgame, and tablet text and the picker label glyphs.")


def verify_chinese_picker(arm, base, app, stack):
    locales, records, labels = app + 0x820, app + 0x1800, app + 0x1a00
    stock_locales = (b"en", b"fr", b"it", b"de", b"es", b"pt", b"pt-br")
    stock_labels = ("English", "Français", "Italiano", "Deutsch", "Español", "Brasil português")
    selected_labels = list(stock_labels)
    destructor = app + 0x1b00
    requests = []
    imports = ("set_supported_locales", "assign_game_string", "append_locale_pair",
               "append_language_label", "register_static_destructor")
    functions = {base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in imports}

    def put_string(at, value):
        if len(value) <= 10:
            arm.mem_write(at, (bytes([len(value) * 2]) + value).ljust(12, b"\0"))
        else:
            payload = at + 0x400
            arm.mem_write(payload, value + b"\0")
            arm.mem_write(at, pack("<3I", 33, len(value), payload))

    def get_string(at):
        flags, length, data = unpack("<3I", arm.mem_read(at, 12))
        return bytes(arm.mem_read(data, length) if flags & 1 else arm.mem_read(at + 1, (flags & 255) // 2))

    def engine_call(uc, address, _size, _data):
        a, b, c = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        function = functions[address]
        requests.append(function)
        if function == "set_supported_locales":
            assert a == app
            for i, locale in enumerate(stock_locales):
                put_string(records + i * 24, locale)
            arm.mem_write(locales, pack("<3I", records, records + 7 * 24, records + 7 * 24))
        elif function == "assign_game_string":
            put_string(a, bytes(arm.mem_read(b, c)))
        elif function == "append_locale_pair":
            assert a == locales
            arm.mem_write(records + 7 * 24, bytes(arm.mem_read(b, 24)))
            arm.mem_write(locales, pack("<3I", records, records + 8 * 24, records + 8 * 24))
        elif function == "append_language_label":
            assert a == labels
            selected_labels.append(get_string(b).decode())
        else:
            assert (a, b, c) == (destructor, labels, 0x1234)
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, engine_call, begin=address, end=address) for address in functions]
    for at, values in ((SUPPORTED_LOCALES_HOOK, (app, 0, 0)), (LANGUAGE_LABELS_HOOK, (destructor, labels, 0x1234))):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2), values, strict=True):
            arm.reg_write(reg, value)
        arm.reg_write(UC_ARM_REG_SP, stack)
        arm.emu_start(base + at, base + at + 4, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + at + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
    assert requests == [imports[0], imports[1], imports[1], *imports[2:]]
    assert [get_string(records + i * 24) for i in range(8)] == [*stock_locales[:6], b"zh", stock_locales[6]]
    assert get_string(records + 6 * 24 + 12) == b"simplifiedchinese"
    assert selected_labels == [*stock_labels, CHINESE_LABEL]
    for hook in hooks:
        arm.hook_del(hook)
    print("The seventh language picker entry maps to the Simplified Chinese OBB locale.")


def verify_template_layers(arm, base, app, stack):
    mods_slot, table, records, source, entry, field, paths, array, owned, output = (
        app + n * 0x100 for n in range(1, 11)
    )
    overlays = base + EVENT_OVERLAY
    arm.mem_write(base + 0xED0200, pack("<I", mods_slot))
    arm.mem_write(mods_slot, pack("<I", app))
    original = b"data/events.txt"

    def set_string(at, value):
        assert len(value) <= 10
        arm.mem_write(at, (bytes([2 * len(value)]) + value).ljust(12, b"\0"))

    def game_string(at):
        flags, length, data = unpack("<3I", arm.mem_read(at, 12))
        return bytes(arm.mem_read(data, length)) if flags & 1 else bytes(arm.mem_read(at + 1, (flags & 255) // 2))

    def run(at, a, b, c=0, d=0):
        regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
        for register, value in zip(regs, (a, b, c, d)):
            arm.reg_write(register, value)
        arm.reg_write(UC_ARM_REG_SP, stack)
        arm.emu_start(base + at, base + at + 4, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + at + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
        return arm.reg_read(UC_ARM_REG_R0)

    imports = {base + SPRITE_REPLACEMENT_IMPORTS[n]: n for n in (
        "load_events", "destroy_file_paths", "append_event", "destroy_event", "initialise_event",
        "directory_data", "append_job", "append_prefab", "initialise_prefab", "strcmp"
    )}
    imports.update({base + NATIVE_ATLAS_IMPORTS[n]: n for n in (
        "get_mod_file_paths", "move_bytes", "copy_bytes", "new_array", "delete_array", "delete_object", "debug_log"
    )})
    imports[base + FAST_LIST_INSERT] = "fast_list_insert"
    calls = []
    mode = "events"
    active_paths = None
    prefab_calls = 0

    def intercepted(uc, at, _size, _data):
        nonlocal active_paths, prefab_calls
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = imports[at]
        result = 0
        if name == "get_mod_file_paths":
            if mode == "prefab":
                # list_prefab_files asks each layer for both prefab files.
                requested = game_string(b)
                assert d == 0 and a != app
                assert requested in (b"data/prefabs.txt", b"data/prefabs_dlc.txt")
                index = prefab_calls // 2
                prefab_calls += 1
                items = () if requested == b"data/prefabs.txt" else (b"ModADlc", b"ModBDlc")[index:index + 1]
                data, slots, used = unpack("<3I", uc.mem_read(c, 12))
                assert data == array and used + len(items) <= slots
                for item in items:
                    set_string(array + used * 12, item)
                    used += 1
                arm.mem_write(c + 8, pack("<I", used))
                active_paths = c
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
                return
            assert a == app
            active_paths = c
            if mode == "events":
                assert d == 0 and game_string(b) == original
                items = (b"/a/events", b"/b/events")
            else:
                assert d == 1 and c == paths
                items = (b"ModA", b"ModB", b"Base")
            for i, item in enumerate(items):
                set_string(array + i * 12, item)
            arm.mem_write(c, pack("<3I", array, len(items), len(items)))
        elif name == "load_events":
            assert a == table
            calls.append((game_string(b), uc.mem_read(overlays, 1)[0]))
        elif name == "destroy_file_paths":
            assert a == active_paths
        elif name == "debug_log":
            message = bytes(uc.mem_read(a, 48)).partition(b"\0")[0]
            assert message.startswith((b"PATools events:", b"PATools jobs:", b"PATools prefabs:"))
        elif name == "directory_data":
            assert a == entry and game_string(b) == b"Name"
            result = field
        elif name == "strcmp":
            left, right = (bytes(uc.mem_read(p, 32)).partition(b"\0")[0] for p in (a, b))
            result = int(left != right)
        elif name in ("move_bytes", "copy_bytes"):
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
        elif name == "fast_list_insert":
            data, slots, used = unpack("<3I", uc.mem_read(a, 12))
            assert data == array and used < slots
            uc.mem_write(data + used * 12, bytes(uc.mem_read(b, 12)))
            arm.mem_write(a + 8, pack("<I", used + 1))
            result = used
        elif name == "new_array":
            assert a == 8
            result = output
        elif name in ("append_event", "append_prefab", "append_job"):
            assert a == table and b == source
            calls.append((name, c))
            result = 2
        else:
            calls.append((name, a))
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, intercepted, begin=at, end=at) for at in imports]
    arm.mem_write(source, pack("<3I", 33, len(original), source + 32))
    arm.mem_write(source + 32, original + b"\0")
    run(EVENTS_LOAD_HOOK, table, source)
    assert calls == [(original, 0), (b"/a/events", 1), (b"/b/events", 1)]
    assert arm.mem_read(overlays, 1) == b"\0"

    calls.clear()
    arm.mem_write(table, pack("<7I", 0, 2, records, owned, 2, 0, 0))
    arm.mem_write(owned, b"\1\1")
    set_string(records + 24, b"Other")
    set_string(records + 80 + 24, b"Override")
    arm.mem_write(field + 12, pack("<I", 4))
    set_string(field + 28, b"Override")
    arm.reg_write(UC_ARM_REG_R6, entry)
    arm.mem_write(overlays, b"\1")
    assert run(EVENT_ENTRY_HOOK, table, source) == 1
    assert calls == [("destroy_event", records + 80), ("initialise_event", records + 80)]
    set_string(field + 28, b"Added")
    assert run(EVENT_ENTRY_HOOK, table, source) == 2 and calls[-1][0] == "append_event"
    arm.mem_write(overlays, b"\0")

    mode = "base-first"
    run(JOB_PATHS_HOOK, app, source, paths, 1)
    assert [game_string(array + 12 * i) for i in range(3)] == [b"Base", b"ModA", b"ModB"]
    mode = "prefab"
    prefab_path = b"data/prefabs.txt"
    arm.mem_write(source, pack("<3I", 33, len(prefab_path), source + 32))
    arm.mem_write(source + 32, prefab_path + b"\0")
    arm.mem_write(paths, pack("<3I", array, 8, 0))
    run(PREFAB_PATHS_HOOK, app, source, paths, 1)
    assert [game_string(array + 12 * i) for i in range(3)] == [b"data/prefabs.txt", b"ModADlc", b"ModBDlc"]

    calls.clear()
    arm.mem_write(table, pack("<3I", records, 4, 2))
    set_string(records, b"First")
    set_string(records + 40, b"Override")
    arm.mem_write(records + 68, pack("<3I", owned, 2, 2))
    set_string(source, b"Override")
    job_settings = bytes(range(16))
    arm.mem_write(source + 12, job_settings + pack("<3I", entry, 4, 2))
    arm.mem_write(entry, pack("<2I", 10, 20))
    assert run(JOB_ENTRY_HOOK, table, source, 2) == 1
    assert arm.mem_read(records + 52, 28) == job_settings + pack("<3I", output, 2, 2)
    assert arm.mem_read(output, 8) == pack("<2I", 10, 20) and calls == [("delete_array", owned)]
    set_string(source, b"Added")
    assert run(JOB_ENTRY_HOOK, table, source, 2) == 2 and calls[-1][0] == "append_job"

    calls.clear()
    arm.mem_write(records + 56, b"\0" * 56)
    set_string(records + 56, b"Override")
    arm.mem_write(records + 56 + 36, pack("<I", owned))
    set_string(field + 28, b"Override")
    arm.reg_write(UC_ARM_REG_R8, entry)
    assert run(PREFAB_ENTRY_HOOK, table, source, 2) == 1
    assert calls == [("delete_array", owned), ("initialise_prefab", records + 56)]
    set_string(field + 28, b"Added")
    assert run(PREFAB_ENTRY_HOOK, table, source, 2) == 2 and calls[-1][0] == "append_prefab"

    for hook in hooks:
        arm.hook_del(hook)
    print("Events, jobs and prefabs preserve original indices when overridden and append new names.")


def verify_sound_file_types(arm, base, app, stack):
    path, extension, expected = (app + n * 0x100 for n in range(1, 4))
    for hook in READER_EXTENSION_HOOKS:
        for candidate, suffix in (
            (b"/data/user/0/com.paradoxplaza.prisonarchitect/files/mods/sample.ogg", b".ogg"),
            (b"/mods/test.1/siren.close.WAV", b".WAV"),
            (b"/mods/test.1/sample", b""),
            (b"data/sounds/sample.wav", b".wav"),
        ):
            arm.mem_write(path, candidate + b"\0")
            arm.reg_write(UC_ARM_REG_R0, path)
            arm.reg_write(UC_ARM_REG_R1, ord("."))
            arm.reg_write(UC_ARM_REG_SP, stack)
            arm.emu_start(base + hook, base + hook + 4, count=1000)
            assert arm.reg_read(UC_ARM_REG_PC) == base + hook + 4
            result = path + len(candidate) - len(suffix) if suffix else 0
            assert arm.reg_read(UC_ARM_REG_R0) == result

    def compare(uc, address, _size, _data):
        a, b = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1))
        values = [bytes(uc.mem_read(p, 8)).partition(b"\0")[0].lower() for p in (a, b)]
        uc.reg_write(UC_ARM_REG_R0, int(values[0] != values[1]))
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    address = base + SPRITE_REPLACEMENT_IMPORTS["strcasecmp"]
    comparison = arm.hook_add(UC_HOOK_CODE, compare, begin=address, end=address)
    for hook, kind in zip(SOUND_EXTENSION_COMPARE_HOOKS, (b"wav", b"ogg")):
        arm.mem_write(expected, kind + b"\0")
        for actual, matches in ((kind.upper(), True), (b"mp3", False)):
            arm.mem_write(extension, b"\x06" + actual + b"\0")
            arm.reg_write(UC_ARM_REG_R0, extension)
            arm.reg_write(UC_ARM_REG_R1, expected)
            arm.reg_write(UC_ARM_REG_SP, stack)
            arm.emu_start(base + hook, base + hook + 4, count=100)
            assert arm.reg_read(UC_ARM_REG_PC) == base + hook + 4
            assert (arm.reg_read(UC_ARM_REG_R0) == 0) == matches
    arm.hook_del(comparison)
    print("Audio reader parses the basename extension on Android paths, ignoring case in the decoder.")


def verify_selection(arm, base, app, stack):
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    pref = app + 0x100
    path = app + 0x200
    names = app + 0x300
    arm.mem_write(pref, b"\x12Old Guard\0\0")
    lookup = {base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
              ("get_app_save_folder", "append_game_string", "assign_game_string",
               "fopen", "fread", "fclose", "split_game_string")}
    lookup[base + NATIVE_ATLAS_IMPORTS["delete_object"]] = "delete_object"
    lookup[base + FAST_LIST_INSERT] = "fast_list_insert"
    observed = []
    open_selection = None

    def import_call(uc, address, _size, _data):
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = lookup[address]
        result = 0
        if name == "get_app_save_folder":
            uc.mem_write(a, b"\x0c/files/\0\0\0\0\0")
        elif name == "append_game_string":
            assert uc.mem_read(b, c) == b"patools-active-mods.txt"
            complete = b"/files/patools-active-mods.txt"
            uc.mem_write(path, complete + b"\0")
            uc.mem_write(a, pack("<3I", 33, len(complete), path))
        elif name == "fopen":
            assert a == path and uc.mem_read(b, 3) == b"rb\0"
            result = int(open_selection is not None)
        elif name == "fread":
            assert (b, c, d) == (1, 4097, 1)
            uc.mem_write(a, open_selection)
            result = len(open_selection)
        elif name == "fclose":
            assert a == 1
        elif name == "delete_object":
            assert a in (path, path + 128)
        elif name == "assign_game_string":
            uc.mem_write(path + 128, bytes(uc.mem_read(b, c)) + b"\0")
            uc.mem_write(a, pack("<3I", 65, c, path + 128))
        elif name == "fast_list_insert":
            count, = unpack("<I", uc.mem_read(names + 8, 4))
            assert a == names and c == count
            _, length, data = unpack("<3I", uc.mem_read(b, 12))
            observed.append((10, bytes(uc.mem_read(data, length))))
            uc.mem_write(names + 8, pack("<I", count + 1))
        elif name == "split_game_string":
            assert c == names
            capacity, length, data = unpack("<3I", uc.mem_read(a, 12))
            if capacity & 1:
                value = bytes(uc.mem_read(data, length))
            else:
                value = bytes(uc.mem_read(a + 1, (capacity & 255) // 2))
            observed.append((b, value))
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in lookup]
    for open_selection in (None, b"", b"Batman Callout,Office Chair",
                           "\n警卫, 经典版\n\nOffice Chair\n".encode(), b"x" * 4097):
        arm.mem_write(names, bytes(12))
        arm.reg_write(UC_ARM_REG_R0, pref)
        arm.reg_write(UC_ARM_REG_R1, 44)
        arm.reg_write(UC_ARM_REG_R2, names)
        arm.emu_start(base + MOD_SELECTION_HOOK, base + MOD_SELECTION_HOOK + 4, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + MOD_SELECTION_HOOK + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
    assert observed == [(44, b"Old Guard"), (44, b""), (44, b"Batman Callout,Office Chair"),
                        (10, "警卫, 经典版".encode()), (10, b"Office Chair"), (44, b"Old Guard")]
    for hook in hooks:
        arm.hook_del(hook)
    print("The native mod loader uses the manager selection and falls back to legacy preferences if absent.")


def verify_script_paths(arm, base, app, stack, mod_fixtures):
    root, relative, result, storage, dirent = (app + i for i in (0x100, 0x200, 0x300, 0x400, 0x600))
    mod_root = b"/files/mods/test/"
    requested = mod_root + b"data/scripts/Batman.lua"
    path = b""
    listing = []
    next_entry = iter(())
    directories = {}
    exact = False
    lookup = {base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
              ("concat_game_string", "assign_game_string", "disk_file_exists", "strlen", "strcmp", "strcasecmp",
               "strncmp", "opendir", "readdir", "closedir")}
    lookup[base + NATIVE_ATLAS_IMPORTS["copy_bytes"]] = "copy_bytes"

    def string_at(uc, ptr):
        return bytes(uc.mem_read(ptr, 256)).split(b"\0", 1)[0]

    def import_call(uc, address, _size, _data):
        nonlocal path, next_entry
        a, b, c = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        name = lookup[address]
        returned = 0
        if name == "concat_game_string":
            assert (a, b, c) == (result, root, relative)
            path = requested
            uc.mem_write(storage, path + b"\0")
            uc.mem_write(result, pack("<3I", 65, len(path), storage))
        elif name == "assign_game_string":
            assert a == result
            path = bytes(uc.mem_read(b, c))
        elif name == "disk_file_exists":
            assert a == result
            returned = int(exact)
        elif name == "strlen":
            returned = len(string_at(uc, a))
        elif name == "strcmp":
            returned = int(string_at(uc, a) != string_at(uc, b))
        elif name == "strncmp":
            returned = int(string_at(uc, a)[:c] != string_at(uc, b)[:c])
        elif name == "strcasecmp":
            returned = int(string_at(uc, a).lower() != string_at(uc, b).lower())
        elif name == "copy_bytes":
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
        elif name == "opendir":
            folder = string_at(uc, a).removeprefix(mod_root[:-1])
            assert not exact and folder in directories
            next_entry = iter(directories[folder])
            returned = 1
        elif name == "readdir":
            assert a == 1
            entry = next(next_entry, None)
            if entry:
                uc.mem_write(dirent + 19, entry + b"\0")
                returned = dirent
        elif name == "closedir":
            assert a == 1
        uc.reg_write(UC_ARM_REG_R0, returned)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in lookup]
    original = b"Sample.ogg"
    if mod_fixtures:
        fixture = Path(__file__).resolve().parents[1] / "fixtures/mods/mods_2010s_Chinese_style_Prison_Mod.zip"
        with ZipFile(fixture) as archive:
            sample = next(n for n in archive.namelist() if n.startswith("data/sounds/") and n.endswith(".ogg"))
            original = sample.split("/")[-1].encode()
            assert original.lower()[:-4] in archive.read("data/sounds.txt").lower()

    for relative_path, exact, directories, expected in (
        (b"data/scripts/Batman.lua", False, {b"": [b"data"], b"/data": [b"Scripts"],
         b"/data/Scripts": [b"readme.txt", b"batman.lua"]}, b"data/Scripts/batman.lua"),
        (b"data/scripts/Batman.lua", True, {}, b"data/scripts/Batman.lua"),
        (b"data/scripts/Batman.lua", False, {b"": [b"data"], b"/data": [b"Scripts", b"SCRIPTS"]},
         b"data/scripts/Batman.lua"),
        (b"data/scripts/Batman.lua", False, {b"": [b"data"], b"/data": [b"SCRIPTS", b"Scripts", b"scripts"],
         b"/data/scripts": [b"batman.lua", b"BATMAN.lua", b"Batman.lua"]}, b"data/scripts/Batman.lua"),
        (b"data/sounds/" + original.lower(), False, {b"": [b"Data"], b"/Data": [b"Sounds"],
         b"/Data/Sounds": [original]}, b"Data/Sounds/" + original),
        (b"data/palogo.png", False, {b"": [b"data"], b"/data": [b"PAlogo.png"]}, b"data/PAlogo.png"),
        (b"data/language/simplifiedchinese/d11.txt", False, {b"": [b"data"], b"/data": [b"Language"],
         b"/data/Language": [b"SimplifiedChinese"], b"/data/Language/SimplifiedChinese": [b"D11.TXT"]},
         b"data/Language/SimplifiedChinese/D11.TXT"),
        (b"data/objects.png", False, {b"": [b"data"], b"/data": [b"Objects.PNG"]}, b"data/Objects.PNG"),
        (b"data/../manifest.txt", False, {b"": [b"data"]}, b"data/../manifest.txt"),
        (b"manifest.txt", False, {}, b"manifest.txt"),
    ):
        arm.mem_write(relative, pack("<3I", 65, len(relative_path), relative + 12))
        arm.mem_write(relative + 12, relative_path + b"\0")
        arm.mem_write(root, pack("<3I", 65, len(mod_root), root + 12))
        arm.mem_write(root + 12, mod_root + b"\0")
        requested = mod_root + relative_path
        for hook in MOD_FILE_PATH_HOOKS:
            arm.reg_write(UC_ARM_REG_R0, result)
            arm.reg_write(UC_ARM_REG_R1, root)
            arm.reg_write(UC_ARM_REG_R2, relative)
            arm.emu_start(base + hook, base + hook + 4, count=10000)
            assert arm.reg_read(UC_ARM_REG_PC) == base + hook + 4
            assert arm.reg_read(UC_ARM_REG_SP) == stack
            assert path == mod_root + expected
    for hook in hooks:
        arm.hook_del(hook)
    print("Mod assets resolve case differences at each path component, preferring exact spelling and rejecting ambiguity.")


def verify_asset_readers(arm, base, app, stack):
    path, filesystem, paths, slot, reader = (app + i for i in (0x100, 0x200, 0x300, 0x700, 0xf00))
    requested = b"data/sounds/sample.ogg"
    arm.mem_write(path, pack("<3I", 33, len(requested), path + 12))
    arm.mem_write(path + 12, requested + b"\0")
    arm.mem_write(base + 0xED0200, pack("<I", slot))
    lookups = {
        **{base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
           ("get_binary_reader", "get_text_reader", "destroy_file_paths", "strlen", "strcmp", "strncmp",
            "strcasecmp", "memcmp", "fopen", "fread", "fclose")},
        **{base + NATIVE_ATLAS_IMPORTS[name]: name for name in ("get_mod_file_paths", "copy_bytes", "debug_log")},
    }
    attempts = []
    searched = []
    reachable = set()
    palette_files = {}
    opened_palette = None
    gallery_reads = None
    gallery_headers_read = set()
    active = 0
    destroyed = 0
    archive_search = 1
    mod_records = app + 0x1100
    prefixes = (b"/older/", b"/newer/")
    arm.mem_write(app, pack("<3I", mod_records, 2, 2))

    def string_at(address):
        return bytes(arm.mem_read(address, 128)).partition(b"\0")[0]

    def game_string(address):
        flag, _, data = unpack("<3I", arm.mem_read(address, 12))
        return string_at(data if flag & 1 else address + 1)

    def import_call(uc, address, _size, _data):
        nonlocal destroyed, opened_palette
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = lookups[address]
        result = 0
        if name == "get_mod_file_paths":
            assert active == app and d == 0
            searched.append(game_string(b))
            if a == active:
                roots = prefixes
            else:
                item, capacity, count = unpack("<3I", uc.mem_read(a, 12))
                assert (capacity, count) == (1, 1) and item in (mod_records, mod_records + 108)
                roots = (prefixes[(item - mod_records) // 108],)
            entries = [prefix + searched[-1] for prefix in roots]
            uc.mem_write(c, pack("<3I", paths, len(entries), len(entries)))
            for i, entry in enumerate(entries):
                data = paths + 32 + i * 64
                uc.mem_write(paths + i * 12, pack("<3I", 65, len(entry), data))
                uc.mem_write(data, entry + b"\0")
        elif name in ("get_binary_reader", "get_text_reader"):
            assert a == filesystem
            sample = game_string(b)
            assert c == (archive_search if sample == requested else 0)
            attempts.append(sample)
            result = reader if sample in reachable else 0
        elif name == "destroy_file_paths":
            destroyed += 1
        elif name == "strlen":
            result = len(string_at(a))
        elif name == "strcmp":
            result = int(string_at(a) != string_at(b))
        elif name == "strcasecmp":
            result = int(string_at(a).lower() != string_at(b).lower())
        elif name == "strncmp":
            result = int(string_at(a)[:c] != string_at(b)[:c])
        elif name == "memcmp":
            result = int(uc.mem_read(a, c) != uc.mem_read(b, c))
        elif name == "fopen":
            assert opened_palette is None and string_at(b) == b"rb"
            filename = string_at(a)
            if gallery_reads is not None:
                gallery_reads.append(filename)
            if gallery_reads is not None and filename in reachable and (
                filename not in palette_files or filename in gallery_headers_read
            ):
                result = reader
            else:
                opened_palette = palette_files.get(filename)
                if gallery_reads is not None:
                    gallery_headers_read.add(filename)
                result = slot if opened_palette is not None else 0
        elif name == "fread":
            assert b == 1 and c == 24 and d == slot and opened_palette is not None
            uc.mem_write(a, opened_palette[:c])
            result = len(opened_palette[:c])
        elif name == "fclose":
            assert a == slot and opened_palette is not None
            opened_palette = None
        elif name == "debug_log":
            assert string_at(a) == b"PATools image: %s\n" and string_at(b) in palette_files
        else:
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
            result = a
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in lookups]

    def verify_lookup(hook, expected, queries):
        nonlocal destroyed
        attempts.clear()
        searched.clear()
        destroyed = 0
        arm.mem_write(slot, pack("<I", active))
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2),
                                   (filesystem, path, archive_search)):
            arm.reg_write(register, value)
        arm.reg_write(UC_ARM_REG_SP, stack)
        arm.emu_start(base + hook, base + hook + 4, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + hook + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
        assert arm.reg_read(UC_ARM_REG_R0) == reader
        assert attempts == expected and searched == queries and destroyed == len(queries)

    wav = requested[:-4] + b".wav"
    newer_ogg, older_ogg = [prefix + requested for prefix in reversed(prefixes)]
    newer_wav, older_wav = [prefix + wav for prefix in reversed(prefixes)]
    all_mod_paths = [newer_ogg, newer_wav, older_ogg, older_wav]
    all_queries = [requested, wav, requested, wav]
    for active, reachable, expected, queries in (
        (app, {newer_ogg, newer_wav}, all_mod_paths[:1], all_queries[:1]),
        (app, {newer_wav, older_ogg}, all_mod_paths[:2], all_queries[:2]),
        (app, {older_wav}, all_mod_paths, all_queries),
        (app, {requested}, all_mod_paths + [requested], all_queries),
        (0, {requested}, [requested], []),
    ):
        verify_lookup(SOUND_SAMPLE_HOOK, expected, queries)
    print("Sound samples honor mod priority across formats and prefer OGG within a single mod.")

    root = Path(__file__).resolve().parents[1]
    stock = next((root / "com.paradoxplaza.prisonarchitect").glob("*.obb"))
    with ZipFile(stock) as archive, ZipFile(root / "fixtures/mods/mods_2010s_Chinese_style_Prison_Mod.zip") as fixture:
        stock_paths = set(archive.namelist())
        changed_files = [next(n for n in fixture.namelist()
                              if n.startswith("data/campaign/") and n.endswith(ext) and n in stock_paths
                              and fixture.getinfo(n).CRC != archive.getinfo(n).CRC)
                         for ext in (".lua", ".prison")]
        images = [next(n for n in fixture.namelist()
                       if n.startswith(prefix) and n.endswith(".png") and n in stock_paths
                       and fixture.getinfo(n).CRC != archive.getinfo(n).CRC)
                  for prefix in ("data/campaign/", "data/advisers/")]
        clothing = "data/clothes.png"
        skin = "data/skin.png"
        assert fixture.getinfo(clothing).CRC != archive.getinfo(clothing).CRC
        palette_headers = {clothing: fixture.read(clothing)[:24], skin: archive.read(skin)[:24]}
        logo = "data/PAlogo.png"
        assert fixture.getinfo(logo).CRC != archive.getinfo(logo).CRC
        logo_header = fixture.read(logo)[:24]
        photo = "data/polaroids/canteen.png"
        standalone = "data/clipboard.png"
        photo_header = archive.read(photo)[:24]
        standalone_header = archive.read(standalone)[:24]
        bmp = "data/papersheet.bmp"
        assert archive.read(bmp)[:2] == b"BM"

    def check_override(hook, changed_path, original_flag, unrelated=None):
        nonlocal active, archive_search, reachable, requested
        archive_search = original_flag
        requested = changed_path.encode()
        arm.mem_write(path, pack("<3I", 97, len(requested), path + 12))
        arm.mem_write(path + 12, requested + b"\0")
        active = app
        mod_candidates = [b"/newer/" + requested, b"/older/" + requested]
        reachable = {mod_candidates[0]}
        verify_lookup(hook, mod_candidates[:1], [requested])
        reachable = {mod_candidates[1]}
        verify_lookup(hook, mod_candidates, [requested])
        reachable = {requested}
        verify_lookup(hook, mod_candidates + [requested], [requested])
        active = 0
        verify_lookup(hook, [requested], [])
        if unrelated is None:
            return
        active = app
        requested = unrelated
        arm.mem_write(path, pack("<3I", 97, len(requested), path + 12))
        arm.mem_write(path + 12, requested + b"\0")
        reachable = {requested}
        verify_lookup(hook, [requested], [])

    script_cases = (*((hook, flag, changed_files[0]) for hook, flag in zip(SCRIPT_READER_HOOKS, (1, 0))),
                    *((hook, 1, changed_files[1]) for hook in CAMPAIGN_MAP_READER_HOOKS))
    for hook, flag, changed_path in script_cases:
        if arm.mem_read(base + hook, 4) != pack("<I", branch(
            hook, SPRITE_REPLACEMENT_IMPORTS["get_text_reader"], True
        )):
            check_override(hook, changed_path, flag, b"/installed/mod/data/scripts/Guard.lua")
    print("Campaign script and map overrides follow mod priority and use the archive when absent.")
    for hook, path_name, flag in (
        (BIOGRAPHY_READER_HOOK, "data/biographies.txt", 1),
        (DSP_EFFECTS_READER_HOOK, "data/dsp-effects.txt", 1),
        (DIALOG_READER_HOOK, "data/dialogs/biography.txt", 1),
    ):
        assert path_name in stock_paths
        check_override(hook, path_name, flag)
    print("Prisoner biographies, DSP definitions and dialog layouts use the last available enabled mod or the original file.")
    for hook, shader in (
        (VERTEX_SHADER_READER_HOOK, "data/shaders/gles/lightmap.vs"),
        (FRAGMENT_SHADER_READER_HOOK, "data/shaders/gles/lightmap.fs"),
    ):
        assert shader in stock_paths
        check_override(hook, shader, 1)
    print("GLES vertex and fragment shader readers use mod priority and fall back to the archive.")
    if arm.mem_read(base + PRISONER_RECORDS_READER_HOOK, 4) != pack("<I", branch(
        PRISONER_RECORDS_READER_HOOK, SPRITE_REPLACEMENT_IMPORTS["get_text_reader"], True
    )):
        assert "data/names_in_the_game.txt" in stock_paths
        check_override(PRISONER_RECORDS_READER_HOOK, "data/names_in_the_game.txt", 0)
        print("Named prisoner records use mod priority and retain the original lookup when no mod supplies them.")
    if arm.mem_read(base + IMAGE_READER_HOOK, 4) != pack("<I", branch(
        IMAGE_READER_HOOK, SPRITE_REPLACEMENT_IMPORTS["get_binary_reader"], True
    )):
        for image in (*images, photo, bmp):
            check_override(IMAGE_READER_HOOK, image, 1, b"data/tablet/composite.csimage")
        requested = b"data/campaign/riot/snapshot.bmp"
        arm.mem_write(path, pack("<3I", 97, len(requested), path + 12))
        arm.mem_write(path + 12, requested + b"\0")
        reachable = {requested}
        verify_lookup(IMAGE_READER_HOOK, [requested], [])
        print("Campaign and adviser PNGs can override archive images through the original image loader.")
        for filename, header, invalid_width in (
            *((name, header, 1) for name, header in palette_headers.items()),
            ("data/palogo.png", logo_header, 0),
            (standalone, standalone_header, 0),
        ):
            requested = filename.encode()
            arm.mem_write(path, pack("<3I", 97, len(requested), path + 12))
            arm.mem_write(path + 12, requested + b"\0")
            newer, older = (prefix + requested for prefix in reversed(prefixes))
            reachable = {newer, older, requested}
            palette_files = {newer: header, older: header}
            verify_lookup(IMAGE_READER_HOOK, [newer], [requested])
            palette_files[newer] = header[:16] + pack(">2I", invalid_width, 128)
            verify_lookup(IMAGE_READER_HOOK, [older], [requested])
            palette_files[older] = b"truncated"
            verify_lookup(IMAGE_READER_HOOK, [requested], [requested])
            palette_files = {}
            verify_lookup(IMAGE_READER_HOOK, [requested], [requested])
        print("Standalone PNGs and palettes use mod priority and skip missing or invalid PNG headers.")

    encoded_photo = photo.encode()
    newer_photo, older_photo = (prefix + encoded_photo for prefix in reversed(prefixes))
    mode = app + 0x1200
    arm.mem_write(mode, b"rb\0")
    for filename, enabled, headers, expected, queries in (
        (encoded_photo, app, {newer_photo: photo_header}, [newer_photo, newer_photo], [encoded_photo]),
        (encoded_photo.removeprefix(b"data/"), app, {older_photo: photo_header, newer_photo: b"bad"},
         [newer_photo, older_photo, older_photo], [encoded_photo]),
        (encoded_photo, app, {}, [newer_photo, older_photo, encoded_photo], [encoded_photo]),
        (encoded_photo, 0, {}, [encoded_photo], []),
        (b"saves/polaroids/canteen.png", app, {}, [b"saves/polaroids/canteen.png"], []),
    ):
        active = enabled
        palette_files = headers
        reachable = {expected[-1]}
        gallery_reads = []
        gallery_headers_read.clear()
        searched.clear()
        destroyed = 0
        arm.mem_write(slot, pack("<I", active))
        arm.mem_write(path, filename + b"\0")
        for reg, value in ((UC_ARM_REG_R0, path), (UC_ARM_REG_R1, mode), (UC_ARM_REG_SP, stack)):
            arm.reg_write(reg, value)
        arm.emu_start(base + GALLERY_IMAGE_HOOK, base + GALLERY_IMAGE_HOOK + 4, count=20000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + GALLERY_IMAGE_HOOK + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
        assert arm.reg_read(UC_ARM_REG_R0) == reader
        assert gallery_reads == expected and searched == queries and destroyed == len(queries)
    print("Standalone interface images and packaged Polaroids accept mod textures, with original save paths retained.")
    for hook in hooks:
        arm.hook_del(hook)


def verify_campaign_listing(arm, base, app, stack):
    filesystem, directory, pattern, paths, entries, mod_entries, mods, slot = (
        app + i for i in (0x100, 0x200, 0x300, 0x400, 0x500, 0x900, 0xD00, 0xF00)
    )
    chapter = b"data/campaign/riot/"
    stock = [chapter + b"riot.lua", chapter + b"cutscene.lua"]
    extra = chapter + b"new_script.lua"
    another = chapter + b"another.lua"
    listing = {b"/first/data/campaign/riot/": [b"riot.lua", b"new_script.lua"],
               b"/second/Data/Campaign/Riot/": [b"NEW_SCRIPT.lua", b"another.lua"]}
    folders = {
        b"/first": [b"data"], b"/first/data": [b"campaign"], b"/first/data/campaign": [b"riot"],
        b"/second": [b"Data"], b"/second/Data": [b"Campaign"], b"/second/Data/Campaign": [b"Riot"],
    }
    directory_entry = app + 0x1400
    folder_entries = iter(())

    def put(address, *values):
        arm.mem_write(address, pack(f"<{len(values)}I", *values))

    def words(address, count):
        return unpack(f"<{count}I", arm.mem_read(address, count * 4))

    def string_at(address):
        return bytes(arm.mem_read(address, 128)).partition(b"\0")[0]

    def game_string(address):
        flags, _, data = words(address, 3)
        return string_at(data if flags & 1 else address + 1)

    def store_string(address, storage, value):
        put(address, 65, len(value), storage)
        arm.mem_write(storage, value + b"\0")

    store_string(directory, directory + 16, chapter)
    store_string(pattern, pattern + 16, b"*.lua")
    for offset, root in zip((0, 108), (b"/first/", b"/second/")):
        store_string(mods + offset, mods + offset + 16, root)
    put(app, mods, 2, 2)
    put(slot, app)
    put(base + 0xED0200, slot)
    imports = {base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
               ("list_archive", "list_directory", "destroy_file_paths", "strlen", "strcmp", "strncmp", "strcasecmp",
                "opendir", "readdir", "closedir")}
    imports[base + NATIVE_ATLAS_IMPORTS["copy_bytes"]] = "copy_bytes"
    imports[base + FAST_LIST_INSERT] = "insert"
    scanned = []

    def fill(out, start, values):
        put(out, start, 8, len(values))
        for i, value in enumerate(values):
            store_string(start + i * 12, start + 112 + i * 80, value)

    def import_call(uc, address, _size, _data):
        nonlocal folder_entries
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = imports[address]
        result = 0
        if name == "list_archive":
            assert (a, b, c, d) == (filesystem, directory, pattern, paths)
            assert words(uc.reg_read(UC_ARM_REG_SP), 2) == (1, 0)
            fill(d, entries, stock)
        elif name == "list_directory":
            assert game_string(b) == b"*.lua" and d == 1
            folder = game_string(a)
            scanned.append(folder)
            fill(c, mod_entries, [folder + n for n in listing[folder]])
        elif name == "opendir":
            folder_entries = iter(folders[string_at(a)])
            result = 1
        elif name == "readdir":
            assert a == 1
            entry = next(folder_entries, None)
            if entry:
                uc.mem_write(directory_entry + 19, entry + b"\0")
                result = directory_entry
        elif name == "closedir":
            assert a == 1
        elif name == "insert":
            assert a == paths and c == words(paths + 8, 1)[0]
            store_string(entries + c * 12, entries + 112 + c * 80, game_string(b))
            put(paths + 8, c + 1)
            result = c
        elif name == "strlen":
            result = len(string_at(a))
        elif name == "strcmp":
            result = int(string_at(a) != string_at(b))
        elif name == "strncmp":
            result = int(string_at(a)[:c] != string_at(b)[:c])
        elif name == "strcasecmp":
            result = int(string_at(a).lower() != string_at(b).lower())
        elif name == "copy_bytes":
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
            result = a
        else:
            assert words(a, 1) == (mod_entries,)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in imports]
    for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
                               (filesystem, directory, pattern, paths)):
        arm.reg_write(register, value)
    arm.reg_write(UC_ARM_REG_SP, stack)
    put(stack, 1, 0)
    arm.emu_start(base + SCRIPT_LIST_HOOK, base + SCRIPT_LIST_HOOK + 4, count=10000)
    assert arm.reg_read(UC_ARM_REG_PC) == base + SCRIPT_LIST_HOOK + 4
    assert arm.reg_read(UC_ARM_REG_SP) == stack
    assert scanned == list(listing)
    assert [game_string(entries + i * 12) for i in range(words(paths + 8, 1)[0])] == stock + [extra, another]
    for hook in hooks:
        arm.hook_del(hook)
    print("Campaign script discovery retains archive order and lists each new script once.")


def verify_language_layers(arm, base, app, stack):
    mods, slot, table, table_slot, path, stock = (app + n * 0x100 for n in range(1, 7))
    filenames = (b"d11.txt", b"base-language.txt", b"fullgame.txt", b"tablets.txt")
    prefixes = (b"/office/", b"/chinese-style/")
    root = b"data/language/"
    fixtures = Path(__file__).resolve().parents[1] / "fixtures/mods"
    with ZipFile(fixtures / "mods_Office_Chair.zip") as archive:
        office_paths = {n.encode() for n in archive.namelist() if n.startswith(root.decode())}
    with ZipFile(fixtures / "mods_2010s_Chinese_style_Prison_Mod.zip") as archive:
        locale_paths = {
            n.encode(): archive.read(n).decode("utf-8-sig").splitlines()
            for n in archive.namelist()
            if n.startswith(root.decode()) and n.rsplit("/", 1)[-1].encode() in filenames
            and (n.count("/") == 2 or n.split("/")[2] in ("german", "simplifiedchinese"))
        }
    phrase_values = {
        name: {parts[0]: parts[1] for line in lines
               if len(parts := line.split(maxsplit=1)) == 2
               and parts[0] in ("equipment_ModifiedHandgun", "interfacedeployment_patrols")}
        for name, lines in locale_paths.items()
    }
    listed = []
    loaded = []
    cleared = []
    phrases = {}

    def put(address, *values):
        arm.mem_write(address, pack(f"<{len(values)}I", *values))

    def string(address):
        return bytes(arm.mem_read(address, 112)).partition(b"\0")[0]

    def game_string(address):
        flags, _, data = unpack("<3I", arm.mem_read(address, 12))
        return string(data if flags & 1 else address + 1)

    def set_string(address, storage, value):
        put(address, 113, len(value), storage)
        arm.mem_write(storage, value + b"\0")

    put(app, mods, 2, 2)
    put(slot, app)
    put(base + 0xED0200, slot)
    put(table_slot, table)
    put(base + 0xED0218, table_slot)
    set_string(stock, stock + 12, b"data/language")
    imports = {base + NATIVE_ATLAS_IMPORTS[n]: n for n in
               ("load_language_table", "get_mod_file_paths", "copy_bytes")}
    imports.update({base + SPRITE_REPLACEMENT_IMPORTS[n]: n for n in ("strlen", "strcmp", "destroy_file_paths")})
    imports[base + LOAD_LANGUAGE_STRUCTURE] = "load_stock"

    def intercept(uc, address, _size, _data):
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = imports[address]
        ret = 0
        if name == "load_stock":
            assert b == stock
            loaded.append(game_string(b))
        elif name == "get_mod_file_paths":
            candidate = game_string(b)
            entry, cap, count = unpack("<3I", uc.mem_read(a, 12))
            assert (cap, count, d) == (1, 1, 0) and entry in (mods, mods + 108)
            i = (entry - mods) // 108
            listed.append((i, candidate))
            if candidate in (office_paths, locale_paths)[i]:
                put(c, path, 1, 1)
                set_string(path, path + 16, prefixes[i] + candidate)
        elif name == "load_language_table":
            assert a == table and c == 0
            assert uc.mem_read(base + LANGUAGE_OVERLAY, 1) == b"\x01"
            filename = game_string(b)
            loaded.append(filename)
            if filename.startswith(prefixes[1]):
                phrases.update(phrase_values[filename.removeprefix(prefixes[1])])
        elif name == "destroy_file_paths":
            cleared.append(a)
        elif name == "strlen":
            ret = len(string(a))
        elif name == "strcmp":
            ret = int(string(a) != string(b))
        else:
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
            ret = a
        uc.reg_write(UC_ARM_REG_R0, ret)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    hooks = [arm.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address) for address in imports]
    for locale, handgun in ((b"german", "Modifizierte Pistole"),
                            (b"simplifiedchinese", "改装过的手枪"),
                            (b"english", "Modified Handgun")):
        listed.clear()
        loaded.clear()
        cleared.clear()
        phrases.clear()
        set_string(stack + 40, stack + 64, locale)
        arm.reg_write(UC_ARM_REG_R1, stock)
        arm.reg_write(UC_ARM_REG_SP, stack)
        arm.emu_start(base + MOD_LANGUAGE_HOOK, base + MOD_LANGUAGE_HOOK + 4, count=20000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + MOD_LANGUAGE_HOOK + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack
        assert arm.mem_read(base + LANGUAGE_OVERLAY, 1) == b"\0"
        folders = (root,) if locale == b"english" else (root, root + locale + b"/")
        expected = [b"data/language"]
        for i, available in enumerate((office_paths, locale_paths)):
            expected.extend(prefixes[i] + folder + name for folder in folders for name in filenames
                            if folder + name in available)
        assert loaded == expected
        assert listed == [(i, folder + name) for i in range(2) for folder in folders for name in filenames]
        assert len(cleared) == len(listed)
        assert phrases["equipment_ModifiedHandgun"] == handgun
        if locale == b"simplifiedchinese":
            assert phrases["interfacedeployment_patrols"] == "民警巡逻"
    for hook in hooks:
        arm.hook_del(hook)
    for overlay, target in ((0, 0xAF2A50), (1, 0xAF2744)):
        arm.mem_write(base + LANGUAGE_OVERLAY, bytes([overlay]))
        arm.reg_write(UC_ARM_REG_CPSR, arm.reg_read(UC_ARM_REG_CPSR) & ~(1 << 30))
        arm.emu_start(base + LANGUAGE_DUPLICATE_BRANCH, base + target, count=20)
        assert arm.reg_read(UC_ARM_REG_PC) == base + target
    arm.mem_write(base + LANGUAGE_OVERLAY, b"\0")
    print("Mod translations include desktop d11 phrases and preserve shared, tablet and locale precedence.")


def verify_sound_definitions(arm, base, app, stack):
    paths, records, manager, values, existing, incoming = (app + n * 0x100 for n in range(1, 7))
    group, group_name = app + 0x700, app + 0x800
    stock_path = b"data/sounds.txt"
    layer_paths = (b"/mods/first/data/sounds.txt", b"/mods/second/data/sounds.txt", stock_path)
    cleared, removed, destroyed, freed = [], [], [], []
    found_group = 0

    def put(address, *values):
        arm.mem_write(address, pack(f"<{len(values)}I", *values))

    def words(address, n):
        return unpack(f"<{n}I", arm.mem_read(address, 4 * n))

    def string_at(address):
        return bytes(arm.mem_read(address, 80)).partition(b"\0")[0]

    def game_string(address):
        flags, _, data = words(address, 3)
        return string_at(data if flags & 1 else address + 1)

    lookups = {base + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
               ("strcmp", "strcasecmp", "clear_sound_event", "remove_sound_instance", "destroy_sound_instance",
                "find_sample_group", "create_sample_group", "destroy_sample_group")}
    lookups.update({base + NATIVE_ATLAS_IMPORTS[name]: name for name in
                    ("get_mod_file_paths", "move_bytes", "delete_object")})

    def import_call(uc, address, _size, _data):
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        name = lookups[address]
        result = 0
        if name == "strcmp":
            result = int(string_at(a) != string_at(b))
        elif name == "strcasecmp":
            result = int(string_at(a).lower() != string_at(b).lower())
        elif name == "get_mod_file_paths":
            assert c == paths and d == 1 and game_string(b) == stock_path
            put(paths, records, 3, 3)
            for i, path in enumerate(layer_paths):
                data = records + 40 + i * 50
                arm.mem_write(data, path + b"\0")
                put(records + i * 12, 49, len(path), data)
        elif name == "move_bytes":
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
            result = a
        elif name == "clear_sound_event":
            cleared.append(a)
        elif name == "remove_sound_instance":
            head, tail, count, revision = words(a, 4)
            node = head
            for _ in range(b):
                node = words(node + 4, 1)[0]
            instance, next_node, previous = words(node, 3)
            if previous:
                put(previous + 4, next_node)
            if next_node:
                put(next_node + 8, previous)
            put(a, head if previous else next_node, tail if next_node else previous, count - 1, revision + 1)
            removed.append(instance)
        elif name in ("destroy_sound_instance", "destroy_sample_group"):
            destroyed.append(a)
        elif name == "delete_object":
            freed.append(a)
        else:
            assert a == manager and b == group_name
            result = found_group if name == "find_sample_group" else group
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def run_hook(hook, *args):
        for reg, arg in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            arm.reg_write(reg, arg)
        arm.reg_write(UC_ARM_REG_SP, stack)
        arm.emu_start(base + hook, base + hook + 4, count=10000)
        assert arm.reg_read(UC_ARM_REG_PC) == base + hook + 4
        assert arm.reg_read(UC_ARM_REG_SP) == stack

    hooks = [arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in lookups]
    arm.mem_write(group_name, stock_path + b"\0")
    put(group_name + 32, 33, len(stock_path), group_name)
    for hook in SOUND_PATHS_HOOKS:
        run_hook(hook, app, group_name + 32, paths, 1)
        assert tuple(game_string(records + i * 12) for i in range(3)) == (stock_path, *layer_paths[:2])

    def event(address, offset, names):
        nodes = [app + offset + i * 32 for i in range(len(names))]
        for i, (node, name) in enumerate(zip(nodes, names)):
            arm.mem_write(node + 12, (bytes([len(name) * 2]) + name).ljust(12, b"\0"))
            put(node, node + 12, nodes[i + 1] if i + 1 < len(nodes) else 0, nodes[i - 1] if i else 0)
        put(address, nodes[0], nodes[-1], len(nodes), 0)
        return nodes

    base_nodes = event(existing, 0x900, [b"Place", b"Remove", b"PLACE"])
    mod_nodes = event(incoming, 0xA00, [b"place", b"Place", b"Use"])
    put(manager + 4, values)
    put(values + 4, existing)
    put(stack + 0x24, manager)
    put(stack + 8, paths)
    arm.reg_write(UC_ARM_REG_R7, 1)
    put(stack + 0x1c, 0)
    run_hook(SOUND_EVENT_HOOK, incoming)
    assert cleared == [incoming] and not removed
    put(stack + 0x1c, 1)
    run_hook(SOUND_EVENT_HOOK, incoming)
    assert removed == destroyed == freed == [base_nodes[0] + 12, base_nodes[2] + 12]
    assert words(existing, 4) == (base_nodes[1], mod_nodes[-1], 4, 3)
    assert words(base_nodes[1] + 4, 2) == (mod_nodes[0], 0)
    assert words(mod_nodes[0] + 4, 2) == (mod_nodes[1], base_nodes[1])
    assert words(incoming, 3) == (0, 0, 0)

    run_hook(SOUND_GROUP_HOOK, manager, group_name)
    assert arm.reg_read(UC_ARM_REG_R0) == group and group not in destroyed
    found_group = group
    run_hook(SOUND_GROUP_HOOK, manager, group_name)
    assert arm.reg_read(UC_ARM_REG_R0) == group and destroyed[-1] == group
    for hook in hooks:
        arm.hook_del(hook)
    print("Sound definitions load base first and preserve unrelated events and same-layer event instances.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("apk")
    parser.add_argument("--obb", help="Require the Chinese picker and check its assets in this OBB.")
    parser.add_argument("--no-mod-fixtures", action="store_true", help="Skip checks using local third-party mod ZIPs.")
    args = parser.parse_args()
    verify(args.apk, args.obb, mod_fixtures=not args.no_mod_fixtures)
    print("The relocated ARM startup hook calls both native mod routines before the renderer.")
