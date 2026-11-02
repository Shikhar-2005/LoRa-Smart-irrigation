"""
LoRa Smart Irrigation - Soil & Fertilizer Service

Location-aware soil nutrient estimation engine.
Replaces the previous pseudo-empirical edge formulas with a two-tier model:

  Effective NPK = Regional Baseline (from location/soil type)
                + Fertilizer Delta  (from farmer's amendment inputs)

Baseline values are calibrated to the Kaggle Crop Recommendation dataset
scale (N: 0-140, P: 5-145, K: 5-205) using ICAR / Soil Health Card
averages for major Indian soil classifications.

Also provides the agronomic advisory layer:
  - Crop NPK requirement lookup + deficit analysis
  - Fertilizer prescription engine (synthetic + organic alternatives)
  - Soil health score computation
  - Sowing calendar (ICAR-based, month-indexed)
  - Disease and pest risk rules
"""

import math
from datetime import datetime

# --- Regional Soil Baselines (ICAR / Soil Health Card benchmarks) -----------
#
# These represent unadulterated (virgin / unfertilized) average nutrient
# levels for each major Indian soil classification, scaled to match the
# Kaggle Crop Recommendation dataset feature ranges.

SOIL_BASELINES = {
    'alluvial': {
        'name': 'Alluvial Soil (Indo-Gangetic Plains)',
        'n': 75.0,  'p': 45.0,  'k': 45.0,
        'ph': 7.0,
        'description': 'Rich loamy soil found in river plains of North India. '
                       'Naturally high in nitrogen and phosphorus.',
    },
    'black_cotton': {
        'name': 'Black Cotton Soil (Deccan / Regur)',
        'n': 35.0,  'p': 25.0,  'k': 75.0,
        'ph': 7.8,
        'description': 'Clay-rich volcanic soil found in Central & Western India. '
                       'Very high potassium, low nitrogen.',
    },
    'red_laterite': {
        'name': 'Red / Laterite Soil (South & East)',
        'n': 30.0,  'p': 20.0,  'k': 30.0,
        'ph': 6.0,
        'description': 'Iron-rich acidic soil common in South India, Karnataka, '
                       'Tamil Nadu, and parts of Odisha & West Bengal.',
    },
    'arid_desert': {
        'name': 'Arid / Desert Soil (Thar / Northwest)',
        'n': 18.0,  'p': 15.0,  'k': 35.0,
        'ph': 8.2,
        'description': 'Sandy alkaline soil with very low organic content. '
                       'Common in Rajasthan and parts of Gujarat.',
    },
    'mountain_forest': {
        'name': 'Mountain / Forest Soil (Hilly / Northeast)',
        'n': 60.0,  'p': 30.0,  'k': 50.0,
        'ph': 5.8,
        'description': 'Humus-rich acidic soil found in Himalayan foothills, '
                       'Western Ghats, and the Northeast.',
    },
}


# --- Fertilizer Nutrient Grades (N%-P%-K%) ----------------------------------
#
# Standard Indian-market fertilizer compositions.
# Values represent the percentage of each nutrient per kg of product.

FERTILIZER_DATABASE = {
    'none': {
        'name': 'None (Virgin / Unfertilized)',
        'n_pct': 0,  'p_pct': 0,  'k_pct': 0,
    },
    'urea': {
        'name': 'Urea (46-0-0)',
        'n_pct': 46,  'p_pct': 0,  'k_pct': 0,
    },
    'dap': {
        'name': 'DAP (18-46-0)',
        'n_pct': 18,  'p_pct': 46,  'k_pct': 0,
    },
    'mop': {
        'name': 'Muriate of Potash (0-0-60)',
        'n_pct': 0,  'p_pct': 0,  'k_pct': 60,
    },
    'npk_10_26_26': {
        'name': 'NPK Complex (10-26-26)',
        'n_pct': 10,  'p_pct': 26,  'k_pct': 26,
    },
    'npk_12_32_16': {
        'name': 'NPK Complex (12-32-16)',
        'n_pct': 12,  'p_pct': 32,  'k_pct': 16,
    },
    'npk_20_20_0': {
        'name': 'NPK Complex (20-20-0)',
        'n_pct': 20,  'p_pct': 20,  'k_pct': 0,
    },
    'ssp': {
        'name': 'Single Super Phosphate (0-16-0)',
        'n_pct': 0,  'p_pct': 16,  'k_pct': 0,
    },
    'compost': {
        'name': 'Farmyard Manure / Compost',
        'n_pct': 5,  'p_pct': 3,  'k_pct': 5,
    },
}


