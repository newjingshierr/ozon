@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "D:\ozo"
python automation\run.py --dry-run
echo.
pause
endlocal
