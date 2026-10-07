"""Draw the section of one pen clamp from the real CAD geometry, with a 13 mm and an 8 mm pen.

    python cad/figure_clamp_section.py      # writes images/clamp-section.png (needs matplotlib)
"""
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Polygon, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as b  # noqa: E402

TC = 69.0  # the upper clamp, in the pen frame (z = along the pen)


def section():
    """The polygons of the clamp section at its centre plane, in the pen frame (x across, y toward the V)."""
    return [np.asarray(p) for p in b.clamp(TC).slice(TC).to_polygons()]


def main():
    polys = section()
    fig, axs = plt.subplots(1, 2, figsize=(13, 7.2), dpi=120)
    for ax, D in zip(axs, (13.0, 8.0)):
        r = D / 2
        shift = math.sqrt(2) * (b.R_REF - r)
        # the clamp: outer outlines filled, holes (the bore and the thread) cleared by the even-odd rule
        verts, codes = [], []
        for p in polys:
            verts += p.tolist() + [p[0].tolist()]
            codes += [1] + [2] * (len(p) - 1) + [79]
        from matplotlib.path import Path as MPath
        from matplotlib.patches import PathPatch
        ax.add_patch(PathPatch(MPath(verts, codes), fc="#bbdefb", ec="#1565c0", lw=1.4))
        # the pen and its two contact lines with the V
        ax.add_patch(Circle((0, shift), r, fc="#90a4ae", ec="#263238", lw=2))
        ax.plot(0, shift, "+", color="#263238", ms=12, mew=2)
        ax.plot(0, 0, "+", color="#c62828", ms=12, mew=2)
        for sgn in (-1, 1):
            ax.plot(sgn * r / math.sqrt(2), shift + r / math.sqrt(2), "o", color="#c62828", ms=9)
        # the thumbscrew, turned in until it touches the pen
        tip = shift - r
        ax.add_patch(Rectangle((-b.M8_D / 2 + 0.15, tip - b.SCREW_L), b.M8_D - 0.3, b.SCREW_L, fc="#ffcc80", ec="#e65100", lw=1.4, alpha=0.9))
        ax.add_patch(Rectangle((-b.HEAD_D / 2, tip - b.SCREW_L - b.HEAD_H), b.HEAD_D, b.HEAD_H, fc="#ffb74d", ec="#e65100", lw=1.4))
        ax.annotate("", xy=(0, tip + 0.3), xytext=(0, tip - 5), arrowprops=dict(arrowstyle="-|>", color="#bf360c", lw=3))
        ax.text(b.HEAD_D / 2 + 0.8, tip - b.SCREW_L - b.HEAD_H / 2, "printed M8\nthumbscrew", va="center", fontsize=11)
        ax.text(9.8, 15.5, "V on the gripper side", fontsize=11, color="#0d47a1")
        ax.text(-16.5, -1.0, "3 mm\nring wall", fontsize=10, color="#0d47a1")
        ax.set_title(f"{D:.0f} mm pen: its axis moves {shift:.1f} mm toward the V", fontsize=13)
        ax.set_xlim(-18, 18); ax.set_ylim(tip - b.SCREW_L - b.HEAD_H - 1.5, 19)
        ax.set_aspect("equal"); ax.axis("off")
    fig.suptitle("Section of one pen clamp (true CAD geometry). The screw pushes the pen into the 90° V, so the pen touches the V on two lines (red dots).\n"
                 "A thinner pen sits deeper in the V: its axis moves √2 × (6.5 mm − r) toward the gripper. Red cross: the axis of a 13 mm pen.",
                 fontsize=11.5)
    out = Path(__file__).resolve().parents[1] / "images" / "clamp-section.png"
    fig.savefig(out, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
