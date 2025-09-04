#!/usr/bin/env python3
"""
AirysDark-AI_probe.py
Deep probe: scan *every* file and directory to determine the correct build command.

Outputs exactly one line for GitHub Actions to capture:
  BUILD_CMD=<command>
"""

import os, re, shlex, subprocess, sys
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(".").resolve()

# ------------------------------
# Utilities
# ------------------------------
def run(cmd: str, cwd: Optional[Path] = None, capture: bool = True) -> Tuple[str, int]:
    if capture:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.stdout, p.returncode
    else:
        p = subprocess.run(cmd, cwd=cwd, shell=True)
        return "", p.returncode

def scan_all_files() -> List[Tuple[str, Path]]:
    """Return list of (lowercased filename, relative path) for ALL files."""
    out = []
    for root, dirs, files in os.walk(ROOT):
        # Skip VCS/CI caches
        for skip in [".git"]:
            if skip in dirs:
                dirs.remove(skip)
        for f in files:
            p = Path(root) / f
            try:
                rel = p.relative_to(ROOT)
            except Exception:
                rel = p
            out.append((f.lower(), rel))
    return out

def find_first_by_name(names: List[str], files: List[Tuple[str, Path]]) -> Optional[Path]:
    names = [n.lower() for n in names]
    for fname, rel in files:
        if fname in names:
            return rel
    return None

def find_all_by_name(names: List[str], files: List[Tuple[str, Path]]) -> List[Path]:
    names = [n.lower() for n in names]
    found = []
    for fname, rel in files:
        if fname in names:
            found.append(rel)
    return found

def find_all_by_ext(exts: List[str], files: List[Tuple[str, Path]]) -> List[Path]:
    exts = [e.lower() for e in exts]
    found = []
    for fname, rel in files:
        for e in exts:
            if fname.endswith(e):
                found.append(rel)
                break
    return found

def path_depth(p: Path) -> int:
    # number of path parts (shorter is closer to repo root)
    return len(Path(str(p)).parts)

def prefer_shortest(paths: List[Path]) -> Optional[Path]:
    if not paths:
        return None
    return sorted(paths, key=path_depth)[0]

def print_output_var(name: str, val: str):
    print(f"{name}={val}")

# ------------------------------
# Android (Gradle)
# ------------------------------
def is_app_module(dirp: Path) -> bool:
    for fn in ("build.gradle", "build.gradle.kts"):
        f = dirp / fn
        if f.exists():
            try:
                t = f.read_text(errors="ignore")
                if "com.android.application" in t:
                    return True
            except Exception:
                pass
    return False

def parse_settings_modules(settings_path: Optional[Path]) -> List[str]:
    if not settings_path or not settings_path.exists():
        return []
    try:
        txt = settings_path.read_text(errors="ignore")
    except Exception:
        return []
    # include(":app", ":mobile") or include ':app', ':feature:home'
    mods = []
    for raw in re.findall(r'include\s*\((.*?)\)', txt, flags=re.S):
        parts = re.split(r'[,\s]+', raw.strip())
        for p in parts:
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    # also catch include ':app', ':foo:bar' without parentheses
    for raw in re.findall(r'include\s+([^\n]+)', txt):
        # split by comma
        for p in raw.split(","):
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    # unique, preserve order
    out = []
    seen = set()
    for m in mods:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out

def probe_android(files: List[Tuple[str, Path]]) -> Optional[str]:
    # All wrappers
    gradlews = [p for (n, p) in files if n == "gradlew"]
    if not gradlews and (ROOT / "gradlew").exists():
        gradlews = [Path("gradlew")]

    if not gradlews:
        # no wrapper found anywhere; last ditch generic
        return "./gradlew assembleDebug --stacktrace"

    # Rank wrappers: prefer one with settings + app module
    ranked = []
    for g in gradlews:
        d = (ROOT / g).parent
        settings = None
        for sname in ("settings.gradle", "settings.gradle.kts"):
            sp = d / sname
            if sp.exists():
                settings = sp
                break
        modules = parse_settings_modules(settings)
        has_app = any(is_app_module(d / m.replace(":", "/")) for m in modules)
        ranked.append((g, settings is not None, has_app, modules))

    ranked.sort(key=lambda x: (not x[1], not x[2], path_depth(x[0])))
    g, _, _, modules = ranked[0]
    g_abs = (ROOT / g)
    try:
        os.chmod(g_abs, 0o755)
    except Exception:
        pass

    # Ask for tasks
    out, _ = run(f"./{g_abs.name} -q tasks --all", cwd=g_abs.parent)
    def task_exists(name: str) -> bool:
        return re.search(rf"(^|\s){re.escape(name)}(\s|$)", out) is not None

    # Best-first
    candidates = ["assembleDebug", "bundleDebug", "assembleRelease", "bundleRelease", "build"]
    module_candidates = []
    for m in modules:
        module_candidates.extend([
            f":{m}:assembleDebug", f":{m}:bundleDebug",
            f":{m}:assembleRelease", f":{m}:bundleRelease",
        ])
    # common guesses
    for guess in ("app", "mobile", "android"):
        module_candidates.extend([
            f":{guess}:assembleDebug", f":{guess}:bundleDebug",
            f":{guess}:assembleRelease", f":{guess}:bundleRelease",
        ])

    for t in candidates:
        if task_exists(t):
            return f"cd {shlex.quote(str(g_abs.parent))} && ./gradlew {t} --stacktrace"
    for t in module_candidates:
        if task_exists(t):
            return f"cd {shlex.quote(str(g_abs.parent))} && ./gradlew {t} --stacktrace"

    # Fallback
    return f"cd {shlex.quote(str(g_abs.parent))} && ./gradlew assembleDebug --stacktrace"

