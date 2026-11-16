package pa.game

import java.io.ByteArrayOutputStream

internal const val GAME_PACKAGE = "com.paradoxplaza.prisonarchitect"
internal const val OBB_ASSET = "assets/patools/main.49.com.paradoxplaza.prisonarchitect.obb"
internal val GOOGLE_PERMISSIONS = setOf("com.android.vending.CHECK_LICENSE", "com.android.vending.BILLING",
    "com.google.android.c2dm.permission.RECEIVE", "$GAME_PACKAGE.permission.C2D_MESSAGE")
internal val GOOGLE_COMPONENTS = setOf("com.google.android.gms.version", "com.google.android.gms.common.api.GoogleApiActivity",
    "com.adjust.sdk.AdjustReferrerReceiver", "$GAME_PACKAGE.core.GCMBroadcastReceiver", "$GAME_PACKAGE.core.GCMService",
    "$GAME_PACKAGE.expansion.ApkExpansionDownloadActivity", "$GAME_PACKAGE.expansion.ApkExpansionDownloadService",
    "$GAME_PACKAGE.expansion.ApkExpansionAlarmReceiver")

internal data class ActivityResources(val theme: Long, val label: Long, val icon: Long)
private data class Attribute(val key: String, val resource: Long, val type: Int, val value: Long = 0, val text: String? = null)

