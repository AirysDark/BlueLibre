#!/usr/bin/env python3
# AirysDark-AI_detector.py (deep scan + safe YAML)
#
# - Walks the entire repo (all subdirs) and reads relevant files.
# - Folder-name hints (linux/android/windows).
# - Android deep detection (manifest, Gradle plugin markers, module layout).
# - CMake content-aware classification (desktop-ish => also flag linux).
# - Emits PROBE workflows ("AirysDark-AI_prob_<type>.yml") with quoted 'on:' and block-style 'with:'.
# - Probe workflow fetches tools, computes BUILD_CMD, writes final workflow, pins remote, opens PRs.
#
# Types: android, cmake, linux, node, python, rust, dotnet, maven, flutter, go, bazel, scons, ninja, unknown

import os
import pathlib
import textwrap
import sys
from typing import Iterable, Tuple, List, Set

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- full repo scan ----------
def scan_all_files() -> List[Tuple[pathlib.Path, pathlib.Path, str]]:
    out: List[Tuple[pathlib.Path, pathlib.Path, str]] = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            ap = pathlib.Path(root) / fn
            try:
                rp = ap.relative_to(ROOT)
            except Exception:
                rp = ap
            out.append((ap, rp, fn.lower()))
    return out

def read_text_lower_safe(path: pathlib.Path) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read()
        try:
            return data.decode("utf-8", errors="ignore").lower()
        except Exception:
            return data.decode("latin-1", errors="ignore").lower()
    except Exception:
        return ""

def any_file_contains(paths: Iterable[pathlib.Path], needles: Iterable[str]) -> bool:
    needles_l = [n.lower() for n in needles]
    for p in paths:
        t = read_text_lower_safe(p)
        if not t:
            continue
        if any(n in t for n in needles_l):
            return True
    return False

def collect_dir_name_hints(files_index: List[Tuple[pathlib.Path, pathlib.Path, str]]) -> Set[str]:
    names: Set[str] = set()
    for _abs, rel, _fn in files_index:
        for part in pathlib.Path(rel).parts:
            names.add(part.lower())
    return names

# ---------- CMake classifier ----------
ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk", "cmake_android",
    "gradle", "externalnativebuild", "find_library(log)", "log-lib", "loglib",
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread",
    "x11", "wayland", "gtk", "qt", "set(cmake_system_name linux",
)

def cmakelists_flavor(cm_txt: str) -> str:
    t = cm_txt.lower()
    if any(h in t for h in ANDROID_HINTS):
        return "android"
    if any(h in t for h in DESKTOP_HINTS):
        return "desktop"
    return "desktop"

# ---------- Android deep detection ----------
ANDROID_PLUGIN_MARKERS = (
    "com.android.application",
    "com.android.library",
    'id("com.android.application")',
    'id("com.android.library")',
)

def has_android_signals(files_index: List[Tuple[pathlib.Path, pathlib.Path, str]], dir_hints: Set[str]) -> bool:
    # strong: AndroidManifest anywhere
    if any(fn == "androidmanifest.xml" for _, _, fn in files_index):
        return True

    # Gradle files anywhere
    gradle_files = [
        abs_p for (abs_p, _rel, fn) in files_index
        if fn in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
    ]
    wrappers = [abs_p for (abs_p, _rel, fn) in files_index if fn == "gradlew"]

    if not gradle_files and not wrappers:
        return False  # no Gradle at all

    # Android plugin markers inside Gradle files
    if any_file_contains(gradle_files, ANDROID_PLUGIN_MARKERS):
        return True

    # Typical Android module structure hints, alongside Gradle
    rel_paths = [str(rel).lower() for (_abs, rel, _f) in files_index]
    if any("/src/main/androidmanifest.xml" in rp for rp in rel_paths):
        return True
    if any("/res/" in rp or rp.endswith("/res") for rp in rel_paths):
        return True
    if any("/src/androidtest" in rp or "/src/test" in rp for rp in rel_paths):
        return True

    # Folder name "android" anywhere with Gradle present
    if "android" in dir_hints and (gradle_files or wrappers):
        return True

    return False

