#!/usr/bin/env bash
set -e

# Always run from the directory containing this script
cd "$(dirname "$0")"

echo "============================================================"
echo " Interplay Project Explorer - macOS Build"
echo "============================================================"

# Use Python 3.13 which has Tk support (python-tk@3.13 must be installed via brew)
PYTHON=python3.13

# Create/activate a virtual environment for a clean build
$PYTHON -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build standalone app
pyinstaller \
  --onefile \
  --windowed \
  --name "InterplayExplorer" \
  interplay_explorer.py

deactivate

echo ""
echo "Build complete: dist/InterplayExplorer"
echo "Note: .venv/ and build/ can be deleted after packaging."
