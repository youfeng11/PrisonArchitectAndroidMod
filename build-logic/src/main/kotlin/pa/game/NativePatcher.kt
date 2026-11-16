package pa.game

import java.io.File

internal class NativePatcher(private val tools: Toolchain, private val profile: V49Profile) {
    fun build(original: ByteArray, staging: File): ByteArray {
        require(sha256(original) == profile.text("ORIGINAL_SHA256")) { "Expected the original v49 ARM library" }
        val source = tools.root.resolve("game/register_object_sprites.S")
        val obj = staging.resolve("register.o")
        val replacement = staging.resolve("replacements.o")
        val elf = staging.resolve("register.elf")
        val code = staging.resolve("register.bin")
        val bank = staging.resolve("bank.bin")
        tools.run(tools.native("clang"), "--target=armv7a-linux-androideabi", "-DNATIVE_MOD_SCAN",
            "-DNATIVE_MOD_ATLAS", "-DNATIVE_SPRITE_REPLACEMENTS", "-c", source, "-o", obj)
        tools.run(tools.native("clang"), "--target=armv7a-linux-androideabi21", "-marm", "-Oz", "-fPIC",
            "-ffreestanding", "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
            "-Wall", "-Wextra", "-Werror", "-c", source.resolveSibling("native_sprite_replacements.c"), "-o", replacement)
        val layout = staging.resolve("patch.ld")
        layout.writeText("SECTIONS { .text 0x${profile.address("CAVE").toString(16)} : { *register.o(.text) } " +
            ".bank_code 0x${profile.address("BANK_CODE").toString(16)} : { *replacements.o(.text .text.* .rodata .rodata.*) } }\n")
        tools.run(listOf(tools.native("ld.lld").path, "-T", layout.path, "--entry=register_object_sprites") +
            profile.linkSymbols.map { (name, value) -> "--defsym=$name=$value" } +
            listOf(obj.path, replacement.path, "-o", elf.path))
        val symbols = tools.run(tools.native("llvm-nm"), "--defined-only", elf).lineSequence()
            .filter { it.isNotBlank() }.associate { line ->
                val fields = line.trim().split(Regex("\\s+"))
                require(fields.size == 3) { "Invalid symbol line $line" }
                fields[2] to fields[0].toLong(16)
            }
        tools.run(tools.native("llvm-objcopy"), "-O", "binary", "--only-section=.text", elf, code)
        tools.run(tools.native("llvm-objcopy"), "-O", "binary", "--only-section=.bank_code", elf, bank)
        return patch(original, code.readBytes(), bank.readBytes(), symbols)
    }

    private fun patch(original: ByteArray, payload: ByteArray, bank: ByteArray, symbols: Map<String, Long>): ByteArray {
        val image = Binary(original.copyOf())
        val cave = profile.address("CAVE")
        require(payload.size <= profile.address("CAVE_LIMIT") - cave)
        require(image.slice(cave, profile.address("CAVE_LIMIT") - cave).all { it == 0.toByte() })
        payload.copyInto(image.bytes, cave)
        for (patch in profile.patches + profile.offlinePatches) {
            require(image.u32(patch.address) == patch.expected) { "Unexpected v49 instruction at 0x${patch.address.toString(16)}" }
            image.put32(patch.address, patch.resolve(symbols))
        }
        require(image.u8(4) == 1 && image.u8(5) == 1) { "Expected a little-endian ELF32 image" }
        val phoff = image.i32(28)
        val phentsize = image.u16(42)
        val headers = (0 until image.u16(44)).map { phoff + it * phentsize }
        headers.forEach { image.bounds(it, 32) }
        val executable = headers.single { image.i32(it) == 1 && image.i32(it + 4) == 0 && image.i32(it + 8) == 0 && image.i32(it + 12) == 0 }
        require(image.u32(executable + 16) == 0xeabf07L && image.u32(executable + 20) == 0xeabf07L)
        image.put32(executable + 16, (cave + payload.size).toLong())
        image.put32(executable + 20, (cave + payload.size).toLong())
        val writable = headers.single { image.i32(it) == 1 && image.u32(it + 4) == 0xeacab0L }
        val address = image.i32(writable + 8)
        val size = image.i32(writable + 20)
        require(image.i32(writable + 24) == 6 && address + size == profile.address("BANK_BASELINE"))
        val stateSize = profile.address("BANK_BASELINE_SIZE") + profile.address("NATIVE_ATLAS_STATE_SIZE") + 16 +
            profile.address("DEFAULT_STAFF_STATE_SIZE")
        image.put32(writable + 20, (size + stateSize).toLong())
        val bankAddress = profile.address("BANK_CODE")
        val alignment = profile.address("SEGMENT_ALIGNMENT")
        require(address + size + stateSize <= bankAddress && bankAddress % alignment == 0)
        require(phentsize == 32 && headers.take(4).map { image.i32(it) } == listOf(6, 3, 1, 1))
        val offset = (image.bytes.size + alignment - 1) and -alignment
        image.slice(headers[2], 2 * phentsize).copyInto(image.bytes, headers[1])
        words(1, offset.toLong(), bankAddress.toLong(), bankAddress.toLong(), bank.size.toLong(),
            bank.size.toLong(), 5, alignment.toLong()).copyInto(image.bytes, headers[3])
        return concatenate(image.bytes, ByteArray(offset - image.bytes.size), bank)
    }
}
