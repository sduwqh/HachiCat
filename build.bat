@echo off
echo Building Accompet...
C:\venv-accompet\Scripts\python.exe -m PyInstaller --onedir --windowed --name Accompet --add-data "assets;assets" run.py
echo.
echo Build complete! Output in dist\Accompet\
echo Run: dist\Accompet\Accompet.exe
pause
