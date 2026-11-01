# LoRa Smart Irrigation System

An autonomous, off-grid IoT network for precision agriculture using LoRa radio, edge computing, and cloud AI.

## Project Overview

This project implements a smart irrigation system consisting of a solar-powered field node and a mains-powered gateway node. The field node collects soil and environmental data and transmits it via LoRa telemetry to the gateway node. The gateway forwards this data to a Flask-based cloud server, which uses a Machine Learning model and live weather data to provide crop recommendations and intelligent irrigation decisions.

### Architecture

Field Node (ESP32 + Sensors) -> LoRa (433MHz) -> Gateway Node (ESP32 + WiFi) -> HTTP POST -> Flask Server

The Cloud Server is responsible for:
- Machine Learning Inference (Random Forest)
- Weather API Integration (OpenWeatherMap)
- Smart Irrigation Logic (Rain-skip intelligence)
- SQLite Data Storage
- Web Dashboard and UI
- Telegram Alerts

## Features
- Long-range, low-power telemetry via LoRa.
- Location-aware soil nutrient estimation (regional soil baselines + farmer fertilizer inputs).
- Machine Learning crop recommendation (via scikit-learn).
- Weather-aware irrigation that skips watering if rain is forecasted.
- Live web dashboard with real-time graphs and historical data.
- Push alerts via Telegram Bot API.

## Directory Structure
- `field_node/`: PlatformIO project for the sensor node.
- `gateway_node/`: PlatformIO project for the gateway and relay node.
- `cloud_server/`: Python Flask backend, ML model, and web dashboard.
- `docs/`: Additional documentation including the wiring guide.

## Quick Start

### 1. Hardware Setup
Refer to `HARDWARE_CONNECTIONS.md` for step-by-step wiring and `docs/wiring_guide.md` for the pin table.

> **Demo/USB-only mode:** Battery, solar panel, and TP4056 are not required. Power both ESP32 boards directly from PC USB ports. Relay is optional (connect VCC+GND+IN only for the click; leave COM/NO/NC open).

### 2. Firmware (ESP32)
1. Install the **PlatformIO IDE** extension in VS Code.
2. Open the `field_node/` folder in VS Code → click **Upload** in the PlatformIO toolbar.
3. Open the `gateway_node/` folder → copy `include/credentials.h.example` to `include/credentials.h`.
4. Set `SERVER_URL` to your laptop's IP on the shared network (run `ipconfig`, use the WiFi adapter IPv4 — **not** `127.0.0.1`).
5. Click **Upload**.
6. On first boot, the Gateway creates a `LoRa-Irrigation-Setup` WiFi hotspot. Connect your phone to it, open `http://192.168.4.1`, and select your network.
7. See `docs/FLASH_AND_DEMO.md` for the full step-by-step flash guide.

### 3. Cloud Server
1. Navigate to the `cloud_server/` directory.
2. Install Python dependencies: `pip install -r requirements.txt`.
3. Train the ML model: `python train_model.py`.
4. Start the server: `python flask_app.py`.
5. Access the dashboard at `http://localhost:5000` (or `http://<your-laptop-IP>:5000` from other devices on the same network — Flask is configured with `host='0.0.0.0'`).

## Irrigation Logic (Cloud-First)

The gateway uses a **cloud-first** decision model:
1. Sensor data is uploaded to Flask (`/api/predict`) **before** the relay is touched.
2. Flask responds with `{"irrigation": {"triggered": true/false, ...}}`.
3. If `triggered == true` → gateway opens relay. If `triggered == false` (e.g. rain forecast) → relay stays closed.
4. If the cloud is unreachable → fallback to local threshold (`moisture < 30%`).

## Bill of Materials (BOM)
Key components include:
- ESP32 Development Boards (x2)
- SX1278 LoRa Radio Modules (x2)
- Sensors: Capacitive Soil Moisture, DS18B20 (Soil Temp), BME280 (Air Data), BH1750 (Light)
- 5V Relay Module and 12V Solenoid Valve *(optional for USB-only demo — relay alone works without valve)*
- TP4056 Charger, 18650 Battery, and 5V Solar Panel for the field node *(optional for USB-only demo)*
