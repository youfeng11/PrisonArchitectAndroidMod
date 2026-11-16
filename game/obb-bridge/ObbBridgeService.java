package com.paradoxplaza.prisonarchitect.patools;

import android.app.Service;
import android.content.Intent;
import android.os.Binder;
import android.os.IBinder;
import android.os.ParcelFileDescriptor;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;

import com.youfeng.pa.tools.platform.gameobb.IObbInstaller;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.util.zip.ZipFile;

public final class ObbBridgeService extends Service {
    private static final String CLIENT_PACKAGE = "com.youfeng.pa.tools";
    private static final String OBB_NAME = EmbeddedObb.NAME;
    private static final long MAX_BYTES = 1L << 30;

    private final IObbInstaller.Stub bridge = new IObbInstaller.Stub() {
        @Override
        public synchronized ParcelFileDescriptor openGameObb() {
            enforceClient();
            try {
                // Opening before first launch also prepares the bundled archive.
                try (android.content.res.AssetFileDescriptor ignored = getAssets().openFd(EmbeddedObb.ASSET)) {
                    // The offline build stores this asset without compression.
                } catch (FileNotFoundException unbundledBuild) {
                    return openArchive(new File(directory(), OBB_NAME));
                }
                return openArchive(EmbeddedObb.prepare(ObbBridgeService.this));
            } catch (IOException | ErrnoException e) {
                throw failure(e);
            }
        }

        @Override
        public synchronized void install(ParcelFileDescriptor archive, long length) {
            try {
                enforceClient();
            } catch (SecurityException e) {
                if (archive != null) {
                    try {
                        archive.close();
                    } catch (IOException ignored) {
                    }
                }
                throw e;
            }
            if (archive == null) throw new IllegalArgumentException("缺少待安装 OBB。");
            try (InputStream source = new ParcelFileDescriptor.AutoCloseInputStream(archive);
                 RandomAccessFile handle = EmbeddedObb.openLock(ObbBridgeService.this);
                 FileLock ignored = handle.getChannel().lock()) {
                if (archive.getStatSize() != length) throw new IOException("待安装 OBB 长度不符。");
                replace(source, length, directory());
            } catch (IOException | ErrnoException e) {
                throw failure(e);
            }
        }

        @Override
        public synchronized void restore() {
            enforceClient();
            try (RandomAccessFile handle = EmbeddedObb.openLock(ObbBridgeService.this);
                 FileLock ignored = handle.getChannel().lock()) {
                File folder = directory();
                try (ParcelFileDescriptor backup = openArchive(backupOf(folder))) {
                    long length = backup.getStatSize();
                    try (InputStream source = new ParcelFileDescriptor.AutoCloseInputStream(backup.dup())) {
                        replace(source, length, folder);
                    }
                }
            } catch (IOException | ErrnoException e) {
                throw failure(e);
            }
        }

    };

    @Override
    public IBinder onBind(Intent intent) {
        return bridge;
    }

    private void enforceClient() {
        enforceCallingPermission(getPackageName() + ".permission.PATOOLS_OBB", "无权调用游戏 OBB 服务。");
        try {
            if (getPackageManager().getApplicationInfo(CLIENT_PACKAGE, 0).uid == Binder.getCallingUid()) return;
        } catch (android.content.pm.PackageManager.NameNotFoundException ignored) {
        }
        throw new SecurityException("仅允许 PATools 调用游戏 OBB 服务。");
    }

    private File directory() throws IOException {
        File folder = getObbDir();
        if (folder == null || (!folder.isDirectory() && !folder.mkdirs())) {
            throw new IOException("游戏 OBB 目录不可用。");
        }
        return folder;
    }

    private static File backupOf(File folder) {
        return new File(folder, OBB_NAME + ".patools-backup");
    }

    private static ParcelFileDescriptor openArchive(File file) throws IOException, ErrnoException {
        java.io.FileDescriptor fd = Os.open(file.getPath(),
                OsConstants.O_RDONLY | OsConstants.O_CLOEXEC | OsConstants.O_NOFOLLOW | OsConstants.O_NONBLOCK, 0);
        try {
            android.system.StructStat stat = Os.fstat(fd);
            if (!OsConstants.S_ISREG(stat.st_mode) || stat.st_size < 1 || stat.st_size > MAX_BYTES) {
                throw new IOException("OBB 文件大小或类型无效。");
            }
            return ParcelFileDescriptor.dup(fd);
        } finally {
            Os.close(fd);
        }
    }

    private static void replace(InputStream source, long length, File folder) throws IOException, ErrnoException {
        File target = new File(folder, OBB_NAME);
        File backup = backupOf(folder);
        File staged = File.createTempFile(".patools-", ".tmp", folder);
        try {
            copyArchive(source, length, staged);
            try (ZipFile zip = new ZipFile(staged)) {
                if (!EmbeddedObb.hasGameResources(zip)) {
                    throw new IOException("待安装 OBB 缺少游戏资源。");
                }
            }
            if (!Files.exists(backup.toPath(), LinkOption.NOFOLLOW_LINKS)
                    && Files.exists(target.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                File stagedBackup = File.createTempFile(".patools-backup-", ".tmp", folder);
                try {
                    ParcelFileDescriptor previous = openArchive(target);
                    try (InputStream input = new ParcelFileDescriptor.AutoCloseInputStream(previous)) {
                        copyArchive(input, previous.getStatSize(), stagedBackup);
                    }
                    Files.move(stagedBackup.toPath(), backup.toPath());
                } finally {
                    stagedBackup.delete();
                }
            }
            Files.move(staged.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            staged.delete();
        }
    }

    private static void copyArchive(InputStream input, long length, File file) throws IOException {
        if (length < 1 || length > MAX_BYTES) throw new IOException("待写入 OBB 大小无效。");
        try (FileOutputStream output = new FileOutputStream(file)) {
            byte[] buffer = new byte[64 * 1024];
            long remaining = length;
            while (remaining > 0) {
                int count = input.read(buffer, 0, (int) Math.min(buffer.length, remaining));
                if (count <= 0) throw new IOException("待写入 OBB 提前结束。");
                output.write(buffer, 0, count);
                remaining -= count;
            }
            if (input.read() != -1) throw new IOException("待写入 OBB 长度不符。");
            output.getFD().sync();
        }
    }

    private static IllegalStateException failure(Exception error) {
        return new IllegalStateException("游戏 OBB 操作失败：" + error.getMessage());
    }
}
