package pa.game

import org.junit.Assert.*
import org.junit.Test

class BinaryTest {
    @Test fun smaliReplacementAcceptsWindowsLineEndings() {
        val source = ".method public a()V\r\n    .locals 0\r\n    return-void\r\n.end method\r\n"
        val result = replaceSmaliMethods(source, mapOf("a()V" to "    .locals 1\n    return-void"))
        assertTrue(result.contains("    .locals 1\n"))
        assertFalse(result.contains("\r"))
        assertThrows(IllegalArgumentException::class.java) { replaceSmaliMethods(source + source, mapOf("a()V" to "")) }
    }
    @Test fun littleEndianAndUnsignedWords() {
        val data = Binary(ByteArray(12))
        data.put32(0, 0xffffffffL)
        data.put16(4, 0x1234)
        assertEquals(0xffffffffL, data.u32(0))
        assertEquals(0x1234, data.u16(4))
        assertEquals(0x34, data.u8(4))
    }
    @Test fun branchesAreSignedAndRangeChecked() {
        assertEquals(0xeb000002L, branch(0x1000, 0x1010, true))
        assertEquals(0xeafffffcL, branch(0x1000, 0xff8))
        assertThrows(IllegalArgumentException::class.java) { branch(0, 3) }
        assertThrows(IllegalArgumentException::class.java) { branch(0, 1L shl 30) }
    }
    @Test fun truncatedAndInvalidChunksFailBeforeAllocation() {
        assertThrows(IllegalArgumentException::class.java) { Binary(ByteArray(3)).u32(0) }
        assertThrows(IllegalArgumentException::class.java) { Binary(words(0x00080001, 0)).chunks(0) }
        assertThrows(IllegalArgumentException::class.java) { Binary(words(0x00080001, 100)).chunks(0) }
        assertThrows(IllegalArgumentException::class.java) { Binary(ByteArray(8)).slice(-1, 4) }
    }
    @Test fun resourceRelocationIsScoped() {
        assertEquals("res/patools/drawable/icon.xml", ResourceTables.resourcePath("res/drawable/icon.xml"))
        assertEquals("assets/readme.txt", ResourceTables.resourcePath("assets/readme.txt"))
    }

    @Test fun resourceMergeRelocatesStringsAndValueIndices() {
        fun table(id: Long, text: String): ByteArray {
            val encoded = text.toByteArray()
            val raw = concatenate(byteArrayOf(text.length.toByte(), encoded.size.toByte()), encoded, byteArrayOf(0))
            val padded = raw + ByteArray((4 - raw.size % 4) % 4)
            val pool = concatenate(words(0x001c0001, (32 + padded.size).toLong(), 1, 0, 0x100, 32, 0, 0), padded)
            val type = words(0x00140201, 40, 0, 1, 24, 0, 8, 0, 0x03000008, 0)
            val pkg = concatenate(words(0x000c0200, 52, id), type)
            return concatenate(words(0x000c0002, (12 + pool.size + pkg.size).toLong(), 1), pool, pkg)
        }
        val merged = Binary(ResourceTables.merge(table(0x7f, "stock"), table(0x80, "res/icon.xml")))
        assertEquals(2, merged.i32(8))
        val chunks = merged.chunks(12)
        val pool = Binary(chunks[0].bytes)
        assertEquals(2, pool.i32(8))
        val second = pool.i32(20) + pool.i32(32)
        assertEquals("res/patools/icon.xml", pool.slice(second + 2, pool.u8(second + 1)).toString(Charsets.UTF_8))
        assertEquals(1, Binary(chunks[2].bytes).i32(12 + 36))
    }
}
