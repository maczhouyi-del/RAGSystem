#!/usr/bin/env bash
# Read-only launcher; forwards arguments without evaluating them.
set -eu
diagnostic_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for diagnostic_python in "$diagnostic_root/.venv/bin/python" python3 python; do
  if "$diagnostic_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    exec "$diagnostic_python" "$diagnostic_root/scripts/diagnose.py" "$@"
  fi
done
echo 'python: missing — Install Python 3.11+ or create the project .venv; no files were modified.' >&2
exit 2
