
# LibrePods — Stock (Non‑root) Build

This build removes the L2CAP FCR native hook and Magisk/Xposed artifacts so the app runs on unmodified Android.

## Changes
- Removed `root-module/` and all Magisk packaging scripts.
- Disabled `System.loadLibrary("l2c_fcr_hook")` and any runtime offset checks.
- Start destination goes directly to the app (no root/onboarding gate).
- JNI kept only for `airpods_core` payload parsing (safe).

## Bluetooth Path (Public APIs Only)
- BLE GATT for discovery/control.
- Optionally add BLE L2CAP CoC for API 29+ (client/server) with GATT fallback.

Build & behavior

Open android/ in Android Studio → build/run app.

On Android 10+:

If your pods (or your accessory firmware) expose a PSM characteristic at 0000FF01-0000-1000-8000-00805F9B34FB, the app will try L2CAP CoC.

If not, or if connect fails, it falls back to GATT seamlessly.


Toggle is ON by default; users can switch it off anytime in App Settings.

## Optional: High-throughput BLE L2CAP CoC (API 29+)
- Added `com.yourco.airpods.L2capCocManager` and integrated into `BleClient`.
- If the accessory exposes a **PSM characteristic** at UUID `0000FF01-0000-1000-8000-00805F9B34FB` (little-endian 16-bit PSM),
  the app will attempt a **CoC** client connection automatically and fall back to GATT on failure.
- You can flip the in-code flag `useCocPreferred` to force GATT if needed.

> Note: AirPods may not expose CoC; this logic auto-falls back to GATT if CoC isn’t available.

Added a **Settings toggle** under CocSettingsScreen: lets the user enable/disable L2CAP CoC preference at runtime.

- Added Settings toggle: **Prefer high-throughput (L2CAP)** in App Settings. Persisted via SharedPreferences.
703048


# librepods

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
