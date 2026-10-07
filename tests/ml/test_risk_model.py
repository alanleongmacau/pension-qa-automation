"""Quality, robustness and performance tests for the transaction risk-scoring model.

The model is tested as a black box through the API, the same way a QA team
would test a model delivered by a data-science team:

1. Quality gate     – accuracy / precision / recall / F1 on a held-out labelled set
2. Golden cases     – business-critical scenarios that must always be classified correctly
3. Metamorphic      – properties that must hold without knowing the "right" score
                      (more money / more transactions must never LOWER the risk)
4. Contract         – response schema, determinism, input validation
5. Performance      – p95 latency budget
"""
from __future__ import annotations

import csv
import json
import statistics
import time
from pathlib import Path

import pytest
from jsonschema import validate

from tests.helpers import schemas

pytestmark = pytest.mark.ml

DATA = Path(__file__).parents[1] / "data" / "risk_eval_set.csv"
REPORTS = Path(__file__).parents[2] / "reports"

# Recall is weighted highest: missing a suspicious transaction is costlier than a false alarm.
THRESHOLDS = {"accuracy": 0.95, "precision": 0.85, "recall": 0.95, "f1": 0.90}
P95_LATENCY_MS = 100

BASE_PROFILE = {"amount": 10_000, "is_cross_border": False, "txn_count_24h": 3, "account_age_days": 365}


def _load_eval_set() -> list[dict]:
    with DATA.open() as f:
        return [
            {
                "features": {
                    "amount": float(r["amount"]),
                    "is_cross_border": r["is_cross_border"] == "1",
                    "txn_count_24h": int(r["txn_count_24h"]),
                    "account_age_days": int(r["account_age_days"]),
                },
                "label": int(r["label"]),
            }
            for r in csv.DictReader(f)
        ]


# ---------------------------------------------------------------- 1. quality gate
@pytest.mark.smoke
def test_model_meets_quality_thresholds_on_holdout_set(api):
    rows = _load_eval_set()
    tp = fp = fn = tn = 0
    misclassified = []
    for row in rows:
        predicted = api.risk_score(**row["features"]).json()["flagged"]
        actual = bool(row["label"])
        tp += predicted and actual
        fp += predicted and not actual
        fn += actual and not predicted
        tn += not predicted and not actual
        if predicted != actual:
            misclassified.append({**row["features"], "label": row["label"]})

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    metrics = {
        "samples": len(rows),
        "positives": tp + fn,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "accuracy": round((tp + tn) / len(rows), 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        "thresholds": THRESHOLDS,
        "misclassified": misclassified,
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "model_metrics.json").write_text(json.dumps(metrics, indent=2))

    failures = {k: (metrics[k], v) for k, v in THRESHOLDS.items() if metrics[k] < v}
    assert not failures, f"Model below quality gate (actual, required): {failures}"


# ---------------------------------------------------------------- 2. golden cases
@pytest.mark.parametrize(
    "features, expected_flag",
    [
        pytest.param({"amount": 80_000, "is_cross_border": True, "txn_count_24h": 1, "account_age_days": 2000}, True,
                     id="large-cross-border-transfer"),
        pytest.param({"amount": 25_000, "is_cross_border": False, "txn_count_24h": 1, "account_age_days": 5}, True,
                     id="large-amount-new-account"),
        pytest.param({"amount": 800, "is_cross_border": False, "txn_count_24h": 25, "account_age_days": 1500}, True,
                     id="high-velocity-small-amounts"),
        pytest.param({"amount": 3_000, "is_cross_border": False, "txn_count_24h": 1, "account_age_days": 1000}, False,
                     id="routine-monthly-contribution"),
        pytest.param({"amount": 40_000, "is_cross_border": True, "txn_count_24h": 2, "account_age_days": 900}, False,
                     id="moderate-cross-border-established"),
        pytest.param({"amount": 60_000, "is_cross_border": False, "txn_count_24h": 2, "account_age_days": 900}, False,
                     id="large-domestic-established"),
    ],
)
def test_golden_scenarios(api, features, expected_flag):
    body = api.risk_score(**features).json()

    assert body["flagged"] is expected_flag, f"score={body['score']}"


# ---------------------------------------------------------------- 3. metamorphic properties
@pytest.mark.parametrize("cross_border", [False, True])
@pytest.mark.parametrize("account_age_days", [10, 365, 3000])
def test_score_never_decreases_as_amount_increases(api, cross_border, account_age_days):
    amounts = [100, 1_000, 10_000, 20_001, 35_000, 50_001, 75_000, 150_000]
    scores = [
        api.risk_score(**{**BASE_PROFILE, "amount": a, "is_cross_border": cross_border,
                          "account_age_days": account_age_days}).json()["score"]
        for a in amounts
    ]

    assert scores == sorted(scores), dict(zip(amounts, scores))


def test_score_never_decreases_as_transaction_count_increases(api):
    counts = [0, 2, 5, 10, 15, 16, 20, 40]
    scores = [api.risk_score(**{**BASE_PROFILE, "txn_count_24h": c}).json()["score"] for c in counts]

    assert scores == sorted(scores), dict(zip(counts, scores))


def test_score_never_increases_as_account_gets_older(api):
    ages = [0, 7, 29, 30, 90, 365, 3650]
    profile = {**BASE_PROFILE, "amount": 25_000}
    scores = [api.risk_score(**{**profile, "account_age_days": a}).json()["score"] for a in ages]

    assert scores == sorted(scores, reverse=True), dict(zip(ages, scores))


# ---------------------------------------------------------------- 4. contract & robustness
def test_response_matches_contract_and_flag_matches_threshold(api):
    for amount in (500, 30_000, 90_000):
        body = api.risk_score(**{**BASE_PROFILE, "amount": amount, "is_cross_border": True}).json()
        validate(body, schemas.RISK_SCORE)
        assert body["flagged"] == (body["score"] >= 0.5)


def test_scoring_is_deterministic(api):
    scores = {api.risk_score(**BASE_PROFILE).json()["score"] for _ in range(10)}

    assert len(scores) == 1


@pytest.mark.parametrize(
    "override",
    [{"amount": -1}, {"txn_count_24h": -1}, {"account_age_days": -5}, {"amount": "lots"}, {"is_cross_border": "maybe"}],
    ids=["negative-amount", "negative-count", "negative-age", "string-amount", "bad-boolean"],
)
def test_invalid_features_are_rejected(api, override):
    assert api.risk_score(**{**BASE_PROFILE, **override}).status_code == 422


def test_extreme_values_are_handled(api):
    resp = api.risk_score(amount=1e12, is_cross_border=True, txn_count_24h=10_000, account_age_days=0)

    assert resp.status_code == 200
    assert 0.0 <= resp.json()["score"] <= 1.0


# ---------------------------------------------------------------- 5. performance
def test_p95_scoring_latency_within_budget(api):
    api.risk_score(**BASE_PROFILE)  # warm-up
    timings = []
    for i in range(200):
        start = time.perf_counter()
        resp = api.risk_score(**{**BASE_PROFILE, "amount": 1_000 + i * 250})
        timings.append((time.perf_counter() - start) * 1000)
        assert resp.status_code == 200

    p95 = statistics.quantiles(timings, n=100)[94]
    print(f"\nlatency ms: median={statistics.median(timings):.1f} p95={p95:.1f} max={max(timings):.1f}")
    assert p95 < P95_LATENCY_MS
