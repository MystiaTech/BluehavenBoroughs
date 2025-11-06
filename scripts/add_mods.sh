#!/usr/bin/env bash
set -euo pipefail

MODE="print"
if [[ "${1:-}" == "--apply" ]]; then
  MODE="apply"
  shift
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

python3 - "$MODE" "$SCRIPT_DIR" "$@" <<'PY'
import json
import shutil
import subprocess
import sys
from pathlib import Path

mode = sys.argv[1]
script_dir = Path(sys.argv[2])
extra_args = sys.argv[3:]
mod_sources_path = script_dir / "mod_sources.json"
if not mod_sources_path.exists():
    sys.exit(
        "mod_sources.json is missing. Run scripts/generate_mod_sources.py to fetch mod metadata."
    )

data = json.loads(mod_sources_path.read_text())
packwiz_path = shutil.which("packwiz")
if mode == "apply" and packwiz_path is None:
    sys.exit("packwiz is not available on PATH; cannot apply commands.")

def emit(cmd: list[str]) -> str:
    return " ".join(cmd)

missing: list[str] = []
missing_versions: list[str] = []
for entry in data.get("mods", []):
    name = entry.get("name", "<unknown>")
    version = entry.get("version") or "unspecified"
    mr_project = entry.get("modrinth") or {}
    mr_version = entry.get("modrinth_version") or {}
    cf_project = entry.get("curseforge") or {}
    cf_version = entry.get("curseforge_file") or {}

    command: list[str] | None = None
    provider: str | None = None

    if mr_project and mr_version:
        command = ["packwiz", "modrinth", "add", mr_project["slug"], "--version", mr_version["id"]]
        provider = "modrinth"
    elif cf_project and cf_version:
        command = [
            "packwiz",
            "curseforge",
            "add",
            str(cf_project.get("id")),
            "--file-id",
            str(cf_version.get("id")),
        ]
        provider = "curseforge"
    elif mr_project:
        command = ["packwiz", "modrinth", "add", mr_project["slug"]]
        provider = "modrinth (no version match)"
        missing_versions.append(f"{name} ({version}) - Modrinth version not matched")
    elif cf_project:
        command = ["packwiz", "curseforge", "add", str(cf_project.get("id"))]
        provider = "curseforge (no version match)"
        missing_versions.append(f"{name} ({version}) - CurseForge file not matched")
    else:
        missing.append(f"{name} ({version})")
        continue

    if mode == "apply":
        subprocess.run(command + extra_args, check=True)
    else:
        print(f"# {name} (version {version}) via {provider}")
        print(emit(command + list(extra_args)))
        print()

if missing:
    sys.stderr.write("Missing provider matches for:\n")
    for entry in missing:
        sys.stderr.write(f"  - {entry}\n")
    sys.stderr.flush()
if missing_versions:
    sys.stderr.write("\nEntries without an environment-matched release:\n")
    for entry in missing_versions:
        sys.stderr.write(f"  - {entry}\n")
    sys.stderr.flush()
PY
