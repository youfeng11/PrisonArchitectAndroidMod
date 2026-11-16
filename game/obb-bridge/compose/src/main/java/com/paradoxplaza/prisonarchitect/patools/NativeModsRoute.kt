package com.paradoxplaza.prisonarchitect.patools

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.res.stringResource

@Composable
internal fun NativeModsRoute(model: NativeModsModel, pickMod: () -> Unit, openGame: () -> Unit) {
    val externalArchive = model.externalArchive
    val replacement = model.replacement
    val canConfirmImport = !model.busy && !model.pickingArchive && replacement == null
    var confirmRestart by rememberSaveable { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val notice = model.message
    val noticeText = notice?.let { stringResource(it.resource, *it.args) }

    LaunchedEffect(externalArchive) {
        if (externalArchive != null) confirmRestart = false
    }
    LaunchedEffect(notice, noticeText) {
        if (notice != null && noticeText != null) {
            snackbar.showSnackbar(noticeText)
            model.dismissMessage(notice)
        }
    }

    NativeModsTheme {
        if (externalArchive != null && canConfirmImport) {
            ModConfirmationDialog(
                title = R.string.mods_import,
                message = stringResource(R.string.mods_import_external_message),
                confirmLabel = R.string.mods_import,
                onConfirm = model::confirmExternalArchive,
                onDismiss = model::dismissExternalArchive,
            )
        }
        if (replacement != null) {
            ModReplacementDialog(replacement.name, model::confirmReplacement, model::dismissReplacement)
        }
        if (confirmRestart) {
            ModConfirmationDialog(
                title = R.string.mods_restart_title,
                message = stringResource(R.string.mods_restart_message),
                confirmLabel = R.string.mods_restart,
                onConfirm = {
                    confirmRestart = false
                    model.restart(openGame)
                },
                onDismiss = { confirmRestart = false },
                cancelLabel = R.string.mods_return,
                onCancel = {
                    confirmRestart = false
                    openGame()
                },
            )
        }
        NativeModsScreen(
            state = NativeModsUiState(
                mods = model.mods,
                loaded = model.loaded,
                canRefresh = canConfirmImport && externalArchive == null,
                canPlay = !model.busy && !model.pickingArchive,
                showProgress = model.busy && !model.refreshing,
                refreshing = model.refreshing,
                needsRestart = model.needsRestart,
                thumbnailRevision = model.thumbnailRevision,
                externalImportPending = externalArchive != null,
            ),
            actions = NativeModsActions(
                pickMod = pickMod,
                refresh = { model.refresh() },
                enable = model::enable,
                move = model::move,
                remove = model::remove,
                play = {
                    if (model.runningGamePid() == 0) {
                        model.restarted()
                        openGame()
                    } else {
                        confirmRestart = true
                    }
                },
            ),
            snackbar = snackbar,
        )
    }
}

@Composable
internal fun NativeModsTheme(content: @Composable () -> Unit) {
    val context = LocalContext.current
    val dark = isSystemInDarkTheme()
    val dynamic = Build.VERSION.SDK_INT >= 31 && !LocalInspectionMode.current
    MaterialTheme(
        colorScheme = when {
            dynamic && dark -> dynamicDarkColorScheme(context)
            dynamic -> dynamicLightColorScheme(context)
            dark -> darkColorScheme()
            else -> lightColorScheme()
        },
        content = content,
    )
}
