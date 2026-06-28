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
    """Send image to Telegram chat via Bot API"""
    if not HAS_REQUESTS:
        print("❌ Cannot send to Telegram. Install requests: pip install requests")
        return
        
    if telegram_config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not telegram_config.BOT_TOKEN:
        print("⚠️ Cannot send: BOT_TOKEN not set in telegram_config.py")
        return
        
    print("🚀 Sending receipt image to Telegram...")
    url = f"https://api.telegram.org/bot{telegram_config.BOT_TOKEN}/sendPhoto"
    
    # Read image from memory instead of file
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
            print("✅ Image sent to Telegram successfully!")
        else:
            print(f"❌ Telegram send failed: {response.text}")
    except Exception as e:
        print(f"Error sending to Telegram: {e}")

def extract_all_raster_images(data):
    """Extract Raster image commands (GS v 0) and compose into an Image object"""
    if not HAS_PIL:
        print("❌ Cannot create image. Install Pillow: pip install Pillow")
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
        
    print(f"\n🖼️ Found {len(images_data)} image section(s) (width {max_width}px, total height {total_height}px)")
    print("⏳ Composing image...")
    
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
    print(f"\n[{datetime.datetime.now()}] 🖨️ Client connected from: {addr}")
    full_data = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data: break
            full_data += data
            
        if full_data:
            print(f"--- Received {len(full_data)} bytes total ---")
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Raw file saving (currently disabled)
            # with open(f"job_{timestamp}.bin", "ab") as f:
            #     f.write(full_data)
            
            # Extract raster image and send to Telegram instead of saving to file
            img = extract_all_raster_images(full_data)
            
            if img:
                send_to_telegram(img)
            else:
                print("⚠️ No image commands found in this data (POS may have sent plain text)")
                
            # 2. Save analyzer output (currently disabled)
            # analysis_result = analyze_commands(full_data)
            # txt_filename = f"escpos_analyzer_{timestamp}.txt"
            # with open(txt_filename, "w", encoding="utf-8") as f:
            #     f.write(analysis_result)
            # print(f"📄 Analyzer output saved to: {txt_filename}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

def start_printer_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        print("="*65)
        print(f"🟢 ESC/POS Printer emulator started on port {PORT}")
        print("Mode: Receive receipt images and send to Telegram instantly (no local save)")
        print("Press Ctrl+C to stop")
        print("="*65)
        
        try:
            server_socket.settimeout(1.0)
            # Create Thread Pool with max 5 concurrent workers
            # If more than 5 connections arrive, the 6th will wait in queue
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                while True:
                    try:
                        conn, addr = server_socket.accept()
                        executor.submit(handle_client, conn, addr)
                    except socket.timeout:
                        continue
        except KeyboardInterrupt:
            print("\n🔴 Printer emulator shutting down (Ctrl+C)...")
            sys.exit(0)

if __name__ == "__main__":
    start_printer_server()