# --- Dosage Multipliers (per-acre application scale) -------------------------
#
# These translate farmer-friendly dose labels into a delta contribution.
# The scaling factor converts fertilizer grade % into Kaggle-scale nutrient
# units: delta_N = (n_pct / 100) * dose_kg * SCALE_FACTOR
# SCALE_FACTOR is calibrated so that a standard (50 kg/acre) DAP application
# produces deltas that shift baseline values into the correct Kaggle ranges.

DOSAGE_LEVELS = {
    'none':     {'name': 'None',                          'kg_per_acre': 0},
    'low':      {'name': 'Low (~25 kg/acre — half bag)',  'kg_per_acre': 25},
    'standard': {'name': 'Standard (~50 kg/acre — 1 bag)','kg_per_acre': 50},
    'high':     {'name': 'High (~100 kg/acre — 2 bags)',  'kg_per_acre': 100},
}

# Scaling factor: converts (grade% × kg) into Kaggle-scale nutrient units.
# Calibrated empirically so that typical Indian fertilizer applications
# produce NPK values within the Kaggle dataset distribution.
_SCALE_FACTOR = 0.025


# --- Region → Default Soil Type Mapping -------------------------------------

REGION_TO_SOIL = {
    'north_india':   'alluvial',
    'east_india':    'alluvial',
    'south_india':   'red_laterite',
    'west_india':    'black_cotton',
    'central_india': 'black_cotton',
    'tropical':      'red_laterite',
    'subtropical':   'alluvial',
    'temperate':     'mountain_forest',
    'arid':          'arid_desert',
    'any':           'alluvial',       # sensible default
}


# --- Public API --------------------------------------------------------------

def get_available_soil_types():
    """Return soil types for populating frontend dropdown.
    Returns list of {key, name, description} dicts."""
    return [
        {'key': key, 'name': info['name'], 'description': info['description']}
        for key, info in SOIL_BASELINES.items()
    ]


def get_available_fertilizers():
    """Return fertilizers for populating frontend dropdown.
    Returns list of {key, name} dicts."""
    return [
        {'key': key, 'name': info['name']}
        for key, info in FERTILIZER_DATABASE.items()
    ]


def get_available_dosages():
    """Return dosage levels for populating frontend dropdown.
    Returns list of {key, name} dicts."""
    return [
        {'key': key, 'name': info['name']}
        for key, info in DOSAGE_LEVELS.items()
    ]


def get_default_soil_for_region(region):
    """Map a region key (from region_crops.py) to the most likely soil type."""
    return REGION_TO_SOIL.get(region, 'alluvial')


def calculate_estimated_npk(soil_type='alluvial', fertilizer_type='none',
                             dosage='none'):
    """
    Calculate estimated soil NPK using the two-tier model:
      Effective NPK = Regional Baseline + Fertilizer Delta

    Args:
        soil_type:       Key from SOIL_BASELINES (e.g. 'alluvial', 'black_cotton')
        fertilizer_type: Key from FERTILIZER_DATABASE (e.g. 'urea', 'dap')
        dosage:          Key from DOSAGE_LEVELS (e.g. 'none', 'standard', 'high')

    Returns:
        dict with keys: n, p, k, ph, soil_name, fertilizer_name, dosage_name,
                        baseline_n/p/k, delta_n/p/k
    """
    # Look up baseline
    soil = SOIL_BASELINES.get(soil_type, SOIL_BASELINES['alluvial'])
    base_n, base_p, base_k = soil['n'], soil['p'], soil['k']
    ph = soil['ph']

    # Look up fertilizer
    fert = FERTILIZER_DATABASE.get(fertilizer_type, FERTILIZER_DATABASE['none'])
    dose = DOSAGE_LEVELS.get(dosage, DOSAGE_LEVELS['none'])
    kg = dose['kg_per_acre']

    # Calculate deltas
    delta_n = round(fert['n_pct'] * kg * _SCALE_FACTOR, 1)
    delta_p = round(fert['p_pct'] * kg * _SCALE_FACTOR, 1)
    delta_k = round(fert['k_pct'] * kg * _SCALE_FACTOR, 1)

    # Effective values (clamped to Kaggle dataset range)
    eff_n = round(min(max(base_n + delta_n, 0), 140), 1)
    eff_p = round(min(max(base_p + delta_p, 0), 145), 1)
    eff_k = round(min(max(base_k + delta_k, 0), 205), 1)

    return {
        'n': eff_n,
        'p': eff_p,
        'k': eff_k,
        'ph': ph,
        'soil_name': soil['name'],
        'fertilizer_name': fert['name'],
        'dosage_name': dose['name'],
        'baseline': {'n': base_n, 'p': base_p, 'k': base_k},
        'delta':    {'n': delta_n, 'p': delta_p, 'k': delta_k},
    }


