#!/usr/bin/env python3
# AirysDark-AI_detector.py
#
# Scans *all files/dirs* in repo to detect build systems.
# Adds CMake content-aware detection to also flag "linux" when the CMakeLists looks desktop-ish.
# Writes one PROBE workflow per detected type: .github/workflows/AirysDark-AI_prob_<type>.yml

import os
import pathlib
import textwrap
import sys

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- Full-repo scan ----------
def scan_all_files():
    files = []
    for root, dirs, filenames in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in filenames:
            p = pathlib.Path(root) / fn
            try:
                rel = p.relative_to(ROOT)
            except Exception:
                rel = p
            files.append((fn.lower(), rel))
    return files

def read_text_safe(p: pathlib.Path) -> str:
    try:
        return (ROOT / p).read_text(errors="ignore")
    except Exception:
        return ""

# ---------- CMake classifier ----------
ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk", "cmake_android", "gradle", "externalnativebuild",
    "find_library(log)", "log-lib", "loglib"
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread", "x11", "wayland", "gtk", "qt",
    "set(cmake_system_name linux"
)

def cmakelists_flavor(cm_txt: str) -> str:
    t = cm_txt.lower()
    # Any explicit Android/NDK signal?
    if any(h in t for h in ANDROID_HINTS):
        return "android"
    # Strong desktop-ish signals?
    if any(h in t for h in DESKTOP_HINTS):
        return "desktop"
    # Default bias: treat as desktop unless clearly Android
    return "desktop"

def detect_types():
    files = scan_all_files()
    fnames = [n for n, _ in files]
    rels   = [str(p).lower() for _, p in files]

    types = []

    # Android / Gradle
    if ("gradlew" in fnames) or any("build.gradle" in n or "settings.gradle" in n for n in fnames):
        types.append("android")

    # CMake (content-aware -> may also flag linux)
    cmake_paths = [p for (n, p) in files if n == "cmakelists.txt"]
    if cmake_paths:
        types.append("cmake")
        # Inspect each CMakeLists; if any looks desktop, also add linux
        for p in cmake_paths:
            txt = read_text_safe(p)
            flavor = cmakelists_flavor(txt)
            if flavor == "desktop" and "linux" not in types:
                types.append("linux")

    # Linux umbrella (Make / Meson / any *.mk) — kept as before
    if "makefile" in fnames or "gnumakefile" in fnames or "meson.build" in fnames or any(r.endswith(".mk") for r in rels):
        if "linux" not in types:
            types.append("linux")

    # Node
    if "package.json" in fnames:
        types.append("node")
    # Python
    if "pyproject.toml" in fnames or "setup.py" in fnames:
        types.append("python")
    # Rust
    if "cargo.toml" in fnames:
        types.append("rust")
    # .NET
    if any(r.endswith(".sln") or r.endswith(".csproj") or r.endswith(".fsproj") for r in rels):
        types.append("dotnet")
    # Maven
    if "pom.xml" in fnames:
        types.append("maven")
    # Flutter
    if "pubspec.yaml" in fnames:
        types.append("flutter")
    # Go
    if "go.mod" in fnames:
        types.append("go")
    # Bazel
    if any(n in ("workspace", "workspace.bazel", "module.bazel") for n in fnames) or \
       any(os.path.basename(r) in ("build", "build.bazel") for r in rels):
        types.append("bazel")
    # SCons
    if "sconstruct" in fnames or "sconscript" in fnames:
        types.append("scons")
    # Ninja (direct)
    if "build.ninja" in fnames:
        types.append("ninja")

    if not types:
        types.append("unknown")

    # de-dupe preserve order
    seen, out = set(), []
    for t in types:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

# ---------- Type-specific setup (embedded into final workflow) ----------
def setup_steps_inline(ptype: str) -> str:
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
        return textwrap.dedent("""
          - name: Install Meson & Ninja (Linux only)
            run: |
              sudo apt-get update
              sudo apt-get install -y meson ninja-build pkg-config
        """)
    if ptype == "bazel":
        return textwrap.dedent("""
          - uses: bazelbuild/setup-bazelisk@v3
        """)
    if ptype == "scons":
        return textwrap.dedent("""
          - name: Install SCons
            run: |
              sudo apt-get update
              sudo apt-get install -y scons
        """)
    if ptype == "ninja":
        return textwrap.dedent("""
          - name: Ensure Ninja
            run: |
              sudo apt-get update
              sudo apt-get install -y ninja-build
        """)
    # cmake/python/unknown: setup-python only
    return ""

