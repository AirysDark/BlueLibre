*** a/app/build.gradle.kts
--- b/app/build.gradle.kts
@@
-plugins {
-    id("com.android.application")
-    id("org.jetbrains.kotlin.android")
-    // id("org.jetbrains.kotlin.plugin.compose") // remove: not needed
-}
+plugins {
+    alias(libs.plugins.android.application)
+    alias(libs.plugins.kotlin.android)
+}
 
 android {
@@
+    buildFeatures {
+        compose = true
+    }
+    // With Kotlin 2.0+, Compose compiler is bundled. If you need to pin it, uncomment:
+    // composeOptions {
+    //     kotlinCompilerExtensionVersion = "1.6.11"
+    // }
 }
 
 dependencies {
-    // Compose deps — make sure to use the BOM
-    implementation(platform("androidx.compose:compose-bom:2024.10.00"))
-    implementation("androidx.compose.ui:ui")
-    implementation("androidx.compose.ui:ui-graphics")
-    implementation("androidx.compose.ui:ui-tooling-preview")
-    implementation("androidx.compose.material3:material3")
-    implementation("androidx.activity:activity-compose:1.9.2")
-    implementation("androidx.navigation:navigation-compose:2.8.0")
+    // Compose using version catalog + BOM
+    implementation(platform(libs.androidx.compose.bom))
+    implementation(libs.androidx.ui)
+    implementation(libs.androidx.ui.graphics)
+    implementation(libs.androidx.ui.tooling.preview)
+    implementation(libs.androidx.material3)
+    implementation(libs.androidx.activity.compose)
+    implementation(libs.androidx.navigation.compose)
@@
     implementation(libs.androidx.core.ktx)
     implementation(libs.androidx.lifecycle.runtime.ktx)
     implementation(libs.annotations)
 }