# =============================================================================
# AGRONOMIC ADVISORY LAYER
# =============================================================================

# --- Crop NPK Requirements (optimal ranges from ICAR / Kaggle dataset) -------
#
# Each entry is (min, max) in Kaggle-scale units (same scale as SOIL_BASELINES).
# Crops from the 22-class Kaggle Crop Recommendation dataset.

CROP_NPK_REQUIREMENTS = {
    'rice':        {'n': (60, 100), 'p': (30,  60), 'k': (30,  60)},
    'maize':       {'n': (60, 100), 'p': (30,  60), 'k': (15,  30)},
    'chickpea':    {'n': (30,  50), 'p': (50,  80), 'k': (70, 100)},
    'kidneybeans': {'n': (15,  25), 'p': (50,  80), 'k': (15,  30)},
    'pigeonpeas':  {'n': (15,  25), 'p': (40,  70), 'k': (15,  30)},
    'mothbeans':   {'n': (15,  25), 'p': (40,  60), 'k': (15,  30)},
    'mungbean':    {'n': (15,  25), 'p': (30,  50), 'k': (15,  30)},
    'blackgram':   {'n': (15,  25), 'p': (40,  60), 'k': (15,  30)},
    'lentil':      {'n': (15,  25), 'p': (40,  70), 'k': (15,  30)},
    'pomegranate': {'n': (20,  40), 'p': (10,  25), 'k': (40,  60)},
    'banana':      {'n': (90, 130), 'p': (25,  50), 'k': (40,  80)},
    'mango':       {'n': (15,  30), 'p': (10,  20), 'k': (40,  60)},
    'grapes':      {'n': (20,  40), 'p': (10,  25), 'k': (30,  50)},
    'watermelon':  {'n': (80, 120), 'p': (40,  80), 'k': (40,  80)},
    'muskmelon':   {'n': (80, 120), 'p': (40,  80), 'k': (40,  80)},
    'apple':       {'n': (15,  30), 'p': (10,  25), 'k': (40,  60)},
    'orange':      {'n': (15,  30), 'p': (10,  20), 'k': (40,  60)},
    'papaya':      {'n': (40,  70), 'p': (30,  60), 'k': (40,  80)},
    'coconut':     {'n': (15,  30), 'p': (10,  20), 'k': (40,  80)},
    'cotton':      {'n': (100, 135), 'p': (30,  55), 'k': (15,  30)},
    'jute':        {'n': (60, 100), 'p': (30,  60), 'k': (30,  60)},
    'coffee':      {'n': (90, 130), 'p': (15,  30), 'k': (25,  45)},
    'wheat':       {'n': (80, 120), 'p': (40,  70), 'k': (40,  70)},
}

# --- Fertilizer Prescription Lookup ------------------------------------------
#
# Maps the nutrient with a deficit to the cheapest Indian-market fix.
# 'product'     : human-readable product name
# 'dose_kg_acre': recommended application per acre for a moderate deficit
# 'long_term'   : soil health note for repeated use
# 'organic'     : organic / slow-release alternative with its dose

NUTRIENT_PRESCRIPTIONS = {
    'n': {
        'product':      'Urea (46-0-0)',
        'dose_kg_acre': 20,
        'long_term':    (
            'Repeated urea-only application acidifies soil over 3-5 seasons. '
            'Rotate with compost or FYM every 3rd season to maintain pH.'
        ),
        'organic':      'Vermicompost 400 kg/acre (slow N release, improves structure)',
    },
    'p': {
        'product':      'DAP (18-46-0)',
        'dose_kg_acre': 25,
        'long_term':    (
            'DAP is soil-safe at <= 50 kg/acre. Excess P causes P-fixation in '
            'clay soils and can lock out Zn and Fe micronutrients.'
        ),
        'organic':      'Bone meal 30 kg/acre (slow P release, improves root health)',
    },
    'k': {
        'product':      'MOP / Muriate of Potash (0-0-60)',
        'dose_kg_acre': 15,
        'long_term':    (
            'MOP raises soil Cl over time in heavy soils. Prefer SOP on '
            'Cl-sensitive crops (potato, grapes). Optimal at <= 50 kg/acre.'
        ),
        'organic':      'Wood ash 100 kg/acre (K + Ca, improves pH slightly)',
    },
}

