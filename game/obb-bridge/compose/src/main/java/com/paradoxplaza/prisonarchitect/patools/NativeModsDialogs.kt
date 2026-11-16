package com.paradoxplaza.prisonarchitect.patools

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp

@Composable
internal fun ModConfirmationDialog(
    @StringRes title: Int,
    message: String,
    @StringRes confirmLabel: Int,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    confirmEnabled: Boolean = true,
    @StringRes cancelLabel: Int = R.string.mods_cancel,
    onCancel: () -> Unit = onDismiss,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(stringResource(title)) },
        text = { Text(message) },
        confirmButton = {
            TextButton(onClick = onConfirm, enabled = confirmEnabled) {
                Text(stringResource(confirmLabel))
            }
        },
        dismissButton = {
            TextButton(onClick = onCancel) { Text(stringResource(cancelLabel)) }
        },
    )
}

@Composable
internal fun ModReplacementDialog(name: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    ModConfirmationDialog(
        title = R.string.mods_replace_title,
        message = stringResource(R.string.mods_replace_message, name),
        confirmLabel = R.string.mods_replace,
        onConfirm = onConfirm,
        onDismiss = onDismiss,
    )
}

@Composable
internal fun ModDetailsDialog(mod: NativeModStore.InstalledMod, onClose: () -> Unit) {
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(mod.name) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (mod.author.isNotBlank()) Text(stringResource(R.string.mods_author, mod.author))
                if (mod.version.isNotBlank()) Text(stringResource(R.string.mods_version, mod.version))
                if (mod.date.isNotBlank()) Text(stringResource(R.string.mods_date, mod.date))
                Text(mod.description.ifBlank { stringResource(R.string.mods_no_description) })
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.mods_close)) } },
    )
}
