# LoRa Smart Irrigation & Agronomic Advisory System

An autonomous, off-grid IoT network and decision-support platform for precision agriculture using LoRa radio telemetry, edge computing, cloud machine learning, and agronomic advisory intelligence.

---

## Project Overview

Traditional smart irrigation systems typically function as open-loop binary triggers (e.g. *"water when moisture < 30%"*) with single-crop classification. This project elevates smart farming into a full-cycle **Decision Support System (DSS)**:

1. **Edge Telemetry:** A solar-compatible **Field Node** (ESP32) collects real-time soil moisture, soil temperature, air temperature, relative humidity, and ambient light, transmitting packets over long distances via **433 MHz LoRa (SX1278)**.
2. **Gateway & Relay Control:** A mains-powered **Gateway Node** (ESP32) receives packets, forwards telemetry via HTTP POST over Wi-Fi to a Flask cloud server, and coordinates valve/pump actuation via a **cloud-first control model** with automatic offline fallback.
3. **Agronomic Decision Engine:** Rather than simply reporting sensor data, the cloud server computes:
   - **Top-3 Ranked Crop Recommendations** via Random Forest ML model.
   - **Nutrient Deficit & Fertilizer Prescriptions** tailored to Indian markets (Urea, DAP, MOP) with exact dosages, organic alternatives, and long-term soil health protection warnings.
   - **Moisture Trend Velocity:** Least-squares linear regression predicting drying rate (%/hr) and hours remaining until threshold.
   - **Soil Health Score (0–100):** Composite metric tracking moisture variance, nutrient balance, and irrigation frequency.
   - **ICAR Sowing Calendar:** Identifying optimal crop planting windows.
   - **Pathology Risk Engine:** Detecting environmental conditions for fungal blast, downy mildew, root heat stress, and waterlogging.

---

## System Architecture

```text
┌─────────────────────────┐          LoRa RF (433 MHz)         ┌─────────────────────────┐
│       Field Node        │ ─────────────────────────────────> │      Gateway Node       │
│ ESP32 + Capacitive Soil │         Range: up to 1-3 km        │  ESP32 + Wi-Fi Uplink   │
│ DS18B20 + BME280+BH1750 │                                    │  5V Relay / Valve Ctrl  │
└─────────────────────────┘                                    └────────────┬────────────┘
                                                                            │ HTTP POST
                                                                            ▼
                                                               ┌─────────────────────────┐
                                                               │      Flask Server       │
                                                               │  • Random Forest ML     │
                                                               │  • OpenWeatherMap API   │
                                                               │  • Agronomic Prescriber │
                                                               │  • SQLite Database      │
                                                               │  • Glassmorphic UI      │
                                                               │  • Telegram Push Alerts │
                                                               └─────────────────────────┘
```

---

## Core Features

### 1. Agronomic Advisory & Fertilizer Prescription Engine
* **22-Crop Requirement Knowledge Base:** Calibrated nutrient benchmarks (N, P, K) for 22 crops from the ICAR/Kaggle agricultural dataset.
* **Targeted Deficit Analysis:** Compares effective soil nutrients against the selected crop's requirements.
* **Indian-Market Prescriptions:** Prescribes exact applications (kg/acre) for **Urea (46-0-0)**, **DAP (18-46-0)**, and **MOP (0-0-60)**.
* **Long-Term Soil Health Safeguards:** Informs farmers of soil acidification risks from chronic urea use, phosphorus fixation from excessive DAP, and chloride accumulation from MOP.
* **Organic Alternatives:** Provides sustainable alternatives including vermicompost, bone meal, and wood ash.

### 2. Predictive Farm Insights
* **Moisture Trend & Velocity:** Linear regression over recent sensor readings calculating drying rate (`%/hr`) and hours until irrigation is required.
* **Soil Health Score (0–100):** Evaluates moisture stability (std dev), nutrient balance against indigenous soil baselines, and irrigation cycle frequency.
* **Sowing Calendar:** ICAR-based calendar indicating whether the current month is an optimal planting window or displaying a countdown to the next season.
* **Disease & Environmental Stress Rules:**
  * **Fungal Blast (Rice/Maize):** Triggers when humidity $> 80\%$ and air temperature $> 25^\circ\text{C}$.
  * **Downy Mildew:** Triggers when humidity $> 75\%$ and air temperature is between $18\text{–}28^\circ\text{C}$.
  * **Root Heat Stress:** Triggers when soil temperature $> 35^\circ\text{C}$ and moisture $< 25\%$.
  * **Waterlogging Alert:** Warns against irrigation when moisture $> 80\%$ and imminent rainfall is detected.

### 3. Location-Aware Soil Modeling
* Solves the common limitation of low-cost IoT setups (where optical/resistive NPK probes are prohibitively expensive or unreliable) using a two-tier soil model:
  $$\text{Effective NPK} = \text{Regional Soil Baseline (ICAR)} + \text{Farmer Amendment Delta}$$
* Built-in baselines for Alluvial, Black Cotton, Red/Laterite, Arid/Desert, and Mountain/Forest soils.

### 4. Cloud-First Adaptive Irrigation
* **Weather-Aware Rain Skip:** Queries OpenWeatherMap 3-hour forecasts. If rain probability exceeds threshold ($\ge 60\%$), scheduled irrigation is aborted to conserve water.
* **Offline Fallback:** If cloud connectivity drops, the gateway automatically falls back to edge logic (`moisture < 30%`).

