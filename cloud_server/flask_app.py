"""
LoRa Smart Irrigation - Flask Application
Main server: REST API, ML inference, sensor storage, and dashboard serving.
"""

import os
import json
import random
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
import joblib
import numpy as np

from database import (
    init_db, store_reading, store_alert,
    get_latest, get_history, get_alerts, get_stats,
    get_setting, set_setting,
)
from telegram_bot import send_alert, format_sensor_alert, format_weather_alert
from weather_service import get_current_weather, get_hourly_forecast, should_skip_irrigation
from region_crops import filter_predictions, get_region_for_city, get_available_regions, get_default_soil_for_city
from soil_service import (
    calculate_estimated_npk,
    get_available_soil_types, get_available_fertilizers, get_available_dosages,
)

# --- App Setup ---------------------------------------------------------------

app = Flask(__name__)

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crop_model.pkl')
MOISTURE_THRESHOLD = 30  # Below this -> irrigation triggered

model = None


def load_model():
    """Load the trained Random Forest model from disk."""
    global model
    if os.path.exists(MODEL_PATH):
        model = joblib.load(MODEL_PATH)
        print(f"[OK] ML model loaded ({MODEL_PATH})")
    else:
        print("[!] Model not found - run train_model.py first!")


# --- ML Inference ------------------------------------------------------------

def map_sensor_to_features(data, ph_override=None):
    """Map raw sensor readings to the 7 features the ML model expects.

    Args:
        data: dict with sensor + NPK values
        ph_override: if provided, use this pH instead of the empirical proxy
    """
    if ph_override is not None:
        ph = ph_override
    else:
        ph = 6.5 + 0.01 * (data['moisture'] - 50)       # Empirical proxy fallback
    rainfall = data['moisture'] * 2.5                      # Empirical proxy

    return np.array([[
        data['n'],          # Nitrogen   (location + fertilizer based)
        data['p'],          # Phosphorus (location + fertilizer based)
        data['k'],          # Potassium  (location + fertilizer based)
        data['soil_temp'],  # temperature
        data['humidity'],   # humidity
        ph,                 # ph (from soil profile or proxy)
        rainfall,           # rainfall
    ]])


def predict_crop(data, ph_override=None):
    """Run ML prediction; return top crops with confidence scores."""
    if model is None:
        return {'crop': 'Model not loaded', 'confidence': 0, 'top_3': [], 'top_5': []}

    features = map_sensor_to_features(data, ph_override=ph_override)
    prediction = model.predict(features)[0]
    probabilities = model.predict_proba(features)[0]
    classes = model.classes_

    ranked = sorted(zip(classes, probabilities), key=lambda x: -x[1])
    top5 = [(c, round(p * 100, 2)) for c, p in ranked[:5]]

    return {
        'crop': prediction,
        'confidence': round(float(max(probabilities)) * 100, 2),
        'top_3': top5[:3],
        'top_5': top5,
    }


# --- Helpers -----------------------------------------------------------------

def _compute_cloud_npk():
    """Compute NPK from saved soil + fertilizer settings.
    Returns the full result dict from soil_service, or None if not configured."""
    soil_type = get_setting('soil_type', 'alluvial')
    fert_type = get_setting('fertilizer_type', 'none')
    fert_dose = get_setting('fertilizer_dose', 'none')
    return calculate_estimated_npk(soil_type, fert_type, fert_dose)


def _apply_region_filter(prediction):
    """Apply region-based crop filtering if a city is configured."""
    city = get_setting('city', '')
    region = get_region_for_city(city)
    if region != 'any':
        filtered = filter_predictions(prediction['top_5'], region)
        prediction['top_5'] = filtered
        prediction['top_3'] = filtered[:3]
        if filtered:
            prediction['crop'] = filtered[0][0]
            prediction['confidence'] = filtered[0][1]
        prediction['region'] = region
    return prediction


def _check_rain_skip(moisture):
    """Check weather forecast for rain-skip logic. Returns (triggered, skipped, reason)."""
    irrigation_triggered = moisture < MOISTURE_THRESHOLD
    rain_skipped = False
    skip_reason = ''

    lat = get_setting('latitude')
    lon = get_setting('longitude')

    if lat and lon and irrigation_triggered:
        should_skip, reason, _ = should_skip_irrigation(float(lat), float(lon))
        if should_skip:
            irrigation_triggered = False
            rain_skipped = True
            skip_reason = reason

    return irrigation_triggered, rain_skipped, skip_reason


