/*
 * LoRa Smart Irrigation - Cloud Uplink Implementation
 *
 * Uses WiFiManager for captive portal WiFi setup.
 * On first boot, the ESP32 creates a hotspot called "LoRa-Irrigation-Setup".
 * Connect to it from your phone, pick your WiFi, enter the password.
 * Credentials are saved to flash and used automatically on next boot.
 *
 * To reset saved WiFi: hold BOOT button during startup (GPIO 0).
 */

#include "cloud_uplink.h"
#include "config.h"

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiManager.h>

// --- WiFiManager instance ---
static WiFiManager wm;

// Reset pin: hold this LOW during boot to clear saved WiFi and re-enter setup
#define WIFI_RESET_PIN 0  // GPIO 0 = BOOT button on most ESP32 DevKits

// --- WiFi Management --------------------------------------------------------

bool wifi_connect() {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    // Check if user is holding the BOOT button to reset WiFi
    pinMode(WIFI_RESET_PIN, INPUT_PULLUP);
    delay(100);
    if (digitalRead(WIFI_RESET_PIN) == LOW) {
        Serial.println("[*] BOOT button held - clearing saved WiFi credentials!");
        wm.resetSettings();
        delay(500);
    }

    // WiFiManager settings
    wm.setConfigPortalTimeout(180);  // Portal stays open for 3 minutes
    wm.setConnectTimeout(15);        // Try each network for 15 seconds
    wm.setAPStaticIPConfig(IPAddress(192,168,4,1), IPAddress(192,168,4,1), IPAddress(255,255,255,0));

    Serial.println("[*] Starting WiFiManager...");
    Serial.println("    If no saved WiFi found, connect to hotspot:");
    Serial.println("    SSID: 'LoRa-Irrigation-Setup'");
    Serial.println("    Then open 192.168.4.1 in your browser");

    // autoConnect: tries saved credentials first.
    // If they fail (or none saved), starts AP with captive portal.
    bool connected = wm.autoConnect("LoRa-Irrigation-Setup");

    if (connected) {
        Serial.print("[OK] WiFi connected! IP: ");
        Serial.println(WiFi.localIP());
        return true;
    } else {
        Serial.println("[FAIL] WiFi setup timed out. Will retry next cycle.");
        return false;
    }
}

bool wifi_is_connected() {
    return WiFi.status() == WL_CONNECTED;
}

bool wifi_ensure_connected() {
    if (wifi_is_connected()) {
        return true;
    }
    Serial.println("[*] WiFi lost, reconnecting...");
    // Try reconnecting with saved credentials
    WiFi.reconnect();
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_CONNECT_TIMEOUT) {
        delay(500);
        Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[OK] Reconnected!");
        return true;
    }
    // If reconnect fails, start the portal again
    Serial.println("\n[*] Reconnect failed, starting setup portal...");
    return wifi_connect();
}

// --- HTTP POST --------------------------------------------------------------

int cloud_post_reading(
    float moisture, float soil_temp, float air_temp,
    float humidity, float light,
    float n, float p, float k
) {
    if (!wifi_ensure_connected()) {
        Serial.println("[FAIL] Cannot POST - WiFi not connected");
        return -1;
    }

    // Build JSON payload
    JsonDocument doc;
    doc["moisture"]  = round(moisture * 10.0f) / 10.0f;
    doc["soil_temp"] = round(soil_temp * 10.0f) / 10.0f;
    doc["air_temp"]  = round(air_temp * 10.0f) / 10.0f;
    doc["humidity"]  = round(humidity * 10.0f) / 10.0f;
    doc["light"]     = round(light);
    doc["n"]         = round(n * 10.0f) / 10.0f;
    doc["p"]         = round(p * 10.0f) / 10.0f;
    doc["k"]         = round(k * 10.0f) / 10.0f;

    String payload;
    serializeJson(doc, payload);

    Serial.print("[*] POST ");
    Serial.println(API_PREDICT_URL);
    Serial.print("    Payload: ");
    Serial.println(payload);

    // HTTP POST with retries
    int responseCode = -1;

    for (int attempt = 1; attempt <= HTTP_MAX_RETRIES; attempt++) {
        HTTPClient http;
        http.begin(API_PREDICT_URL);
        http.addHeader("Content-Type", "application/json");
        http.setTimeout(HTTP_TIMEOUT_MS);

        responseCode = http.POST(payload);

        if (responseCode == 200) {
            String response = http.getString();
            Serial.print("[OK] Server response (");
            Serial.print(responseCode);
            Serial.print("): ");
            Serial.println(response.substring(0, 200));
            http.end();
            return responseCode;
        }

        Serial.print("[!!] HTTP POST failed (attempt ");
        Serial.print(attempt);
        Serial.print("/");
        Serial.print(HTTP_MAX_RETRIES);
        Serial.print("): code ");
        Serial.println(responseCode);

        if (responseCode > 0) {
            Serial.print("    Response: ");
            Serial.println(http.getString().substring(0, 200));
        }

        http.end();

        if (attempt < HTTP_MAX_RETRIES) {
            delay(2000);  // Wait before retry
        }
    }

    return responseCode;
}
