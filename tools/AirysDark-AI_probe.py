#!/usr/bin/env python3
"""
AirysDark-AI_probe.py — smarter build-command prober

Outputs a single line for GitHub Actions:
  BUILD_CMD=<the command to run>

Covers: android, cmake, linux, node, python, rust, dotnet, maven, flutter, go,
        bazel, scons, ninja, unknown
"""

import argparse, os, re, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(".").resolve()

# ---------------- Utilities ----------------
def sh(cmd, cwd=None, check=False):
    p = subprocess.run(
        cmd, cwd=cwd, shell=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout)
    return p.stdout, p.returncode

def print_output_var(name, val):
    print(f"{name}={val}")

def find_all(globs):
    out = []
    for g in globs:
        out.extend(ROOT.glob(g))
    # de-dup but keep order
    seen, dedup = set(), []
    for p in out:
        if p not in seen:
            dedup.append(p)
            seen.add(p)
    return dedup

def find_first(globs):
    for p in find_all(globs):
        return p
    return None

def count_sources(dir_path: Path):
    exts = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp")
    n = 0
    for p in dir_path.rglob("*"):
        if p.suffix.lower() in exts:
            n += 1
    return n

# ---------------- Android (Gradle) ----------------
def parse_settings_modules(settings_path: Path):
    """
    Parse settings.gradle(.kts) and extract included modules like ':app', ':feature:home'.
    """
    if not settings_path or not settings_path.exists():
        return []
    txt = settings_path.read_text(errors="ignore")
    # Groovy/KTS variants:
    # include(':app', ':lib'); include(":feature:home")
    # include ':app', ':lib'
    mods = []

    # include(...) style
    for raw in re.findall(r'include\s*\((.*?)\)', txt, flags=re.S):
        for part in re.split(r'[, \n\t]+', raw.strip()):
            part = part.strip().strip('"\'')
            if part.startswith(":"):
                mods.append(part[1:])

    # include ':a', ':b' style (no parentheses)
    # capture lines like: include ':app', ':lib'
    for line in txt.splitlines():
        m = re.match(r'\s*include\s+(.+)', line)
        if m:
            payload = m.group(1)
            for part in re.split(r'[, \s]+', payload.strip()):
                part = part.strip().strip('"\'')
                if part.startswith(":"):
                    mods.append(part[1:])

    # unique keep-order
    seen, order = set(), []
    for m in mods:
        if m and m not in seen:
            seen.add(m)
            order.append(m)
    return order

def module_is_android_app(root_dir: Path, module_name: str) -> bool:
    # translate module like "app" or "feature:home" -> path "feature/home"
    mod_path = root_dir / module_name.replace(":", "/")
    for fname in ("build.gradle", "build.gradle.kts"):
        f = mod_path / fname
        if f.exists():
            t = f.read_text(errors="ignore")
            if "com.android.application" in t:
                return True
    return False

def pick_best_gradlew():
    # prefer root gradlew, else the one whose dir has settings + app module
    candidates = []
    for g in find_all(["gradlew", "**/gradlew"]):
        d = g.parent
        settings = None
        for s in ("settings.gradle", "settings.gradle.kts"):
            sp = d / s
            if sp.exists():
                settings = sp
                break
        modules = parse_settings_modules(settings) if settings else []
        has_app = any(module_is_android_app(d, m) for m in modules)
        candidates.append((g, settings is not None, has_app, modules))

    if not candidates:
        return None, None, []

    # sort: settings present & has_app first, root-most path next (shortest parts)
    candidates.sort(key=lambda x: (not x[1], not x[2], len(x[0].parts)))
    g, _, _, modules = candidates[0]
    try:
        g.chmod(0o755)
    except Exception:
        pass
    return g, g.parent, modules

def probe_android():
    g, gdir, modules = pick_best_gradlew()
    if not g:
        # no wrapper found, generic attempt
        return "./gradlew assembleDebug --stacktrace"

    # query tasks
    out, _ = sh(f"./{g.name} -q tasks --all", cwd=gdir)
    def task_exists(t):
        return re.search(rf"(^|\s){re.escape(t)}(\s|$)", out) is not None

    # ranked tasks (plain then module-specific)
    base_tasks = ["assembleDebug", "bundleDebug", "assembleRelease", "bundleRelease", "build"]
    module_tasks = []
    # prefer real app modules from settings
    for m in modules:
        if module_is_android_app(gdir, m):
            for t in ("assembleDebug","bundleDebug","assembleRelease","bundleRelease"):
                module_tasks.append(f":{m}:{t}")
    # common guesses
    for guess in ("app","mobile","android"):
        for t in ("assembleDebug","bundleDebug","assembleRelease","bundleRelease"):
            module_tasks.append(f":{guess}:{t}")

    for t in base_tasks:
        if task_exists(t):
            return f'cd {shlex.quote(str(gdir))} && ./gradlew {t} --stacktrace'
    for t in module_tasks:
        if task_exists(t):
            return f'cd {shlex.quote(str(gdir))} && ./gradlew {t} --stacktrace'
    # final fallback
    return f'cd {shlex.quote(str(gdir))} && ./gradlew assembleDebug --stacktrace'

