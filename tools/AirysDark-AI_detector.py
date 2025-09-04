#!/usr/bin/env python3
# AirysDark-AI_detector.py â€ deep detector with folder-name + content heuristics
#
# Recursively scans the ENTIRE repo:
#   â€¢ Filename signals (gradlew, CMakeLists.txt, Makefile, *.mk, meson.build, WORKSPACE, etc.)
#   â€¢ Content signals (README/*.md/*.txt/docs/**) for build commands/keywords
#   â€¢ Reads CMakeLists.txt to decide Android vs Desktop/Linux
#   â€¢ Folder-name signals: if any path segment equals "linux", "windows", "android"
#
# Generates one PROBE workflow per detected type:
#   .github/workflows/AirysDark-AI_prob_<type>.yml
#
# Types supported:
#   android, cmake, linux, node, python, rust, dotnet, maven, flutter, go,
#   bazel, scons, ninja, windows, unknown

import os
import pathlib
import re
import sys
import textwrap
from typing import List, Tuple, Set

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
DOC_DIR_HINTS = ("docs",)
MAX_READ_BYTES = 200_000
MAX_FILES_TO_READ = 400

def scan_all_files() -> List[Tuple[str, pathlib.Path]]:
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

def safe_read_text(p: pathlib.Path) -> str:
    try:
        raw = (ROOT / p).read_bytes()
        if len(raw) > MAX_READ_BYTES:
            raw = raw[:MAX_READ_BYTES]
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def collect_text_corpus(files: List[Tuple[str, pathlib.Path]]) -> str:
    picked: List[pathlib.Path] = []
    # README*
    for name, rel in files:
        if pathlib.Path(rel.name.lower()).name.startswith("readme"):
            picked.append(rel)
    # text extensions
    for name, rel in files:
        if len(picked) >= MAX_FILES_TO_READ:
            break
        if pathlib.Path(name).suffix in TEXT_EXTS:
            picked.append(rel)
    # docs/**
    for name, rel in files:
        if len(picked) >= MAX_FILES_TO_READ:
            break
        parts = [p.lower() for p in pathlib.Path(rel).parts]
        if any(h in parts for h in DOC_DIR_HINTS) and pathlib.Path(name).suffix in TEXT_EXTS:
            picked.append(rel)

    seen: Set[str] = set()
    ordered: List[pathlib.Path] = []
    for p in picked:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(p)

    chunks: List[str] = []
    for p in ordered[:MAX_FILES_TO_READ]:
        chunks.append(safe_read_text(p))
    return "\n\n".join(chunks).lower()

# -------- CMake classifier (Android vs Desktop) --------
ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk", "cmake_android",
    "externalnativebuild", "gradle", "find_library(log)", "log-lib", "loglib"
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread",
    "x11", "wayland", "gtk", "qt", "set(cmake_system_name linux"
)
def classify_cmakelists_text(txt: str) -> str:
    t = txt.lower()
    if any(h in t for h in ANDROID_HINTS):
        return "android"
    if any(h in t for h in DESKTOP_HINTS):
        return "desktop"
    return "desktop"

def has_dir_segment(files: List[Tuple[str, pathlib.Path]], segment: str) -> bool:
    seg = segment.lower()
    for _, rel in files:
        parts = [p.lower() for p in pathlib.Path(rel).parts]
        if seg in parts:
            return True
    return False

BUILD_CMD_PATTERNS = [
    r"\bcmake\s+(-S\s+\S+|\.)\s+-B\s+\S+",
    r"\bmake(\s+-C\s+\S+)?\b",
    r"\bmeson\s+setup\b",
    r"\bninja(\s+-C\s+\S+)?\b",
    r"\b(?:\.\/)?gradlew\s+[\w:\-]+",
    r"\bnpm\s+(ci|install)\b|\bnpm\s+run\s+build\b",
    r"\bpip\s+install\b|\bpytest\b|\bpython\s+-m\s+pytest\b",
    r"\bcargo\s+build\b",
    r"\bdotnet\s+build\b",
    r"\bmvn\b|\bmaven\b",
    r"\bflutter\s+build\b",
    r"\bgo\s+build\b",
    r"\bbazel(isk)?\s+(build|test)\b",
    r"\bscons\b",
]
def text_hints_detect_types(corpus: str) -> Set[str]:
    found: Set[str] = set()
    keymap = [
        ("android", ["gradle", "gradlew", "android", "externalnativebuild", "aab", "apk"]),
        ("cmake",   ["cmake"]),
        ("linux",   ["make", "meson", "ninja", ".mk"]),
        ("node",    ["npm", "yarn", "pnpm", "package.json"]),
        ("python",  ["pip install", "pytest", "pyproject.toml", "setup.py"]),
        ("rust",    ["cargo build", "cargo test", "cargo"]),
        ("dotnet",  ["dotnet build", ".sln", ".csproj", "nuget", "windows"]),
        ("maven",   ["mvn ", "maven"]),
        ("flutter", ["flutter build", "dart", "pubspec.yaml"]),
        ("go",      ["go build", "go.mod"]),
        ("bazel",   ["bazel build", "bazel test", "workspace", "build.bazel"]),
        ("scons",   ["scons"]),
        ("ninja",   ["build.ninja", "ninja -C"]),
        ("windows", ["msbuild", "vcxproj", "win32", "windows"]),
    ]
    for t, keys in keymap:
        if any(k in corpus for k in keys):
            found.add(t)
    for pat in BUILD_CMD_PATTERNS:
        if re.search(pat, corpus):
            if "cmake" in pat: found.add("cmake")
            if "make" in pat or "meson" in pat or "ninja" in pat: found.add("linux")
            if "gradle" in pat or "gradlew" in pat: found.add("android")
            if "npm" in pat: found.add("node")
            if "pip" in pat or "pytest" in pat: found.add("python")
            if "cargo" in pat: found.add("rust")
            if "dotnet" in pat: found.add("dotnet"); found.add("windows")
            if "mvn" in pat or "maven" in pat: found.add("maven")
            if "flutter" in pat: found.add("flutter")
            if "go build" in pat: found.add("go")
            if "bazel" in pat: found.add("bazel")
            if "scons" in pat: found.add("scons")
    return found

