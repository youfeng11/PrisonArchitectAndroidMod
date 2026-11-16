"""Run the APK's ARM registration hook and stock enum/atlas lookup on an appended bank."""

from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from struct import pack, unpack
from zipfile import ZipFile
import re

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1,
    UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_SP,
)


ARENA = 0x02000000
STOP = ARENA + 0x100
ORIGINAL_COUNT = 734
LIBRARY = "lib/armeabi-v7a/libmain.so"
SPRITE = re.compile(
    r'BEGIN "\[i (\d+)\]"\s+Name ("[^"]+"|\S+)\s+x (\d+)\s+y (\d+)\s+w (\d+)\s+h (\d+)'
    r'\s+RotateType (\d+)(?:\s+TopAligned (true|false))?'
)


def sprites(obb):
    with ZipFile(obb) as archive:
        bank = archive.read("data/objects.spritebank").decode().split("BEGIN Markers", 1)[0]
        records = [
            (int(index), name.strip('"'), (*map(int, (x, y, w, h, rotation)), aligned == "true"))
            for index, name, x, y, w, h, rotation, aligned in SPRITE.findall(bank)
        ]
        materials = archive.read("data/materials.txt").decode()
        objects = {}
        for block in re.findall(r"(?ms)^BEGIN (?:Object|Equipment)[ \t]*\r?\n.*?^END\b", materials):
            fields = dict(re.findall(r"(?m)^\s*(Name|Sprite|SpriteVariants)\s+(\S+)", block))
            if fields.get("Sprite", "").startswith("PAToolsMod_"):
                objects[fields["Name"]] = (fields["Sprite"], int(fields.get("SpriteVariants", 1)))
        return records, objects


