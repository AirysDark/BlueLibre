plugins {
    alias(cat.plugins.android.application) apply false
    alias(cat.plugins.kotlin.android)      apply false
    alias(cat.plugins.kotlin.compose)      apply false
}

tasks.register<Delete>("clean") {
    delete(rootProject.buildDir)
}

buildscript {
    repositories {
        google()
        mavenCentral()
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
