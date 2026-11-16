"""Exercise custom staff definitions and the patched v49 ARM factory/AI hooks."""

from argparse import ArgumentParser
from io import BytesIO
from struct import pack, unpack_from
from zipfile import ZipFile
import re

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R7, UC_ARM_REG_R10, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_R6,
)
from patch_profile import (
    LIBRARY, TOOLBAR_ICON_HOOK, DEFAULT_STAFF_STATE, DEFAULT_STAFF_FACTORY_HOOK,
    DEFAULT_STAFF_HANGOUT_HOOKS, DEFAULT_STAFF_TIRED_HOOK,
    DEFAULT_STAFF_HANGOUT_UPDATE_HOOK,
    SPRITE_REPLACEMENT_IMPORTS, NATIVE_ATLAS_IMPORTS,
)

BASE, ARENA = 0x10000000, 0x20000000
STACK, ENTRY, NAME, TARGET, FILE, APP = (ARENA + i * 0x1000 for i in range(1, 7))
STOP = ARENA + 0x7000


def verify(apk, mod):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    with ZipFile(mod) as archive:
        path = next(n for n in archive.namelist() if n.endswith('data/materials.txt'))
        material = archive.read(path).decode('utf-8-sig').split('BEGIN Object', 2)[1]
        production = archive.read(path.removesuffix('materials.txt') + 'production.txt').decode('utf-8-sig')
    properties = re.findall(r'^\s*Properties\s+(\w+)', material, re.M)
    room = re.search(r'^\s*HangOutRoom\s+(\w+)', material, re.M)[1]
    assert len(re.findall(r'BEGIN\s+Sprite\b', material)) == 4
    assert {'DefaultBehaviour', 'StaffNeeds', 'Staff', 'Entity'} <= set(properties)

    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type='PT_LOAD'))
    end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment['p_vaddr'], segment.data())
    arm.mem_map(ARENA, 0x200000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    heap, allocated, freed, constructed, zone_queries, tired_queries = ARENA + 0x10000, [], [], [], [], []
    current_type = 200  # Deliberately arbitrary; no dependency on the Laborer ID.
    machine = ARENA + 0xB000

    def put(address, *values):
        arm.mem_write(address, pack('<' + 'I' * len(values), *values))

    def word(address):
        return unpack_from('<I', arm.mem_read(address, 4))[0]

    def alloc(size):
        nonlocal heap
        result = heap
        heap += (size + 15) & ~15
        allocated.append(size)
        return result

    def text(address):
        raw = bytearray()
        while len(raw) < 1024:
            # A linker change may put a valid short string at a segment's final
            # page. Do not read past its terminator into an unmapped next page.
            size = min(64, 4096 - address % 4096, 1024 - len(raw))
            prefix, separator, _ = bytes(arm.mem_read(address, size)).partition(b'\0')
            raw.extend(prefix)
            if separator:
                return raw.decode()
            address += size
        raise AssertionError('Unterminated native string')

    def string(address):
        return text(word(address + 8) if arm.mem_read(address, 1)[0] & 1 else address + 1)

    def write_string(address, value):
        raw = value.encode()
        if len(raw) <= 10:
            arm.mem_write(address, (bytes([len(raw) * 2]) + raw).ljust(12, b'\0'))
        else:
            buf = alloc(len(raw) + 1)
            arm.mem_write(buf, raw + b'\0')
            put(address, 1, len(raw), buf)

    def definition(props, hangout=room):
        rows = [('Properties', p) for p in props] + [('HangOutRoom', hangout)]
        write_directory(rows)

    def write_directory(rows):
        pointers, present = alloc(4 * len(rows)), alloc(len(rows))
        for i, (key, value) in enumerate(rows):
            data = alloc(40)
            write_string(data, key)
            put(data + 12, 4)
            write_string(data + 28, value)
            put(pointers + i * 4, data)
        arm.mem_write(present, b'\1' * len(rows))
        put(ENTRY + 40, 0, len(rows), pointers, present)

    imported = {BASE + a: n for n, a in SPRITE_REPLACEMENT_IMPORTS.items()}
    imported.update({BASE + NATIVE_ATLAS_IMPORTS[n]: n for n in
                     ('new_object', 'delete_object', 'copy_bytes', 'get_mod_file_paths')})
    imported.update({BASE + address: name for address, name in {
        0x3C2BDC: 'insert_worker', 0x3CA49C: 'incapacitated',
        0x3AC628: 'world_lookup_object', 0x3CACA0: 'is_processor', 0x3CACD0: 'material_type',
    }.items()})

    def intercept(uc, address, _size, _data):
        name = imported.get(address)
        if not name:
            return
        a, b, c = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        result = 0
        if name == 'new_object': result = alloc(a)
        elif name == 'delete_object': freed.append(a)
        elif name == 'copy_bytes': uc.mem_write(a, bytes(uc.mem_read(b, c))); result = a
        elif name == 'copy_game_string': uc.mem_write(a, bytes(uc.mem_read(b, 12))); result = a
        elif name == 'get_mod_file_paths': put(c, 0, 0, 0)
        elif name == 'strlen': result = len(text(a).encode())
        elif name == 'strcmp': result = 0 if text(a) == text(b) else 1
        elif name == 'memcmp': result = 0 if uc.mem_read(a, c) == uc.mem_read(b, c) else 1
        elif name == 'directory_child': result = 0
        elif name == 'directory_data':
            assert string(b) == 'HangOutRoom'
            for i in range(word(a + 44)):
                data = word(word(a + 48) + i * 4)
                if string(data) == string(b): result = data; break
        elif name == 'lookup_object_id': result = current_type
        elif name == 'lookup_zone_id': zone_queries.append(string(a)); result = 17
        elif name in ('worker_ctor', 'entity_ctor'): constructed.append((name, a))
        elif name == 'gets_tired': tired_queries.append(a); result = int(a == 5)
        elif name == 'incapacitated': result = 0
        elif name == 'world_lookup_object': result = machine
        elif name == 'is_processor': result = 1
        elif name == 'material_type': result = 0
        elif name == 'insert_worker':
            assert c == word(a + 8)
            uc.mem_write(word(a) + c * 4, bytes(uc.mem_read(b, 4)))
            put(a + 8, c + 1)
            result = c
        else: raise AssertionError(f'Unexpected import {name}')
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, intercept)
    put(BASE + 0xED0200, APP)
    put(APP, APP + 16)
    write_string(NAME, 'Laborer')
    write_string(FILE, '/fixture/data/materials.txt')

    def run(hook, *args, stop=None, balanced=True):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            arm.reg_write(reg, value)
        arm.reg_write(UC_ARM_REG_SP, STACK)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        end = BASE + hook + 4 if stop is None else stop
        arm.emu_start(BASE + hook, end, count=50000)
        assert arm.reg_read(UC_ARM_REG_PC) == end, hex(arm.reg_read(UC_ARM_REG_PC))
        if balanced:
            assert arm.reg_read(UC_ARM_REG_SP) == STACK
        return arm.reg_read(UC_ARM_REG_R0)

    def read(props, hangout=room):
        definition(props, hangout)
        put(STACK + 0x1A4, FILE)
        put(STACK + 0x1AC, ENTRY)
        run(TOOLBAR_ICON_HOOK, TARGET, NAME)

    def create(type_id, kind, size):
        arm.reg_write(UC_ARM_REG_R4, type_id)
        run(DEFAULT_STAFF_FACTORY_HOOK, stop=BASE + 0xADBBB8)
        result = arm.reg_read(UC_ARM_REG_R5)
        assert allocated[-1] == size
        assert constructed[-1] == (kind + '_ctor', result)
        put(result + 0x18, type_id)
        return result

    read(properties)
    assert word(BASE + DEFAULT_STAFF_STATE)
    entity = create(current_type, 'worker', 0x1E0)
    create(current_type + 1, 'entity', 0x1D0)
    hangout_hooks = (*DEFAULT_STAFF_HANGOUT_HOOKS, DEFAULT_STAFF_HANGOUT_UPDATE_HOOK)
    for hook in hangout_hooks:
        arm.reg_write(UC_ARM_REG_R4, entity)
        arm.reg_write(UC_ARM_REG_R5, 9)
        arm.reg_write(UC_ARM_REG_R6, 9)
        run(hook)
        assert word(entity + 0x1D8) == 17
    assert zone_queries == [room] * 3
    assert run(DEFAULT_STAFF_TIRED_HOOK, current_type) == 1
    assert not tired_queries
    assert run(DEFAULT_STAFF_TIRED_HOOK, 5) == 1
    assert run(DEFAULT_STAFF_TIRED_HOOK, 6) == 0
    assert tired_queries == [5, 6]

    # The mobile registry does not list Worker as a registered field, but its
    # production loader reads repeated Worker strings separately. Execute that
    # original reader and eligibility path, rather than introducing new rules.
    processor_blocks = re.findall(r'BEGIN\s+Processor\b(.*?)\bEND\b', production, re.S)
    assert len(processor_blocks) == 4
    for block in processor_blocks:
        workers = re.findall(r'^\s*Worker\s+(\w+)', block, re.M)
        assert workers == ['Laborer']
        write_directory([('Worker', name) for name in workers])
        worker_list, worker_items, worker_key = alloc(12), alloc(16), alloc(8)
        arm.mem_write(worker_key, b'Worker\0')
        put(worker_list, worker_items, 4, 0)
        put(STACK, worker_list)
        arm.reg_write(UC_ARM_REG_R10, ENTRY)
        arm.reg_write(UC_ARM_REG_R7, worker_key)
        run(0xA3065C, stop=BASE + 0xA30714)
        assert word(worker_list + 8) == 1 and word(worker_items) == current_type

        # Point the original CapableOfJob code at one processor rule and an
        # operable machine. Staff may use its worker list without prisoner-only
        # training checks; unrelated types must not take that success branch.
        rules, rule = ARENA + 0xC000, ARENA + 0xC100
        put(rules, rule, 1, 1)
        put(rule, 123)
        put(rule + 0x1C, worker_items, 1, 1)
        put(machine + 0x18, 123)
        world, job, queue = ARENA + 0xD000, ARENA + 0xF000, ARENA + 0xF100
        put(APP + 16 + 0xE0, world)

        def set_global(instruction, literal, value):
            delta = word(BASE + literal)
            put((BASE + instruction + 8 + delta) & 0xFFFFFFFF, value)

        set_global(0xAADCF0 - 4, 0xAADCE8 + 8 + 0xFEC, rules)
        set_global(0xAADD0C, 0xAADD04 + 8 + 0xFFC, rules)
        set_global(0xAADD18, 0xAADD10 + 8 + 0xFF4, rules)
        set_global(0xAADD20, 0xAADD1C + 8 + 0xFF8, rules)
        put(job + 0x14, 9)
        assert run(0xAADB5C, queue, job, entity, stop=STOP) == 1
        put(worker_items, current_type + 1)
        # No matching worker must fall through to the ordinary job checks.
        run(0xAADB5C, queue, job, entity, stop=BASE + 0xAADDBC, balanced=False)

    read([p for p in properties if p != 'StaffNeeds'], '')
    assert run(DEFAULT_STAFF_TIRED_HOOK, current_type) == 0
    for hook in hangout_hooks:
        arm.reg_write(UC_ARM_REG_R4, entity)
        arm.reg_write(UC_ARM_REG_R5, 9)
        arm.reg_write(UC_ARM_REG_R6, 9)
        run(hook)
        assert word(entity + 0x1D8) == 9
    read(properties + ['Scripted'])
    create(current_type, 'entity', 0x1D0)
    read([p for p in properties if p != 'Staff'])
    create(current_type, 'entity', 0x1D0)
    read(properties)
    read(['Entity', 'Staff'])  # A higher-priority definition removes the behavior.
    create(current_type, 'entity', 0x1D0)
    assert word(BASE + DEFAULT_STAFF_STATE) == 0
    assert len(freed) == 3
    read(properties)
    run(0x9C83D4, 0, FILE, ARENA + 0x8000, 0)
    assert word(BASE + DEFAULT_STAFF_STATE) == 0 and len(freed) == 4
    create(current_type, 'entity', 0x1D0)
    print('PASS: default staff factory, hangout, fatigue, scripted exclusion and overrides; '
          'all four Laborer processor rules read Worker and accept the custom staff type')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    parser.add_argument('mod')
    args = parser.parse_args()
    verify(args.apk, args.mod)
