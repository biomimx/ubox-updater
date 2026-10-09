#!/bin/sh
# Local build (macOS/Linux). Windows: see build_local.bat
set -e
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --name "uBox Updater" --add-data "firmware:firmware" run_updater.py
echo "Built: dist/uBox Updater.app (macOS) or dist/uBox Updater/ (Linux)"
