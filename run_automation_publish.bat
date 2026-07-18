@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "D:\ozo"
if not exist "automation\logs" mkdir "automation\logs"
python automation\run.py --publish >> "automation\logs\scheduled.log" 2>&1
endlocal