# ---------- detect types ----------
def detect_types():
    files_index = scan_all_files()
    dir_hints   = collect_dir_name_hints(files_index)
    fnames      = [fn for (_a, _r, fn) in files_index]
    rels        = [str(rel).lower() for (_a, rel, _f) in files_index]

    types: List[str] = []

    # folder-name hints
    if "linux" in dir_hints and "linux" not in types: types.append("linux")
    if "android" in dir_hints and "android" not in types: types.append("android")
    if "windows" in dir_hints and "windows" not in types: types.append("windows")

    # ANDROID deep
    if has_android_signals(files_index, dir_hints):
        if "android" not in types:
            types.append("android")

    # CMAKE (content-aware)
    cmake_paths = [abs_p for (abs_p, _rel, fn) in files_index if fn == "cmakelists.txt"]
    if cmake_paths and "cmake" not in types:
        types.append("cmake")
    for p in cmake_paths:
        txt = read_text_lower_safe(p)
        if txt and cmakelists_flavor(txt) == "desktop" and "linux" not in types:
            types.append("linux")

    # LINUX umbrella (make/meson/*.mk)
    if ("makefile" in fnames) or ("gnumakefile" in fnames) or ("meson.build" in fnames) or any(r.endswith(".mk") for r in rels):
        if "linux" not in types:
            types.append("linux")

    # other ecosystems
    if "package.json" in fnames and "node" not in types:
        types.append("node")
    if ("pyproject.toml" in fnames or "setup.py" in fnames) and "python" not in types:
        types.append("python")
    if "cargo.toml" in fnames and "rust" not in types:
        types.append("rust")
    if any(r.endswith(".sln") or r.endswith(".csproj") or r.endswith(".fsproj") for r in rels) and "dotnet" not in types:
        types.append("dotnet")
    if "pom.xml" in fnames and "maven" not in types:
        types.append("maven")
    if "pubspec.yaml" in fnames and "flutter" not in types:
        types.append("flutter")
    if "go.mod" in fnames and "go" not in types:
        types.append("go")
    if any(n in ("workspace", "workspace.bazel", "module.bazel") for n in fnames) or \
       any(os.path.basename(r) in ("build", "build.bazel") for r in rels):
        if "bazel" not in types:
            types.append("bazel")
    if "sconstruct" in fnames or "sconscript" in fnames:
        if "scons" not in types:
            types.append("scons")
    if "build.ninja" in fnames and "ninja" not in types:
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

# ---------- setup snippets ----------
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
            with:
              node-version: "20"
        """)
    if ptype == "rust":
        return textwrap.dedent("""
          - uses: dtolnay/rust-toolchain@stable
          - run: rustc --version && cargo --version
        """)
    if ptype == "dotnet":
        return textwrap.dedent("""
          - uses: actions/setup-dotnet@v4
            with:
              dotnet-version: "8.0.x"
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
            with:
              flutter-version: "3.22.0"
          - run: flutter --version
        """)
    if ptype == "go":
        return textwrap.dedent("""
          - uses: actions/setup-go@v5
            with:
              go-version: "1.22"
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
    # cmake/python/unknown: only setup-python is required
    return ""

PIN_REMOTE_YAML = textwrap.dedent("""\
      - name: Pin git remote with token (just-in-time)
        env:
          BOT_TOKEN: ${{ secrets.BOT_TOKEN }}
          REPO_SLUG: ${{ github.repository }}
        run: |
          set -euxo pipefail
          git config --local --name-only --get-regexp '^http\\.https://github\\.com/\\.extraheader$' >/dev/null 2>&1 && \
            git config --local --unset-all http.https://github.com/.extraheader || true
          git config --global --add safe.directory "$GITHUB_WORKSPACE"
          git remote set-url origin "https://x-access-token:${BOT_TOKEN}@github.com/${REPO_SLUG}.git"
          git config --global url."https://x-access-token:${BOT_TOKEN}@github.com/".insteadOf "https://github.com/"
          git remote -v
""")

