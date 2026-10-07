"""Print reports/model_metrics.json as a Markdown table (used in the CI job summary)."""
import json
from pathlib import Path

metrics = json.loads((Path(__file__).resolve().parents[1] / "reports" / "model_metrics.json").read_text())
cm = metrics["confusion_matrix"]

print("### Risk model quality gate\n")
print("| Metric | Value | Threshold | Result |\n|---|---|---|---|")
for name, threshold in metrics["thresholds"].items():
    ok = "✅" if metrics[name] >= threshold else "❌"
    print(f"| {name} | {metrics[name]:.4f} | {threshold} | {ok} |")
print(f"\nSamples: {metrics['samples']} · TP {cm['tp']} · FP {cm['fp']} · FN {cm['fn']} · TN {cm['tn']}")