# --- Sowing Calendar (ICAR-based, months as 1-12) ----------------------------
#
# Lists the optimal sowing months for each crop in the Indian agricultural
# calendar. Multiple windows are listed where applicable (Kharif + Rabi).

SOWING_CALENDAR = {
    'rice':        [6, 7, 8],
    'wheat':       [10, 11, 12],
    'maize':       [6, 7, 8, 2, 3],
    'chickpea':    [10, 11],
    'kidneybeans': [6, 7],
    'pigeonpeas':  [6, 7],
    'mothbeans':   [6, 7, 8],
    'mungbean':    [6, 7, 2, 3],
    'blackgram':   [6, 7, 10],
    'lentil':      [10, 11],
    'pomegranate': [2, 3, 7, 8],
    'banana':      [6, 7, 2, 3],
    'mango':       [7, 8],
    'grapes':      [1, 2, 7],
    'watermelon':  [2, 3, 6, 7],
    'muskmelon':   [2, 3, 6, 7],
    'apple':       [1, 2],
    'orange':      [6, 7],
    'papaya':      [6, 7, 2, 3],
    'coconut':     [5, 6, 7],
    'cotton':      [4, 5, 6],
    'jute':        [3, 4, 5],
    'coffee':      [5, 6],
    'wheat':       [10, 11, 12],
}

# Month name lookup for display
_MONTH_NAMES = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
}

# --- Disease / Pest Risk Rules ------------------------------------------------
#
# Rule-based checks against current sensor readings.
# Conditions checked server-side; no hardware changes required.

DISEASE_RISK_RULES = [
    {
        'name': 'Fungal Blast (Rice / Maize)',
        'crops': ['rice', 'maize', 'jute'],
        'condition': lambda h, t, m: h > 80 and t > 25,
        'severity': 'HIGH',
        'recommendation': (
            'High humidity + warm temperature is prime blast condition. '
            'Ensure good field drainage. Consider propiconazole-based '
            'foliar spray if symptoms appear. Avoid waterlogging.'
        ),
    },
    {
        'name': 'Downy Mildew (Wheat / Maize / Grapes)',
        'crops': ['wheat', 'maize', 'grapes', 'muskmelon', 'watermelon'],
        'condition': lambda h, t, m: h > 75 and 18 <= t <= 28,
        'severity': 'MEDIUM',
        'recommendation': (
            'Cool-humid conditions favour downy mildew. Improve air circulation. '
            'Apply mancozeb or copper oxychloride as a preventive spray. '
            'Avoid overhead irrigation in the evening.'
        ),
    },
    {
        'name': 'Root Heat Stress',
        'crops': None,   # applies to all crops
        'condition': lambda h, t, m: t > 35 and m < 25,
        'severity': 'HIGH',
        'recommendation': (
            'Soil is hot and dry. Root damage risk is critical. '
            'Irrigate immediately to bring moisture above 40%. '
            'Apply mulch (straw / dry leaves) to reduce soil temperature.'
        ),
    },
    {
        'name': 'Waterlogging / Root Rot Risk',
        'crops': None,
        'condition': lambda h, t, m: m > 85,
        'severity': 'MEDIUM',
        'recommendation': (
            'Moisture is critically high. Risk of anaerobic root rot. '
            'Check field drainage. Do not irrigate until moisture drops below 70%. '
            'Consider raised-bed planting for next season.'
        ),
    },
]


# =============================================================================
# AGRONOMIC ADVISORY FUNCTIONS
# =============================================================================

