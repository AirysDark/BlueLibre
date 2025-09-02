# CI Workflows for librepods

Drop this `.github/workflows/` folder into the root of your repository.

## Windows x64 Build
- Installs Ninja
- Bootstraps vcpkg
- Configures with CMake preset `win64-release`
- Builds, installs to `build/out`, and uploads an artifact

## Android Debug APK
- Uses Java 17 (Temurin)
- Makes Gradle wrapper executable
- Builds `:app:assembleDebug` and uploads the APK

If the Android job cannot find NDK/CMake automatically,
uncomment the SDK manager steps to install a specific NDK and CMake version.
