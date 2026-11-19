#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${EVENT_PHOTO_PYTHON:-$root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  printf '%s\n' 'Runtime missing. Run install.sh first, or set EVENT_PHOTO_PYTHON.' >&2
  exit 1
fi
command_name="${1:-help}"
if [[ $# -gt 0 ]]; then shift; fi
case "$command_name" in
  light) exec "$python_bin" "$root/scripts/lighting_field.py" "$@" ;;
  beauty) exec "$python_bin" "$root/scripts/beauty_finish.py" "$@" ;;
  doctor) exec "$python_bin" "$root/scripts/download_models.py" --check "$@" ;;
  models) exec "$python_bin" "$root/scripts/download_models.py" "$@" ;;
  *) printf '%s\n' 'Usage: run.sh {light|beauty|doctor|models} [arguments]' ;;
esac
