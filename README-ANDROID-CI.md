# Librepods Android CI Quick Drop-in

This bundle gives you:
- `.github/workflows/android.yml` — minimal, stable CI using JDK 21 + Gradle cache.
- `android/gradle.properties` — safe defaults for CI speed.
- `android/app/build.gradle.kts` — cleaned app module config (no androidComponents/APK hooks).

## How to apply

1. Copy **.github/workflows/android.yml** into your repo.
2. Copy **android/gradle.properties** (merge with yours if you already have one).
3. Replace **android/app/build.gradle.kts** (or adapt the changes into your current file).

> Important: Remove any `androidComponents { ... }` code that references `MultipleArtifact.APK`.
> That API doesn't exist; it prevents variants from being created, which is why no APKs are produced.

## Run locally
From the `android` folder:
```
./gradlew assembleDebug
```
The APK will be at:
```
android/app/build/outputs/apk/debug/app-debug.apk
```'
