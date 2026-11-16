package com.paradoxplaza.prisonarchitect.patools

import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
internal fun NativeModCard(
    mod: NativeModStore.InstalledMod,
    controlsEnabled: Boolean,
    showDragHandle: Boolean,
    canMoveToTop: Boolean,
    elevated: Boolean,
    thumbnailRevision: Int,
    onToggle: (Boolean) -> Unit,
    onMoveToTop: () -> Unit,
    onDetails: () -> Unit,
    onRemove: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = MaterialTheme.shapes.medium,
        color = if (elevated) MaterialTheme.colorScheme.surfaceContainerHighest else MaterialTheme.colorScheme.surfaceContainerLow,
        shadowElevation = if (elevated) 6.dp else 0.dp,
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(24.dp), contentAlignment = Alignment.Center) {
                    if (showDragHandle) DragHandle()
                }
                ModThumbnail(mod.directory, thumbnailRevision)
                Column(Modifier.weight(1f)) {
                    Text(mod.name, style = MaterialTheme.typography.titleMedium)
                    val summary = listOf(mod.author, mod.version).filter { it.isNotBlank() }.joinToString(" · ")
                    if (summary.isNotEmpty()) Text(summary, style = MaterialTheme.typography.bodySmall)
                }
                val enableLabel = stringResource(R.string.mods_enable_label, mod.name)
                Switch(
                    checked = mod.enabled,
                    enabled = controlsEnabled,
                    onCheckedChange = onToggle,
                    modifier = Modifier.semantics { contentDescription = enableLabel },
                )
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                if (mod.enabled) {
                    TextButton(enabled = controlsEnabled && canMoveToTop, onClick = onMoveToTop) {
                        ModActionLabel(R.drawable.ms_vertical_align_top_24, R.string.mods_move_to_top)
                    }
                }
                TextButton(enabled = controlsEnabled, onClick = onDetails) {
                    Text(stringResource(R.string.mods_details))
                }
                TextButton(
                    enabled = controlsEnabled,
                    onClick = onRemove,
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) {
                    ModActionLabel(R.drawable.ms_delete_24, R.string.mods_delete)
                }
            }
        }
    }
}

@Composable
internal fun ModActionLabel(@DrawableRes icon: Int, @StringRes label: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(painterResource(icon), contentDescription = null, modifier = Modifier.size(18.dp))
        Text(stringResource(label))
    }
}

@Composable
private fun DragHandle() {
    val color = MaterialTheme.colorScheme.onSurfaceVariant
    val label = stringResource(R.string.mods_drag_label)
    Canvas(Modifier.size(24.dp).semantics { contentDescription = label }) {
        val gap = 5.dp.toPx()
        val radius = 1.5.dp.toPx()
        for (row in -1..1) {
            val y = center.y + row * gap
            drawCircle(color, radius, Offset(center.x - gap / 2f, y))
            drawCircle(color, radius, Offset(center.x + gap / 2f, y))
        }
    }
}
