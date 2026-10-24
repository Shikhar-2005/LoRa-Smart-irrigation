/*
 * LoRa Smart Irrigation - Sensor Interface
 *
 * Reads all field sensors. NPK values in the struct are legacy placeholders;
 * the cloud server overrides them with location + fertilizer based estimates.
 */

#ifndef SENSORS_H
#define SENSORS_H

#include <Arduino.h>

// --- Data Structure ---------------------------------------------------------

struct SensorData {
    float moisture;     // Soil moisture (0-100%)
    float soil_temp;    // Soil temperature (C) - DS18B20
    float air_temp;     // Air temperature (C) - BME280
    float humidity;     // Relative humidity (%) - BME280
    float pressure;     // Barometric pressure (hPa) - BME280
    float light;        // Light intensity (lux, 0-65535) - BH1750
    float n;            // Nitrogen   (legacy placeholder, overridden by cloud)
    float p;            // Phosphorus (legacy placeholder, overridden by cloud)
    float k;            // Potassium  (legacy placeholder, overridden by cloud)
    bool  valid;        // True if all critical readings succeeded
};

// --- Public API -------------------------------------------------------------

/**
 * Initialize all sensor peripherals.
 * Call once in setup().
 */
void sensors_init();

/**
 * Read all sensors. NPK fields are populated with legacy placeholder values;
 * the cloud server overrides them with location + fertilizer estimates.
 * Returns a SensorData struct with all values populated.
 */
SensorData sensors_read();

/**
 * Format sensor data into a LoRa-transmittable string.
 * Format: "LIRR,moisture,soil_temp,air_temp,humidity,light,n,p,k"
 * Note: pressure is logged locally but not transmitted (not used by ML model).
 */
String sensors_format_packet(const SensorData& data);

/**
 * Print sensor data to Serial for debugging.
 */
void sensors_print(const SensorData& data);

#endif // SENSORS_H
