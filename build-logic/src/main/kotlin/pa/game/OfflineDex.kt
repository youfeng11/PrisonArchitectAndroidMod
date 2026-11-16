package pa.game

import java.io.File

internal fun replaceSmaliMethods(source: String, changes: Map<String, String>): String {
    var text = source.replace("\r\n", "\n").replace("\r", "\n")
    for ((signature, body) in changes) {
        val pattern = Regex("(^\\.method [^\n]* " + Regex.escape(signature) + "\n).*?^\\.end method$", setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL))
        require(pattern.findAll(text).count() == 1) { "Missing or ambiguous method $signature" }
        text = pattern.replace(text) { it.groupValues[1] + body + "\n.end method" }
    }
    return text
}

internal class OfflineDex(private val tools: Toolchain, private val profile: V49Profile, private val smaliClasspath: String) {
    private val game = "com/paradoxplaza/prisonarchitect"
    private val helper = "L$game/patools/EmbeddedObb;"
    private fun methods(file: File, changes: Map<String, String>) {
        file.writeText(replaceSmaliMethods(file.readText(), changes))
    }
    fun patch(original: ByteArray, staging: File): ByteArray {
        require(sha256(original) == profile.dexHash) { "Expected the original v49 DEX" }
        val source = staging.resolve("stock.dex").apply { writeBytes(original) }
        val smali = staging.resolve("stock-smali")
        val cli = listOf(tools.java("java").path, "-cp", smaliClasspath)
        tools.run(cli + listOf("com.android.tools.smali.baksmali.Main", "disassemble", "--jobs", "4", "-o", smali.path, source.path))
        methods(smali.resolve("mz.smali"), mapOf("a(L$game/core/MainActivity;)Z" to
            "    .locals 1\n    invoke-static {p0}, ${helper}->prepareForStartup(Landroid/app/Activity;)Z\n    move-result v0\n    return v0"))
        methods(smali.resolve("$game/core/MainActivity.smali"), mapOf("getApkExpansionPath()Ljava/lang/String;" to
            "    .locals 1\n    invoke-static {}, ${helper}->getPath()Ljava/lang/String;\n    move-result-object v0\n    return-object v0"))
        val noop = "    .locals 0\n    return-void"
        methods(smali.resolve("$game/core/GooglePlayRemoteNotificationNativeInterface.smali"), mapOf("RequestRemoteToken()V" to noop))
        methods(smali.resolve("$game/tracking/AdjustNativeInterface.smali"), listOf("onInit()V", "trackEvent(Ljava/lang/String;)V",
            "trackRevenueEvent(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V").associateWith { noop })
        val device = smali.resolve("$game/core/DeviceNativeInterface.smali")
        val method = Regex("^\\.method public getUniqueId\\(\\)Ljava/lang/String;\n(.*?)^\\.end method$",
            setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL)).find(device.readText().replace("\r\n", "\n")) ?: error("Missing device ID method")
        val fallback = method.groupValues[1].substringAfter("    :cond_2f\n", "").substringBefore("    :pswitch_data_ae\n").trimEnd()
        require(fallback.isNotEmpty())
        methods(device, mapOf("getUniqueId()Ljava/lang/String;" to
            "    .registers 4\n\n$fallback\n\n    :cond_1d\n    :goto_1d\n    return-object v0"))
        val iap = "L$game/networking/GooglePlayIAPNativeInterface;"
        val changes = listOf("Init()V", "CloseTransaction(Ljava/lang/String;Ljava/lang/String;)V", "CancelProductDescriptionsRequest()V",
            "RequestProductPurchase(Ljava/lang/String;I)V", "RestoreManagedPurchases()V",
            "RestorePendingManagedTransactions([Ljava/lang/String;)V", "RestorePendingUnmanagedTransactions()V",
            "onActivityResult(IILandroid/content/Intent;)V", "onDestroy()V").associateWith { noop }.toMutableMap()
        changes["RequestProductDescriptions([Ljava/lang/String;)V"] =
            "    .locals 7\n    move-object v0, p0\n    const/4 v1, 0x0\n    new-array v1, v1, [Ljava/lang/String;\n" +
            (2..6).joinToString("") { "    move-object v$it, v1\n" } +
            "    invoke-virtual/range {v0 .. v6}, ${iap}->NativeOnProductsDescriptionsRequestComplete(" +
            "[Ljava/lang/String;".repeat(6) + ")V\n    return-void"
        methods(smali.resolve("$game/networking/GooglePlayIAPNativeInterface.smali"), changes)
        val output = staging.resolve("offline.dex")
        tools.run(cli + listOf("com.android.tools.smali.smali.Main", "assemble", "--jobs", "4", "-o", output.path, smali.path))
        return output.readBytes()
    }
}
