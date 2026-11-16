package pa.game

import org.gradle.api.DefaultTask
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.*
import java.io.File
import java.nio.file.Files
import java.util.Properties

abstract class BuildGameTask : DefaultTask() {
    @get:Internal abstract val workspace: DirectoryProperty
    @get:Internal abstract val sdk: DirectoryProperty
    @get:InputFile abstract val sourceApk: RegularFileProperty
    @get:InputFile abstract val composeApk: RegularFileProperty
    @get:InputFile abstract val profileFile: RegularFileProperty
    @get:InputFile abstract val keystore: RegularFileProperty
    @get:InputFile abstract val signingProperties: RegularFileProperty
    @get:InputFile abstract val obb: RegularFileProperty
    @get:Input abstract val host: Property<String>
    @get:Input abstract val projectVersion: Property<String>
    @get:InputFiles abstract val patchSources: ConfigurableFileCollection
    @get:Classpath abstract val smaliClasspath: ConfigurableFileCollection
    @get:OutputFile abstract val output: RegularFileProperty

    @TaskAction fun build() {
        val root = workspace.get().asFile
        val target = output.get().asFile
        target.parentFile.mkdirs()
        val staging = Files.createTempDirectory(target.parentFile.toPath(), "game-build-").toFile()
        try {
            val tools = Toolchain(root, sdk.get().asFile)
            ApkBuilder(tools, V49Profile(profileFile.get().asFile)).build(
                sourceApk.get().asFile, composeApk.get().asFile, obb.get().asFile,
                ApkSigning.load(keystore.get().asFile, signingProperties.get().asFile),
                projectVersion.get(), smaliClasspath.asPath, target, staging)
            logger.lifecycle("Built ${target.absolutePath}")
        } finally { staging.deleteRecursively() }
    }
}

internal fun Project.gameProperty(name: String, fallback: String): String = providers.gradleProperty("game.$name").getOrElse(fallback)

