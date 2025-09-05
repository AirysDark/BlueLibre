#!/usr/bin/env python3
# AirysDark-AI_android.py — Android workflow generator + AI probe
#
# Modes:
#   --mode probe-ai    -> Use AI (OpenAI -> llama.cpp -> heuristic) to derive BUILD_CMD,
#                         write final Android workflow, and dump probe artifacts.
#
# Env used for AI:
#   OPENAI_API_KEY, OPENAI_MODEL (default gpt-4o-mini)
#   MODEL_PATH (llama gguf), LLAMA_CPP_BIN (llama-cli)
#
# Secrets expected in workflow when running final build:
#   BOT_TOKEN (FG-PAT), optional OPENAI_API_KEY
#
# Files consumed (optional, produced by detector):
#   tools/airysdark_ai_probe_inputs.json
#
# Files written:
#   tools/android_probe.json
#   tools/android_probe.log
#   .github/workflows/AirysDark-AI_android.yml
#
import os, json, pathlib, subprocess, shlex, re, textwrap, sys

ROOT = pathlib.Path(".").resolve()
TOOLS = ROOT / "tools"
WF    = ROOT / ".github" / "workflows"
TOOLS.mkdir(parents=True, exist_ok=True)
WF.mkdir(parents=True, exist_ok=True)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLAMA_CPP_BIN = os.getenv("LLAMA_CPP_BIN", "llama-cli")
LLAMA_MODEL_PATH = os.getenv("MODEL_PATH", "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")

