/*
 * LoRa Smart Irrigation - Sensor Implementations
 *
 * Reads capacitive soil moisture (ADC), BME280 (air temp + humidity +
 * pressure), DS18B20 (soil temperature), BH1750 (light intensity),
 * then computes NPK estimates using empirical soft-sensing formulas.
 */

#include "sensors.h"
#include "config.h"

#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BME280.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <BH1750.h>

// --- Sensor Objects ---------------------------------------------------------

static Adafruit_BME280 bme;
static OneWire oneWire(DS18B20_PIN);
static DallasTemperature ds18b20(&oneWire);
static BH1750 lightMeter(BH1750_ADDR);

static bool bme_ok = false;

// --- Init -------------------------------------------------------------------

void sensors_init() {
    // Soil moisture - analog input
    analogReadResolution(12);       // 12-bit ADC (0-4095)
    analogSetAttenuation(ADC_11db); // Full 0-3.3V range

    // I2C bus (shared by BME280 + BH1750)
    Wire.begin();

    // BME280 (I2C)
    bme_ok = bme.begin(BME280_ADDR);
    if (bme_ok) {
        // Configure for weather monitoring (low power)
        bme.setSampling(
            Adafruit_BME280::MODE_FORCED,   // Take reading only when asked
            Adafruit_BME280::SAMPLING_X1,   // Temperature oversampling
            Adafruit_BME280::SAMPLING_X1,   // Pressure oversampling
            Adafruit_BME280::SAMPLING_X1,   // Humidity oversampling
            Adafruit_BME280::FILTER_OFF,    // No IIR filter
            Adafruit_BME280::STANDBY_MS_1000
        );
        Serial.println("[OK] BME280 initialized");
    } else {
        Serial.println("[!!] BME280 init FAILED - check wiring (I2C addr 0x76/0x77)");
    }

    // DS18B20 (OneWire)
    ds18b20.begin();
    int ds_count = ds18b20.getDeviceCount();
    Serial.print("[OK] DS18B20 devices found: ");
    Serial.println(ds_count);

    // BH1750 (I2C)
    if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
        Serial.println("[OK] BH1750 initialized");
    } else {
        Serial.println("[!!] BH1750 init FAILED - check wiring");
    }
}

// --- Individual Sensor Reads ------------------------------------------------

static float read_moisture() {
    // Take multiple readings and average for stability
    long sum = 0;
    const int samples = 10;

    for (int i = 0; i < samples; i++) {
        sum += analogRead(SOIL_MOISTURE_PIN);
        delay(10);
    }
    float raw = (float)sum / samples;

    // Map ADC range to 0-100% (inverted: higher ADC = drier)
    float pct = ((float)MOISTURE_DRY_VALUE - raw)
              / ((float)MOISTURE_DRY_VALUE - (float)MOISTURE_WET_VALUE)
              * 100.0f;

    // Clamp to valid range
    if (pct < 0.0f) pct = 0.0f;
    if (pct > 100.0f) pct = 100.0f;

    return pct;
}

static float read_air_temp() {
    if (!bme_ok) return -999.0f;
    bme.takeForcedMeasurement();
    float t = bme.readTemperature();
    if (isnan(t)) {
        Serial.println("[!!] BME280 temperature read failed");
        return -999.0f;
    }
    return t;
}

static float read_humidity() {
    if (!bme_ok) return -999.0f;
    float h = bme.readHumidity();
    if (isnan(h)) {
        Serial.println("[!!] BME280 humidity read failed");
        return -999.0f;
    }
    return h;
}

static float read_pressure() {
    if (!bme_ok) return -999.0f;
    float p = bme.readPressure() / 100.0f;  // Pa -> hPa
    if (isnan(p)) {
        Serial.println("[!!] BME280 pressure read failed");
        return -999.0f;
    }
    return p;
}

static float read_soil_temp() {
    ds18b20.requestTemperatures();
    float t = ds18b20.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C) {
        Serial.println("[!!] DS18B20 read failed - disconnected?");
        return -999.0f;
    }
    return t;
}

static float read_light() {
    float lux = lightMeter.readLightLevel();
    if (lux < 0) {
        Serial.println("[!!] BH1750 read failed");
        return 0.0f;
    }
    return lux;
}

// --- NPK Soft-Sensing -------------------------------------------------------
//
// These formulas estimate N, P, K from physical sensor readings.
// They are empirical proxies -- not a replacement for real soil testing.
// The ML model on the cloud server is trained to work with these estimates.
//
// IMPORTANT: These formulas MUST match cloud_server/flask_app.py api_simulate()

static void estimate_npk(SensorData& data) {
    float m  = data.moisture;
    float st = data.soil_temp;
    float at = data.air_temp;
    float h  = data.humidity;
    float li = data.light;

    data.n = 0.35f * m * (1.0f + 0.02f * st) + 4.0f * (h / 100.0f);
    data.p = 0.20f * m * (1.0f - 0.005f * at) + 8.0f * (1.0f - h / 150.0f);
    data.k = 0.25f * m * (1.0f + 0.003f * li) + 6.0f * st / 40.0f;
}

// --- Public API -------------------------------------------------------------

SensorData sensors_read() {
    SensorData data;
    data.valid = true;

    data.moisture  = read_moisture();
    data.air_temp  = read_air_temp();
    data.humidity  = read_humidity();
    data.pressure  = read_pressure();
    data.soil_temp = read_soil_temp();
    data.light     = read_light();

    // Check for failed readings
    if (data.air_temp < -900 || data.humidity < -900 || data.soil_temp < -900) {
        data.valid = false;
    }

    // Compute NPK estimates (even with partial data, for logging)
    estimate_npk(data);

    return data;
}

String sensors_format_packet(const SensorData& data) {
    // Format: LIRR,moisture,soil_temp,air_temp,humidity,light,n,p,k
    // Note: pressure is NOT included in the packet (not needed by ML model)
    char buf[128];
    snprintf(buf, sizeof(buf),
        "%s,%.1f,%.1f,%.1f,%.1f,%.0f,%.1f,%.1f,%.1f",
        PACKET_HEADER,
        data.moisture, data.soil_temp, data.air_temp,
        data.humidity, data.light,
        data.n, data.p, data.k
    );
    return String(buf);
}

void sensors_print(const SensorData& data) {
    Serial.println("--- Sensor Readings ---");
    Serial.print("  Moisture:  "); Serial.print(data.moisture, 1); Serial.println("%");
    Serial.print("  Soil Temp: "); Serial.print(data.soil_temp, 1); Serial.println(" C");
    Serial.print("  Air Temp:  "); Serial.print(data.air_temp, 1); Serial.println(" C");
    Serial.print("  Humidity:  "); Serial.print(data.humidity, 1); Serial.println("%");
    Serial.print("  Pressure:  "); Serial.print(data.pressure, 1); Serial.println(" hPa");
    Serial.print("  Light:     "); Serial.print(data.light, 0); Serial.println(" lux");
    Serial.print("  N (est):   "); Serial.println(data.n, 1);
    Serial.print("  P (est):   "); Serial.println(data.p, 1);
    Serial.print("  K (est):   "); Serial.println(data.k, 1);
    Serial.print("  Valid:     "); Serial.println(data.valid ? "YES" : "NO");
    Serial.println("-----------------------");
}
