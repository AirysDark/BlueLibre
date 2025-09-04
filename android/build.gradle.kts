plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

android {
    buildFeatures { compose = true }
    // With Kotlin 2.x, you can usually omit the compiler extension version;
    // if you need to pin it, add composeOptions with a matching version.
    // composeOptions { kotlinCompilerExtensionVersion = "1.6.x" }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
}
