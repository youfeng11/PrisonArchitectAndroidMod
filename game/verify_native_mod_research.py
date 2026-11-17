"""Run tablet research augmentation against the actual Manufactury definitions."""

from argparse import ArgumentParser
from copy import deepcopy
from io import BytesIO
import json
from struct import pack, unpack, unpack_from
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
)
from patch_profile import LIBRARY, MOD_RESEARCH_JSON_HOOK, MOD_RESEARCH_IMPORTS, NATIVE_ATLAS_IMPORTS, SPRITE_REPLACEMENT_IMPORTS
from verify_native_production import definitions

BASE, ARENA = 0x10000000, 0x20000000
STACK, ROOT, PATH, HEAP = ARENA + 0x4000, ARENA + 0x5000, ARENA + 0x6000, ARENA + 0x10000


def verify(apk, obb, mod):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    with ZipFile(obb) as archive:
        original = json.loads(archive.read('data/tablet/jsondata/bureaucracyResearch.json'))
    base_items = [data for kind, data in definitions(obb, 'data/research.txt') if kind == 'Research' and 'Name' in data]
    additions = [data for kind, data in definitions(mod, 'data/research.txt') if kind == 'Research']
    assert len(base_items) == len(original['ResearchData']) == 35 and len(additions) == 2
    all_items = [None, *base_items, *additions]
    ids = {item['Name']: i for i, item in enumerate(all_items) if item}
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type='PT_LOAD'))
    end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment['p_vaddr'], segment.data())
    arm.mem_map(ARENA, 0x200000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    heap = HEAP
    cells = {ROOT: ([deepcopy(original)], 0)}

    def alloc(size):
        nonlocal heap
        result = heap
        heap += (size + 15) & ~15
        return result

    def put(address, *values): arm.mem_write(address, pack('<' + 'I' * len(values), *values))
    def word(address): return unpack_from('<I', arm.mem_read(address, 4))[0]
    def get(address): container, key = cells[address]; return container[key]
    def set_value(address, value): container, key = cells[address]; container[key] = value
    def construct(address, value): cells[address] = ([value], 0)

    def cstring(address):
        result = bytearray()
        while len(result) < 1024:
            data, separator, _ = bytes(arm.mem_read(address, min(64, 4096 - address % 4096))).partition(b'\0')
            result.extend(data)
            if separator: return result.decode()
            address += len(data)
        raise AssertionError('Unterminated native string')

    def game_string(address, text):
        data = text.encode()
        if len(data) <= 10:
            arm.mem_write(address, (bytes([len(data) * 2]) + data).ljust(12, b'\0'))
        else:
            target = alloc(len(data) + 1)
            arm.mem_write(target, data + b'\0')
            put(address, 1, len(data), target)

    native_items = {}
    for i, item in enumerate(all_items):
        if not item: continue
        pointer = alloc(0x50)
        game_string(pointer, item['Name'])
        put(pointer + 0x18, 2, ids.get(item.get('Requires'), 0), 2, 0, int(item.get('Cost', 0)) & 0xFFFFFFFF)
        native_items[i] = pointer

    imported = {BASE + address: name for name, address in MOD_RESEARCH_IMPORTS.items()}
    imported.update({BASE + NATIVE_ATLAS_IMPORTS[n]: n for n in ('new_array', 'delete_array', 'delete_object', 'copy_bytes')})
    imported[BASE + SPRITE_REPLACEMENT_IMPORTS['strlen']] = 'strlen'
    count = len(all_items)

    def intercept(uc, address, _size, _data):
        name = imported.get(address)
        if not name: return
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        result = 0
        if name == 'read_research_json_original': assert (a, b, c) == (2, PATH, ROOT)
        elif name == 'research_item_count': result = count
        elif name == 'research_item': result = native_items[a]
        elif name in ('json_member', 'json_index'):
            container = get(a)
            key = cstring(b) if name == 'json_member' else b
            if isinstance(container, dict): container.setdefault(key, None)
            result = alloc(24)
            cells[result] = (container, key)
        elif name == 'json_size': result = len(get(a))
        elif name == 'json_is_array': result = int(isinstance(get(a), list))
        elif name == 'json_real': result = unpack('<I', pack('<f', float(get(a))))[0]
        elif name == 'json_text': game_string(a, get(b))
        elif name == 'json_construct': construct(a, {} if b == 7 else None)
        elif name == 'json_construct_text': construct(a, cstring(b))
        elif name == 'json_construct_int': construct(a, b)
        elif name == 'json_construct_real': construct(a, unpack('<d', pack('<II', c, d))[0])
        elif name == 'json_swap':
            old_a, old_b = get(a), get(b)
            set_value(a, old_b); set_value(b, old_a)
        elif name == 'json_append': get(a).append(deepcopy(get(b)))
        elif name == 'json_destroy': del cells[a]
        elif name == 'new_array': result = alloc(a)
        elif name == 'copy_bytes': uc.mem_write(a, bytes(uc.mem_read(b, c)))
        elif name == 'strlen': result = len(cstring(a).encode())
        elif name not in ('delete_array', 'delete_object'): raise AssertionError(name)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, intercept)

    def run():
        for reg, value in ((UC_ARM_REG_R0, 2), (UC_ARM_REG_R1, PATH), (UC_ARM_REG_R2, ROOT), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MOD_RESEARCH_JSON_HOOK, BASE + MOD_RESEARCH_JSON_HOOK + 4, count=2000000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MOD_RESEARCH_JSON_HOOK + 4
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    run()
    result = get(ROOT)['ResearchData']
    assert result[:35] == original['ResearchData'] and len(result) == 37
    for item, node in zip(additions, result[35:]):
        assert node['research_name'] == 'research_' + item['Name']
        assert node['research_description'] == 'researchtooltip_' + item['Name']
        assert node['cost'] == abs(int(item['Cost']))
        assert node['icon'] and not (node['ypos'] < -0.85 and node['xpos'] > 0.75)
        for other in result:
            if node is other: continue
            assert abs(node['xpos'] - other['xpos']) >= 0.075 or abs(node['ypos'] - other['ypos']) >= 0.105
    run()
    assert len(result) == 37  # Existing nodes are not appended twice.
    count = 36
    construct(ROOT, deepcopy(original))
    run()
    assert get(ROOT) == original
    print('Manufactury research labels, costs, stable IDs and non-overlapping tablet positions verified; base tree unchanged.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk'); parser.add_argument('obb'); parser.add_argument('mod')
    args = parser.parse_args()
    verify(args.apk, args.obb, args.mod)
