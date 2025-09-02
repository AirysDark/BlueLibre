plugins {
    alias(cat.plugins.android.application)
    alias(cat.plugins.kotlin.android)
    alias(cat.plugins.kotlin.compose)
    id("kotlin-parcelize")
}
// …and in dependencies: implementation(cat.androidx.core.ktx) etc.

android {
    namespace = "me.kavishdevar.librepods"
    compileSdk = 35

    defaultConfig {
        applicationId = "me.kavishdevar.librepods"
        minSdk = 28
        targetSdk = 35
        versionCode = 7
        versionName = "0.1.0-rc.4"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures {
        compose = true
        viewBinding = true
    }

    // Keep if you actually have CMakeLists.txt
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    packaging {
        // Helpful defaults
        resources.excludes += setOf(
            "META-INF/AL2.0", "META-INF/LGPL2.1",
            "META-INF/*.kotlin_module"
        )
    }
}

dependencies {
    implementation(cat.accompanist.permissions)
    implementation(cat.hiddenapibypass)
    implementation(cat.androidx.core.ktx)
    implementation(cat.androidx.lifecycle.runtime.ktx)
    implementation(cat.androidx.activity.compose)

    implementation(platform(cat.androidx.compose.bom))
    implementation(cat.androidx.ui)
    implementation(cat.androidx.ui.graphics)
    implementation(cat.androidx.ui.tooling.preview)
    implementation(cat.androidx.material3)

    implementation(cat.annotations)
    implementation(cat.androidx.navigation.compose)

    implementation(cat.androidx.constraintlayout)
    implementation(cat.haze)
    implementation(cat.haze.materials)
    implementation(cat.androidx.dynamicanimation)

    // Local AARs if any present
    compileOnly(fileTree(mapOf("dir" to "libs", "include" to listOf("*.aar"))))
}
