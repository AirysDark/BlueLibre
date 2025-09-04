#!/usr/bin/env python3
import os, pathlib, textwrap, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- Helpers ----------
def exists_any(patterns):
    for pat in patterns:
        if list(ROOT.glob(pat)):
            return True
    return False

def detect_types():
    types = []
    if (ROOT / "gradlew").exists() or exists_any(["android/**/gradlew", "**/build.gradle*", "**/settings.gradle*"]):
        types.append("android")
    if (ROOT / "CMakeLists.txt").exists() or exists_any(["**/CMakeLists.txt"]):
        types.append("cmake")
    if (ROOT / "package.json").exists():
        types.append("node")
    if (ROOT / "pyproject.toml").exists() or (ROOT / "setup.py").exists():
        types.append("python")
    if (ROOT / "Cargo.toml").exists():
        types.append("rust")
    if exists_any(["*.sln", "**/*.csproj", "**/*.fsproj"]):
        types.append("dotnet")
    if (ROOT / "pom.xml").exists():
        types.append("maven")
    if (ROOT / "pubspec.yaml").exists():
        types.append("flutter")
    if (ROOT / "go.mod").exists():
        types.append("go")
    if not types:
        types.append("unknown")
    return types

BUILD_CMDS = {
    "android": "./gradlew assembleDebug --stacktrace",
    "cmake":   "cmake -S . -B build && cmake --build build -j",
    "node":    "npm ci && npm run build --if-present",
    "python":  "pip install -e . && pytest || python -m pytest",
    "rust":    "cargo build --locked --all-targets --verbose",
    "dotnet":  "dotnet restore && dotnet build -c Release",
    "maven":   "mvn -B package --file pom.xml",
    "flutter": "flutter build apk --debug",
    "go":      "go build ./...",
    "unknown": "echo 'No build system detected' && exit 1",
}

# ---------- Common blocks ----------
HEADER = """name: AirysDark-AI — {title}

on:
  workflow_dispatch:
  push:
  pull_request:
  workflow_call: {{}}

permissions:
  contents: write
  pull-requests: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {{ fetch-depth: 0 }}

      - uses: actions/setup-python@v5
        with: {{ python-version: "3.11" }}
      - run: pip install requests
"""

CACHES_COMMON = """      - name: Cache llama.cpp build
        id: cache-llama
        uses: actions/cache@v4
        with:
          path: llama.cpp/build
          key: llama-build-${{ runner.os }}-v1

      - name: Build llama.cpp (CMake, no CURL)
        if: steps.cache-llama.outputs.cache-hit != 'true'
        run: |
          git clone --depth=1 https://github.com/ggml-org/llama.cpp
          cd llama.cpp
          cmake -S . -B build -D CMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
          cmake --build build -j
          echo "LLAMA_CPP_BIN=$PWD/build/bin/llama-cli" >> $GITHUB_ENV

      - name: Use cached llama.cpp binary
        if: steps.cache-llama.outputs.cache-hit == 'true'
        run: echo "LLAMA_CPP_BIN=$GITHUB_WORKSPACE/llama.cpp/build/bin/llama-cli" >> $GITHUB_ENV

      - name: Cache TinyLlama model
        id: cache-model
        uses: actions/cache@v4
        with:
          path: models
          key: gguf-tinyllama-1.1b-q4km-v1

      - name: Fetch GGUF model (TinyLlama)
        if: steps.cache-model.outputs.cache-hit != 'true'
        run: |
          mkdir -p models
          curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \            https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
          ls -lh models || true
"""

AI_STEP = """      - name: Configure git identity
        run: |
          git config --global user.name "AirysDark-AI_builder"
          git config --global user.email "AirysDark-AI_builder@users.noreply.github.com"

      - name: Attempt AI auto-fix (OpenAI → llama fallback)
        if: always() && steps.build.outputs.EXIT_CODE != '0'
        env:
          PROVIDER: openai
          FALLBACK_PROVIDER: llama
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}
          MODEL_PATH: models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
          AI_BUILDER_ATTEMPTS: "3"
          BUILD_CMD: ${{ steps.build.outputs.BUILD_CMD }}
          LLAMA_CTX: "4096"
          MAX_PROMPT_TOKENS: "2500"
          AI_LOG_TAIL: "120"
          MAX_FILES_IN_TREE: "80"
          RECENT_DIFF_MAX_CHARS: "3000"
        run: python3 tools/AirysDark-AI_builder.py || true

      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: ai-build-and-fix
          path: |
            build.log
            .pre_ai_fix.patch
            **/build/**/outputs/**
          if-no-files-found: warn

      - name: Check for changes
        id: changes
        run: |
          if [ -n "$(git status --porcelain)" ]; then
            echo "changed=true" >> "$GITHUB_OUTPUT"
          else
            echo "changed=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Create PR with fixes
        if: steps.changes.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.BOT_TOKEN }}
          branch: ai/autofix-${{ github.run_id }}
          title: "AirysDark-AI: build fix"
          body: |
            Automated fix from AirysDark-AirysDark-AI.
            • Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
            • Artifacts include build.log and any proposed patch (.pre_ai_fix.patch)
          commit-message: "AirysDark-AI: apply automatic fix"
          labels: |
            AirysDark-AI
            bot
          add-paths: |
            **/*
"""

