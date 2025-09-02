
librepods — settings fix

What this zip contains
----------------------
- android/settings.gradle.kts   (Kotlin DSL — single version-catalog 'from' call)
- README.txt

What you need to do
-------------------
1) Ensure you **remove android/settings.gradle** (the Groovy DSL one).
   Gradle must see only ONE settings file, otherwise the version catalog
   will be imported twice and you'll get the: 
     "you can only call the 'from' method a single time" error.

2) Place settings.gradle.kts from this zip at: android/settings.gradle.kts
   (replace the existing file if present).

3) Clean caches and rebuild:
     On local:
       - Delete: .gradle/ and android/.gradle/ folders (optional but helpful)
       - Run:     ./gradlew --no-build-cache clean :app:assembleDebug
     On GitHub Actions:
       - Caches will refresh automatically; no extra changes needed.

Notes
-----
- Your libs.versions.toml should remain at: android/gradle/libs.versions.toml
- If you keep only the Kotlin DSL settings file, this error should be gone.
