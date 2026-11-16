plugins { `kotlin-dsl` }
repositories { google(); mavenCentral(); gradlePluginPortal() }
dependencies {
    implementation(localGroovy())
    testImplementation("junit:junit:4.13.2")
}
gradlePlugin {
    plugins {
        create("gameBuild") {
            id = "pa.game-build"
            implementationClass = "pa.game.GameBuildPlugin"
        }
    }
}
