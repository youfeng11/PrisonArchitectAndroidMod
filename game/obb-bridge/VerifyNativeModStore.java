package com.paradoxplaza.prisonarchitect.patools;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

final class VerifyNativeModStore {
    public static void main(String[] arguments) throws IOException {
        Path files = Paths.get(arguments[0]);
        Path atomicTarget = files.resolve("atomic-write-check.txt");
        Files.write(atomicTarget, "original".getBytes(StandardCharsets.UTF_8));
        NativeModStore.writeAtomically(atomicTarget, "replacement".getBytes(StandardCharsets.UTF_8));
        require(read(atomicTarget).equals("replacement"));
        Files.delete(atomicTarget);
        // Force rename failure after staging completed and verify it is cleaned up.
        Files.createDirectory(atomicTarget);
        Path retained = atomicTarget.resolve("original.txt");
        Files.write(retained, "original".getBytes(StandardCharsets.UTF_8));
        try {
            NativeModStore.writeAtomically(atomicTarget, "replacement".getBytes(StandardCharsets.UTF_8));
            throw new AssertionError("A nonempty directory was overwritten");
        } catch (IOException expected) {
            require(read(retained).equals("original"));
        }
        try (java.util.stream.Stream<Path> entries = Files.list(files)) {
            require(entries.noneMatch(path -> path.getFileName().toString().startsWith(".patools-write-")));
        }
        Files.delete(retained);
        Files.delete(atomicTarget);
        NativeModStore store = new NativeModStore(files);
        Files.write(files.resolve("preferences.txt"), "Mods \"Legacy Mod\"\n".getBytes(StandardCharsets.UTF_8));
        Path legacy = Files.createDirectories(files.resolve("mods/legacy"));
        Files.write(legacy.resolve("manifest.txt"), "Name \"Legacy Mod\"\n".getBytes(StandardCharsets.UTF_8));
        require(store.list().get(0).enabled);

        String name = store.install(zip("outer/Manifest.txt", "outer/Data/language/de/manifest.txt", "outer/Data/scripts/Test.lua"));
        require(name.equals("Test Mod"));
        require(read(files.resolve("patools-active-mods.txt")).equals("Legacy Mod,Test Mod"));
        NativeModStore.InstalledMod test = store.list().get(1);
        require(test.enabled && read(test.directory.resolve("data/scripts/Test.lua")).equals("data"));
        require(read(test.directory.resolve("manifest.txt")).equals("Name \"Test Mod\"\n"));
        require(Files.isRegularFile(test.directory.resolve("data/language/de/manifest.txt")));
        Path selection = files.resolve("patools-active-mods.txt");
        Files.write(selection, "Legacy Mod,Absent Mod,Test Mod".getBytes(StandardCharsets.UTF_8));
        require(store.listByPriority().get(0).name.equals(name));
        store.moveToPriority(test.name, 1);
        require(read(selection).equals("Test Mod,Absent Mod,Legacy Mod"));
        require(store.list().get(0).name.equals(name));
        store.moveToPriority(test.name, 1);
        require(read(selection).equals("Test Mod,Absent Mod,Legacy Mod"));
        try {
            store.install(zip("outer/manifest.txt", "outer/Thumbnail.PNG", "outer/data/scripts/New.lua"));
            throw new AssertionError("Duplicate archive silently replaced installed data");
        } catch (NativeModStore.DuplicateModException expected) {
            require(expected.name.equals(name));
            require(Files.isRegularFile(test.directory.resolve("data/scripts/Test.lua")));
        }
        require(name.equals(store.update(zip("outer/manifest.txt", "outer/Thumbnail.PNG", "outer/data/scripts/New.lua"), name)));
        require(Files.isRegularFile(test.directory.resolve(NativeModStore.THUMBNAIL)));
        require(read(selection).equals("Test Mod,Absent Mod,Legacy Mod"));
        store.moveToPriority(test.name, 0);
        require(read(selection).equals("Legacy Mod,Absent Mod,Test Mod"));
        require(store.list().get(1).loadPosition == 2);
        require(!Files.exists(test.directory.resolve("data/scripts/Test.lua")));
        require(Files.isRegularFile(test.directory.resolve("data/scripts/New.lua")));
        try {
            store.update(zip("outer/manifest.txt", "outer/data/scripts/Wrong.lua"), "Legacy Mod");
            throw new AssertionError("Mismatched update was accepted");
        } catch (NativeModStore.InvalidModException expected) {
            require(Files.isRegularFile(test.directory.resolve("data/scripts/New.lua")));
        }
        try {
            store.update(zip("outer/manifest.txt", "outer/../invalid"), name);
            throw new AssertionError("Invalid update was accepted");
        } catch (NativeModStore.InvalidModException expected) {
            require(Files.isRegularFile(test.directory.resolve("data/scripts/New.lua")));
            require(read(selection).equals("Legacy Mod,Absent Mod,Test Mod"));
        }
        store.setEnabled(test, false);
        require(name.equals(store.update(zip("outer/manifest.txt", "outer/data/scripts/Test.lua"), name)));
        require(!Files.exists(test.directory.resolve(NativeModStore.THUMBNAIL)));
        require(!store.list().get(1).enabled && read(selection).equals("Legacy Mod,Absent Mod"));
        store.moveToPriority(test.name, 0);
        require(read(selection).equals("Legacy Mod,Absent Mod"));
        Path interrupted = files.resolve("patools-mod-backups").resolve(test.directory.getFileName());
        Files.move(test.directory, interrupted);
        require(new NativeModStore(files).list().size() == 2);
        require(Files.isRegularFile(test.directory.resolve("data/scripts/Test.lua")) && !Files.exists(interrupted));
        Files.createDirectory(interrupted);
        Files.copy(test.directory.resolve("manifest.txt"), interrupted.resolve("manifest.txt"));
        require(new NativeModStore(files).list().size() == 2);
        require(Files.isRegularFile(test.directory.resolve("data/scripts/Test.lua")) && !Files.exists(interrupted));
        store.remove(test);
        require(!Files.exists(test.directory));

        String translation = store.install(zip("outer/Data/Language/Manifest.txt",
                "outer/Data/Language/base-language.txt", "outer/data/language/german/base-language.txt"));
        require(translation.equals("Test Translation"));
        NativeModStore.InstalledMod language = store.list().get(1);
        require(language.enabled && read(language.directory.resolve("manifest.txt")).startsWith("Name \"Test Translation\""));
        require(read(language.directory.resolve("data/language/manifest.txt")).contains("ThumbnailSprite"));
        require(read(language.directory.resolve("data/language/base-language.txt")).equals("data"));
        require(Files.isRegularFile(language.directory.resolve("data/language/german/base-language.txt")));
        store.remove(language);
        require(store.list().size() == 1);

        String nested = "BEGIN Object\n"
                + "    Name Banner\n"
                + "    BEGIN Sprite\n        x 0\n        y 3\n        w 4\n        h 1\n"
                + "    BEGIN Sprite\n        x 0\n        y 3\n        w 4\n        h 1\n"
                + "        RotateType 4\n"
                + "    END\n"
                + "BEGIN Object\n    Name Second\n    Sprite Banner\nEND\n";
        String nestedName = store.install(archive(new String[] {"nested/manifest.txt", "nested/data/materials.txt"},
                new String[] {"Name \"Nested Sprites\"\n", nested}));
        require(nestedName.equals("Nested Sprites"));
        NativeModStore.InstalledMod nestedMod = store.list().get(1);
        String nestedMaterials = read(nestedMod.directory.resolve("data/materials.txt"));
        require(count(nestedMaterials, "BEGIN Sprite") == 1);
        require(count(nestedMaterials, "BEGIN Object") == 2);
        require(nestedMaterials.contains("RotateType 4") && nestedMaterials.contains("Second"));
        require(balanced(nestedMaterials));
        // A repaired definition has no nested sprite left to merge.
        require(MaterialDefinitionRepair.repairNestedSprites(
                nestedMaterials.getBytes(StandardCharsets.UTF_8)) == null);
        // Different rectangles describe distinct sprites, so the file stays as delivered.
        String conflicting = "BEGIN Object\n    BEGIN Sprite\n        x 0\n        y 1\n"
                + "    BEGIN Sprite\n        x 5\n        y 1\n    END\nEND\n";
        require(MaterialDefinitionRepair.repairNestedSprites(
                conflicting.getBytes(StandardCharsets.UTF_8)) == null);
        store.remove(nestedMod);
        require(store.list().size() == 1);

        // A mod installed before this repair is normalised the next time it is listed.
        Path installedByHand = Files.createDirectories(files.resolve("mods/legacy-nested"));
        Files.write(installedByHand.resolve("manifest.txt"), "Name \"Legacy Nested\"\n".getBytes(StandardCharsets.UTF_8));
        Files.createDirectories(installedByHand.resolve("data"));
        Files.write(installedByHand.resolve("data/materials.txt"), nested.getBytes(StandardCharsets.UTF_8));
        NativeModStore.InstalledMod migrated = null;
        for (NativeModStore.InstalledMod mod : new NativeModStore(files).list()) {
            if (mod.name.equals("Legacy Nested")) migrated = mod;
        }
        require(migrated != null);
        String migratedMaterials = read(migrated.directory.resolve("data/materials.txt"));
        require(count(migratedMaterials, "BEGIN Sprite") == 1 && balanced(migratedMaterials));
        try (java.util.stream.Stream<Path> entries = Files.list(migrated.directory.resolve("data"))) {
            require(entries.noneMatch(path -> path.getFileName().toString().startsWith(".patools-write-")));
        }
        store.remove(migrated);
        require(store.list().size() == 1);

        String namedWithComma = store.install(zip("comma/manifest.txt", "comma/data/scripts/Test.lua"));
        require(namedWithComma.equals("警卫, 经典版"));
        require(read(selection).equals("\nLegacy Mod\nAbsent Mod\n警卫, 经典版"));
        NativeModStore reopened = new NativeModStore(files);
        NativeModStore.InstalledMod commaMod = reopened.list().get(1);
        require(commaMod.enabled && commaMod.name.equals(namedWithComma));
        reopened.moveToPriority(commaMod.name, 1);
        require(read(selection).equals("\n警卫, 经典版\nAbsent Mod\nLegacy Mod"));
        reopened.setEnabled(commaMod, false);
        require(read(selection).equals("Absent Mod,Legacy Mod") && !reopened.list().get(1).enabled);
        reopened.remove(commaMod);

        for (String path : Arrays.asList("../escape", "outer/../escape", "/files/escape", "outer/data\\escape")) {
            try (InputStream invalid = zip("outer/manifest.txt", path)) {
                store.install(invalid);
                throw new AssertionError("Unsafe ZIP path was accepted");
            } catch (NativeModStore.InvalidModException expected) {
                require(store.list().size() == 1);
            }
        }
        try {
            store.install(zip("outer/manifest.txt", "outer/Manifest.txt"));
            throw new AssertionError("Conflicting manifest names were accepted");
        } catch (NativeModStore.InvalidModException expected) {
            require(store.list().size() == 1);
        }
        for (String archive : Arrays.copyOfRange(arguments, 1, arguments.length)) {
            try (InputStream file = Files.newInputStream(Paths.get(archive))) {
                System.out.println("Installed " + store.install(file));
            }
        }
        require(store.list().size() == arguments.length);
        for (NativeModStore.InstalledMod mod : store.list()) {
            Path materials = mod.directory.resolve("data/materials.txt");
            if (!Files.isRegularFile(materials)) continue;
            String text = read(materials);
            require(balanced(text));
            if (text.contains("slogan_I")) {
                // The 2010s Chinese Style mod repeats BEGIN Sprite; the engine
                // drops every later object until the run is collapsed.
                require(count(text, "BEGIN Sprite") == 1);
                require(count(text, "BEGIN Object") == 3);
                require(text.contains("ArmedGuard") && text.contains("Guard"));
            }
        }
        System.out.println("ZIP roots, selection migration, load order, update recovery, removal and traversal rejection verified.");
    }

