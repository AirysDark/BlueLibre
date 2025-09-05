#!/usr/bin/env python3
# AirysDark-AI_detector.py
#
# Recursively scan the repository for build systems & hints.
# - Looks in every folder (skips .git)
# - Uses folder-name hints (linux/android/windows etc.)
# - CMake content-aware detection (desktop-like => also mark "linux")
# - Writes:
#     tools/airysdark_ai_scan.json  (machine-readable, with evidence)
#     tools/airysdark_ai_scan.md    (human-friendly summary)
#     .github/workflows/AirysDark-AI_prob.yml  (generic manual probe workflow)
#
# The PROBE workflow is manual-run and expects you to set env.TARGET.

import os
import json
import sys
import pathlib
import textwrap

ROOT = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
WF_DIR = ROOT / ".github" / "workflows"
TOOLS_DIR = ROOT / "tools"
WF_DIR.mkdir(parents=True, exist_ok=True)
TOOLS_DIR.mkdir(parents=True, exist_ok=True)

# -------------------- scanning helpers --------------------

def scan_all_files():
    """Return list of (lower_filename, relative_path) for every file in repo (skips .git)."""
    out = []
    for r, dnames, fnames in os.walk(ROOT):
        # skip .git
        if ".git" in dnames:
            dnames.remove(".git")
        rpath = pathlib.Path(r)
        for fn in fnames:
            p = rpath / fn
            try:
                rel = p.relative_to(ROOT)
            except Exception:
                rel = p
            out.append((fn.lower(), rel))
    return out

def read_text_safe(relpath: pathlib.Path) -> str:
    try:
        return (ROOT / relpath).read_text(errors="ignore")
    except Exception:
        return ""

def all_dir_name_hints(files):
    """Collect EVERY path segment as a lowercased name-hint."""
    names = set()
    for _, rel in files:
        for part in pathlib.Path(rel).parts:
            names.add(part.lower())
    return names

# -------------------- content-aware CMake classifier --------------------

ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk",
    "externalnativebuild", "gradle", "cmake_android",
    "find_library(log)", "log-lib", "loglib"
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread",
    "x11", "wayland", "gtk", "qt", "set(cmake_system_name linux"
)

def cmakelists_flavor(txt: str) -> str:
    t = txt.lower()
    if any(h in t for h in ANDROID_HINTS):
        return "android"
    if any(h in t for h in DESKTOP_HINTS):
        return "desktop"
    # default: desktop unless clearly android
    return "desktop"

# -------------------- detection --------------------

