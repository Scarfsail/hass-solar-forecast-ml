# model.py
import logging

import joblib
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler

from .config import Configuration

_LOGGER = logging.getLogger(__name__)

# -----------------------------
# Existing functions for PV power prediction...
# def train_model(data_df, model_path, scaler_path):
#     ... (your existing PV power training code)
# -----------------------------

# Consumption Model (Quantile Regression) Functions
CONSUMPTION_MODEL_PREFIX = "consumption_model"


def train_consumption_model(df: pd.DataFrame):
    """
    Train three GradientBoostingRegressor models (for quantile regression) to predict energy consumption.
    We use:
      - alpha=0.05 for the lower bound (minimal predicted usage),
      - alpha=0.5 for the median (most probable usage),
      - alpha=0.95 for the upper bound (maximal predicted usage).

    The features used are: hour and day_of_week.
    The models and a StandardScaler are saved to disk with filenames prefixed by model_path_prefix.
    """
    cfg = Configuration.get_instance()
    if df.empty or len(df) < 10:
        raise ValueError("Not enough data to train consumption model.")
    feature_cols = ["hour", "day_of_week"]
    X = df[feature_cols].values
    y = df["power"].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train models for three quantiles
    model_low = GradientBoostingRegressor(
        loss="quantile", alpha=0.05, n_estimators=100, max_depth=3
    )
    model_med = GradientBoostingRegressor(
        loss="quantile", alpha=0.5, n_estimators=100, max_depth=3
    )
    model_high = GradientBoostingRegressor(
        loss="quantile", alpha=0.95, n_estimators=100, max_depth=3
    )

    model_low.fit(X_scaled, y)
    model_med.fit(X_scaled, y)
    model_high.fit(X_scaled, y)

    # Save the models and scaler using the given prefix.
    joblib.dump(model_low, cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_low.pkl"))
    joblib.dump(model_med, cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_med.pkl"))
    joblib.dump(model_high, cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_high.pkl"))
    joblib.dump(scaler, cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_scaler.pkl"))

    return (model_low, model_med, model_high), scaler


def load_consumption_models():
    """
    Load the three trained models and the scaler from disk.
    """
    cfg = Configuration.get_instance()
    model_low = joblib.load(cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_low.pkl"))
    model_med = joblib.load(cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_med.pkl"))
    model_high = joblib.load(cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_high.pkl"))
    scaler = joblib.load(cfg.storage_path(CONSUMPTION_MODEL_PREFIX + "_scaler.pkl"))
    return (model_low, model_med, model_high), scaler


def predict_consumption(models, scaler, input_data):
    """
    Given input_data (a list of dicts with keys 'hour' and 'day_of_week'),
    predict energy consumption for each input using the three quantile models.

    Returns a list of dictionaries for each input sample with:
      - "hour": input hour,
      - "min": lower quantile prediction,
      - "med": median prediction,
      - "max": upper quantile prediction.
    """
    df = pd.DataFrame(input_data)
    feature_cols = ["hour", "day_of_week"]
    if not all(col in df.columns for col in feature_cols):
        raise ValueError("Input data must contain 'hour' and 'day_of_week'")
    X = df[feature_cols].values
    X_scaled = scaler.transform(X)

    pred_low = models[0].predict(X_scaled)
    pred_med = models[1].predict(X_scaled)
    pred_high = models[2].predict(X_scaled)

    predictions = []
    for i in range(len(pred_low)):
        predictions.append(
            {
                "hour": input_data[i]["hour"],
                "min": pred_low[i],
                "med": pred_med[i],
                "max": pred_high[i],
            }
        )
    return predictions
