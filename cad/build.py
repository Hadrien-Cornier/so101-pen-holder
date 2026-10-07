"""Build the SO-101 pen sleeve and check it against the stock gripper.

    python cad/build.py            # writes print/*.stl and results/checks.json, exits 1 if a check fails

Units are mm. Every coordinate is in the frame of the `gripper` body of the SO-101 MuJoCo model
(MuJoCo Menagerie `robotstudio_so101`): z is the wrist_roll axis and the fingers point to -z.

The printed parts:
  sleeve.stl         slides up onto the end of the stock fixed finger and holds the pen in two V clamps
  thumbscrew.stl     print 3: two press the pen into the V clamps, one presses the side of the finger
  thread_coupon.stl  a short piece of the M8 thread; print it first to test the screw fit on your printer

The pen leans 20 deg out of the open side of the jaws, so that it is vertical when the arm draws.
Each clamp is a ring with a 90 deg V on the gripper side and a printed M8 thread on the other side.
A pen of radius r sits with its axis sqrt(2) (R_REF - r) toward the V, so the tip position is known
for every round pen from 8 to 13 mm.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import manifold3d as m3d
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
MESHES = ROOT / "cad" / "meshes"

# ---------------------------------------------------------------------------------------------- pen layout
TILT = math.radians(20.0)  # the pen leans out of the open side of the jaws
U = np.array([0.0, -math.sin(TILT), math.cos(TILT)])  # pen axis, tip to top
EX = np.array([1.0, 0.0, 0.0])
EY = np.array([0.0, math.cos(TILT), math.sin(TILT)])  # toward the V (toward the gripper)
TIP = np.array([0.0, -6.0, -120.0])  # contact tip of a 13 mm pen
R_REF = 6.5  # the V is tangent to a 13 mm pen; a thinner pen sits deeper
R_CLEAR = 6.8  # bore radius on the screw side
R_MIN = 4.0  # 8 mm pen
CLAMPS = (26.0, 69.0)  # clamp centres above the tip, along the pen
CLAMP_LEN = 10.0
WALL = 3.0  # ring wall
V_BACK = 4.0  # material behind the V
BEAM_Y = (R_REF * math.sqrt(2) + 1.0, R_REF * math.sqrt(2) + 8.0)  # spine on the gripper side of the pen
BEAM_X = 6.0
FOAM = 3.0  # the arm presses the tip this far into a soft pad under the paper
CLEAR = 5.0  # every other point stays this far above the paper

# ---------------------------------------------------------------------------------------------- printed thread
M8_D, M8_P = 8.0, 1.25
FIT_THREAD = 0.15  # each side moved by this much: 0.3 mm radial play. Tune it with thread_coupon.stl.
BOSS_X, BOSS_T = 7.0, 14.0  # thread boss on the outside of each ring
BOSS_Y_OUT = R_CLEAR + 8.0
HOLE_W0 = R_CLEAR - 2.5  # the hole thread starts this far from the pen axis (inside the bore)
SCREW_L, HEAD_D, HEAD_H = 16.0, 16.0, 6.0  # thumbscrew: thread length, knurled head

# ---------------------------------------------------------------------------------------------- finger sleeve
CHEEK_TOP = -58.0  # the sleeve covers the finger from here to its end (z = -104.4)
CHEEK_Y = 13.5  # largest half width of the sleeve
CHEEK_WALL = 2.6  # sleeve wall outside each finger flank
CHEEK_OFF = 3.5  # sleeve wall behind the outer face of the finger
X_PEN_CLEAR = -6.9  # the sleeve stops here, so the pen stays free
FIT_FINGER = 0.15  # pocket clearance around the finger
PINCH = (-19.1, -73.3)  # (x, z) of the side screw: between the 3rd and 4th finger holes
PINCH_BOSS_LEN = 10.0
PATCH = ((-17.0, -3.0), (-13.0, -10.0), (-95.0, -60.0))  # where the web meets the -y side of the sleeve

# ---------------------------------------------------------------------------------------------- print model (mass)
RHO, PERIMETER, INFILL = 1.24, 1.6, 0.40  # g/cm3 (PLA; PETG 1.27), 4 walls x 0.4 mm, 40 % infill


# ---------------------------------------------------------------------------------------------- helpers
def to_manifold(mesh: trimesh.Trimesh) -> m3d.Manifold:
    return m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                                 tri_verts=np.asarray(mesh.faces, np.uint32)))


def to_trimesh(m: m3d.Manifold) -> trimesh.Trimesh:
    g = m.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=True)


def moved(m: m3d.Manifold, A: np.ndarray) -> m3d.Manifold:
    """Apply a 4 x 4 rigid transform."""
    return m.transform(np.asarray(A, float)[:3, :4])


def overlap(a: m3d.Manifold, b: m3d.Manifold) -> float:
    return (a ^ b).volume()


def box(x, y, z) -> m3d.Manifold:
    return m3d.Manifold.cube((x[1] - x[0], y[1] - y[0], z[1] - z[0])).translate((x[0], y[0], z[0]))


def prism(pts, height, A) -> m3d.Manifold:
    """Extrude a 2D polygon (any winding) by `height` along its local z, then place it with the 4 x 4 transform A."""
    cs = m3d.CrossSection([np.asarray(pts, float).tolist()], m3d.FillRule.EvenOdd)
    return moved(m3d.Manifold.extrude(cs, height), A)


def print_mass(tm: trimesh.Trimesh) -> float:
    v = tm.volume / 1000.0
    shell = min(v, tm.area / 100.0 * PERIMETER / 10.0)
    return RHO * (shell + INFILL * (v - shell))


def pen_frame() -> np.ndarray:
    A = np.eye(4)
    A[:3, 0], A[:3, 1], A[:3, 2], A[:3, 3] = EX, EY, U, TIP
    return A


def quat_T(pos_m, quat_wxyz) -> np.ndarray:
    q = np.array(quat_wxyz, float)
    q /= np.linalg.norm(q)
    return trimesh.transformations.translation_matrix(np.array(pos_m) * 1000) @ trimesh.transformations.quaternion_matrix(q)


def gripper(jaw_q: float = 0.0) -> dict:
    """The stock gripper meshes in the gripper frame (poses from so101.xml). jaw_q > 0 opens the jaw."""
    def load(name, A):
        m = trimesh.load(MESHES / name)
        m.apply_scale(1000)
        m.apply_transform(A)
        return m
    R = trimesh.transformations.rotation_matrix(jaw_q, [0, 0, 1])
    return {
        "fixed_jaw": load("wrist_roll_follower_so101_v1.stl", quat_T([0, -0.000218, 0.00095], [0, 1, 0, 0])),
        "jaw_servo": load("sts3215_03a_v1.stl", quat_T([0.0077, 0.0001, -0.0234], [1, -1, 0, 0])),
        "moving_jaw": load("moving_jaw_so101_v1.stl",
                           quat_T([0.0202, 0.0188, -0.0234], [1, 1, 0, 0]) @ R @ quat_T([0, 0, 0.0189], [1, 0, 0, 0])),
    }


def jaw_rest_angle(part: m3d.Manifold):
    """Close the moving jaw from open until it touches `part`; return that angle (rad)."""
    for q in np.arange(0.6, -0.2, -0.005):
        if overlap(part, to_manifold(gripper(q)["moving_jaw"])) > 0.05:
            return round(float(q + 0.005), 3)
    return None


# ---------------------------------------------------------------------------------------------- finger
def finger_profile(fj: trimesh.Trimesh):
    """Along z: the x of the outer face of the finger and its half width |y|, from mesh sections."""
    zs = np.arange(CHEEK_TOP, -104.0, -2.0)
    b = np.array([fj.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1]).bounds for z in zs])
    return zs, b[:, 0, 0], np.max(np.abs(b[:, :, 1]), axis=1)


def finger_pocket(fj: trimesh.Trimesh) -> m3d.Manifold:
    """The finger grown by the fit clearance and swept toward +z: the sleeve slides up onto the finger from below.
    The finger gets narrower toward its end, so the pocket still fits its flanks and its outer face (a wedge)."""
    base, c = to_manifold(fj), FIT_FINGER
    copies = [base.translate((dx, dy, float(dz))) for dx in (-c, 0.0, c) for dy in (-c, 0.0, c) for dz in np.arange(-c, 60.0, 1.0)]
    return m3d.Manifold.batch_boolean(copies, m3d.OpType.Add)


def cheeks(fj: trimesh.Trimesh, z_low: float) -> m3d.Manifold:
    """The sleeve body around the finger: a side profile (x, z) cut by a front profile (y, z) that follows the
    finger flanks with CHEEK_WALL of material."""
    zs, xs, hw = finger_profile(fj)
    keep = zs >= z_low
    zs, xs, hw = zs[keep], xs[keep], hw[keep]
    side = [(X_PEN_CLEAR, CHEEK_TOP), (X_PEN_CLEAR, z_low), (xs[-1] - CHEEK_OFF, z_low)]
    side += [(x - CHEEK_OFF, z) for z, x in zip(zs[::-1], xs[::-1])]
    # (u, v, w) -> (x = u, y = CHEEK_Y - w, z = v): the profile in the x-z plane, |y| <= CHEEK_Y
    A_side = np.array([[1, 0, 0, 0], [0, 0, -1, CHEEK_Y], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    yz = [(min(CHEEK_Y, h + CHEEK_WALL), z) for z, h in zip(zs, hw)]
    yz = yz + [(yz[-1][0], z_low - 0.01)]
    front = [(y, z) for y, z in yz] + [(-y, z) for y, z in yz[::-1]]
    front = [pt for i, pt in enumerate(front) if i == 0 or np.hypot(pt[0] - front[i - 1][0], pt[1] - front[i - 1][1]) > 1e-3]
    # (u, v, w) -> (x = w - 60, y = u, z = v): the profile in the y-z plane, |x| <= 60
    A_front = np.array([[0, 0, 1, -60], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)
    return prism(side, 2 * CHEEK_Y, A_side) ^ prism(front, 120.0, A_front)


# ---------------------------------------------------------------------------------------------- clamps and thread
def clip(poly, n, d):
    """Keep the part of polygon `poly` (N x 2) where n . p <= d (Sutherland-Hodgman)."""
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        fa, fb = n @ a - d, n @ b - d
        if fa <= 0:
            out.append(a)
        if fa * fb < 0:
            out.append(a + (b - a) * fa / (fa - fb))
    return np.array(out)


def v_bore(t0, t1) -> m3d.Manifold:
    """The free space of every pen from 8 to 13 mm, in the pen frame: a 90 deg V on the +y side (faces tangent to
    R_REF), open to its vertex so that a thin pen can sit deep in it, and a circle R_CLEAR on the screw side."""
    a = np.linspace(0, 2 * math.pi, 128, endpoint=False)
    wedge = np.c_[14 * np.cos(a), 14 * np.sin(a)]
    for ang in (math.radians(45), math.radians(135)):
        wedge = clip(wedge, np.array([math.cos(ang), math.sin(ang)]), R_REF)
    circle = np.c_[R_CLEAR * np.cos(a), R_CLEAR * np.sin(a)]
    upper = np.array([[-R_CLEAR, 0], [R_CLEAR, 0], [R_CLEAR, 14], [-R_CLEAR, 14]], float)  # no wider than the bore: a 3 mm ring wall
    cs = m3d.CrossSection([wedge.tolist()]) ^ (m3d.CrossSection([circle.tolist()]) + m3d.CrossSection([upper.tolist()]))
    return m3d.Manifold.extrude(cs, t1 - t0).translate((0, 0, t0))


def thread(length, offset, n=144) -> m3d.Manifold:
    """M8 x 1.25 right-hand thread along +z from z = 0, radius moved by `offset` (- for the screw, + for the hole).
    A twisted extrusion of the section r(theta): the section of a helix is the axial profile mapped onto the angle."""
    P, R = M8_P, M8_D / 2
    h = 5 * 0.866 * P / 8  # flank height of the ISO basic profile

    def prof(s):  # s in [0, P): crest P/8 at R, flank, root P/4 at R - h, flank
        s = s % P
        if s < P / 8:
            return R
        if s < P / 8 + 5 * P / 16:
            return R - h * (s - P / 8) / (5 * P / 16)
        if s < P / 8 + 5 * P / 16 + P / 4:
            return R - h
        return R - h + h * (s - (P / 8 + 5 * P / 16 + P / 4)) / (5 * P / 16)

    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    r = np.array([prof(-t / (2 * math.pi) * P) for t in a]) + offset
    cs = m3d.CrossSection([np.c_[r * np.cos(a), r * np.sin(a)].tolist()])
    turns = length / P
    return m3d.Manifold.extrude(cs, length, n_divisions=int(turns * 24), twist_degrees=360.0 * turns)


def thread_hole(y0, y1, tc) -> m3d.Manifold:
    """Internal thread cutter along -y from y0 to y1 (y1 < y0) at pen height tc, pen frame."""
    return thread(y0 - y1, FIT_THREAD).rotate((90, 0, 0)).translate((0, y0, tc))


def thumbscrew() -> m3d.Manifold:
    """Printed thumbscrew, axis +z: thread from z = 0 (tip) to SCREW_L, knurled head above. Print it head down."""
    sh = thread(SCREW_L, -FIT_THREAD) - m3d.Manifold.cylinder(0.6, 6, circular_segments=48).translate((0, 0, -0.01)) \
        + m3d.Manifold.cylinder(0.6, M8_D / 2 - 1.0, M8_D / 2 - 0.4, circular_segments=48)  # 0.6 mm tip chamfer
    head = m3d.Manifold.cylinder(HEAD_H, HEAD_D / 2, circular_segments=96).translate((0, 0, SCREW_L))
    for k in range(12):  # grip flutes
        a = 2 * math.pi * k / 12
        head -= m3d.Manifold.cylinder(HEAD_H + 2, 1.3, circular_segments=24).translate(
            (HEAD_D / 2 * math.cos(a), HEAD_D / 2 * math.sin(a), SCREW_L - 1))
    neck = m3d.Manifold.cylinder(1.0, M8_D / 2 - 0.2, HEAD_D / 2 - 1, circular_segments=48).translate((0, 0, SCREW_L - 1.0))
    return sh + head + neck


def boss(tc) -> m3d.Manifold:
    return m3d.Manifold.cube((2 * BOSS_X, BOSS_Y_OUT - R_CLEAR + 2.0, BOSS_T)).translate((-BOSS_X, -BOSS_Y_OUT, tc - BOSS_T / 2))


def clamp(tc) -> m3d.Manifold:
    """One pen clamp in the pen frame: a ring with the V on the gripper side and a threaded boss on the other side."""
    t0 = tc - CLAMP_LEN / 2
    ring = m3d.Manifold.cylinder(CLAMP_LEN, R_CLEAR + WALL, circular_segments=64).translate((0, 0, t0))
    back = m3d.Manifold.cube((2 * (R_CLEAR + WALL) - 2, V_BACK + R_REF * math.sqrt(2), CLAMP_LEN)).translate(
        (-(R_CLEAR + WALL - 1), 0, t0))
    c = ring + back + boss(tc)
    c -= v_bore(t0 - 1, t0 + CLAMP_LEN + 1)
    return c - thread_hole(-HOLE_W0, -BOSS_Y_OUT - 1.0, tc)


def pen_screw(r, tc) -> m3d.Manifold:
    """A pen thumbscrew turned in until its tip touches a pen of radius r, pen frame, its thread in phase with the hole."""
    tip_y = math.sqrt(2) * (R_REF - r) - r
    d = -tip_y - HOLE_W0
    return thumbscrew().rotate((0, 0, 360.0 * d / M8_P)).rotate((90, 0, 0)).translate((0, tip_y, tc))


def pinch_frame(hw) -> np.ndarray:
    """Pose of the side thumbscrew: tip on the +y flank of the finger, head outward (+y)."""
    A = np.eye(4)
    A[:3, :3] = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)  # local z -> +y, local y -> -z
    A[:3, 3] = (PINCH[0], hw, PINCH[1])
    return A


def coupon() -> m3d.Manifold:
    """Thread test print: one boss with the same thread."""
    return boss(0.0) - thread_hole(-HOLE_W0, -BOSS_Y_OUT - 1.0, 0.0)


# ---------------------------------------------------------------------------------------------- the sleeve
def sleeve(fj: trimesh.Trimesh):
    zs, _, hwv = finger_profile(fj)
    hw = float(np.interp(-PINCH[1], -zs, hwv))  # finger half width at the side screw
    M = pen_frame()
    local = clamp(CLAMPS[0]) + clamp(CLAMPS[1])
    local += box((-BEAM_X, BEAM_X), BEAM_Y, (CLAMPS[0] - CLAMP_LEN / 2, CLAMPS[1] + CLAMP_LEN / 2))
    spine = moved(box((-BEAM_X, BEAM_X), BEAM_Y, CLAMPS), M)
    web = m3d.Manifold.batch_hull([box(*PATCH), spine])
    s = moved(local, M) + web + cheeks(fj, -100.0)
    s += box((PINCH[0] - BOSS_X, PINCH[0] + BOSS_X), (hw + FIT_FINGER, hw + FIT_FINGER + CHEEK_WALL + PINCH_BOSS_LEN),
             (PINCH[1] - BOSS_X, PINCH[1] + BOSS_X))
    s -= moved(v_bore(-5, 160), M)
    s -= finger_pocket(fj)
    F = pinch_frame(hw)
    s -= moved(thread(FIT_FINGER + CHEEK_WALL + PINCH_BOSS_LEN + 1.0, FIT_THREAD).translate((0, 0, -0.5)), F)
    s = to_manifold(to_trimesh(s)).simplify(0.01)  # drop slivers of the booleans
    return s, F, hw


def pen_cyl(r, length, shift) -> m3d.Manifold:
    return m3d.Manifold.cylinder(length, r, circular_segments=64).translate((0, shift, 0))


PENS = (("Wacom Pen 4K (LP1100K)", 143.2, 12.0), ("BIC 4-Colour", 145.0, 11.6), ("Pilot V5", 122.0, 10.6),
        ("13 mm pen", 145.0, 13.0), ("10 mm pen", 145.0, 10.0), ("8 mm pen", 145.0, 8.0))


def main() -> int:
    (ROOT / "print").mkdir(exist_ok=True)
    (ROOT / "results").mkdir(exist_ok=True)
    g = gripper()
    sl, F, hw = sleeve(g["fixed_jaw"])
    fj, servo = to_manifold(g["fixed_jaw"]), to_manifold(g["jaw_servo"])
    chk = {"sleeve_vs_fixed_finger_mm3": overlap(sl, fj), "sleeve_vs_jaw_servo_mm3": overlap(sl, servo)}
    q_rest = jaw_rest_angle(sl)
    chk["moving_jaw_stop_rad"] = q_rest
    for q in (0.3, 0.6, 1.0, 1.4):
        chk[f"sleeve_vs_moving_jaw_at_{q}_rad_mm3"] = overlap(sl, to_manifold(gripper(q)["moving_jaw"]))
    jaw_open = to_manifold(gripper(1.0)["moving_jaw"])
    chk["fitting_path_vs_open_moving_jaw_mm3"] = max(overlap(sl.translate((0, 0, -float(dz))), jaw_open) for dz in (2, 5, 10, 20, 40, 60))
    chk["fitting_path_vs_fixed_jaw_mm3"] = max(overlap(sl.translate((0, 0, -float(dz))), fj) for dz in (2, 5, 10, 20, 40))
    obs = [fj, servo, to_manifold(gripper(q_rest or 0.0)["moving_jaw"])]
    M = pen_frame()
    pens = []
    for name, length, D in PENS:
        r = D / 2
        shift = math.sqrt(2) * (R_REF - r)
        cyl = moved(pen_cyl(r, length, shift), M)
        chk[f"pen {name} vs sleeve_mm3"] = overlap(cyl, sl)
        chk[f"pen {name} vs gripper_mm3"] = sum(overlap(cyl, o) for o in obs)
        tip = M[:3, :3] @ np.array([0, shift, 0]) + TIP
        pens.append({"pen": name, "diameter_mm": D, "axis_shift_toward_gripper_mm": round(shift, 2),
                     "tip_mm": np.round(tip, 2).tolist(), "tip_off_wrist_roll_axis_mm": round(float(np.hypot(*tip[:2])), 2)})
    for r in (R_MIN, R_REF):
        for tc in CLAMPS:
            sc = moved(pen_screw(r, tc), M)
            chk[f"pen screw, {2 * r:.0f} mm pen, clamp at {tc:.0f} mm, vs sleeve_mm3"] = overlap(sc, sl)
            chk[f"pen screw, {2 * r:.0f} mm pen, clamp at {tc:.0f} mm, vs gripper_mm3"] = sum(overlap(sc, o) for o in obs)
    side = moved(thumbscrew().rotate((0, 0, 360.0 * 0.5 / M8_P)), F)
    chk["side screw vs sleeve_mm3"] = overlap(side, sl)
    chk["side screw vs jaw servo and moving jaw_mm3"] = overlap(side, servo) + overlap(side, obs[2])
    head_gap = hw + SCREW_L - (hw + FIT_FINGER + CHEEK_WALL + PINCH_BOSS_LEN)
    pen_head_gap = -BOSS_Y_OUT - ((math.sqrt(2) * (R_REF - R_MIN) - R_MIN) - SCREW_L)
    chk["side screw head gap to its boss_mm"] = head_gap
    chk["pen screw head gap to its boss, 8 mm pen_mm"] = pen_head_gap
    tm = to_trimesh(sl)
    low = float(((tm.vertices - TIP) @ U).min())
    chk["lowest sleeve point above the tip_mm"] = low
    chk = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in chk.items()}
    bad = [k for k, v in chk.items() if k.endswith("_mm3") and v > 0.5]
    bad += [k for k in ("side screw head gap to its boss_mm", "pen screw head gap to its boss, 8 mm pen_mm") if chk[k] < 0.5]
    bad += ["moving_jaw_stop_rad"] if q_rest is None or q_rest > 0.05 else []
    bad += ["lowest sleeve point above the tip_mm"] if low < FOAM + CLEAR else []
    bad += ["sleeve watertight"] if not tm.is_watertight else []
    st = to_trimesh(thumbscrew())
    tm.export(ROOT / "print" / "sleeve.stl")
    st.export(ROOT / "print" / "thumbscrew.stl")
    to_trimesh(coupon()).export(ROOT / "print" / "thread_coupon.stl")
    rep = {"frame": "SO-101 MuJoCo `gripper` body frame, mm", "pen_axis_tip_to_top": np.round(U, 4).tolist(),
           "clamps_mm_above_tip": CLAMPS, "side_screw_xz_mm": PINCH,
           "mass_g_est": {"sleeve": round(print_mass(tm), 1), "thumbscrew_each": round(print_mass(st), 1)},
           "sleeve_bbox_mm": np.round(tm.extents, 1).tolist(), "pens": pens, "checks": chk, "failed": bad}
    (ROOT / "results" / "checks.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps({"mass_g_est": rep["mass_g_est"], "failed": bad}, indent=1))
    print("PASS" if not bad else "FAIL")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
