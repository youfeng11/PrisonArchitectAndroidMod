package pa.game

import groovy.json.JsonSlurper
import java.io.File
import java.security.MessageDigest

internal data class InstructionPatch(
    val address: Int,
    val expected: Long,
    val value: Long?,
    val target: String?,
    val link: Boolean,
    val condition: Long,
) {
    fun resolve(symbols: Map<String, Long>): Long {
        if (value != null) return value
        val destination = target ?: error("Missing branch target")
        val addressValue = symbols[destination] ?: number(destination)
        return (branch(address.toLong(), addressValue, link) and 0x0fffffffL) or (condition shl 28)
    }
}
internal class V49Profile(file: File) {
    @Suppress("UNCHECKED_CAST")
    private val data = JsonSlurper().parse(file) as Map<String, Any?>
    @Suppress("UNCHECKED_CAST")
    val constants = data.getValue("constants") as Map<String, Any?>
    @Suppress("UNCHECKED_CAST")
    val linkSymbols = data.getValue("linkSymbols") as Map<String, String>
    val patches = readPatches("patches")
    val offlinePatches = readPatches("offlinePatches")
    val dexHash = data.getValue("stockDexSha256").toString()
    fun address(name: String) = number(constants.getValue(name)).toInt()
    fun text(name: String) = constants.getValue(name).toString()
    @Suppress("UNCHECKED_CAST")
    private fun readPatches(key: String): List<InstructionPatch> =
        (data.getValue(key) as List<Map<String, Any?>>).map {
            InstructionPatch(number(it.getValue("address")).toInt(), number(it.getValue("expected")),
                it["value"]?.let(::number), it["target"] as String?, it["link"] == true,
                it["condition"]?.let(::number) ?: 14L)
        }
}
internal fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
