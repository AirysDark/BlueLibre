# BlueLibre — AI Autobuilder (Android/Gradle, OpenAI preset)

This drops into your BlueLibre repo and makes CI self-heal Android build failures.

## GitHub setup (once)

1) Copy these into your repo:
```
tools/ai_autobuilder.py
.github/workflows/ai-autobuilder.yml
```

2) Repo → Settings → Secrets and variables → Actions
- **Secret**: `OPENAI_API_KEY = sk-...yourkey...`
- **Variable**: `BUILD_CMD = ./gradlew assembleDebug --stacktrace`
- (Optional) **Variable**: `OPENAI_MODEL = gpt-4.1-mini`

3) Push any change or open the **Actions** tab → run **BlueLibre AI Autobuilder**.

## How it works
- Runs your Gradle build, captures logs to `build.log`.
- Asks OpenAI for a minimal unified-diff patch to fix the failure.
- Applies the patch, retries the build up to 2–3 times.
- If still failing, pushes a `fix/ai-autobuilder-<run_id>` branch with the changes.

## Local use
```bash
export OPENAI_API_KEY=sk-...yourkey...
export PROVIDER=openai
export BUILD_CMD="./gradlew assembleDebug --stacktrace"
python3 tools/ai_autobuilder.py
```

## Revert a bad patch
```bash
git apply -R .pre_ai_fix.patch
```

## Notes
- This workflow sets up JDK 17 and Android SDK platform 34 / build-tools 34.0.0.
- Adjust SDK versions in `.github/workflows/ai-autobuilder.yml` if your project needs a different API level.
