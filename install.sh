#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    PYTHONPATH="$here" exec "$py" -m codejig "$@" install
  fi
done
echo "install.sh: Python 3.11+ not found" >&2
exit 2
