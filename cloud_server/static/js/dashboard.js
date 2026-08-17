/**
 * LoRa Smart Irrigation — Dashboard JavaScript
 * AJAX data fetching, Chart.js charts, gauge updates, auto-refresh.
 */

// ─── Constants ──────────────────────────────────────────────────────

const REFRESH_INTERVAL = 30_000;  // 30 seconds
const GAUGE_CIRCUMFERENCE = 326.73;
const API = {
    latest:   '/api/latest',
    history:  '/api/history',
    alerts:   '/api/alerts',
    stats:    '/api/stats',
    weather:  '/api/weather',
    settings: '/api/settings',
    simulate: '/api/simulate',
};

// ─── State ──────────────────────────────────────────────────────────

let historyChart = null;
let currentTimeRange = 6;  // hours
let refreshTimer = null;

// ─── DOM Helpers ────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ─── Gauge Update ───────────────────────────────────────────────────

function setGauge(elementId, value, maxValue) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const pct = Math.min(value / maxValue, 1);
    const offset = GAUGE_CIRCUMFERENCE * (1 - pct);
    el.style.strokeDashoffset = offset;
}

function animateValue(elementId, targetValue, decimals = 1) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const current = parseFloat(el.textContent) || 0;
    const diff = targetValue - current;
    const steps = 30;
    let step = 0;

    function tick() {
        step++;
        const progress = step / steps;
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        const val = current + diff * eased;
        el.textContent = val.toFixed(decimals);
        if (step < steps) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
}

// ─── Data Fetching ──────────────────────────────────────────────────

async function fetchJSON(url) {
    try {
        const resp = await fetch(url);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (err) {
        console.error(`Fetch error: ${url}`, err);
        return null;
    }
}

// ─── Update Functions ───────────────────────────────────────────────

function updateSensorGauges(data) {
    if (!data) return;

    // Moisture (0-100%)
    animateValue('valMoisture', data.moisture, 1);
    setGauge('gaugeMoisture', data.moisture, 100);

    // Soil Temp (0-50°C)
    animateValue('valSoilTemp', data.soil_temp, 1);
    setGauge('gaugeSoilTemp', data.soil_temp, 50);

    // Air Temp (0-50°C)
    animateValue('valAirTemp', data.air_temp, 1);
    setGauge('gaugeAirTemp', data.air_temp, 50);

    // Humidity (0-100%)
    animateValue('valHumidity', data.humidity, 1);
    setGauge('gaugeHumidity', data.humidity, 100);

    // Light (0-1024)
    animateValue('valLight', data.light, 0);
    setGauge('gaugeLight', data.light, 1024);
}

function updateNPK(data) {
    if (!data) return;

    const nMax = 140, pMax = 145, kMax = 205;

    animateValue('valN', data.n_estimated, 1);
    animateValue('valP', data.p_estimated, 1);
    animateValue('valK', data.k_estimated, 1);

    $('#barN').style.width = `${Math.min((data.n_estimated / nMax) * 100, 100)}%`;
    $('#barP').style.width = `${Math.min((data.p_estimated / pMax) * 100, 100)}%`;
    $('#barK').style.width = `${Math.min((data.k_estimated / kMax) * 100, 100)}%`;
}

function updatePrediction(data) {
    if (!data || !data.predicted_crop) return;

    $('#predictedCrop').textContent = data.predicted_crop;
    $('#confidence').textContent = `${(data.confidence || 0).toFixed(1)}%`;
}

function updateIrrigation(data) {
    if (!data) return;

    const card = $('#irrigationCard');
    const state = $('#irrigationState');
    const detail = $('#irrigationDetail');
    const icon = $('.water-drop');

    card.classList.remove('active', 'rain-skip');

    if (data.irrigation_triggered) {
        card.classList.add('active');
        state.textContent = 'ACTIVE';
        detail.textContent = `Valve OPEN — Moisture at ${data.moisture?.toFixed(1) || '?'}%`;
        icon.textContent = '💧';
    } else {
        state.textContent = 'IDLE';
        detail.textContent = 'Valve closed — Soil moisture adequate';
        icon.textContent = '✅';
    }
}

function updateAlerts(alerts) {
    const container = $('#alertsList');
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<div class="empty-state">No alerts yet</div>';
        return;
    }

    container.innerHTML = alerts.slice(0, 30).map(a => {
        const time = formatTime(a.timestamp);
        const dotClass = a.alert_type || 'info';
        return `
            <div class="alert-item">
                <span class="alert-dot ${dotClass}"></span>
                <div class="alert-content">
                    <div class="alert-message">${escapeHtml(a.message)}</div>
                    <div class="alert-time">${time}</div>
                </div>
            </div>`;
    }).join('');
}

