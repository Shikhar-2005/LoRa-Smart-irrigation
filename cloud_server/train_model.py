"""
LoRa Smart Irrigation - ML Model Training

Trains a Random Forest classifier on the Kaggle Crop Recommendation dataset.
Falls back to synthetic data generation if the dataset CSV isn't available.

Usage:
    python train_model.py

Output:
    crop_model.pkl - serialized scikit-learn Random Forest model
"""

import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, 'crop_model.pkl')
DATASET_PATH = os.path.join(SCRIPT_DIR, 'Crop_recommendation.csv')

# --- Crop profiles (parameter ranges matching Kaggle dataset stats) ----------

CROP_PROFILES = {
    'rice':        {'N': (60, 100),  'P': (35, 60),   'K': (35, 55),   'temperature': (20, 28), 'humidity': (80, 95),  'ph': (5.0, 7.0), 'rainfall': (180, 260)},
    'maize':       {'N': (60, 100),  'P': (35, 60),   'K': (15, 35),   'temperature': (18, 28), 'humidity': (55, 75),  'ph': (5.5, 7.0), 'rainfall': (60, 110)},
    'chickpea':    {'N': (20, 50),   'P': (55, 80),   'K': (75, 85),   'temperature': (15, 22), 'humidity': (14, 20),  'ph': (7.0, 8.0), 'rainfall': (65, 100)},
    'kidneybeans': {'N': (15, 30),   'P': (55, 75),   'K': (15, 25),   'temperature': (15, 22), 'humidity': (18, 25),  'ph': (5.5, 6.5), 'rainfall': (60, 110)},
    'pigeonpeas':  {'N': (15, 35),   'P': (55, 75),   'K': (15, 25),   'temperature': (18, 32), 'humidity': (30, 65),  'ph': (4.5, 7.5), 'rainfall': (120, 170)},
    'mothbeans':   {'N': (15, 30),   'P': (40, 60),   'K': (15, 25),   'temperature': (24, 32), 'humidity': (40, 65),  'ph': (3.5, 9.0), 'rainfall': (30, 70)},
    'mungbean':    {'N': (15, 35),   'P': (40, 65),   'K': (15, 25),   'temperature': (27, 31), 'humidity': (80, 90),  'ph': (6.0, 7.5), 'rainfall': (35, 60)},
    'blackgram':   {'N': (25, 45),   'P': (55, 75),   'K': (15, 25),   'temperature': (25, 35), 'humidity': (60, 70),  'ph': (6.0, 8.0), 'rainfall': (60, 70)},
    'lentil':      {'N': (15, 30),   'P': (55, 80),   'K': (15, 25),   'temperature': (18, 28), 'humidity': (18, 65),  'ph': (6.0, 8.0), 'rainfall': (35, 55)},
    'pomegranate': {'N': (15, 35),   'P': (5, 20),    'K': (35, 55),   'temperature': (18, 26), 'humidity': (85, 95),  'ph': (5.5, 7.5), 'rainfall': (100, 120)},
    'banana':      {'N': (80, 120),  'P': (70, 100),  'K': (45, 55),   'temperature': (25, 32), 'humidity': (75, 85),  'ph': (5.5, 7.0), 'rainfall': (90, 115)},
    'mango':       {'N': (15, 35),   'P': (15, 30),   'K': (25, 45),   'temperature': (27, 37), 'humidity': (45, 65),  'ph': (4.5, 7.0), 'rainfall': (90, 110)},
    'grapes':      {'N': (15, 35),   'P': (120, 145), 'K': (190, 210), 'temperature': (8, 42),  'humidity': (80, 84),  'ph': (5.5, 7.0), 'rainfall': (60, 75)},
    'watermelon':  {'N': (80, 110),  'P': (5, 20),    'K': (45, 55),   'temperature': (24, 28), 'humidity': (80, 90),  'ph': (6.0, 7.0), 'rainfall': (40, 55)},
    'muskmelon':   {'N': (80, 110),  'P': (5, 20),    'K': (45, 55),   'temperature': (27, 31), 'humidity': (90, 93),  'ph': (6.0, 7.0), 'rainfall': (20, 30)},
    'apple':       {'N': (15, 35),   'P': (120, 145), 'K': (195, 210), 'temperature': (21, 25), 'humidity': (90, 94),  'ph': (5.5, 6.5), 'rainfall': (100, 130)},
    'orange':      {'N': (15, 30),   'P': (5, 15),    'K': (5, 15),    'temperature': (10, 35), 'humidity': (90, 95),  'ph': (6.5, 8.0), 'rainfall': (100, 120)},
    'papaya':      {'N': (35, 60),   'P': (45, 65),   'K': (45, 55),   'temperature': (22, 37), 'humidity': (90, 95),  'ph': (6.0, 7.0), 'rainfall': (110, 150)},
    'coconut':     {'N': (15, 30),   'P': (5, 15),    'K': (25, 35),   'temperature': (25, 30), 'humidity': (90, 98),  'ph': (5.5, 6.5), 'rainfall': (130, 175)},
    'cotton':      {'N': (100, 140), 'P': (40, 60),   'K': (15, 25),   'temperature': (22, 27), 'humidity': (75, 85),  'ph': (6.5, 8.0), 'rainfall': (60, 85)},
    'jute':        {'N': (60, 90),   'P': (40, 55),   'K': (35, 45),   'temperature': (23, 28), 'humidity': (78, 92),  'ph': (6.0, 7.5), 'rainfall': (150, 180)},
    'coffee':      {'N': (80, 120),  'P': (15, 30),   'K': (25, 35),   'temperature': (23, 28), 'humidity': (50, 70),  'ph': (6.0, 7.0), 'rainfall': (120, 170)},
}

