"""
LoRa Smart Irrigation - Region Crop Filtering
Maps geographic regions to viable crops so the ML model only suggests
crops that can actually grow in the user's area.
"""

# --- All 22 Kaggle crops -----------------------------------------------------

ALL_CROPS = [
    'rice', 'maize', 'chickpea', 'kidneybeans', 'pigeonpeas',
    'mothbeans', 'mungbean', 'blackgram', 'lentil', 'pomegranate',
    'banana', 'mango', 'grapes', 'watermelon', 'muskmelon',
    'apple', 'orange', 'papaya', 'coconut', 'cotton', 'jute', 'coffee',
]

# --- Region -> Viable crops --------------------------------------------------

REGION_CROPS = {
    # India - zone-based
    'south_india': [
        'rice', 'coconut', 'banana', 'mango', 'papaya', 'coffee',
        'cotton', 'jute', 'pigeonpeas', 'blackgram', 'mungbean',
        'mothbeans', 'orange', 'watermelon', 'muskmelon', 'maize',
    ],
    'north_india': [
        'rice', 'maize', 'chickpea', 'lentil', 'kidneybeans',
        'mungbean', 'cotton', 'apple', 'grapes', 'watermelon',
        'muskmelon', 'orange', 'pomegranate', 'banana', 'papaya',
    ],
    'west_india': [
        'cotton', 'mango', 'banana', 'pomegranate', 'grapes',
        'watermelon', 'muskmelon', 'mothbeans', 'pigeonpeas',
        'chickpea', 'maize', 'coconut', 'papaya', 'orange', 'jute',
    ],
    'east_india': [
        'rice', 'jute', 'maize', 'banana', 'mango', 'papaya',
        'coconut', 'lentil', 'blackgram', 'mungbean', 'pigeonpeas',
        'watermelon', 'muskmelon', 'orange', 'coffee',
    ],
    'central_india': [
        'cotton', 'maize', 'chickpea', 'lentil', 'pigeonpeas',
        'blackgram', 'mungbean', 'mothbeans', 'orange', 'banana',
        'mango', 'watermelon', 'muskmelon', 'pomegranate',
    ],

    # Climate-based (generic)
    'tropical': [
        'rice', 'banana', 'coconut', 'mango', 'papaya', 'coffee',
        'jute', 'pigeonpeas', 'blackgram', 'mungbean', 'mothbeans',
        'watermelon', 'muskmelon', 'orange', 'cotton', 'maize',
    ],
    'subtropical': [
        'rice', 'maize', 'cotton', 'banana', 'mango', 'orange',
        'pomegranate', 'grapes', 'watermelon', 'muskmelon',
        'chickpea', 'lentil', 'kidneybeans', 'pigeonpeas',
        'blackgram', 'mungbean', 'papaya', 'coffee',
    ],
    'temperate': [
        'apple', 'grapes', 'maize', 'chickpea', 'lentil',
        'kidneybeans', 'pomegranate', 'orange', 'cotton',
    ],
    'arid': [
        'mothbeans', 'chickpea', 'mungbean', 'cotton',
        'pomegranate', 'watermelon', 'muskmelon', 'maize',
        'pigeonpeas', 'lentil',
    ],

    # Default - all crops (no filtering)
    'any': ALL_CROPS,
}

# --- City -> Region lookup (common Indian cities) ----------------------------

CITY_REGIONS = {
    # South India
    'bengaluru': 'south_india', 'bangalore': 'south_india',
    'chennai': 'south_india', 'hyderabad': 'south_india',
    'kochi': 'south_india', 'thiruvananthapuram': 'south_india',
    'coimbatore': 'south_india', 'mysuru': 'south_india',
    'mysore': 'south_india', 'mangalore': 'south_india',
    'visakhapatnam': 'south_india', 'madurai': 'south_india',

    # North India
    'delhi': 'north_india', 'new delhi': 'north_india',
    'lucknow': 'north_india', 'jaipur': 'north_india',
    'chandigarh': 'north_india', 'amritsar': 'north_india',
    'dehradun': 'north_india', 'shimla': 'temperate',
    'srinagar': 'temperate', 'varanasi': 'north_india',

    # West India
    'mumbai': 'west_india', 'pune': 'west_india',
    'ahmedabad': 'west_india', 'surat': 'west_india',
    'nagpur': 'central_india', 'nashik': 'west_india',
    'rajkot': 'arid', 'jodhpur': 'arid',

    # East India
    'kolkata': 'east_india', 'bhubaneswar': 'east_india',
    'patna': 'east_india', 'guwahati': 'east_india',
    'ranchi': 'east_india',

    # Central India
    'bhopal': 'central_india', 'indore': 'central_india',
    'raipur': 'central_india', 'jabalpur': 'central_india',
}


# --- Public API --------------------------------------------------------------

def get_region_for_city(city_name):
    """Look up region for a given city name (case-insensitive)."""
    if not city_name:
        return 'any'
    return CITY_REGIONS.get(city_name.lower().strip(), 'any')


def get_viable_crops(region='any'):
    """Get the list of crops viable in a given region."""
    return REGION_CROPS.get(region, REGION_CROPS['any'])


def filter_predictions(predictions, region='any'):
    """
    Filter ML predictions to only include region-appropriate crops.

    Args:
        predictions: list of (crop_name, probability) tuples, sorted desc
        region: key from REGION_CROPS

    Returns:
        Filtered list of (crop_name, probability) tuples.
        Falls back to original list if filtering removes everything.
    """
    viable = set(get_viable_crops(region))
    filtered = [(crop, prob) for crop, prob in predictions if crop in viable]
    return filtered if filtered else predictions


def get_default_soil_for_city(city_name):
    """Look up the default indigenous soil type for a city.
    Chains city → region → soil type lookups."""
    from soil_service import get_default_soil_for_region
    region = get_region_for_city(city_name)
    return get_default_soil_for_region(region)


def get_available_regions():
    """Return display-name -> key mapping for the settings UI."""
    return {
        'India - South': 'south_india',
        'India - North': 'north_india',
        'India - West': 'west_india',
        'India - East': 'east_india',
        'India - Central': 'central_india',
        'Tropical': 'tropical',
        'Subtropical': 'subtropical',
        'Temperate': 'temperate',
        'Arid / Semi-Arid': 'arid',
        'Any / No Filter': 'any',
    }