function updateStats(stats) {
    if (!stats) return;

    document.getElementById('statReadings').textContent =
        formatNumber(stats.total_readings || 0);
    document.getElementById('statIrrigations').textContent =
        formatNumber(stats.irrigation_count || 0);
    document.getElementById('statAlerts').textContent =
        formatNumber(stats.total_alerts || 0);
    document.getElementById('statAvgMoisture').textContent =
        stats.avg_moisture != null ? `${stats.avg_moisture.toFixed(1)}%` : '—';
}

function updateWeather(weatherData) {
    if (!weatherData) {
        $('#weatherCard').style.display = 'none';
        return;
    }

    // Current weather
    if (weatherData.current) {
        const c = weatherData.current;
        $('#weatherTemp').textContent = Math.round(c.temperature);
        $('#weatherDesc').textContent = c.description;
    }

    // Forecast items
    const forecastEl = $('#weatherForecast');
    if (weatherData.forecast && weatherData.forecast.forecasts) {
        forecastEl.innerHTML = weatherData.forecast.forecasts.map(fc => {
            const time = fc.time.split(' ')[1]?.slice(0, 5) || fc.time;
            const rainClass = fc.rain_chance >= 60 ? 'high' : fc.rain_chance >= 30 ? 'med' : 'low';
            return `
                <div class="forecast-item">
                    <span class="forecast-time">${time}</span>
                    <span class="forecast-desc">${fc.description}</span>
                    <span class="forecast-rain ${rainClass}">${fc.rain_chance.toFixed(0)}%</span>
                </div>`;
        }).join('');
    }

    // Rain skip banner
    const banner = $('#rainSkipBanner');
    if (weatherData.rain_skip && weatherData.rain_skip.should_skip) {
        banner.style.display = 'flex';
        $('#rainSkipText').textContent = weatherData.rain_skip.reason;
    } else {
        banner.style.display = 'none';
    }
}

function updateConnectionStatus(online) {
    const chip = $('#connectionStatus');
    const dot = chip.querySelector('.status-text');

    if (online) {
        chip.classList.remove('offline');
        dot.textContent = 'Connected';
    } else {
        chip.classList.add('offline');
        dot.textContent = 'Offline';
    }
}

function updateLastUpdateTime() {
    const now = new Date();
    const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    $('#lastUpdate').textContent = `Updated ${time}`;
}

// ─── Chart ──────────────────────────────────────────────────────────

function buildChart(readings) {
    const ctx = document.getElementById('historyChart');
    if (!ctx) return;

    const labels = readings.map(r => {
        const d = new Date(r.timestamp + 'Z');
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

    const datasets = [
        {
            label: 'Moisture (%)',
            data: readings.map(r => r.moisture),
            borderColor: '#00b4d8',
            backgroundColor: 'rgba(0, 180, 216, 0.08)',
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 10,
            borderWidth: 2,
        },
        {
            label: 'Soil Temp (°C)',
            data: readings.map(r => r.soil_temp),
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.05)',
            fill: false,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 10,
            borderWidth: 2,
        },
        {
            label: 'Humidity (%)',
            data: readings.map(r => r.humidity),
            borderColor: '#8b5cf6',
            backgroundColor: 'rgba(139, 92, 246, 0.05)',
            fill: false,
            tension: 0.4,
            pointRadius: 0,
            pointHitRadius: 10,
            borderWidth: 2,
        },
    ];

    if (historyChart) {
        historyChart.data.labels = labels;
        historyChart.data.datasets.forEach((ds, i) => {
            ds.data = datasets[i].data;
        });
        historyChart.update('none');
        return;
    }

    historyChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 },
                        boxWidth: 12,
                        boxHeight: 2,
                        useBorderRadius: true,
                        borderRadius: 1,
                        padding: 15,
                    },
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    borderColor: 'rgba(255, 255, 255, 0.08)',
                    borderWidth: 1,
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    titleFont: { family: 'Inter', weight: '600' },
                    bodyFont: { family: 'Inter' },
                    padding: 10,
                    cornerRadius: 10,
                    displayColors: true,
                    boxPadding: 4,
                },
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: {
                        color: '#475569',
                        font: { family: 'Inter', size: 10 },
                        maxTicksLimit: 10,
                    },
                    border: { display: false },
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: {
                        color: '#475569',
                        font: { family: 'Inter', size: 10 },
                    },
                    border: { display: false },
                },
            },
        },
    });
}

