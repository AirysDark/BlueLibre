# BlueLibre — AI Autobuilder with OpenAI → llama.cpp fallback

This package adds a CI workflow that tries OpenAI first and, on quota or request errors, falls back to a local llama.cpp model.

## Files
- `tools/ai_autobuilder.py` — patched with fallback
- `.github/workflows/ai-autobuilder-android.yml` — Android workflow with wrapper autodetect, exit-code capture, and llama.cpp install

## GitHub Actions setup
1. Add files to your repo and commit.
2. Settings → Secrets and variables → Actions:
   - **Secret**: `OPENAI_API_KEY = sk-...` (optional if you rely only on llama)
   - **Variable**: `OPENAI_MODEL = gpt-4o-mini` (recommended)
   - **Variable**: `MODEL_PATH = models/Llama-3-8B-Instruct.Q4_K_M.gguf` (path to your GGUF in CI)

## Providing a GGUF model in CI
- Upload your model to a private release or artifact and download it in a prior step, e.g.:
  ```yaml
  - name: Fetch GGUF model
    run: |
      mkdir -p models
      curl -L -o models/Llama-3-8B-Instruct.Q4_K_M.gguf "<YOUR_SIGNED_URL>"
  ```

## Local run
```bash
export OPENAI_API_KEY=sk-...          # optional if using llama only
export PROVIDER=openai
export FALLBACK_PROVIDER=llama
export MODEL_PATH=~/models/Llama-3-8B-Instruct.Q4_K_M.gguf
export BUILD_CMD="cd android && ./gradlew assembleDebug --stacktrace"
python3 tools/ai_autobuilder.py
```

## Revert a patch
```bash
git apply -R .pre_ai_fix.patch
```