# ---------------- CMake ----------------
def score_cmakelists(cmake_file: Path):
    txt = cmake_file.read_text(errors="ignore").lower()
    score = 0
    for kw in ("project(", "add_executable(", "find_package(", "add_library("):
        if kw in txt:
            score += 2
    score += min(50, count_sources(cmake_file.parent))  # proximity to sources helps
    # slightly prefer top-level (short path)
    score += max(0, 10 - len(cmake_file.parts))
    return score

def probe_cmake():
    cmakes = find_all(["CMakeLists.txt", "**/CMakeLists.txt"])
    if not cmakes:
        return "echo 'No CMakeLists.txt found' && exit 1"
    # choose best scoring one
    best = max(cmakes, key=score_cmakelists)
    d = best.parent
    outdir = f'build/{str(d.relative_to(ROOT)).replace("/", "_")}'
    return f'cmake -S "{d}" -B "{outdir}" && cmake --build "{outdir}" -j'

# ---------------- Linux (Make/Meson/Ninja) ----------------
def probe_linux():
    mk = find_all(["Makefile", "**/Makefile"])
    if mk:
        # pick the Makefile closest to repo root (shortest path)
        mk.sort(key=lambda p: len(p.parts))
        return f'make -C "{mk[0].parent}" -j'
    mb = find_all(["meson.build", "**/meson.build"])
    if mb:
        # pick meson closest to root
        mb.sort(key=lambda p: len(p.parts))
        d = mb[0].parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    bn = find_all(["build.ninja", "**/build.ninja"])
    if bn:
        bn.sort(key=lambda p: len(p.parts))
        return f'ninja -C "{bn[0].parent}"'
    return "echo 'No Makefile/meson.build/build.ninja found' && exit 1"

# ---------------- Node ----------------
def probe_node():
    pj = find_all(["package.json", "**/package.json"])
    if not pj:
        return "echo 'No package.json found' && exit 1"
    # pick the one closest to root
    pj.sort(key=lambda p: len(p.parts))
    d = pj[0].parent
    # resolve scripts:build?
    txt = pj[0].read_text(errors="ignore")
    has_build = re.search(r'"scripts"\s*:\s*{[^}]*"build"\s*:', txt) is not None
    if has_build:
        return f'cd "{d}" && npm ci && npm run build'
    return f'cd "{d}" && npm ci && npm run build --if-present'

# ---------------- Python ----------------
def probe_python():
    py = find_all(["pyproject.toml","setup.py","**/pyproject.toml","**/setup.py"])
    if not py:
        return "echo 'No python project found' && exit 1"
    py.sort(key=lambda p: len(p.parts))
    d = py[0].parent
    return f'cd "{d}" && pip install -e . && (pytest || python -m pytest || true)'

# ---------------- Other ecosystems ----------------
def probe_rust():
    # cargo finds workspace automatically
    return "cargo build --locked --all-targets --verbose"

def probe_dotnet():
    return "dotnet restore && dotnet build -c Release"

def probe_maven():
    # mvn figures root by pom.xml in cwd, but we prefer top-most pom.xml
    p = find_first(["pom.xml", "**/pom.xml"])
    if p:
        return f'cd "{p.parent}" && mvn -B package --file pom.xml'
    return "mvn -B package --file pom.xml"

def probe_flutter():
    p = find_first(["pubspec.yaml","**/pubspec.yaml"])
    if p:
        return f'cd "{p.parent}" && flutter build apk --debug'
    return "flutter build apk --debug"

def probe_go():
    p = find_first(["go.mod","**/go.mod"])
    if p:
        return f'cd "{p.parent}" && go build ./...'
    return "go build ./..."

def probe_bazel():
    # build all targets
    return "bazel build //..."

def probe_scons():
    # parallel scons
    return "scons -Q -j$(nproc)"

def probe_ninja():
    p = find_first(["build.ninja","**/build.ninja"])
    if p:
        return f'ninja -C "{p.parent}"'
    return "ninja -C build"

# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True,
        choices=["android","cmake","linux","node","python","rust",
                 "dotnet","maven","flutter","go","bazel","scons","ninja","unknown"])
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
    elif args.type == "bazel": cmd = probe_bazel()
    elif args.type == "scons": cmd = probe_scons()
    elif args.type == "ninja": cmd = probe_ninja()
    else: cmd = "echo 'No build system detected' && exit 1"

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())