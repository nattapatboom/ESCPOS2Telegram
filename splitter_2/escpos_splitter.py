#!/ cures/bin/env python3
import socket
import threading
import datetime
import sys
import yaml
import time
import concurrent.futures

# ชื่อไฟล์คอนฟิกเริ่มต้น
DEFAULT_CONFIG_FILE = 'splitter_config.yaml'

def load_config(config_path=DEFAULT_CONFIG_FILE):
    """โหลดการตั้งค่าจากไฟล์ YAML"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ ไม่สามารถโหลดไฟล์คอนฟิกได้: {e}")
        return None

def forward_to_printer(ip, port, data, printer_name):
    """ส่งข้อมูลไปยังเครื่องพิมพ์เป้าหมาย"""
    try:
        print(f"📡 กำลังส่งข้อมูลไปยัง {printer_name} ({ip}:{port})...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)  # Timeout 10 วินาที
            s.connect((ip, port))
            s.sendall(data)
        print(f"✅ ส่งข้อมูลไปยัง {printer_name} สำเร็จ")
    except Exception as e:
        print(f"❌ ไม่สามารถส่งข้อมูลไปยัง {printer_name} ({ip}) ได้: {e}")

def handle_client(conn, addr, config):
    """รับข้อมูลจาก POS แล้วส่งต่อให้ทุกเครื่องพิมพ์"""
    print(f"\n[{datetime.datetime.now()}] 📥 รับข้อมูลจาก: {addr}")
    full_data = b""
    try:
        # รับข้อมูลทั้งหมดจนกว่าจะปิดการเชื่อมต่อ
        while True:
            data = conn.recv(8192)
            if not data:
                break
            full_data += data
            
        if full_data:
            print(f"📊 ได้รับข้อมูลขนาด {len(full_data)} bytes")
            
            printers = config.get('printers', [])
            if not printers:
                print("⚠️ คำเตือน: ไม่พบเครื่องพิมพ์ในคอนฟิก")
                return

            # ส่งข้อมูลไปยังทุกเครื่องพิมพ์พร้อมกัน (Parallel)
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(printers)) as executor:
                futures = []
                for p in printers:
                    ip = p.get('ip')
                    port = p.get('port', 9100)
                    name = p.get('name', ip)
                    futures.append(executor.submit(forward_to_printer, ip, port, full_data, name))
                
                # รอให้ทุกอย่างเสร็จสิ้น (หรือ timeout)
                concurrent.futures.wait(futures, timeout=30)
                
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการรับข้อมูล: {e}")
    finally:
        conn.close()

def start_splitter():
    # รับชื่อไฟล์คอนฟิกจาก argument ถ้ามี
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    config = load_config(config_path)
    if not config:
        return

    listen_port = config.get('listen_port', 9100)
    host = '0.0.0.0'

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind((host, listen_port))
        except Exception as e:
            print(f"❌ ไม่สามารถ bind พอร์ต {listen_port} ได้: {e}")
            print("ตรวจสอบว่ามีโปรแกรมอื่นใช้งานพอร์ตนี้อยู่หรือไม่")
            return

        server_socket.listen(10)
        
        print("="*65)
        print(f"🚀 ESC/POS Printer Splitter เริ่มทำงานแล้ว")
        print(f"📍 รอรับข้อมูลที่พอร์ต: {listen_port}")
        print(f"🖨️ เครื่องพิมพ์ปลายทาง: {len(config.get('printers', []))} เครื่อง")
        for p in config.get('printers', []):
            print(f"   - {p.get('name')} ({p.get('ip')}:{p.get('port', 9100)})")
        print("-" * 65)
        print("กด Ctrl+C เพื่อปิดโปรแกรม")
        print("="*65)

        try:
            while True:
                conn, addr = server_socket.accept()
                # สร้าง Thread ใหม่เพื่อจัดการแต่ละการเชื่อมต่อที่เข้ามา
                client_thread = threading.Thread(target=handle_client, args=(conn, addr, config))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n🔴 ปิดโปรแกรม Splitter...")
            sys.exit(0)

if __name__ == "__main__":
    start_splitter()
