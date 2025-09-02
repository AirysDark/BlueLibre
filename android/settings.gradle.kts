// android/settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
    versionCatalogs {
        // NOTE: we renamed the catalog to "cat" (since you changed usages to cat.*)
        create("cat") {
            from(files("gradle/libs.versions.toml"))
        }
    }
}

rootProject.name = "librepods"
include(":app")