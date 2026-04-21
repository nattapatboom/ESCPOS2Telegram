#!/bin/bash
echo "🗑️ กำลังหยุดและลบระบบทั้งหมด (Container และ Network)..."

# ปิดระบบ ลบ Container ลบ Network แต่ไม่ลบไฟล์โค้ด (Volumes)
docker-compose down

echo ""
echo "✅ ระบบถูกล้างออกเรียบร้อยแล้ว!"
echo "📌 (หากต้องการเริ่มระบบใหม่ทั้งหมดตั้งแต่ศูนย์ ให้ใช้คำสั่ง ./start.sh)"