def sh(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.stdout, p.returncode

def read_text(p: pathlib.Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except Exception:
        return ""

def repo_tree(limit=400):
    out, _ = sh("git ls-files || true")
    files = out.strip().splitlines()
    return "\n".join(files[:limit])

def load_probe_inputs():
    p = TOOLS / "airysdark_ai_probe_inputs.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}

def call_openai(prompt: str) -> str:
    import requests
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("no_openai_key")
    url = "https://api.openai.com/v1/chat/completions"
    payload = {"model": OPENAI_MODEL,
               "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.2}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"openai_http_{r.status_code}:{r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"]

def call_llama(prompt: str) -> str:
    mp = pathlib.Path(LLAMA_MODEL_PATH)
    if not mp.exists():
        raise RuntimeError("llama_model_missing")
    args = [LLAMA_CPP_BIN, "-m", str(mp), "-p", prompt, "-n", "512", "--temp", "0.2", "-c", "4096"]
    out = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if out.returncode != 0:
        raise RuntimeError("llama_failed")
    return out.stdout

def parse_build_cmd_from_ai(text: str) -> str | None:
    """
    Accepts answers that contain a command line; we try to pull the first plausible gradle invocation.
    """
    # common patterns
    m = re.search(r'(?:^|\n)(?:cd [^\n]+ && )?\.?/gradlew[^\n]+', text)
    if m: return m.group(0).strip()
    m = re.search(r'(?:^|\n)cd [^\n]+ && \.\/gradlew[^\n]+', text)
    if m: return m.group(0).strip()
    # minimal
    m = re.search(r'(?:^|\n)\.\/gradlew\s+[^\n]+', text)
    if m: return m.group(0).strip()
    return None

def heuristic_fallback() -> str:
    # last-resort guess
    # try to find a gradlew nearest root
    gw = None
    if (ROOT/"gradlew").exists(): gw = ROOT/"gradlew"
    else:
        for p in ROOT.glob("**/gradlew"):
            gw = p; break
    if gw is None:
        return "./gradlew assembleDebug --stacktrace"
    return f"cd {shlex.quote(str(gw.parent))} && ./gradlew assembleDebug --stacktrace"

def build_prompt(context):
    tree = repo_tree()
    hints = json.dumps(context, indent=2)
    log_tail = ""
    bl = ROOT / "build.log"
    if bl.exists():
        t = bl.read_text(errors="ignore").splitlines()
        log_tail = "\n".join(t[-120:])
    prompt = f"""
You are an Android build sherpa. Given this repo tree and hints, produce the single most likely command to build an installable app (APK/AAB) in CI. Prefer Debug if flavors exist.

Constraints:
- Output ONLY the shell command (NO explanation), e.g.:
  cd app && ./gradlew :app:assembleDebug --stacktrace

Repo tree (truncated):
{tree}

Hints (from detector):
{hints}

Recent build.log tail (if any):
{log_tail}
""".strip()
    return prompt

def write_final_workflow(build_cmd: str):
    yml = r"""
name: AirysDark-AI - Android (generated)

on:
  workflow_dispatch: {}

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install requests

      # Android toolchain
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - uses: android-actions/setup-android@v3
      - run: yes | sdkmanager --licenses
      - run: sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

      - name: Ensure AirysDark-AI tools (builder)
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p tools
          BASE_URL="https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools"
          [ -f tools/AirysDark-AI_builder.py ] || curl -fL "$BASE_URL/AirysDark-AI_builder.py" -o tools/AirysDark-AI_builder.py

      - name: Build (capture)
        id: build
        run: |
          set -euxo pipefail
          CMD="__BUILD_CMD__"
          echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"
          set +e; bash -lc "$CMD" | tee build.log; EXIT=$?; set -e
          echo "EXIT_CODE=$EXIT" >> "$GITHUB_OUTPUT"
          [ -s build.log ] || echo "(no build output captured)" > build.log
          exit 0
        continue-on-error: true

      - name: Upload build log
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: android-build-log
          path: build.log
          if-no-files-found: warn
          retention-days: 7

      - name: Upload common Android outputs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: android-outputs
          if-no-files-found: ignore
          retention-days: 7
          path: |
            **/build/outputs/**/*.apk
            **/build/outputs/**/*.aab
            **/build/outputs/**/*.mapping.txt
            **/build/outputs/**/mapping.txt

      # --- AI auto-fix (OpenAI -> llama.cpp) ---
      - name: Build llama.cpp (CMake, no CURL, in temp)
        if: ${{ always() && steps.build.outputs.EXIT_CODE != '0' }}
        run: |
          set -euxo pipefail
          TMP="${{ runner.temp }}"
          cd "$TMP"
          rm -rf llama.cpp
          git clone --depth=1 https://github.com/ggml-org/llama.cpp
          cd llama.cpp
          cmake -S . -B build -D CMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
          cmake --build build -j
          echo "LLAMA_CPP_BIN=$PWD/build/bin/llama-cli" >> $GITHUB_ENV

      - name: Fetch GGUF model (TinyLlama)
        if: ${{ always() && steps.build.outputs.EXIT_CODE != '0' }}
        run: |
          mkdir -p models
          curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
            https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

      - name: Attempt AI auto-fix (OpenAI -> llama fallback)
        if: ${{ always() && steps.build.outputs.EXIT_CODE != '0' }}
        env:
          PROVIDER: openai
          FALLBACK_PROVIDER: llama
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}
          MODEL_PATH: models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
          AI_BUILDER_ATTEMPTS: "3"
          BUILD_CMD: ${{ steps.build.outputs.BUILD_CMD }}
        run: python3 tools/AirysDark-AI_builder.py || true

      - name: Upload AI patch (if any)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: android-ai-patch
          path: .pre_ai_fix.patch
          if-no-files-found: ignore
          retention-days: 7

      - name: Check for changes
        id: diff
        run: |
          git add -A
          if git diff --cached --quiet; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else:
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Pin git remote with token (FG-PAT)
        if: ${{ steps.diff.outputs.changed == 'true' }}
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          REPO_SLUG: ${{ github.repository }}
        run: |
          set -euxo pipefail
          git config --local --name-only --get-regexp '^http\.https://github\.com/\.extraheader$' >/dev/null 2>&1 && \
            git config --local --unset-all http.https://github.com/.extraheader || true
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
          git remote set-url origin "https://x-access-token:${BOT_TOKEN}@github.com/${REPO_SLUG}.git"
          git config --global url."https://x-access-token:${BOT_TOKEN}@github.com/".insteadOf "https://github.com/"
          git remote -v

      - name: Create PR with AI fixes
        if: ${{ steps.diff.outputs.changed == 'true' }}
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.BOT_TOKEN }}
          branch: ai/airysdark-ai-autofix-android
          commit-message: "chore: AirysDark-AI auto-fix (android)"
          title: "AirysDark-AI: automated build fix (android)"
          body: |
            This PR was opened automatically by a generated workflow after a failed build.
            - Build command: ${{ steps.build.outputs.BUILD_CMD }}
            - Captured the failing build log
            - Proposed a minimal fix via AI
            - Committed the changes for review
          labels: automation, ci
""".lstrip("\n").replace("__BUILD_CMD__", build_cmd)
    (WF / "AirysDark-AI_android.yml").write_text(yml)

def probe_ai():
    log_lines = []
    def log(x): 
        print(x)
        log_lines.append(x)

    # Build prompt from repo context + detector inputs
    ctx = load_probe_inputs()
    prompt = build_prompt(ctx)

    # 1) Try OpenAI
    build_cmd = None
    try:
        out = call_openai(prompt)
        candidate = parse_build_cmd_from_ai(out)
        if candidate:
            build_cmd = candidate
            log("[probe] OpenAI produced a build command.")
    except Exception as e:
        log(f"[probe] OpenAI error: {e}")

    # 2) Try llama.cpp
    if not build_cmd:
        try:
            out = call_llama(prompt)
            candidate = parse_build_cmd_from_ai(out)
            if candidate:
                build_cmd = candidate
                log("[probe] llama.cpp produced a build command.")
        except Exception as e:
            log(f"[probe] llama.cpp error: {e}")

    # 3) Heuristic fallback
    if not build_cmd:
        build_cmd = heuristic_fallback()
        log("[probe] Falling back to heuristic build command.")

    # Normalize to include --stacktrace
    if " --stacktrace" not in build_cmd:
        build_cmd = build_cmd.strip() + " --stacktrace"

    # Write final workflow and probe artifacts
    write_final_workflow(build_cmd)
    (TOOLS / "android_probe.json").write_text(json.dumps({"build_cmd": build_cmd}, indent=2))
    (TOOLS / "android_probe.log").write_text("\n".join(log_lines))

    # Print for GHA output capture
    print(f"BUILD_CMD={build_cmd}")

def main():
    # Only implemented probe-ai for now
    if len(sys.argv) >= 3 and sys.argv[1] == "--mode" and sys.argv[2] == "probe-ai":
        return probe_ai()
    print("Usage: AirysDark-AI_android.py --mode probe-ai")
    return 2

if __name__ == "__main__":
    sys.exit(main())