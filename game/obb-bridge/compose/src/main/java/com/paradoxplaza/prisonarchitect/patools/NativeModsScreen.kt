package com.paradoxplaza.prisonarchitect.patools

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

internal data class NativeModsUiState(
    val mods: List<NativeModStore.InstalledMod>,
    val loaded: Boolean = true,
    val canRefresh: Boolean = true,
    val canPlay: Boolean = true,
    val showProgress: Boolean = false,
    val refreshing: Boolean = false,
    val needsRestart: Boolean = false,
    val thumbnailRevision: Int = 0,
    val externalImportPending: Boolean = false,
) {
    val canEdit: Boolean get() = loaded && canRefresh
}

internal class NativeModsActions(
    val pickMod: () -> Unit,
    val refresh: () -> Unit,
    val enable: (NativeModStore.InstalledMod, Boolean) -> Unit,
    val move: (NativeModStore.InstalledMod, Int) -> Unit,
    val remove: (NativeModStore.InstalledMod) -> Unit,
    val play: () -> Unit,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun NativeModsScreen(
    state: NativeModsUiState,
    actions: NativeModsActions,
    snackbar: SnackbarHostState,
) {
    val reorder = remember { ModReorderState() }
    var removing by rememberSaveable { mutableStateOf<String?>(null) }
    var details by rememberSaveable { mutableStateOf<String?>(null) }

    LaunchedEffect(state.externalImportPending) {
        if (state.externalImportPending) {
            details = null
            removing = null
        }
    }

    state.mods.firstOrNull { it.directory.fileName.toString() == details }?.let { mod ->
        ModDetailsDialog(mod, onClose = { details = null })
    }
    state.mods.firstOrNull { it.directory.fileName.toString() == removing }?.let { mod ->
        ModConfirmationDialog(
            title = R.string.mods_delete_title,
            message = stringResource(R.string.mods_delete_message, mod.name),
            confirmLabel = R.string.mods_delete,
            confirmEnabled = state.canEdit,
            onConfirm = {
                removing = null
                actions.remove(mod)
            },
            onDismiss = { removing = null },
        )
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.mods_title)) },
                windowInsets = WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal),
            )
        },
        bottomBar = { PlayModBar(state, reorder.dragging == null, actions.play) },
    ) { insets ->
        NativeModsList(
            state = state,
            actions = actions,
            reorder = reorder,
            showDetails = { details = it.directory.fileName.toString() },
            requestRemoval = { removing = it.directory.fileName.toString() },
            modifier = Modifier.fillMaxSize().padding(insets).consumeWindowInsets(insets),
        )
    }
}

@Composable
private fun PlayModBar(state: NativeModsUiState, idle: Boolean, play: () -> Unit) {
    Surface(color = MaterialTheme.colorScheme.surfaceContainer) {
        Box(
            Modifier.fillMaxWidth().windowInsetsPadding(
                WindowInsets.safeDrawing.only(WindowInsetsSides.Bottom + WindowInsetsSides.Horizontal),
            ),
            contentAlignment = Alignment.Center,
        ) {
            if (state.showProgress) {
                LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
            }
            Button(
                modifier = Modifier.widthIn(max = 740.dp).fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                enabled = state.canPlay && idle,
                onClick = play,
            ) {
                ModActionLabel(
                    R.drawable.ms_sports_esports_24,
                    if (state.needsRestart) R.string.mods_apply_and_play else R.string.mods_play,
                )
            }
        }
    }
}
