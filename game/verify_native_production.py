"""Exercise the v49 production overlay using production definitions from real ZIPs."""

from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from struct import pack, unpack
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
    UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_CPSR,
)

from patch_profile import (
    FAST_LIST_INSERT, FEMALE_NEEDS_PATHS_HOOK, LIBRARY, NATIVE_ATLAS_IMPORTS, NEEDS_MISSING_FILE_BRANCH, NEEDS_PATHS_HOOK,
    PROCESSOR_RULE_HOOK, PRODUCTION_LOAD_HOOK, PRODUCTION_OVERLAY,
    PRODUCTION_PATHS_HOOK, PRODUCTION_RULE_HOOK, SPRITE_REPLACEMENT_IMPORTS,
    REFORM_PROGRAM_PATHS_HOOK, RESEARCH_DUPLICATE_BRANCH, RESEARCH_PATHS_HOOK,
)


BASE = 0x10000000
ARENA = 0x20000000
STACK = ARENA + 0x4000
# FILES holds five 64-byte GameString records, so it spans 0x400 bytes.
PATHS, FILES = ARENA + 0x100, ARENA + 0x200
RULES, PROCESSORS, INPUT, RESOURCES = ARENA + 0x400, ARENA + 0x500, ARENA + 0x600, ARENA + 0x700
RULES_DATA, PROCESSORS_DATA, HEAP = (ARENA + i for i in (0x2000, 0x3000, 0x5000))
BASE_FILE, MOD_FILE, OVERRIDE_FILE = "data/production.txt", "/mods/logs/data/production.txt", "/mods/test/data/production.txt"
PROCESSORS_FILE = "data/processors.txt"
STANDALONE_FILE = "/mods/standalone/data/processors.txt"
OVERRIDE_PROCESSORS = "/mods/test/data/processors.txt"
MATCH_FIELDS = ("Rule", "Material", "Container", "Room", "StackInRoom", "Distribution", "MinSlotId", "MaxSlotId", "Condition")


def definitions(archive, name):
    kind = None
    depth = 0
    with ZipFile(archive) as zip_file:
        lines = zip_file.read(next(p for p in zip_file.namelist() if p.endswith(name))).decode().splitlines()
    for line in lines:
        fields = line.split(None, 1)
        if fields and fields[0] == "BEGIN":
            if not depth:
                kind, entries = fields[1].strip(), {}
            depth += 1
        elif fields and fields[0] == "END":
            depth -= 1
            if not depth:
                yield kind, entries
        elif depth == 1 and len(fields) == 2:
            entries[fields[0]] = fields[1].strip()


