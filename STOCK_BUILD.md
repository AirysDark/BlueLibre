
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

## Build
Open `android/` in Android Studio and build the `app` module as usual.


## Optional: High-throughput BLE L2CAP CoC (API 29+)
- Added `com.yourco.airpods.L2capCocManager` and integrated into `BleClient`.
- If the accessory exposes a **PSM characteristic** at UUID `0000FF01-0000-1000-8000-00805F9B34FB` (little-endian 16-bit PSM),
  the app will attempt a **CoC** client connection automatically and fall back to GATT on failure.
- You can flip the in-code flag `useCocPreferred` to force GATT if needed.

> Note: AirPods may not expose CoC; this logic auto-falls back to GATT if CoC isn’t available.

Added a **Settings toggle** under CocSettingsScreen: lets the user enable/disable L2CAP CoC preference at runtime.

- Added Settings toggle: **Prefer high-throughput (L2CAP)** in App Settings. Persisted via SharedPreferences.
