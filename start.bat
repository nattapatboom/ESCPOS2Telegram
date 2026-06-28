@echo off
chcp 65001 >nul
echo 🚀 Starting ESC/POS Printer emulator (4 printers)...
echo.

:: Use --build to ensure code changes rebuild the image
docker compose up -d --build

echo.
echo ✅ System is running!
echo 📌 View live logs: docker compose logs -f
echo.
pause
