#!/usr/bin/env python3
"""
AirysDark-AI_probe.py — deep repo scan to pick the right BUILD_CMD
Priority:
  1) Parse README / docs for explicit build commands matching the requested type
  2) Infer from repo files (heuristics)
Prints exactly one line: BUILD_CMD=<command>
"""

import os, re, shlex, subprocess, sys
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from collections import Counter

ROOT = Path(".").resolve()

# ---------- scanning ----------
TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc"}
DOC_DIR_HINTS = ("docs",)
MAX_READ_BYTES = 200_000
MAX_FILES_TO_READ = 400

def scan_all_files() -> List[Tuple[str, Path]]:
    out = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = Path(root) / f
            try:
                rel = p.relative_to(ROOT)
            except Exception:
                rel = p
            out.append((f.lower(), rel))
    return out

def safe_read_text(p: Path) -> str:
    try:
        raw = (ROOT / p).read_bytes()
        if len(raw) > MAX_READ_BYTES:
            raw = raw[:MAX_READ_BYTES]
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def collect_text_corpus() -> str:
    files = scan_all_files()
    picked: List[Path] = []

    # Priority 1: README*
    for name, rel in files:
        if Path(rel.name.lower()).name.startswith("readme"):
            picked.append(rel)

    # Priority 2: text extensions anywhere
    for name, rel in files:
        if len(picked) >= MAX_FILES_TO_READ: break
        if Path(name).suffix in TEXT_EXTS:
            picked.append(rel)

    # Priority 3: docs/**
    for name, rel in files:
        if len(picked) >= MAX_FILES_TO_READ: break
        parts = [p.lower() for p in Path(rel).parts]
        if any(h in parts for h in DOC_DIR_HINTS) and Path(name).suffix in TEXT_EXTS:
            picked.append(rel)

    # Dedup preserve order
    seen = set(); ordered: List[Path] = []
    for p in picked:
        key = str(p).lower()
        if key not in seen:
            seen.add(key); ordered.append(p)

    chunks: List[str] = []
    for p in ordered[:MAX_FILES_TO_READ]:
        chunks.append(safe_read_text(p))
    return "\n\n".join(chunks)

# ---------- helpers ----------
def run(cmd: str, cwd: Optional[Path] = None, capture: bool = True):
    if capture:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.stdout, p.returncode
    else:
        p = subprocess.run(cmd, cwd=cwd, shell=True)
        return "", p.returncode

def prefer_shortest(paths: List[Path]) -> Optional[Path]:
    if not paths: return None
    return sorted(paths, key=lambda p: len(Path(str(p)).parts))[0]

def print_output_var(name: str, val: str):
    print(f"{name}={val}")

