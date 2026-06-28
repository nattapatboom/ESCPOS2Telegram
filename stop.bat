@echo off
chcp 65001 >nul
echo ⏸️ Stopping the system temporarily...
echo.

:: Stop containers without removing them
docker compose stop

echo.
echo ✅ System stopped
echo 📌 Double-click start.bat to resume
echo.
pause
