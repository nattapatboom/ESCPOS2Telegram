#!/usr/bin/env python3
"""
ESC/POS Printer Splitter
━━━━━━━━━━━━━━━━━━━━━━━━
Architecture:
  - Each printer has its own Queue + Worker Thread
  - Worker sends one job at a time (no concurrent sends to the same printer)
  - Multiple POS clients can send simultaneously — jobs queue up (FIFO)
  - Each printer runs independently (does not block others)
"""
import socket
import threading
import datetime
import sys
import yaml
import queue

# ─── Default config file ───────────────────────────────────────────────
DEFAULT_CONFIG_FILE = 'splitter_config.yaml'

# ─── Safety constants ───────────────────────────────────────────────────
MAX_CONCURRENT_CLIENTS = 20   # Max simultaneous POS connections
PRINTER_CONNECT_TIMEOUT = 5   # Printer connect timeout (seconds)
PRINTER_SEND_TIMEOUT    = 10  # Data send timeout after connect (seconds)
PRINTER_RETRY           = 2   # Number of retry attempts if printer is unresponsive
CLIENT_DATA_TIMEOUT     = 1.5 # Timeout waiting for POS data (seconds)
PRINTER_QUEUE_SIZE      = 50  # Max queued jobs per printer

# ─── Global state ────────────────────────────────────────────────────────
_client_semaphore = threading.Semaphore(MAX_CONCURRENT_CLIENTS)
_active_clients   = 0
_active_lock      = threading.Lock()


# ───────────────────────────────────────────────────────────────────────────
def _log(level: str, msg: str):
    """Print log with timestamp and thread name"""
    ts  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    tid = threading.current_thread().name
    print(f"[{ts}][{tid}] {level} {msg}", flush=True)


# ───────────────────────────────────────────────────────────────────────────
def load_config(config_path: str = DEFAULT_CONFIG_FILE):
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        _log("❌", f"Failed to load config file: {e}")
        return None


# ───────────────────────────────────────────────────────────────────────────
def _send_once(ip: str, port: int, data: bytes, printer_name: str) -> bool:
    """
    Attempt to send data once. Returns True on success.
    Separate timeout for connect vs send.
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
        _log("🔌", f"{printer_name}: connection refused (printer off?)")
    except OSError as e:
        _log("❌", f"{printer_name}: network error — {e}")
    except Exception as e:
        _log("❌", f"{printer_name}: unexpected error — {e}")
    return False


def forward_to_printer(ip: str, port: int, data: bytes, printer_name: str) -> bool:
    """Send data to printer with retry"""
    for attempt in range(1, PRINTER_RETRY + 1):
        _log("📡", f"[{attempt}/{PRINTER_RETRY}] Sending to {printer_name} ({ip}:{port}) ...")
        if _send_once(ip, port, data, printer_name):
            _log("✅", f"{printer_name}: success ({len(data)} bytes)")
            return True
        if attempt < PRINTER_RETRY:
            _log("🔁", f"{printer_name}: waiting 1s then retry ...")
            # Brief pause before retry to give printer time to recover
            import time; time.sleep(1)

    _log("🚫", f"{printer_name}: failed after {PRINTER_RETRY} attempts — skipping job")
    return False


# ───────────────────────────────────────────────────────────────────────────
class PrinterQueue:
    """
    Per-printer job queue
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    - Worker thread runs in the background for the program's lifetime
    - Dequeues jobs one at a time (FIFO) — no concurrent sends
    - Queue has a fixed max size (PRINTER_QUEUE_SIZE) to prevent memory overflow
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
        _log("🖨️", f"Queue worker ready: {name} ({ip}:{port})")

    # ── Public ──────────────────────────────────────────────────────────────
    def submit(self, data: bytes) -> bool:
        """
        Add job to queue (non-blocking)
        Returns False if queue is full — logs warning but doesn't hang
        """
        try:
            self._q.put_nowait(data)
            _log("📬", f"{self.name}: job queued (queue: {self._q.qsize()} jobs)")
            return True
        except queue.Full:
            _log("⚠️", f"{self.name}: queue full ({PRINTER_QUEUE_SIZE} jobs) — dropping job")
            return False

    @property
    def queue_size(self) -> int:
        return self._q.qsize()

    # ── Private ─────────────────────────────────────────────────────────────
    def _worker(self):
        """
        Worker main loop:
        - Blocks until a job is available
        - Sends jobs one at a time, FIFO order
        - Runs forever (daemon thread dies when program exits)
        """
        while True:
            data = self._q.get()   # Blocks until job available
            try:
                forward_to_printer(self.ip, self.port, data, self.name)
            finally:
                self._q.task_done()