# ---------- README/doc command extraction ----------
# Map each type to patterns that should count as *that* type’s build command.
# We capture the whole command line; if multi-line code blocks contain chained commands with &&, we keep them.
TYPE_PATTERNS: Dict[str, List[re.Pattern]] = {
    "android": [
        re.compile(r"(^|\n|\r)(?:\$?\s*)?(?:\.\/)?gradlew\s+[^\n\r]+", re.I),
        re.compile(r"(^|\n|\r)(?:\$?\s*)?gradle\s+[^\n\r]+", re.I),
    ],
    "cmake": [
        re.compile(r"(^|\n|\r).*(?:cmake\s+-S\s+\S+|\bcmake\s+\.)\s+-B\s+\S+.*", re.I),
        re.compile(r"(^|\n|\r).*\bcmake\s+[-\w\/\"\. ]+&&\s*cmake\s+--build[^\n\r]*", re.I),
    ],
    "linux": [
        re.compile(r"(^|\n|\r)(?:\$?\s*)?make(\s+-C\s+\S+)?(\s+-j\S*)?", re.I),
        re.compile(r"(^|\n|\r).*\bmeson\s+setup[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\bninja(\s+-C\s+\S+)?[^\n\r]*", re.I),
    ],
    "node": [
        re.compile(r"(^|\n|\r).*\bnpm\s+(?:ci|install)\b[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\bnpm\s+run\s+build\b[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\bpnpm\s+(?:install|build)\b[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\byarn\s+(?:install|build)\b[^\n\r]*", re.I),
    ],
    "python": [
        re.compile(r"(^|\n|\r).*\bpip\s+install\b[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\bpytest\b[^\n\r]*", re.I),
        re.compile(r"(^|\n|\r).*\bpython\s+-m\s+pytest\b[^\n\r]*", re.I),
    ],
    "rust": [
        re.compile(r"(^|\n|\r).*\bcargo\s+build\b[^\n\r]*", re.I),
    ],
    "dotnet": [
        re.compile(r"(^|\n|\r).*\bdotnet\s+build\b[^\n\r]*", re.I),
    ],
    "maven": [
        re.compile(r"(^|\n|\r).*\bmvn\b[^\n\r]*", re.I),
    ],
    "flutter": [
        re.compile(r"(^|\n|\r).*\bflutter\s+build\b[^\n\r]*", re.I),
    ],
    "go": [
        re.compile(r"(^|\n|\r).*\bgo\s+build\b[^\n\r]*", re.I),
    ],
    "bazel": [
        re.compile(r"(^|\n|\r).*\bbazel(?:isk)?\s+(?:build|test)\b[^\n\r]*", re.I),
    ],
    "scons": [
        re.compile(r"(^|\n|\r).*\bscons\b[^\n\r]*", re.I),
    ],
    "ninja": [
        re.compile(r"(^|\n|\r).*\bninja(\s+-C\s+\S+)?[^\n\r]*", re.I),
    ],
}

def extract_doc_command_for_type(ptype: str, corpus: str) -> Optional[str]:
    """
    Return the first plausible command from docs for this type.
    If multiple match, pick the shortest sensible line, strip prompts, normalize whitespace.
    """
    pats = TYPE_PATTERNS.get(ptype, [])
    candidates: List[str] = []
    for pat in pats:
        for m in pat.finditer(corpus):
            line = m.group(0)
            # normalize: strip newlines, strip leading $ and spaces
            line = re.sub(r"^[\n\r\s$>]*", "", line)
            line = line.strip()
            # Avoid “mvn (something about build)” false-positives without commands
            if len(line.split()) >= 2:
                candidates.append(line)
    if not candidates:
        return None
    # Favor lines that chain the full sequence (e.g. cmake && build) but are not ridiculously long
    candidates = sorted(candidates, key=lambda s: (len(s), s))
    return candidates[0]

# ---------- file-based probers (fallbacks) ----------
def probe_linux(files: List[Tuple[str, Path]]) -> Optional[str]:
    makefiles = [p for (n, p) in files if n in ("makefile", "gnumakefile")]
    mf = prefer_shortest(makefiles)
    if mf:
        if str(mf.parent) == ".":
            return "make -j"
        return f'make -C "{mf.parent}" -j'
    # Meson/Ninja
    mesons = [p for (n, p) in files if n == "meson.build"]
    mb = prefer_shortest(mesons)
    if mb:
        d = mb.parent
        return f'(cd "{d}" && (meson setup build --wipe || true); meson setup build || true; ninja -C build)'
    # Only .mk files
    mk_paths = [p for (n, p) in files if str(p).lower().endswith(".mk")]
    if mk_paths:
        cnt = Counter(str(p.parent) for p in mk_paths)
        likely_dir = Path(sorted(cnt.items(), key=lambda kv: (-kv[1], len(Path(kv[0]).parts)))[0][0])
        return f'make -C "{likely_dir}" -j'
    return None

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
    mods = []
    for raw in re.findall(r'include\s*\((.*?)\)', txt, flags=re.S):
        for p in re.split(r'[,\s]+', raw.strip()):
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    for raw in re.findall(r'include\s+([^\n]+)', txt):
        for p in raw.split(","):
            s = p.strip().strip('"\'')

            if s.startswith(":"):
                mods.append(s[1:])
    out, seen = [], set()
    for m in mods:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out

