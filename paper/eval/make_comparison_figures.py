"""Before/after figures for the remediation section, from results.json (baseline) and results_after.json."""
import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"
before = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
after = json.loads((HERE / "results_after.json").read_text(encoding="utf-8"))

# Approval latency vs stored workflows
fig, ax = plt.subplots(figsize=(3.45, 2.2))
for res, label, style in [(before, "Baseline (linear scan)", "o-"), (after, "After (indexed)", "s--")]:
    xs = [r["workflows"] for r in res["E3_scaling"]]
    ax.plot(xs, [r["approve_p50_ms"] for r in res["E3_scaling"]], style, color="black", ms=3.5, lw=1.1,
            mfc="black" if "Baseline" in label else "white", label=label)
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("Stored workflows (log scale)")
ax.set_ylabel("Median approve (ms)")
ax.grid(alpha=0.3, lw=0.5)
ax.legend(frameon=False, fontsize=7)
fig.tight_layout()
for ext in ("pdf", "svg"):
    fig.savefig(FIG / f"approval_scaling_compare.{ext}")
plt.close(fig)

# Guardrail detection by category
short = {"Verbatim injection": "Verbatim", "Paraphrased injection": "Paraphrased", "Obfuscated injection": "Obfuscated",
         "Code / command payload": "Code/cmd", "Secret leakage": "Secrets"}
rows_b, rows_a = before["E5_guardrail"]["rows"], after["E5_guardrail"]["rows"]
fig, ax = plt.subplots(figsize=(3.45, 2.2))
w = 0.38
for i, (rb, ra) in enumerate(zip(rows_b, rows_a)):
    for off, r, fc in [(-w / 2, rb, "0.35"), (w / 2, ra, "white")]:
        h = 100 * r["detected"] / r["n"]
        ax.bar(i + off, h, w, color=fc, edgecolor="black", lw=0.6)
        ax.text(i + off, h + 2, f"{r['detected']}", ha="center", fontsize=6)
ax.set_xticks(range(len(rows_b)), [short[r["category"]] for r in rows_b], fontsize=7, rotation=25, ha="right")
ax.set_ylim(0, 140)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_ylabel("Detected (%)")
ax.grid(axis="y", alpha=0.3, lw=0.5)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(fc="0.35", ec="black", label="Baseline"), Patch(fc="white", ec="black", label="After")],
          frameon=False, fontsize=7, loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.0))
fig.tight_layout()
for ext in ("pdf", "svg"):
    fig.savefig(FIG / f"guardrail_compare.{ext}")
plt.close(fig)
print("ok")
