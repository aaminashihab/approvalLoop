"""Draws Fig. 1 (system architecture) to paper/figures/architecture.{pdf,svg}."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

FIG = Path(__file__).resolve().parents[1] / "figures"
FIG.mkdir(exist_ok=True)

fig, ax = plt.subplots(figsize=(7.16, 2.55))
ax.set_xlim(0, 100)
ax.set_ylim(0, 36)
ax.axis("off")


def box(x, y, w, h, text, fill="white", bold=False, dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8",
                                fc=fill, ec="black", lw=0.8, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.6,
            fontweight="bold" if bold else "normal", linespacing=1.25)


def arrow(x1, y1, x2, y2, label=None, lx=0, ly=1.1):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, lw=0.8, color="black",
                                 shrinkA=0, shrinkB=0))
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, ha="center", fontsize=5.8, style="italic")


# Untrusted zone
ax.add_patch(FancyBboxPatch((0.6, 6), 16.8, 27.5, boxstyle="round,pad=0.2,rounding_size=1", fc="0.94", ec="0.5", lw=0.6, ls=":"))
ax.text(9, 31.6, "Untrusted: model output", ha="center", fontsize=6, color="0.25")
box(2, 21, 14, 7.5, "LLM agent\n(finance / support /\nsales)")
box(2, 9, 14, 7.5, "Structured\nAgentActionProposal\n+ signed credential")
arrow(9, 21, 9, 16.5)

# Gateway
ax.add_patch(FancyBboxPatch((20.5, 6), 37, 27.5, boxstyle="round,pad=0.2,rounding_size=1", fc="white", ec="black", lw=1.0))
ax.text(39, 31.6, "Agent Gateway (deterministic)", ha="center", fontsize=6.6, fontweight="bold")
box(22.5, 15, 10, 9, "Identity &\nallow-list\n(HMAC/OIDC,\nreplay cache)")
box(34.5, 15, 10, 9, "Safety\nguardrail\n(pattern\nfilter)")
box(46.5, 15, 9.5, 9, "Versioned\npolicy\nprofile")
arrow(16.4, 12.75, 22.5, 19.5)
arrow(32.5, 19.5, 34.5, 19.5)
arrow(44.5, 19.5, 46.5, 19.5)
box(22.5, 7.5, 33.5, 4.5, "Any check fails  →  DENY (fail closed)", fill="0.92")

# Outcomes
box(61, 26, 15, 6, "ALLOW\n(below auto limit)", bold=True)
box(61, 16.5, 15, 6, "HOLD\n(needs a person)", bold=True)
box(61, 6.5, 15, 6, "DENY\n(above ceiling)", bold=True)
arrow(56, 21, 61, 29)
arrow(56, 19.5, 61, 19.5)
arrow(56, 18, 61, 9.5)

box(79, 16.5, 9, 6, "Memory Bank\n(paused\nworkflow)")
box(90.3, 16.5, 9.2, 6, "Human\napprover\n(console)")
arrow(76, 19.5, 79, 19.5)
arrow(88, 19.5, 90.3, 19.5)

box(83, 26, 14, 6, "Idempotent\nexecutor (worker)")
arrow(76, 29, 83, 29)
arrow(94.9, 22.5, 94.9, 26, "approve", lx=2.6, ly=-0.6)

box(83, 6.5, 14, 6, "Audit trail &\ntraces")
arrow(76, 9.5, 83, 9.5)
arrow(94.9, 16.5, 94.9, 12.5, "reject", lx=2.4, ly=-0.6)

fig.tight_layout(pad=0.1)
for ext in ("pdf", "svg"):
    fig.savefig(FIG / f"architecture.{ext}")
print("ok")
