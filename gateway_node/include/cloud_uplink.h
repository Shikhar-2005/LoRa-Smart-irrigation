/*
 * LoRa Smart Irrigation - Cloud Uplink Interface
 *
 * WiFi connection management and HTTP POST to cloud server.
 */

#ifndef CLOUD_UPLINK_H
#define CLOUD_UPLINK_H

#include <Arduino.h>

// --- Public API -------------------------------------------------------------

/**
 * Connect to WiFi network defined in credentials.h.
 * Blocks until connected or timeout is reached.
 * Returns true if connected.
 */
bool wifi_connect();

/**
 * Check if WiFi is currently connected.
 */
bool wifi_is_connected();

/**
 * Reconnect WiFi if disconnected.
 * Returns true if connected after attempt.
 */
bool wifi_ensure_connected();

/**
 * POST sensor data to the cloud server's /api/predict endpoint.
 * Parses the JSON response to extract the irrigation decision.
 *
 * @param moisture    Soil moisture (%)
 * @param soil_temp   Soil temperature (C)
 * @param air_temp    Air temperature (C)
 * @param humidity    Relative humidity (%)
 * @param light       Light intensity (lux)
 * @param n           Nitrogen estimate
 * @param p           Phosphorus estimate
 * @param k           Potassium estimate
 *
 * Returns:
 *   1  = Cloud authorizes irrigation (HTTP 200, "irrigation.triggered" == true)
 *   0  = Cloud denies irrigation    (HTTP 200, "irrigation.triggered" == false,
 *                                    e.g. rain expected or moisture sufficient)
 *  -1  = Failure: WiFi disconnected, HTTP POST failed after retries,
 *                 or JSON deserialization error
 */
int cloud_post_reading(
    float moisture, float soil_temp, float air_temp,
    float humidity, float light,
    float n, float p, float k
);

#endif // CLOUD_UPLINK_H
