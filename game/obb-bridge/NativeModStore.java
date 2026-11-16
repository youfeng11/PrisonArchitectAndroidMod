package com.paradoxplaza.prisonarchitect.patools;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;
import java.util.zip.CRC32;

final class NativeModStore {
    private static final long MAX_ARCHIVE = 512L * 1024 * 1024;
    static final long MAX_EXPANDED = 1024L * 1024 * 1024;
    private static final int MAX_ENTRIES = 20000;
    private static final int MAX_SELECTION = 4096;
    private static final String MANIFEST = "manifest.txt";
    static final String THUMBNAIL = "thumbnail.png";
    private static final String LANGUAGE_DIRECTORY = "data/language/";
    private static final String LANGUAGE_MANIFEST = LANGUAGE_DIRECTORY + MANIFEST;
    private static final String DATA = "data";
    private static final String MATERIALS = "materials.txt";
    private static final long MAX_MATERIALS = 8L * 1024 * 1024;

    private final Path files;
    private final Path mods;
    private final Path selection;
    private final Path backups;

    NativeModStore(Path files) {
        this.files = files;
        mods = files.resolve("mods");
        selection = files.resolve("patools-active-mods.txt");
        backups = files.resolve("patools-mod-backups");
    }

    static final class InstalledMod {
        final Path directory;
        final String name;
        final boolean enabled;
        final int loadPosition;
        final String author;
        final String version;
        final String date;
        final String description;

        InstalledMod(Path directory, Map<String, String> manifest, int loadPosition) {
            this.directory = directory;
            this.name = manifest.get("Name");
            this.loadPosition = loadPosition;
            this.enabled = loadPosition >= 0;
            this.author = manifest.getOrDefault("Author", "");
            this.version = manifest.getOrDefault("Version", "");
            this.date = manifest.getOrDefault("Date", "");
            this.description = manifest.getOrDefault("Description", "");
        }
    }

