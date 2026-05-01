# ESCPOS2Telegram

ESCPOS2Telegram is a containerized Python TCP server that emulates an 80mm ESC/POS thermal printer. It captures incoming print data (specifically raster images) over the network and automatically relays the receipts as images directly to a Telegram chat. Additionally, it now includes a **Printer Splitter** utility to forward print jobs to multiple physical or virtual printers.

## Features

### 1. ESC/POS to Telegram
- **ESC/POS Emulation:** Acts as a network thermal printer listening on port 9100.
- **Image Extraction:** Automatically extracts raster image commands (`GS v 0`) from the raw print data and reconstructs the receipt image.
- **Telegram Integration:** Sends the reconstructed receipt image to a specified Telegram chat using a Telegram Bot.
- **Multi-Printer Support:** Designed to run multiple simulated printers simultaneously using Docker Compose and Macvlan networking.

### 2. ESC/POS Printer Splitter [NEW]
- **Command Forwarding:** Receives ESC/POS data and forwards it to one or more printers simultaneously.
- **YAML Configuration:** Easy to configure target printers (IP and Port) via a YAML file.
- **Parallel Forwarding:** Uses multi-threading to ensure that a slow printer doesn't block others.
- **Docker Ready:** Can run as multiple instances with independent configurations and code.

## Prerequisites

- Python 3.x
- Docker and Docker Compose
- PyYAML (for Splitter configuration)
- A Telegram Bot Token and Chat ID (for Telegram feature)

## Setup and Installation

### 1. Configuration (Telegram)
Create `telegram_config.py` in the root or printer directory:
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"
```

### 2. Configuration (Printer Splitter)
The Splitter uses a `splitter_config.yaml` file located in its folder:
```yaml
listen_port: 9100
printers:
  - ip: "192.168.1.11"
    port: 9100
    name: "Kitchen Printer"
  - ip: "192.168.1.12"
    port: 9100
    name: "Bar Printer"
```

### 3. Running with Docker Compose (Recommended)
The `docker-compose.yml` is pre-configured to run multiple printers and two splitter instances (`splitter_1` and `splitter_2`).

```bash
docker-compose up -d --build
```

### 4. Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run Telegram Bridge
python esc_pos2telegram.py

# Run Printer Splitter (pointing to a config file)
python escpos_splitter.py splitter_1/splitter_config.yaml
```

## File Structure

- `esc_pos2telegram.py`: Main Telegram bridge logic.
- `escpos_splitter.py`: Main Printer Splitter logic.
- `splitter_1/` & `splitter_2/`: Independent folders for Splitter instances containing their own code and config.
- `printer_1/` to `printer_4/`: Folders for simulated printers.
- `splitter_config.yaml`: Template for splitter configuration.
- `Dockerfile.splitter`: Docker configuration for the Splitter.
- `docker-compose.yml`: Orchestrates all printers and splitters using Macvlan.