def get_crop_npk_prescription(crop_name, current_n, current_p, current_k):
    """
    Compare current NPK values to crop requirements and generate a fertilizer
    prescription for any nutrient that is below the crop's minimum requirement.

    Args:
        crop_name : str  - lowercase crop name (e.g. 'rice')
        current_n : float
        current_p : float
        current_k : float

    Returns:
        list of dicts, one per deficient nutrient:
            {
                'nutrient': 'N' | 'P' | 'K',
                'status':   'ok' | 'low' | 'high',
                'current':  float,
                'optimal_min': float,
                'optimal_max': float,
                'deficit':  float (0 if ok),
                'product':  str,
                'dose_kg_acre': float (0 if no action),
                'long_term': str,
                'organic': str,
            }
    """
    req = CROP_NPK_REQUIREMENTS.get(crop_name.lower())
    if not req:
        return []

    results = []
    checks = [
        ('N', current_n, req['n']),
        ('P', current_p, req['p']),
        ('K', current_k, req['k']),
    ]
    for label, current, (opt_min, opt_max) in checks:
        key = label.lower()
        presc = NUTRIENT_PRESCRIPTIONS[key]

        if current < opt_min:
            deficit = round(opt_min - current, 1)
            # Scale dose proportionally to deficit (mild / moderate / severe)
            scale = min(deficit / max(opt_min, 1), 1.0)
            dose = round(presc['dose_kg_acre'] * (0.5 + 0.5 * scale), 1)
            results.append({
                'nutrient':    label,
                'status':      'low',
                'current':     round(current, 1),
                'optimal_min': opt_min,
                'optimal_max': opt_max,
                'deficit':     deficit,
                'product':     presc['product'],
                'dose_kg_acre': dose,
                'long_term':   presc['long_term'],
                'organic':     presc['organic'],
            })
        elif current > opt_max:
            excess = round(current - opt_max, 1)
            results.append({
                'nutrient':    label,
                'status':      'high',
                'current':     round(current, 1),
                'optimal_min': opt_min,
                'optimal_max': opt_max,
                'deficit':     0,
                'excess':      excess,
                'product':     None,
                'dose_kg_acre': 0,
                'long_term':   (
                    'Nutrient level is above optimal. Avoid adding more of this '
                    'nutrient this season. Excess may lock out other micronutrients.'
                ),
                'organic':     None,
            })
        else:
            results.append({
                'nutrient':    label,
                'status':      'ok',
                'current':     round(current, 1),
                'optimal_min': opt_min,
                'optimal_max': opt_max,
                'deficit':     0,
                'product':     None,
                'dose_kg_acre': 0,
                'long_term':   None,
                'organic':     None,
            })
    return results


def get_top3_with_prescriptions(top3_list, current_n, current_p, current_k):
    """
    Enrich the top-3 (crop, probability) list with NPK status + prescription.

    Args:
        top3_list  : list of (crop_name: str, probability: float) tuples
        current_n/p/k : float

    Returns:
        list of dicts:
            {
                'crop': str,
                'probability': float,
                'match_pct': float,
                'npk_prescription': list (from get_crop_npk_prescription),
                'sowing_window': dict (from get_sowing_window),
            }
    """
    current_month = datetime.now().month
    enriched = []
    for crop, prob in top3_list:
        enriched.append({
            'crop':             crop,
            'probability':      round(prob, 4),
            'match_pct':        round(prob * 100, 1),
            'npk_prescription': get_crop_npk_prescription(
                crop, current_n, current_p, current_k),
            'sowing_window':    get_sowing_window(crop, current_month),
        })
    return enriched


def get_sowing_window(crop_name, current_month=None):
    """
    Return whether the crop is currently in its optimal sowing window.

    Args:
        crop_name     : str (lowercase)
        current_month : int 1-12 (defaults to server's current month)

    Returns:
        {
            'in_window':    bool,
            'window_desc':  str  (e.g. "Jun - Aug")
            'months':       list[int],
            'months_until': int  (0 if in window, else months until next window)
        }
    """
    if current_month is None:
        current_month = datetime.now().month

    months = SOWING_CALENDAR.get(crop_name.lower(), [])
    if not months:
        return {
            'in_window':    False,
            'window_desc':  'No calendar data',
            'months':       [],
            'months_until': -1,
        }

    in_window = current_month in months

    # Build a human-readable window description (compress consecutive months)
    sorted_months = sorted(set(months))
    window_desc = ', '.join(_MONTH_NAMES[m] for m in sorted_months)

    # Months until next window
    if in_window:
        months_until = 0
    else:
        months_until = None
        for offset in range(1, 13):
            future = ((current_month - 1 + offset) % 12) + 1
            if future in months:
                months_until = offset
                break
        if months_until is None:
            months_until = -1

    return {
        'in_window':    in_window,
        'window_desc':  window_desc,
        'months':       sorted_months,
        'months_until': months_until,
    }


