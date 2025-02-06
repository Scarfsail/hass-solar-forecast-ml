import logging

import joblib
import pandas as pd
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .dal import METEO_PARAMS

_LOGGER = logging.getLogger(__name__)


# Update feature_cols to use the same parameter names
feature_cols = METEO_PARAMS  # + ["sun_altitude", "sun_azimuth"]


def train_model(data_df, model_path, scaler_path):
    """Train an MLP neural network regressor using the merged data.
    The data_df must include all meteo features and a 'power' column.
    Saves the trained model and scaler to the provided paths.
    """

    _LOGGER.info("Starting training with %d records", len(data_df))

    for col in [*feature_cols, "power"]:
        if col not in data_df.columns:
            raise ValueError(f"Column {col} not found in data.")
    X = data_df[feature_cols].values
    y = data_df["power"].values

    # Scale the features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Create and train the MLP regressor
    model = MLPRegressor(
        random_state=42,  # for reproducibility
        hidden_layer_sizes=(128, 64),
        activation="relu",
        learning_rate="adaptive",
        solver="adam",
        max_iter=5000,
    )

    # Perform 5-fold cross validation
    # cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="r2")
    # _LOGGER.info(f"Cross-validation R² scores: {cv_scores}")
    # _LOGGER.info(
    #    f"Mean R² score: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})"
    # )

    model.fit(X_scaled, y)

    # Save the model and scaler
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    return model, scaler


def load_model_and_scaler(model_path, scaler_path):
    """Load the trained model and scaler."""
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    return model, scaler


def predict_power(model, scaler, forecast_data):
    """
    Given forecast_data (a list of dictionaries with meteo features), predict panel power.
    Returns a list of predictions.
    """

    df = pd.DataFrame(forecast_data)
    for col in feature_cols:
        if col not in df.columns:
            raise ValueError(f"Forecast data missing column {col}")
    X = df[feature_cols].values
    X_scaled = scaler.transform(X)
    predictions = model.predict(X_scaled)
    return predictions.flatten().tolist()
