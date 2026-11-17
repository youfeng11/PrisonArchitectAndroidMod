"""Check the new-program row hook's ARM ABI, gesture routing and references."""

from argparse import ArgumentParser
from io import BytesIO
from struct import pack, unpack
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR
from patch_profile import LIBRARY, PROGRAM_ENTRY_HOOK, PROGRAM_UI_IMPORTS, SPRITE_REPLACEMENT_IMPORTS

BASE, ARENA = 0x10000000, 0x20000000
RESULT, SCREEN, TITLE, STACK = ARENA, ARENA + 0x100, ARENA + 0x200, ARENA + 0x8000
ROOT, BUTTON, OVERLAY = ARENA + 0x1000, ARENA + 0x2000, ARENA + 0x3000


def verify(apk):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type='PT_LOAD'))
    end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
    arm.mem_map(BASE, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(BASE + segment['p_vaddr'], segment.data())
    arm.mem_map(ARENA, 0x10000)
    imports = {BASE + value: name for name, value in PROGRAM_UI_IMPORTS.items()}
    imports[BASE + SPRITE_REPLACEMENT_IMPORTS['strlen']] = 'strlen'
    children = {'ReportsTabContentButton': BUTTON, 'NewProgramsDisabledInputs': OVERLAY}
    consumed, released, found = [], [], []

    def cstring(address):
        return bytes(arm.mem_read(address, 128)).split(b'\0', 1)[0].decode()

    def intercept(uc, address, _size, _data):
        name = imports.get(address)
        if not name:
            return
        a, b, c = (uc.reg_read(reg) for reg in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        result = 0
        if name == 'original_program_entry':
            assert (a, b, c) == (RESULT, SCREEN, TITLE)
            uc.mem_write(a, pack('<II', ROOT, ROOT + 16))
        elif name == 'widget_child':
            assert b == ROOT
            capacity, length, pointer = unpack('<III', uc.mem_read(c, 12))
            assert capacity & 1
            key = cstring(pointer)
            assert length == len(key)
            child = children[key]
            found.append(key)
            uc.mem_write(a, pack('<II', child, child + 16))
        elif name == 'widget_consume_input':
            consumed.append((a, b))
        elif name == 'release_widget_reference':
            released.append(a)
        elif name == 'strlen':
            result = len(cstring(a))
        else:
            raise AssertionError(name)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, intercept)
    for reg, value in ((UC_ARM_REG_R0, RESULT), (UC_ARM_REG_R1, SCREEN), (UC_ARM_REG_R2, TITLE), (UC_ARM_REG_SP, STACK)):
        arm.reg_write(reg, value)
    arm.emu_start(BASE + PROGRAM_ENTRY_HOOK, BASE + PROGRAM_ENTRY_HOOK + 4, count=10000)
    assert arm.reg_read(UC_ARM_REG_PC) == BASE + PROGRAM_ENTRY_HOOK + 4
    assert arm.reg_read(UC_ARM_REG_SP) == STACK
    assert bytes(arm.mem_read(RESULT, 8)) == pack('<II', ROOT, ROOT + 16)
    assert found == list(children)
    assert consumed == [(ROOT, 0), (BUTTON, 0), (OVERLAY, 0)]
    assert released == [BUTTON + 16, OVERLAY + 16]
    print('Program rows preserve factory arguments and ownership; buttons and disabled overlays pass gestures to the scroll view.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('apk')
    verify(parser.parse_args().apk)
