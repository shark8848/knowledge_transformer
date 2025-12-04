#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_FILE="$ROOT_DIR/config/plugins.yaml"
DEPEND_FILE="$ROOT_DIR/config/plugins-deps.yaml"
DEFAULT_MODULES=(
  "rag_converter.plugins.builtin.doc_to_docx"
  "rag_converter.plugins.builtin.svg_to_png"
  "rag_converter.plugins.builtin.gif_to_mp4"
  "rag_converter.plugins.builtin.webp_to_png"
  "rag_converter.plugins.builtin.audio_to_mp3"
  "rag_converter.plugins.builtin.video_to_mp4"
)

usage() {
  cat <<'EOF'
Usage: manage_plugins.sh <command> [options]

Commands:
  list                List registered plugin modules
  register <module>   Register a plugin module
  unregister <module> Remove a plugin module
  reset               Reset to builtin defaults
  
  deps list           Show all dependency requirements
  deps set <module> <pkg1> [pkg2...]
                      Set dependencies for a module
  deps remove <module>
                      Remove dependencies for a module
  deps install [module]
                      Install dependencies (all or specific module)

Options:
  --file PATH         Override plugin YAML path
  --deps PATH         Override dependency YAML path
  --no-verify         Skip import verification

Examples:
  ./manage_plugins.sh list
  ./manage_plugins.sh register custom.plugins.pdf_converter
  ./manage_plugins.sh deps set custom.plugins.pdf_converter pypdf2 pillow
  ./manage_plugins.sh deps install custom.plugins.pdf_converter
EOF
}

PLUGIN_FILE_OVERRIDE=""
DEPEND_FILE_OVERRIDE=""
VERIFY_IMPORT=1
CMD_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      shift; PLUGIN_FILE_OVERRIDE="$1"; shift;;
    --deps)
      shift; DEPEND_FILE_OVERRIDE="$1"; shift;;
    --no-verify)
      VERIFY_IMPORT=0; shift;;
    -h|--help)
      usage; exit 0;;
    *)
      CMD_ARGS+=("$1"); shift;;
  esac
done

set -- "${CMD_ARGS[@]}"

PLUGIN_FILE="${PLUGIN_FILE_OVERRIDE:-$PLUGIN_FILE}"
DEPEND_FILE="${DEPEND_FILE_OVERRIDE:-$DEPEND_FILE}"

ensure_yaml_file() {
  local file="$1"
  [[ -f "$file" ]] && return
  mkdir -p "$(dirname "$file")"
  cat <<EOF >"$file"
modules:
$(for module in "${DEFAULT_MODULES[@]}"; do printf "  - %s\n" "$module"; done)
EOF
}

read_modules() {
  [[ -f "$PLUGIN_FILE" ]] || return
  grep -E '^\s*-\s+' "$PLUGIN_FILE" | sed 's/^\s*-\s*//'
}

write_modules() {
  local modules=("$@")
  mkdir -p "$(dirname "$PLUGIN_FILE")"
  {
    echo "modules:"
    for module in "${modules[@]}"; do
      [[ -n "$module" ]] && echo "  - $module"
    done
  } >"$PLUGIN_FILE"
}

verify_import() {
  local module="$1"
  [[ $VERIFY_IMPORT -eq 0 ]] && return
  PYTHONPATH="$ROOT_DIR/src" python3 - <<PY
import importlib
try:
    importlib.import_module("$module")
except Exception as exc:
    raise SystemExit(f"Failed to import '$module': {exc}")
PY
}

cmd_list() {
  [[ -f "$PLUGIN_FILE" ]] || { echo "No plugin file found. Run 'reset' to create defaults."; return; }
  read_modules
}

cmd_register() {
  local module="${1:-}"
  [[ -n "$module" ]] || { echo "Error: Module name required"; exit 1; }
  ensure_yaml_file "$PLUGIN_FILE"
  mapfile -t modules < <(read_modules)
  for existing in "${modules[@]}"; do
    [[ "$existing" == "$module" ]] && { echo "Module '$module' already registered"; return; }
  done
  verify_import "$module"
  modules+=("$module")
  write_modules "${modules[@]}"
  echo "✓ Registered plugin module: $module"
}

cmd_unregister() {
  local module="${1:-}"
  [[ -n "$module" ]] || { echo "Error: Module name required"; exit 1; }
  [[ -f "$PLUGIN_FILE" ]] || { echo "No plugin file found"; return; }
  mapfile -t modules < <(read_modules)
  local new_modules=()
  local removed=0
  for existing in "${modules[@]}"; do
    if [[ "$existing" == "$module" ]]; then
      removed=1
      continue
    fi
    new_modules+=("$existing")
  done
  write_modules "${new_modules[@]}"
  if (( removed )); then
    echo "✓ Removed plugin module: $module"
  else
    echo "Module '$module' not found"
  fi
}

