#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "============================================================"
echo " MediaCentral Explorer - macOS Build"
echo "============================================================"

PYTHON=python3.13

$PYTHON -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install "pyinstaller>=6.0.0"

python build.py

deactivate

echo ""
echo "Build complete."
echo "  App : dist/MCExplorer.app"
echo "  DMG : dist/MCExplorer.dmg"
