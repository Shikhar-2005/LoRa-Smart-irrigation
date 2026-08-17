/*
 * LoRa Smart Irrigation - Cloud Uplink Implementation
 *
 * Handles WiFi connection, JSON payload construction,
 * and HTTP POST with retry logic.
 */

#include "cloud_uplink.h"
#include "config.h"

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- WiFi Management --------------------------------------------------------

bool wifi_connect() {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    Serial.print("[*] Connecting to WiFi '");
    Serial.print(WIFI_SSID);
    Serial.print("'");

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_CONNECT_TIMEOUT) {
            Serial.println("\n[FAIL] WiFi connection timeout!");
            return false;
        }
        delay(500);
        Serial.print(".");
    }

    Serial.println();
    Serial.print("[OK] WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    return true;
}

bool wifi_is_connected() {
    return WiFi.status() == WL_CONNECTED;
}

bool wifi_ensure_connected() {
    if (wifi_is_connected()) {
        return true;
    }
    Serial.println("[*] WiFi disconnected, reconnecting...");
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