internal class ManifestPatcher(bytes: ByteArray) {
    private val binary = Binary(bytes)
    private val chunks = binary.chunks(8)
    private val pool = Binary(chunks[0].bytes)
    private val names = mutableListOf<String>()
    private val offsets = mutableListOf<Int>()
    private val strings = ByteArrayOutputStream()
    private val ids = mutableListOf<Long>()
    init {
        require(binary.u16(0) == 3 && binary.u16(2) == 8 && binary.i32(4) == bytes.size)
        require(chunks[0].type == 1 && chunks[1].type == 0x180)
        val count = pool.i32(8)
        require(pool.i32(12) == 0 && pool.i32(16) == 0 && pool.i32(24) == 0 && pool.i32(20) == 28 + 4 * count)
        repeat(count) {
            val offset = pool.i32(28 + it * 4)
            offsets += offset
            val at = pool.i32(20) + offset
            val size = pool.u16(at)
            require(size < 0x8000)
            names += pool.slice(at + 2, size * 2).toString(Charsets.UTF_16LE)
        }
        strings.write(pool.slice(pool.i32(20), pool.bytes.size - pool.i32(20)))
        val map = Binary(chunks[1].bytes)
        for (at in 8 until map.bytes.size step 4) ids += map.u32(at)
    }
    private fun index(value: String, resource: Long = 0): Int {
        val existing = names.indices.firstOrNull { names[it] == value && ids.getOrElse(it) { 0 } == resource }
        if (existing != null) return existing
        val at = names.size
        if (resource != 0L) {
            while (ids.size < at) ids += 0
            ids += resource
        }
        names += value
        offsets += strings.size()
        val encoded = value.toByteArray(Charsets.UTF_16LE)
        require(value.length < 0x8000)
        strings.write(byteArrayOf((value.length and 255).toByte(), (value.length shr 8).toByte()))
        strings.write(encoded)
        strings.write(byteArrayOf(0, 0))
        return at
    }
    private fun text(key: String, resource: Long, value: String) = Attribute(key, resource, 3, text = value)
    private fun element(tag: String, attributes: List<Attribute> = emptyList(), children: ByteArray = byteArrayOf()): ByteArray {
        val ns = index("http://schemas.android.com/apk/res/android")
        val name = index(tag)
        val encoded = ByteArrayOutputStream()
        for (attribute in attributes.sortedBy { it.resource }) {
            val key = index(attribute.key, attribute.resource)
            val raw = attribute.text?.let { index(it) } ?: -1
            encoded.write(words(ns.toLong(), key.toLong(), raw.toLong(),
                (8L or (attribute.type.toLong() shl 24)), if (attribute.type == 3) raw.toLong() else attribute.value))
        }
        val header = ByteArray(36)
        val start = Binary(header)
        start.put16(0, 0x102); start.put16(2, 16); start.put32(4, (36 + encoded.size()).toLong())
        start.put32(12, -1); start.put32(16, -1); start.put32(20, name.toLong())
        start.put16(24, 20); start.put16(26, 20); start.put16(28, attributes.size)
        return concatenate(header, encoded.toByteArray(), children, words(0x00100103, 24, 0, -1, -1, name.toLong()))
    }
    private fun filter(action: String, categories: List<String>, data: List<Attribute> = emptyList()): ByteArray {
        val body = ByteArrayOutputStream()
        body.write(element("action", listOf(text("name", 0x01010003, action))))
        for (category in categories) body.write(element("category", listOf(text("name", 0x01010003, category))))
        for (entry in data) body.write(element("data", listOf(entry)))
        return element("intent-filter", children = body.toByteArray())
    }
    fun patch(resources: ActivityResources): ByteArray {
        val result = ByteArrayOutputStream()
        var skip = 0
        for (chunk in chunks.drop(2)) {
            if (skip > 0) {
                if (chunk.type == 0x102) skip++
                if (chunk.type == 0x103) skip--
                continue
            }
            val node = Binary(chunk.bytes)
            val tag = if (chunk.type in listOf(0x102, 0x103)) names[node.i32(20)] else null
            if (chunk.type == 0x102 && tag == "manifest") {
                repeat(node.u16(28)) { i ->
                    val at = 16 + node.u16(24) + i * node.u16(26)
                    if (names[node.i32(at + 4)] == "versionName") {
                        require(node.u8(at + 15) == 3) { "Expected a string versionName" }
                        val original = names[node.i32(at + 16)]
                        val version = index(if (original.endsWith("-mod")) original else "$original-mod")
                        node.put32(at + 8, version.toLong())
                        node.put32(at + 16, version.toLong())
                    }
                }
            }
            if (chunk.type == 0x102 && tag in setOf("uses-permission", "permission", "activity", "service", "receiver", "meta-data")) {
                val start = node.u16(24)
                val size = node.u16(26)
                repeat(node.u16(28)) { i ->
                    val at = 16 + start + i * size
                    if (names[node.i32(at + 4)] == "name" && node.i32(at + 8) != -1) {
                        if (names[node.i32(at + 8)] in GOOGLE_PERMISSIONS + GOOGLE_COMPONENTS) skip = 1
                    }
                }
                if (skip > 0) continue
            }
            if (chunk.type == 0x102 && tag == "application") {
                result.write(element("permission", listOf(text("name", 0x01010003, "$GAME_PACKAGE.permission.PATOOLS_OBB"),
                    Attribute("protectionLevel", 0x01010009, 0x11, 2))))
            }
            if (chunk.type == 0x103 && tag == "application") {
                result.write(element("meta-data", listOf(text("name", 0x01010003, "$GAME_PACKAGE.patools.COMPOSITE_RESIZE"),
                    Attribute("value", 0x01010024, 0x12, -1))))
                result.write(element("service", listOf(text("name", 0x01010003, "$GAME_PACKAGE.patools.ObbBridgeService"),
                    text("permission", 0x01010006, "$GAME_PACKAGE.permission.PATOOLS_OBB"),
                    Attribute("exported", 0x01010010, 0x12, -1), text("process", 0x01010011, ":patools_obb"))))
                val mimeTypes = listOf("application/zip", "application/x-zip-compressed", "application/vnd.rar",
                    "application/x-rar", "application/x-rar-compressed", "application/x-7z-compressed", "application/x-tar",
                    "application/x-gtar", "application/x-compressed-tar", "application/gzip", "application/x-gzip",
                    "application/x-bzip2", "application/x-xz", "application/x-mod", "audio/mod", "audio/x-mod", "application/octet-stream")
                val launcher = filter("android.intent.action.MAIN", listOf("android.intent.category.LAUNCHER"))
                val archiveTypes = concatenate(*mimeTypes.map {
                    element("data", listOf(text("mimeType", 0x01010026, it)))
                }.toTypedArray())
                val defaultCategory = element("category", listOf(text("name", 0x01010003, "android.intent.category.DEFAULT")))
                val view = element("intent-filter", children = concatenate(
                    element("action", listOf(text("name", 0x01010003, "android.intent.action.VIEW"))),
                    defaultCategory, element("data", listOf(text("scheme", 0x01010027, "content"))), archiveTypes))
                result.write(element("activity", listOf(Attribute("theme", 0x01010000, 1, resources.theme),
                    Attribute("label", 0x01010001, 1, resources.label), Attribute("icon", 0x01010002, 1, resources.icon),
                    text("name", 0x01010003, "$GAME_PACKAGE.patools.NativeModsActivity"),
                    Attribute("exported", 0x01010010, 0x12, -1), text("process", 0x01010011, ":patools_mods"),
                    text("taskAffinity", 0x01010012, "$GAME_PACKAGE.patools.mods"), Attribute("launchMode", 0x0101001d, 0x10, 2)),
                    concatenate(launcher, view)))
            }
            result.write(chunk.bytes)
        }
        while (strings.size() % 4 != 0) strings.write(0)
        val poolStart = 28 + offsets.size * 4
        val poolBytes = concatenate(words(0x001c0001, (poolStart + strings.size()).toLong(), offsets.size.toLong(),
            0, 0, poolStart.toLong(), 0), words(*offsets.map { it.toLong() }.toLongArray()), strings.toByteArray())
        val mapping = concatenate(words(0x00080180, (8 + ids.size * 4).toLong()), words(*ids.toLongArray()))
        val body = concatenate(poolBytes, mapping, result.toByteArray())
        return concatenate(words(0x00080003, (8 + body.size).toLong()), body)
    }
}
