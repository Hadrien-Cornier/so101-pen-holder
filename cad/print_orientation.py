"""Check the print orientation of the sleeve: which faces need support, and where the supports stand.

    python cad/build.py               # first: writes results/sleeve_in_gripper_frame.stl
    python cad/print_orientation.py   # writes results/print_orientation.json

For 8 candidate orientations, the script adds up the area of the faces that face down more than 45 deg from
vertical (a common slicer limit for supports), by feature: the V faces, the screw side of the bores, the thread
holes, the finger pocket and the outside. For the chosen orientation (build.PRINT_UP), it traces a vertical
support column down from each outside face that needs support, and reports where the columns stand: on the bed,
or on the sleeve. It also checks that no column passes through the finger pocket.
"""
from __future__ import annotations

import json
import math

import numpy as np
import trimesh
from scipy.spatial import cKDTree

import build as b

LIMIT = math.radians(45.0)


def labels(sl: trimesh.Trimesh, fj: trimesh.Trimesh) -> np.ndarray:
    """Feature of each face of the sleeve (gripper frame)."""
    c, n = sl.triangles_center, sl.face_normals
    lab = np.full(len(c), "outside", dtype=object)
    rel = c - b.TIP
    t = rel @ b.U
    rad = rel - np.outer(t, b.U)
    dist = np.linalg.norm(rad, axis=1)
    for tc in b.CLAMPS:
        bore = (np.abs(t - tc) <= b.CLAMP_LEN / 2 + 0.2) & (dist < b.R_CLEAR + 0.6) & (np.abs(n @ b.U) < 0.5)
        v_side = rad @ b.EY > 0.5
        lab[bore & v_side] = "V faces"
        lab[bore & ~v_side] = "bore, screw side"
        r = c - (b.TIP + tc * b.U)  # the screw axis goes through the clamp centre, along -EY
        d_ax = np.linalg.norm(r - np.outer(r @ b.EY, b.EY), axis=1)
        sel = (d_ax < b.M8_D / 2 + 0.6) & (r @ b.EY < -(b.R_CLEAR - 0.6)) & (np.abs(n @ b.EY) < 0.9) & (lab == "outside")
        lab[sel] = "thread holes"
    px, pz = b.PINCH
    sel = (np.hypot(c[:, 0] - px, c[:, 2] - pz) < b.M8_D / 2 + 0.6) & (c[:, 1] > 0) & (np.abs(n[:, 1]) < 0.9) & (lab == "outside")
    lab[sel] = "thread holes"
    pts, _ = trimesh.sample.sample_surface_even(fj, 400000, radius=0.12, seed=1)
    d_f, _ = cKDTree(pts).query(c, distance_upper_bound=2.0)
    lab[(d_f < 0.8) & (lab == "outside")] = "finger pocket"
    return lab


def overhangs(sl, lab, up) -> dict:
    up = np.asarray(up, float) / np.linalg.norm(up)
    n, a = sl.face_normals, sl.area_faces
    h = sl.vertices[sl.faces] @ up
    bed = (h.max(axis=1) < h.min() + 0.3) & (n @ up < -0.99)
    down = (n @ up < -math.sin(LIMIT)) & ~bed
    return {"on_bed_mm2": round(float(a[bed].sum()), 1), "height_mm": round(float(h.max() - h.min()), 1),
            "needs_support_mm2": {k: round(float(a[down & (lab == k)].sum()), 1) for k in sorted(set(lab))}}


def support_columns(sl, lab, fj) -> dict:
    """Trace a column straight down from each outside face that needs support, in the print orientation."""
    A = b.print_pose(b.PRINT_UP)
    R = A[:3, :3]
    v = sl.vertices @ R.T
    z0 = v[:, 2].min()
    v[:, 2] -= z0
    pm = trimesh.Trimesh(v, sl.faces, process=False)
    n, c, a = pm.face_normals, pm.triangles_center, pm.area_faces
    bed = (v[pm.faces][:, :, 2].max(axis=1) < 0.3) & (n[:, 2] < -0.99)
    idx = np.where((n[:, 2] < -math.sin(LIMIT)) & (lab == "outside") & ~bed)[0]
    origins = c[idx] - [0, 0, 0.05]
    first = pm.ray.intersects_first(origins, np.tile([0, 0, -1.0], (len(idx), 1)))
    lands = np.where(first >= 0, lab[np.clip(first, 0, None)], "bed")
    through = np.zeros(len(idx), bool)
    for k, o in enumerate(origins):
        zs = np.arange(0.0, o[2], 1.0)
        if len(zs):
            g = (np.c_[np.full(len(zs), o[0]), np.full(len(zs), o[1]), zs] + [0, 0, z0]) @ R  # back to the gripper frame
            through[k] = (fj.contains(g) & (g[:, 2] < b.CHEEK_TOP)).any()  # inside the finger, within the sleeve
    return {"needs_support_mm2": round(float(a[idx].sum()), 1),
            "columns_land_on_mm2": {k: round(float(a[idx][lands == k].sum()), 1) for k in sorted(set(lands))},
            "columns_through_the_finger_pocket_mm2": round(float(a[idx][through].sum()), 1)}


def main() -> int:
    sl = trimesh.load(b.ROOT / "results" / "sleeve_in_gripper_frame.stl")
    fj = b.gripper()["fixed_jaw"]
    lab = labels(sl, fj)
    cands = {"pen axis vertical, tip end up (chosen)": b.PRINT_UP, "pen axis vertical, tip end down": b.U,
             "finger end down (as on the arm)": [0, 0, 1], "finger entry down": [0, 0, -1],
             "+x up": [1, 0, 0], "-x up": [-1, 0, 0], "+y up": [0, 1, 0], "-y up": [0, -1, 0]}
    rep = {"limit_deg_from_vertical": 45, "feature_area_mm2": {k: round(float(sl.area_faces[lab == k].sum()), 1) for k in sorted(set(lab))},
           "orientations": {k: overhangs(sl, lab, up) for k, up in cands.items()},
           "chosen_support_columns": support_columns(sl, lab, fj)}
    (b.ROOT / "results" / "print_orientation.json").write_text(json.dumps(rep, indent=2) + "\n")
    for k, r in rep["orientations"].items():
        print(f"{k:42s} bed {r['on_bed_mm2']:6.1f} mm2  support {r['needs_support_mm2']}")
    print("chosen orientation, support columns:", rep["chosen_support_columns"])
    ok = rep["orientations"]["pen axis vertical, tip end up (chosen)"]["needs_support_mm2"].get("V faces", 0) < 0.5 \
        and rep["chosen_support_columns"]["columns_through_the_finger_pocket_mm2"] < 0.5
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
