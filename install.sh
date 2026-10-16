#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
if ! command -v git >/dev/null 2>&1; then
  echo "install.sh: git not found (Fedora: sudo dnf install git; Debian/Ubuntu: sudo apt install git; macOS: xcode-select --install)" >&2
  exit 2
fi
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1; then
    PYTHONPATH="$here" exec "$py" -m codejig "$@" install
  fi
done
echo "install.sh: Python 3.11+ not found" >&2
exit 2
