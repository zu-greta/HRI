#!/usr/bin/env bash
# One-command setup for macOS / Linux:   bash setup.sh
set -e
cd "$(dirname "$0")"

# Pick a Python 3.11-3.13 (prefer 3.12)
PY=""
for c in python3.12 python3.13 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)'; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11-3.13 not found. macOS: brew install python@3.12"; exit 1
fi
echo "Using $($PY --version)"

[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "Setup finished. In every new terminal run:  source .venv/bin/activate"
python check_setup.py || true
