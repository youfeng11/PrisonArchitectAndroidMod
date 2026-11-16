"""Exercise v49's composite LoadImage call and UV mapping on the ARM engine."""

from argparse import ArgumentParser
from io import BytesIO
from math import isclose
from struct import pack, unpack
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP,
)

from verify_registered_sprite_apk import LIBRARY, sprites


ARENA = 0x02000000
STOP = ARENA + 0x100
LOAD_CALL = 0x8D2764
LOAD_IMAGE = 0x8CAFF0
TEX_COORDS = 0x8CB0B8


def read_coordinates(apk, width, height, rectangles):
    with ZipFile(apk) as archive:
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(s["p_vaddr"] + s["p_memsz"] for s in segments)
    arm.mem_map(0, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x4000)
    arm.reg_write(UC_ARM_REG_C1_C0_2, 0xF << 20)
    arm.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
    bank, image, output, stack = (ARENA + offset for offset in (0x200, 0x400, 0x600, 0x2000))
    arm.mem_write(image + 0x18, pack("<II", width, height))

    def imports(uc, address, _size, _data):
        if address == 0x3C91E8:
            uc.reg_write(UC_ARM_REG_PC, LOAD_IMAGE)
        elif address in (0x3C5114, 0x3C4ED4):  # recursive_mutex lock and unlock
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        else:
            raise AssertionError(f"Unexpected import: {address:#x}")

    arm.hook_add(UC_HOOK_CODE, imports, begin=0x3ABBAC, end=0x3E0000)
    arm.reg_write(UC_ARM_REG_SP, stack)
    for register, value in zip(
        (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3),
        (bank, image, width // 32, width // 32),
    ):
        arm.reg_write(register, value)
    arm.emu_start(LOAD_CALL, LOAD_CALL + 4, count=200)
    assert arm.reg_read(UC_ARM_REG_PC) == LOAD_CALL + 4

    result = []
    for x, y, w, h in rectangles:
        arm.mem_write(stack, pack("<5I", h, output, output + 4, output + 8, output + 12))
        for register, value in zip(
            (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), (bank, x, y, w)
        ):
            arm.reg_write(register, value)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        arm.emu_start(TEX_COORDS, STOP, count=100)
        assert arm.reg_read(UC_ARM_REG_PC) == STOP
        u, v, du, dv = unpack("<4f", arm.mem_read(output, 16))
        result.append((u * width, (1 - v) * height, du * width, -dv * height))
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("previous_apk")
    parser.add_argument("fixed_apk")
    parser.add_argument("expanded_obb")
    args = parser.parse_args()
    bank, bindings = sprites(args.expanded_obb)
    with ZipFile(args.expanded_obb) as archive, archive.open("data/tablet/composite.csimage") as texture:
        _, _, width, height = unpack("<4I", texture.read(16))
    assert width != height
    rectangles = [coords[:4] for _, _, coords in bank]
    square_before = read_coordinates(args.previous_apk, 4096, 4096, rectangles[:734])
    assert square_before == read_coordinates(args.fixed_apk, 4096, 4096, rectangles[:734])
    expected = [(x * 32 + .5, y * 32 + .5, w * 32 - 1, h * 32 - 1) for x, y, w, h in rectangles]

    def matches(actual, wanted):
        return all(isclose(a, b, abs_tol=.001) for a, b in zip(actual, wanted))

    broken = read_coordinates(args.previous_apk, width, height, rectangles)
    assert any(not matches(a, b) for a, b in zip(broken[:734], expected[:734]))
    fixed = read_coordinates(args.fixed_apk, width, height, rectangles)
    for (index, name, _), actual, wanted in zip(bank, fixed, expected):
        assert matches(actual, wanted), (index, name, actual, wanted)
    print(f"{width}x{height}: reproduced wrong stock UVs on old APK; fixed APK maps all {len(bank)} entries correctly.")
    print(f"4096x4096: all 734 stock UV rectangles unchanged. Expanded archive binds {len(bindings)} objects.")


if __name__ == "__main__":
    main()
