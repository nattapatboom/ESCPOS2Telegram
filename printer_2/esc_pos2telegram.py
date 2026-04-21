#!/usr/bin/env python3
import socket
import threading
import datetime
import sys
import io
import telegram_config
import concurrent.futures

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

HOST = '0.0.0.0'
PORT = 9100

def send_to_telegram(img):
    """ส่งรูปภาพเข้าแชท Telegram ผ่าน Bot API"""
    if not HAS_REQUESTS:
        print("❌ ไม่สามารถส่งเข้า Telegram ได้ กรุณาติดตั้ง requests โดยรัน: pip install requests")
        return
        
    if telegram_config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not telegram_config.BOT_TOKEN:
        print("⚠️ ไม่สามารถส่งได้: ยังไม่ได้ใส่ BOT_TOKEN ในไฟล์ telegram_config.py")
        return
        
    print("🚀 กำลังส่งรูปภาพใบเสร็จเข้า Telegram...")
    url = f"https://api.telegram.org/bot{telegram_config.BOT_TOKEN}/sendPhoto"
    
    # ดึงข้อมูลภาพจาก Memory แทนที่จะอ่านจากไฟล์
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    try:
        response = requests.post(
            url,
            data={"chat_id": telegram_config.CHAT_ID},
            files={"photo": ("receipt.png", img_byte_arr, "image/png")},
            timeout=15
        )
        if response.status_code == 200:
            print("✅ ส่งรูปภาพเข้า Telegram สำเร็จ!")
        else:
            print(f"❌ ส่ง Telegram ล้มเหลว: {response.text}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดขณะส่ง Telegram: {e}")

def extract_all_raster_images(data):
    """ดึงคำสั่งภาพแบบ Raster (GS v 0) ออกมาต่อกันเป็นรูป แล้วส่งกลับเป็น Image Object"""
    if not HAS_PIL:
        print("❌ ไม่สามารถสร้างรูปภาพได้ กรุณาติดตั้ง Pillow โดยรัน: pip install Pillow")
        return None
        
    idx = 0
    images_data = []
    total_height = 0
    max_width = 0
    
    while True:
        idx = data.find(b'\x1d\x76\x30', idx)
        if idx == -1:
            idx = data.find(b'\x1d\x76\x30', idx)
            if idx == -1:
                break
            
        if idx + 7 > len(data):
            break
            
        m = data[idx+3]
        xL = data[idx+4]
        xH = data[idx+5]
        yL = data[idx+6]
        yH = data[idx+7]
        
        width_bytes = xL + (xH * 256)
        height_dots = yL + (yH * 256)
        
        expected_data_len = width_bytes * height_dots
        if expected_data_len <= 0:
            idx += 8
            continue
            
        actual_len = min(expected_data_len, len(data) - (idx + 8))
        img_data = data[idx+8 : idx+8+actual_len]
        
        images_data.append({
            'width_bytes': width_bytes,
            'height_dots': height_dots,
            'data': img_data
        })
        
        total_height += height_dots
        max_width = max(max_width, width_bytes * 8)
        
        idx += 8 + actual_len

    if not images_data:
        return None
        
    print(f"\n🖼️ ตรวจพบคำสั่งรูปภาพทั้งหมด {len(images_data)} ส่วน (ความกว้าง {max_width}px, ความสูงรวม {total_height}px)")
    print("⏳ กำลังประมวลผลประกอบรูปภาพ...")
    
    img = Image.new('RGB', (max_width, total_height), color='white')
    draw = ImageDraw.Draw(img)
    
    current_y = 0
    for block in images_data:
        w_bytes = block['width_bytes']
        h_dots = block['height_dots']
        b_data = block['data']
        
        byte_idx = 0
        for y in range(h_dots):
            for x_byte in range(w_bytes):
                if byte_idx >= len(b_data):
                    break
                byte = b_data[byte_idx]
                byte_idx += 1
                for bit in range(8):
                    if (byte & (1 << (7 - bit))) != 0:
                        x = x_byte * 8 + bit
                        draw.point((x, current_y + y), fill='black')
        current_y += h_dots
                        
    return img

from escpos_analyzer import analyze_commands

def handle_client(conn, addr):
    print(f"\n[{datetime.datetime.now()}] 🖨️ ลูกค้าเชื่อมต่อจาก: {addr}")
    full_data = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data: break
            full_data += data
            
        if full_data:
            print(f"--- ได้รับข้อมูลทั้งหมด {len(full_data)} bytes ---")
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # บันทึก Raw file (ปัจจุบันถูกปิดการใช้งานไว้)
            # with open(f"job_{timestamp}.bin", "ab") as f:
            #     f.write(full_data)
            
            # ดึงภาพ Raster และส่งเข้า Telegram แทนการบันทึกลงไฟล์
            img = extract_all_raster_images(full_data)
            
            if img:
                send_to_telegram(img)
            else:
                print("⚠️ ไม่พบคำสั่งรูปภาพในข้อมูลนี้ (POS อาจส่งมาเป็นข้อความล้วน)")
                
            # 2. บันทึกตัววิเคราะห์คำสั่งเก็บไว้ (ปัจจุบันถูกปิดการใช้งานไว้)
            # analysis_result = analyze_commands(full_data)
            # txt_filename = f"escpos_analyzer_{timestamp}.txt"
            # with open(txt_filename, "w", encoding="utf-8") as f:
            #     f.write(analysis_result)
            # print(f"📄 บันทึกผลวิเคราะห์คำสั่งลงไฟล์: {txt_filename} เรียบร้อยแล้ว")
                
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
    finally:
        conn.close()

def start_printer_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        print("="*65)
        print(f"🟢 เริ่มจำลอง ESC/POS Printer ที่พอร์ต {PORT}")
        print("โหมดการทำงาน: รับภาพใบเสร็จแล้วส่งเข้า Telegram ทันที (ไม่เซฟลงคอม)")
        print("กด Ctrl+C เพื่อปิดโปรแกรม")
        print("="*65)
        
        try:
            server_socket.settimeout(1.0)
            # สร้าง Thread Pool จำกัดจำนวน Worker ไว้ที่ 5 connection พร้อมกัน
            # หากมีการเชื่อมต่อเข้ามาเกิน 5 เครื่องพร้อมกัน คิวที่ 6 จะถูกพักรอจนกว่าจะว่าง
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                while True:
                    try:
                        conn, addr = server_socket.accept()
                        executor.submit(handle_client, conn, addr)
                    except socket.timeout:
                        continue
        except KeyboardInterrupt:
            print("\n🔴 ปิดเครื่องพิมพ์จำลอง (ได้รับคำสั่ง Ctrl+C)...")
            sys.exit(0)

if __name__ == "__main__":
    start_printer_server()
