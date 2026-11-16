package com.paradoxplaza.prisonarchitect.patools

import android.app.ActivityManager
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.os.Process
import android.os.SystemClock
import android.util.Log
import androidx.annotation.StringRes
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import java.io.FileNotFoundException
import java.io.IOException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

internal class NativeModsModel(private val context: Context) : ViewModel() {
    data class Replacement(val name: String, val uri: Uri)
    class Notice(@StringRes val resource: Int, vararg arguments: String) {
        val args = arguments
    }

    private val store = NativeModStore(context.filesDir.toPath())
    private var hasResumed = false
    var mods by mutableStateOf<List<NativeModStore.InstalledMod>>(emptyList())
        private set
    var busy by mutableStateOf(false)
        private set
    var refreshing by mutableStateOf(false)
        private set
    var pickingArchive by mutableStateOf(false)
        private set
    var replacement by mutableStateOf<Replacement?>(null)
        private set
    var externalArchive by mutableStateOf<Uri?>(null)
        private set
    var loaded by mutableStateOf(false)
        private set
    var message by mutableStateOf<Notice?>(null)
        private set
    var needsRestart by mutableStateOf(false)
        private set
    var thumbnailRevision by mutableStateOf(0)
        private set

    init { reload(showConfirmation = false) }

    fun onResume() {
        if (hasResumed) refresh(showConfirmation = false)
        hasResumed = true
    }

    fun refresh(showConfirmation: Boolean = true) {
        if (busy || pickingArchive || replacement != null || externalArchive != null) return
        reload(showConfirmation)
    }

    private fun reload(showConfirmation: Boolean) = runTask {
        refreshing = loaded
        try {
            mods = withContext(Dispatchers.IO) { store.listByPriority() }
            loaded = true
            thumbnailRevision++
            if (showConfirmation) message = Notice(R.string.mods_refreshed)
        } finally {
            refreshing = false
        }
    }

    fun restorePicker(state: Bundle) {
        if (state.getBoolean("pickingArchive")) startPicker()
    }

    fun startPicker() {
        pickingArchive = true
    }

    fun onArchivePicked(uri: Uri?) {
        pickingArchive = false
        if (uri == null) return
        importArchive(uri)
    }

    fun offerExternalArchive(uri: Uri) {
        externalArchive = uri
    }

    fun dismissExternalArchive() {
        externalArchive = null
    }

    fun confirmExternalArchive() {
        val uri = externalArchive ?: return
        if (busy || pickingArchive || replacement != null) return
        externalArchive = null
        importArchive(uri)
    }

    fun dismissReplacement() {
        replacement = null
    }

    fun confirmReplacement() {
        val confirmed = replacement ?: return
        replacement = null
        importArchive(confirmed.uri, confirmed.name)
    }

    fun enable(mod: NativeModStore.InstalledMod, value: Boolean) = change { store.setEnabled(mod, value) }

    fun move(mod: NativeModStore.InstalledMod, targetIndex: Int) {
        if (busy || !loaded || pickingArchive || replacement != null) return
        val previous = mods
        val from = previous.indexOfFirst { it.directory == mod.directory && it.enabled }
        val enabledCount = previous.count { it.enabled }
        if (from < 0 || targetIndex !in 0 until enabledCount || from == targetIndex) return

        mods = previous.toMutableList().apply { add(targetIndex, removeAt(from)) }
        runTask {
            try {
                changeAndReload { store.moveToPriority(mod.name, targetIndex) }
            } catch (failure: Exception) {
                mods = previous
                throw failure
            }
        }
    }

    fun remove(mod: NativeModStore.InstalledMod) = change { store.remove(mod) }

    fun runningGamePid(): Int {
        val manager = context.getSystemService(ActivityManager::class.java)
        return manager.runningAppProcesses?.firstOrNull {
            it.uid == Process.myUid() && it.processName == context.packageName
        }?.pid ?: 0
    }

    fun restarted() {
        needsRestart = false
        message = null
    }

