#!/usr/bin/env python3
"""
ESC/POS Printer Splitter
━━━━━━━━━━━━━━━━━━━━━━━━
สถาปัตยกรรม:
  - แต่ละปริ้นเตอร์มี Queue + Worker Thread เป็นของตัวเอง
  - Worker ส่งข้อมูลทีละ 1 งาน (ไม่มีการส่งพร้อมกันไปปริ้นเตอร์เดียวกัน)
  - POS หลายเครื่องส่งมาพร้อมกัน → งานเข้าคิวรอตามลำดับ (FIFO)
  - ปริ้นเตอร์แต่ละเครื่องทำงานอิสระจากกัน (ไม่บล็อกกัน)
"""
import socket
import threading
import datetime
import sys
import yaml
import queue

# ─── ชื่อไฟล์คอนฟิกเริ่มต้น ───────────────────────────────────────────────
DEFAULT_CONFIG_FILE = 'splitter_config.yaml'

# ─── ค่าคงที่ความปลอดภัย ───────────────────────────────────────────────────
MAX_CONCURRENT_CLIENTS = 20   # จำนวน POS ที่รับได้พร้อมกันสูงสุด
PRINTER_CONNECT_TIMEOUT = 5   # timeout การ connect ไปหาปริ้นเตอร์ (วินาที)
PRINTER_SEND_TIMEOUT    = 10  # timeout การส่งข้อมูลหลัง connect สำเร็จ (วินาที)
PRINTER_RETRY           = 2   # จำนวนครั้งที่ลอง retry ถ้าปริ้นเตอร์ไม่ตอบสนอง
CLIENT_DATA_TIMEOUT     = 1.5 # timeout รอรับข้อมูลจาก POS (วินาที)
PRINTER_QUEUE_SIZE      = 50  # จำนวน job สูงสุดในคิวต่อปริ้นเตอร์ 1 เครื่อง

# ─── State ส่วนกลาง ────────────────────────────────────────────────────────
_client_semaphore = threading.Semaphore(MAX_CONCURRENT_CLIENTS)
_active_clients   = 0
_active_lock      = threading.Lock()


# ───────────────────────────────────────────────────────────────────────────
def _log(level: str, msg: str):
    """พิมพ์ log พร้อม timestamp และ thread name"""
    ts  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    tid = threading.current_thread().name
    print(f"[{ts}][{tid}] {level} {msg}", flush=True)


# ───────────────────────────────────────────────────────────────────────────
def load_config(config_path: str = DEFAULT_CONFIG_FILE):
    """โหลดการตั้งค่าจากไฟล์ YAML"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        _log("❌", f"ไม่สามารถโหลดไฟล์คอนฟิกได้: {e}")
        return None


# ───────────────────────────────────────────────────────────────────────────
def _send_once(ip: str, port: int, data: bytes, printer_name: str) -> bool:
    """
    พยายามส่งข้อมูล 1 ครั้ง คืน True ถ้าสำเร็จ
    แยก timeout ของ connect กับ send ออกจากกัน
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(PRINTER_CONNECT_TIMEOUT)
            s.connect((ip, port))
            s.settimeout(PRINTER_SEND_TIMEOUT)
            s.sendall(data)
        return True
    except socket.timeout as e:
        _log("⏱️", f"{printer_name}: timeout — {e}")
    except ConnectionRefusedError:
        _log("🔌", f"{printer_name}: ปฏิเสธการเชื่อมต่อ (ปริ้นเตอร์ปิดอยู่?)")
    except OSError as e:
        _log("❌", f"{printer_name}: network error — {e}")
    except Exception as e:
        _log("❌", f"{printer_name}: ข้อผิดพลาดไม่คาดคิด — {e}")
    return False


