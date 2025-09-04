#!/usr/bin/env python3
# AirysDark-AI_detector.py
# Detects project type(s) and generates ready-to-run workflows:
#   .github/workflows/AirysDark-AI_<type>.yml
#
# Each generated workflow:
# - triggers on push / PR / manual dispatch (Run button) and is reusable (workflow_call)
# - installs language/toolchain where needed
# - ensures tools/ has the AI scripts (fetch from AirysDark-AI org if missing)
# - runs the build, captures build.log
# - if it fails, runs the AI autobuilder (OpenAI → llama.cpp fallback)
# - opens a PR with changes using a PAT (secrets.BOT_TOKEN) with repo+workflow scopes

import os
import pathlib
import textwrap
import sys

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- Helpers ----------
def exists_any(patterns):
    for pat in patterns:
        if list(ROOT.glob(pat)):
            return True
    return False

def detect_types():
    """
    Prioritize Android/Gradle. Generate CMake only if there is a *top-level*
    CMakeLists.txt and NO Gradle (avoids Android+NDK double-generation).
    """
    types = []

    has_gradle = (ROOT / "gradlew").exists() or exists_any([
        "**/gradlew", "**/build.gradle*", "**/settings.gradle*"
    ])
    if has_gradle:
        types.append("android")

    has_top_cmake = (ROOT / "CMakeLists.txt").exists()
    if has_top_cmake and not has_gradle:
        types.append("cmake")

    if (ROOT / "package.json").exists():
        types.append("node")
    if (ROOT / "setup.py").exists() or (ROOT / "pyproject.toml").exists():
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

    # de-dupe while preserving order
    seen = set()
    dedup = []
    for t in types:
        if t not in seen:
            dedup.append(t)
            seen.add(t)
    return dedup

# ---------- Build commands ----------
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

# ---------- Type-specific setup ----------
def setup_steps(ptype: str) -> str:
    if ptype == "android":
        return textwrap.dedent("""
          - uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: "17"
          - uses: android-actions/setup-android@v3
          - run: yes | sdkmanager --licenses
          - run: sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
        """)
    if ptype == "node":
        return textwrap.dedent("""
          - uses: actions/setup-node@v4
            with: { node-version: "20" }
        """)
    if ptype == "rust":
        return textwrap.dedent("""
          - uses: dtolnay/rust-toolchain@stable
          - run: rustc --version && cargo --version
        """)
    if ptype == "dotnet":
        return textwrap.dedent("""
          - uses: actions/setup-dotnet@v4
            with: { dotnet-version: "8.0.x" }
          - run: dotnet --info
        """)
    if ptype == "maven":
        return textwrap.dedent("""
          - uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: "17"
          - run: mvn --version
        """)
    if ptype == "flutter":
        return textwrap.dedent("""
          - uses: subosito/flutter-action@v2
            with: { flutter-version: "3.22.0" }
          - run: flutter --version
        """)
    if ptype == "go":
        return textwrap.dedent("""
          - uses: actions/setup-go@v5
            with: { go-version: "1.22" }
          - run: go version
        """)
    # cmake/python/unknown don't need extra setup beyond setup-python
    return ""

# ---------- Workflow writer (includes Run button + reusable + PAT PR) ----------
def write_workflow(ptype: str, cmd: str):
    setup = setup_steps(ptype)
    yaml = f"""
    name: AirysDark-AI — {ptype.capitalize()} (generated)

    on:
      push:
      pull_request:
      workflow_dispatch:
      workflow_call:

    jobs:
      build:
        runs-on: ubuntu-latest
        permissions:
          contents: write
          pull-requests: write
        steps:
          - uses: actions/checkout@v4

          - uses: actions/setup-python@v5
            with: {{ python-version: "3.11" }}
          - run: pip install requests

{setup if setup.strip() else ""}\
          - name: Ensure AirysDark-AI tools
            shell: bash
            run: |
              set -euo pipefail
              mkdir -p tools
              BASE_URL="https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools"
              [ -f tools/AirysDark-AI_detector.py ] || curl -fL "$BASE_URL/AirysDark-AI_detector.py" -o tools/AirysDark-AI_detector.py
              [ -f tools/AirysDark-AI_builder.py ]  || curl -fL "$BASE_URL/AirysDark-AI_builder.py"  -o tools/AirysDark-AI_builder.py
              ls -la tools

          - name: Build (capture)
            id: build
            shell: bash
            run: |
              set -euxo pipefail
              CMD="{cmd}"
              echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"
              set +e; bash -lc "$CMD" | tee build.log; EXIT=$?; set -e
              echo "EXIT_CODE=$EXIT" >> "$GITHUB_OUTPUT"
              [ -f build.log ] || echo "(no build output captured)" > build.log
              exit 0
            continue-on-error: true

          # --- AI auto-fix block (OpenAI → llama fallback) ---
          - name: Build llama.cpp (CMake, no CURL)
            run: |
              git clone --depth=1 https://github.com/ggml-org/llama.cpp
              cd llama.cpp
              cmake -S . -B build -D CMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
              cmake --build build -j
              echo "LLAMA_CPP_BIN=$PWD/build/bin/llama-cli" >> $GITHUB_ENV

          - name: Fetch GGUF model (TinyLlama)
            run: |
              mkdir -p models
              curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \\
                https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

          - name: Attempt AI auto-fix (OpenAI → llama fallback)
            if: always() && steps.build.outputs.EXIT_CODE != '0'
            env:
              PROVIDER: openai
              FALLBACK_PROVIDER: llama
              OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}
              OPENAI_MODEL: ${{{{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}}}
              MODEL_PATH: models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
              AI_BUILDER_ATTEMPTS: "3"
              BUILD_CMD: ${{{{ steps.build.outputs.BUILD_CMD }}}}
            run: python3 tools/AirysDark-AI_builder.py || true

          # --- Only open PR if changes exist (use PAT with workflow scope) ---
          - name: Check for changes
            id: diff
            run: |
              git add -A
              if git diff --cached --quiet; then
                echo "changed=false" >> "$GITHUB_OUTPUT"
              else
                echo "changed=true" >> "$GITHUB_OUTPUT"
              fi

          - name: Create PR with AI fixes
            if: steps.diff.outputs.changed == 'true'
            uses: peter-evans/create-pull-request@v6
            with:
              token: ${{{{ secrets.BOT_TOKEN }}}}   # PAT with repo + workflow scopes
              branch: ai/airysdark-ai-autofix
              commit-message: "chore: AirysDark-AI auto-fix"
              title: "AirysDark-AI: automated build fix"
              body: |
                This PR was opened automatically by a generated workflow after a failed build.
                - Captured the failing build log
                - Proposed a minimal fix via AI
                - Committed the changes for review
              labels: automation, ci
    """
    out = WF / f"AirysDark-AI_{ptype}.yml"
    out.write_text(textwrap.dedent(yaml))
    print(f"✅ Generated: {out.name}")

# ---------- Main ----------
def main():
    types = detect_types()
    for t in types:
        cmd = BUILD_CMDS.get(t, BUILD_CMDS["unknown"])
        write_workflow(t, cmd)
    print(f"Done. Generated {len(types)} workflow(s) in {WF}")

if __name__ == "__main__":
    sys.exit(main())