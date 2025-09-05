#!/usr/bin/env python3
"""
AirysDark-AI_prob.py (Step 2)
- Reads detector logs + JSON
- Deep-scans entire repo (all folders/subfolders)
- Builds a concise report and (optionally) asks the AI to produce a build workflow YAML
- Writes:
    .github/workflows/AirysDark-AI_build.yml
    tools/airysdark_ai_prob_report.json
    tools/airysdark_ai_prob_report.log
    tools/airysdark_ai_build_ai_response.txt
    pr_body_build.md
"""
import os, json, pathlib, datetime, re, sys

ROOT  = pathlib.Path(os.getenv("PROJECT_DIR", ".")).resolve()
TOOLS = ROOT / "tools"
WF    = ROOT / ".github" / "workflows"
WF.mkdir(parents=True, exist_ok=True)
TOOLS.mkdir(parents=True, exist_ok=True)

TARGET = os.getenv("TARGET", "__SET_ME__").strip()

REPORT_JSON = TOOLS / "airysdark_ai_prob_report.json"
REPORT_LOG  = TOOLS / "airysdark_ai_prob_report.log"
AI_OUT_TXT  = TOOLS / "airysdark_ai_build_ai_response.txt"
PR_BODY     = ROOT / "pr_body_build.md"
OUT_WORKFLOW= WF / "AirysDark-AI_build.yml"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

def read_text(p: pathlib.Path, max_bytes=200_000):
    try:
        b = p.read_bytes()[:max_bytes]
        return b.decode("utf-8", errors="ignore")
    except Exception:
        try:
            return p.read_text(errors="ignore")
        except Exception:
            return ""

