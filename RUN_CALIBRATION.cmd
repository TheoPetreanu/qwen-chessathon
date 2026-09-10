@echo off
cd /d C:\Users\theop\Documents\chessathon
del /q calib_*.log calibrate.log 2>nul
.venv\Scripts\python.exe tests\calibrate.py --start 2400 --step 300 --pairs 8 --base 10000 --inc 100 --workers 3
echo.
echo ===== DONE =====
pause