def run_tasks_list(gradlew: Path) -> str:
    out, _ = run(f"./{gradlew.name} -q tasks --all", cwd=gradlew.parent)
    return out

def task_exists(tasks_out: str, name: str) -> bool:
    return re.search(rf"(^|\s){re.escape(name)}(\s|$)", tasks_out) is not None

def probe_android(files: List[Tuple[str, Path]]) -> Optional[str]:
    gradlews = [p for (n, p) in files if n == "gradlew"]
    if not gradlews and (ROOT / "gradlew").exists():
        gradlews = [Path("gradlew")]
    if not gradlews:
        return "./gradlew assembleDebug --stacktrace"
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
        ranked.append((g, settings is not None, has_app))
    ranked.sort(key=lambda x: (not x[1], not x[2], len(Path(str(x[0])).parts)))
    g = ranked[0][0]
    g_abs = (ROOT / g)
    try: os.chmod(g_abs, 0o755)
    except Exception: pass

    tasks_out = run_tasks_list(g_abs)
    base = shlex.quote(str(g_abs.parent))
    for t in ["assembleDebug","bundleDebug","assembleRelease","bundleRelease","build"]:
        if task_exists(tasks_out, t):
            return f"cd {base} && ./gradlew {t} --stacktrace"
    for guess in ("app","mobile","android"):
        for t in ["assembleDebug","bundleDebug","assembleRelease","bundleRelease"]:
            if task_exists(tasks_out, f":{guess}:{t}"):
                return f"cd {base} && ./gradlew :{guess}:{t} --stacktrace"
    return f"cd {base} && ./gradlew assembleDebug --stacktrace"

def probe_cmake(files: List[Tuple[str, Path]]) -> Optional[str]:
    cmakes = [p for (n, p) in files if n == "cmakelists.txt"]
    first = prefer_shortest(cmakes)
    if not first: return None
    outdir = f'build/{str(first.parent).replace("/", "_")}'
    return f'cmake -S "{first.parent}" -B "{outdir}" && cmake --build "{outdir}" -j'

def probe_node(files: List[Tuple[str, Path]]) -> Optional[str]:
    pkgs = [p for (n, p) in files if n == "package.json"]
    if not pkgs: return None
    def has_build_script(pkg_path: Path) -> bool:
        try: txt = (ROOT / pkg_path).read_text(errors="ignore")
        except Exception: return False
        return re.search(r'"scripts"\s*:\s*{[^}]*"build"\s*:', txt, flags=re.S) is not None
    with_build = [p for p in pkgs if has_build_script(p)]
    chosen = prefer_shortest(with_build) or prefer_shortest(pkgs)
    return f'cd "{chosen.parent}" && npm ci && npm run build --if-present'

def probe_python(files: List[Tuple[str, Path]]) -> Optional[str]:
    pyprojects = [p for (n, p) in files if n == "pyproject.toml"]
    setups     = [p for (n, p) in files if n == "setup.py"]
    chosen = prefer_shortest(pyprojects) or prefer_shortest(setups)
    if not chosen: return None
    d = chosen.parent
    return f'cd "{d}" && pip install -e . && (pytest || python -m pytest || true)'

def probe_rust(files: List[Tuple[str, Path]]) -> Optional[str]:
    cargos = [p for (n, p) in files if n == "cargo.toml"]
    chosen = prefer_shortest(cargos)
    if not chosen: return None
    return f'cd "{chosen.parent}" && cargo build --locked --all-targets --verbose'

def probe_dotnet(files: List[Tuple[str, Path]]) -> Optional[str]:
    slns = [p for (n, p) in files if str(p).lower().endswith(".sln")]
    if slns:
        chosen = prefer_shortest(slns)
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    csfs = [p for (n, p) in files if str(p).lower().endswith((".csproj",".fsproj"))]
    chosen = prefer_shortest(csfs)
    if chosen:
        return f'dotnet restore "{chosen}" && dotnet build "{chosen}" -c Release'
    return None

