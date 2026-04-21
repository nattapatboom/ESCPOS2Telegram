@echo off
chcp 65001 >nul
echo 🚀 กำลังเริ่มต้นระบบจำลอง ESC/POS Printer (4 เครื่อง)...

:: ใช้ --build เพื่อให้แน่ใจว่าถ้ามีการแก้โค้ด มันจะสร้าง Image ใหม่ให้ด้วย
docker-compose up -d --build

echo.
echo ✅ ระบบทำงานเรียบร้อยแล้ว!
echo 📌 คุณสามารถดู Log สดๆ ได้โดยพิมพ์คำสั่ง: docker-compose logs -f
echo.
pause
