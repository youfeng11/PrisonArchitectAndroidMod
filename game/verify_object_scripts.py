"""Run the v49 object-script existence check against an archive and disk fixture."""

from argparse import ArgumentParser
from io import BytesIO
from struct import pack, unpack_from
from zipfile import ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP

from verify_registered_sprite_apk import LIBRARY


CHECK = 0xAD7B9C
FILE_SYSTEM_GOT = 0xED0D4C
ARENA = 0x02000000
SCRIPT = b"data/scripts/guard.lua"


def exists(apk, in_archive, on_disk):
    with ZipFile(apk) as archive:
        library = archive.read(LIBRARY)
    elf = ELFFile(BytesIO(library))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(s["p_vaddr"] + s["p_memsz"] for s in segments)
    arm.mem_map(0, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(segment["p_vaddr"], segment.data())
    arm.mem_map(ARENA, 0x4000)
    path, path_bytes, slot, filesystem, names, entries, ctype, stack = (
        ARENA + offset for offset in (0, 0x40, 0x80, 0x100, 0x180, 0x190, 0x400, 0x3000)
    )

    def put(address, *words):
        arm.mem_write(address, pack(f"<{len(words)}I", *words))

    put(path, 0x21, len(SCRIPT), path_bytes)
    arm.mem_write(path_bytes, SCRIPT + b"\0")
    put(FILE_SYSTEM_GOT, slot)
    put(slot, filesystem)
    put(filesystem, names, entries, 0, 1)
    put(names, path_bytes if in_archive else 0)
    put(entries, ARENA + 0x200 if in_archive else 0)
    # The hash routine reads the Android libc ctype table through the GOT.
    literal = unpack_from("<i", library, 0xB159F4 + 8 + 0xB8)[0]
    put(0xB159FC + 8 + literal, slot + 4)
    put(slot + 4, ctype)
    put(ctype, ctype + 4)

    def imports(uc, address, _size, _data):
        r0, r1 = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1))
        if address == 0x3C13E8:
            assert (r0, r1) == (filesystem, path)
            uc.reg_write(UC_ARM_REG_PC, 0xB159B0)
            return
        if address == 0x3B02F4:
            assert r0 == path
            uc.reg_write(UC_ARM_REG_R0, int(on_disk))
        elif address == 0x3ABCB0:
            uc.reg_write(UC_ARM_REG_R0, r0 // r1)
            uc.reg_write(UC_ARM_REG_R1, r0 % r1)
        elif address == 0x3CB288:
            assert r0 == path_bytes and r1 == path_bytes
            uc.reg_write(UC_ARM_REG_R0, 0)
        elif address not in (0x3C5114, 0x3C4ED4):
            raise AssertionError(f"Unexpected import: {address:#x}")
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, imports, begin=0x3ABBAC, end=0x3E0000)
    arm.reg_write(UC_ARM_REG_R0, path)
    arm.reg_write(UC_ARM_REG_SP, stack)
    arm.emu_start(CHECK, CHECK + 4, count=1000)
    assert arm.reg_read(UC_ARM_REG_PC) == CHECK + 4
    return arm.reg_read(UC_ARM_REG_R0) == 1


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("previous_apk")
    parser.add_argument("fixed_apk")
    args = parser.parse_args()
    assert not exists(args.previous_apk, in_archive=True, on_disk=False)
    assert exists(args.fixed_apk, in_archive=True, on_disk=False)
    assert exists(args.fixed_apk, in_archive=False, on_disk=True)
    assert not exists(args.fixed_apk, in_archive=False, on_disk=False)
    print("OBB-only, disk-only and missing paths resolve correctly on the patched ARM call site.")


if __name__ == "__main__":
    main()