def detect_types() -> List[str]:
    files = scan_all_files()
    fnames = [n for n, _ in files]
    rels   = [str(p).lower() for _, p in files]

    detected: List[str] = []

    # Folder-name signals
    if has_dir_segment(files, "linux"):   detected.append("linux")
    if has_dir_segment(files, "windows"): detected.append("windows")
    if has_dir_segment(files, "android"): detected.append("android")

    # Filename-based
    if ("gradlew" in fnames) or any("build.gradle" in n or "settings.gradle" in n for n in fnames):
        if "android" not in detected: detected.append("android")

    cmake_paths = [p for (n, p) in files if n == "cmakelists.txt"]
    if cmake_paths and "cmake" not in detected:
        detected.append("cmake")

    if "makefile" in fnames or "gnumakefile" in fnames or "meson.build" in fnames or any(r.endswith(".mk") for r in rels):
        if "linux" not in detected: detected.append("linux")

    if "package.json" in fnames: detected.append("node")
    if "pyproject.toml" in fnames or "setup.py" in fnames: detected.append("python")
    if "cargo.toml" in fnames: detected.append("rust")
    if any(r.endswith(".sln") or r.endswith(".csproj") or r.endswith(".fsproj") for r in rels):
        detected.append("dotnet"); detected.append("windows")
    if "pom.xml" in fnames: detected.append("maven")
    if "pubspec.yaml" in fnames: detected.append("flutter")
    if "go.mod" in fnames: detected.append("go")
    if any(n in ("workspace", "workspace.bazel", "module.bazel") for n in fnames) or \
       any(os.path.basename(r) in ("build", "build.bazel") for r in rels):
        detected.append("bazel")
    if "sconstruct" in fnames or "sconscript" in fnames: detected.append("scons")
    if "build.ninja" in fnames: detected.append("ninja")

    # Docs content
    corpus = collect_text_corpus(files)
    content_types = text_hints_detect_types(corpus)
    for t in content_types:
        if t not in detected:
            detected.append(t)

    # CMake content-aware classification: add linux if desktop-ish
    if cmake_paths:
        for p in cmake_paths:
            txt = safe_read_text(p)
            if classify_cmakelists_text(txt) == "desktop" and "linux" not in detected:
                detected.append("linux")

    if not detected:
        detected.append("unknown")

    # De-dupe preserving order
    seen, out = set(), []
    for t in detected:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def runner_for(ptype: str) -> str:
    if ptype in ("windows", "dotnet"):
        return "windows-latest"
    return "ubuntu-latest"

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
    if ptype in ("dotnet", "windows"):
        return textwrap.dedent("""
          - name: .NET info
            run: dotnet --info
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

def write_probe_workflow_for_type(ptype: str):
    setup_inline = setup_steps_inline(ptype)
    runs_on = runner_for(ptype)

    yaml = f"""
    name: AirysDark-AI â€ Probe {ptype.capitalize()}

    on:
      workflow_dispatch:

    permissions:
      contents: write
      pull-requests: write

    jobs:
      probe:
        runs-on: {runs_on}
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

{setup_inline if setup_inline.strip() else ""}\
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
              BUILD_CMD: "${{ steps.probe.outputs.BUILD_CMD }}"
            run: |
              set -euo pipefail
              mkdir -p .github/workflows
              cat > .github/workflows/AirysDark-AI_{ptype}.yml <<'YAML'
              name: AirysDark-AI â€ {ptype.capitalize()} (generated)

              on:
                push:
                pull_request:
                workflow_dispatch:

              jobs:
                build:
                  runs-on: {runs_on}
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

                    # --- AI auto-fix (OpenAI â llama.cpp) ---
                    - name: Build llama.cpp (CMake, no CURL, in temp)
                      if: always() && steps.build.outputs.EXIT_CODE != '0'
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
                      if: always() && steps.build.outputs.EXIT_CODE != '0'
                      run: |
                        mkdir -p models
                        curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \\
                          https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

                    - name: Attempt AI auto-fix (OpenAI â llama fallback)
                      if: always() && steps.build.outputs.EXIT_CODE != '0'
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
                        token: ${{ secrets.BOT_TOKEN }}
                        branch: ai/airysdark-ai-autofix-{ptype}
                        commit-message: "chore: AirysDark-AI auto-fix ({ptype})"
                        title: "AirysDark-AI: automated build fix ({ptype})"
                        body: |
                          This PR was opened automatically by a generated workflow after a failed build.
                          - Build command: ${{ steps.build.outputs.BUILD_CMD }}
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
                - Next: merge this PR, then run **AirysDark-AI â€ {ptype.capitalize()} (generated)**
              labels: automation, ci
    """
    (WF / f"AirysDark-AI_prob_{ptype}.yml").write_text(textwrap.dedent(yaml))
    print(f"â Generated: AirysDark-AI_prob_{ptype}.yml")

def main():
    types = detect_types()
    for t in types:
        write_probe_workflow_for_type(t)
    print(f"Done. Generated {len(types)} PROBE workflow(s) in {WF}")

if __name__ == "__main__":
    sys.exit(main())