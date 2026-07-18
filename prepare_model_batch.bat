@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
cd /d "D:\ozo"
python automation\run.py prepare --limit 20
echo.
echo Model input created. Use the Codex Scheduled task to write the content.
pause
endlocal
