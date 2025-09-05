### AirysDark-AI: detector results

**Detected build types:**
- linux
  - folder hint: 'linux' present in path segments
  - CMakeLists suggests desktop build: CMakeLists.txt
  - CMakeLists suggests desktop build: linux/CMakeLists.txt
  - CMakeLists suggests desktop build: android/app/src/main/cpp/CMakeLists.txt
- android
  - folder hint: 'android' present in path segments
  - found gradle settings: android/settings.gradle.kts
  - found gradle: android/build.gradle.kts
  - found gradle: android/app/build.gradle.kts
- cmake
  - found 3 CMakeLists.txt

**Next steps:**
1. Edit **`.github/workflows/AirysDark-AI_prob.yml`** and set `env.TARGET` to the build you want (e.g. `android`, `linux`, `cmake`).
2. Merge this PR.
3. From the Actions tab, manually run **AirysDark-AI - Probe (LLM builds workflow)**.

