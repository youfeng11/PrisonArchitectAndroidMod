package com.paradoxplaza.prisonarchitect.patools

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListLayoutInfo
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshDefaults
import androidx.compose.material3.pulltorefresh.pullToRefresh
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import kotlin.math.abs

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun NativeModsList(
    state: NativeModsUiState,
    actions: NativeModsActions,
    reorder: ModReorderState,
    showDetails: (NativeModStore.InstalledMod) -> Unit,
    requestRemoval: (NativeModStore.InstalledMod) -> Unit,
    modifier: Modifier = Modifier,
) {
    val installed = state.mods
    val enabledCount = remember(installed) { installed.count { it.enabled } }
    val listState = rememberLazyListState()
    val edge = with(LocalDensity.current) { 48.dp.toPx() }
    val mods = remember(installed, reorder.dragging, reorder.from, reorder.to) { reorder.displayOrder(installed) }
    val currentMods by rememberUpdatedState(mods)
    val moveMod by rememberUpdatedState(actions.move)
    val canRefresh = state.canRefresh && reorder.dragging == null
    val controlsEnabled = state.canEdit && reorder.dragging == null
    val refreshState = rememberPullToRefreshState()
    val refreshLabel = stringResource(R.string.mods_refresh)
    val raisePriorityLabel = stringResource(R.string.mods_priority_raise)
    val lowerPriorityLabel = stringResource(R.string.mods_priority_lower)
    val drop = reorder.drop

    LaunchedEffect(drop) {
        if (drop != null) {
            drop.remaining.animateTo(0f, tween(180))
            reorder.finishAnimation(drop)
        }
    }
    LaunchedEffect(reorder.dragging) {
        while (reorder.dragging != null) {
            withFrameNanos { }
            val delta = reorder.scrollDelta(listState.layoutInfo, edge)
            if (delta != 0f) {
                listState.scrollBy(delta)
                reorder.updateDropTarget(listState.layoutInfo, currentMods, enabledCount)
            }
        }
    }

    val dragGesture = if (state.canEdit && enabledCount > 1) {
        Modifier.pointerInput(installed) {
            detectDragGesturesAfterLongPress(
                onDragStart = { reorder.start(it.y, listState.layoutInfo, installed, enabledCount) },
                onDrag = { change, amount ->
                    if (reorder.dragging != null) {
                        change.consume()
                        reorder.dragBy(amount.y)
                        reorder.updateDropTarget(listState.layoutInfo, currentMods, enabledCount)
                    }
                },
                onDragEnd = { reorder.finish(moveMod) },
                onDragCancel = { reorder.finish() },
            )
        }
    } else Modifier

    Box(
        modifier = modifier.pullToRefresh(
            isRefreshing = state.refreshing,
            onRefresh = actions.refresh,
            enabled = canRefresh || state.refreshing,
            state = refreshState,
        ).semantics {
            if (canRefresh) customActions = listOf(CustomAccessibilityAction(refreshLabel) {
                actions.refresh()
                true
            })
        },
        contentAlignment = Alignment.TopCenter,
    ) {
        LazyColumn(
            Modifier.widthIn(max = 740.dp).fillMaxSize().then(dragGesture),
            state = listState,
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        stringResource(R.string.mods_enabled_count, enabledCount, mods.size),
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    FilledTonalButton(enabled = controlsEnabled, onClick = actions.pickMod) {
                        ModActionLabel(R.drawable.ms_add_24, R.string.mods_import)
                    }
                }
            }
            if (state.loaded) item {
                Text(
                    stringResource(if (mods.isEmpty()) R.string.mods_empty else R.string.mods_priority_hint),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            itemsIndexed(mods, key = { _, mod -> mod.directory.toString() }) { index, mod ->
                val key = mod.directory.toString()
                val moving = reorder.dragging?.directory == mod.directory
                val settling = drop?.takeIf { it.key == key }
                val elevated = moving || settling != null
                val showDragHandle = mod.enabled && enabledCount > 1
                val accessibleReorder = if (showDragHandle && controlsEnabled) {
                    Modifier.semantics {
                        customActions = buildList {
                            if (index > 0) add(CustomAccessibilityAction(raisePriorityLabel) {
                                actions.move(mod, index - 1)
                                true
                            })
                            if (index < enabledCount - 1) add(CustomAccessibilityAction(lowerPriorityLabel) {
                                actions.move(mod, index + 1)
                                true
                            })
                        }
                    }
                } else Modifier
                NativeModCard(
                    mod = mod,
                    controlsEnabled = controlsEnabled,
                    showDragHandle = showDragHandle,
                    canMoveToTop = index > 0,
                    elevated = elevated,
                    thumbnailRevision = state.thumbnailRevision,
                    onToggle = { actions.enable(mod, it) },
                    onMoveToTop = {
                        actions.move(mod, 0)
                        listState.requestScrollToItem(0)
                    },
                    onDetails = { showDetails(mod) },
                    onRemove = { requestRemoval(mod) },
                    modifier = Modifier
                        .animateItem(
                            fadeInSpec = null,
                            fadeOutSpec = null,
                            placementSpec = if (elevated) null else tween(180),
                        )
                        .zIndex(if (elevated) 1f else 0f)
                        .graphicsLayer {
                            if (elevated) {
                                val offset = listState.layoutInfo.visibleItemsInfo.firstOrNull { it.key == key }?.offset
                                translationY = when {
                                    offset == null -> 0f
                                    moving -> reorder.cardTop - offset
                                    settling != null -> (settling.top - offset) * settling.remaining.value
                                    else -> 0f
                                }
                            } else {
                                translationY = 0f
                            }
                        }
                        .then(accessibleReorder),
                )
            }
        }
        PullToRefreshDefaults.Indicator(
            state = refreshState,
            isRefreshing = state.refreshing,
            modifier = Modifier.align(Alignment.TopCenter),
        )
    }
}

