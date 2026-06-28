@echo off
chcp 65001 >nul
echo 🗑️ Stopping and removing all containers and networks...
echo.

:: Stop system, remove containers and networks (keeps code and volumes)
docker compose down

echo.
echo ✅ System cleaned up!
echo 📌 Double-click start.bat to start fresh
echo.
pause