def verify(apk, records, bindings, vanilla=False):
    with ZipFile(apk) as archive:
        library = archive.read(LIBRARY)
    elf = ELFFile(BytesIO(library))
    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    segments = list(elf.iter_segments(type="PT_LOAD"))
    arm.mem_map(0, (max(s["p_vaddr"] + s["p_memsz"] for s in segments) + 4095) & ~4095)
    for s in segments:
        arm.mem_write(s["p_vaddr"], s.data())
    arm.mem_map(ARENA, 0x50000)
    stack, app, app_slot, enum, pointers, used, names, request = (
        ARENA + i for i in (0x40000, 0x2000, 0x1000, 0x1100, 0x3000, 0x6000, 0x8000, 0x18000)
    )
    heap = ARENA + 0x19000
    bank = app + 0x40C
    count = len(records)
    material_calls = []
    truncate_calls = []

    def put(address, *items):
        arm.mem_write(address, pack(f"<{len(items)}I", *items))

    def word(address):
        return unpack("<I", arm.mem_read(address, 4))[0]

    def allocate(size):
        nonlocal heap
        address = heap
        heap += (size + 15) & ~15
        return address

    def string(addr, text):
        value = text.encode()
        if len(value) <= 10:
            arm.mem_write(addr, (bytes([2 * len(value)]) + value).ljust(12, b"\0"))
        else:
            ptr = allocate(len(value) + 1)
            arm.mem_write(ptr, value + b"\0")
            put(addr, 0x21, len(value), ptr)

    put(0xED0200, app_slot)
    put(0xED3188, enum)
    put(app_slot, app)
    put(bank + 0x14, 0xFFFFFFFF, count, pointers, used)
    put(enum, names, ORIGINAL_COUNT, ORIGINAL_COUNT)
    arm.mem_write(used, b"\x01" * count)
    originals = []
    sprite_addresses = []
    for index, name, coords in records:
        address = allocate(36)
        string(address, name)
        arm.mem_write(address + 12, pack("<5IB", *coords))
        put(pointers + 4 * index, address)
        sprite_addresses.append(address)
        if index < ORIGINAL_COUNT:
            string(names + 12 * index, name)
            originals.append(bytes(arm.mem_read(names + 12 * index, 12)))

    # Supply allocator and string boundaries. The actual v49 FastList insertion,
    # enum lookup and sprite lookup run as ARM code.
    def hooks(uc, address, _size, _data):
        r0, r1, r2 = (uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2))
        if address == 0x3C92C0:
            uc.reg_write(UC_ARM_REG_PC, 0x751FE0)
            return
        if address == 0x3C9FC8:
            uc.reg_write(UC_ARM_REG_PC, 0x789D84)
            return
        if address == 0x3C93B0:
            ptr, old_size = word(r0), word(r0 + 8)
            new = allocate(r1 * 12)
            uc.mem_write(new, bytes(uc.mem_read(ptr, old_size * 12)))
            put(r0, new, r1)
        elif address == 0x3AC658:
            uc.mem_write(r0, bytes(uc.mem_read(r1, 12)))
        elif address == 0x3ACB08:
            equal = uc.mem_read(r0, r2) == uc.mem_read(r1, r2)
            uc.reg_write(UC_ARM_REG_R0, 0 if equal else 1)
        elif address == 0x3CA3E8:
            assert r0 == bank
            put(bank + 0x18, count)
        elif address == 0x3D4CE4:
            assert r0 == bank
            truncate_calls.append(r1)
            put(bank + 0x18, min(word(bank + 0x18), r1))
        elif address == 0x3D4CF0:
            material_calls.append((r0, r1, word(enum + 8)))
            uc.reg_write(UC_ARM_REG_PC, STOP)
            return
        else:
            raise AssertionError(f"Unexpected import at {address:#x}")
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    arm.hook_add(UC_HOOK_CODE, hooks, begin=0x3ABBAC, end=0x3E0000)
    arm.reg_write(UC_ARM_REG_SP, stack)
    arm.reg_write(UC_ARM_REG_R0, bank)
    arm.emu_start(0x8D279C, 0x8D27A0, count=200)
    assert arm.reg_read(UC_ARM_REG_PC) == 0x8D27A0
    expected_count = ORIGINAL_COUNT if vanilla else count
    for _ in range(2):
        # Model an extra entry added by a previous inline material definition.
        put(bank + 0x18, count + 1)
        put(enum + 8, ORIGINAL_COUNT)
        arm.reg_write(UC_ARM_REG_R0, bank)
        arm.reg_write(UC_ARM_REG_R1, ORIGINAL_COUNT)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        arm.emu_start(0x9C77D4, STOP, count=200)
        assert word(bank + 0x18) == expected_count
        arm.reg_write(UC_ARM_REG_R0, request)
        arm.reg_write(UC_ARM_REG_R1, request + 12)
        arm.emu_start(0x9C78EC, STOP, count=max(20000, count * 100))
        assert arm.reg_read(UC_ARM_REG_PC) == STOP
    assert truncate_calls == [expected_count] * 2
    assert material_calls == [(request, request + 12, expected_count)] * 2
    current = word(enum)
    assert bytes(arm.mem_read(current, ORIGINAL_COUNT * 12)) == b"".join(originals)
    assert list(unpack(f"<{count}I", arm.mem_read(pointers, count * 4))) == sprite_addresses

    registry = request + 0x40
    put(registry, 0, 0xFFFFFFFF, enum)
    resolved = {}
    for index, name, coords in records[ORIGINAL_COUNT:]:
        string(request, name)
        arm.reg_write(UC_ARM_REG_R0, registry)
        arm.reg_write(UC_ARM_REG_R1, request)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        arm.emu_start(0x786C90, STOP, count=50000)
        expected = 0xFFFFFFFF if vanilla else index
        assert arm.reg_read(UC_ARM_REG_R0) == expected, (name, index, arm.reg_read(UC_ARM_REG_R0))
        if vanilla:
            continue
        resolved[name] = index
        arm.reg_write(UC_ARM_REG_R0, bank)
        arm.reg_write(UC_ARM_REG_R1, index)
        arm.reg_write(UC_ARM_REG_LR, STOP)
        arm.emu_start(0x8CC0E8, STOP, count=100)
        assert unpack("<5IB", arm.mem_read(arm.reg_read(UC_ARM_REG_R0) + 12, 21)) == coords
        print(f"{name} -> {index} -> {coords}")
    if not vanilla:
        world_object = request + 0x100
        for name, (sprite, variants) in bindings.items():
            base = resolved[sprite]
            for variant in range(variants):
                put(world_object + 0x1C, variant)
                arm.reg_write(UC_ARM_REG_R5, world_object)
                arm.reg_write(UC_ARM_REG_R6, base)
                arm.emu_start(0x8EC4C0, 0x8EC4E0, count=20)
                assert arm.reg_read(UC_ARM_REG_R4) == base + variant
                print(f"{name} variant {variant} selects {base + variant}")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("patched", type=Path)
    parser.add_argument("obb", type=Path)
    args = parser.parse_args()
    bank, bindings = sprites(args.obb)
    assert len(bank) > ORIGINAL_COUNT
    assert [index for index, _, _ in bank] == list(range(len(bank)))
    verify(args.original, bank, bindings, vanilla=True)
    verify(args.patched, bank, bindings)
    print(f"All {ORIGINAL_COUNT} built-in slots retained; {len(bank) - ORIGINAL_COUNT} appended names resolve.")


if __name__ == "__main__":
    main()
