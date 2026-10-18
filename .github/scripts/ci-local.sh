#!/bin/bash
set -eu
cd "$(git rev-parse --show-toplevel)"
export PYTHONDONTWRITEBYTECODE=1
echo "ci-local: ruff"
ruff check codejig tests .github/scripts
echo "ci-local: unit tests"
python -m unittest discover -s tests
echo "ci-local: coverage gate"
python -m coverage run --branch --include='codejig/*' -m unittest discover -s tests -t . >/dev/null 2>&1 || true
python -m coverage report --fail-under=93 >/dev/null
echo "ci-local: reuse"
reuse lint -q