def list_repo():
    items = []
    for root, dirs, files in os.walk(ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        r = pathlib.Path(root)
        rel_dir = str(r.relative_to(ROOT)) or "."
        dir_entry = {"dir": rel_dir, "files": []}
        for fn in files:
            path = r / fn
            try:
                size = path.stat().st_size
            except Exception:
                size = -1
            ext = pathlib.Path(fn).suffix.lower()
            info = {"name": fn, "ext": ext, "size": size}
            if size >= 0 and size <= 200*1024 and ext in (".gradle",".kts",".xml",".json",".yml",".yaml",".cmake",".txt",".md",".toml",".ini",".c",".cpp",".h",".hpp",".java",".kt",".py"):
                info["preview"] = read_text(path, 40_000)
            dir_entry["files"].append(info)
        items.append(dir_entry)
    return items

def load_detector_data():
    scan_log = (TOOLS / "airysdark_ai_scan.log").read_text(errors="ignore") if (TOOLS / "airysdark_ai_scan.log").exists() else ""
    scan_json = {}
    for candidate in ["airysdark_ai_scan.json", "airysdark_ai_detected.json"]:
        p = TOOLS / candidate
        if p.exists():
            try:
                scan_json = json.loads(p.read_text(errors="ignore"))
                break
            except Exception:
                pass
    return scan_log, scan_json

def write_probe_reports(structure, detector_log, detector_json):
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    REPORT_JSON.write_text(json.dumps({"timestamp": ts,"target": TARGET,"detector_log": detector_log,"detector_json": detector_json,"structure": structure}, indent=2))
    with REPORT_LOG.open("w", encoding="utf-8") as f:
        f.write(f"[{ts}] AirysDark-AI probe report (target={TARGET})\n\n")
        f.write("Detected types (from detector): " + ", ".join(detector_json.get("types", [])) + "\n\n")
        f.write("Directory structure summary:\n")
        for d in structure[:200]:
            f.write(f"- {d['dir']}/\n")
            for fi in d["files"][:30]:
                f.write(f"   {fi['name']} (ext={fi['ext']}, size={fi['size']})\n")
        f.write("\n--- End of probe ---\n")

def extract_yaml_from_text(text):
    m = re.search(r"```yaml\s+(.+?)```", text, flags=re.S|re.I)
    if m: return m.group(1).strip()
    m = re.search(r"```[^\n]*\n(.+?)```", text, flags=re.S)
    if m: return m.group(1).strip()
    if text.strip().lower().startswith(("name:", "on:", "permissions:", "jobs:", "env:")):
        return text.strip()
    return ""

def heuristic_template(target:str) -> str:
    base_cmd = {
        "android": "bash -lc './gradlew assembleDebug --stacktrace'",
        "linux":   "bash -lc 'make -j || ( [ -d linux ] && make -C linux -j ) || true'",
        "cmake":   "bash -lc 'cmake -S . -B build && cmake --build build -j'",
        "node":    "bash -lc 'npm ci && npm run build --if-present'",
        "python":  "bash -lc 'pip install -e . && (pytest || python -m pytest || true)'",
        "rust":    "bash -lc 'cargo build --locked --all-targets --verbose'",
        "dotnet":  "bash -lc 'dotnet restore && dotnet build -c Release'",
        "maven":   "bash -lc 'mvn -B package --file pom.xml'",
        "flutter": "bash -lc 'flutter build apk --debug'",
        "go":      "bash -lc 'go build ./...'",
        "bazel":   "bash -lc 'bazel build //... || true'",
        "scons":   "bash -lc 'scons -j$(nproc) || true'",
        "ninja":   "bash -lc 'ninja -C build || true'",
        "unknown": "bash -lc 'echo no-known-build-system && exit 1'"
    }.get(target, "bash -lc 'echo no-known-build-system && exit 1'")

    return f"""name: AirysDark-AI - Build ({target})

on:
  workflow_dispatch: {{}}  # manual only

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: actions/setup-python@v5
        with: {{ python-version: "3.11" }}

      - name: Install basics (best-effort)
        run: |
          sudo apt-get update
          sudo apt-get install -y git curl ca-certificates

      - name: Build ({target})
        run: {base_cmd}

      - name: Upload outputs (best-effort)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: {target}-outputs
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
            **/*.whl
            **/outputs/**/*.apk
            **/outputs/**/*.aab
"""

def call_openai(messages):
    import requests
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    data = {"model": OPENAI_MODEL, "messages": messages, "temperature": 0.2}
    r = requests.post(url, headers=headers, json=data, timeout=180)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"]

def synthesize_workflow_with_ai(target, detector_log, detector_json, structure):
    # Compact, bounded structure summary to fit context
    lines = []
    max_dirs = 150
    max_files_per_dir = 25
    for d in structure[:max_dirs]:
        lines.append(f"- {d['dir']}/")
        for fi in d["files"][:max_files_per_dir]:
            nm = fi["name"]; ex = fi["ext"]
            lines.append(f"   {nm} (ext={ex})")
    structure_text = "\n".join(lines)

    sys_prompt = (
        "You are a GitHub Actions expert. Given a repository scan and a target platform, "
        "write a single, correct GitHub Actions workflow YAML file that builds the project."
    )
    user_prompt = f"""
Target platform: {target}

Constraints:
- The workflow's filename will be .github/workflows/AirysDark-AI_build.yml
- It MUST trigger only on: workflow_dispatch
- It MUST NOT auto-run on push or pull_request
- It MUST include needed setup steps for {target} (e.g., Java/Android SDK, CMake, Node, etc.)
- Prefer reproducible, standard steps. Avoid secrets or PAT use here.
- Upload typical build artifacts (build/, out/, dist/, target/, APK/AAB/whl, etc.)
- Output ONLY a YAML workflow (no backticks, no prose). If unsure, provide a safe baseline for {target}.

Detector summary (truncated):
{detector_log[:5000]}

Detected types (JSON): {json.dumps(detector_json.get('types', []))}

Repo structure (trimmed):
{structure_text[:20000]}
""".strip()

    messages = [
        {"role":"system","content":sys_prompt},
        {"role":"user","content":user_prompt}
    ]
    text = call_openai(messages)
    AI_OUT_TXT.write_text(text)
    yaml = extract_yaml_from_text(text) or text.strip()
    # Force manual-only trigger
    if "on:" not in yaml.lower():
        yaml = "on:\n  workflow_dispatch: {}\n" + yaml
    yaml = re.sub(r"\bon:\s*\n(?:.*\n)*?(?=jobs:|env:|permissions:|name:|$)", "on:\n  workflow_dispatch: {}\n", yaml, count=1, flags=re.I)
    return yaml

def main():
    if TARGET == "__SET_ME__":  # guard
        print("TARGET is not set. Edit env.TARGET in the workflow and run again.", file=sys.stderr)
        sys.exit(2)

    detector_log, detector_json = load_detector_data()
    structure = list_repo()
    write_probe_reports(structure, detector_log, detector_json)

    yaml_text = ""
    if OPENAI_API_KEY:
        try:
            yaml_text = synthesize_workflow_with_ai(TARGET, detector_log, detector_json, structure)
        except Exception as e:
            print(f"OpenAI failed: {e}", file=sys.stderr)
            yaml_text = heuristic_template(TARGET)
    else:
        yaml_text = heuristic_template(TARGET)

    OUT_WORKFLOW.write_text(yaml_text)
    print(f"✅ Wrote workflow: {OUT_WORKFLOW}")

    PR_BODY.write_text(
        f"""### AirysDark-AI: build workflow (from probe)
Target: **{TARGET}**

This PR adds `.github/workflows/AirysDark-AI_build.yml`, generated by the probe.
- The workflow triggers **only** on `workflow_dispatch` (manual run required).
- Review the steps and adjust if needed.

Artifacts from the probe:
- `tools/airysdark_ai_prob_report.json`
- `tools/airysdark_ai_prob_report.log`
- `tools/airysdark_ai_build_ai_response.txt` (raw LLM output, if AI was used)
"""
    )

if __name__ == "__main__":
    main()