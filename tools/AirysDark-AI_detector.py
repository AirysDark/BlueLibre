#!/usr/bin/env python3
# AirysDark-AI_detector.py — DETECT ONLY
#
# - Deep scans repo (all dirs; skips .git)
# - Decides build types: android, linux, cmake, node, python, rust, dotnet, maven, flutter, go, bazel, scons, ninja, unknown
# - Writes logs + JSON under tools/
# - Generates exactly ONE workflow: .github/workflows/AirysDark-AI_prob.yml
#   • The workflow *does not* fetch tools; it assumes this detector PR added them
#   • The workflow requires manual edit: env.TARGET must be set by the user before running

import os, json, pathlib, datetime, sys

ROOT  = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
TOOLS = ROOT / "tools"
WF    = ROOT / ".github" / "workflows"
TOOLS.mkdir(parents=True, exist_ok=True)
WF.mkdir(parents=True, exist_ok=True)

# --- signal lists for CMake flavor ---
ANDROID_HINTS = (
    "android", "android_abi", "android_platform", "ndk", "cmake_android",
    "gradle", "externalnativebuild", "find_library(log)", "log-lib", "loglib"
)
DESKTOP_HINTS = (
    "add_executable", "pkgconfig", "find_package(", "threads", "pthread",
    "x11", "wayland", "gtk", "qt", "set(cmake_system_name linux"
)

def read_text_safe(p: pathlib.Path) -> str:
    try: return p.read_text(errors="ignore")
    except Exception: return ""

def cmakelists_flavor(cm_txt: str) -> str:
    t = cm_txt.lower()
    if any(h in t for h in ANDROID_HINTS): return "android"
    if any(h in t for h in DESKTOP_HINTS): return "desktop"
    return "desktop"

def deep_scan():
    hits = {k: [] for k in [
        "android_gradle","cmakelists","make_like","node","python","rust",
        "dotnet","maven","flutter","go","bazel","scons","ninja"
    ]}
    cmake_flavors = []
    folder_hints = set()

    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs: dirs.remove(".git")
        r = pathlib.Path(root)
        for part in r.relative_to(ROOT).parts:
            if part: folder_hints.add(part.lower())
        for fn in files:
            low = fn.lower()
            rel = (r / fn).relative_to(ROOT)
            if low == "gradlew" or low.startswith("build.gradle") or low.startswith("settings.gradle"):
                hits["android_gradle"].append(str(rel))
            if low == "cmakelists.txt":
                hits["cmakelists"].append(str(rel))
                cmake_flavors.append({"path": str(rel), "flavor": cmakelists_flavor(read_text_safe(r / fn))})
            if low in ("makefile","gnumakefile","meson.build","build.ninja") or low.endswith(".mk"):
                hits["make_like"].append(str(rel))
            if low == "package.json":
                hits["node"].append(str(rel))
            if low in ("pyproject.toml","setup.py"):
                hits["python"].append(str(rel))
            if low == "cargo.toml":
                hits["rust"].append(str(rel))
            if low.endswith(".sln") or low.endswith(".csproj") or low.endswith(".fsproj"):
                hits["dotnet"].append(str(rel))
            if low == "pom.xml":
                hits["maven"].append(str(rel))
            if low == "pubspec.yaml":
                hits["flutter"].append(str(rel))
            if low == "go.mod":
                hits["go"].append(str(rel))
            if low in ("workspace","workspace.bazel","module.bazel") or fn in ("BUILD","BUILD.bazel"):
                hits["bazel"].append(str(rel))
            if low in ("sconstruct","sconscript"):
                hits["scons"].append(str(rel))
            if low == "build.ninja":
                hits["ninja"].append(str(rel))

    # Folder name hints
    if "android" in folder_hints: hits["android_gradle"].append("folder-hint:android")
    if "linux"   in folder_hints: hits["make_like"].append("folder-hint:linux")

    return hits, cmake_flavors, sorted(folder_hints)

def decide_types(hits, cmake_flavors):
    types = set()
    if hits["android_gradle"]: types.add("android")
    if hits["cmakelists"]:
        types.add("cmake")
        if any(x["flavor"] == "desktop" for x in cmake_flavors): types.add("linux")
    if hits["make_like"]: types.add("linux")
    if hits["node"]:      types.add("node")
    if hits["python"]:    types.add("python")
    if hits["rust"]:      types.add("rust")
    if hits["dotnet"]:    types.add("dotnet")
    if hits["maven"]:     types.add("maven")
    if hits["flutter"]:   types.add("flutter")
    if hits["go"]:        types.add("go")
    if hits["bazel"]:     types.add("bazel")
    if hits["scons"]:     types.add("scons")
    if hits["ninja"]:     types.add("ninja")
    if not types:         types.add("unknown")
    order = ["android","linux","cmake","node","python","rust","dotnet","maven","flutter","go","bazel","scons","ninja","unknown"]
    return [t for t in order if t in types]