def android_block():
    return textwrap.dedent("""      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "17" }
      - uses: android-actions/setup-android@v3
      - run: yes | sdkmanager --licenses
      - run: sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

      - name: Ensure Gradle wrapper (first-run safe)
        shell: bash
        run: |
          set -euxo pipefail
          PROJ="."
          if [ -f "android/settings.gradle" ] || [ -f "android/settings.gradle.kts" ]; then
            PROJ="android"
          elif [ -d "android" ]; then
            PROJ="android"
          fi
          echo "PROJDIR=$PROJ" >> "$GITHUB_OUTPUT"
          cd "$PROJ"
          if [ -f "gradlew" ]; then
            chmod +x gradlew
          else
            gradle wrapper --gradle-version 8.7
            chmod +x gradlew || true
          fi
          ./gradlew --version

      - name: Cache Gradle
        uses: actions/cache@v4
        with:
          path: |
            ~/.gradle/caches
            ~/.gradle/wrapper
          key: gradle-${{ runner.os }}-${{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties', '**/settings.gradle*') }}
          restore-keys: |
            gradle-${{ runner.os }}-
""")

def build_capture(cmd_expr: str):
    # cmd_expr is a shell-safe command string to run
    return textwrap.dedent(f"""      - name: Build (capture)
        id: build
        shell: bash
        run: |
          set -euxo pipefail
          CMD="{cmd_expr}"
          echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"
          set +e; bash -lc "$CMD" | tee build.log; EXIT=$?; set -e
          echo "EXIT_CODE=$EXIT" >> "$GITHUB_OUTPUT"
          [ -s build.log ] || echo "(no build output captured)" > build.log
          exit 0
        continue-on-error: true
""")

def write_workflow(ptype: str, build_cmd: str):
    title = f"{ptype.capitalize()}"
    yaml_parts = [HEADER.format(title=title)]

    # Toolchains / setup per type
    if ptype == "android":
        yaml_parts.append(android_block())
        # Android build runs gradlew from detected folder; prepend 'cd $PROJDIR &&'
        build_cmd_expr = 'bash -lc "cd ${GITHUB_WORKSPACE}/${{ steps.build.outputs.PROJDIR || '' }} && ./gradlew assembleDebug --stacktrace"'
        # But for clarity use BUILD_CMD with cd path captured earlier in Ensure Gradle wrapper:
        build_cmd_expr = 'cd ${GITHUB_WORKSPACE}/${{ steps.build.outputs.PROJDIR || '' }} && ./gradlew assembleDebug --stacktrace'
        yaml_parts.append(build_capture(build_cmd_expr))
    else:
        # Non-android optional toolchains
        if ptype == "cmake":
            yaml_parts.append("""      - name: CMake presence
        run: cmake --version
""")
        if ptype == "node":
            yaml_parts.append("""      - uses: actions/setup-node@v4
        with: { node-version: "20" }
""")
        if ptype == "rust":
            yaml_parts.append("""      - uses: dtolnay/rust-toolchain@stable
""")
        if ptype == "dotnet":
            yaml_parts.append("""      - uses: actions/setup-dotnet@v4
        with: { dotnet-version: "8.0.x" }
""")
        if ptype == "maven":
            yaml_parts.append("""      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: "17" }
""")
        if ptype == "flutter":
            yaml_parts.append("""      - uses: subosito/flutter-action@v2
        with: { flutter-version: "3.22.0" }
""")
        if ptype == "go":
            yaml_parts.append("""      - uses: actions/setup-go@v5
        with: { go-version: "1.22" }
""")
        # Build command
        yaml_parts.append(build_capture(build_cmd))

    # Common caches and AI fix
    yaml_parts.append(CACHES_COMMON)
    yaml_parts.append(AI_STEP)

    out = WF / f"AirysDark-AI_{ptype}.yml"
    out.write_text(textwrap.dedent("""""" + "\n".join(yaml_parts)))
    print(f"✅ Generated: {out}")

def main():
    types = detect_types()
    for t in types:
        write_workflow(t, BUILD_CMDS[t])
    print(f"Done. Generated {len(types)} workflow(s) in {WF}")

if __name__ == "__main__":
    main()
