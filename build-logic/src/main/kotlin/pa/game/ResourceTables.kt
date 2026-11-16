package pa.game

import java.io.ByteArrayOutputStream

internal object ResourceTables {
    fun resourcePath(path: String) = if (path.startsWith("res/")) "res/patools/" + path.removePrefix("res/") else path
    private data class Table(val offsets: List<Int>, val strings: ByteArray, val resourcePackage: ByteArray)
    private fun parse(bytes: ByteArray, packageId: Int): Table {
        val binary = Binary(bytes)
        require(binary.u16(0) == 2 && binary.u16(2) == 12 && binary.i32(4) == bytes.size && binary.i32(8) == 1)
        val chunks = binary.chunks(12)
        require(chunks.size == 2 && chunks[0].type == 1 && chunks[1].type == 0x200)
        val pool = Binary(chunks[0].bytes)
        val pkg = Binary(chunks[1].bytes)
        require(pool.u16(2) == 28 && pkg.i32(8) == packageId)
        require(pool.i32(12) == 0 && pool.i32(16) == 0x100 && pool.i32(24) == 0)
        return Table((0 until pool.i32(8)).map { pool.i32(28 + it * 4) },
            pool.slice(pool.i32(20), pool.bytes.size - pool.i32(20)), pkg.bytes)
    }
    fun replaceXmlReference(bytes: ByteArray, oldId: Long, newId: Long): ByteArray {
        val binary = Binary(bytes.copyOf())
        val matches = mutableListOf<Int>()
        for (chunk in binary.chunks(8)) {
            if (chunk.type != 0x102) continue
            val node = Binary(chunk.bytes)
            val start = node.u16(chunk.header + 8)
            val stride = node.u16(chunk.header + 10)
            repeat(node.u16(chunk.header + 12)) { index ->
                val attribute = chunk.header + start + index * stride
                if (node.u8(attribute + 15) == 1 && node.u32(attribute + 16) == oldId) matches += chunk.offset + attribute + 16
            }
        }
        require(matches.size == 1) { "Expected one launcher reference" }
        binary.put32(matches.single(), newId)
        return binary.bytes
    }
    private fun rename(table: Table): Table {
        val output = ByteArrayOutputStream()
        val offsets = mutableListOf<Int>()
        val strings = Binary(table.strings)
        fun length(at: Int): Pair<Int, Int> =
            if (strings.u8(at) and 128 != 0) (((strings.u8(at) and 127) shl 8) or strings.u8(at + 1)) to at + 2
            else strings.u8(at) to at + 1
        fun writeLength(value: Int) {
            require(value < 0x8000)
            if (value >= 128) output.write(0x80 or (value shr 8))
            output.write(value and 255)
        }
        for (offset in table.offsets) {
            val (_, second) = length(offset)
            val (size, start) = length(second)
            val value = strings.slice(start, size).toString(Charsets.UTF_8)
            require(strings.u8(start + size) == 0)
            offsets += output.size()
            if (value.startsWith("res/")) {
                val replacement = resourcePath(value)
                val encoded = replacement.toByteArray(Charsets.UTF_8)
                writeLength(replacement.length)
                writeLength(encoded.size)
                output.write(encoded)
                output.write(0)
            } else output.write(strings.slice(offset, start + size + 1 - offset))
        }
        while (output.size() % 4 != 0) output.write(0)
        return table.copy(offsets = offsets, strings = output.toByteArray())
    }
    private fun shiftStrings(bytes: ByteArray, offset: Int): ByteArray {
        val pkg = Binary(bytes.copyOf())
        fun shift(at: Int) {
            require(pkg.u16(at) == 8)
            if (pkg.u8(at + 3) == 3) pkg.put32(at + 4, pkg.u32(at + 4) + offset)
        }
        for (chunk in pkg.chunks(pkg.u16(2))) {
            if (chunk.type != 0x201) continue
            val table = Binary(chunk.bytes)
            val count = table.i32(12)
            val start = table.i32(16)
            val flags = table.u8(9)
            val offsets = when {
                flags and 1 != 0 -> (0 until count).map { table.u16(chunk.header + it * 4 + 2) * 4 }
                flags and 2 != 0 -> (0 until count).map { table.u16(chunk.header + it * 2) }.filter { it != 0xffff }.map { it * 4 }
                else -> (0 until count).map { table.i32(chunk.header + it * 4) }.filter { it != -1 }
            }
            for (entry in offsets) {
                val at = chunk.offset + start + entry
                val entryFlags = pkg.u16(at + 2)
                require(entryFlags and 8 == 0) { "Compact resource entries are unsupported" }
                val size = pkg.u16(at)
                if (entryFlags and 1 != 0) repeat(pkg.i32(at + 12)) { shift(at + size + it * 12 + 4) }
                else shift(at + size)
            }
        }
        return pkg.bytes
    }
    fun merge(stock: ByteArray, compose: ByteArray): ByteArray {
        val game = parse(stock, 0x7f)
        val manager = rename(parse(compose, 0x80))
        val offsets = game.offsets + manager.offsets.map { game.strings.size + it }
        val poolStart = 28 + 4 * offsets.size
        val pool = concatenate(words(0x001c0001, (poolStart + game.strings.size + manager.strings.size).toLong(),
            offsets.size.toLong(), 0, 0x100, poolStart.toLong(), 0),
            words(*offsets.map { it.toLong() }.toLongArray()), game.strings, manager.strings)
        val body = concatenate(pool, game.resourcePackage, shiftStrings(manager.resourcePackage, game.offsets.size))
        return concatenate(words(0x000c0002, (12 + body.size).toLong(), 2), body)
    }
}
