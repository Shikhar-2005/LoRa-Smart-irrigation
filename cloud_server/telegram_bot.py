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
    """Format a rich sensor data alert for Telegram, including top-3 crops and NPK status."""
    irr_label = "[WATER] ACTIVE - Valve OPEN" if irrigation_active else "[OK] IDLE - Valve CLOSED"

    # Build NPK status line for top crop
    top_crop = prediction.get('crop', 'N/A')
    top_conf = prediction.get('confidence', 0)

    # Top-3 runner-up list
    top3 = prediction.get('top_3', [])
    runners_lines = ''
    for i, (crop, prob) in enumerate(top3[:3], 1):
        runners_lines += f"  {i}. {crop.title()} ({prob:.1f}%)\n"

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
        f"<b>Top Crop Recommendations:</b>\n"
        f"{runners_lines}\n"
        f"<b>Irrigation:</b> {irr_label}"
    )
    return msg


def format_disease_risk_alert(risks, crop, sensor_data):
    """Format a disease / stress risk alert for Telegram."""
    if not risks:
        return None
    lines = [f"<b>Disease / Stress Risk Alert</b>", "====================", ""]
    lines.append(f"Crop: <b>{crop.title()}</b>")
    lines.append(f"Soil Temp: {sensor_data.get('soil_temp', '?'):.1f} C  "
                 f"Humidity: {sensor_data.get('humidity', '?'):.1f}%  "
                 f"Moisture: {sensor_data.get('moisture', '?'):.1f}%")
    lines.append("")
    for r in risks:
        sev = r['severity']
        lines.append(f"[{sev}] <b>{r['name']}</b>")
        lines.append(f"  {r['recommendation'][:200]}")
        lines.append("")
    return '\n'.join(lines)


def format_morning_digest(data, prediction, soil_health, moisture_trend, disease_risks):
    """Format a daily morning digest summary for Telegram."""
    top_crop = prediction.get('crop', 'N/A') if prediction else 'N/A'
    top_conf = prediction.get('confidence', 0) if prediction else 0

    moisture = data.get('moisture', 0) if data else 0
    trend = moisture_trend.get('trend_label', 'Stable') if moisture_trend else 'Stable'
    hours_until = moisture_trend.get('hours_until_threshold') if moisture_trend else None

    score = soil_health.get('score', 0) if soil_health else 0
    health_label = soil_health.get('label', 'Unknown') if soil_health else 'Unknown'

    risk_summary = ''
    if disease_risks:
        risk_summary = f"\n<b>Risks:</b> {len(disease_risks)} active alerts\n"

    threshold_note = ''
    if hours_until is not None:
        threshold_note = f"  Irrigation needed in approx {hours_until:.1f} hours\n"

    msg = (
        f"<b>Good Morning - Daily Farm Digest</b>\n"
        f"====================\n\n"
        f"<b>Current Readings:</b>\n"
        f"  Moisture: <b>{moisture:.1f}%</b> ({trend})\n"
        f"{threshold_note}"
        f"  N: {data.get('n', 0):.1f} | "
        f"P: {data.get('p', 0):.1f} | "
        f"K: {data.get('k', 0):.1f}\n\n"
        f"<b>Best Crop Today:</b> {top_crop.title()} ({top_conf:.1f}%)\n\n"
        f"<b>Soil Health Score:</b> {score}/100 ({health_label})\n"
        f"{risk_summary}\n"
        f"<i>Have a great farming day!</i>"
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
