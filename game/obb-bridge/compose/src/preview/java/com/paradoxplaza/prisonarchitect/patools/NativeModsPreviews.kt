package com.paradoxplaza.prisonarchitect.patools

import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.tooling.preview.Preview
import java.nio.file.Paths

private val sampleMods = listOf(
    sampleMod("Garden Furniture", loadPosition = 1),
    sampleMod("Additional Guard Uniforms", loadPosition = 0),
    sampleMod("Clearer Signs", loadPosition = -1),
)

private val previewActions = NativeModsActions(
    pickMod = {},
    refresh = {},
    enable = { _, _ -> },
    move = { _, _ -> },
    remove = {},
    play = {},
)

@Preview(name = "Empty mod list", widthDp = 390, heightDp = 760)
@Composable
private fun EmptyModListPreview() {
    NativeModsPreview(NativeModsUiState(mods = emptyList()))
}

@Preview(name = "Installed mods", widthDp = 390, heightDp = 760, locale = "zh")
@Composable
private fun InstalledModsPreview() {
    NativeModsPreview(NativeModsUiState(mods = sampleMods, needsRestart = true))
}

@Preview(name = "Replace an installed mod", widthDp = 390, heightDp = 760, locale = "zh")
@Composable
private fun ReplaceInstalledModPreview() {
    NativeModsPreview(NativeModsUiState(mods = sampleMods, canRefresh = false)) {
        ModReplacementDialog(sampleMods.first().name, onConfirm = {}, onDismiss = {})
    }
}

@Composable
private fun NativeModsPreview(state: NativeModsUiState, dialog: @Composable () -> Unit = {}) {
    NativeModsTheme {
        dialog()
        NativeModsScreen(state, previewActions, remember { SnackbarHostState() })
    }
}

private fun sampleMod(name: String, loadPosition: Int): NativeModStore.InstalledMod {
    return NativeModStore.InstalledMod(
        Paths.get("preview", name),
        mapOf("Name" to name, "Author" to "Example author", "Version" to "1.0"),
        loadPosition,
    )
}
