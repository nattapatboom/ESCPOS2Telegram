#!/usr/bin/env python3
import socket
import threading
import datetime
import sys
import yaml
import time
import concurrent.futures

# Default config file name
DEFAULT_CONFIG_FILE = 'splitter_config.yaml'

def load_config(config_path=DEFAULT_CONFIG_FILE):
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Failed to load config file: {e}")
        return None

def forward_to_printer(ip, port, data, printer_name):
    """Send data to target printer"""
    try:
        print(f"📡 Sending to {printer_name} ({ip}:{port})...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)  # 10 second timeout
            s.connect((ip, port))
            s.sendall(data)
        print(f"✅ Sent to {printer_name} successfully")
    except Exception as e:
        print(f"❌ Cannot send to {printer_name} ({ip}): {e}")

def handle_client(conn, addr, config):
    """Receive data from POS and forward to all printers"""
    print(f"\n[{datetime.datetime.now()}] 📥 Received from: {addr}")
    full_data = b""
    try:
        # Set timeout to detect end of data transmission
        # If POS stops sending for 1.5 seconds, assume data is complete
        conn.settimeout(1.5)
        while True:
            try:
                data = conn.recv(8192)
                if not data:
                    break
                full_data += data
            except socket.timeout:
                # Timeout reached — data likely complete
                break
            
        if full_data:
            print(f"📊 Received {len(full_data)} bytes")

            # Send "ready to print" status back to POS immediately
            # DLE EOT (0x10 0x04) = printer status OK
            try:
                conn.sendall(b'\x10\x04\x01')  # DLE EOT - Printer Status: OK
            except Exception:
                pass
            
            printers = config.get('printers', [])
            if not printers:
                print("⚠️ Warning: No printers found in config")
                return

            # Send to all printers in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(printers)) as executor:
                futures = []
                for p in printers:
                    ip = p.get('ip')
                    port = p.get('port', 9100)
                    name = p.get('name', ip)
                    futures.append(executor.submit(forward_to_printer, ip, port, full_data, name))
                
                # Wait for all to complete (or timeout)
                concurrent.futures.wait(futures, timeout=30)
                
    except Exception as e:
        print(f"Error receiving data: {e}")
    finally:
        conn.close()

def start_splitter():
    # Read config file from argument if provided
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
            print(f"❌ Cannot bind port {listen_port}: {e}")
            print("Check if another program is using this port")
            return

        server_socket.listen(10)
        
        print("="*65)
        print(f"🚀 ESC/POS Printer Splitter started")
        print(f"📍 Listening on port: {listen_port}")
        print(f"🖨️ Target printers: {len(config.get('printers', []))}")
        for p in config.get('printers', []):
            print(f"   - {p.get('name')} ({p.get('ip')}:{p.get('port', 9100)})")
        print("-" * 65)
        print("Press Ctrl+C to stop")
        print("="*65)

        try:
            while True:
                conn, addr = server_socket.accept()
                # Create new thread for each incoming connection
                client_thread = threading.Thread(target=handle_client, args=(conn, addr, config))
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n🔴 Shutting down Splitter...")
            sys.exit(0)

if __name__ == "__main__":
    start_splitter()
