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
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R10,
    UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
)
from patch_profile import LIBRARY, MOD_RESEARCH_JSON_HOOK, MOD_RESEARCH_IMPORTS, NATIVE_ATLAS_IMPORTS, SPRITE_REPLACEMENT_IMPORTS, RESEARCH_PLACEMENT_STATE, RESEARCH_PLACEMENT_IMPORTS, RESEARCH_WIDGET_ATTACH_HOOK
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
    arm.mem_map(ARENA, 0x800000)
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

    def install_items():
        native_items.clear()
        for i, item in enumerate(all_items):
            if not item: continue
            pointer = alloc(0x50)
            game_string(pointer, item['Name'])
            put(pointer + 0x18, 2, ids.get(item.get('Requires'), 0), 2, 0, int(item.get('Cost', 0)) & 0xFFFFFFFF)
            native_items[i] = pointer

    install_items()

    imported = {BASE + address: name for name, address in MOD_RESEARCH_IMPORTS.items()}
    imported.update({BASE + NATIVE_ATLAS_IMPORTS[n]: n for n in ('new_array', 'delete_array', 'delete_object', 'copy_bytes', 'debug_log')})
    imported.update({BASE + address: name for name, address in RESEARCH_PLACEMENT_IMPORTS.items()})
    imported[BASE + SPRITE_REPLACEMENT_IMPORTS['strlen']] = 'strlen'
    count = len(all_items)
    widget_id, added, scaled = 0, [], []
    parent_widget, shared_widget, element = ARENA + 0x7000, ARENA + 0x7100, ARENA + 0x7200
    widget = ARENA + 0x7300
    put(shared_widget, widget, 0)

    def intercept(uc, address, _size, _data):
        name = imported.get(address)
        if not name: return
        a, b, c, d = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
        result = 0
        if name == 'read_research_json_original':
            assert (a, b, c) == (2, PATH, ROOT)
            construct(ROOT, deepcopy(original))
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
        elif name == 'original_add_research_widget':
            assert (a, b) == (parent_widget, shared_widget)
            added.append(widget_id)
        elif name == 'research_widget_id': assert a == element; result = widget_id
        elif name == 'scale_research_widget':
            assert a == widget
            scaled.append((widget_id, unpack('<ff', arm.mem_read(b, 8))))
        elif name not in ('delete_array', 'delete_object', 'debug_log'): raise AssertionError(name)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    for address in imported:
        arm.hook_add(UC_HOOK_CODE, intercept, begin=address, end=address)

    def run():
        for reg, value in ((UC_ARM_REG_R0, 2), (UC_ARM_REG_R1, PATH), (UC_ARM_REG_R2, ROOT), (UC_ARM_REG_SP, STACK)):
            arm.reg_write(reg, value)
        arm.emu_start(BASE + MOD_RESEARCH_JSON_HOOK, BASE + MOD_RESEARCH_JSON_HOOK + 4, count=500000000)
        assert arm.reg_read(UC_ARM_REG_PC) == BASE + MOD_RESEARCH_JSON_HOOK + 4
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    def scenario(extra):
        nonlocal heap, count, widget_id
        heap = HEAP
        cells.clear()
        construct(ROOT, deepcopy(original))
        all_items[:] = [None, *base_items, *extra]
        ids.clear(); ids.update({item['Name']: i for i, item in enumerate(all_items) if item})
        count = len(all_items)
        install_items()
        run()
        result = deepcopy(get(ROOT)['ResearchData'])
        base_count, scale = unpack('<If', arm.mem_read(BASE + RESEARCH_PLACEMENT_STATE, 8))
        assert base_count == 35 and 0 < scale <= 1
        assert result[:35] == original['ResearchData'] and len(result) == count - 1
        for i, (item, node) in enumerate(zip(extra, result[35:]), 35):
            assert node['research_name'] == 'research_' + item['Name']
            assert node['research_description'] == 'researchtooltip_' + item['Name']
            assert node['cost'] == abs(int(item.get('Cost', 0))) and node['icon']
            x, y = node['xpos'], node['ypos']
            assert 0.0249 <= x <= 0.965 - 0.055 * scale + 0.0001
            assert -0.985 + 0.07 * scale - 0.0001 <= y <= -0.255 - 0.01 * scale + 0.0001
            assert not (x + 0.0375 * scale > 0.7901 and y - 0.0525 * scale < -0.9001)
            for j, other in enumerate(result[:i]):
                sizes = scale + (1 if j < 35 else scale)
                assert abs(x - other['xpos']) >= 0.0375 * sizes + 0.0008 or abs(y - other['ypos']) >= 0.0525 * sizes + 0.0008
        run()
        assert get(ROOT)['ResearchData'] == result
        assert unpack('<If', arm.mem_read(BASE + RESEARCH_PLACEMENT_STATE, 8)) == (35, scale)
        added.clear(); scaled.clear()
        for widget_id in range(1, count):
            for reg, value in ((UC_ARM_REG_R0, parent_widget), (UC_ARM_REG_R1, shared_widget),
                               (UC_ARM_REG_R10, element), (UC_ARM_REG_SP, STACK)):
                arm.reg_write(reg, value)
            arm.emu_start(BASE + RESEARCH_WIDGET_ATTACH_HOOK, BASE + RESEARCH_WIDGET_ATTACH_HOOK + 4, count=10000)
            assert arm.reg_read(UC_ARM_REG_SP) == STACK
        assert added == list(range(1, count))
        assert [id_ for id_, _ in scaled] == (list(range(36, count)) if scale < 0.999 else [])
        assert all(abs(x - scale) < 0.0001 and abs(y - scale) < 0.0001 for _, (x, y) in scaled)
        return result, scale

    baseline, scale = scenario(additions)
    assert scale == 1, 'The real two-node mod should retain normal size'
    reverse, scale = scenario(list(reversed(additions)))
    assert {n['research_name']: (n['xpos'], n['ypos']) for n in baseline[35:]} == {n['research_name']: (n['xpos'], n['ypos']) for n in reverse[35:]}
    scenario([])
    _, wide_scale = scenario([{'Name': f'Wide{i}', 'Requires': 'PrisonLabour', 'Cost': '-100'} for i in range(60)])
    assert wide_scale < 1
    chain = [{'Name': f'CrossMod{i}', 'Requires': f'CrossMod{i + 1}', 'Cost': '200'} for i in range(30)]
    chain[-1]['Requires'] = 'PrisonLabour'
    scenario(chain)
    scenario([{'Name': 'CycleA', 'Requires': 'CycleB', 'Cost': '10'}, {'Name': 'CycleB', 'Requires': 'CycleA', 'Cost': '10'}])
    print(f'Original research unchanged; Manufactury, forward parents, 60 siblings ({wide_scale:.0%} size), cross-mod chains, cycles, stable IDs and new-widget-only scaling verified.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk'); parser.add_argument('obb'); parser.add_argument('mod')
    args = parser.parse_args()
    verify(args.apk, args.obb, args.mod)
