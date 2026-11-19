#!/bin/sh
set -eu
cd "$(dirname "$0")"
export JARVIS_DATA_DIR="${JARVIS_DATA_DIR:-$HOME/Library/Application Support/Jarvis}"
umask 077
if [ ! -x .venv/bin/python ]; then
    echo 'Setting up Jarvis with Python 3.12. The first launch needs internet.'
    python3.12 -c 'import tkinter' || { echo 'Install Python 3.12 with Tk from python.org first.'; exit 1; }
    python3.12 -m venv .venv
fi
if ! cmp -s requirements.txt .venv/jarvis-installed.txt; then
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt .venv/jarvis-installed.txt
fi
exec .venv/bin/python run_jarvis_face.py "$@"
