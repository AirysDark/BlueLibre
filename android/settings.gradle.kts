// ----- Plugin repositories (where Gradle looks for plugins like AGP) -----
pluginManagement {
    repositories {
        // Required for com.android.application / com.android.library, etc.
        google()
        // Community Gradle plugins
        gradlePluginPortal()
        // Libraries that also publish their plugins here
        mavenCentral()
    }
}

// ----- Dependency repositories (where your app/libs come from) -----
dependencyResolutionManagement {
    // Prevent modules from declaring their own repos (keeps it centralized here)
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        // Required for most AndroidX / Compose / AGP transitive artifacts
        google()
        // Most third-party libs
        mavenCentral()
        // (Optional) add more repos here if you really need them, e.g.:
        // maven("https://jitpack.io")
    }
}

// ----- Name your root project (change to your preferred name) -----
rootProject.name = "BlueLibre"

// ----- Include modules in the build -----
include(":app")
// If you have more modules, list them as well:
// include(":core", ":feature:home", ":feature:settings")
