def analyze_commands(data):
    """วิเคราะห์คำสั่ง (แยกจากระบบหลักเพื่อความเป็นระเบียบ)"""
    i = 0
    lines = []
    text_buffer = bytearray()
    
    def flush_text():
        if text_buffer:
            try:
                decoded = text_buffer.decode('cp874', errors='replace')
                if decoded.strip():
                    lines.append(f"[TEXT] {decoded}")
            except:
                pass
            text_buffer.clear()

    while i < len(data):
        b = data[i]
        if b == 0x1B:
            flush_text()
            if i + 1 < len(data):
                cmd = data[i+1]
                if cmd == 0x40: i += 2; lines.append("[ESC @] Init")
                elif cmd == 0x2A:
                    if i + 4 < len(data):
                        length = (data[i+3] + data[i+4]*256) * (1 if data[i+2] in [0,1] else 3)
                        i += 5 + length; lines.append("[ESC *] Bit Image")
                    else: i += 2
                elif cmd in [0x21, 0x61, 0x74, 0x2D, 0x45, 0x47, 0x4A, 0x64, 0x32, 0x33]: i += 3; lines.append(f"[ESC {chr(cmd) if 32<=cmd<=126 else hex(cmd)}]")
                else: i += 2
            else: i += 1
        elif b == 0x1D:
            flush_text()
            if i + 1 < len(data):
                cmd = data[i+1]
                if cmd == 0x56: i += 3; lines.append("[GS V] Cut")
                elif cmd == 0x76:
                    if i + 7 < len(data):
                        l = (data[i+4] + data[i+5]*256) * (data[i+6] + data[i+7]*256)
                        i += 8 + l; lines.append("[GS v 0] Raster Image")
                    else: i += 2
                elif cmd == 0x6B:
                    if i + 2 < len(data):
                        m = data[i+2]
                        lines.append(f"[GS k] Barcode {m}")
                        if 0<=m<=6:
                            i += 3
                            while i<len(data) and data[i]!=0: i+=1
                            i+=1
                        else:
                            i += 4 + data[i+3] if i+3<len(data) else 3
                    else: i += 2
                elif cmd in [0x48, 0x66, 0x68, 0x77, 0x21, 0x42]: i += 3; lines.append(f"[GS {chr(cmd) if cmd in [0x48,0x66,0x68,0x77,0x42] else hex(cmd)}]")
                else: i += 2
            else: i += 1
        elif b == 0x1C: flush_text(); i += 4; lines.append("[FS]")
        elif b == 0x0A: flush_text(); i += 1; lines.append("[LF]")
        elif b >= 0x20: text_buffer.append(b); i += 1
        else: flush_text(); i += 1
            
    flush_text()
    return "\n".join(lines)
