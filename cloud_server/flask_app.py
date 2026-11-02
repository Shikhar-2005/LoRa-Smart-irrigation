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
    get_recent_moisture_readings, get_soil_health_inputs, get_irrigation_event_count,
)
from telegram_bot import send_alert, format_sensor_alert, format_weather_alert
from weather_service import get_current_weather, get_hourly_forecast, should_skip_irrigation
from region_crops import filter_predictions, get_region_for_city, get_available_regions, get_default_soil_for_city
from soil_service import (
    calculate_estimated_npk,
    get_available_soil_types, get_available_fertilizers, get_available_dosages,
    get_top3_with_prescriptions, compute_soil_health_score,
    get_sowing_window, check_disease_risk,
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

    # Disease / stress risk alerts
    top_crop = data.get('predicted_crop', '')
    risks = check_disease_risk(data['air_temp'], data['humidity'], data['moisture'], top_crop)
    for risk in risks:
        if risk['severity'] == 'HIGH':
            store_alert('warning',
                        f"[DISEASE RISK] {risk['name']}: {risk['recommendation'][:120]}")

    # Waterlogging risk: moisture very high AND rain was just skipped
    if rain_skipped and data['moisture'] > 80:
        store_alert('warning',
                    f"Waterlogging risk: moisture at {data['moisture']:.1f}% AND rain expected. "
                    f"Do NOT irrigate. Check field drainage.")


def _compute_moisture_trend():
    """
    Compute moisture drying/wetting rate from the last 10 readings.

    Returns:
        dict with:
            slope_pct_per_hour : float  (negative = drying, positive = wetting)
            hours_until_threshold : float | None
            trend_label : str  ('Drying Fast', 'Drying', 'Stable', 'Wetting')
    """
    readings = get_recent_moisture_readings(10)
    if len(readings) < 2:
        return {
            'slope_pct_per_hour': 0.0,
            'hours_until_threshold': None,
            'trend_label': 'Insufficient data',
        }

    # Convert timestamps to hours relative to first reading
    try:
        times = []
        moistures = []
        for r in readings:
            ts = r['timestamp']
            # Handle both 'YYYY-MM-DD HH:MM:SS' and ISO formats
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
                try:
                    dt = datetime.strptime(ts, fmt)
                    break
                except ValueError:
                    dt = None
            if dt is None:
                continue
            times.append(dt.timestamp() / 3600.0)   # hours since epoch
            moistures.append(r['moisture'])

        if len(times) < 2:
            raise ValueError("not enough valid timestamps")

        # Least-squares slope
        n = len(times)
        t_mean = sum(times) / n
        m_mean = sum(moistures) / n
        num = sum((times[i] - t_mean) * (moistures[i] - m_mean) for i in range(n))
        den = sum((times[i] - t_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0.0

        # Hours until threshold from current moisture
        current_moisture = moistures[-1]
        if slope < -0.01:
            hours_until = (current_moisture - MOISTURE_THRESHOLD) / abs(slope)
            hours_until = round(max(0.0, hours_until), 1)
        else:
            hours_until = None

        if slope < -2.0:
            label = 'Drying Fast'
        elif slope < -0.5:
            label = 'Drying'
        elif slope > 0.5:
            label = 'Wetting'
        else:
            label = 'Stable'

        return {
            'slope_pct_per_hour': round(slope, 2),
            'hours_until_threshold': hours_until,
            'trend_label': label,
            'current_moisture': round(current_moisture, 1),
        }

    except Exception:
        return {
            'slope_pct_per_hour': 0.0,
            'hours_until_threshold': None,
            'trend_label': 'Stable',
        }


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

        # --- Agronomic advisory layer ----------------------------------------
        # top_3 from predict_crop returns (crop, probability_pct) tuples;
        # get_top3_with_prescriptions expects (crop, probability_fraction) tuples.
        top3_raw = [(c, p / 100.0) for c, p in prediction['top_3']]
        top3_enriched = get_top3_with_prescriptions(
            top3_raw, data['n'], data['p'], data['k'])

        soil_health = compute_soil_health_score(get_soil_health_inputs())
        moisture_trend = _compute_moisture_trend()
        disease_risks = check_disease_risk(
            data['air_temp'], data['humidity'], data['moisture'],
            prediction['crop'])

        # Irrigation + weather logic
        irrigation_triggered, rain_skipped, skip_reason = _check_rain_skip(data['moisture'])

        # Determine decision source
        if rain_skipped:
            decision_source = 'WEATHER_SKIP'
        elif model is not None:
            decision_source = 'CLOUD_ML'
        else:
            decision_source = 'LOCAL_FALLBACK'

        # Store reading (with advisory fields)
        data['predicted_crop'] = prediction['crop']
        data['confidence'] = prediction['confidence']
        data['irrigation_triggered'] = 1 if irrigation_triggered else 0
        data['top_crops_json'] = json.dumps(top3_enriched)
        data['soil_health_score'] = soil_health['score']
        data['decision_source'] = decision_source
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
            'top_3_enriched': top3_enriched,
            'soil_health': soil_health,
            'moisture_trend': moisture_trend,
            'disease_risks': disease_risks,
            'decision_source': decision_source,
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

    # Agronomic advisory layer
    top3_raw = [(c, p / 100.0) for c, p in prediction['top_3']]
    top3_enriched = get_top3_with_prescriptions(top3_raw, n, p, k)
    soil_health = compute_soil_health_score(get_soil_health_inputs())
    moisture_trend = _compute_moisture_trend()
    disease_risks = check_disease_risk(at, h, m, prediction['crop'])

    # Store
    sim_data['predicted_crop'] = prediction['crop']
    sim_data['confidence'] = prediction['confidence']
    sim_data['irrigation_triggered'] = 1 if irrigation_triggered else 0
    sim_data['top_crops_json'] = json.dumps(top3_enriched)
    sim_data['soil_health_score'] = soil_health['score']
    sim_data['decision_source'] = 'CLOUD_ML' if model else 'LOCAL_FALLBACK'
    reading_id = store_reading(sim_data)

    if irrigation_triggered:
        store_alert('irrigation',
                    f"[SIM] Irrigation activated! Moisture: {m:.1f}%")

    return jsonify({
        'status': 'ok',
        'simulated_data': sim_data,
        'prediction': prediction,
        'top_3_enriched': top3_enriched,
        'soil_health': soil_health,
        'moisture_trend': moisture_trend,
        'disease_risks': disease_risks,
        'irrigation_triggered': irrigation_triggered,
        'reading_id': reading_id,
    }), 200


@app.route('/api/advisory')
def api_advisory():
    """
    Return the full agronomic advisory payload for the dashboard:
    - Top-3 enriched crop recommendations with NPK prescription
    - Soil health score
    - Moisture trend forecast
    - Disease / stress risks
    - Sowing window for the top recommended crop
    """
    try:
        latest = get_latest()
        if not latest:
            return jsonify({'error': 'No readings yet'}), 404

        n = latest.get('n_estimated', 75.0) or 75.0
        p = latest.get('p_estimated', 45.0) or 45.0
        k = latest.get('k_estimated', 45.0) or 45.0
        top_crop = latest.get('predicted_crop', '')
        air_temp = latest.get('air_temp', 25.0) or 25.0
        humidity = latest.get('humidity', 60.0) or 60.0
        moisture = latest.get('moisture', 50.0) or 50.0

        # Try to parse top_crops_json if stored, else regenerate
        top3_enriched = None
        raw_json = latest.get('top_crops_json')
        if raw_json:
            try:
                top3_enriched = json.loads(raw_json)
            except Exception:
                pass

        if not top3_enriched:
            # Regenerate from latest prediction
            if top_crop:
                top3_raw = [(top_crop, 1.0)]
                top3_enriched = get_top3_with_prescriptions(top3_raw, n, p, k)
            else:
                top3_enriched = []

        soil_health = compute_soil_health_score(get_soil_health_inputs())
        moisture_trend = _compute_moisture_trend()
        disease_risks = check_disease_risk(air_temp, humidity, moisture, top_crop)

        # Irrigation adequacy: compare last two readings
        recent = get_recent_moisture_readings(5)
        irrigation_adequacy = None
        if len(recent) >= 2:
            prev = recent[-2]['moisture'] if recent[-2]['moisture'] else None
            curr = recent[-1]['moisture'] if recent[-1]['moisture'] else None
            if prev is not None and curr is not None and curr > prev:
                recovery = round(curr - prev, 1)
                target = 45.0
                adequate = curr >= target
                irrigation_adequacy = {
                    'recovery_pct': recovery,
                    'current_moisture': round(curr, 1),
                    'target_pct': target,
                    'adequate': adequate,
                    'note': (
                        f'Moisture recovered by {recovery}% after last irrigation. '
                        + ('Adequate.' if adequate
                           else f'Below target of {target}%. Consider longer irrigation next cycle.')
                    ),
                }

        return jsonify({
            'top_3_enriched':       top3_enriched,
            'soil_health':          soil_health,
            'moisture_trend':       moisture_trend,
            'disease_risks':        disease_risks,
            'irrigation_adequacy':  irrigation_adequacy,
            'irrigation_24h':       get_irrigation_event_count(24),
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Startup -----------------------------------------------------------------

with app.app_context():
    init_db()
    load_model()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
