package com.paradoxplaza.prisonarchitect.patools;

import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Enumeration;
import java.util.zip.ZipEntry;
import java.util.zip.ZipException;
import java.util.zip.ZipFile;

import me.zhanghai.android.libarchive.Archive;
import me.zhanghai.android.libarchive.ArchiveEntry;
import me.zhanghai.android.libarchive.ArchiveException;

import static com.paradoxplaza.prisonarchitect.patools.NativeModStore.ModError.*;

final class ModArchive {
    interface EntryData {
        InputStream open() throws IOException;
    }

    interface Visitor {
        void entry(String name, boolean directory, long size, long crc, EntryData data) throws IOException;
    }

    private final Path file;
    private final boolean zip;

    ModArchive(Path file) throws IOException {
        this.file = file;
        try (InputStream input = Files.newInputStream(file)) {
            int first = input.read();
            int second = input.read();
            int third = input.read();
            int fourth = input.read();
            zip = first == 'P' && second == 'K' &&
                    ((third == 3 && fourth == 4) || (third == 5 && fourth == 6) || (third == 7 && fourth == 8));
        }
    }

    void visit(Visitor visitor) throws IOException {
        if (zip) visitZip(visitor);
        else visitNative(visitor);
    }

    private void visitZip(Visitor visitor) throws IOException {
        try (ZipFile archive = new ZipFile(file.toFile())) {
            Enumeration<? extends ZipEntry> entries = archive.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                visitor.entry(entry.getName(), entry.isDirectory(), entry.getSize(), entry.getCrc(),
                        () -> archive.getInputStream(entry));
            }
        } catch (ZipException failure) {
            throw new NativeModStore.InvalidModException(CORRUPT_ENTRY);
        }
    }

    private void visitNative(Visitor visitor) throws IOException {
        long archive = Archive.readNew();
        try {
            Archive.readSupportFilterGzip(archive);
            Archive.readSupportFilterBzip2(archive);
            Archive.readSupportFilterXz(archive);
            Archive.readSupportFormat7zip(archive);
            Archive.readSupportFormatRar(archive);
            Archive.readSupportFormatRar5(archive);
            Archive.readSupportFormatTar(archive);
            Archive.readOpenFileName(archive, file.toString().getBytes(StandardCharsets.UTF_8), 65536);
            long remaining = NativeModStore.MAX_EXPANDED;
            for (long entry; (entry = Archive.readNextHeader(archive)) != 0; ) {
                if (ArchiveEntry.isEncrypted(entry)) {
                    throw new NativeModStore.InvalidModException(ENCRYPTED_ARCHIVE);
                }
                int type = ArchiveEntry.filetype(entry);
                boolean directory = type == ArchiveEntry.AE_IFDIR;
                if ((!directory && type != ArchiveEntry.AE_IFREG) || ArchiveEntry.hardlinkIsSet(entry)) {
                    throw new NativeModStore.InvalidModException(UNSUPPORTED_ENTRY);
                }
                long size = ArchiveEntry.size(entry);
                if (size < 0 || size > remaining) throw new NativeModStore.InvalidModException(ARCHIVE_SIZE);
                remaining -= size;
                String name = ArchiveEntry.pathnameUtf8(entry);
                if (name == null) {
                    byte[] rawName = ArchiveEntry.pathname(entry);
                    if (rawName == null) throw new NativeModStore.InvalidModException(INVALID_PATH);
                    name = new String(rawName, StandardCharsets.UTF_8);
                }
                if ((Archive.format(archive) & Archive.FORMAT_BASE_MASK) == Archive.FORMAT_TAR) {
                    while (name.startsWith("./")) name = name.substring(2);
                    if (directory && (name.isEmpty() || name.equals("."))) continue;
                }
                visitor.entry(name, directory, size, -1, () -> new EntryInputStream(archive));
            }
        } catch (ArchiveException failure) {
            String message = failure.getMessage();
            NativeModStore.ModError reason = CORRUPT_ENTRY;
            if (message != null && message.contains("Unrecognized archive format")) reason = UNSUPPORTED_FORMAT;
            if (Archive.readHasEncryptedEntries(archive) > 0) reason = ENCRYPTED_ARCHIVE;
            NativeModStore.InvalidModException error = new NativeModStore.InvalidModException(reason);
            error.initCause(failure);
            throw error;
        } finally {
            Archive.readFree(archive);
        }
    }

    // The enclosing archive owns the entry stream and advances it after each callback.
    private static final class EntryInputStream extends InputStream {
        private final long archive;
        private final byte[] single = new byte[1];

        EntryInputStream(long archive) { this.archive = archive; }

        @Override
        public int read() throws IOException {
            return read(single, 0, 1) == -1 ? -1 : single[0] & 0xFF;
        }

        @Override
        public int read(byte[] bytes, int offset, int length) throws IOException {
            if (length == 0) return 0;
            ByteBuffer output = ByteBuffer.wrap(bytes, offset, length);
            Archive.readData(archive, output);
            int count = output.position() - offset;
            return count == 0 ? -1 : count;
        }
    }
}