internal class ModReorderState {
    class Drop(val key: String, val top: Float) {
        val remaining = Animatable(1f)
    }

    var dragging by mutableStateOf<NativeModStore.InstalledMod?>(null)
        private set
    var from by mutableIntStateOf(0)
        private set
    var to by mutableIntStateOf(0)
        private set
    var drop by mutableStateOf<Drop?>(null)
        private set
    private var fingerY by mutableFloatStateOf(0f)
    private var grabY by mutableFloatStateOf(0f)
    val cardTop: Float get() = fingerY - grabY

    fun displayOrder(installed: List<NativeModStore.InstalledMod>): List<NativeModStore.InstalledMod> {
        if (dragging == null) return installed
        return installed.toMutableList().apply { add(to, removeAt(from)) }
    }

    fun start(
        pointerY: Float,
        layout: LazyListLayoutInfo,
        installed: List<NativeModStore.InstalledMod>,
        enabledCount: Int,
    ) {
        val y = pointerY + layout.viewportStartOffset
        val item = layout.visibleItemsInfo.firstOrNull { y >= it.offset && y < it.offset + it.size } ?: return
        val index = installed.indexOfFirst { it.directory.toString() == item.key }
        if (index !in 0 until enabledCount) return
        from = index
        to = index
        grabY = y - item.offset
        fingerY = y
        drop = null
        dragging = installed[index]
    }

    fun dragBy(deltaY: Float) {
        fingerY += deltaY
    }

    fun finish(move: ((NativeModStore.InstalledMod, Int) -> Unit)? = null) {
        val mod = dragging ?: return
        drop = Drop(mod.directory.toString(), cardTop)
        if (from != to) move?.invoke(mod, to)
        dragging = null
    }

    fun finishAnimation(completed: Drop) {
        if (drop === completed) drop = null
    }

    fun scrollDelta(layout: LazyListLayoutInfo, edge: Float): Float {
        val delta = when {
            fingerY < layout.viewportStartOffset + edge -> fingerY - layout.viewportStartOffset - edge
            fingerY > layout.viewportEndOffset - edge -> fingerY - layout.viewportEndOffset + edge
            else -> 0f
        }
        return (delta * 0.2f).coerceIn(-edge, edge)
    }

    fun updateDropTarget(
        layout: LazyListLayoutInfo,
        order: List<NativeModStore.InstalledMod>,
        enabledCount: Int,
    ) {
        val draggedKey = dragging?.directory?.toString()
        val visible = layout.visibleItemsInfo.filter { item ->
            order.take(enabledCount).any { it.directory.toString() == item.key && item.key != draggedKey }
        }
        val nearest = visible.minByOrNull { abs(fingerY - (it.offset + it.size / 2f)) } ?: return
        val current = layout.visibleItemsInfo.firstOrNull { it.key == draggedKey }
        val above = current == null || nearest.offset < current.offset
        val midpoint = nearest.offset + nearest.size / 2f
        if (if (above) fingerY <= midpoint else fingerY >= midpoint) {
            to = order.indexOfFirst { it.directory.toString() == nearest.key }
        }
    }
}
