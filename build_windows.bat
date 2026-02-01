@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building Video Trimmer app...
python build_app.py

echo.
echo Done! Check dist\VideoTrimmer\ for the app.
pause
