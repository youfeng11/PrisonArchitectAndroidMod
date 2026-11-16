pluginManagement {
    includeBuild("build-logic")
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
dependencyResolutionManagement {
    repositories { google(); mavenCentral() }
}
rootProject.name = "PrisonArchitect"
include(":mod-manager")
project(":mod-manager").projectDir = file("game/obb-bridge/compose")