### 5. Monitoring & Multi-Channel Alerts
* **Glassmorphic Web Dashboard:** Real-time animated SVG gauges, historical trend charts (Chart.js), interactive NPK simulator, soil health dials, and advisory cards.
* **Telegram Bot Integration:** Push alerts for valve events, rain-skip notices, high-risk disease warnings, and daily morning farm briefings.

---

## Directory Structure

```text
LoRa-Smart-Irrigation/
├── field_node/                  # PlatformIO project: Sensor node firmware
│   ├── include/                 # Pin definitions, LoRa radio config, sleep settings
│   └── src/                     # Deep sleep routines, sensor reading, LoRa TX
├── gateway_node/                # PlatformIO project: Gateway & relay node firmware
│   ├── include/                 # Wi-Fi credentials, pin mapping, HTTP payload schemas
│   └── src/                     # LoRa RX, Wi-Fi captive portal, cloud POST, relay control
├── cloud_server/                # Python Flask backend
│   ├── crop_model.pkl           # Trained Random Forest classifier
│   ├── database.py              # SQLite schema, migrations, time-series query engine
│   ├── flask_app.py             # REST API routes, ML pipeline, irrigation logic
│   ├── region_crops.py          # Geographic & climatic crop constraint filters
│   ├── soil_service.py          # Soil baselines, NPK deficit prescriber, pathology rules
│   ├── telegram_bot.py          # Push notification templates & Telegram Bot client
│   ├── weather_service.py       # OpenWeatherMap forecast client & rain-skip logic
│   ├── static/                  # CSS styles (glassmorphism), vanilla JS dashboard logic
│   └── templates/               # Responsive HTML5 dashboard
└── docs/                        # Hardware wiring guides and flashing instructions
```

---

## REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/predict` | `POST` | Ingests sensor packet from gateway, computes ML predictions, runs advisory rules, logs reading to SQLite, and returns cloud irrigation decision. |
| `/api/advisory` | `GET` | Returns full agronomic intelligence payload (top-3 crops with fertilizer prescriptions, soil health score, moisture trend, disease alerts). |
| `/api/latest` | `GET` | Fetches the most recent sensor reading and ML prediction. |
| `/api/history?hours=24` | `GET` | Returns historical time-series sensor telemetry for graphing. |
| `/api/settings` | `GET` / `POST` | Inspects or updates coordinates, city, soil type, and fertilizer amendments. |
| `/api/simulate` | `POST` | Generates realistic synthetic telemetry for rapid bench demonstration without hardware. |
| `/api/stats` | `GET` | Returns system health statistics, total packet count, and average soil moisture. |

---

## Quick Start Guide

### 1. Hardware Setup
Refer to `HARDWARE_CONNECTIONS.md` for step-by-step pin connections and `docs/wiring_guide.md` for the wiring schematic.

> **USB / Bench Demo Mode:** Battery, solar panel, and TP4056 are optional. Both ESP32 boards can be powered directly via micro-USB cables. The relay module can be demonstrated with `VCC + GND + IN` connected (audible switching confirmed) without needing a plumbed 12V solenoid valve.

### 2. Firmware (ESP32)
1. Install **PlatformIO IDE** in VS Code.
2. Open `field_node/` $\to$ click **Upload** in the PlatformIO toolbar.
3. Open `gateway_node/` $\to$ copy `include/credentials.h.example` to `include/credentials.h`.
4. Set `SERVER_URL` to your computer's local network IP (e.g. `http://192.168.1.50:5000`).
5. Click **Upload**.
6. On initial boot, connect to the gateway's `LoRa-Irrigation-Setup` captive Wi-Fi portal (`http://192.168.4.1`) to configure Wi-Fi credentials.
7. Full flashing instructions are detailed in `docs/FLASH_AND_DEMO.md`.

### 3. Cloud Server
1. Navigate to `cloud_server/`:
   ```bash
   cd cloud_server
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. *(Optional)* Retrain the ML model:
   ```bash
   python train_model.py
   ```
4. Start the application:
   ```bash
   python flask_app.py
   ```
5. Open `http://localhost:5000` in your browser (or `http://<your-ip>:5000` from any device on the local network).

---

## Bill of Materials (BOM)

| Component | Quantity | Purpose |
|---|---|---|
| ESP32 DevKit V1 (38-pin WROOM-32) | 2 | Microcontroller for Field Node and Gateway Node |
| Ai-Thinker Ra-02 (SX1278, 433 MHz) | 2 | Long-range LoRa transceivers with IPEX antennas |
| Capacitive Soil Moisture Sensor v1.2 | 1 | Corrosion-resistant analog soil moisture sensing |
| DS18B20 Probe (Waterproof OneWire) | 1 | Subsurface soil temperature sensing |
| BME280 Sensor (I2C) | 1 | Ambient air temperature, relative humidity, and barometric pressure |
| BH1750 Sensor (I2C) | 1 | Sunlight intensity (lux) measurement |
| 5V Single-Channel Relay Module | 1 | Valve / pump switching with optocoupler isolation |
| TP4056 + 18650 Li-ion + 5V Solar Panel | 1 | Off-grid power supply for Field Node *(optional for bench demo)* |
