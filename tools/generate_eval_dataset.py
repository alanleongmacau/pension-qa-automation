"""Generate the held-out, labelled evaluation set for the risk model.

Uses a different random seed from training and *no* label noise, so the labels
are the ground-truth business rule the model is supposed to learn.

    python tools/generate_eval_dataset.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.risk_model import FEATURES, generate_dataset  # noqa: E402

OUT = ROOT / "tests" / "data" / "risk_eval_set.csv"


def main(n: int = 400, seed: int = 2026) -> None:
    X, y = generate_dataset(n, seed, label_noise=0.0)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([*FEATURES, "label"])
        for row, label in zip(X, y):
            w.writerow([f"{row[0]:.2f}", int(row[1]), int(row[2]), int(row[3]), int(label)])
    print(f"wrote {n} rows ({int(y.sum())} positive) to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
