"""Fix two dangling references in the supplied Manufactury 4.0 mod ZIP."""

from argparse import ArgumentParser
from pathlib import Path
from zipfile import ZipFile


CORRECTIONS = {
    'data/grants.lua': (b'Grant_M4_Cotton_Production', b'Grant_M4_CottonProduction'),
    'data/scripts/M4_CottonPlant.lua': (b'M4_RemoveStruckGardenPlant', b'M4_RemoveStruckCottonPlant'),
}


def build(source, output):
    if source.resolve() == output.resolve():
        raise ValueError('Choose a separate output path; preserve the original mod.')
    with ZipFile(source) as archive:
        replacements = {}
        for filename, (old, new) in CORRECTIONS.items():
            data = archive.read(filename)
            if data.count(old) != 1:
                raise ValueError(f'Expected one reference to {old.decode()} in {filename}')
            replacements[filename] = data.replace(old, new)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, 'w') as repaired:
            for entry in archive.infolist():
                repaired.writestr(entry, replacements.get(entry.filename, archive.read(entry)))
    with ZipFile(source) as original, ZipFile(output) as repaired:
        assert original.namelist() == repaired.namelist()
        changed = {name for name in original.namelist() if original.read(name) != repaired.read(name)}
        assert changed == set(CORRECTIONS)
    print(f'Corrected grant parent and job reference; all other entries preserved: {output}')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build(args.source, args.output)