# ---------- PROBE workflow (generic) ----------
def write_probe_workflow_for_type(ptype: str):
    setup_inline = setup_steps_inline(ptype)

    tmpl = r"""
name: AirysDark-AI - Probe __PTYPE_CAP__

'on':
  workflow_dispatch: {}
  push:
    branches:
      - '**'
  pull_request: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  probe:
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
__SETUP_INLINE__
      - name: Probe build command
        id: probe
        shell: bash
        run: |
          set -euxo pipefail
          python3 tools/AirysDark-AI_probe.py --type "__PTYPE__" | tee /tmp/probe.out
          CMD=$(grep -E '^BUILD_CMD=' /tmp/probe.out | sed 's/^BUILD_CMD=//')
          echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"

      - name: Generate final workflow .github/workflows/AirysDark-AI___PTYPE__.yml
        shell: bash
        env:
          BUILD_CMD: "${{ steps.probe.outputs.BUILD_CMD }}"
        run: |
          set -euo pipefail
          mkdir -p .github/workflows
          cat > .github/workflows/AirysDark-AI___PTYPE__.yml <<'YAML'
          name: AirysDark-AI - __PTYPE_CAP__ (generated)

          'on':
            workflow_dispatch: {}
            push:
              branches:
                - '**'
            pull_request: {}

          jobs:
            build:
              runs-on: ubuntu-latest
              permissions:
                contents: write
                pull-requests: write
              steps:
                - uses: actions/checkout@v4
                  with:
                    fetch-depth: 0
                    persist-credentials: false

                - uses: actions/setup-python@v5
                  with:
                    python-version: "3.11"
                - run: pip install requests
__SETUP_INLINE__
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
                    name: __PTYPE__-build-log
                    path: build.log
                    if-no-files-found: warn
                    retention-days: 7

                # --- AI auto-fix (OpenAI -> llama.cpp) ---
                - name: Build llama.cpp (CMake, no CURL, in temp)
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
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
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
                  run: |
                    mkdir -p models
                    curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
                      https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

                - name: Attempt AI auto-fix (OpenAI -> llama fallback)
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
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
                    name: __PTYPE__-ai-patch
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

                # Pin remote with BOT_TOKEN before creating PR (avoids credential issues)
                - name: Pin git remote with token (just-in-time)
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
                    branch: ai/airysdark-ai-autofix-__PTYPE__
                    commit-message: "chore: AirysDark-AI auto-fix (__PTYPE__)"
                    title: "AirysDark-AI: automated build fix (__PTYPE__)"
                    body: |
                      This PR was opened automatically by a generated workflow after a failed build.
                      - Build command: ${{ steps.build.outputs.BUILD_CMD }}
                      - Captured the failing build log
                      - Proposed a minimal fix via AI
                      - Committed the changes for review
                    labels: automation, ci
          YAML

      # Pin before PR that adds the final workflow
      - name: Pin git remote with token (just-in-time)
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

      - name: Create PR with generated final workflow
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.BOT_TOKEN }}
          branch: ai/airysdark-ai-workflow-__PTYPE__
          commit-message: "chore: add AirysDark-AI___PTYPE__ workflow (probed)"
          title: "AirysDark-AI: add __PTYPE__ workflow (from probe)"
          body: |
            This PR adds the final __PTYPE__ AI build workflow, generated by the probe run.
            - Probed command: ${{ steps.probe.outputs.BUILD_CMD }}
            - Next: merge this PR, then run \"AirysDark-AI - __PTYPE_CAP__ (generated)\"
          labels: automation, ci
""".lstrip("\n")

    setup_block = ""
    if setup_inline.strip():
        setup_block = textwrap.indent(setup_inline.rstrip() + "\n", " " * 6)

    yaml = (tmpl
            .replace("__SETUP_INLINE__", setup_block.rstrip("\n"))
            .replace("__PTYPE__", ptype)
            .replace("__PTYPE_CAP__", ptype.capitalize())
            )

    (WF / f"AirysDark-AI_prob_{ptype}.yml").write_text(yaml)
    print(f"✅ Generated: AirysDark-AI_prob_{ptype}.yml")