    List<InstalledMod> list() throws IOException {
        recoverUpdates();
        repairInstalledMaterials();
        List<InstalledMod> list = new ArrayList<>();
        if (!Files.isDirectory(mods, LinkOption.NOFOLLOW_LINKS)) return list;
        List<String> enabled = new ArrayList<>(enabledNames());
        try (Stream<Path> directories = Files.list(mods)) {
            for (Path directory : (Iterable<Path>) directories.sorted()::iterator) {
                Path manifest = directory.resolve(MANIFEST);
                if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)
                        || !Files.isRegularFile(manifest, LinkOption.NOFOLLOW_LINKS)) continue;
                try {
                    String text = readSmallText(manifest, 64 * 1024);
                    Map<String, String> metadata = manifestMetadata(text);
                    list.add(new InstalledMod(directory, metadata, enabled.indexOf(metadata.get("Name"))));
                } catch (InvalidModException ignored) {
                    // A directory installed outside this manager may have a malformed manifest.
                }
            }
        }
        list.sort(Comparator.comparingInt((InstalledMod mod) -> mod.enabled ? mod.loadPosition : Integer.MAX_VALUE)
                .thenComparing(mod -> mod.name, String.CASE_INSENSITIVE_ORDER));
        return list;
    }

    List<InstalledMod> listByPriority() throws IOException {
        List<InstalledMod> installed = list();
        // The engine applies the final layer last. Display that layer first.
        installed.sort(Comparator.comparingInt((InstalledMod mod) -> mod.loadPosition).reversed());
        return installed;
    }

    String install(InputStream input) throws IOException {
        return install(input, null);
    }

    String update(InputStream input, String installedName) throws IOException {
        return install(input, installedName);
    }

    private String install(InputStream input, String installedName) throws IOException {
        Path staging = Files.createTempDirectory(files, ".patools-mod-");
        try {
            Path download = staging.resolve("mod.archive");
            Path content = Files.createDirectory(staging.resolve("content"));
            try (OutputStream output = Files.newOutputStream(download)) {
                copy(input, output, MAX_ARCHIVE, null);
            }
            extract(download, content);
            try {
                repairModMaterials(content);
            } catch (IOException | RuntimeException failure) {
                // A definition this repair cannot prove safe stays untouched.
            }
            Path manifest = content.resolve(MANIFEST);
            String text = readSmallText(manifest, 64 * 1024);
            // Keep the UTF-8 signature out of the native parser's first token.
            if (text.startsWith("\uFEFF")) {
                text = text.substring(1);
                Files.write(manifest, text.getBytes(StandardCharsets.UTF_8));
            }
            String name = parseManifestName(text);
            if (installedName != null && !installedName.equals(name)) {
                throw new InvalidModException(ModError.NAME_MISMATCH, installedName);
            }
            InstalledMod installed = null;
            for (InstalledMod mod : list()) {
                if (!mod.name.equals(name)) continue;
                if (installed != null) throw new InvalidModException(ModError.AMBIGUOUS_NAME);
                installed = mod;
            }
            if (installedName == null && installed != null) throw new DuplicateModException(name);
            if (installedName != null) {
                if (installed == null) throw new InvalidModException(ModError.MISSING_UPDATE, installedName);
                replaceContent(installed.directory, content);
                return name;
            }
            Files.createDirectories(mods);
            Path destination = mods.resolve("patools_" + id(name));
            Set<String> enabled = enabledNames();
            enabled.add(name);
            Files.move(content, destination, StandardCopyOption.ATOMIC_MOVE);
            try {
                writeSelection(enabled);
            } catch (IOException failure) {
                Files.move(destination, content, StandardCopyOption.ATOMIC_MOVE);
                throw failure;
            }
            return name;
        } finally {
            discard(staging);
        }
    }

    private void replaceContent(Path destination, Path content) throws IOException {
        Files.createDirectories(backups);
        Path previous = backups.resolve(destination.getFileName());
        Files.move(destination, previous, StandardCopyOption.ATOMIC_MOVE);
        try {
            Files.move(content, destination, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException failure) {
            try {
                Files.move(previous, destination, StandardCopyOption.ATOMIC_MOVE);
            } catch (IOException rollback) {
                failure.addSuppressed(rollback);
            }
            throw failure;
        }
        discard(previous);
    }

    private void recoverUpdates() throws IOException {
        if (!Files.isDirectory(backups, LinkOption.NOFOLLOW_LINKS)) return;
        try (Stream<Path> entries = Files.list(backups)) {
            for (Path previous : (Iterable<Path>) entries::iterator) {
                if (!Files.isDirectory(previous, LinkOption.NOFOLLOW_LINKS)) continue;
                Path destination = mods.resolve(previous.getFileName());
                if (Files.isDirectory(destination, LinkOption.NOFOLLOW_LINKS)) {
                    discard(previous);
                } else if (!Files.exists(destination, LinkOption.NOFOLLOW_LINKS)
                        && Files.isRegularFile(previous.resolve(MANIFEST), LinkOption.NOFOLLOW_LINKS)) {
                    Files.createDirectories(mods);
                    Files.move(previous, destination, StandardCopyOption.ATOMIC_MOVE);
                }
            }
        }
    }

    /* Desktop mods sometimes repeat BEGIN Sprite without closing the previous
     * block. The engine nests definitions by BEGIN/END depth, so every later
     * object becomes a child of that sprite and is never registered. Collapse
     * the repeated declarations into the single block they describe. */
    private static void repairModMaterials(Path mod) throws IOException {
        Path data = child(mod, DATA);
        Path materials = data == null || !Files.isDirectory(data, LinkOption.NOFOLLOW_LINKS)
                ? null : child(data, MATERIALS);
        if (materials == null || !Files.isRegularFile(materials, LinkOption.NOFOLLOW_LINKS)) return;
        long size = Files.size(materials);
        if (size <= 0 || size > MAX_MATERIALS) return;
        byte[] repaired = MaterialDefinitionRepair.repairNestedSprites(Files.readAllBytes(materials));
        if (repaired != null) writeAtomically(materials, repaired);
    }

    private void repairInstalledMaterials() {
        if (!Files.isDirectory(mods, LinkOption.NOFOLLOW_LINKS)) return;
        try (Stream<Path> entries = Files.list(mods)) {
            for (Path directory : (Iterable<Path>) entries::iterator) {
                if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) continue;
                try {
                    repairModMaterials(directory);
                } catch (IOException | RuntimeException ignored) {
                    // A definition this repair cannot prove safe stays untouched.
                }
            }
        } catch (IOException ignored) {
        }
    }

    private static Path child(Path directory, String name) throws IOException {
        if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) return null;
        try (Stream<Path> entries = Files.list(directory)) {
            for (Path entry : (Iterable<Path>) entries::iterator) {
                if (entry.getFileName().toString().equalsIgnoreCase(name)) return entry;
            }
        }
        return null;
    }

    void setEnabled(InstalledMod mod, boolean enabled) throws IOException {
        Set<String> names = enabledNames();
        if (enabled) names.add(mod.name);
        else names.remove(mod.name);
        writeSelection(names);
    }

    void moveToPriority(String name, int targetIndex) throws IOException {
        List<String> names = new ArrayList<>(enabledNames());
        List<String> priority = new ArrayList<>();
        for (InstalledMod entry : listByPriority()) {
            if (entry.enabled && !priority.contains(entry.name)) priority.add(entry.name);
        }
        int current = priority.indexOf(name);
        if (current < 0 || targetIndex < 0 || targetIndex >= priority.size() || current == targetIndex) return;
        Set<String> installed = new HashSet<>(priority);
        priority.add(targetIndex, priority.remove(current));
        int layer = priority.size() - 1;
        for (int i = 0; i < names.size(); ++i) {
            if (installed.contains(names.get(i))) names.set(i, priority.get(layer--));
        }
        writeSelection(new LinkedHashSet<>(names));
    }

    void remove(InstalledMod mod) throws IOException {
        Path trash = Files.createTempDirectory(files, ".patools-trash-");
        Path moved = trash.resolve("content");
        try {
            Files.move(mod.directory, moved, StandardCopyOption.ATOMIC_MOVE);
            try {
                setEnabled(mod, false);
            } catch (IOException failure) {
                Files.move(moved, mod.directory, StandardCopyOption.ATOMIC_MOVE);
                throw failure;
            }
        } catch (IOException failure) {
            if (!Files.exists(moved)) discard(trash);
            throw failure;
        }
        discard(trash);
    }

    private static void extract(Path archive, Path target) throws IOException {
        ModArchive source = new ModArchive(archive);
        String root = findRoot(source);
        Set<Path> written = new HashSet<>();
        source.visit(new ModArchive.Visitor() {
            private long remaining = MAX_EXPANDED;

            @Override
            public void entry(String path, boolean directory, long size, long checksum, ModArchive.EntryData data)
                    throws IOException {
                if (directory || !path.startsWith(root) || isMetadata(path)) return;
                String relative = path.substring(root.length());
                if (relative.equalsIgnoreCase(MANIFEST)) {
                    relative = MANIFEST;
                } else if (relative.equalsIgnoreCase(THUMBNAIL)) {
                    relative = THUMBNAIL;
                } else if (relative.equalsIgnoreCase(LANGUAGE_MANIFEST)) {
                    relative = LANGUAGE_MANIFEST;
                } else if (relative.regionMatches(true, 0, LANGUAGE_DIRECTORY, 0, LANGUAGE_DIRECTORY.length())) {
                    relative = LANGUAGE_DIRECTORY + relative.substring(LANGUAGE_DIRECTORY.length());
                } else if (relative.regionMatches(true, 0, "data/", 0, 5)) {
                    relative = "data/" + relative.substring(5);
                }
                Path output = target.resolve(relative);
                if (!written.add(output) || size > remaining) {
                    throw new InvalidModException(ModError.DUPLICATE_PATH_OR_SIZE);
                }
                Files.createDirectories(output.getParent());
                CRC32 crc = checksum >= 0 ? new CRC32() : null;
                try (InputStream input = data.open(); OutputStream sink = Files.newOutputStream(output)) {
                    long length = copy(input, sink, remaining, crc);
                    if ((size >= 0 && length != size) || (crc != null && crc.getValue() != checksum)) {
                        throw new InvalidModException(ModError.CORRUPT_ENTRY);
                    }
                    remaining -= length;
                }
            }
        });
        if (!written.contains(target.resolve(MANIFEST))) {
            Path languageManifest = target.resolve(LANGUAGE_MANIFEST);
            if (!written.contains(languageManifest)) {
                throw new InvalidModException(ModError.MISSING_MANIFEST);
            }
            Files.copy(languageManifest, target.resolve(MANIFEST));
        }
    }

    private static String findRoot(ModArchive source) throws IOException {
        List<String> roots = new ArrayList<>();
        source.visit(new ModArchive.Visitor() {
            private int count;

            @Override
            public void entry(String name, boolean directory, long size, long checksum, ModArchive.EntryData data)
                    throws IOException {
                if (++count > MAX_ENTRIES) throw new InvalidModException(ModError.TOO_MANY_ENTRIES);
                String path = directory && name.endsWith("/") ? name.substring(0, name.length() - 1) : name;
                for (String segment : path.split("/", -1)) {
                    if (segment.isEmpty() || segment.equals(".") || segment.equals("..")
                            || segment.contains("\\") || segment.contains(":")
                            || segment.codePoints().anyMatch(Character::isISOControl)) {
                        throw new InvalidModException(ModError.INVALID_PATH);
                    }
                }
                int slash = path.lastIndexOf('/');
                if (!directory && !isMetadata(name) && path.substring(slash + 1).equalsIgnoreCase(MANIFEST)) {
                    roots.add(path.substring(0, slash + 1));
                }
            }
        });
        roots.sort(Comparator.comparingInt(String::length));
        if (roots.isEmpty()) throw new InvalidModException(ModError.MISSING_MANIFEST);
        String root = roots.get(0);
        if (root.length() >= LANGUAGE_DIRECTORY.length()) {
            int start = root.length() - LANGUAGE_DIRECTORY.length();
            if ((start == 0 || root.charAt(start - 1) == '/')
                    && root.regionMatches(true, start, LANGUAGE_DIRECTORY, 0, LANGUAGE_DIRECTORY.length())) {
                root = root.substring(0, start);
            }
        }
        for (int i = 1; i < roots.size(); i++) {
            String other = roots.get(i);
            if (!other.startsWith(root) || !other.regionMatches(true, root.length(), "data/", 0, 5)) {
                throw new InvalidModException(ModError.MULTIPLE_MODS);
            }
        }
        return root;
    }

    private static boolean isMetadata(String path) {
        return path.startsWith("__MACOSX/") || path.endsWith("/.DS_Store") || path.equals(".DS_Store");
    }

    private static String parseManifestName(String text) throws InvalidModException {
        for (String line : text.replaceFirst("^\uFEFF", "").split("\\R")) {
            String[] fields = line.trim().split("[ \\t]+", 2);
            if (fields.length != 2 || !fields[0].equals("Name")) continue;
            String value = fields[1];
            if (value.startsWith("\"")) {
                int end = value.indexOf('"', 1);
                if (end < 0) break;
                value = value.substring(1, end);
            } else {
                value = value.split("[ \\t]", 2)[0];
            }
            if (!value.trim().isEmpty() && !value.equals("(empty)") && !value.contains("\"")
                    && value.codePoints().noneMatch(Character::isISOControl)) return value;
            break;
        }
        throw new InvalidModException(ModError.INVALID_NAME);
    }

    private static Map<String, String> manifestMetadata(String text) throws InvalidModException {
        Map<String, String> metadata = new LinkedHashMap<>();
        metadata.put("Name", parseManifestName(text));
        Set<String> keys = new HashSet<>(Arrays.asList("Author", "Version", "Date", "Description"));
        for (String line : text.split("\\R")) {
            String[] fields = line.trim().split("[ \\t]+", 2);
            if (fields.length != 2 || !keys.contains(fields[0])) continue;
            String value = fields[1];
            if (value.startsWith("\"")) {
                int end = value.lastIndexOf('"');
                if (end == 0) continue;
                value = value.substring(1, end);
            }
            metadata.putIfAbsent(fields[0], value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n"));
        }
        return metadata;
    }

    private Set<String> enabledNames() throws IOException {
        String names = "";
        if (Files.exists(selection)) {
            names = readSmallText(selection, MAX_SELECTION);
        } else {
            Path preferences = files.resolve("preferences.txt");
            if (Files.exists(preferences)) {
                for (String line : readSmallText(preferences, 128 * 1024).split("\\R")) {
                    String[] fields = line.trim().split("[ \\t]+", 2);
                    if (fields.length == 2 && fields[0].equals("Mods")) {
                        names = fields[1];
                        if (names.startsWith("\"") && names.endsWith("\"") && names.length() > 1) {
                            names = names.substring(1, names.length() - 1);
                        }
                        break;
                    }
                }
            }
        }
        boolean lineSeparated = names.startsWith("\n");
        Set<String> enabled = new LinkedHashSet<>(Arrays.asList(
                lineSeparated ? names.substring(1).split("\n") : names.split(",")));
        enabled.remove("");
        enabled.remove("(empty)");
        return enabled;
    }

    private void writeSelection(Set<String> names) throws IOException {
        boolean lineSeparated = names.stream().anyMatch(name -> name.contains(","));
        String contents = lineSeparated ? "\n" + String.join("\n", names) : String.join(",", names);
        byte[] encoded = contents.getBytes(StandardCharsets.UTF_8);
        if (encoded.length > MAX_SELECTION) throw new InvalidModException(ModError.LONG_SELECTION);
        writeAtomically(selection, encoded);
    }

    static void writeAtomically(Path target, byte[] contents) throws IOException {
        Path staged = Files.createTempFile(target.getParent(), ".patools-write-", ".tmp");
        try {
            Files.write(staged, contents);
            Files.move(staged, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(staged);
        }
    }

    private static String readSmallText(Path path, int limit) throws IOException {
        if (Files.size(path) > limit) throw new InvalidModException(ModError.TEXT_SIZE);
        try {
            return StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(Files.readAllBytes(path))).toString();
        } catch (CharacterCodingException failure) {
            throw new InvalidModException(ModError.TEXT_ENCODING);
        }
    }

    private static long copy(InputStream input, OutputStream output, long limit, CRC32 crc) throws IOException {
        byte[] buffer = new byte[65536];
        long total = 0;
        for (int count; (count = input.read(buffer)) >= 0; ) {
            total += count;
            if (total > limit) throw new InvalidModException(ModError.ARCHIVE_SIZE);
            output.write(buffer, 0, count);
            if (crc != null) crc.update(buffer, 0, count);
        }
        return total;
    }

    private static String id(String name) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(name.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (int i = 0; i < 16; i++) hex.append(String.format(Locale.ROOT, "%02x", digest[i] & 255));
            return hex.toString();
        } catch (NoSuchAlgorithmException failure) {
            throw new AssertionError(failure);
        }
    }

    private static void discard(Path directory) {
        try (Stream<Path> files = Files.walk(directory)) {
            for (Path path : (Iterable<Path>) files.sorted(Comparator.reverseOrder())::iterator) {
                Files.deleteIfExists(path);
            }
        } catch (IOException | java.io.UncheckedIOException ignored) {
            // Temporary trees have no manifest in the native mod search directory.
        }
    }

    enum ModError {
        NAME_MISMATCH,
        AMBIGUOUS_NAME,
        MISSING_UPDATE,
        DUPLICATE_PATH_OR_SIZE,
        CORRUPT_ENTRY,
        MISSING_MANIFEST,
        TOO_MANY_ENTRIES,
        INVALID_PATH,
        MULTIPLE_MODS,
        INVALID_NAME,
        LONG_SELECTION,
        TEXT_SIZE,
        TEXT_ENCODING,
        ARCHIVE_SIZE,
        ENCRYPTED_ARCHIVE,
        UNSUPPORTED_FORMAT,
        UNSUPPORTED_ENTRY,
        DUPLICATE,
    }

    static class InvalidModException extends IOException {
        final ModError reason;
        final String[] arguments;

        InvalidModException(ModError reason, String... arguments) {
            super(reason.name());
            this.reason = reason;
            this.arguments = arguments;
        }
    }

    static final class DuplicateModException extends InvalidModException {
        final String name;

        DuplicateModException(String name) {
            super(ModError.DUPLICATE);
            this.name = name;
        }
    }
}