def probe_maven(files: List[Tuple[str, Path]]) -> Optional[str]:
    poms = [p for (n, p) in files if n == "pom.xml"]
    chosen = prefer_shortest(poms)
    if not chosen: return None
    return f'mvn -B package --file "{chosen}"'

def probe_flutter(files: List[Tuple[str, Path]]) -> Optional[str]:
    pubs = [p for (n, p) in files if n == "pubspec.yaml"]
    chosen = prefer_shortest(pubs)
    if not chosen: return None
    return f'cd "{chosen.parent}" && flutter build apk --debug'

def probe_go(files: List[Tuple[str, Path]]) -> Optional[str]:
    mods = [p for (n, p) in files if n == "go.mod"]
    chosen = prefer_shortest(mods)
    if not chosen: return None
    return f'cd "{chosen.parent}" && go build ./...'

def probe_bazel(files: List[Tuple[str, Path]]) -> Optional[str]:
    workspaces = [p for (n, p) in files if n in ("workspace", "workspace.bazel", "module.bazel")]
    builds     = [p for (n, p) in files if n in ("build", "build.bazel")]
    root = prefer_shortest(workspaces) or prefer_shortest(builds)
    if not root: return None
    d = root.parent
    return f'cd "{d}" && (command -v bazelisk >/dev/null 2>&1 && bazelisk build //... || bazel build //...)'

def probe_scons(files: List[Tuple[str, Path]]) -> Optional[str]:
    sconstructs = [p for (n, p) in files if n == "sconstruct"]
    sconss      = [p for (n, p) in files if n == "sconscript"]
    chosen = prefer_shortest(sconstructs) or prefer_shortest(sconss)
    if not chosen: return None
    d = chosen.parent
    return f'scons -C "{d}" -j'

def probe_ninja(files: List[Tuple[str, Path]]) -> Optional[str]:
    ninjas = [p for (n, p) in files if n == "build.ninja"]
    chosen = prefer_shortest(ninjas)
    if not chosen: return None
    return f'ninja -C "{chosen.parent}"'

# ---------- main ----------
def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--type":
        print("Usage: AirysDark-AI_probe.py --type <android|cmake|linux|node|python|rust|dotnet|maven|flutter|go|bazel|scons|ninja|unknown>")
        return 2
    ptype = sys.argv[2].strip().lower()

    # 1) Docs/README parsing — highest priority
    corpus_raw = collect_text_corpus()
    corpus = corpus_raw  # keep original case for commands, regex is case-insensitive
    doc_cmd = extract_doc_command_for_type(ptype, corpus)
    if doc_cmd:
        # Normalize some common “cd path && cmd” patterns but otherwise preserve
        # Executable bit for gradlew will be handled by the workflow build step.
        print_output_var("BUILD_CMD", doc_cmd)
        return 0

    # 2) File-based probing — fallback
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
        "bazel":   probe_bazel,
        "scons":   probe_scons,
        "ninja":   probe_ninja,
        "unknown": lambda _f: "echo 'No build system detected' && exit 1",
    }

    func = dispatch.get(ptype, dispatch["unknown"])
    cmd = func(files)

    if not cmd:
        # Friendly error lines so the workflow UI is clear
        friendly = {
            "linux":   "echo 'No Makefile / meson.build found (only .mk includes?)' && exit 1",
            "cmake":   "echo 'No CMakeLists.txt found' && exit 1",
            "bazel":   "echo 'No Bazel WORKSPACE / BUILD found' && exit 1",
            "scons":   "echo 'No SConstruct / SConscript found' && exit 1",
            "ninja":   "echo 'No build.ninja found' && exit 1",
        }
        cmd = friendly.get(ptype, "echo 'No build system detected' && exit 1")

    print_output_var("BUILD_CMD", cmd)
    return 0

if __name__ == "__main__":
    sys.exit(main())