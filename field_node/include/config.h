/*
 * LoRa Smart Irrigation - Field Node Configuration
 *
 * Pin assignments, LoRa parameters, sleep settings, and calibration
 * constants. Edit these values to match your hardware wiring.
 */

#ifndef CONFIG_H
#define CONFIG_H

// =========================================================================
// LoRa Radio (SX1278 via SPI)
// =========================================================================
// Wiring: Connect SX1278 to ESP32 default SPI bus
//   NSS/CS  -> GPIO 5
//   RST     -> GPIO 14
//   DIO0    -> GPIO 2
//   SCK     -> GPIO 18  (default VSPI CLK)
//   MISO    -> GPIO 19  (default VSPI MISO)
//   MOSI    -> GPIO 23  (default VSPI MOSI)

#define LORA_CS_PIN     5
#define LORA_RST_PIN    14
#define LORA_DIO0_PIN   2
#define LORA_DIO1_PIN   -1    // Not used, set -1

// LoRa radio parameters (MUST match gateway_node/include/config.h)
#define LORA_FREQUENCY      433.0   // MHz (433 for India, 868 EU, 915 US)
#define LORA_BANDWIDTH      125.0   // kHz
#define LORA_SPREAD_FACTOR  9       // 7-12 (higher = longer range, slower)
#define LORA_CODING_RATE    7       // 5-8
#define LORA_SYNC_WORD      0x12    // Private network sync word
#define LORA_TX_POWER       17      // dBm (2-20)
#define LORA_PREAMBLE       8       // Preamble length

// Packet header to identify our packets
#define PACKET_HEADER       "LIRR"

// =========================================================================
// Sensor Pins
// =========================================================================

// Capacitive soil moisture sensor (analog output)
#define SOIL_MOISTURE_PIN   34      // ADC1_CH6 (GPIO 34)

// BME280 - Air temperature + humidity + pressure (I2C)
// Shares I2C bus with BH1750: SDA=21, SCL=22
#define BME280_ADDR         0x76    // SDO to GND = 0x76, SDO to VCC = 0x77

// DS18B20 - Soil temperature (OneWire)
#define DS18B20_PIN         15      // GPIO 15

// BH1750 - Light intensity (I2C)
// Shares I2C bus with BME280: SDA=21, SCL=22
#define BH1750_ADDR         0x23    // ADDR pin LOW = 0x23, HIGH = 0x5C

// =========================================================================
// Calibration
// =========================================================================

// Soil moisture sensor calibration (raw ADC values)
// Measure these with your specific sensor:
//   DRY_VALUE  = ADC reading when sensor is in dry air
//   WET_VALUE  = ADC reading when sensor is submerged in water
#define MOISTURE_DRY_VALUE  3500    // ADC reading in dry air
#define MOISTURE_WET_VALUE  1500    // ADC reading in water

// =========================================================================
// Deep Sleep
// =========================================================================

// How long to sleep between readings (in seconds)
// 300 = 5 minutes (good for production)
//  30 = 30 seconds (good for testing/demo)
#define SLEEP_DURATION_SEC  300

// =========================================================================
// Misc
// =========================================================================

#define SERIAL_BAUD         115200
#define LED_PIN             4       // Built-in LED moved to GPIO 4 (GPIO 2 used by LoRa DIO0)
#define SENSOR_WARMUP_MS    2000    // Wait after power-on for sensors to stabilize
#define MAX_TX_RETRIES      3       // LoRa transmit retry count

#endif // CONFIG_H
