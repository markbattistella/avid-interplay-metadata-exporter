@echo off
echo ============================================================
echo  Interplay Project Explorer - Windows Build
echo ============================================================

:: Install/upgrade dependencies
pip install -r requirements.txt

:: Build standalone exe
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "InterplayExplorer" ^
  --add-data "." ^
  interplay_explorer.py

echo.
echo Build complete: dist\InterplayExplorer.exe
pause
