#!/usr/bin/env python3
# AirysDark-AI_detector.py
# - Recursive detection for all project types (whole repo)
# - Generates one workflow per detected type:
#     .github/workflows/AirysDark-AI_<type>.yml
# - Linux type supports Makefile and Meson/Ninja automatically

import os
import pathlib
import textwrap
import sys

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- Helpers ----------
def exists_any(patterns):
    """Return True if any glob pattern matches anywhere in repo (recursive)."""
    for pat in patterns:
        if list(ROOT.glob(pat)):
            return True
    return False

def detect_types():
    types = []
    # android / gradle
    if exists_any(["**/gradlew", "**/build.gradle*", "**/settings.gradle*"]):
        types.append("android")
    # cmake
    if exists_any(["**/CMakeLists.txt"]):
        types.append("cmake")
    # node
    if exists_any(["**/package.json"]):
        types.append("node")
    # python
    if exists_any(["**/setup.py", "**/pyproject.toml"]):
        types.append("python")
    # rust
    if exists_any(["**/Cargo.toml"]):
        types.append("rust")
    # dotnet
    if exists_any(["**/*.sln", "**/*.csproj", "**/*.fsproj"]):
        types.append("dotnet")
    # maven
    if exists_any(["**/pom.xml"]):
        types.append("maven")
    # flutter
    if exists_any(["**/pubspec.yaml"]):
        types.append("flutter")
    # go
    if exists_any(["**/go.mod"]):
        types.append("go")
    # linux: treat Makefiles, meson.build, *.mk, or a linux/ dir as a linux build
    if exists_any(["**/Makefile", "**/*.mk", "**/meson.build", "linux", "linux/**"]):
        types.append("linux")

    if not types:
        types.append("unknown")

    # de-dupe while preserving order
    seen, deduped = set(), []
    for t in types:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    return deduped

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
    # Linux: Makefile (root or first found) → make; else Meson/Ninja (root or first found)
    "linux": (
        "bash -lc '"
        "if [ -f Makefile ]; then "
        "  make -j; "
        "else "
        "  set -e; "
        "  d=$(git ls-files | grep -E \"(^|/)Makefile$\" | head -n1 | xargs -I{} dirname {}); "
        "  if [ -n \"$d\" ]; then "
        "    make -C \"$d\" -j; "
        "  elif [ -f meson.build ]; then "
        "    (meson setup build --wipe || true); meson setup build || true; ninja -C build; "
        "  else "
        "    d=$(git ls-files | grep -E \"(^|/)meson.build$\" | head -n1 | xargs -I{} dirname {}); "
        "    if [ -n \"$d\" ]; then "
        "      (cd \"$d\" && (meson setup build --wipe || true); meson setup build || true; ninja -C build); "
        "    else "
        "      echo \"No Makefile or meson.build found; cannot run linux build\"; exit 1; "
        "    fi; "
        "  fi; "
        "fi'"
    ),
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
    if ptype == "linux":
        # ensure meson/ninja are available when meson.build is present
        return textwrap.dedent("""
          - name: Install Meson & Ninja (Linux only)
            run: |
              sudo apt-get update
              sudo apt-get install -y meson ninja-build pkg-config
        """)
    # cmake/python/unknown don't need extra setup beyond setup-python
    return ""

# ---------- Workflow writer ----------
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
              else:
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
        write_workflow(t, BUILD_CMDS[t])
    print(f"Done. Generated {len(types)} workflow(s) in {WF}")

if __name__ == "__main__":
    sys.exit(main())