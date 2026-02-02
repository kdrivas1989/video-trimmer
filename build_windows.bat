@echo off
echo ================================
echo Building Video Trimmer for Windows
echo ================================

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.11+ from python.org
    pause
    exit /b 1
)

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

REM Build the executable
echo Building executable...
pyinstaller build_windows.spec --clean

echo.
echo ================================
echo Build complete!
echo Executable: dist\VideoTrimmer.exe
echo ================================
pause
