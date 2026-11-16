package pa.game

import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class BundledResourcesTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test fun checksRejectAnApkWithoutBundledResources() {
        val apk = temporary.newFile("game.apk")
        ZipOutputStream(apk.outputStream()).use {
            it.putNextEntry(ZipEntry("AndroidManifest.xml"))
            it.write(byteArrayOf(0))
            it.closeEntry()
        }
        val error = assertThrows(IllegalArgumentException::class.java) {
            GameChecks(temporary.root, File(temporary.root, "sdk"), "unused-python")
                .run(apk, File(temporary.root, "resources.obb"), "smoke") {}
        }
        assertTrue(error.message.orEmpty().contains("bundled OBB"))
    }
}
