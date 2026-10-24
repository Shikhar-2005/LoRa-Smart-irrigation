"""
LoRa Smart Irrigation - Telegram Bot Module
Sends formatted push alerts via Telegram Bot API.
"""

import os
import requests

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')


def send_alert(message, parse_mode='HTML'):
    """
    Send a Telegram alert message.
    Returns True on success, False on failure or if not configured.
    """
    if BOT_TOKEN == 'YOUR_BOT_TOKEN' or CHAT_ID == 'YOUR_CHAT_ID':
        print(f"[Telegram] Bot not configured. Would send:\n{message[:200]}...")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("[Telegram] Alert sent successfully")
            return True
        else:
            print(f"[Telegram] Failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


def format_sensor_alert(data, prediction, irrigation_active):
    """Format a rich sensor data alert for Telegram."""
    irr_label = "[WATER] ACTIVE - Valve OPEN" if irrigation_active else "[OK] IDLE - Valve CLOSED"

    msg = (
        f"<b>LoRa Smart Irrigation Update</b>\n"
        f"====================\n\n"
        f"<b>Sensor Readings:</b>\n"
        f"  Moisture: <b>{data['moisture']:.1f}%</b>\n"
        f"  Soil Temp: <b>{data['soil_temp']:.1f} C</b>\n"
        f"  Air Temp: <b>{data['air_temp']:.1f} C</b>\n"
        f"  Humidity: <b>{data['humidity']:.1f}%</b>\n"
        f"  Light: <b>{data['light']:.0f}</b>\n\n"
        f"<b>Soil Nutrients (Location + Fertilizer):</b>\n"
        f"  N: <b>{data['n']:.1f}</b> | "
        f"P: <b>{data['p']:.1f}</b> | "
        f"K: <b>{data['k']:.1f}</b>\n\n"
        f"<b>AI Prediction:</b> {prediction.get('crop', 'N/A')} "
        f"({prediction.get('confidence', 0):.1f}%)\n\n"
        f"<b>Irrigation:</b> {irr_label}"
    )
    return msg


def format_weather_alert(data, weather_info, skip_reason=None):
    """Format an alert with weather context (used for rain-skip events)."""
    if skip_reason:
        msg = (
            f"<b>Irrigation Skipped</b>\n"
            f"====================\n\n"
            f"Moisture: <b>{data['moisture']:.1f}%</b> (below threshold)\n"
            f"Reason: {skip_reason}\n\n"
            f"Forecast: {weather_info.get('description', 'N/A')}\n"
            f"Rain probability: {weather_info.get('rain_chance', 0):.0f}%\n\n"
            f"<i>Saving water - nature will handle it!</i>"
        )
        return msg

    # Fallback to standard alert
    return format_sensor_alert(
        data,
        {'crop': 'N/A', 'confidence': 0},
        data.get('irrigation_triggered', False)
    )
