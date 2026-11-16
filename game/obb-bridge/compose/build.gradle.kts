plugins {
    id("com.android.application") version "9.5.1"
    id("org.jetbrains.kotlin.plugin.compose") version "2.2.10"
}

abstract class CopyModStore : DefaultTask() {
    @get:InputFiles abstract val sources: ConfigurableFileCollection
    @get:OutputDirectory abstract val output: DirectoryProperty

    @TaskAction
    fun copySource() {
        for (source in sources) {
            source.copyTo(output.file(source.name).get().asFile, overwrite = true)
        }
    }
}

val storeSources = tasks.register<CopyModStore>("copyStoreSources") {
    sources.from("../NativeModStore.java", "../ModArchive.java", "../MaterialDefinitionRepair.java")
    output.set(layout.buildDirectory.dir("generated/modStore"))
}

val libarchive = "me.zhanghai.android.libarchive:library:1.1.6"
val libarchiveForJvm = configurations.create("libarchiveForJvm") {
    isTransitive = false
    isCanBeConsumed = false
}

tasks.register<Sync>("syncArchiveJar") {
    from(libarchiveForJvm.elements.map { files ->
        zipTree(files.single().asFile).matching { include("classes.jar") }
    })
    into(layout.buildDirectory.dir("archive-jvm"))
}

android {
    namespace = "com.paradoxplaza.prisonarchitect.patools"
    compileSdk { version = release(37) }

    defaultConfig {
        applicationId = "com.paradoxplaza.prisonarchitect.patools"
        minSdk = 28
    }

    buildTypes {
        create("preview") {
            initWith(getByName("debug"))
            matchingFallbacks += "debug"
        }
    }

    buildFeatures { compose = true }
    testOptions { unitTests.isIncludeAndroidResources = true }
    androidResources {
        additionalParameters += listOf("--package-id", "0x80")
    }
}

androidComponents {
    // Compose preview discovery packages resources through each variant's unit tests.
    beforeVariants {
        (it as com.android.build.api.variant.HasUnitTestBuilder).enableUnitTest = true
    }
    onVariants { it.sources.java?.addGeneratedSourceDirectory(storeSources, CopyModStore::output) }
}

kotlin {
    compilerOptions { moduleName.set("GameModManager") }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.11.0")
    implementation("androidx.lifecycle:lifecycle-livedata-core-ktx:2.11.0")
    implementation("androidx.compose.material3:material3")
    add("previewImplementation", "androidx.compose.ui:ui-tooling")
    implementation(libarchive)
    add(libarchiveForJvm.name, "${libarchive}@aar")
}
