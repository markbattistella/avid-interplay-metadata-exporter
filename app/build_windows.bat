@echo off
cd /d "%~dp0"

echo ============================================================
echo  MediaCentral Explorer - Windows Build
echo ============================================================

pip install -r requirements.txt
pip install "pyinstaller>=6.0.0"

python build.py

echo.
echo Build complete.
echo   Folder   : dist\MCExplorer\
echo   Installer: dist\MCExplorer-Setup.exe
pause
