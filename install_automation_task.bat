@echo off
setlocal
rem Run this file as Administrator only when you are ready to enable scheduling.
rem The task starts at 00:15 and repeats every 240 minutes (4 hours).
schtasks /Create /F /TN "ArtBoxWorld-Ozon-SEO" /SC MINUTE /MO 240 /ST 00:15 /TR "D:\ozo\run_automation_publish.bat"
if errorlevel 1 (
  echo Failed to create the scheduled task. Try Run as administrator.
) else (
  echo Scheduled task ArtBoxWorld-Ozon-SEO was created successfully.
)
pause
endlocal
