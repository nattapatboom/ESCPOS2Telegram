# ใช้ Python รุ่นน้ำหนักเบา (slim) เพื่อประหยัดพื้นที่
FROM python:3.11-slim

# กำหนดโฟลเดอร์ทำงานภายใน Container เป็น /app ตามที่ต้องการ
WORKDIR /app

# คัดลอกไฟล์ requirements.txt เข้าไปก่อนเพื่อติดตั้ง Library
# (การทำแบบนี้จะช่วยให้ Docker นำ Cache มาใช้ได้ หากไม่มีการเปลี่ยน dependencies)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# คัดลอกเฉพาะไฟล์โค้ดที่จำเป็นเข้าไปใน /app (เป็นค่าเริ่มต้นเผื่อไม่ได้ Mount Volume)
COPY esc_pos2telegram.py telegram_config.py escpos_analyzer.py /app/

# เปิดพอร์ต 9100 สำหรับให้โปรแกรม POS ยิงข้อมูลเข้ามา
EXPOSE 9100

# กำหนดคำสั่งเริ่มต้นเมื่อเปิด Container
# การใช้พารามิเตอร์ -u จะช่วยให้คำสั่ง print() แสดงผลออกทาง Docker log ได้ทันทีโดยไม่ถูกค้างใน Buffer
CMD ["python", "-u", "esc_pos2telegram.py"]