# ───────────────────────────────────────────────────────────────────────────
def handle_client(conn: socket.socket, addr, printer_queues: list):
    """
    Receive data from POS and queue it to all printers
    (Does not wait for printers to finish — releases POS connection ASAP)
    """
    global _active_clients

    # ── Check client limit ─────────────────────────────────────────────
    if not _client_semaphore.acquire(blocking=False):
        _log("⚠️", f"Rejected {addr} — max clients reached ({MAX_CONCURRENT_CLIENTS})")
        try:
            conn.close()
        except Exception:
            pass
        return

    with _active_lock:
        _active_clients += 1
        current = _active_clients

    _log("📥", f"Connection from {addr}  (active: {current}/{MAX_CONCURRENT_CLIENTS})")

    full_data = b""
    try:
        # ── Receive data from POS ──────────────────────────────────────
        conn.settimeout(CLIENT_DATA_TIMEOUT)
        while True:
            try:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                full_data += chunk
            except socket.timeout:
                # Timeout reached — assume POS finished sending
                break

        if not full_data:
            _log("⚠️", f"{addr}: no data received")
            return

        _log("📊", f"{addr}: received {len(full_data)} bytes")

        # ── Reply to POS immediately ────────────────────────────────────
        try:
            conn.sendall(b'\x10\x04\x01')  # DLE EOT — Printer Status: OK
        except Exception:
            pass  # Not critical

        # ── Queue job to all printers ─────────────────────────────────
        ok = sum(pq.submit(full_data) for pq in printer_queues)
        _log("📋", f"Queued {ok}/{len(printer_queues)} printers")
        # Show current queue status
        status = ", ".join(f"{pq.name}({pq.queue_size})" for pq in printer_queues)
        _log("📊", f"Queue status: {status}")

    except Exception as e:
        _log("❌", f"Error receiving data from {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        _client_semaphore.release()
        with _active_lock:
            _active_clients -= 1
        _log("🔚", f"Closed connection {addr}")


# ───────────────────────────────────────────────────────────────────────────
def start_splitter():
    config_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONFIG_FILE
    config = load_config(config_path)
    if not config:
        return

    listen_port = config.get('listen_port', 9100)
    printers    = config.get('printers', [])

    if not printers:
        _log("❌", "No printers found in config")
        return

    # ── Create Queue Workers for each printer upfront ────────────────
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
            _log("❌", f"Cannot bind port {listen_port}: {e}")
            return

        server_socket.listen(MAX_CONCURRENT_CLIENTS)

        print("=" * 65)
        print("🚀 ESC/POS Printer Splitter started")
        print(f"📍 Listening on port       : {listen_port}")
        print(f"👥 Max concurrent POS      : {MAX_CONCURRENT_CLIENTS}")
        print(f"🖨️  Target printers         : {len(printers)}")
        for p in printers:
            print(f"   - {p.get('name')} ({p.get('ip')}:{p.get('port', 9100)})")
        print(f"📬 Max queue per printer   : {PRINTER_QUEUE_SIZE} jobs")
        print(f"⏱️  Connect timeout         : {PRINTER_CONNECT_TIMEOUT}s")
        print(f"⏱️  Send timeout            : {PRINTER_SEND_TIMEOUT}s")
        print(f"🔁 Retry per printer       : {PRINTER_RETRY} times")
        print("-" * 65)
        print("Press Ctrl+C to stop")
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
            _log("🔴", "Shutting down Splitter...")
            sys.exit(0)


if __name__ == "__main__":
    start_splitter()
