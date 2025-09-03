# Bluelibre. v1.0.0

A cross-platform AirPods desktop & Android client.  
Supports model detection and battery status display for **AirPods 1, 2, 3, 4, 4 ANC, Pro, Pro 2, and Max**.

---

=======
>>>>>>> b9ad7d31f761902b107364aa10d1d236867ab441
## 🖥️ Windows 10/11 (x64)

```powershell
git clone https://github.com/AirysDark/librepods
cd librepods

# Bootstrap vcpkg
git clone https://github.com/microsoft/vcpkg .vcpkg
.\.vcpkg\bootstrap-vcpkg.bat

# Configure & build (uses CMakePresets.json)
cmake --preset win64-release
cmake --build --preset win64-release-build --parallel
cmake --install build --prefix build\out
```

---

## 🐧 Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build pkg-config libdbus-1-dev libbluetooth-dev

git clone https://github.com/AirysDark/librepods
cd librepods

git rm airpods_models.cpp && git commit -m "fix: remove duplicate root airpods_models.cpp"  # if present

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
sudo cmake --install build --prefix /usr/local
```

---

## 🤖 Android

```bash
cd android
chmod +x gradlew
./gradlew :app:assembleDebug
```

Or open `android/` in **Android Studio** (Java 17 + NDK + CMake required).

---

## ⚙️ GitHub Actions (CI)

### Windows workflow
Ensure the job:
- Runs on `windows-latest`
- Installs **Ninja**
- Bootstraps **vcpkg**
- Calls `cmake --preset win64-release` and builds

Example steps:

```yaml
- uses: actions/checkout@v4
- name: Install Ninja
  run: choco install ninja -y
- name: Bootstrap vcpkg
  run: |
    git clone https://github.com/microsoft/vcpkg .vcpkg
    .\.vcpkg\bootstrap-vcpkg.bat
- name: Configure
  run: cmake --preset win64-release
- name: Build
  run: cmake --build --preset win64-release-build --parallel
```

### Android workflow
- Use **Java 17 (Temurin)**
- Install **NDK + CMake** in runner
- Make `gradlew` executable
- Build with `:app:assembleDebug`

Example steps:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-java@v4
  with:
    distribution: temurin
    java-version: "17"
- name: Grant execute to gradlew
  run: chmod +x android/gradlew
- name: Build debug APK
  working-directory: android
  run: ./gradlew :app:assembleDebug --no-daemon
```

---

## 📦 Features
- WinRT backend for Windows
- BlueZ/DBus backend for Linux
- Kotlin BLE + JNI bridge for Android
- All AirPods models supported with fallback display
