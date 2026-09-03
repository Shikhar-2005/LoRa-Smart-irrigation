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
- Edge-computed NPK soft-sensing without expensive industrial probes.
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
Refer to `docs/wiring_guide.md` for complete pin-to-pin connection details for both the Field Node and the Gateway Node.

### 2. Firmware (ESP32)
1. Open the `field_node` folder in PlatformIO.
2. Build and upload to the first ESP32.
3. Open the `gateway_node` folder in PlatformIO.
4. Copy `include/credentials.h.example` to `include/credentials.h` and add your WiFi and Server URL details.
5. Build and upload to the second ESP32.

### 3. Cloud Server
1. Navigate to the `cloud_server` directory.
2. Install Python dependencies: `pip install -r requirements.txt`.
3. Train the ML model: `python train_model.py`.
4. Start the server: `python flask_app.py`.
5. Access the dashboard at `http://localhost:5000`.

## Bill of Materials (BOM)
Key components include:
- ESP32 Development Boards (x2)
- SX1278 LoRa Radio Modules (x2)
- Sensors: Capacitive Soil Moisture, DS18B20 (Soil Temp), BME280 (Air Data), BH1750 (Light)
- 5V Relay Module and 12V Solenoid Valve
- TP4056 Charger, 18650 Battery, and 5V Solar Panel for the field node.
