"""Transaction risk-screening model used by the /risk/score endpoint.

The model is a gradient-boosted classifier trained on synthetic data at
startup. Monotonic constraints encode domain knowledge that the test suite
verifies (e.g. a larger amount must never *lower* the risk score).
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

MODEL_VERSION = "risk-hgb-1.2.0"
FEATURES = ["amount", "is_cross_border", "txn_count_24h", "account_age_days"]

# +1: score may only go up as the feature grows, -1: only down, 0: free
MONOTONIC_CONSTRAINTS = [1, 0, 1, -1]


def ground_truth_label(amount, is_cross_border, txn_count_24h, account_age_days):
    """Business rule the model is meant to approximate (vectorised)."""
    return (
        ((amount > 50_000) & (is_cross_border == 1))
        | (txn_count_24h > 15)
        | ((account_age_days < 30) & (amount > 20_000))
    ).astype(int)


def generate_dataset(n: int, seed: int, label_noise: float = 0.03):
    rng = np.random.default_rng(seed)
    amount = np.round(rng.gamma(shape=1.6, scale=18_000, size=n), 2)
    is_cross_border = rng.binomial(1, 0.25, size=n)
    txn_count_24h = rng.poisson(5, size=n) + rng.binomial(1, 0.08, size=n) * rng.integers(10, 30, size=n)
    account_age_days = rng.integers(0, 3_650, size=n)
    y = ground_truth_label(amount, is_cross_border, txn_count_24h, account_age_days)
    flip = rng.random(n) < label_noise
    y = np.where(flip, 1 - y, y)
    X = np.column_stack([amount, is_cross_border, txn_count_24h, account_age_days])
    return X, y


class RiskModel:
    def __init__(self, seed: int = 42, n_train: int = 6_000):
        X, y = generate_dataset(n_train, seed)
        self._clf = HistGradientBoostingClassifier(
            max_iter=200,
            learning_rate=0.1,
            monotonic_cst=MONOTONIC_CONSTRAINTS,
            random_state=seed,
        )
        self._clf.fit(X, y)

    def score(self, amount: float, is_cross_border: bool, txn_count_24h: int, account_age_days: int) -> float:
        x = np.array([[amount, int(is_cross_border), txn_count_24h, account_age_days]], dtype=float)
        return float(self._clf.predict_proba(x)[0, 1])
