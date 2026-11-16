"""Repair the upstream Chinese Style Prison Mod's malformed materials blocks."""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile


MATERIALS = "data/materials.txt"
UPSTREAM_MATERIALS = "e8462ceb453326cc0190897f24b675ea4be180c39fad71a49ceb446190c25be1"
NAME_KEY = b"object_slogan_i"
LABELS = {
    "data/language/base-language.txt": "Reform Banner",
    "data/language/simplifiedchinese/base-language.txt": "改造标语",
}


def repair_materials(source):
    if sha256(source).hexdigest() != UPSTREAM_MATERIALS:
        raise ValueError("Unexpected upstream materials.txt. Review the new version before applying this repair.")
    lines = source.splitlines(keepends=True)
    objects = [i for i, line in enumerate(lines) if line.split() == [b"BEGIN", b"Object"]]
    first, second, _ = objects
    sprite_start = next(i for i in range(first, second) if lines[i].split() == [b"BEGIN", b"Sprite"])
    newline = b"\r\n" if lines[sprite_start].endswith(b"\r\n") else b"\n"
    # All four malformed declarations refer to the same rectangle. RotateType 4
    # uses that one rectangle for every direction on v49.
    sprite = (b"    BEGIN Sprite x 0 y 3 w 4 h 1 RotateType 4 END" + newline + b"END" + newline)
    repaired = b"".join(lines[:sprite_start]) + sprite + b"".join(lines[second:])
    depth = 0
    for token in repaired.split():
        if token == b"BEGIN":
            depth += 1
        if token == b"END":
            depth -= 1
            if depth < 0:
                raise ValueError("A materials block closed before it opened.")
    if depth:
        raise ValueError("A materials block is still open.")
    return repaired


def build(source, output):
    if source.resolve() == output.resolve():
        raise ValueError("Choose a separate path for the updated ZIP.")
    with ZipFile(source) as original:
        replacements = {MATERIALS: repair_materials(original.read(MATERIALS))}
        for path, label in LABELS.items():
            content = original.read(path)
            if any(line.split()[:1] == [NAME_KEY] for line in content.splitlines()):
                raise ValueError(f"The translation already defines {NAME_KEY!r} in {path}.")
            replacements[path] = content.rstrip(b"\r\n") + b"\r\n" + NAME_KEY + b" " + label.encode() + b"\r\n"
        with ZipFile(output, "w") as updated:
            for entry in original.infolist():
                updated.writestr(entry, replacements[entry.filename] if entry.filename in replacements else original.read(entry))
    with ZipFile(source) as original, ZipFile(output) as updated:
        assert original.namelist() == updated.namelist()
        assert {entry.filename for entry in original.infolist() if entry.CRC != updated.getinfo(entry.filename).CRC} == replacements.keys()
        assert updated.testzip() is None


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
