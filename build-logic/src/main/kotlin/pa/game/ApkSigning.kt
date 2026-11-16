package pa.game

import java.io.File
import java.util.Properties

internal data class ApkSigning(
    val keystore: File,
    val alias: String,
    val storePassword: String,
    val keyPassword: String,
) {
    companion object {
        fun load(keystore: File, config: File): ApkSigning {
            val properties = Properties()
            config.inputStream().use { properties.load(it) }
            fun required(name: String): String = properties.getProperty(name)
                ?.takeIf { it.isNotEmpty() } ?: error("Missing $name in $config")
            return ApkSigning(keystore, required("keyAlias"), required("storePassword"), required("keyPassword"))
        }
    }
}