cmd_reset() {
  write_modules "${DEFAULT_MODULES[@]}"
  echo "✓ Plugin modules reset to builtin defaults"
}

cmd_deps_list() {
  [[ -f "$DEPEND_FILE" ]] || { echo "No dependency file found"; return; }
  python3 - <<PY
import yaml
from pathlib import Path
path = Path("$DEPEND_FILE")
if not path.exists():
    exit(0)
with path.open('r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}
deps = data.get('dependencies', {})
if not deps:
    print("No dependencies registered")
else:
    for module, pkgs in deps.items():
        print(f"{module}: {' '.join(pkgs or [])}")
PY
}

cmd_deps_set() {
  local module="${1:-}"
  shift || true
  local pkgs=("$@")
  [[ -n "$module" ]] || { echo "Error: Module name required"; exit 1; }
  [[ ${#pkgs[@]} -gt 0 ]] || { echo "Error: At least one package required"; exit 1; }
  
  mkdir -p "$(dirname "$DEPEND_FILE")"
  python3 - <<PY
import yaml
from pathlib import Path
path = Path("$DEPEND_FILE")
if path.exists():
    with path.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
else:
    data = {}
deps = data.setdefault('dependencies', {})
module = "$module"
pkgs = [$(printf '"%s",' "${pkgs[@]}")]
deps[module] = pkgs
with path.open('w', encoding='utf-8') as f:
    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
print(f"✓ Set dependencies for {module}: {' '.join(pkgs)}")
PY
}

cmd_deps_remove() {
  local module="${1:-}"
  [[ -n "$module" ]] || { echo "Error: Module name required"; exit 1; }
  [[ -f "$DEPEND_FILE" ]] || { echo "No dependency file found"; return; }
  
  python3 - <<PY
import yaml
from pathlib import Path
path = Path("$DEPEND_FILE")
with path.open('r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}
deps = data.get('dependencies', {})
module = "$module"
if module in deps:
    del deps[module]
    with path.open('w', encoding='utf-8') as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"✓ Removed dependencies for {module}")
else:
    print(f"No dependencies found for {module}")
PY
}

cmd_deps_install() {
  local target_module="${1:-}"
  [[ -f "$DEPEND_FILE" ]] || { echo "No dependency file found"; return; }
  
  if [[ -n "$target_module" ]]; then
    echo "Installing dependencies for: $target_module"
    python3 - <<PY
import yaml, subprocess, sys
from pathlib import Path
path = Path("$DEPEND_FILE")
with path.open('r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}
deps = data.get('dependencies', {})
module = "$target_module"
if module not in deps:
    print(f"No dependencies found for {module}")
    sys.exit(0)
pkgs = deps[module]
if pkgs:
    print(f"Installing: {' '.join(pkgs)}")
    subprocess.run([sys.executable, '-m', 'pip', 'install'] + pkgs, check=True)
else:
    print(f"No packages to install for {module}")
PY
  else
    echo "Installing all plugin dependencies..."
    python3 - <<PY
import yaml, subprocess, sys
from pathlib import Path
path = Path("$DEPEND_FILE")
with path.open('r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}
deps = data.get('dependencies', {})
all_pkgs = set()
for module, pkgs in deps.items():
    if pkgs:
        all_pkgs.update(pkgs)
if all_pkgs:
    pkgs_list = sorted(all_pkgs)
    print(f"Installing: {' '.join(pkgs_list)}")
    subprocess.run([sys.executable, '-m', 'pip', 'install'] + pkgs_list, check=True)
else:
    print("No dependencies to install")
PY
  fi
  echo "✓ Installation complete"
}

# Main command dispatcher
[[ $# -eq 0 ]] && { usage; exit 1; }

case "$1" in
  list)
    cmd_list;;
  register)
    shift; cmd_register "$@";;
  unregister)
    shift; cmd_unregister "$@";;
  reset)
    cmd_reset;;
  deps)
    [[ $# -lt 2 ]] && { echo "Error: deps subcommand required"; usage; exit 1; }
    case "$2" in
      list)
        cmd_deps_list;;
      set)
        shift 2; cmd_deps_set "$@";;
      remove)
        shift 2; cmd_deps_remove "$@";;
      install)
        shift 2; cmd_deps_install "$@";;
      *)
        echo "Error: Unknown deps subcommand: $2"; usage; exit 1;;
    esac
    ;;
  -h|--help)
    usage;;
  *)
    echo "Error: Unknown command: $1"; usage; exit 1;;
esac
