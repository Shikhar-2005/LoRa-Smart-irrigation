"""
LoRa Smart Irrigation - Soil & Fertilizer Service

Location-aware soil nutrient estimation engine.
Replaces the previous pseudo-empirical edge formulas with a two-tier model:

  Effective NPK = Regional Baseline (from location/soil type)
                + Fertilizer Delta  (from farmer's amendment inputs)

Baseline values are calibrated to the Kaggle Crop Recommendation dataset
scale (N: 0-140, P: 5-145, K: 5-205) using ICAR / Soil Health Card
averages for major Indian soil classifications.
"""

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
