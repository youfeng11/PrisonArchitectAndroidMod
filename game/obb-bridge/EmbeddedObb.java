package com.paradoxplaza.prisonarchitect.patools;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.util.Log;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.StandardCopyOption;
import java.util.zip.ZipFile;

public final class EmbeddedObb {
    static final String NAME = "main.49.com.paradoxplaza.prisonarchitect.mod.obb";
    static final String ASSET = "patools/main.49.com.paradoxplaza.prisonarchitect.obb";
    private static String path;
    private static Activity preparingActivity;

    private EmbeddedObb() {}

    public static boolean prepareForStartup(Activity activity) {
        if (path != null) return false;
        if (preparingActivity == activity) return true;
        preparingActivity = activity;
        ProgressBar progress = new ProgressBar(activity);
        activity.addContentView(progress, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));
        new Thread(() -> {
            try {
                File archive = prepare(activity.getApplicationContext());
                activity.runOnUiThread(() -> {
                    path = archive.getAbsolutePath();
                    if (preparingActivity == activity) preparingActivity = null;
                    if (activity.isFinishing() || activity.isDestroyed()) return;
                    ((ViewGroup) progress.getParent()).removeView(progress);
                    activity.startActivity(new Intent(activity, activity.getClass())
                            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP));
                });
            } catch (IOException | SecurityException failure) {
                Log.e("PAEmbeddedObb", "Unable to prepare bundled game resources", failure);
                activity.runOnUiThread(() -> showFailure(activity, progress, failure));
            }
        }, "PA resource setup").start();
        return true;
    }

    private static void showFailure(Activity activity, ProgressBar progress, Exception failure) {
        if (preparingActivity == activity) preparingActivity = null;
        if (activity.isFinishing() || activity.isDestroyed()) return;
        ((ViewGroup) progress.getParent()).removeView(progress);
        new AlertDialog.Builder(activity)
                .setTitle("无法准备游戏资源")
                .setMessage("请检查可用存储空间，然后重新打开游戏。\n" + failure.getLocalizedMessage())
                .setPositiveButton("退出", (dialog, which) -> activity.finish())
                .setOnCancelListener(dialog -> activity.finish())
                .show();
    }

    public static String getPath() {
        return path;
    }

    static synchronized File prepare(Context context) throws IOException {
        File folder = context.getObbDir();
        if (folder == null || (!folder.isDirectory() && !folder.mkdirs() && !folder.isDirectory())) {
            throw new IOException("游戏 OBB 目录不可用。");
        }
        File target = new File(folder, NAME);
        try (RandomAccessFile handle = openLock(context);
             FileLock ignored = handle.getChannel().lock()) {
            if (hasGameResources(target)) return target;

            File staged = File.createTempFile(".patools-bundled-", ".tmp", folder);
            try {
                try (InputStream input = context.getAssets().open(ASSET);
                     FileOutputStream output = new FileOutputStream(staged)) {
                    byte[] buffer = new byte[256 * 1024];
                    int count;
                    while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                    output.getFD().sync();
                }
                if (!hasGameResources(staged)) throw new IOException("安装包内置的 OBB 缺少游戏资源。");
                Files.move(staged.toPath(), target.toPath(),
                        StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
                Log.i("PAEmbeddedObb", "Installed bundled OBB (" + target.length() + " bytes)");
                return target;
            } finally {
                Files.deleteIfExists(staged.toPath());
            }
        }
    }

    static RandomAccessFile openLock(Context context) throws IOException {
        return new RandomAccessFile(new File(context.getFilesDir(), "patools-obb.lock"), "rw");
    }

    static boolean hasGameResources(ZipFile archive) {
        return archive.getEntry("data/tablet/composite.csimage") != null
                && archive.getEntry("data/materials.txt") != null;
    }

    private static boolean hasGameResources(File file) {
        if (!Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS)) return false;
        try (ZipFile archive = new ZipFile(file)) {
            return hasGameResources(archive);
        } catch (IOException failure) {
            return false;
        }
    }
}