def verify(apk, obb, mod):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for segment in elf.iter_segments(type="PT_LOAD"):
        start = segment["p_vaddr"] & ~4095
        end = (segment["p_vaddr"] + segment["p_memsz"] + 4095) & ~4095
        arm.mem_map(BASE + start, end - start)
        arm.mem_write(BASE + segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x10000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    def put(address, *values):
        arm.mem_write(address, pack(f"<{len(values)}I", *values))

    def words(address, count=1):
        return unpack(f"<{count}I", arm.mem_read(address, 4 * count))

    def c_string(address):
        return bytes(arm.mem_read(address, 128)).partition(b"\0")[0].decode()

    def game_string(address):
        size, _, data = words(address, 3)
        return c_string(data if size & 1 else address + 1)

    file_addresses = {}
    for index, file in enumerate((BASE_FILE, MOD_FILE, STANDALONE_FILE, OVERRIDE_FILE, OVERRIDE_PROCESSORS)):
        address = FILES + index * 64
        put(address, 65, len(file), address + 12)
        arm.mem_write(address + 12, file.encode() + b"\0")
        file_addresses[file] = address
    put(RULES, RULES_DATA, 80, 0)
    put(PROCESSORS, PROCESSORS_DATA, 32, 0)

    ids = {"": 0}

    def encode(value):
        return ids.setdefault(value, len(ids))

    def parsed(entries):
        for kind, fields in entries:
            if kind == "ProductionRule":
                yield kind, tuple(encode(fields.get(key, "")) for key in MATCH_FIELDS + ("Processor",)), ()
            elif kind == "Processor":
                settings = [encode(fields.get(key, "")) for key in ("Processor", "Input", "InputCount", "Output", "OutputCount")]
                time, = unpack("<I", pack("<f", float(fields.get("OperatingTime", "0"))))
                yield kind, (*settings, time, 0), ()

    base = list(parsed(definitions(obb, "data/production.txt")))
    addon = list(parsed(definitions(mod, "data/production.txt")))
    assert len(addon) == 6
    with ZipFile(obb) as archive:
        assert PROCESSORS_FILE.encode() in archive.read("data/mod_types.txt")
    custom_processor = next(fields for kind, fields, _ in addon if kind == "Processor")
    custom_rule = next(fields for kind, fields, _ in addon if kind == "ProductionRule")
    standalone = [("Processor", (*custom_processor[:4], encode("6"), *custom_processor[5:]), (101, 102))]
    override = [("Processor", (*custom_processor[:4], encode("8"), *custom_processor[5:]), ()),
                ("ProductionRule", (*custom_rule[:-1], encode("Test Processor")), ())]
    final_processors = [("Processor", (*custom_processor[:4], encode("10"), *custom_processor[5:]), (201, 202))]
    layers = {
        BASE_FILE: base,
        MOD_FILE: addon,
        STANDALONE_FILE: standalone,
        OVERRIDE_FILE: override,
        OVERRIDE_PROCESSORS: final_processors,
    }
    mod_files = (
        {BASE_FILE: MOD_FILE},
        {PROCESSORS_FILE: STANDALONE_FILE},
        {BASE_FILE: OVERRIDE_FILE, PROCESSORS_FILE: OVERRIDE_PROCESSORS},
    )
    production_mods, production_records = ARENA + 0xC00, ARENA + 0xD00
    put(production_mods, production_records, len(mod_files), len(mod_files))
    production_lookups = []
    loaded = []
    logged = []
    freed = []
    heap = HEAP
    current_layer = []

    def layer_hook(uc, address, _size, _data):
        path = game_string(uc.reg_read(UC_ARM_REG_R1))
        loaded.append(path)
        assert bool(uc.mem_read(BASE + PRODUCTION_OVERLAY, 1)[0]) == (path != BASE_FILE)
        current_layer[:] = layers[path]
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    load = BASE + SPRITE_REPLACEMENT_IMPORTS["load_production_rules"]
    arm.hook_add(UC_HOOK_CODE, layer_hook, begin=load, end=load)
    imports = {BASE + SPRITE_REPLACEMENT_IMPORTS[name]: name for name in
               ("strcmp", "memcmp", "append_processor_rule", "append_production_rule")}
    imports.update({BASE + NATIVE_ATLAS_IMPORTS[name]: name for name in
                    ("get_mod_file_paths", "new_array", "delete_array", "copy_bytes", "move_bytes", "debug_log")})
    imports[BASE + FAST_LIST_INSERT] = "fast_list_insert"
    paths_expected = tuple(layers)

    def append_path(address):
        data, capacity, count = words(PATHS, 3)
        assert count < capacity
        put(data + count * 12, *words(address, 3))
        put(PATHS + 8, count + 1)
        return count

    def import_call(uc, address, _size, _data):
        nonlocal heap
        name = imports[address]
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
        result = 0
        if name == "get_mod_file_paths":
            requested = game_string(b)
            assert c == PATHS
            if a == production_mods:
                # The preceding APK asks the stock function only for production.txt.
                assert requested == BASE_FILE and d == 1
                for path in (MOD_FILE, OVERRIDE_FILE, BASE_FILE):
                    append_path(file_addresses[path])
            elif requested in (BASE_FILE, PROCESSORS_FILE):
                record, capacity, count = words(a, 3)
                layer, remainder = divmod(record - production_records, 108)
                assert capacity == count == 1 and remainder == 0 and 0 <= layer < len(mod_files) and d == 0
                production_lookups.append((layer, requested))
                path = mod_files[layer].get(requested)
                if path:
                    append_path(file_addresses[path])
            else:
                base_file, *mod_paths = paths_expected
                assert (requested, d) == (base_file, 1)
                put(PATHS, PATHS + 12, 3, 3)
                for i, path in enumerate((*mod_paths, base_file)):
                    put(PATHS + 12 + i * 12, *words(file_addresses[path], 3))
        elif name == "fast_list_insert":
            assert a == PATHS and c == words(PATHS + 8)[0]
            result = append_path(b)
        elif name == "debug_log":
            assert c_string(a) == "PATools production: %s (%d total production rules)\n"
            assert not uc.mem_read(BASE + PRODUCTION_OVERLAY, 1)[0]
            logged.append(c_string(b))
        elif name in ("copy_bytes", "move_bytes", "assign_research_string"):
            uc.mem_write(a, bytes(uc.mem_read(b, c)))
            result = a
        elif name == "copy_research_string":
            uc.mem_write(a, bytes(uc.mem_read(b, 12)))
            result = a
        elif name == "strcmp":
            result = int(c_string(a) != c_string(b))
        elif name == "memcmp":
            result = int(uc.mem_read(a, c) != uc.mem_read(b, c))
        elif name == "new_array":
            result = heap
            heap += (a + 7) & ~7
        elif name == "delete_array":
            freed.append(a)
        else:
            assert c == words(a + 8)[0]
            size = 40 if name == "append_production_rule" else 56
            uc.mem_write(words(a)[0] + size * c, bytes(uc.mem_read(b, size)))
            put(a + 8, c + 1)
            result = c
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    import_hooks = {address: arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address) for address in imports}

    def execute(hook, a, b, c=0, d=0):
        for register, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), (a, b, c, d)):
            arm.reg_write(register, value)
        arm.reg_write(UC_ARM_REG_SP, STACK)
        arm.emu_start(BASE + hook, BASE + hook + 4, count=100000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + hook + 4
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    put(PATHS, PATHS + 12, 8, 0)
    execute(PRODUCTION_PATHS_HOOK, production_mods, file_addresses[BASE_FILE], PATHS, 1)
    assert tuple(game_string(PATHS + 12 + i * 12) for i in range(words(PATHS + 8)[0])) == paths_expected
    assert production_lookups == [(i, path) for i in range(len(mod_files)) for path in (BASE_FILE, PROCESSORS_FILE)]
    for i in range(len(paths_expected)):
        execute(PRODUCTION_LOAD_HOOK, ARENA, PATHS + 12 + i * 12)
        assert not arm.mem_read(BASE + PRODUCTION_OVERLAY, 1)[0]
        # Execute the parser's insertion sites with the records that would be
        # read from this layer. The loader's flag is live only during parsing.
        arm.mem_write(BASE + PRODUCTION_OVERLAY, bytes([i > 0]))
        for kind, fields, resources in current_layer:
            if kind == "ProductionRule":
                put(INPUT, *fields)
                execute(PRODUCTION_RULE_HOOK, RULES, INPUT, words(RULES + 8)[0])
            else:
                if resources:
                    put(RESOURCES, *resources)
                put(INPUT, *fields, RESOURCES if resources else 0, len(resources), len(resources), 0, 0, 0, 0)
                execute(PROCESSOR_RULE_HOOK, PROCESSORS, INPUT, words(PROCESSORS + 8)[0])
                if i > 0:
                    index = words(PROCESSORS + 8)[0] - 1
                    assert words(PROCESSORS_DATA + 56 * index, 7) == fields
        arm.mem_write(BASE + PRODUCTION_OVERLAY, b"\0")

    assert loaded == list(layers)
    assert logged == list(layers)[1:]
    production = [words(RULES_DATA + 40 * i, 10) for i in range(words(RULES + 8)[0])]
    processors = [words(PROCESSORS_DATA + 56 * i, 14) for i in range(words(PROCESSORS + 8)[0])]
    before_rules = [fields for kind, fields, _ in base if kind == "ProductionRule"]
    assert production[:len(before_rules)] == before_rules and len(production) == len(before_rules) + 5
    assert override[1][1] in production and custom_rule not in production
    before_processors = [fields for kind, fields, _ in base if kind == "Processor"]
    assert [p[:7] for p in processors[:-1]] == before_processors
    assert processors[-1][:7] == final_processors[0][1]
    pointer, capacity, count = processors[-1][7:10]
    assert pointer != RESOURCES and capacity == count == 2 and words(pointer, count) == (201, 202)
    assert freed == [HEAP]
    print(f"Preserved {len(before_rules)} base production rules and {len(before_processors)} processors. "
          "Standalone processors.txt and production.txt merge in mod order without changing unrelated records.")

    for file, hook in (("data/reform_programs.txt", REFORM_PROGRAM_PATHS_HOOK),
                       ("data/research.txt", RESEARCH_PATHS_HOOK)):
        assert list(definitions(obb, file))
        paths_expected = (file, f"/mods/first/{file}", f"/mods/second/{file}")
        for i, path in enumerate(paths_expected):
            address = FILES + i * 64
            put(address, 65, len(path), address + 12)
            arm.mem_write(address + 12, path.encode() + b"\0")
            file_addresses[path] = address
        execute(hook, ARENA, file_addresses[file], PATHS, 1)
        assert tuple(game_string(PATHS + 12 + i * 12) for i in range(3)) == paths_expected
    print("Reform programs and research load the base file before the two mod layers in their selected order.")

    def verify_needs_paths():
        common, female = "data/needs.txt", "data/needs-female.txt"
        assert any(kind == "Need" and fields.get("Name") == "Comfort" for kind, fields in definitions(obb, common))
        assert any(kind == "Need" for kind, _ in definitions(obb, female))
        office_chair = Path(__file__).resolve().parents[1] / "fixtures/mods/mods_Office_Chair.zip"
        (kind, provider), = definitions(office_chair, common)
        assert (kind, provider["Object"], provider["PrimaryNeed"]) == ("Provider", "OfficeChair", "Comfort")
        layer_files = [{common}, {common, female}]
        mod_paths = [f"/mods/{i}/{name}" for i, files in enumerate(layer_files) for name in (common, female) if name in files]
        paths = [common, female, *mod_paths]
        addresses = {}
        for i, path in enumerate(paths):
            address = ARENA + 0x800 + i * 64
            put(address, 65, len(path), address + 12)
            arm.mem_write(address + 12, path.encode() + b"\0")
            addresses[path] = address

        mods, records = ARENA + 0xA00, ARENA + 0xB00
        put(mods, records, 2, 2)
        put(PATHS, PATHS + 12, 8, 0)
        original_calls = []

        def append_path(address):
            data, _, count = words(PATHS, 3)
            put(data + count * 12, *words(address, 3))
            put(PATHS + 8, count + 1)
            return count

        def list_call(uc, address, _size, _data):
            a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
            assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0
            if address == files_import:
                item, capacity, count = words(a, 3)
                assert (capacity, count, c, d) == (1, 1, PATHS, 0)
                layer = (item - records) // 108
                assert item == records + layer * 108 and layer in (0, 1)
                name = game_string(b)
                if name in layer_files[layer]:
                    append_path(addresses[f"/mods/{layer}/{name}"])
                original_calls.append((layer, name))
            else:
                assert a == PATHS and c == words(PATHS + 8)[0]
                uc.reg_write(UC_ARM_REG_R0, append_path(b))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        files_import = BASE + NATIVE_ATLAS_IMPORTS["get_mod_file_paths"]
        insert_import = BASE + FAST_LIST_INSERT
        for address in (files_import, insert_import):
            arm.hook_del(import_hooks[address])
        hooks = [arm.hook_add(UC_HOOK_CODE, list_call, begin=address, end=address)
                 for address in (files_import, insert_import)]
        for female_prison in (False, True):
            original_calls.clear()
            put(PATHS + 8, 0)
            if female_prison:
                execute(FEMALE_NEEDS_PATHS_HOOK, mods, addresses[female], PATHS, 1)
            execute(NEEDS_PATHS_HOOK, mods, addresses[common], PATHS, 1)
            expected = [female, common, *mod_paths] if female_prison else [common, *mod_paths[:2]]
            assert [game_string(PATHS + 12 + i * 12) for i in range(words(PATHS + 8)[0])] == expected
            assert original_calls == [(i, name) for i in range(2) for name in ((common, female) if female_prison else (common,))]
        for hook in hooks:
            arm.hook_del(hook)

        # Enter the real loop tail with the failure flag set and a valid layer remaining.
        arm.reg_write(UC_ARM_REG_CPSR, arm.reg_read(UC_ARM_REG_CPSR) & ~(1 << 30))
        arm.reg_write(UC_ARM_REG_R4, 1)
        arm.reg_write(UC_ARM_REG_R8, 0)
        arm.reg_write(UC_ARM_REG_R11, STACK + 0x100)
        put(STACK + 0x100 - 0x2C, 2)
        arm.emu_start(BASE + NEEDS_MISSING_FILE_BRANCH, BASE + 0x9ED370, count=5)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + 0x9ED370 and arm.reg_read(UC_ARM_REG_R8) == 1
        print("Need providers load after the base needs and a missing layer does not stop the reader.")

    verify_needs_paths()

    # Run the engine's own assignment path with an already populated slot.
    # The branch sees a nonzero string comparison because its name is present.
    items, item, names, name_slot = ARENA + 0x6000, ARENA + 0x6500, ARENA + 0x6800, ARENA + 0x6900
    index = 3
    slot = items + index * 76
    research = {fields.get("Name"): fields for kind, fields in definitions(obb, "data/research.txt")
                if kind == "Research"}
    security = research["Security"]
    assert security["Requires"] == "Warden"
    name = b"\x10Security\0\0\0"
    arm.mem_write(slot, name)
    arm.mem_write(item, name)
    stock = (1, 1, 1, 9, 21, 360, 0, 0, 0, 0, 0, 0, 0)
    overlay = (1, 6, 1, 9, 50, 90, 0, 0, 0, 0, 0, 0, 0)
    put(slot + 24, *stock)
    put(item + 24, *overlay)
    put(name_slot, names)
    put(STACK + 4, name_slot)
    put(STACK + 0x28, item + 24)
    for address, operation in ((BASE + 0x3AC658, "copy_research_string"),
                               (BASE + 0x3ACE74, "assign_research_string")):
        imports[address] = operation
        arm.hook_add(UC_HOOK_CODE, import_call, begin=address, end=address)
    arm.reg_write(UC_ARM_REG_SP, STACK)
    for register, value in ((UC_ARM_REG_R4, slot), (UC_ARM_REG_R5, items),
                            (UC_ARM_REG_R7, item), (UC_ARM_REG_R10, index)):
        arm.reg_write(register, value)
    arm.reg_write(UC_ARM_REG_CPSR, arm.reg_read(UC_ARM_REG_CPSR) & ~(1 << 30))
    arm.emu_start(BASE + RESEARCH_DUPLICATE_BRANCH, BASE + 0xA468A8, count=1000)
    assert arm.reg_read(UC_ARM_REG_PC) == BASE + 0xA468A8
    assert words(slot + 24, 13) == overlay
    assert game_string(slot) == game_string(names + index * 12) == "Security"
    assert not any(arm.mem_read(items, 3 * 76))
    print("A research override writes to the existing engine ID and updates its prerequisite and settings.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("apk")
    parser.add_argument("obb")
    parser.add_argument("mod")
    args = parser.parse_args()
    verify(args.apk, args.obb, args.mod)
