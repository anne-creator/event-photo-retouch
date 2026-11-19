#!/usr/bin/env bash
set -euo pipefail
version="${EVENT_PHOTO_VERSION:-v0.2.0}"
source_dir=""
models_from=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) source_dir="$2"; shift 2 ;;
    --models-from) models_from="$2"; shift 2 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
scratch="$(mktemp -d)"
staging=""
cleanup() {
  rm -rf -- "$scratch"
  if [[ -n "$staging" && -d "$staging" ]]; then rm -rf -- "$staging"; fi
}
trap cleanup EXIT
python_ok() { "$1" -c 'import sys; sys.exit(not ((3,11) <= sys.version_info < (3,15)))' >/dev/null 2>&1; }
python_bin="${PYTHON:-}"
if [[ -n "$python_bin" ]]; then
  python_ok "$python_bin" || { printf '%s\n' 'PYTHON must point to Python 3.11 through 3.14' >&2; exit 1; }
else
  for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$candidate"; then
      python_bin="$(command -v "$candidate")"; break
    fi
  done
fi
if [[ -z "$python_bin" ]]; then
  uv_bin="$(command -v uv || true)"
  if [[ -z "$uv_bin" ]]; then
    printf '%s\n' 'Provisioning a private Python runtime with uv.'
    curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o "$scratch/uv-install.sh"
    UV_INSTALL_DIR="$scratch/uv" UV_NO_MODIFY_PATH=1 sh "$scratch/uv-install.sh"
    uv_bin="$scratch/uv/uv"
  fi
  export UV_PYTHON_INSTALL_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/event-photo-retouch/python"
  "$uv_bin" python install 3.11 --quiet
  python_bin="$("$uv_bin" python find --managed-python 3.11)"
fi
if [[ -z "$source_dir" ]]; then
  curl --fail --location --silent --show-error "https://github.com/anne-creator/event-photo-retouch/archive/refs/tags/$version.tar.gz" -o "$scratch/source.tar.gz"
  "$python_bin" - "$scratch" <<'PY'
import pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1])
with tarfile.open(p/'source.tar.gz') as tar:
    for member in tar.getmembers():
        dest=(p/member.name).resolve()
        if not dest.is_relative_to(p.resolve()) or not (member.isfile() or member.isdir()):
            raise SystemExit('Unsafe archive member')
    tar.extractall(p)
PY
  for candidate in "$scratch"/event-photo-retouch-*; do
    [[ -f "$candidate/SKILL.md" ]] && source_dir="$candidate"
  done
fi
[[ -n "$source_dir" && -f "$source_dir/SKILL.md" ]] || { printf '%s\n' 'Invalid source directory' >&2; exit 1; }
skill_root="${CODEX_HOME:-$HOME/.codex}/skills"
destination="$skill_root/event-photo-retouch"
mkdir -p "$skill_root"
staging="$(mktemp -d "$skill_root/.event-photo-retouch.XXXXXX")"
for entry in SKILL.md scripts references requirements.txt run.sh models.json LICENSE NOTICE third_party; do
  cp -R -- "$source_dir/$entry" "$staging/$entry"
done
"$python_bin" -m venv "$staging/.venv"
"$staging/.venv/bin/python" -m pip install --disable-pip-version-check --quiet -r "$staging/requirements.txt"
if [[ -n "$models_from" ]]; then
  "$staging/.venv/bin/python" "$staging/scripts/download_models.py" --from-dir "$models_from"
else
  "$staging/.venv/bin/python" "$staging/scripts/download_models.py"
fi
chmod +x "$staging/run.sh"
if [[ -e "$destination" ]]; then
  backup_root="${CODEX_HOME:-$HOME/.codex}/skill-backups"
  mkdir -p "$backup_root"
  backup="$backup_root/event-photo-retouch.$(date +%Y%m%d%H%M%S).$$"
  mv -- "$destination" "$backup"
  printf 'Previous skill backed up: %s\n' "$backup"
fi
mv -- "$staging" "$destination"
staging=""
"$destination/run.sh" doctor
printf 'Installed: %s\nInvoke in Codex: $event-photo-retouch\n' "$destination"
