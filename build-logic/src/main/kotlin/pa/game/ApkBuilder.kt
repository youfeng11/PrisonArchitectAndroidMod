package pa.game

import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.zip.CRC32
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

internal class ApkBuilder(private val tools: Toolchain, private val profile: V49Profile) {
    private fun bytes(archive: ZipFile, name: String): ByteArray =
        archive.getInputStream(archive.getEntry(name) ?: error("Missing APK entry $name")).use { it.readBytes() }
    private fun resourceId(text: String, attribute: String, prefix: String): Long =
        Regex("android:$attribute\\(0x[0-9a-f]+\\)=@(0x$prefix[0-9a-f]{6})")
            .find(text)?.groupValues?.get(1)?.let(::number) ?: error("Missing $attribute resource")
    private fun write(zip: ZipOutputStream, original: ZipEntry, name: String, contents: ByteArray) {
        require(!name.startsWith("/") && name.split('/').none { it == ".." })
        val entry = ZipEntry(name)
        entry.time = original.time
        entry.method = original.method
        if (entry.method == ZipEntry.STORED) {
            entry.size = contents.size.toLong()
            entry.crc = CRC32().apply { update(contents) }.value
        }
        zip.putNextEntry(entry)
        zip.write(contents)
        zip.closeEntry()
    }
    fun build(source: File, compose: File, obb: File, signing: ApkSigning, smaliClasspath: String, output: File, staging: File) {
        require(source.canonicalFile != output.canonicalFile)
        ZipFile(obb).use { archive ->
            for (name in listOf("data/tablet/composite.csimage", "data/materials.txt", "data/tablet/jsondata/purchases.json"))
                require(archive.getEntry(name) != null) { "Missing OBB entry $name" }
        }
        val generated = staging.resolve("generated").apply { mkdirs() }
        val classes = staging.resolve("classes").apply { mkdirs() }
        val dex = staging.resolve("dex").apply { mkdirs() }
        val aidlRoot = tools.root.resolve("game/obb-bridge/aidl")
        val aidl = aidlRoot.resolve("com/youfeng/pa/tools/platform/gameobb/IObbInstaller.aidl")
        tools.run(tools.android("aidl"), "--lang=java", "--min_sdk_version=28", "-I${aidlRoot.absolutePath}",
            "-p${tools.platform.resolve("framework.aidl")}", "-o${generated.absolutePath}", aidl)
        val javaSources = listOf(tools.root.resolve("game/obb-bridge/ObbBridgeService.java"),
            tools.root.resolve("game/obb-bridge/EmbeddedObb.java")) + generated.walkTopDown().filter { it.extension == "java" }.toList()
        tools.run(listOf(tools.java("javac").path, "--release", "8", "-encoding", "UTF-8", "-Xlint:-options",
            "-cp", tools.platform.resolve("android.jar").path, "-d", classes.path) + javaSources.map { it.path })
        tools.run(listOf(tools.android("d8", true).path, "--min-api", "28", "--lib", tools.platform.resolve("android.jar").path,
            "--output", dex.path) + classes.walkTopDown().filter { it.extension == "class" }.map { it.path }.toList())
        val composeManifest = tools.run(tools.android("aapt"), "dump", "xmltree", compose, "AndroidManifest.xml")
        val activity = composeManifest.split("E: activity (").firstOrNull { it.contains("$GAME_PACKAGE.patools.NativeModsActivity") }
            ?: error("Missing mod manager activity")
        val resources = ActivityResources(resourceId(activity, "theme", "80"), resourceId(activity, "label", "80"), resourceId(activity, "icon", "80"))
        val originalManifest = tools.run(tools.android("aapt"), "dump", "xmltree", source, "AndroidManifest.xml")
        val application = originalManifest.substringAfter("E: application (").substringBefore("E:")
        val stockIcon = resourceId(application, "icon", "7f")
        val unsigned = staging.resolve("unsigned.apk")
        ZipFile(source).use { stock ->
            ZipFile(compose).use { manager ->
                val additions = manager.entries().asSequence().filter { entry ->
                    entry.name == "resources.arsc" || entry.name.startsWith("res/") ||
                    entry.name.startsWith("lib/") || Regex("classes[0-9]*\\.dex").matches(entry.name) ||
                    entry.name.startsWith("META-INF/services/") || entry.name.startsWith("kotlin/")
                }.associateByTo(linkedMapOf()) { it.name }
                val native = NativePatcher(tools, profile).build(bytes(stock, profile.text("LIBRARY")), staging)
                val stockNames = stock.entries().asSequence().map { it.name }.toSet()
                var dexIndex = 2
                while ("classes$dexIndex.dex" in stockNames) dexIndex++
                val written = mutableSetOf<String>()
                ZipOutputStream(unsigned.outputStream().buffered()).use { zip ->
                    for (entry in stock.entries().asSequence()) {
                        val name = entry.name
                        if (name.startsWith("META-INF/", true) || name.startsWith("lib/") && !name.startsWith("lib/armeabi-v7a/")) continue
                        var value = bytes(stock, name)
                        when (name) {
                            profile.text("LIBRARY") -> value = native
                            "AndroidManifest.xml" -> value = ManifestPatcher(value).patch(resources)
                            "classes.dex" -> value = OfflineDex(tools, profile, smaliClasspath).patch(value, staging)
                            "resources.arsc" -> {
                                value = ResourceTables.merge(value, bytes(manager, name))
                                additions.remove(name)
                            }
                        }
                        check(written.add(name)) { "Duplicate APK entry $name" }
                        write(zip, entry, name, value)
                    }
                    check(written.add(OBB_ASSET))
                    val obbEntry = ZipEntry(OBB_ASSET)
                    obbEntry.method = ZipEntry.STORED
                    obbEntry.size = obb.length()
                    val crc = CRC32()
                    obb.inputStream().buffered().use { input ->
                        val buffer = ByteArray(65536)
                        var count = input.read(buffer)
                        while (count >= 0) { crc.update(buffer, 0, count); count = input.read(buffer) }
                    }
                    obbEntry.crc = crc.value
                    zip.putNextEntry(obbEntry)
                    obb.inputStream().buffered().use { it.copyTo(zip) }
                    zip.closeEntry()
                    write(zip, ZipEntry("bridge.dex").apply { method = ZipEntry.DEFLATED }, "classes${dexIndex++}.dex",
                        dex.resolve("classes.dex").readBytes())
                    for ((name, entry) in additions) {
                        if (name.startsWith("lib/") && !name.startsWith("lib/armeabi-v7a/")) continue
                        val renamed = if (Regex("classes[0-9]*\\.dex").matches(name)) "classes${dexIndex++}.dex" else ResourceTables.resourcePath(name)
                        check(written.add(renamed)) { "APK entry collision $renamed" }
                        var value = bytes(manager, name)
                        if (name == "res/drawable/ic_mods_launcher.xml") value = ResourceTables.replaceXmlReference(value, 0x0106000d, stockIcon)
                        write(zip, entry, renamed, value)
                    }
                }
            }
        }
        val aligned = staging.resolve("aligned.apk")
        val signed = staging.resolve("signed.apk")
        tools.run(tools.android("zipalign"), "-f", "-p", "4", unsigned, aligned)
        val storePassword = staging.resolve("store-password.txt").apply { writeText(signing.storePassword + "\n") }
        val keyPassword = staging.resolve("key-password.txt").apply { writeText(signing.keyPassword + "\n") }
        tools.run(tools.android("apksigner", true), "sign", "--ks", signing.keystore, "--ks-key-alias", signing.alias,
            "--ks-pass", "file:${storePassword.path}", "--key-pass", "file:${keyPassword.path}",
            "--v4-signing-enabled", "false", "--out", signed, aligned)
        tools.run(tools.android("apksigner", true), "verify", signed)
        tools.run(tools.android("zipalign"), "-c", "-p", "4", signed)
        ZipFile(signed).use { require(it.getEntry(profile.text("LIBRARY")) != null && it.getEntry("classes.dex") != null) }
        Files.move(signed.toPath(), output.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    }
}
