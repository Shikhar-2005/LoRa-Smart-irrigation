/*
 * LoRa Smart Irrigation - Gateway Node (main)
 *
 * This node sits at the farm's WiFi edge. It:
 *   1. Listens for LoRa packets from the Field Node
 *   2. Parses sensor data from the received packet
 *   3. Decides whether to open the solenoid valve (irrigation)
 *   4. POSTs the data to the cloud server via WiFi
 *   5. Returns to listening
 *
 * The gateway stays powered on at all times (no deep sleep).
 */

#include <Arduino.h>
#include <RadioLib.h>

#include "config.h"
#include "cloud_uplink.h"

// --- LoRa Radio Object ------------------------------------------------------

SX1278 radio = new Module(LORA_CS_PIN, LORA_DIO0_PIN, LORA_RST_PIN, LORA_DIO1_PIN);

// --- State ------------------------------------------------------------------

static bool relay_active = false;
static unsigned long relay_on_time = 0;

// --- Forward Declarations ---------------------------------------------------

bool lora_init();
bool parse_packet(const String& packet,
                  float& moisture, float& soil_temp, float& air_temp,
                  float& humidity, float& light,
                  float& n, float& p, float& k);
void relay_init();
void relay_set(bool on);
void relay_update();
void blink_led(int times, int on_ms, int off_ms);

// --- Setup ------------------------------------------------------------------

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(100);

    pinMode(LED_PIN, OUTPUT);

    Serial.println("\n==========================================");
    Serial.println("  LoRa Smart Irrigation - Gateway Node");
    Serial.println("==========================================\n");

    // Initialize relay (OFF by default)
    relay_init();

    // Connect to WiFi
    if (!wifi_connect()) {
        Serial.println("[!!] WiFi failed - will retry on first packet");
    }

    // Initialize LoRa radio in receive mode
    if (!lora_init()) {
        Serial.println("[FAIL] LoRa init failed! Check wiring.");
        blink_led(10, 100, 100);  // Rapid blink = critical error
        // Don't halt - keep trying in loop
    }

    Serial.println("\n[*] Gateway ready. Listening for field packets...\n");
}

// --- Main Loop --------------------------------------------------------------

void loop() {
    // Check if relay needs to be turned off (auto-timeout)
    relay_update();

    // Try to receive a LoRa packet
    String packet;
    int state = radio.receive(packet);

    if (state == RADIOLIB_ERR_NONE) {
        // Packet received!
        Serial.println("================================================");
        Serial.print("[RX] Packet received (");
        Serial.print(packet.length());
        Serial.print(" bytes, RSSI: ");
        Serial.print(radio.getRSSI());
        Serial.print(" dBm, SNR: ");
        Serial.print(radio.getSNR());
        Serial.println(" dB)");
        Serial.print("     Raw: ");
        Serial.println(packet);

        // Parse the packet
        float moisture, soil_temp, air_temp, humidity, light, n, p, k;

        if (parse_packet(packet, moisture, soil_temp, air_temp,
                         humidity, light, n, p, k)) {

            Serial.println("[OK] Packet parsed successfully");
            Serial.print("     Moisture: "); Serial.print(moisture, 1); Serial.println("%");
            Serial.print("     Soil Temp: "); Serial.print(soil_temp, 1); Serial.println(" C");

            // --- Irrigation Decision ---
            if (moisture < MOISTURE_THRESHOLD) {
                Serial.print("[!!] Moisture below threshold (");
                Serial.print(MOISTURE_THRESHOLD, 1);
                Serial.println("%) - ACTIVATING IRRIGATION");
                relay_set(true);
                blink_led(3, 200, 100);  // Triple blink = irrigation ON
            } else {
                Serial.println("[OK] Moisture adequate - no irrigation needed");
                relay_set(false);
            }

            // --- Cloud Upload ---
            Serial.println("[*] Uploading to cloud server...");
            int http_code = cloud_post_reading(
                moisture, soil_temp, air_temp,
                humidity, light, n, p, k
            );

            if (http_code == 200) {
                Serial.println("[OK] Cloud upload successful");
                blink_led(1, 500, 0);  // Long blink = cloud OK
            } else {
                Serial.print("[FAIL] Cloud upload failed (HTTP ");
                Serial.print(http_code);
                Serial.println(")");
                blink_led(2, 100, 100);  // Short double = cloud fail
            }

        } else {
            Serial.println("[!!] Packet parse failed - ignoring");
        }

        Serial.println("================================================\n");

    } else if (state == RADIOLIB_ERR_RX_TIMEOUT) {
        // No packet received - this is normal, just keep listening
        // RadioLib's default receive timeout is ~2 seconds

    } else {
        // Some other error
        Serial.print("[!!] LoRa receive error: ");
        Serial.println(state);
    }
}

