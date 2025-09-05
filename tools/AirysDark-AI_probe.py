#!/usr/bin/env python3
"""
AirysDark-AI_probe.py
Figures out the most likely build command for a given project type,
so the workflow can run the *right* command before invoking the AI fixer.

Usage (GitHub Actions):
  - name: Probe build command
    id: probe
    run: |
      python3 tools/AirysDark-AI_probe.py --type "${{ matrix.type || inputs.type || 'linux' }}"
"""

import argparse, os, re, subprocess, sys, shlex
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(".").resolve()

def sh(cmd: str, cwd: Path | None = None, check: bool = False) -> tuple[str, int]:
    p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout)
    return p.stdout, p.returncode

def scan_all_files() -> List[Tuple[Path, Path, str]]:
    out: List[Tuple[Path, Path, str]] = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            ap = Path(root) / fn
            try:
                rp = ap.relative_to(ROOT)
            except Exception:
                rp = ap
            out.append((ap, rp, fn.lower()))
    return out

def find_first(globs: Iterable[str]) -> Path | None:
    for pat in globs:
        for p in ROOT.glob(pat):
            return p
    return None

def print_output_var(name: str, val: str):
    print(f"{name}={val}")

# ---------------- Android ----------------
def probe_android() -> str:
    """
    Strategy:
      1) find gradlew(s) anywhere
      2) pick the wrapper whose directory has a settings.gradle(.kts)
      3) parse settings for modules; prefer :app
      4) ask Gradle for tasks; prefer assemble/bundle (Debug → Release → build)
    """
    wrappers = list(ROOT.glob("**/gradlew"))
    if not wrappers and (ROOT / "gradlew").exists():
        wrappers = [ROOT / "gradlew"]
    if not wrappers:
        # fallback
        return "./gradlew assembleDebug --stacktrace"

    # rank wrappers: prefer one with settings + app module present
    def parse_modules(settings: Path) -> list[str]:
        if not settings or not settings.exists():
            return []
        txt = settings.read_text(errors="ignore")
        # include(":app", ":feature:home")
        mods: list[str] = []
        for m in re.findall(r'include\s*\((.*?)\)', txt, flags=re.S):
            parts = re.split(r'[,\s]+', m.strip())
            for p in parts:
                p = p.strip().strip('"\'')

                if p.startswith(":"):
                    mods.append(p[1:])
        # include ':app', ':lib'
        for m in re.findall(r'include\s+([^\n]+)', txt, flags=re.I):
            for p in re.split(r'[, \t]+', m.strip()):
                p = p.strip().strip('"\'')

                if p.startswith(":"):
                    mods.append(p[1:])
        # unique, preserve order
        seen, out = set(), []
        for mm in mods:
            if mm and mm not in seen:
                seen.add(mm)
                out.append(mm)
        return out

    def has_app_module(basedir: Path, modules: list[str]) -> bool:
        for m in modules:
            for buildfile in ("build.gradle", "build.gradle.kts"):
                f = basedir / m.replace(":", "/") / buildfile
                if f.exists():
                    t = f.read_text(errors="ignore").lower()
                    if "com.android.application" in t:
                        return True
        # common guesses
        for guess in ("app", "mobile", "android"):
            for buildfile in ("build.gradle", "build.gradle.kts"):
                f = basedir / guess / buildfile
                if f.exists():
                    t = f.read_text(errors="ignore").lower()
                    if "com.android.application" in t:
                        return True
        return False

    ranked: list[tuple[Path,bool,bool,list[str]]] = []
    for g in wrappers:
        d = g.parent
        settings = None
        for s in ("settings.gradle", "settings.gradle.kts"):
            sp = d / s
            if sp.exists():
                settings = sp
                break
        modules = parse_modules(settings) if settings else []
        ranked.append((g, settings is not None, has_app_module(d, modules), modules))

    ranked.sort(key=lambda x: (not x[1], not x[2]))  # settings, then app module
    g, _, _, modules = ranked[0]
    try:
        g.chmod(0o755)
    except Exception:
        pass

    # query tasks
    tasks_out, _ = sh(f"./{g.name} -q tasks --all", cwd=g.parent)

    def exists_task(name: str) -> bool:
        return re.search(rf"(^|\s){re.escape(name)}(\s|$)", tasks_out) is not None

    # candidates
    base = ["assembleDebug", "bundleDebug", "assembleRelease", "bundleRelease", "build"]
    module_candidates: list[str] = []
    for m in modules:
        module_candidates += [f":{m}:{t}" for t in base]
    for guess in ("app", "mobile", "android"):
        module_candidates += [f":{guess}:{t}" for t in base]

    for t in base:
        if exists_task(t):
            return f'cd {shlex.quote(str(g.parent))} && ./gradlew {t} --stacktrace'
    for t in module_candidates:
        if exists_task(t):
            return f'cd {shlex.quote(str(g.parent))} && ./gradlew {t} --stacktrace'

    # last resort
    return f'cd {shlex.quote(str(g.parent))} && ./gradlew assembleDebug --stacktrace'

# ---------------- CMake ----------------
def probe_cmake() -> str:
    if (ROOT / "CMakeLists.txt").exists():
        return "cmake -S . -B build && cmake --build build -j"
    first = find_first(["**/CMakeLists.txt"])
    if first:
        outdir = f'build/{str(first.parent).replace("/", "_")}'
        return f'cmake -S "{first.parent}" -B "{outdir}" && cmake --build "{outdir}" -j'
    return "echo 'No CMakeLists.txt found' && exit 1"

# ---------------- Linux (Make/Meson/Ninja) ----------------
def probe_linux() -> str:
    # simple Makefile root
    if (ROOT / "Makefile").exists():
        return "make -j"
    mk = find_first(["**/Makefile"])
    if mk:
        return f'make -C "{mk.parent}" -j'
    # Meson/Ninja
    if (ROOT / "meson.build").exists():
        return "(meson setup build --wipe || true); meson setup build || true; ninja -C build"
    mb = find_first(["**/meson.build"])
    if mb:
        d = mb.parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    # Raw Ninja
    if (ROOT / "build.ninja").exists():
        return "ninja"
    bn = find_first(["**/build.ninja"])
    if bn:
        return f'cd "{bn.parent}" && ninja'
    return "echo 'No Makefile/meson.build/build.ninja found' && exit 1"

# ---------------- Other ecosystems ----------------
def probe_node() -> str:
    if (ROOT / "package.json").exists():
        return "npm ci && npm run build --if-present"
    p = find_first(["**/package.json"])
    if p:
        return f'cd "{p.parent}" && npm ci && npm run build --if-present'
    return "echo 'No package.json found' && exit 1"

def probe_python() -> str:
    if (ROOT / "pyproject.toml").exists() or (ROOT / "setup.py").exists():
        return "pip install -e . && (pytest || python -m pytest || true)"
    p = find_first(["**/pyproject.toml", "**/setup.py"])
    if p:
        return f'cd "{p.parent}" && pip install -e . && (pytest || python -m pytest || true)'
    return "echo 'No python project found' && exit 1"

def probe_rust() -> str:
    return "cargo build --locked --all-targets --verbose"

def probe_dotnet() -> str:
    return "dotnet restore && dotnet build -c Release"

def probe_maven() -> str:
    return "mvn -B package --file pom.xml"

def probe_flutter() -> str:
    return "flutter build apk --debug"

def probe_go() -> str:
    return "go build ./..."

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
    else: cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())