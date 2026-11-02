"""
LoRa Smart Irrigation - Database Module
SQLite storage for sensor readings, alerts, and system settings.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'irrigation.db')


def get_connection():
    """Get a SQLite connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent read performance
    return conn


def init_db():
    """Initialize database tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        moisture REAL,
        soil_temp REAL,
        air_temp REAL,
        humidity REAL,
        light REAL,
        n_estimated REAL,
        p_estimated REAL,
        k_estimated REAL,
        predicted_crop TEXT,
        confidence REAL,
        irrigation_triggered INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        alert_type TEXT,
        message TEXT,
        details TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # Index for faster time-range queries
    c.execute('''CREATE INDEX IF NOT EXISTS idx_readings_timestamp
                 ON sensor_readings(timestamp)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_alerts_timestamp
                 ON alerts(timestamp)''')

    # --- Schema migrations (ADD COLUMN IF NOT EXISTS via try/except) ----------
    new_cols = [
        "ALTER TABLE sensor_readings ADD COLUMN top_crops_json TEXT",
        "ALTER TABLE sensor_readings ADD COLUMN soil_health_score REAL",
        "ALTER TABLE sensor_readings ADD COLUMN decision_source TEXT",
    ]
    for sql in new_cols:
        try:
            c.execute(sql)
        except Exception:
            pass  # column already exists

    # Seed default soil & fertilizer settings (INSERT OR IGNORE = won't overwrite)
    defaults = {
        'soil_type': 'alluvial',
        'fertilizer_type': 'none',
        'fertilizer_dose': 'none',
    }
    for key, value in defaults.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                  (key, value))

    conn.commit()
    conn.close()
    print("[OK] Database initialized")


# --- Sensor Readings ---------------------------------------------------------

def store_reading(data):
    """Store a sensor reading and return its ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''INSERT INTO sensor_readings
        (moisture, soil_temp, air_temp, humidity, light,
         n_estimated, p_estimated, k_estimated,
         predicted_crop, confidence, irrigation_triggered,
         top_crops_json, soil_health_score, decision_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['moisture'], data['soil_temp'], data['air_temp'],
         data['humidity'], data['light'],
         data['n'], data['p'], data['k'],
         data.get('predicted_crop'), data.get('confidence'),
         data.get('irrigation_triggered', 0),
         data.get('top_crops_json'), data.get('soil_health_score'),
         data.get('decision_source')))
    conn.commit()
    reading_id = c.lastrowid
    conn.close()
    return reading_id


def get_latest():
    """Get the most recent sensor reading."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_history(hours=24):
    """Get sensor readings from the last N hours."""
    conn = get_connection()
    c = conn.cursor()
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''SELECT * FROM sensor_readings
                 WHERE timestamp >= ?
                 ORDER BY timestamp ASC''', (since,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# --- Alerts ------------------------------------------------------------------

def store_alert(alert_type, message, details=''):
    """Store an alert event."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT INTO alerts (alert_type, message, details) VALUES (?, ?, ?)',
              (alert_type, message, details))
    conn.commit()
    conn.close()


def get_alerts(limit=50):
    """Get recent alerts, newest first."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# --- Statistics --------------------------------------------------------------

def get_stats():
    """Get summary statistics for the dashboard."""
    conn = get_connection()
    c = conn.cursor()

    c.execute('SELECT COUNT(*) as total_readings FROM sensor_readings')
    total = c.fetchone()['total_readings']

    c.execute('SELECT COUNT(*) as count FROM sensor_readings WHERE irrigation_triggered = 1')
    irrigations = c.fetchone()['count']

    c.execute('''SELECT MIN(timestamp) as first_reading,
                        MAX(timestamp) as last_reading
                 FROM sensor_readings''')
    time_range = dict(c.fetchone())

    c.execute('''SELECT
        AVG(moisture)   as avg_moisture,
        AVG(soil_temp)  as avg_soil_temp,
        AVG(humidity)   as avg_humidity,
        MIN(moisture)   as min_moisture,
        MAX(moisture)   as max_moisture
        FROM sensor_readings
        WHERE timestamp >= datetime('now', '-24 hours')''')
    averages = dict(c.fetchone())

    c.execute('SELECT COUNT(*) as count FROM alerts')
    total_alerts = c.fetchone()['count']

    conn.close()

    return {
        'total_readings': total,
        'irrigation_count': irrigations,
        'total_alerts': total_alerts,
        'first_reading': time_range.get('first_reading'),
        'last_reading': time_range.get('last_reading'),
        **{k: v for k, v in averages.items() if v is not None}
    }


# --- Settings ----------------------------------------------------------------

def get_setting(key, default=None):
    """Get a setting value by key."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key, value):
    """Set or update a setting value."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
              (key, str(value)))
    conn.commit()
    conn.close()


# --- Advisory Layer Queries --------------------------------------------------

def get_recent_moisture_readings(n=10):
    """Return the last N moisture values and timestamps for trend computation."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''SELECT moisture, timestamp FROM sensor_readings
                 ORDER BY id DESC LIMIT ?''', (n,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    # Reverse so oldest is first (chronological order)
    rows.reverse()
    return rows


def get_soil_health_inputs(days=30):
    """
    Aggregate data needed for soil health score computation.

    Returns a dict with:
        moisture_values, n_values, p_values, k_values,
        irrigation_count, total_readings
    """
    conn = get_connection()
    c = conn.cursor()
    since = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    c.execute('''SELECT moisture, n_estimated, p_estimated, k_estimated,
                        irrigation_triggered
                 FROM sensor_readings
                 WHERE timestamp >= ?''', (since,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {
            'moisture_values': [], 'n_values': [], 'p_values': [], 'k_values': [],
            'irrigation_count': 0, 'total_readings': 0,
        }

    moisture_vals = [r['moisture'] for r in rows if r['moisture'] is not None]
    n_vals = [r['n_estimated'] for r in rows if r['n_estimated'] is not None]
    p_vals = [r['p_estimated'] for r in rows if r['p_estimated'] is not None]
    k_vals = [r['k_estimated'] for r in rows if r['k_estimated'] is not None]
    irr_count = sum(1 for r in rows if r['irrigation_triggered'] == 1)

    return {
        'moisture_values':  moisture_vals,
        'n_values':         n_vals,
        'p_values':         p_vals,
        'k_values':         k_vals,
        'irrigation_count': irr_count,
        'total_readings':   len(rows),
    }


def get_irrigation_event_count(hours=24):
    """Return number of irrigation events (irrigation_triggered=1) in the last N hours."""
    conn = get_connection()
    c = conn.cursor()
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''SELECT COUNT(*) as cnt FROM sensor_readings
                 WHERE irrigation_triggered = 1 AND timestamp >= ?''', (since,))
    row = c.fetchone()
    conn.close()
    return row['cnt'] if row else 0