class GameBuildPlugin : Plugin<Project> {
    override fun apply(project: Project) = with(project) {
        val root = rootDir
        val local = Properties()
        root.resolve("local.properties").takeIf { it.isFile }?.inputStream()?.use { local.load(it) }
        val sdkPath = gameProperty("sdkDir", local.getProperty("sdk.dir")
            ?: System.getenv("ANDROID_HOME") ?: System.getenv("ANDROID_SDK_ROOT") ?: "")
        require(!providers.gradleProperty("game.edition").isPresent) {
            "game.edition has been removed. Run buildGame to build the APK with bundled resources."
        }
        val source = file(gameProperty("sourceApk", "com.paradoxplaza.prisonarchitect.apk"))
        val obbFile = file(gameProperty("obb", "com.paradoxplaza.prisonarchitect/main.49.com.paradoxplaza.prisonarchitect.obb"))
        val signingFile = file(gameProperty("signingProperties", "signing/signing.properties"))
        val signing = Properties()
        signingFile.takeIf { it.isFile }?.inputStream()?.use { signing.load(it) }
        val keystoreFile = file(gameProperty("keystore", signing.getProperty("storeFile", "signing/prisonarchitect.p12")))
        val outputFile = root.resolve("build/PrisonArchitect.apk")
        val profile = root.resolve("game/profiles/v49.json")
        val sdkDir = file(sdkPath.ifEmpty { "." })
        val smali = configurations.create("gameSmali") { isCanBeConsumed = false }
        dependencies.add(smali.name, "com.android.tools.smali:smali:3.0.10")
        dependencies.add(smali.name, "com.android.tools.smali:smali-baksmali:3.0.10")
        val preflight = tasks.register("validateGameInputs") {
            group = "game"
            doLast {
                require(sdkPath.isNotEmpty()) { "Set game.sdkDir, sdk.dir or ANDROID_HOME" }
                require(source.isFile) { "Missing source APK $source" }
                require(profile.isFile) { "Missing patch profile $profile" }
                require(obbFile.isFile) { "Missing OBB $obbFile" }
                require(signingFile.isFile) { "Missing signing configuration $signingFile. See game/README.md" }
                require(keystoreFile.isFile) { "Missing signing keystore $keystoreFile" }
                val tools = Toolchain(root, sdkDir)
                for (name in listOf("clang", "ld.lld", "llvm-nm", "llvm-objcopy")) tools.native(name)
                tools.android("aidl"); tools.android("aapt"); tools.android("zipalign")
                tools.android("d8", true); tools.android("apksigner", true)
                require(tools.platform.resolve("android.jar").isFile) { "Android SDK Platform 36 is required" }
            }
        }
        val build = tasks.register("buildGame", BuildGameTask::class.java) {
            group = "game"
            description = "Build the game APK with Kotlin patching and packaging."
            dependsOn(preflight, ":mod-manager:assembleDebug")
            workspace.set(layout.projectDirectory)
            sdk.set(sdkDir)
            sourceApk.set(source)
            composeApk.set(root.resolve("game/obb-bridge/compose/build/outputs/apk/debug/mod-manager-debug.apk"))
            profileFile.set(profile)
            keystore.set(keystoreFile)
            signingProperties.set(signingFile)
            host.set(System.getProperty("os.name") + "/" + System.getProperty("java.version"))
            projectVersion.set(provider { project.version.toString() })
            patchSources.from(fileTree("game") { include("*.c", "*.S", "obb-bridge/*.java", "obb-bridge/aidl/**/*.aidl") })
            obb.set(obbFile)
            val localSmali = providers.gradleProperty("game.smaliDir")
            smaliClasspath.from(if (localSmali.isPresent) fileTree(localSmali.get()) { include("*.jar") } else smali)
            output.set(outputFile)
        }
        val check = tasks.register("checkGame") {
            group = "game"
            description = "Run Python ARM regressions on an existing APK."
            mustRunAfter(build)
            dependsOn(":mod-manager:syncArchiveJar")
            doLast {
                val target = file(gameProperty("checkApk", outputFile.path))
                require(target.isFile) { "Missing APK $target. Run buildGame first." }
                GameChecks(root, sdkDir, gameProperty("python", if (System.getProperty("os.name").startsWith("Windows")) "python" else "python3"))
                    .run(target, obbFile, gameProperty("checks", "full"), project.version.toString(), logger::lifecycle)
            }
        }
        tasks.register("generateNativeRegions") {
            group = "game"
            doLast {
                root.resolve("build").mkdirs()
                val tools = Toolchain(root, sdkDir)
                logger.lifecycle(tools.run(gameProperty("python", if (tools.windows) "python" else "python3"),
                    root.resolve("game/generate_native_regions.py"), "--apk", source, "--obb", obbFile))
            }
        }
        tasks.register("installGame") {
            group = "game"
            description = "Build, check and install on the explicitly selected device."
            dependsOn(build, check)
            doLast {
                require(file(gameProperty("checkApk", outputFile.path)).canonicalFile == outputFile.canonicalFile) { "installGame must check the APK being installed" }
                val serial = providers.gradleProperty("game.device").orNull ?: error("Set -Pgame.device=<serial>")
                val tools = Toolchain(root, sdkDir)
                val prefix = listOf(tools.adb().path, "-s", serial)
                val gamePid = runCatching { tools.run(prefix + listOf("shell", "pidof", GAME_PACKAGE)) }.getOrDefault("")
                require(gamePid.trim().isEmpty()) { "Save and exit the game before installing" }
                logger.lifecycle(tools.run(prefix + listOf("install", "-r", outputFile.path)))
                if (gameProperty("launch", "false").toBoolean()) logger.lifecycle(tools.run(prefix +
                    listOf("shell", "am", "start", "-n", "$GAME_PACKAGE/$ORIGINAL_GAME_PACKAGE.core.MainActivity")))
            }
        }
        gradle.projectsEvaluated {
            project(":mod-manager").tasks.named("preDebugBuild").configure { mustRunAfter(preflight) }
        }
    }
}