def write_artifacts(hits, cmake_flavors, folder_hints, types):
    ts = datetime.datetime.utcnow().isoformat()+"Z"

    # Human summary
    summary = [f"[{ts}] AirysDark-AI detector scan", "Detected build types: " + ", ".join(types), ""]
    def add(label, key):
        if hits[key]:
            summary.append(f"- {label}: {len(hits[key])}")
    add("Android Gradle files", "android_gradle")
    add("CMake files", "cmakelists")
    add("Make/Meson/Ninja signals", "make_like")
    add("Node projects", "node")
    add("Python projects", "python")
    add("Rust projects", "rust")
    add(".NET projects", "dotnet")
    add("Maven projects", "maven")
    add("Flutter projects", "flutter")
    add("Go projects", "go")
    add("Bazel signals", "bazel")
    add("SCons signals", "scons")
    add("Ninja files", "ninja")

    log = summary[:] + ["", "Detailed file hits:"]
    for k, arr in hits.items():
        if arr:
            log.append(f"{k}:")
            for p in arr:
                log.append(f"  - {p}")
    if cmake_flavors:
        log.append("")
        log.append("cmake_flavors:")
        for x in cmake_flavors:
            log.append(f"  - {x['path']} -> {x['flavor']}")

    (TOOLS / "airysdark_ai_detector_summary.txt").write_text("\n".join(summary))
    (TOOLS / "airysdark_ai_scan.log").write_text("\n".join(log))
    (TOOLS / "airysdark_ai_detected.json").write_text(json.dumps({"types": types}, indent=2))
    (TOOLS / "airysdark_ai_scan.json").write_text(json.dumps({
        "timestamp": ts,
        "types": types,
        "hits": hits,
        "cmake_flavors": cmake_flavors,
        "folder_hints": folder_hints,
    }, indent=2))

def generate_prob_workflow(types):
    valid = types[:] or ["unknown"]
    valid_list = ", ".join(valid)
    yml = f"""name: AirysDark-AI - Probe (LLM builds workflow)

on:
  workflow_dispatch: {{}}  # manual only

permissions:
  contents: write
  pull-requests: write

# IMPORTANT: set TARGET to one of: {valid_list}
env:
  TARGET: "__SET_ME__"  # e.g. android / linux / cmake / node / python / ...

jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout (no credentials)
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - name: Guard: ensure TARGET is set
        run: |
          if [ "${{{{ env.TARGET }}}}" = "__SET_ME__" ]; then
            echo "TARGET is not set. Edit this workflow to set env.TARGET (e.g. android) and run again."
            exit 1
          fi
          echo "TARGET=${{{{ env.TARGET }}}}"

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Verify tools exist (added by detector PR)
        run: |
          set -euxo pipefail
          test -f tools/AirysDark-AI_prob.py
          test -f tools/AirysDark-AI_builder.py
          ls -la tools

      - name: Run repo probe (AI-assisted)
        env:
          TARGET: ${{{{ env.TARGET }}}}
          OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}   # optional; falls back to heuristic if absent
          OPENAI_MODEL: ${{{{ vars.OPENAI_MODEL || 'gpt-4o-mini' }}}}
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
        run: |
          set -euxo pipefail
          git add -A
          if git diff --cached --quiet; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Open PR with generated build workflow
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{{{ secrets.BOT_TOKEN }}}}   # Fine-grained PAT: contents+pull-requests on this repo
          branch: ai/airysdark-ai-build
          commit-message: "chore: add AirysDark-AI_build.yml (from probe)"
          title: "AirysDark-AI: add build workflow (from probe)"
          body-path: pr_body_build.md
          labels: automation, ci
"""
    (WF / "AirysDark-AI_prob.yml").write_text(yml)

def main():
    hits, cmake_flavors, folder_hints = deep_scan()
    types = decide_types(hits, cmake_flavors)
    write_artifacts(hits, cmake_flavors, folder_hints, types)
    generate_prob_workflow(types)
    print("Detected types:", ", ".join(types))
    print(f"Wrote workflow: {WF / 'AirysDark-AI_prob.yml'}")

if __name__ == "__main__":
    sys.exit(main())