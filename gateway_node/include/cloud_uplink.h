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
 * Returns HTTP response code (200 = success), or -1 on failure.
 */
int cloud_post_reading(
    float moisture, float soil_temp, float air_temp,
    float humidity, float light,
    float n, float p, float k
);

#endif // CLOUD_UPLINK_H
