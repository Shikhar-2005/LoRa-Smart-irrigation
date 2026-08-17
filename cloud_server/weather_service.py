"""
LoRa Smart Irrigation - Weather Service
OpenWeatherMap API client for forecasts and rain-skip irrigation logic.
"""

import os
import time
import requests

OWM_API_KEY = os.environ.get('OWM_API_KEY', 'YOUR_OWM_API_KEY')
OWM_BASE_URL = 'https://api.openweathermap.org/data/2.5'

# In-memory cache to avoid redundant API calls
_cache = {}
CACHE_TTL = 1800  # 30 minutes


def _get_cached(key):
    """Return cached data if still valid, else None."""
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None


def _set_cache(key, data):
    _cache[key] = (data, time.time())


# --- Current Weather ---------------------------------------------------------

def get_current_weather(lat, lon):
    """Fetch current weather for given coordinates."""
    if OWM_API_KEY == 'YOUR_OWM_API_KEY':
        return _mock_weather()

    cache_key = f"current_{lat}_{lon}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(f"{OWM_BASE_URL}/weather", params={
            'lat': lat, 'lon': lon,
            'appid': OWM_API_KEY, 'units': 'metric'
        }, timeout=10)
        resp.raise_for_status()
        d = resp.json()

        result = {
            'temperature': d['main']['temp'],
            'feels_like': d['main'].get('feels_like'),
            'humidity': d['main']['humidity'],
            'description': d['weather'][0]['description'].title(),
            'icon': d['weather'][0]['icon'],
            'wind_speed': d['wind']['speed'],
            'pressure': d['main']['pressure'],
            'clouds': d['clouds']['all'],
            'city': d.get('name', 'Unknown'),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[Weather] Error fetching current weather: {e}")
        return _mock_weather()


# --- Hourly Forecast ---------------------------------------------------------

def get_hourly_forecast(lat, lon, periods=6):
    """Fetch 3-hour-step forecast and extract rain probabilities."""
    if OWM_API_KEY == 'YOUR_OWM_API_KEY':
        return _mock_forecast()

    cache_key = f"forecast_{lat}_{lon}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        resp = requests.get(f"{OWM_BASE_URL}/forecast", params={
            'lat': lat, 'lon': lon,
            'appid': OWM_API_KEY, 'units': 'metric',
            'cnt': periods,
        }, timeout=10)
        resp.raise_for_status()
        d = resp.json()

        forecasts = []
        for item in d['list'][:periods]:
            forecasts.append({
                'time': item['dt_txt'],
                'temperature': item['main']['temp'],
                'humidity': item['main']['humidity'],
                'description': item['weather'][0]['description'].title(),
                'icon': item['weather'][0]['icon'],
                'rain_chance': item.get('pop', 0) * 100,
                'rain_volume': item.get('rain', {}).get('3h', 0),
                'wind_speed': item['wind']['speed'],
            })

        result = {
            'forecasts': forecasts,
            'city': d.get('city', {}).get('name', 'Unknown'),
        }
        _set_cache(cache_key, result)
        return result
    except Exception as e:
        print(f"[Weather] Error fetching forecast: {e}")
        return _mock_forecast()


# --- Rain-Skip Logic ---------------------------------------------------------

def should_skip_irrigation(lat, lon, rain_threshold=60):
    """
    Check if irrigation should be skipped because rain is imminent.

    Returns:
        (should_skip: bool, reason: str, max_rain_chance: float)
    """
    forecast_data = get_hourly_forecast(lat, lon, periods=3)
    if not forecast_data or not forecast_data.get('forecasts'):
        return False, "No forecast data available", 0

    max_rain_chance = 0
    rain_period = None

    for fc in forecast_data['forecasts'][:2]:  # Next ~6 hours
        if fc['rain_chance'] > max_rain_chance:
            max_rain_chance = fc['rain_chance']
            rain_period = fc['time']

    if max_rain_chance >= rain_threshold:
        reason = f"Rain expected ({max_rain_chance:.0f}% chance) around {rain_period}"
        return True, reason, max_rain_chance

    return False, f"No significant rain expected (max {max_rain_chance:.0f}%)", max_rain_chance


# --- Mock Data (when API key not configured) ---------------------------------

def _mock_weather():
    return {
        'temperature': 28.5,
        'feels_like': 31.2,
        'humidity': 65,
        'description': 'Partly Cloudy',
        'icon': '02d',
        'wind_speed': 3.2,
        'pressure': 1013,
        'clouds': 40,
        'city': 'Demo City',
    }


def _mock_forecast():
    return {
        'forecasts': [
            {'time': '2026-08-17 18:00:00', 'temperature': 27.0, 'humidity': 70,
             'description': 'Light Rain', 'icon': '10d',
             'rain_chance': 45, 'rain_volume': 0.5, 'wind_speed': 4.1},
            {'time': '2026-08-17 21:00:00', 'temperature': 24.0, 'humidity': 80,
             'description': 'Moderate Rain', 'icon': '10n',
             'rain_chance': 72, 'rain_volume': 2.3, 'wind_speed': 5.5},
            {'time': '2026-08-18 00:00:00', 'temperature': 22.0, 'humidity': 85,
             'description': 'Cloudy', 'icon': '04n',
             'rain_chance': 30, 'rain_volume': 0, 'wind_speed': 2.8},
        ],
        'city': 'Demo City',
    }