# ------------------------------
# CMake
# ------------------------------
def probe_cmake(files: List[Tuple[str, Path]]) -> Optional[str]:
    cmakes = [p for (n, p) in files if n == "cmakelists.txt"]
    first = prefer_shortest(cmakes)
    if not first:
        return None
    # Use per-subdir build dir to avoid clashes
    outdir = f'build/{str(first.parent).replace("/", "_")}'
    return f'cmake -S "{first.parent}" -B "{outdir}" && cmake --build "{outdir}" -j'

# ------------------------------
# Linux (Make / Meson+Ninja)
# ------------------------------
def probe_linux(files: List[Tuple[str, Path]]) -> Optional[str]:
    # Makefiles anywhere (any case)
    makefiles = [p for (n, p) in files if n == "makefile"]
    mf = prefer_shortest(makefiles)
    if mf:
        if str(mf.parent) == ".":
            return "make -j"
        return f'make -C "{mf.parent}" -j'
    # Meson
    mesons = [p for (n, p) in files if n == "meson.build"]
    mb = prefer_shortest(mesons)
    if mb:
        d = mb.parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    return None

# ------------------------------
# Node
# ------------------------------
def probe_node(files: List[Tuple[str, Path]]) -> Optional[str]:
    pkgs = [p for (n, p) in files if n == "package.json"]
    if not pkgs:
        return None
    # prefer shortest path and one that has "build" script
    def has_build_script(pkg_path: Path) -> bool:
        try:
            txt = (ROOT / pkg_path).read_text(errors="ignore")
        except Exception:
            return False
        return re.search(r'"scripts"\s*:\s*{[^}]*"build"\s*:', txt, flags=re.S) is not None

    with_build = [p for p in pkgs if has_build_script(p)]
    chosen = prefer_shortest(with_build) or prefer_shortest(pkgs)
    return f'cd "{chosen.parent}" && npm ci && npm run build --if-present'

# ------------------------------
# Python
# ------------------------------
def probe_python(files: List[Tuple[str, Path]]) -> Optional[str]:
    # Prefer pyproject at shortest depth; else setup.py
    pyprojects = [p for (n, p) in files if n == "pyproject.toml"]
    setups     = [p for (n, p) in files if n == "setup.py"]
    chosen = prefer_shortest(pyprojects) or prefer_shortest(setups)
    if not chosen:
        return None
    d = chosen.parent
    return f'cd "{d}" && pip install -e . && (pytest || python -m pytest || true)'

# ------------------------------
# Rust
# ------------------------------
def probe_rust(files: List[Tuple[str, Path]]) -> Optional[str]:
    cargos = [p for (n, p) in files if n == "cargo.toml"]
    chosen = prefer_shortest(cargos)
    if not chosen:
        return None
    return f'cd "{chosen.parent}" && cargo build --locked --all-targets --verbose'

# ------------------------------
# .NET
# ------------------------------
def probe_dotnet(files: List[Tuple[str, Path]]) -> Optional[str]:
    slns = [p for (n, p) in files if str(p).lower().endswith(".sln")]
    if slns:
        chosen = prefer_shortest(slns)
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    csfs = [p for (n, p) in files if str(p).lower().endswith((".csproj", ".fsproj"))]
    chosen = prefer_shortest(csfs)
    if chosen:
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    return None

# ------------------------------
# Maven
# ------------------------------
def probe_maven(files: List[Tuple[str, Path]]) -> Optional[str]:
    poms = [p for (n, p) in files if n == "pom.xml"]
    chosen = prefer_shortest(poms)
    if not chosen:
        return None
    return f'mvn -B package --file "{chosen}"'

# ------------------------------
# Flutter
# ------------------------------
def probe_flutter(files: List[Tuple[str, Path]]) -> Optional[str]:
    pubs = [p for (n, p) in files if n == "pubspec.yaml"]
    chosen = prefer_shortest(pubs)
    if not chosen:
        return None
    return f'cd "{chosen.parent}" && flutter build apk --debug'

# ------------------------------
# Go
# ------------------------------
def probe_go(files: List[Tuple[str, Path]]) -> Optional[str]:
    gomods = [p for (n, p) in files if n == "go.mod"]
    chosen = prefer_shortest(gomods)
    if not chosen:
        return None
    return f'cd "{chosen.parent}" && go build ./...'

# ------------------------------
# Unknown / fallback
# ------------------------------
def probe_unknown(_files: List[Tuple[str, Path]]) -> str:
    return "echo 'No build system detected' && exit 1"

# ------------------------------
# Entry
# ------------------------------
def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--type":
        print("Usage: AirysDark-AI_probe.py --type <android|cmake|linux|node|python|rust|dotnet|maven|flutter|go|unknown>")
        return 2

    ptype = sys.argv[2].strip().lower()
    files = scan_all_files()

    dispatch = {
        "android": probe_android,
        "cmake":   probe_cmake,
        "linux":   probe_linux,
        "node":    probe_node,
        "python":  probe_python,
        "rust":    probe_rust,
        "dotnet":  probe_dotnet,
        "maven":   probe_maven,
        "flutter": probe_flutter,
        "go":      probe_go,
        "unknown": probe_unknown,
    }

    if ptype not in dispatch:
        print_output_var("BUILD_CMD", "echo 'Unknown type' && exit 1")
        return 1

    cmd = dispatch[ptype](files)
    if not cmd:
        # Fallbacks for some types
        if ptype == "android":
            cmd = "./gradlew assembleDebug --stacktrace"
        elif ptype == "linux":
            cmd = "echo 'No Makefile or meson.build found' && exit 1"
        elif ptype == "cmake":
            cmd = "echo 'No CMakeLists.txt found' && exit 1"
        else:
            cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())