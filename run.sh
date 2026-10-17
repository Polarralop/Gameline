#!/bin/sh
# Start Gameline in the menu bar. First run sets up the venv.
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
exec .venv/bin/python -m gameline "$@"