def forward_to_printer(ip: str, port: int, data: bytes, printer_name: str) -> bool:
    """ส่งข้อมูลไปปริ้นเตอร์ พร้อม retry"""
    for attempt in range(1, PRINTER_RETRY + 1):
        _log("📡", f"[{attempt}/{PRINTER_RETRY}] ส่งไปยัง {printer_name} ({ip}:{port}) ...")
        if _send_once(ip, port, data, printer_name):
            _log("✅", f"{printer_name}: สำเร็จ ({len(data)} bytes)")
            return True
        if attempt < PRINTER_RETRY:
            _log("🔁", f"{printer_name}: รอ 1 วินาที แล้ว retry ...")
            # รอสั้นๆ ก่อน retry เพื่อให้ปริ้นเตอร์มีเวลาหายใจ
            import time; time.sleep(1)

    _log("🚫", f"{printer_name}: ล้มเหลวทุก {PRINTER_RETRY} ครั้ง — ข้ามงานนี้")
    return False


# ───────────────────────────────────────────────────────────────────────────
class PrinterQueue:
    """
    คิวงานส่วนตัวสำหรับปริ้นเตอร์ 1 เครื่อง
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Worker thread ทำงานในพื้นหลังตลอดเวลาที่โปรแกรมรัน
    - ดึงงานจากคิวทีละ 1 งาน (FIFO) → ไม่มีการส่งซ้อนกัน
    - คิวมีขนาดจำกัด (PRINTER_QUEUE_SIZE) ป้องกัน memory ล้น
    """

    def __init__(self, ip: str, port: int, name: str):
        self.ip   = ip
        self.port = port
        self.name = name
        self._q   = queue.Queue(maxsize=PRINTER_QUEUE_SIZE)
        self._thread = threading.Thread(
            target=self._worker,
            name=f"printer-{name}",
            daemon=True,
        )
        self._thread.start()
        _log("🖨️", f"Queue worker พร้อมทำงาน: {name} ({ip}:{port})")

    # ── Public ──────────────────────────────────────────────────────────────
    def submit(self, data: bytes) -> bool:
        """
        เพิ่มงานเข้าคิว (non-blocking)
        คืน False ถ้าคิวเต็ม → โปรแกรมจะ log แต่ไม่ค้าง
        """
        try:
            self._q.put_nowait(data)
            _log("📬", f"{self.name}: รับงานเข้าคิว (รอในคิว: {self._q.qsize()} งาน)")
            return True
        except queue.Full:
            _log("⚠️", f"{self.name}: คิวเต็ม ({PRINTER_QUEUE_SIZE} งาน) — ทิ้งงานนี้")
            return False

    @property
    def queue_size(self) -> int:
        return self._q.qsize()

    # ── Private ─────────────────────────────────────────────────────────────
    def _worker(self):
        """
        Loop หลักของ worker:
        - รอดึงงานจากคิว (บล็อกจนกว่าจะมีงาน)
        - ส่งข้อมูลทีละ 1 งาน ตามลำดับ FIFO
        - วนซ้ำตลอดไป (daemon thread จะตายเมื่อโปรแกรมปิด)
        """
        while True:
            data = self._q.get()   # บล็อกจนกว่าจะมีงาน
            try:
                forward_to_printer(self.ip, self.port, data, self.name)
            finally:
                self._q.task_done()


