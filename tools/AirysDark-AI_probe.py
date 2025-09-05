#!/usr/bin/env python3
"""
AirysDark-AI_probe.py
Figures out the most likely build command for a given project type, so workflows run the right thing.

Usage in GitHub Actions (example):
  - name: Probe build command
    id: probe
    shell: bash
    run: |
      python3 tools/AirysDark-AI_probe.py --type "android" | tee /tmp/probe.out
      CMD=$(grep -E '^BUILD_CMD=' /tmp/probe.out | sed 's/^BUILD_CMD=//')
      echo "BUILD_CMD=$CMD" >> "$GITHUB_OUTPUT"

This script prints exactly one line for Actions to parse:
  BUILD_CMD=<command to run>
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(".").resolve()

# -------------------- helpers --------------------
def sh(cmd, cwd=None, check=False, capture=True, env=None):
    if capture:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        if check and p.returncode != 0:
            raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout)
        return p.stdout, p.returncode
    p = subprocess.run(cmd, cwd=cwd, shell=True, env=env)
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd)
    return "", p.returncode

def first_glob(*patterns: str):
    for pat in patterns:
        for p in ROOT.glob(pat):
            return p
    return None

def all_glob(*patterns: str):
    out = []
    for pat in patterns:
        out.extend(ROOT.glob(pat))
    # de-dupe preserve order
    seen = set()
    uniq = []
    for p in out:
        sp = str(p.resolve())
        if sp not in seen:
            seen.add(sp)
            uniq.append(p)
    return uniq

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def print_output_var(name: str, val: str):
    print(f"{name}={val}")

# -------------------- ANDROID PROBE (smart) --------------------
def parse_modules_from_settings(settings_text: str):
    """
    Extract module names from settings.gradle(.kts).
    Examples:
      include(":app", ":feature:home")
      include ':app', ':lib'
    Returns ["app", "feature:home", "lib"] (no leading ":").
    """
    mods = []

    # include("...", "...")
    for m in re.finditer(r'include\s*\((.*?)\)', settings_text, flags=re.S):
        inside = m.group(1)
        for part in re.split(r'[,\s]+', inside.strip()):
            part = part.strip().strip('"\'')
            if part.startswith(":"):
                mods.append(part[1:])

    # include ':app', ':lib'
    st = settings_text.replace("'", '"')
    for m in re.finditer(r'include\s+((?::[\w\-\.:]+"\s*,?\s*)+|(?::[\w\-\.:]+"\s*)+)', st):
        inside = m.group(0)
        for p2 in re.findall(r'":?([\w\-\.:]+)"', inside):
            mods.append(p2)

    # unique, preserve order
    seen = set()
    out = []
    for x in mods:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

def is_application_module(mod_dir: Path) -> bool:
    for fn in ("build.gradle.kts", "build.gradle"):
        fp = mod_dir / fn
        if fp.exists():
            t = read_text(fp)
            if "com.android.application" in t:
                return True
    return False

def collect_android_wrappers():
    out = []
    if (ROOT / "gradlew").exists():
        out.append(ROOT / "gradlew")
    for w in ROOT.glob("**/gradlew"):
        if w not in out:
            out.append(w)
    for w in out:
        try:
            w.chmod(0o755)
        except Exception:
            pass
    return out

def enumerate_candidate_tasks(tasks_out: str, modules):
    """
    Return candidate tasks in preference order, but only those present in tasks output.
    """
    present = []

    def has(t: str) -> bool:
        return t in tasks_out

    # unqualified first
    for t in ["assembleDebug", "bundleDebug", "build", "assembleRelease", "bundleRelease"]:
        if has(t):
            present.append(t)

    # module-qualified, prefer app-ish names first
    module_order = list(modules)
    for fav in ["app", "mobile", "android"]:
        if fav in module_order:
            module_order.remove(fav)
            module_order.insert(0, fav)

    for m in module_order:
        for base in ["assembleDebug", "bundleDebug", "build", "assembleRelease", "bundleRelease"]:
            mt = f":{m}:{base}"
            if has(mt):
                present.append(mt)

    # unique preserve order
    seen = set()
    uniq = []
    for t in present:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq

def probe_android():
    """
    Strategy:
      - Find all gradle wrappers
      - For each: locate nearest settings.gradle(.kts), parse modules
      - Prefer modules applying com.android.application
      - Ask Gradle for tasks; pick best available
    """
    wrappers = collect_android_wrappers()
    if not wrappers:
        return "./gradlew assembleDebug --stacktrace"

    for w in wrappers:
        root = w.parent
        # Find settings file
        settings = None
        for sfn in ("settings.gradle.kts", "settings.gradle"):
            sp = root / sfn
            if sp.exists():
                settings = sp
                break

        modules = []
        if settings:
            modules = parse_modules_from_settings(read_text(settings))

        # prioritize application modules
        app_modules = [m for m in modules if is_application_module(root / m.replace(":", "/"))]
        if app_modules:
            modules = app_modules + [m for m in modules if m not in app_modules]

        # Query tasks
        tasks_out, _ = sh(f"./{w.name} -q tasks --all", cwd=root)
        candidates = enumerate_candidate_tasks(tasks_out, modules)

        if not candidates:
            # last ditch: try assembleDebug anyway
            candidates = ["assembleDebug"]

        # First candidate wins
        task = candidates[0]
        return f'cd {shlex.quote(str(root))} && ./{w.name} {task} --stacktrace'

    # If loop finishes with nothing, fallback to first wrapper
    w = wrappers[0]
    return f'cd {shlex.quote(str(w.parent))} && ./{w.name} assembleDebug --stacktrace'

# -------------------- other types --------------------
def probe_cmake():
    if (ROOT / "CMakeLists.txt").exists():
        return "cmake -S . -B build && cmake --build build -j"
    p = first_glob("**/CMakeLists.txt")
    if p:
        outdir = f'build/{str(p.parent).replace("/", "_")}'
        return f'cmake -S "{p.parent}" -B "{outdir}" && cmake --build "{outdir}" -j'
    return "echo 'No CMakeLists.txt found' && exit 1"

def probe_linux():
    if (ROOT / "Makefile").exists():
        return "make -j"
    p = first_glob("**/Makefile")
    if p:
        return f'make -C "{p.parent}" -j'
    if (ROOT / "meson.build").exists():
        return "(meson setup build --wipe || true); meson setup build || true; ninja -C build"
    p = first_glob("**/meson.build")
    if p:
        return f'(cd "{p.parent}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    return "echo 'No Makefile or meson.build found' && exit 1"

def probe_node():
    if (ROOT / "package.json").exists():
        return "npm ci && npm run build --if-present"
    p = first_glob("**/package.json")
    if p:
        return f'cd "{p.parent}" && npm ci && npm run build --if-present'
    return "echo 'No package.json found' && exit 1"

def probe_python():
    if (ROOT / "pyproject.toml").exists() or (ROOT / "setup.py").exists():
        return "pip install -e . && (pytest || python -m pytest || true)"
    p = first_glob("**/pyproject.toml", "**/setup.py")
    if p:
        return f'cd "{p.parent}" && pip install -e . && (pytest || python -m pytest || true)'
    return "echo 'No python project found' && exit 1"

def probe_rust():
    return "cargo build --locked --all-targets --verbose"

def probe_dotnet():
    return "dotnet restore && dotnet build -c Release"

def probe_maven():
    return "mvn -B package --file pom.xml"

def probe_flutter():
    return "flutter build apk --debug"

def probe_go():
    return "go build ./..."

# -------------------- main --------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True,
                    choices=["android","cmake","linux","node","python","rust","dotnet","maven","flutter","go","unknown"])
    args = ap.parse_args()

    if args.type == "android": cmd = probe_android()
    elif args.type == "cmake": cmd = probe_cmake()
    elif args.type == "linux": cmd = probe_linux()
    elif args.type == "node": cmd = probe_node()
    elif args.type == "python": cmd = probe_python()
    elif args.type == "rust": cmd = probe_rust()
    elif args.type == "dotnet": cmd = probe_dotnet()
    elif args.type == "maven": cmd = probe_maven()
    elif args.type == "flutter": cmd = probe_flutter()
    elif args.type == "go": cmd = probe_go()
    else:
        cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())