def detect_types_with_evidence():
    files = scan_all_files()
    fnames = [n for n, _ in files]
    rels   = [str(p).lower() for _, p in files]
    dir_hints = all_dir_name_hints(files)

    types = []
    evidence = { }  # type -> list[str]

    def add(t, ev):
        if t not in types:
            types.append(t)
        evidence.setdefault(t, [])
        if isinstance(ev, (list, tuple, set)):
            evidence[t].extend(str(x) for x in ev)
        else:
            evidence[t].append(str(ev))

    # --- folder-name hints ---
    for name in ("linux", "android", "windows", "win", "ios", "mac", "darwin", "unix"):
        if name in dir_hints:
            # map a couple of common aliases
            if name in ("windows", "win"):
                add("windows", f"folder hint: {name}")
            else:
                add(name, f"folder hint: {name}")

    # --- Android / Gradle ---
    if "gradlew" in fnames or any("build.gradle" in n or "settings.gradle" in n for n in fnames):
        add("android", [p for (n, p) in files if n in ("gradlew", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")])

    # --- CMake (also content-aware -> might imply linux) ---
    cmake_paths = [p for (n, p) in files if n == "cmakelists.txt"]
    if cmake_paths:
        add("cmake", cmake_paths)
        for p in cmake_paths:
            flavor = cmakelists_flavor(read_text_safe(p))
            if flavor == "desktop":
                add("linux", f"CMakeLists.txt desktop-like: {p}")

    # --- Linux umbrella: Make / Meson / *.mk ---
    if "makefile" in fnames:
        add("linux", [p for (n, p) in files if n == "makefile"])
    if "gnumakefile" in fnames:
        add("linux", [p for (n, p) in files if n == "gnumakefile"])
    if "meson.build" in fnames:
        add("linux", [p for (n, p) in files if n == "meson.build"])
    if any(r.endswith(".mk") for r in rels):
        add("linux", [p for (_, p) in files if str(p).lower().endswith(".mk")])

    # --- Node ---
    if "package.json" in fnames:
        add("node", [p for (n, p) in files if n == "package.json"])

    # --- Python ---
    if "pyproject.toml" in fnames or "setup.py" in fnames:
        add("python", [p for (n, p) in files if n in ("pyproject.toml", "setup.py")])

    # --- Rust ---
    if "cargo.toml" in fnames:
        add("rust", [p for (n, p) in files if n == "cargo.toml"])

    # --- .NET ---
    dotnet_files = [p for (_, p) in files if str(p).lower().endswith((".sln", ".csproj", ".fsproj"))]
    if dotnet_files:
        add("dotnet", dotnet_files)

    # --- Maven ---
    if "pom.xml" in fnames:
        add("maven", [p for (n, p) in files if n == "pom.xml"])

    # --- Flutter ---
    if "pubspec.yaml" in fnames:
        add("flutter", [p for (n, p) in files if n == "pubspec.yaml"])

    # --- Go ---
    if "go.mod" in fnames:
        add("go", [p for (n, p) in files if n == "go.mod"])

    # --- Bazel ---
    bazel_special = {"workspace", "workspace.bazel", "module.bazel"}
    if any(n in bazel_special for n in fnames) or any(os.path.basename(r) in ("build", "build.bazel") for r in rels):
        add("bazel", [p for (n, p) in files if n in bazel_special or os.path.basename(str(p)).lower() in ("build", "build.bazel")])

    # --- SCons ---
    if "sconstruct" in fnames or "sconscript" in fnames:
        add("scons", [p for (n, p) in files if n in ("sconstruct", "sconscript")])

    # --- Ninja (direct) ---
    if "build.ninja" in fnames:
        add("ninja", [p for (n, p) in files if n == "build.ninja"])

    if not types:
        add("unknown", "no standard build files found")

    # de-dupe evidence entries
    for t in list(evidence.keys()):
        seen = set()
        dedup = []
        for e in evidence[t]:
            se = str(e)
            if se not in seen:
                seen.add(se)
                dedup.append(se)
        evidence[t] = dedup

    return types, evidence

# -------------------- write outputs --------------------

def write_scan_json(types, evidence):
    obj = {"types": types, "evidence": evidence}
    (TOOLS_DIR / "airysdark_ai_scan.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(f"✅ Wrote: {TOOLS_DIR}/airysdark_ai_scan.json")

def write_scan_md(types, evidence):
    lines = []
    lines.append("# AirysDark-AI detector scan\n")
    if types:
        lines.append("**Detected build types:**")
        for t in types:
            lines.append(f"- {t}")
    else:
        lines.append("- (none)")
    lines.append("\n## Evidence")
    for t in types:
        lines.append(f"\n### {t}")
        for ev in evidence.get(t, []):
            lines.append(f"- {ev}")
    (TOOLS_DIR / "airysdark_ai_scan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"✅ Wrote: {TOOLS_DIR}/airysdark_ai_scan.md")

def write_prob_workflow():
    """
    Writes the PROBE workflow template with the validated YAML (manual run, user sets env.TARGET).
    """
    yml = textwrap.dedent("""\
    name: AirysDark-AI - Probe (LLM builds workflow)

    on:
      workflow_dispatch: {}

    permissions:
      contents: write
      pull-requests: write

    # Set TARGET to one of the detected types: android, linux, cmake, node, python, rust, dotnet, maven, flutter, go
    env:
      TARGET: "__SET_ME__"

    jobs:
      probe:
        runs-on: ubuntu-latest
        steps:
          - name: Checkout (no credentials)
            uses: actions/checkout@v4
            with:
              fetch-depth: 0
              persist-credentials: false

          - name: Setup Python
            uses: actions/setup-python@v5
            with:
              python-version: "3.11"

          - name: Verify tools exist (added by detector PR)
            shell: bash
            run: |
              set -euxo pipefail
              test -f tools/AirysDark-AI_prob.py
              test -f tools/AirysDark-AI_builder.py
              ls -la tools
              echo "TARGET=$TARGET"

          - name: Run repo probe (AI-assisted)
            shell: bash
            env:
              TARGET: ${{ env.TARGET }}
              OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # optional
              OPENAI_MODEL: ${{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}
            run: |
              set -euxo pipefail
              python3 tools/AirysDark-AI_prob.py

          - name: Upload probe artifacts
            if: always()
            uses: actions/upload-artifact@v4
            with:
              name: airysdark-ai-probe-artifacts
              if-no-files-found: warn
              retention-days: 7
              path: |
                tools/airysdark_ai_prob_report.json
                tools/airysdark_ai_prob_report.log
                tools/airysdark_ai_build_ai_response.txt
                pr_body_build.md
                .github/workflows/AirysDark-AI_build.yml

          - name: Stage generated build workflow
            id: diff
            shell: bash
            run: |
              set -euxo pipefail
              git add -A
              if git diff --cached --quiet; then
                echo "changed=false" >> "$GITHUB_OUTPUT"
              else:
                echo "changed=true" >> "$GITHUB_OUTPUT"
              fi

          - name: Open PR with generated build workflow
            if: steps.diff.outputs.changed == 'true'
            uses: peter-evans/create-pull-request@v6
            with:
              token: ${{ secrets.BOT_TOKEN }}
              branch: ai/airysdark-ai-build
              commit-message: "chore: add AirysDark-AI_build.yml (from probe)"
              title: "AirysDark-AI: add build workflow (from probe)"
              body-path: pr_body_build.md
              labels: "automation, ci"
    """)
    (WF_DIR / "AirysDark-AI_prob.yml").write_text(yml, encoding="utf-8")
    print(f"✅ Wrote: {WF_DIR}/AirysDark-AI_prob.yml")

# -------------------- main --------------------

def main():
    types, evidence = detect_types_with_evidence()
    write_scan_json(types, evidence)
    write_scan_md(types, evidence)
    write_prob_workflow()
    print("Detected:", ", ".join(types))

if __name__ == "__main__":
    sys.exit(main())