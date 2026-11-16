package pa.game

import java.io.File
import java.nio.file.Files

internal class Toolchain(val root: File, val sdk: File, val javaHome: File = File(System.getProperty("java.home"))) {
    val windows = System.getProperty("os.name").startsWith("Windows", true)
    private val host = if (windows) "windows-x86_64" else "linux-x86_64"
    val buildTools = File(sdk, "build-tools/36.1.0")
    val platform = File(sdk, "platforms/android-36")
    val llvm = File(sdk, "ndk/29.0.13113456/toolchains/llvm/prebuilt/$host/bin")
    fun executable(directory: File, name: String, batch: Boolean = false): File {
        val suffix = if (!windows) "" else if (batch) ".bat" else ".exe"
        return File(directory, name + suffix).also { require(it.isFile) { "Missing tool $it" } }
    }
    fun java(name: String) = executable(File(javaHome, "bin"), name)
    fun android(name: String, batch: Boolean = false) = executable(buildTools, name, batch)
    fun native(name: String) = executable(llvm, name)
    fun adb() = executable(File(sdk, "platform-tools"), "adb")
    fun run(arguments: List<String>, directory: File = root): String {
        require(arguments.isNotEmpty())
        val command = if (windows && arguments.first().endsWith(".bat", true)) {
            listOf("cmd.exe", "/d", "/c") + arguments
        } else arguments
        val log = Files.createTempFile(root.resolve("build").toPath(), "tool-", ".log").toFile()
        try {
            val process = ProcessBuilder(command).directory(directory).redirectErrorStream(true)
                .redirectOutput(log).apply { environment()["JAVA_HOME"] = javaHome.absolutePath }.start()
            val status = try { process.waitFor() } finally {
                if (process.isAlive) process.destroyForcibly()
            }
            val output = log.readText()
            if (status != 0) {
                val diagnostics = root.resolve("build/diagnostics/tool-failures").apply { mkdirs() }
                val retained = diagnostics.resolve(log.name)
                log.copyTo(retained, overwrite = true)
                error("${arguments.first()} exited with $status. Log $retained\n$output")
            }
            return output
        } finally { log.delete() }
    }
    fun run(vararg arguments: Any): String = run(arguments.map { it.toString() })
}
