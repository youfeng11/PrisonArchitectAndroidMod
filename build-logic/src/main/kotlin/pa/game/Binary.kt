package pa.game

import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

internal class Binary(val bytes: ByteArray) {
    fun bounds(at: Int, length: Int) {
        require(at >= 0 && length >= 0 && at <= bytes.size - length) { "Truncated binary at 0x${at.toString(16)} ($length bytes)" }
    }
    fun u8(at: Int): Int { bounds(at, 1); return bytes[at].toInt() and 255 }
    fun u16(at: Int): Int { bounds(at, 2); return u8(at) or (u8(at + 1) shl 8) }
    fun i32(at: Int): Int { bounds(at, 4); return ByteBuffer.wrap(bytes, at, 4).order(ByteOrder.LITTLE_ENDIAN).int }
    fun u32(at: Int): Long = i32(at).toLong() and 0xffffffffL
    fun put16(at: Int, value: Int) { bounds(at, 2); ByteBuffer.wrap(bytes, at, 2).order(ByteOrder.LITTLE_ENDIAN).putShort(value.toShort()) }
    fun put32(at: Int, value: Long) { bounds(at, 4); ByteBuffer.wrap(bytes, at, 4).order(ByteOrder.LITTLE_ENDIAN).putInt(value.toInt()) }
    fun slice(at: Int, size: Int): ByteArray { bounds(at, size); return bytes.copyOfRange(at, at + size) }
    fun chunks(start: Int): List<Chunk> {
        val chunks = mutableListOf<Chunk>()
        var at = start
        while (at < bytes.size) {
            bounds(at, 8)
            val size = i32(at + 4)
            val header = u16(at + 2)
            require(header >= 8 && size >= header) { "Invalid chunk at $at" }
            bounds(at, size)
            chunks += Chunk(u16(at), header, at, slice(at, size))
            at += size
        }
        return chunks
    }
}
internal data class Chunk(val type: Int, val header: Int, val offset: Int, val bytes: ByteArray)
internal fun words(vararg values: Long): ByteArray =
    ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN).apply { values.forEach { putInt(it.toInt()) } }.array()
internal fun concatenate(vararg values: ByteArray): ByteArray =
    ByteArrayOutputStream().apply { values.forEach { write(it) } }.toByteArray()
internal fun branch(at: Long, target: Long, link: Boolean = false): Long {
    val delta = target - at - 8
    require(delta % 4 == 0L && delta >= -(1L shl 25) && delta < (1L shl 25)) { "ARM branch out of range at ${at.toString(16)}" }
    return (if (link) 0xeb000000L else 0xea000000L) or ((delta / 4) and 0xffffffL)
}
internal fun number(value: Any?): Long = when (value) {
    is Number -> value.toLong()
    is String -> if (value.startsWith("0x")) value.substring(2).toLong(16) else value.toLong()
    else -> error("Expected integer, found $value")
}
