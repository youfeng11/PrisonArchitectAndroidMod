package com.paradoxplaza.prisonarchitect.patools

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import java.io.IOException
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.Path
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
internal fun ModThumbnail(directory: Path, revision: Int) {
    val size = 48.dp
    val image = if (LocalInspectionMode.current) {
        null
    } else {
        val pixels = with(LocalDensity.current) { size.roundToPx() }
        val thumbnail by produceState<Bitmap?>(null, directory, revision, pixels) {
            value = withContext(Dispatchers.IO) { readThumbnail(directory, pixels) }
        }
        thumbnail
    }
    Surface(
        modifier = Modifier.size(size),
        shape = MaterialTheme.shapes.small,
        color = MaterialTheme.colorScheme.secondaryContainer,
    ) {
        Box(contentAlignment = Alignment.Center) {
            if (image != null) {
                Image(
                    bitmap = image.asImageBitmap(),
                    contentDescription = null,
                    modifier = Modifier.matchParentSize(),
                    contentScale = ContentScale.Fit,
                )
            } else {
                Icon(
                    painter = painterResource(R.drawable.ms_extension_24),
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
        }
    }
}

private fun readThumbnail(directory: Path, pixels: Int): Bitmap? {
    try {
        val exact = directory.resolve(NativeModStore.THUMBNAIL)
        val file = if (Files.isRegularFile(exact, NOFOLLOW_LINKS)) {
            exact
        } else {
            Files.list(directory).use { files ->
                files.filter {
                    it.fileName.toString().equals(NativeModStore.THUMBNAIL, ignoreCase = true) &&
                        Files.isRegularFile(it, NOFOLLOW_LINKS)
                }.sorted().findFirst().orElse(null)
            }
        } ?: return null

        val path = file.toString()
        val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(path, options)
        if (options.outMimeType != "image/png" || options.outWidth <= 0 || options.outHeight <= 0) return null
        val longestEdge = maxOf(options.outWidth, options.outHeight)
        var sample = 1
        while (longestEdge / sample / 2 >= pixels) sample *= 2
        return BitmapFactory.decodeFile(path, BitmapFactory.Options().apply { inSampleSize = sample })
    } catch (_: IOException) {
        return null
    } catch (_: SecurityException) {
        return null
    }
}
