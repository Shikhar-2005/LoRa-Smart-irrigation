/*
 * LoRa Smart Irrigation - Field Node (main)
 *
 * Lifecycle:
 *   1. Wake from deep sleep
 *   2. Initialize sensors + LoRa radio
 *   3. Read all sensors + estimate NPK
 *   4. Transmit data packet over LoRa
 *   5. Enter deep sleep for SLEEP_DURATION_SEC
 *   6. Repeat
 *
 * Power budget: Active for ~3-5 seconds, then sleeps.
 * At 5-minute intervals, a 3000mAh battery lasts weeks.
 */

#include <Arduino.h>
#include <RadioLib.h>

#include "config.h"
#include "sensors.h"

// --- LoRa Radio Object ------------------------------------------------------

SX1278 radio = new Module(LORA_CS_PIN, LORA_DIO0_PIN, LORA_RST_PIN, LORA_DIO1_PIN);

// --- Forward Declarations ---------------------------------------------------

bool lora_init();
bool lora_send(const String& packet);
void enter_deep_sleep();
void blink_led(int times, int on_ms, int off_ms);

// --- Setup ------------------------------------------------------------------

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(100);

    // LED feedback
    pinMode(LED_PIN, OUTPUT);
    blink_led(1, 200, 0);

    Serial.println("\n========================================");
    Serial.println("  LoRa Smart Irrigation - Field Node");
    Serial.println("========================================\n");

    // Initialize LoRa radio
    if (!lora_init()) {
        Serial.println("[FAIL] LoRa init failed. Sleeping and retrying...");
        blink_led(5, 100, 100);  // Fast blink = error
        enter_deep_sleep();
        return;
    }

    // Initialize sensors
    sensors_init();
    delay(SENSOR_WARMUP_MS);

    // Read all sensors
    Serial.println("\n[*] Reading sensors...");
    SensorData data = sensors_read();
    sensors_print(data);

    if (!data.valid) {
        Serial.println("[!!] Some sensors failed - transmitting anyway");
    }

    // Format and transmit
    String packet = sensors_format_packet(data);
    Serial.print("[*] Packet: ");
    Serial.println(packet);
    Serial.print("[*] Packet size: ");
    Serial.print(packet.length());
    Serial.println(" bytes");

    bool sent = lora_send(packet);
    if (sent) {
        Serial.println("[OK] Packet transmitted successfully");
        blink_led(2, 150, 100);  // Double blink = success
    } else {
        Serial.println("[FAIL] Packet transmission failed after retries");
        blink_led(4, 100, 100);  // Quad blink = TX fail
    }

    // Sleep
    enter_deep_sleep();
}

void loop() {
    // Never reached - deep sleep resets to setup()
}

// --- LoRa Functions ---------------------------------------------------------

bool lora_init() {
    Serial.print("[*] Initializing LoRa SX1278...");

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

    if (state == RADIOLIB_ERR_CHIP_NOT_FOUND) {
        Serial.println("  -> SX1278 not found. Check SPI wiring!");
    }

    return false;
}

bool lora_send(const String& packet) {
    for (int attempt = 1; attempt <= MAX_TX_RETRIES; attempt++) {
        Serial.print("[*] TX attempt ");
        Serial.print(attempt);
        Serial.print("/");
        Serial.print(MAX_TX_RETRIES);
        Serial.print("...");

        String mutable_packet = packet;  // RadioLib transmit() needs mutable String&
        int state = radio.transmit(mutable_packet);

        if (state == RADIOLIB_ERR_NONE) {
            Serial.println(" OK");
            return true;
        }

        Serial.print(" FAILED (code ");
        Serial.print(state);
        Serial.println(")");

        if (attempt < MAX_TX_RETRIES) {
            delay(500);  // Brief pause before retry
        }
    }

    return false;
}

// --- Deep Sleep -------------------------------------------------------------

void enter_deep_sleep() {
    uint64_t sleep_us = (uint64_t)SLEEP_DURATION_SEC * 1000000ULL;

    Serial.print("\n[*] Entering deep sleep for ");
    Serial.print(SLEEP_DURATION_SEC);
    Serial.println(" seconds...");
    Serial.println("========================================\n");
    Serial.flush();

    // Turn off LED
    digitalWrite(LED_PIN, LOW);

    // Configure wakeup source
    esp_sleep_enable_timer_wakeup(sleep_us);

    // Enter deep sleep (wakes up via reset -> setup() runs again)
    esp_deep_sleep_start();
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
