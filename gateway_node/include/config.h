/*
 * LoRa Smart Irrigation - Gateway Node Configuration
 *
 * Pin assignments, LoRa parameters (must match field node),
 * WiFi credentials, server URL, and relay settings.
 *
 * IMPORTANT: Copy credentials.h.example to credentials.h and
 * fill in your WiFi password and server URL. credentials.h is
 * git-ignored to keep secrets out of version control.
 */

#ifndef CONFIG_H
#define CONFIG_H

#include "credentials.h"

// =========================================================================
// LoRa Radio (SX1278 via SPI)
// =========================================================================
// MUST match field_node/include/config.h exactly!
// Wiring:
//   NSS/CS  -> GPIO 5
//   RST     -> GPIO 14
//   DIO0    -> GPIO 2
//   SCK     -> GPIO 18
//   MISO    -> GPIO 19
//   MOSI    -> GPIO 23

#define LORA_CS_PIN     5
#define LORA_RST_PIN    14
#define LORA_DIO0_PIN   2
#define LORA_DIO1_PIN   -1

// These MUST be identical to field node
#define LORA_FREQUENCY      433.0
#define LORA_BANDWIDTH      125.0
#define LORA_SPREAD_FACTOR  9
#define LORA_CODING_RATE    7
#define LORA_SYNC_WORD      0x12
#define LORA_TX_POWER       17
#define LORA_PREAMBLE       8

// Packet header to identify valid packets
#define PACKET_HEADER       "LIRR"

// =========================================================================
// Relay / Solenoid Valve
// =========================================================================

#define RELAY_PIN           26      // GPIO 26 -> relay module IN
#define RELAY_ACTIVE_HIGH   true    // true = HIGH turns relay ON
#define VALVE_ON_DURATION   30000   // ms to keep valve open (30 sec)

// =========================================================================
// Irrigation Threshold
// =========================================================================

#define MOISTURE_THRESHOLD  30.0f   // Below this -> trigger irrigation

// =========================================================================
// Cloud Server
// =========================================================================

// HTTP POST timeout
#define HTTP_TIMEOUT_MS     10000
#define HTTP_MAX_RETRIES    3

// =========================================================================
// Misc
// =========================================================================

#define SERIAL_BAUD         115200
#define LED_PIN             2       // Built-in LED
#define WIFI_CONNECT_TIMEOUT 20000  // ms to wait for WiFi connection

#endif // CONFIG_H
