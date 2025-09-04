#!/usr/bin/env python3
# AirysDark-AI_detector.py
#
# Scans *all files in the repo* recursively to detect build systems.
# For each detected type, writes a PROBE workflow:
#   .github/workflows/AirysDark-AI_prob_<type>.yml
#
# Later, each probe workflow:
#   - fetches AirysDark-AI tools
#   - runs AirysDark-AI_probe.py to determine BUILD_CMD
#   - generates the final AI build workflow
#   - opens a PR with BOT_TOKEN

import os
import pathlib
import textwrap
import sys

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)

# ---------- File scanning ----------
def scan_all_files():
    """Return a list of all files (lowercased name + full path)."""
    out = []
    for root, dirs, files in os.walk(ROOT):
        # skip .git and .github/workflows themselves
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = pathlib.Path(root) / f
            try:
                out.append((f.lower(), p.relative_to(ROOT)))
            except Exception:
                out.append((f.lower(), p))
    return out

def detect_types():
    files = scan_all_files()
    fnames = [name for name, _ in files]
    rels   = [str(path) for _, path in files]

    types = []

    # Android/Gradle
    if any("gradlew" in f for f in fnames) or any("build.gradle" in f or "settings.gradle" in f for f in fnames):
        types.append("android")
    # CMake
    if any("cmakelists.txt" in f for f in fnames):
        types.append("cmake")
    # Linux (Makefile / Meson)
    if any(f in ("makefile",) for f in fnames) or any("meson.build" in f for f in fnames):
        types.append("linux")
    # Node
    if "package.json" in fnames:
        types.append("node")
    # Python
    if "setup.py" in fnames or "pyproject.toml" in fnames:
        types.append("python")
    # Rust
    if "cargo.toml" in fnames:
        types.append("rust")
    # Dotnet
    if any(f.endswith((".sln", ".csproj", ".fsproj")) for f in rels):
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

    if not types:
        types.append("unknown")

    # de-dupe preserve order
    seen, out = set(), []
    for t in types:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

# ---------- Type-specific setup ----------
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
    return ""

# ---------- PROBE workflow generator ----------
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

          - name: Ensure AirysDark-AI tools
            shell: bash
            run: |
              set -euo pipefail
              mkdir -p tools
              BASE_URL="https://raw.githubusercontent.com/AirysDark-AI/AirysDark-AI_builder/main/tools"
              [ -f tools/AirysDark-AI_probe.py ]    || curl -fL "$BASE_URL/AirysDark-AI_probe.py"    -o tools/AirysDark-AI_probe.py
              [ -f tools/AirysDark-AI_builder.py ]  || curl -fL "$BASE_URL/AirysDark-AI_builder.py"  -o tools/AirysDark-AI_builder.py

          - name: Probe build command
            id: probe
            run: |
              set -euxo pipefail
              python3 tools/AirysDark-AI_probe.py --type "{ptype}" | tee /tmp/probe.out
              CMD=$(grep -E '^BUILD_CMD=' /tmp/probe.out | sed 's/^BUILD_CMD=//')
              echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"

          - name: Create PR with generated final workflow
            uses: peter-evans/create-pull-request@v6
            with:
              token: ${{{{ secrets.BOT_TOKEN }}}}
              branch: ai/airysdark-ai-workflow-{ptype}
              commit-message: "chore: add AirysDark-AI_{ptype} workflow (probed)"
              title: "AirysDark-AI: add {ptype} workflow (from probe)"
              body: |
                This PR adds the final {ptype} AI build workflow, generated by the probe run.
                - Probed command: ${{{{ steps.probe.outputs.BUILD_CMD }}}}
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