    private static String read(Path path) throws IOException {
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    private static ByteArrayInputStream zip(String... entries) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream archive = new ZipOutputStream(bytes)) {
            for (String entry : entries) {
                archive.putNextEntry(new ZipEntry(entry));
                String text = entry.equals("outer/Manifest.txt") ? "\uFEFFName \"Test Mod\"\n"
                        : entry.equals("outer/Data/Language/Manifest.txt")
                        ? "\uFEFFName \"Test Translation\"\nThumbnailSprite german\n"
                        : entry.equals("comma/manifest.txt") ? "Name \"警卫, 经典版\"\n"
                        : entry.equals("outer/manifest.txt") ? "Name \"Test Mod\"\n" : "data";
                archive.write(text.getBytes(StandardCharsets.UTF_8));
                archive.closeEntry();
            }
        }
        return new ByteArrayInputStream(bytes.toByteArray());
    }

    private static ByteArrayInputStream archive(String[] names, String[] contents) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ZipOutputStream archive = new ZipOutputStream(bytes)) {
            for (int i = 0; i < names.length; ++i) {
                archive.putNextEntry(new ZipEntry(names[i]));
                archive.write(contents[i].getBytes(StandardCharsets.UTF_8));
                archive.closeEntry();
            }
        }
        return new ByteArrayInputStream(bytes.toByteArray());
    }

    private static int count(String text, String token) {
        int total = 0;
        for (int index = text.indexOf(token); index >= 0; index = text.indexOf(token, index + token.length())) ++total;
        return total;
    }

    private static boolean balanced(String text) {
        int depth = 0;
        for (String token : text.trim().split("\\s+")) {
            if (token.equals("BEGIN")) {
                ++depth;
            } else if (token.equals("END") && --depth < 0) {
                return false;
            }
        }
        return depth == 0;
    }

    private static void require(boolean condition) {
        if (!condition) throw new AssertionError("Unexpected mod store state");
    }
}
