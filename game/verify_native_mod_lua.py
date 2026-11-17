"""Exercise native Lua module registration and job cancellation in the APK."""

from argparse import ArgumentParser
from io import BytesIO
from struct import pack, unpack_from
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC,
)

from patch_profile import LIBRARY, LUA_OBJECT_REGISTER_HOOK, MOD_LUA_IMPORTS, SPRITE_REPLACEMENT_IMPORTS

BASE, ARENA = 0x10000000, 0x20000000
STACK, STOP, APP, WORLD, ITEMS, HEAP = (ARENA + n for n in (0x1000, 0x2000, 0x3000, 0x4000, 0x6000, 0x8000))


def verify(apk):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type='PT_LOAD'))
    end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for s in segments:
        arm.mem_write(BASE + s['p_vaddr'], s.data())
    arm.mem_map(ARENA, 0x20000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    stack, globals_, closures, canceled = [], {}, [], []
    table = {'Spawn': 'original function'}
    queue = WORLD + 0x5C
    state, label, original = ARENA + 0x7000, ARENA + 0x7100, ARENA + 0x7200

    def put(address, *values):
        arm.mem_write(address, pack('<' + 'I' * len(values), *values))

    def word(address):
        return unpack_from('<I', arm.mem_read(address, 4))[0]

    def string(address):
        result = bytearray()
        while len(result) < 1024:
            chunk, separator, _ = bytes(arm.mem_read(address, min(64, 4096 - address % 4096))).partition(b'\0')
            result.extend(chunk)
            if separator: return result.decode()
            address += len(chunk)
        raise AssertionError('Unterminated string')

    def signed(value):
        return value - (1 << 32) if value & (1 << 31) else value

    def at(index):
        index = signed(index)
        if index == -10002: return globals_
        if index == 0 or index > len(stack) or index < -len(stack): return None
        return stack[index - 1 if index > 0 else index]

    imports = {BASE + address: name for name, address in MOD_LUA_IMPORTS.items()}
    imports[BASE + SPRITE_REPLACEMENT_IMPORTS['memcmp']] = 'memcmp'

    def intercept(uc, address, _size, _data):
        if address not in imports: return
        name = imports[address]
        a, b, c = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        result = 0
        if name == 'luaL_register':
            assert (a, string(b), c) == (state, 'Object', original)
            stack.append(table)
        elif name == 'lua_pushcclosure':
            assert a == state and c == 0 and BASE <= b < BASE + end
            closures.append(b)
            stack.append(b)
        elif name == 'lua_setfield':
            target = at(b)
            value = stack.pop()
            target[string(c)] = value
        elif name == 'lua_getfield':
            target = at(b)
            stack.append(target.get(string(c)) if isinstance(target, dict) else None)
        elif name == 'lua_gettop': result = len(stack)
        elif name == 'lua_settop':
            index = signed(b)
            size = index if index >= 0 else len(stack) + index + 1
            del stack[size:]
        elif name == 'lua_type':
            index = signed(b)
            value = at(b)
            result = -1 if index > len(stack) else 0 if value is None else (
                5 if isinstance(value, dict) else 4 if isinstance(value, str) else 3)
        elif name == 'lua_tointeger': result = int(at(b)) & 0xFFFFFFFF
        elif name == 'lua_tolstring':
            raw = str(at(b)).encode()
            arm.mem_write(ARENA + 0x7400, raw + b'\0')
            if c: put(c, len(raw))
            result = ARENA + 0x7400
        elif name == 'memcmp': result = int(uc.mem_read(a, c) != uc.mem_read(b, c))
        elif name == 'cancel_work_job':
            assert a == queue and c == 0
            pointers = [word(ITEMS + i * 4) for i in range(word(queue + 8))]
            found = next(i for i, p in enumerate(pointers) if word(p + 12) == b)
            canceled.append(b)
            del pointers[found]
            if pointers: put(ITEMS, *pointers)
            put(queue + 8, len(pointers))
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, intercept)
    arm.mem_write(label, b'Object\0')
    put(BASE + 0xED0200, APP)
    put(APP, APP + 16)
    put(APP + 16 + 0xE0, WORLD)
    put(queue, ITEMS, 16, 0)

    def run(address, stop, *arguments):
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), arguments):
            arm.reg_write(reg, value)
        arm.reg_write(UC_ARM_REG_SP, STACK)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        arm.emu_start(address, stop, count=100000)
        assert arm.reg_read(UC_ARM_REG_PC) == stop
        assert arm.reg_read(UC_ARM_REG_SP) == STACK

    run(BASE + LUA_OBJECT_REGISTER_HOOK, BASE + LUA_OBJECT_REGISTER_HOOK + 4, state, label, original)
    assert len(closures) == 1 and table == {'Spawn': 'original function', 'CancelJob': closures[0]}

    def proxy(index, unique): return {'id-index': str(index), 'id-uniqueId': str(unique)}

    def set_jobs():
        specs = [(1, 21, 30, 40, 'M4_WaterCottonPlant'), (2, 21, 30, 41, 'M4_WaterCottonPlant'),
                 (3, 21, 31, 40, 'M4_WaterCottonPlant'), (4, 20, 30, 40, 'M4_WaterCottonPlant'),
                 (5, 21, 30, 40, 'Harvest'), (6, 21, 30, 40, 'M4_WaterCottonPlant')]
        addresses = []
        for job_id, kind, index, unique, action in specs:
            p = HEAP + job_id * 0x100
            put(p + 12, job_id)
            put(p + 20, kind)
            put(p + 0x60, index, unique)
            if len(action) <= 10:
                arm.mem_write(p + 0x74, (bytes([len(action) * 2]) + action.encode()).ljust(12, b'\0'))
            else:
                put(p + 0x74, 1, len(action), p + 0xA0)
                arm.mem_write(p + 0xA0, action.encode() + b'\0')
            addresses.append(p)
        put(ITEMS, *addresses)
        put(queue + 8, len(addresses))
        canceled.clear()

    globals_['me'] = globals_['plant'] = proxy(30, 40)
    job_name = 'M4_WaterCottonPlant'
    for arguments in ((proxy(30, 40), job_name), ('plant', job_name), (job_name,), (None, job_name)):
        set_jobs()
        stack[:] = arguments
        run(closures[0], STOP, state)
        assert canceled == [6, 1] and word(queue + 8) == 4
        assert stack == list(arguments)
    for arguments in ((proxy(30, 42), job_name), ({}, job_name), (proxy(30, 40), 'Missing'), (), (1, job_name)):
        set_jobs()
        stack[:] = arguments
        run(closures[0], STOP, state)
        assert not canceled and word(queue + 8) == 6 and stack == list(arguments)
    print('Native Object.CancelJob registration, explicit/implicit targets, unique IDs, duplicate jobs and stack balance verified.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    args = parser.parse_args()
    verify(args.apk)
