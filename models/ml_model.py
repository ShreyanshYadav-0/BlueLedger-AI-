import os

import pandas as pd
from sklearn.ensemble import IsolationForest

_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model

    csv_path = os.path.join("dataset", "enterprise_transactions.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path).dropna()
        df["amount"] = df["amount"].astype(float)
        amounts = df[["amount"]]
    else:
        amounts = pd.DataFrame({"amount": [100, 250, 500, 1200, 3000, 8000, 15000, 45000]})

    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(amounts)
    _model = model
    return _model


def predict_risk(amount):
    """Return a stable risk label stored in the database."""
    model = _load_model()
    prediction = model.predict([[float(amount)]])
    if prediction[0] == -1:
        return "High Risk Transaction"
    return "Normal Transaction"