    fun restart(openGame: () -> Unit) = runTask {
        val pid = runningGamePid()
        if (pid != 0) Process.killProcess(pid)
        val deadline = SystemClock.elapsedRealtime() + 2_500
        while (runningGamePid() != 0 && SystemClock.elapsedRealtime() < deadline) delay(50)
        if (runningGamePid() != 0) error(R.string.mods_game_still_running)
        else {
            restarted()
            openGame()
        }
    }

    fun error(@StringRes resource: Int, vararg arguments: String) {
        message = Notice(resource, *arguments)
    }

    fun dismissMessage(notice: Notice) {
        if (message === notice) message = null
    }

    private fun importArchive(uri: Uri, name: String? = null) = runTask {
        try {
            changeAndReload {
                val stream = context.contentResolver.openInputStream(uri) ?: throw FileNotFoundException()
                stream.use { if (name == null) store.install(it) else store.update(it, name) }
            }
            thumbnailRevision++
        } catch (_: FileNotFoundException) {
            error(R.string.mods_import_unreadable)
        } catch (duplicate: NativeModStore.DuplicateModException) {
            replacement = Replacement(duplicate.name, uri)
        }
    }

    private fun change(action: () -> Unit) = runTask { changeAndReload(action) }

    private suspend fun changeAndReload(action: () -> Unit) {
        mods = withContext(Dispatchers.IO) {
            action()
            store.listByPriority()
        }
        needsRestart = true
        loaded = true
        message = Notice(R.string.mods_saved)
    }

    private fun runTask(work: suspend () -> Unit) {
        if (busy) return
        busy = true
        viewModelScope.launch {
            try {
                work()
            } catch (failure: CancellationException) {
                throw failure
            } catch (failure: NativeModStore.InvalidModException) {
                val resource = when (failure.reason) {
                    NativeModStore.ModError.NAME_MISMATCH -> R.string.mods_error_name_mismatch
                    NativeModStore.ModError.AMBIGUOUS_NAME -> R.string.mods_error_ambiguous_name
                    NativeModStore.ModError.MISSING_UPDATE -> R.string.mods_error_missing_update
                    NativeModStore.ModError.DUPLICATE_PATH_OR_SIZE -> R.string.mods_error_duplicate_path_or_size
                    NativeModStore.ModError.CORRUPT_ENTRY -> R.string.mods_error_corrupt_entry
                    NativeModStore.ModError.MISSING_MANIFEST -> R.string.mods_error_missing_manifest
                    NativeModStore.ModError.TOO_MANY_ENTRIES -> R.string.mods_error_too_many_entries
                    NativeModStore.ModError.INVALID_PATH -> R.string.mods_error_invalid_path
                    NativeModStore.ModError.MULTIPLE_MODS -> R.string.mods_error_multiple_mods
                    NativeModStore.ModError.INVALID_NAME -> R.string.mods_error_invalid_name
                    NativeModStore.ModError.LONG_SELECTION -> R.string.mods_error_long_selection
                    NativeModStore.ModError.TEXT_SIZE -> R.string.mods_error_text_size
                    NativeModStore.ModError.TEXT_ENCODING -> R.string.mods_error_text_encoding
                    NativeModStore.ModError.ARCHIVE_SIZE -> R.string.mods_error_archive_size
                    NativeModStore.ModError.ENCRYPTED_ARCHIVE -> R.string.mods_error_encrypted_archive
                    NativeModStore.ModError.UNSUPPORTED_FORMAT -> R.string.mods_error_archive_format
                    NativeModStore.ModError.UNSUPPORTED_ENTRY -> R.string.mods_error_archive_entry
                    NativeModStore.ModError.DUPLICATE -> R.string.mods_error_duplicate
                }
                error(resource, *failure.arguments)
            } catch (failure: IOException) {
                Log.w("PAToolsMods", "Could not read or change local mods", failure)
                error(R.string.mods_io_error)
            } catch (failure: SecurityException) {
                Log.w("PAToolsMods", "Mod operation permission denied", failure)
                error(R.string.mods_access_error)
            } finally {
                busy = false
            }
        }
    }
}
