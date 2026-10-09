@echo off
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile --name "uBox Updater" --add-data "firmware;firmware" run_updater.py
echo Built: dist\uBox Updater.exe
