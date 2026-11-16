"""Exercise the game APK's ZIP installer on the host JVM."""

from argparse import ArgumentParser
import os
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("java_home", type=Path)
    parser.add_argument("--archive-jar", type=Path)
    parser.add_argument("mods", type=Path, nargs="+")
    args = parser.parse_args()
    source = Path(__file__).resolve().with_name("obb-bridge")
    archive_jar = args.archive_jar or source / "compose/build/archive-jvm/classes.jar"
    java = args.java_home / "bin"
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        files = directory / "game-files"
        files.mkdir()
        run([java / ("javac.exe" if os.name == "nt" else "javac"), "-encoding", "UTF-8", "-cp", archive_jar, "-d", directory,
             source / "NativeModStore.java", source / "ModArchive.java",
             source / "MaterialDefinitionRepair.java", source / "VerifyNativeModStore.java"], check=True)
        run([java / ("java.exe" if os.name == "nt" else "java"), "-cp", os.pathsep.join((str(directory), str(archive_jar))),
             "com.paradoxplaza.prisonarchitect.patools.VerifyNativeModStore", files, *args.mods], check=True)


if __name__ == "__main__":
    main()
