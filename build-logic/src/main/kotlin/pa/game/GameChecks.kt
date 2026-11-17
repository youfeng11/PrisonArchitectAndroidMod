package pa.game

import java.io.File
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.zip.ZipFile

internal class GameChecks(private val root: File, sdk: File, private val python: String) {
    private val tools = Toolchain(root, sdk)
    fun run(apk: File, obb: File, mode: String, projectVersion: String, log: (String) -> Unit) {
        require(mode in listOf("smoke", "full"))
        root.resolve("build").mkdirs()
        ZipFile(apk).use { require(it.getEntry(OBB_ASSET) != null) { "APK is missing the bundled OBB" } }
        val fixtures = listOf("mods_Office_Chair.zip", "mods_Additional_Guard_Sprites.zip", "mods_Additional_Staff_Sprites.zip",
            "mods_2010s_Chinese_style_Prison_Mod.zip", "mods_clearer_needs_icons.zip", "batman-callout.zip",
            "super-grants.zip", "log-export-fix.zip").map { root.resolve("fixtures/mods/$it").path }
        require(obb.isFile) { "Missing OBB $obb" }
        if (mode == "full") {
            fixtures.forEach { require(File(it).isFile) { "Missing regression fixture $it" } }
            require(root.resolve("fixtures/native/native-regions.tsv").isFile) { "Run generateNativeRegions first" }
        }
        val checks = linkedMapOf("APK signature" to listOf(tools.android("apksigner", true).path, "verify", apk.path))
        fun add(name: String, script: String, vararg args: String) {
            checks[name] = listOf(python, root.resolve("game/$script").path) + args
        }
        val scan = mutableListOf(apk.path)
        if (mode == "smoke") scan += "--no-mod-fixtures" else scan += listOf("--obb", obb.path)
        add("Native mod loading", "verify_native_mod_scan.py", *scan.toTypedArray())
        add("Native Lua job API", "verify_native_mod_lua.py", apk.path)
        add("Bundled resources and startup", "verify_offline_game.py", apk.path, obb.path, tools.android("aapt").path,
            "--project-version", projectVersion)
        add("Mod texture color quality", "verify_native_quantization.py", apk.path)
        if (mode == "full") {
            add("Office Chair atlas", "verify_native_mod_atlas.py", apk.path, obb.path, fixtures[0])
            add("Guard and staff atlases", "verify_native_mod_atlas.py", apk.path, obb.path, fixtures[1], fixtures[2])
            add("Chinese style atlas", "verify_native_mod_atlas.py", apk.path, obb.path, fixtures[3])
            add("Sheets and complaint icons", "verify_native_mod_atlas.py", apk.path, obb.path, fixtures[3], "--full-sheets", "--complaints", fixtures[4])
            add("Sprite replacements and previews", "verify_native_sprite_replacements.py", apk.path)
            add("Production and providers", "verify_native_production.py", apk.path, obb.path, fixtures[7])
            val laborer = root.resolve("fixtures/mods/劳动者mod.zip")
            require(laborer.isFile) { "Missing regression fixture $laborer" }
            add("Custom staff behavior", "verify_native_default_staff.py", apk.path, laborer.path)
            add("Custom staff atlas", "verify_native_mod_atlas.py", apk.path, obb.path, laborer.path)
            val manufactury = root.resolve("fixtures/mods/mods_Manufactury_4_0.zip")
            require(manufactury.isFile) { "Missing regression fixture $manufactury" }
            add("Manufactury atlas", "verify_native_mod_atlas.py", apk.path, obb.path, manufactury.path)
            add("Manufactury research", "verify_native_mod_research.py", apk.path, obb.path, manufactury.path)
            add("Mod storage and imports", "verify_native_mod_store.py", tools.javaHome.path, *fixtures.toTypedArray(), manufactury.path)
        }
        val executor = Executors.newFixedThreadPool(4)
        try {
            val results = executor.invokeAll(checks.map { (name, command) -> Callable {
                name to runCatching { tools.run(command) }
            } })
            val failed = mutableListOf<String>()
            for (future in results) {
                val (name, result) = future.get()
                log("[${if (result.isSuccess) "PASS" else "FAIL"}] $name")
                log(result.getOrElse { failed += name; it.message ?: it.toString() })
            }
            check(failed.isEmpty()) { "Failed checks: ${failed.joinToString()}" }
            log("Passed ${checks.size} checks for $apk")
        } finally { executor.shutdownNow() }
    }
}