// --- LoRa Functions ---------------------------------------------------------

bool lora_init() {
    Serial.print("[*] Initializing LoRa SX1278 (RX mode)...");

    int state = radio.begin(
        LORA_FREQUENCY,
        LORA_BANDWIDTH,
        LORA_SPREAD_FACTOR,
        LORA_CODING_RATE,
        LORA_SYNC_WORD,
        LORA_TX_POWER,
        LORA_PREAMBLE
    );

    if (state == RADIOLIB_ERR_NONE) {
        Serial.println(" OK");
        return true;
    }

    Serial.print(" FAILED (code ");
    Serial.print(state);
    Serial.println(")");
    return false;
}

// --- Packet Parsing ---------------------------------------------------------

bool parse_packet(const String& packet,
                  float& moisture, float& soil_temp, float& air_temp,
                  float& humidity, float& light,
                  float& n, float& p, float& k) {
    // Expected format: LIRR,moisture,soil_temp,air_temp,humidity,light,n,p,k
    // Example:         LIRR,45.2,26.3,28.1,65.4,512,34.2,15.6,28.9

    // Check header
    if (!packet.startsWith(PACKET_HEADER)) {
        Serial.println("[!!] Invalid packet header");
        return false;
    }

    // Split by commas
    int idx = 0;
    int commaPositions[8];
    int commaCount = 0;

    for (int i = 0; i < (int)packet.length() && commaCount < 8; i++) {
        if (packet.charAt(i) == ',') {
            commaPositions[commaCount++] = i;
        }
    }

    if (commaCount != 8) {
        Serial.print("[!!] Expected 8 commas, got ");
        Serial.println(commaCount);
        return false;
    }

    // Extract values (field after each comma)
    moisture  = packet.substring(commaPositions[0] + 1, commaPositions[1]).toFloat();
    soil_temp = packet.substring(commaPositions[1] + 1, commaPositions[2]).toFloat();
    air_temp  = packet.substring(commaPositions[2] + 1, commaPositions[3]).toFloat();
    humidity  = packet.substring(commaPositions[3] + 1, commaPositions[4]).toFloat();
    light     = packet.substring(commaPositions[4] + 1, commaPositions[5]).toFloat();
    n         = packet.substring(commaPositions[5] + 1, commaPositions[6]).toFloat();
    p         = packet.substring(commaPositions[6] + 1, commaPositions[7]).toFloat();
    k         = packet.substring(commaPositions[7] + 1).toFloat();

    // Basic sanity check
    if (moisture < 0 || moisture > 100) {
        Serial.println("[!!] Moisture out of range");
        return false;
    }

    return true;
}

// --- Relay Control ----------------------------------------------------------

void relay_init() {
    pinMode(RELAY_PIN, OUTPUT);
    relay_set(false);  // Start with valve closed
    Serial.println("[OK] Relay initialized (OFF)");
}

void relay_set(bool on) {
    relay_active = on;

    if (RELAY_ACTIVE_HIGH) {
        digitalWrite(RELAY_PIN, on ? HIGH : LOW);
    } else {
        digitalWrite(RELAY_PIN, on ? LOW : HIGH);
    }

    if (on) {
        relay_on_time = millis();
        Serial.println("[RELAY] Valve OPEN");
    } else {
        Serial.println("[RELAY] Valve CLOSED");
    }
}

void relay_update() {
    // Auto-close valve after VALVE_ON_DURATION
    if (relay_active && (millis() - relay_on_time > VALVE_ON_DURATION)) {
        Serial.println("[RELAY] Auto-closing valve (timeout reached)");
        relay_set(false);
    }
}

// --- LED Utility ------------------------------------------------------------

void blink_led(int times, int on_ms, int off_ms) {
    for (int i = 0; i < times; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(on_ms);
        digitalWrite(LED_PIN, LOW);
        if (i < times - 1) delay(off_ms);
    }
}
