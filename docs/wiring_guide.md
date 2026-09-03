# Wiring Guide

This document outlines the pin connections for both the Field Node and Gateway Node of the LoRa Smart Irrigation System.

## Field Node (ESP32)

The Field Node operates on battery/solar power and interfaces with various sensors.

### LoRa Module (SX1278)
| LoRa Pin | ESP32 GPIO | Notes |
| -------- | ---------- | ----- |
| NSS / CS | GPIO 5     | SPI Chip Select |
| SCK      | GPIO 18    | SPI Clock (VSPI) |
| MISO     | GPIO 19    | SPI MISO (VSPI) |
| MOSI     | GPIO 23    | SPI MOSI (VSPI) |
| RST      | GPIO 14    | Reset |
| DIO0     | GPIO 2     | Interrupt (Wait for TX/RX) |
| VCC      | 3.3V       | Ensure 3.3V power (Do not use 5V) |
| GND      | GND        | Common Ground |

### Environmental Sensors
| Sensor Module | Sensor Pin | ESP32 GPIO | Notes |
| ------------- | ---------- | ---------- | ----- |
| Capacitive Soil Moisture | AOUT | GPIO 34 | Analog Input (ADC1_CH6) |
| DS18B20 (Soil Temp) | DATA | GPIO 15 | Requires 4.7k Ohm pull-up resistor to 3.3V |
| BME280 (Air Data) | SDA | GPIO 21 | I2C Data line |
| BME280 (Air Data) | SCL | GPIO 22 | I2C Clock line |
| BH1750 (Light) | SDA | GPIO 21 | Shares I2C bus with BME280 |
| BH1750 (Light) | SCL | GPIO 22 | Shares I2C bus with BME280 |

Note: Supply sensors with 3.3V unless they specifically require 5V logic.

---

## Gateway Node (ESP32)

The Gateway Node runs on mains power, receives LoRa packets, controls the water valve relay, and forwards data over WiFi.

### LoRa Module (SX1278)
| LoRa Pin | ESP32 GPIO | Notes |
| -------- | ---------- | ----- |
| NSS / CS | GPIO 5     | SPI Chip Select |
| SCK      | GPIO 18    | SPI Clock (VSPI) |
| MISO     | GPIO 19    | SPI MISO (VSPI) |
| MOSI     | GPIO 23    | SPI MOSI (VSPI) |
| RST      | GPIO 14    | Reset |
| DIO0     | GPIO 2     | Interrupt (Wait for TX/RX) |
| VCC      | 3.3V       | Ensure 3.3V power |
| GND      | GND        | Common Ground |

### Actuation (Relay Module)
| Module Pin | ESP32 GPIO | Notes |
| ---------- | ---------- | ----- |
| IN / Signal | GPIO 26   | Controls the relay |
| VCC | 5V | Power for the optocoupler and coil |
| GND | GND | Common Ground |

**Solenoid Valve Wiring**: 
Connect the 12V DC power supply in series with the Solenoid Valve through the Relay's Normally Open (NO) and Common (COM) terminals.

---

## Power Supply Notes
- **Field Node**: The Field Node should be powered using an 18650 battery paired with a TP4056 charging module and a 5V solar panel.
- **Gateway Node**: The Gateway Node can be powered via a standard 5V micro-USB adapter, while the Solenoid Valve requires its own separate 12V DC 2A power supply. Ensure both grounds (ESP32 and 12V supply) are NOT connected if using a completely isolated optocoupler relay, otherwise connect grounds if using a shared ground system.
