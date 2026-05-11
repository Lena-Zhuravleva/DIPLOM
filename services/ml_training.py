import os
import joblib
import pandas as pd

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score

from services.ml_dataset import build_supplier_ml_dataset


MODEL_DIR = "ml_models"
MODEL_PATH = os.path.join(MODEL_DIR, "supplier_risk_model.pkl")


FEATURE_COLUMNS = [
    "price",
    "lead_time_days",
    "supplier_rating",
    "quantity",
    "duration_min",
    "delay_minutes",
    "quality_score"
]


def prepare_dataframe():
    rows = build_supplier_ml_dataset()

    internal_df = pd.DataFrame(rows) if rows else pd.DataFrame()

    external_path = os.path.join("data", "supplier_risk_dataset.csv")
    external_df = pd.DataFrame()

    if os.path.exists(external_path):
        raw = pd.read_csv(external_path)

        rename_map = {
            "price": "price",
            "Price": "price",
            "lead_time_days": "lead_time_days",
            "Lead Time": "lead_time_days",
            "LeadTime": "lead_time_days",
            "supplier_rating": "supplier_rating",
            "Supplier Rating": "supplier_rating",
            "rating": "supplier_rating",
            "quantity": "quantity",
            "Quantity": "quantity",
            "duration_min": "duration_min",
            "delay_minutes": "delay_minutes",
            "Delay": "delay_minutes",
            "quality_score": "quality_score",
            "Quality Score": "quality_score",
            "target_problem": "target_problem",
            "Risk": "target_problem",
            "risk": "target_problem",
            "Risk Category": "risk_category"
        }

        raw = raw.rename(columns={c: rename_map.get(c, c) for c in raw.columns})

        external_df = pd.DataFrame()

        for col in FEATURE_COLUMNS:
            if col in raw.columns:
                external_df[col] = raw[col]
            else:
                external_df[col] = 0

        if "target_problem" in raw.columns:
            external_df["target_problem"] = raw["target_problem"]
        elif "risk_category" in raw.columns:
            external_df["target_problem"] = raw["risk_category"].astype(str).str.lower().apply(
                lambda x: 1 if x in ["high", "medium", "risk", "problem", "1"] else 0
            )
        else:
            external_df["target_problem"] = 0

    frames = []

    if not internal_df.empty:
        frames.append(internal_df)

    if not external_df.empty:
        frames.append(external_df)

    if not frames:
        return None

    df = pd.concat(frames, ignore_index=True)

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0

    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)
    df["target_problem"] = pd.to_numeric(df["target_problem"], errors="coerce").fillna(0).astype(int)

    if "target_problem" not in df.columns:
        return None

    return df


def train_supplier_risk_model():
    df = prepare_dataframe()

    if df is None or len(df) < 5:
        return {
            "success": False,
            "error": "Недостаточно данных для обучения. Нужно хотя бы 5 поставок."
        }

    X = df[FEATURE_COLUMNS]
    y = df["target_problem"]

    if y.nunique() < 2:
        return {
            "success": False,
            "error": "Недостаточно разных классов. Нужны и нормальные, и проблемные поставки."
        }

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.3,
        random_state=42
    )

    model = GradientBoostingClassifier(
        n_estimators=80,
        learning_rate=0.08,
        max_depth=3,
        random_state=42
    )

    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    metrics = {
        "accuracy": round(accuracy_score(y_test, y_pred), 3),
        "precision": round(precision_score(y_test, y_pred, zero_division=0), 3),
        "recall": round(recall_score(y_test, y_pred, zero_division=0), 3),
    }
    feature_importance = []

    for name, value in zip(FEATURE_COLUMNS, model.feature_importances_):
        feature_importance.append({
            "feature": name,
            "importance": round(float(value), 3)
        })

    feature_importance.sort(key=lambda x: x["importance"], reverse=True)

    os.makedirs(MODEL_DIR, exist_ok=True)

    joblib.dump({
        "model": model,
        "feature_columns": FEATURE_COLUMNS,
        "metrics": metrics,
        "feature_importance": feature_importance
    }, MODEL_PATH)

    return {
        "success": True,
        "rows": len(df),
        "features": FEATURE_COLUMNS,
        "metrics": metrics,
        "feature_importance": feature_importance,
        "model_path": MODEL_PATH
    }


def load_supplier_risk_model():
    if not os.path.exists(MODEL_PATH):
        return None

    return joblib.load(MODEL_PATH)


def predict_supplier_risk(features):
    saved = load_supplier_risk_model()

    if saved is None:
        return None

    model = saved["model"]
    feature_columns = saved["feature_columns"]

    row = {}

    for col in feature_columns:
        row[col] = features.get(col, 0)

    df = pd.DataFrame([row])
    df = df.fillna(0)

    probability = model.predict_proba(df)[0][1]

    return round(float(probability), 3)