FEATURES = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']


def generate_synthetic_data(samples_per_crop=100):
    """Generate synthetic training data matching Kaggle distribution shapes."""
    print("[*] Generating synthetic training data...")

    rows = []
    rng = np.random.default_rng(seed=42)

    for crop, ranges in CROP_PROFILES.items():
        for _ in range(samples_per_crop):
            sample = {}
            for feature, (lo, hi) in ranges.items():
                mean = (lo + hi) / 2
                std = (hi - lo) / 4
                val = rng.normal(mean, std)
                val = np.clip(val, lo * 0.9, hi * 1.1)
                sample[feature] = round(float(val), 2)
            sample['label'] = crop
            rows.append(sample)

    df = pd.DataFrame(rows)
    print(f"    Generated {len(df)} samples for {len(CROP_PROFILES)} crops")
    return df


def train_model():
    """Train and save the crop recommendation model."""

    # -- Load data ------------------------------------------------------------
    if os.path.exists(DATASET_PATH):
        print(f"[OK] Found dataset: {DATASET_PATH}")
        df = pd.read_csv(DATASET_PATH)
    else:
        print(f"[!] Dataset not found at {DATASET_PATH}")
        print("    Download from: https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset")
        print("    Falling back to synthetic data generation...\n")
        df = generate_synthetic_data()

    X = df[FEATURES]
    y = df['label']

    print(f"\n[*] Dataset shape: {X.shape}")
    print(f"[*] Unique crops: {len(y.unique())}")
    print(f"[*] Samples per crop: ~{len(df) // len(y.unique())}")

    # -- Train / Test split ---------------------------------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # -- Train Random Forest --------------------------------------------------
    print("\n[*] Training Random Forest (100 estimators)...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=None,
        min_samples_split=2,
        min_samples_leaf=1,
        random_state=42,
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    # -- Evaluate -------------------------------------------------------------
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"\n{'=' * 50}")
    print(f"  Model Accuracy: {accuracy * 100:.2f}%")
    print(f"{'=' * 50}")

    if accuracy < 0.90:
        print("\n[!] WARNING: Accuracy below 90%.")

    print(f"\n{classification_report(y_test, y_pred)}")

    # -- Feature importance ---------------------------------------------------
    print("[*] Feature Importance:")
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_),
                            key=lambda x: -x[1]):
        bar = '#' * int(imp * 50)
        print(f"    {feat:>12}: {imp:.4f}  {bar}")

    # -- Save -----------------------------------------------------------------
    joblib.dump(model, MODEL_PATH)
    size_kb = os.path.getsize(MODEL_PATH) / 1024
    print(f"\n[OK] Model saved: {MODEL_PATH}  ({size_kb:.1f} KB)")

    return model, accuracy


if __name__ == '__main__':
    train_model()