def check_disease_risk(air_temp, humidity, moisture, crop_name=''):
    """
    Evaluate rule-based disease / stress risks from current sensor readings.

    Args:
        air_temp  : float (degrees C)
        humidity  : float (%)
        moisture  : float (%)
        crop_name : str   (lowercase, used to filter crop-specific rules)

    Returns:
        list of dicts:
            {'name': str, 'severity': 'HIGH'|'MEDIUM', 'recommendation': str}
    """
    risks = []
    crop_lower = (crop_name or '').lower()

    for rule in DISEASE_RISK_RULES:
        # Check crop filter (None = applies to all)
        if rule['crops'] is not None and crop_lower not in rule['crops']:
            continue
        try:
            if rule['condition'](humidity, air_temp, moisture):
                risks.append({
                    'name':           rule['name'],
                    'severity':       rule['severity'],
                    'recommendation': rule['recommendation'],
                })
        except Exception:
            pass

    return risks


def compute_soil_health_score(inputs):
    """
    Compute a 0-100 soil health score from recent readings.

    Args:
        inputs : dict with keys:
            'moisture_values'   : list[float] (recent moisture readings)
            'n_values'          : list[float]
            'p_values'          : list[float]
            'k_values'          : list[float]
            'irrigation_count'  : int (irrigations in last 30 days)
            'total_readings'    : int

    Returns:
        {
            'score':      int (0-100),
            'breakdown':  {
                'moisture_stability': int (0-40),
                'npk_balance':        int (0-40),
                'irrigation_freq':    int (0-20),
            },
            'label':      str  e.g. "Good", "Fair", "Poor"
        }
    """
    if not inputs or not inputs.get('total_readings', 0):
        return {'score': 0, 'breakdown': {}, 'label': 'No data'}

    # --- Component 1: Moisture stability (0-40 pts) ---
    moisture_vals = inputs.get('moisture_values', [])
    if len(moisture_vals) >= 2:
        stddev = _stddev(moisture_vals)
        # Low stddev = stable = good. Score drops as variability increases.
        # stddev of 0 -> 40 pts; stddev of 20+ -> 0 pts
        moisture_score = max(0, int(40 - (stddev / 20.0) * 40))
    else:
        moisture_score = 20   # partial credit with insufficient data

    # --- Component 2: NPK balance (0-40 pts) ---
    # Check if median NPK values fall within at least one valid crop range
    n_med = _median(inputs.get('n_values', [75.0]))
    p_med = _median(inputs.get('p_values', [45.0]))
    k_med = _median(inputs.get('k_values', [45.0]))

    npk_pts = 0
    # Use alluvial baseline as reference "ideal" for scoring
    n_ok = 40 <= n_med <= 120
    p_ok = 20 <= p_med <= 100
    k_ok = 20 <= k_med <= 120
    npk_pts = sum([n_ok, p_ok, k_ok]) * (40 // 3)

    # --- Component 3: Irrigation frequency (0-20 pts) ---
    total = max(inputs.get('total_readings', 1), 1)
    irr_count = inputs.get('irrigation_count', 0)
    irr_rate = irr_count / total  # fraction of readings that triggered irrigation
    # Ideal: ~10-30% irrigation rate. Very high or very low rate is sub-optimal.
    if 0.05 <= irr_rate <= 0.35:
        irr_score = 20
    elif irr_rate < 0.05 or irr_rate > 0.6:
        irr_score = 5
    else:
        irr_score = 12

    score = min(100, moisture_score + npk_pts + irr_score)

    if score >= 75:
        label = 'Good'
    elif score >= 50:
        label = 'Fair'
    else:
        label = 'Poor'

    return {
        'score': score,
        'breakdown': {
            'moisture_stability': moisture_score,
            'npk_balance':        npk_pts,
            'irrigation_freq':    irr_score,
        },
        'label': label,
    }


# --- Private math helpers ----------------------------------------------------

def _stddev(values):
    """Population standard deviation of a list of floats."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def _median(values):
    """Median of a list of floats."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    mid = len(sorted_v) // 2
    if len(sorted_v) % 2 == 0:
        return (sorted_v[mid - 1] + sorted_v[mid]) / 2.0
    return float(sorted_v[mid])
