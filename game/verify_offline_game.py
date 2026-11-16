"""Check the packaged resources and execute the v49 offline edition's ARM queries."""

from argparse import ArgumentParser
from hashlib import file_digest
from io import BytesIO
from pathlib import Path
import re
from subprocess import check_output
from zipfile import ZIP_STORED, ZipFile

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1

from patch_profile import LIBRARY


def verify(apk, obb, aapt, project_version):
    asset = "assets/patools/main.49.com.paradoxplaza.prisonarchitect.obb"
    with ZipFile(apk) as archive, obb.open("rb") as source:
        assert archive.getinfo(asset).compress_type == ZIP_STORED
        with archive.open(asset) as installed:
            assert file_digest(installed, "sha256").digest() == file_digest(source, "sha256").digest()
        elf = ELFFile(BytesIO(archive.read(LIBRARY)))
    manifest = check_output([aapt, "dump", "xmltree", apk, "AndroidManifest.xml"]).decode()
    badging = check_output([aapt, "dump", "badging", apk]).decode()
    assert "name='com.paradoxplaza.prisonarchitect.mod'" in badging
    assert "versionCode='49'" in badging
    assert f"versionName='2.0.9-{project_version}'" in badging
    assert 'com.paradoxplaza.prisonarchitect.mod.permission.PATOOLS_OBB' in manifest
    assert 'com.paradoxplaza.prisonarchitect.permission.PATOOLS_OBB' not in manifest
    assert 'com.paradoxplaza.prisonarchitect.core.MainActivity' in manifest
    assert 'com.paradoxplaza.prisonarchitect.patools.NativeModsActivity' in manifest
    assert 'com.paradoxplaza.prisonarchitect.patools.ObbBridgeService' in manifest
    assert re.search(r'E: meta-data[^\n]*\n\s+A: android:name[^\n]*="packageName"[^\n]*\n'
                     r'\s+A: android:value[^\n]*="com\.paradoxplaza\.prisonarchitect"', manifest)
    for name in (
        "com.android.vending.CHECK_LICENSE", "com.android.vending.BILLING",
        "com.google.android.gms", "com.google.android.c2dm", "ApkExpansionDownload",
    ):
        assert name not in manifest, name

    arm = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    base = 0x10000000
    segments = list(elf.iter_segments(type="PT_LOAD"))
    end = max(segment["p_vaddr"] + segment["p_memsz"] for segment in segments)
    arm.mem_map(base, (end + 4095) & ~4095)
    for segment in segments:
        arm.mem_write(base + segment["p_vaddr"], segment.data())
    resume = base + 0x1000

    def query(address, value, expected):
        arm.reg_write(UC_ARM_REG_R0, 0)
        arm.reg_write(UC_ARM_REG_R1, value)
        arm.reg_write(UC_ARM_REG_LR, resume)
        arm.emu_start(base + address, resume, count=20)
        assert arm.reg_read(UC_ARM_REG_PC) == resume
        assert arm.reg_read(UC_ARM_REG_R0) == expected

    for address in (0x4AC570, 0x4ACE80, 0x4AE1A0):
        query(address, 0, 1)
    for chapter in (-1, 0, 1, 2, 3, 4, 5, 6):
        query(0x4AC5E0, chapter, int(1 <= chapter <= 5))
    for address in (0x4A87A8, 0x4A87B0, 0x4A8DDC):
        query(address, 0, 0)
    print("Mod package, project version, component classes, signature permission, bundled OBB and startup verified.")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("obb", type=Path)
    parser.add_argument("aapt", type=Path)
    parser.add_argument("--project-version", required=True)
    args = parser.parse_args()
    verify(args.apk, args.obb, args.aapt, args.project_version)
