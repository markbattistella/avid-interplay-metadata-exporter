@echo off
echo ============================================================
echo  Interplay Project Explorer - Windows Build
echo ============================================================

:: Install runtime dependencies + build tool
pip install -r requirements.txt
pip install pyinstaller>=6.0.0

:: Build standalone exe
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "InterplayExplorer" ^
  --hidden-import "keyring.backends.Windows" ^
  --hidden-import "keyring.backends.fail" ^
  interplay_explorer.py

echo.
echo Build complete: dist\InterplayExplorer.exe
pause