# ---------- PROBE workflow generator (unchanged from your latest) ----------
def write_probe_workflow_for_type(ptype: str):
    setup_inline = setup_steps_inline(ptype)

    yaml = f"""
    name: AirysDark-AI — Probe {ptype.capitalize()}

    on:
      workflow_dispatch:

    permissions:
      contents: write
      pull-requests: write

    jobs:
      probe:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
            with: {{ fetch-depth: 0 }}

          - uses: actions/setup-python@v5
            with: {{ python-version: "3.11" }}
          - run: pip install requests

          - name: Ensure AirysDark-AI tools (detector, probe, builder)
            shell: bash
            run: |
              set -euo pipefail
              mkdir -p tools
              BASE_URL="https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools"
              curl -fL "$BASE_URL/AirysDark-AI_detector.py" -o tools/AirysDark-AI_detector.py
              curl -fL "$BASE_URL/AirysDark-AI_probe.py"     -o tools/AirysDark-AI_probe.py
              curl -fL "$BASE_URL/AirysDark-AI_builder.py"  -o tools/AirysDark-AI_builder.py
              ls -la tools

          - name: Probe build command
            id: probe
            shell: bash
            run: |
              set -euxo pipefail
              python3 tools/AirysDark-AI_probe.py --type "{ptype}" | tee /tmp/probe.out
              CMD=$(grep -E '^BUILD_CMD=' /tmp/probe.out | sed 's/^BUILD_CMD=//')
              echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"

          - name: Generate final workflow .github/workflows/AirysDark-AI_{ptype}.yml
            shell: bash
            env:
              BUILD_CMD: "${{{{ steps.probe.outputs.BUILD_CMD }}}}"
            run: |
              set -euo pipefail
              mkdir -p .github/workflows
              cat > .github/workflows/AirysDark-AI_{ptype}.yml <<'YAML'
              name: AirysDark-AI — {ptype.capitalize()} (generated)

              on:
                push:
                pull_request:
                workflow_dispatch:

              jobs:
                build:
                  runs-on: ubuntu-latest
                  permissions:
                    contents: write
                    pull-requests: write
                  steps:
                    - uses: actions/checkout@v4
                      with: {{ fetch-depth: 0 }}

                    - uses: actions/setup-python@v5
                      with: {{ python-version: "3.11" }}
                    - run: pip install requests

{setup_inline if setup_inline.strip() else ""}\
                    - name: Ensure AirysDark-AI tools (detector, builder)
                      shell: bash
                      run: |
                        set -euo pipefail
                        mkdir -p tools
                        BASE_URL="https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools"
                        [ -f tools/AirysDark-AI_detector.py ] || curl -fL "$BASE_URL/AirysDark-AI_detector.py" -o tools/AirysDark-AI_detector.py
                        [ -f tools/AirysDark-AI_builder.py ]  || curl -fL "$BASE_URL/AirysDark-AI_builder.py"  -o tools/AirysDark-AI_builder.py

                    - name: Build (capture)
                      id: build
                      shell: bash
                      run: |
                        set -euxo pipefail
                        CMD="$BUILD_CMD"
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
                        name: {ptype}-build-log
                        path: build.log
                        if-no-files-found: warn
                        retention-days: 7

                    # --- AI auto-fix (OpenAI → llama.cpp) ---
                    - name: Build llama.cpp (CMake, no CURL, in temp)
                      if: always() && steps.build.outputs.EXIT_CODE != '0'
                      run: |
                        set -euxo pipefail
                        TMP="${{{{ runner.temp }}}}"
                        cd "$TMP"
                        rm -rf llama.cpp
                        git clone --depth=1 https://github.com/ggml-org/llama.cpp
                        cd llama.cpp
                        cmake -S . -B build -D CMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF
                        cmake --build build -j
                        echo "LLAMA_CPP_BIN=$PWD/build/bin/llama-cli" >> $GITHUB_ENV

                    - name: Fetch GGUF model (TinyLlama)
                      if: always() && steps.build.outputs.EXIT_CODE != '0'
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

                    - name: Upload AI patch (if any)
                      if: always()
                      uses: actions/upload-artifact@v4
                      with:
                        name: {ptype}-ai-patch
                        path: .pre_ai_fix.patch
                        if-no-files-found: ignore
                        retention-days: 7

                    - name: Upload build artifacts
                      if: always()
                      uses: actions/upload-artifact@v4
                      with:
                        name: {ptype}-artifacts
                        if-no-files-found: ignore
                        retention-days: 7
                        path: |
                          build/**
                          out/**
                          dist/**
                          target/**
                          **/build/**
                          **/out/**
                          **/dist/**
                          **/target/**
                          **/*.so
                          **/*.a
                          **/*.dll
                          **/*.dylib
                          **/*.exe
                          **/*.bin
                          **/outputs/**/*.apk
                          **/outputs/**/*.aab
                          **/*.whl

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
                        token: ${{{{ secrets.BOT_TOKEN }}}}
                        branch: ai/airysdark-ai-autofix-{ptype}
                        commit-message: "chore: AirysDark-AI auto-fix ({ptype})"
                        title: "AirysDark-AI: automated build fix ({ptype})"
                        body: |
                          This PR was opened automatically by a generated workflow after a failed build.
                          - Build command: ${{{{ steps.build.outputs.BUILD_CMD }}}}
                          - Captured the failing build log
                          - Proposed a minimal fix via AI
                          - Committed the changes for review
                        labels: automation, ci
              YAML

          - name: Create PR with generated final workflow
            uses: peter-evans/create-pull-request@v6
            with:
              token: ${{ secrets.BOT_TOKEN }}
              branch: ai/airysdark-ai-workflow-{ptype}
              commit-message: "chore: add AirysDark-AI_{ptype} workflow (probed)"
              title: "AirysDark-AI: add {ptype} workflow (from probe)"
              body: |
                This PR adds the final {ptype} AI build workflow, generated by the probe run.
                - Probed command: ${{ steps.probe.outputs.BUILD_CMD }}
                - Next: merge this PR, then run **AirysDark-AI — {ptype.capitalize()} (generated)**
              labels: automation, ci
    """
    (WF / f"AirysDark-AI_prob_{ptype}.yml").write_text(textwrap.dedent(yaml))
    print(f"✅ Generated: AirysDark-AI_prob_{ptype}.yml")

# ---------- Main ----------
def main():
    types = detect_types()
    for t in types:
        write_probe_workflow_for_type(t)
    print(f"Done. Generated {len(types)} PROBE workflow(s) in {WF}")

if __name__ == "__main__":
    sys.exit(main())