// ─── Master Refresh ─────────────────────────────────────────────────

async function refreshDashboard() {
    const [latest, history, alerts, stats, weather] = await Promise.all([
        fetchJSON(API.latest),
        fetchJSON(`${API.history}?hours=${currentTimeRange}`),
        fetchJSON(API.alerts),
        fetchJSON(API.stats),
        fetchJSON(API.weather).catch(() => null),  // May 400 if location not set
    ]);

    const online = latest !== null;
    updateConnectionStatus(online);
    updateLastUpdateTime();

    if (latest) {
        updateSensorGauges(latest);
        updateNPK(latest);
        updatePrediction(latest);
        updateIrrigation(latest);
    }

    if (history && history.readings) {
        buildChart(history.readings);
    }

    if (alerts && alerts.alerts) {
        updateAlerts(alerts.alerts);
    }

    if (stats) {
        updateStats(stats);
    }

    if (weather && !weather.error) {
        updateWeather(weather);
    }
}

// ─── Event Handlers ─────────────────────────────────────────────────

function setupEventListeners() {
    // Simulate button
    $('#btnSimulate').addEventListener('click', async () => {
        const btn = $('#btnSimulate');
        btn.style.opacity = '0.5';
        btn.style.pointerEvents = 'none';

        try {
            const resp = await fetch(API.simulate, { method: 'POST' });
            if (resp.ok) {
                await refreshDashboard();
            }
        } catch (err) {
            console.error('Simulate error:', err);
        }

        setTimeout(() => {
            btn.style.opacity = '1';
            btn.style.pointerEvents = 'auto';
        }, 500);
    });

    // Refresh button
    $('#btnRefresh').addEventListener('click', () => {
        refreshDashboard();
    });

    // Settings modal
    $('#btnSettings').addEventListener('click', async () => {
        const settings = await fetchJSON(API.settings);
        if (settings) {
            $('#inputCity').value = settings.city || '';
            $('#inputLat').value = settings.latitude || '';
            $('#inputLon').value = settings.longitude || '';
        }
        $('#settingsModal').classList.add('visible');
    });

    $('#btnCloseModal').addEventListener('click', () => {
        $('#settingsModal').classList.remove('visible');
    });

    $('#settingsModal').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) {
            e.currentTarget.classList.remove('visible');
        }
    });

    // Save settings
    $('#btnSaveSettings').addEventListener('click', async () => {
        const data = {
            city: $('#inputCity').value.trim(),
            latitude: $('#inputLat').value,
            longitude: $('#inputLon').value,
        };

        try {
            await fetch(API.settings, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            $('#settingsModal').classList.remove('visible');
            refreshDashboard();
        } catch (err) {
            console.error('Save settings error:', err);
        }
    });

    // Time range selector
    $$('.range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            $$('.range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTimeRange = parseInt(btn.dataset.hours, 10);
            // Refetch history for new range
            fetchJSON(`${API.history}?hours=${currentTimeRange}`).then(data => {
                if (data && data.readings) buildChart(data.readings);
            });
        });
    });
}

// ─── Utilities ──────────────────────────────────────────────────────

function formatTime(timestamp) {
    if (!timestamp) return '—';
    try {
        const d = new Date(timestamp.includes('Z') ? timestamp : timestamp + 'Z');
        const now = new Date();
        const diff = (now - d) / 1000;

        if (diff < 60)   return 'Just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch {
        return timestamp;
    }
}

function formatNumber(num) {
    if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
    return String(num);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ─── Init ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    refreshDashboard();

    // Auto-refresh every 30 seconds
    refreshTimer = setInterval(refreshDashboard, REFRESH_INTERVAL);
});
