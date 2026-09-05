"""
Recovery Probability Model for RecoverOS.

Trains Logistic Regression (baseline) + GradientBoosting (primary) on synthetic data.
Outputs P(recovery | action) per candidate action, not just per transaction.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

from app.models.base import ActionType


# Feature columns used for prediction
FEATURE_COLS = [
    "amount", "retry_count", "previous_transactions", "previous_success_rate",
    "avg_payment_amount", "customer_lifetime_value", "days_since_last_payment",
    "hour_of_day", "day_of_month", "is_weekend",
]

CATEGORICAL_COLS = [
    "failure_reason", "customer_segment", "payment_method", "action_taken",
]


class RecoveryPredictor:
    """
    ML model that predicts P(recovery | context, action).

    Uses a GradientBoostingClassifier as the primary model, with a
    LogisticRegression baseline for comparison.
    """

    def __init__(self):
        self.primary_model: Optional[GradientBoostingClassifier] = None
        self.baseline_model: Optional[LogisticRegression] = None
        self.label_encoders: dict[str, LabelEncoder] = {}
        self.scaler: Optional[StandardScaler] = None
        self.is_trained: bool = False
        self._feature_names: list[str] = []

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Engineer features from raw data."""
        df = df.copy()

        # Time features
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], errors="coerce")
            df["hour_of_day"] = ts.dt.hour.fillna(12).astype(int)
            df["day_of_month"] = ts.dt.day.fillna(15).astype(int)
            df["is_weekend"] = ts.dt.dayofweek.isin([5, 6]).astype(int)
        else:
            df["hour_of_day"] = 12
            df["day_of_month"] = 15
            df["is_weekend"] = 0

        # Salary date flag (25th - 5th of month)
        df["near_salary_date"] = ((df["day_of_month"] >= 25) | (df["day_of_month"] <= 5)).astype(int)

        # Fill NaNs
        for col in FEATURE_COLS:
            if col in df.columns:
                df[col] = df[col].fillna(0)
            else:
                df[col] = 0

        return df

    def _encode_categoricals(self, df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        """Encode categorical columns to numeric."""
        df = df.copy()
        for col in CATEGORICAL_COLS:
            if col not in df.columns:
                df[col] = "unknown"

            if fit:
                le = LabelEncoder()
                # Add 'unknown' to handle unseen values at prediction time
                all_vals = list(df[col].astype(str).unique()) + ["unknown"]
                le.fit(all_vals)
                self.label_encoders[col] = le

            le = self.label_encoders.get(col)
            if le is not None:
                # Map unseen values to 'unknown'
                df[col] = df[col].astype(str).map(
                    lambda x, _le=le: x if x in _le.classes_ else "unknown"
                )
                df[f"{col}_encoded"] = le.transform(df[col])
            else:
                df[f"{col}_encoded"] = 0

        return df

    def _get_feature_matrix(self, df: pd.DataFrame) -> np.ndarray:
        """Extract feature matrix from prepared DataFrame."""
        feature_cols = FEATURE_COLS + [f"{c}_encoded" for c in CATEGORICAL_COLS] + ["near_salary_date"]
        self._feature_names = feature_cols
        return df[feature_cols].values.astype(float)

    def train(self, csv_path: str, model_dir: Optional[str] = None) -> dict:
        """
        Train both baseline and primary models on synthetic data.

        Returns training metrics.
        """
        print("  Loading data...")
        df = pd.read_csv(csv_path)
        print(f"  Loaded {len(df)} records")

        # Prepare features
        df = self._prepare_features(df)
        df = self._encode_categoricals(df, fit=True)

        X = self._get_feature_matrix(df)
        y = df["recovered"].values.astype(int)

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, random_state=42, stratify=y
        )

        # Baseline: Logistic Regression
        print("  Training Logistic Regression baseline...")
        self.baseline_model = LogisticRegression(
            max_iter=1000, random_state=42, class_weight="balanced"
        )
        self.baseline_model.fit(X_train, y_train)
        baseline_score = self.baseline_model.score(X_test, y_test)
        baseline_probs = self.baseline_model.predict_proba(X_test)[:, 1]
        baseline_auc = roc_auc_score(y_test, baseline_probs)
        print(f"    Accuracy: {baseline_score:.4f}, AUC: {baseline_auc:.4f}")

        # Primary: Gradient Boosting
        print("  Training GradientBoosting primary model...")
        self.primary_model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            min_samples_split=10,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
        )
        self.primary_model.fit(X_train, y_train)
        primary_score = self.primary_model.score(X_test, y_test)
        primary_probs = self.primary_model.predict_proba(X_test)[:, 1]
        primary_auc = roc_auc_score(y_test, primary_probs)
        print(f"    Accuracy: {primary_score:.4f}, AUC: {primary_auc:.4f}")

        self.is_trained = True

        # Save model
        if model_dir:
            self.save(model_dir)

        metrics = {
            "baseline_accuracy": round(baseline_score, 4),
            "baseline_auc": round(baseline_auc, 4),
            "primary_accuracy": round(primary_score, 4),
            "primary_auc": round(primary_auc, 4),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "feature_count": X.shape[1],
        }

        # Feature importance
        if hasattr(self.primary_model, "feature_importances_"):
            importances = self.primary_model.feature_importances_
            feature_imp = sorted(
                zip(self._feature_names, importances),
                key=lambda x: -x[1]
            )[:10]
            metrics["top_features"] = [
                {"feature": f, "importance": round(float(imp), 4)}
                for f, imp in feature_imp
            ]
            print("  Top features:")
            for f, imp in feature_imp[:5]:
                print(f"    {f}: {imp:.4f}")

        return metrics

    def predict(
        self,
        failure_reason: str,
        customer_segment: str,
        payment_method: str,
        amount: float,
        retry_count: int = 0,
        previous_transactions: int = 0,
        previous_success_rate: float = 0.5,
        avg_payment_amount: float = 1000.0,
        customer_lifetime_value: float = 5000.0,
        days_since_last_payment: int = 7,
        hour_of_day: int = 12,
        day_of_month: int = 15,
        actions: Optional[list[str]] = None,
    ) -> dict[str, float]:
        """
        Predict P(recovery | action) for each candidate action.

        Returns a dict mapping action_type → recovery probability.
        """
        if actions is None:
            actions = [a.value for a in ActionType if a != ActionType.STOP]

        is_weekend = 0  # simplified
        near_salary_date = 1 if (day_of_month >= 25 or day_of_month <= 5) else 0

        results = {}
        for action in actions:
            # Build a single-row DataFrame
            row = {
                "amount": amount,
                "retry_count": retry_count,
                "previous_transactions": previous_transactions,
                "previous_success_rate": previous_success_rate,
                "avg_payment_amount": avg_payment_amount,
                "customer_lifetime_value": customer_lifetime_value,
                "days_since_last_payment": days_since_last_payment,
                "hour_of_day": hour_of_day,
                "day_of_month": day_of_month,
                "is_weekend": is_weekend,
                "near_salary_date": near_salary_date,
                "failure_reason": failure_reason,
                "customer_segment": customer_segment,
                "payment_method": payment_method,
                "action_taken": action,
            }
            df = pd.DataFrame([row])
            df = self._encode_categoricals(df, fit=False)

            feature_cols = FEATURE_COLS + [f"{c}_encoded" for c in CATEGORICAL_COLS] + ["near_salary_date"]
            X = df[feature_cols].values.astype(float)

            if self.scaler is not None:
                X = self.scaler.transform(X)

            if self.primary_model is not None and self.is_trained:
                prob = float(self.primary_model.predict_proba(X)[0, 1])
            else:
                # Fallback to heuristic probabilities
                prob = self._heuristic_probability(failure_reason, action, customer_segment, day_of_month)

            results[action] = round(min(max(prob, 0.01), 0.99), 4)

        return results

    def _heuristic_probability(
        self,
        failure_reason: str,
        action: str,
        customer_segment: str,
        day_of_month: int,
    ) -> float:
        """Fallback heuristic when model isn't trained yet."""
        # Import from synthetic generator for consistent base rates
        base_rates = {
            "BANK_DOWNTIME": {"retry_delayed": 0.70, "send_payment_link": 0.55, "retry_now": 0.15},
            "INSUFFICIENT_FUNDS": {"retry_delayed": 0.45, "offer_discount": 0.48, "send_payment_link": 0.35},
            "EXPIRED_CARD": {"switch_to_upi": 0.62, "send_payment_link": 0.58, "whatsapp_nudge": 0.45},
            "AUTH_OTP_FAILURE": {"send_payment_link": 0.55, "switch_to_upi": 0.50, "whatsapp_nudge": 0.40},
            "USER_ABANDONED": {"whatsapp_nudge": 0.55, "offer_discount": 0.52, "send_payment_link": 0.48},
            "SUBSCRIPTION_MANDATE_FAILURE": {"send_payment_link": 0.55, "escalate_human": 0.45, "whatsapp_nudge": 0.42},
            "SUSPECTED_FRAUD": {"escalate_human": 0.15, "stop": 0.0},
            "INVALID_DETAILS": {"send_payment_link": 0.50, "whatsapp_nudge": 0.42, "switch_to_upi": 0.35},
            "MERCHANT_INTEGRATION_ERROR": {"escalate_human": 0.60, "retry_delayed": 0.55, "retry_now": 0.30},
        }

        cause_rates = base_rates.get(failure_reason, {})
        p = cause_rates.get(action, 0.15)

        # Segment modifier
        if customer_segment == "vip":
            p *= 1.15
        elif customer_segment == "at_risk":
            p *= 0.75

        return min(max(p, 0.01), 0.99)

    def save(self, model_dir: str) -> None:
        """Save trained model artifacts."""
        os.makedirs(model_dir, exist_ok=True)
        artifact = {
            "primary_model": self.primary_model,
            "baseline_model": self.baseline_model,
            "label_encoders": self.label_encoders,
            "scaler": self.scaler,
            "feature_names": self._feature_names,
            "is_trained": self.is_trained,
        }
        path = os.path.join(model_dir, "recovery_model.joblib")
        joblib.dump(artifact, path)
        print(f"  ✓ Model saved to {path}")

    def load(self, model_dir: str) -> bool:
        """Load trained model artifacts. Returns True if successful."""
        path = os.path.join(model_dir, "recovery_model.joblib")
        if not os.path.exists(path):
            print(f"  ⚠ No model found at {path}, using heuristics")
            return False
        try:
            artifact = joblib.load(path)
            self.primary_model = artifact["primary_model"]
            self.baseline_model = artifact["baseline_model"]
            self.label_encoders = artifact["label_encoders"]
            self.scaler = artifact["scaler"]
            self._feature_names = artifact["feature_names"]
            self.is_trained = artifact["is_trained"]
            print(f"  ✓ Model loaded from {path}")
            return True
        except Exception as e:
            print(f"  ⚠ Failed to load model: {e}")
            return False


# Module-level singleton
recovery_predictor = RecoveryPredictor()


def main():
    """CLI entry point for training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train RecoverOS recovery predictor")
    parser.add_argument("--train", action="store_true", help="Train the model")
    parser.add_argument("--data", type=str, default=None, help="Path to CSV data")
    args = parser.parse_args()

    if args.train:
        project_dir = Path(__file__).resolve().parent.parent.parent.parent
        data_path = args.data or str(project_dir / "data" / "synthetic_transactions.csv")
        model_dir = str(project_dir / "data")

        print(f"\n🧠 RecoverOS Recovery Predictor — Training")
        print(f"  Data: {data_path}")

        metrics = recovery_predictor.train(data_path, model_dir)
        print(f"\n📊 Training Results:")
        for k, v in metrics.items():
            if k != "top_features":
                print(f"  {k}: {v}")
        print("\n✅ Training complete!\n")


if __name__ == "__main__":
    main()