# ---------- Android-specific PROBE writer (kept explicit) ----------
def write_probe_workflow_for_android():
    setup_inline = setup_steps_inline("android")

    tmpl = r"""
name: AirysDark-AI - Probe Android

'on':
  workflow_dispatch: {}
  push:
    branches:
      - '**'
  pull_request: {}

permissions:
  contents: write
  pull-requests: write

jobs:
  probe:
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
__SETUP_INLINE__
      - name: Probe build command (Android)
        id: probe
        shell: bash
        run: |
          set -euxo pipefail
          python3 tools/AirysDark-AI_probe.py --type "android" | tee /tmp/probe.out
          CMD=$(grep -E '^BUILD_CMD=' /tmp/probe.out | sed 's/^BUILD_CMD=//')
          echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"

      - name: Generate final workflow .github/workflows/AirysDark-AI_android.yml
        shell: bash
        env:
          BUILD_CMD: "${{ steps.probe.outputs.BUILD_CMD }}"
        run: |
          set -euo pipefail
          mkdir -p .github/workflows
          cat > .github/workflows/AirysDark-AI_android.yml <<'YAML'
          name: AirysDark-AI - Android (generated)

          'on':
            workflow_dispatch: {}
            push:
              branches:
                - '**'
            pull_request: {}

          jobs:
            build:
              runs-on: ubuntu-latest
              permissions:
                contents: write
                pull-requests: write
              steps:
                - uses: actions/checkout@v4
                  with:
                    fetch-depth: 0
                    persist-credentials: false

                - uses: actions/setup-python@v5
                  with:
                    python-version: "3.11"
                - run: pip install requests

                # Android SDK / Java
                - uses: actions/setup-java@v4
                  with:
                    distribution: temurin
                    java-version: "17"
                - uses: android-actions/setup-android@v3
                - run: yes | sdkmanager --licenses
                - run: sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

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
                    name: android-build-log
                    path: build.log
                    if-no-files-found: warn
                    retention-days: 7

                # --- AI auto-fix (OpenAI -> llama.cpp) ---
                - name: Build llama.cpp (CMake, no CURL, in temp)
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
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
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
                  run: |
                    mkdir -p models
                    curl -L -o models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
                      https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

                - name: Attempt AI auto-fix (OpenAI -> llama fallback)
                  if: always() && ${{ steps.build.outputs.EXIT_CODE != '0' }}
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

                - name: Pin git remote with token (just-in-time)
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
          YAML

      - name: Pin git remote with token (just-in-time)
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

      - name: Create PR with generated final workflow
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.BOT_TOKEN }}
          branch: ai/airysdark-ai-workflow-android
          commit-message: "chore: add AirysDark-AI_android workflow (probed)"
          title: "AirysDark-AI: add Android workflow (from probe)"
          body: |
            This PR adds the final Android AI build workflow, generated by the probe run.
            - Probed command: ${{ steps.probe.outputs.BUILD_CMD }}
            - Next: merge this PR, then run "AirysDark-AI - Android (generated)"
          labels: automation, ci
""".lstrip("\n")

    setup_block = ""
    if setup_inline.strip():
        setup_block = textwrap.indent(setup_inline.rstrip() + "\n", " " * 6)

    yaml = (tmpl
            .replace("__SETUP_INLINE__", setup_block.rstrip("\n"))
            )

    (WF / "AirysDark-AI_prob_android.yml").write_text(yaml)
    print("✅ Generated: AirysDark-AI_prob_android.yml")

# ---------- main ----------
def main():
    types = detect_types()
    print("Detected types:", ", ".join(types))
    for t in types:
        if t == "android":
            write_probe_workflow_for_android()
        else:
            write_probe_workflow_for_type(t)
    print(f"Done. Generated {len(types)} PROBE workflow(s) in {WF}")

if __name__ == "__main__":
    sys.exit(main())