def _generate_alerts(data, irrigation_triggered, rain_skipped, skip_reason):
    """Generate and store relevant alerts based on sensor data."""
    if irrigation_triggered:
        msg = f"Irrigation activated! Moisture at {data['moisture']:.1f}% (threshold: {MOISTURE_THRESHOLD}%)"
        store_alert('irrigation', msg, json.dumps(data))
    elif rain_skipped:
        msg = f"Irrigation skipped - {skip_reason}"
        store_alert('rain_skip', msg, json.dumps(data))

    if data['moisture'] < 20:
        store_alert('critical',
                    f"CRITICAL: Soil moisture dangerously low at {data['moisture']:.1f}%!")
    if data['soil_temp'] > 40:
        store_alert('warning',
                    f"WARNING: Soil temperature high at {data['soil_temp']:.1f} C")


# --- Routes ------------------------------------------------------------------

@app.route('/')
def dashboard():
    """Serve the main monitoring dashboard."""
    return render_template('dashboard.html')


@app.route('/api/predict', methods=['POST'])
def api_predict():
    """
    Receive sensor data from Gateway ESP32, run ML prediction, store reading,
    apply irrigation logic, and send Telegram alerts.

    Expected JSON: {moisture, soil_temp, air_temp, humidity, light, n, p, k}
    Note: n, p, k from the edge are legacy dummy values and are overridden
    by the cloud-side location + fertilizer model when configured.
    """
    try:
        data = request.get_json(force=True)

        # Validate physical sensor fields (n, p, k accepted but may be overridden)
        required = ['moisture', 'soil_temp', 'air_temp', 'humidity', 'light']
        for field in required:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
            data[field] = float(data[field])

        # Ensure n, p, k exist (edge may still send them)
        for field in ['n', 'p', 'k']:
            data[field] = float(data.get(field, 0))

        # Override edge NPK with cloud-computed location + fertilizer model
        npk_result = _compute_cloud_npk()
        ph_override = None
        if npk_result:
            data['n'] = npk_result['n']
            data['p'] = npk_result['p']
            data['k'] = npk_result['k']
            ph_override = npk_result['ph']

        # ML prediction + region filter
        prediction = predict_crop(data, ph_override=ph_override)
        prediction = _apply_region_filter(prediction)

        # Irrigation + weather logic
        irrigation_triggered, rain_skipped, skip_reason = _check_rain_skip(data['moisture'])

        # Store reading
        data['predicted_crop'] = prediction['crop']
        data['confidence'] = prediction['confidence']
        data['irrigation_triggered'] = 1 if irrigation_triggered else 0
        reading_id = store_reading(data)

        # Alerts
        _generate_alerts(data, irrigation_triggered, rain_skipped, skip_reason)

        # Telegram
        if rain_skipped:
            lat, lon = float(get_setting('latitude')), float(get_setting('longitude'))
            weather = get_current_weather(lat, lon)
            send_alert(format_weather_alert(data, weather, skip_reason))
        else:
            send_alert(format_sensor_alert(data, prediction, irrigation_triggered))

        return jsonify({
            'status': 'ok',
            'reading_id': reading_id,
            'prediction': prediction,
            'irrigation': {
                'triggered': irrigation_triggered,
                'moisture': data['moisture'],
                'threshold': MOISTURE_THRESHOLD,
                'rain_skipped': rain_skipped,
                'skip_reason': skip_reason,
            },
            'timestamp': datetime.utcnow().isoformat(),
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/latest')
def api_latest():
    """Most recent sensor reading."""
    latest = get_latest()
    if latest:
        return jsonify(latest), 200
    return jsonify({'message': 'No readings yet'}), 404


@app.route('/api/history')
def api_history():
    """Historical sensor readings (default: last 24 h)."""
    hours = min(request.args.get('hours', 24, type=int), 720)
    readings = get_history(hours)
    return jsonify({'readings': readings, 'count': len(readings)}), 200


@app.route('/api/alerts')
def api_alerts():
    """Recent alerts."""
    limit = request.args.get('limit', 50, type=int)
    alerts_list = get_alerts(limit)
    return jsonify({'alerts': alerts_list, 'count': len(alerts_list)}), 200


@app.route('/api/stats')
def api_stats():
    """Summary statistics for the dashboard."""
    return jsonify(get_stats()), 200


@app.route('/api/weather')
def api_weather():
    """Current weather + forecast for configured location."""
    lat = get_setting('latitude')
    lon = get_setting('longitude')
    if not lat or not lon:
        return jsonify({'error': 'Location not configured. Set via /api/settings.'}), 400

    lat, lon = float(lat), float(lon)
    current = get_current_weather(lat, lon)
    forecast = get_hourly_forecast(lat, lon)
    skip, reason, chance = should_skip_irrigation(lat, lon)

    return jsonify({
        'current': current,
        'forecast': forecast,
        'rain_skip': {'should_skip': skip, 'reason': reason, 'rain_chance': chance},
        'location': {
            'latitude': lat, 'longitude': lon,
            'city': get_setting('city', 'Unknown'),
        },
    }), 200


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update system settings (location, soil, fertilizer)."""
    if request.method == 'POST':
        data = request.get_json(force=True)
        for key in ('latitude', 'longitude', 'city',
                    'soil_type', 'fertilizer_type', 'fertilizer_dose'):
            if key in data:
                set_setting(key, data[key])

        # Auto-detect soil type from city if not explicitly set
        if 'city' in data and 'soil_type' not in data:
            city = data['city']
            if city:
                auto_soil = get_default_soil_for_city(city)
                set_setting('soil_type', auto_soil)

        return jsonify({'status': 'ok', 'message': 'Settings updated'}), 200

    # Compute current NPK estimate for display
    npk_result = _compute_cloud_npk()

    return jsonify({
        'latitude': get_setting('latitude', ''),
        'longitude': get_setting('longitude', ''),
        'city': get_setting('city', ''),
        'soil_type': get_setting('soil_type', 'alluvial'),
        'fertilizer_type': get_setting('fertilizer_type', 'none'),
        'fertilizer_dose': get_setting('fertilizer_dose', 'none'),
        'npk_estimate': npk_result,
        'regions': get_available_regions(),
        'available_soils': get_available_soil_types(),
        'available_fertilizers': get_available_fertilizers(),
        'available_dosages': get_available_dosages(),
    }), 200


@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    """
    Inject simulated sensor data for testing without hardware.
    Generates random but realistic physical readings, then uses
    the location + fertilizer model for NPK estimation.
    """
    m  = round(random.uniform(15, 85), 1)
    st = round(random.uniform(18, 38), 1)
    at = round(random.uniform(20, 42), 1)
    h  = round(random.uniform(30, 95), 1)
    li = round(random.uniform(100, 1000), 0)

    # NPK from location + fertilizer model (replaces old pseudo-formulas)
    npk_result = _compute_cloud_npk()
    ph_override = None
    if npk_result:
        n, p, k = npk_result['n'], npk_result['p'], npk_result['k']
        ph_override = npk_result['ph']
    else:
        # Fallback if no soil profile configured
        n, p, k = 75.0, 45.0, 45.0

    sim_data = {
        'moisture': m, 'soil_temp': st, 'air_temp': at,
        'humidity': h, 'light': li, 'n': n, 'p': p, 'k': k,
    }

    # ML prediction + region filter
    prediction = predict_crop(sim_data, ph_override=ph_override)
    prediction = _apply_region_filter(prediction)

    # Irrigation logic
    irrigation_triggered = m < MOISTURE_THRESHOLD

    # Store
    sim_data['predicted_crop'] = prediction['crop']
    sim_data['confidence'] = prediction['confidence']
    sim_data['irrigation_triggered'] = 1 if irrigation_triggered else 0
    reading_id = store_reading(sim_data)

    if irrigation_triggered:
        store_alert('irrigation',
                    f"[SIM] Irrigation activated! Moisture: {m:.1f}%")

    return jsonify({
        'status': 'ok',
        'simulated_data': sim_data,
        'prediction': prediction,
        'irrigation_triggered': irrigation_triggered,
        'reading_id': reading_id,
    }), 200


# --- Startup -----------------------------------------------------------------

with app.app_context():
    init_db()
    load_model()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
