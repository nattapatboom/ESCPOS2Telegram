@echo off
chcp 65001 >nul
echo ⏸️ กำลังหยุดการทำงานของระบบชั่วคราว...

:: สั่งหยุดการทำงาน แต่ไม่ลบ Container
docker-compose stop

echo.
echo ✅ ระบบถูกหยุดการทำงานแล้ว
echo 📌 (คุณสามารถดับเบิ้ลคลิกไฟล์ start.bat เพื่อให้ระบบกลับมาทำงานต่อได้ทันที)
echo.
pause
