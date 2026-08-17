/*
 * LoRa Smart Irrigation - Sensor Interface
 *
 * Reads all field sensors and performs NPK soft-sensing estimation.
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
    float n;            // Nitrogen estimate (soft-sensed)
    float p;            // Phosphorus estimate (soft-sensed)
    float k;            // Potassium estimate (soft-sensed)
    bool  valid;        // True if all critical readings succeeded
};

// --- Public API -------------------------------------------------------------

/**
 * Initialize all sensor peripherals.
 * Call once in setup().
 */
void sensors_init();

/**
 * Read all sensors and compute NPK estimates.
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