# ───────────────────────────────────────────────────────────────────────────
def handle_client(conn: socket.socket, addr, printer_queues: list):
    """
    รับข้อมูลจาก POS แล้วใส่คิวของทุกปริ้นเตอร์
    (ไม่รอให้ปริ้นเตอร์ส่งเสร็จ — คืน connection ให้ POS เร็วที่สุด)
    """
    global _active_clients

    # ── ตรวจสอบ client limit ─────────────────────────────────────────────
    if not _client_semaphore.acquire(blocking=False):
        _log("⚠️", f"ปฏิเสธ {addr} — เกินจำนวน client สูงสุด ({MAX_CONCURRENT_CLIENTS})")
        try:
            conn.close()
        except Exception:
            pass
        return

    with _active_lock:
        _active_clients += 1
        current = _active_clients

    _log("📥", f"รับ connection จาก {addr}  (active: {current}/{MAX_CONCURRENT_CLIENTS})")

    full_data = b""
    try:
        # ── รับข้อมูลจาก POS ──────────────────────────────────────────────
        conn.settimeout(CLIENT_DATA_TIMEOUT)
        while True:
            try:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                full_data += chunk
            except socket.timeout:
                # หมดเวลารอ → ถือว่า POS ส่งข้อมูลครบแล้ว
                break

        if not full_data:
            _log("⚠️", f"{addr}: ไม่ได้รับข้อมูลใดเลย")
            return

        _log("📊", f"{addr}: ได้รับ {len(full_data)} bytes")

        # ── ตอบ POS ทันที ──────────────────────────────────────────────────
        try:
            conn.sendall(b'\x10\x04\x01')  # DLE EOT — Printer Status: OK
        except Exception:
            pass  # ไม่ critical

        # ── ใส่งานเข้าคิวของทุกปริ้นเตอร์ ─────────────────────────────────
        ok = sum(pq.submit(full_data) for pq in printer_queues)
        _log("📋", f"จัดคิวสำเร็จ {ok}/{len(printer_queues)} เครื่อง")
        # แสดงสถานะคิวปัจจุบัน
        status = ", ".join(f"{pq.name}({pq.queue_size})" for pq in printer_queues)
        _log("📊", f"สถานะคิว: {status}")

    except Exception as e:
        _log("❌", f"ข้อผิดพลาดในการรับข้อมูลจาก {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        _client_semaphore.release()
        with _active_lock:
            _active_clients -= 1
        _log("🔚", f"ปิด connection {addr}")


# ───────────────────────────────────────────────────────────────────────────
def start_splitter():
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    config = load_config(config_path)
    if not config:
        return

    listen_port = config.get('listen_port', 9100)
    printers    = config.get('printers', [])

    if not printers:
        _log("❌", "ไม่พบเครื่องพิมพ์ในคอนฟิก")
        return

    # ── สร้าง Queue Worker สำหรับแต่ละปริ้นเตอร์ตั้งแต่เริ่ม ────────────
    printer_queues = [
        PrinterQueue(
            ip=p.get('ip'),
            port=p.get('port', 9100),
            name=p.get('name', p.get('ip')),
        )
        for p in printers
    ]

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_socket.bind(('0.0.0.0', listen_port))
        except Exception as e:
            _log("❌", f"ไม่สามารถ bind พอร์ต {listen_port} ได้: {e}")
            return

        server_socket.listen(MAX_CONCURRENT_CLIENTS)

        print("=" * 65)
        print("🚀 ESC/POS Printer Splitter เริ่มทำงานแล้ว")
        print(f"📍 รอรับข้อมูลที่พอร์ต      : {listen_port}")
        print(f"👥 รับ POS พร้อมกันสูงสุด   : {MAX_CONCURRENT_CLIENTS} เครื่อง")
        print(f"🖨️  เครื่องพิมพ์ปลายทาง     : {len(printers)} เครื่อง")
        for p in printers:
            print(f"   - {p.get('name')} ({p.get('ip')}:{p.get('port', 9100)})")
        print(f"📬 คิวต่อปริ้นเตอร์สูงสุด   : {PRINTER_QUEUE_SIZE} งาน")
        print(f"⏱️  Connect timeout          : {PRINTER_CONNECT_TIMEOUT}s")
        print(f"⏱️  Send timeout             : {PRINTER_SEND_TIMEOUT}s")
        print(f"🔁 Retry ต่อปริ้นเตอร์      : {PRINTER_RETRY} ครั้ง")
        print("-" * 65)
        print("กด Ctrl+C เพื่อปิดโปรแกรม")
        print("=" * 65)

        try:
            while True:
                conn, addr = server_socket.accept()
                t = threading.Thread(
                    target=handle_client,
                    args=(conn, addr, printer_queues),
                    name=f"client-{addr[0]}:{addr[1]}",
                    daemon=True,
                )
                t.start()
        except KeyboardInterrupt:
            _log("🔴", "ปิดโปรแกรม Splitter...")
            sys.exit(0)


if __name__ == "__main__":
    start_splitter()
