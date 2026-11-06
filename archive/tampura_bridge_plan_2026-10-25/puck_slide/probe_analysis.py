"""Analysis of probe_puck_physics_out.json (ARGUMENT.md 4).  Reads only that
file; imports nothing from either project.

Questions:
  A  does the launch speed depend on the effort only (not on the friction)?
  B  which slide model reproduces PyBullet's slide from the separation
     speed: pure Coulomb, or Coulomb plus a velocity drag (the multibody
     damping term, k1 v + k2 v^2, PyBullet's defaults 0.04 if they apply)?
  C  how well would the forward probe (effort 0.01 here) identify the
     combined friction mu_eff from (launch speed, slide distance)?
  D  the goal window seen from where the probe leaves the puck.
"""
import json
import math
import sys

import numpy as np

G = 9.8
SRC = sys.argv[1]
d = json.load(open(SRC))


def slide(v0, mu_eff, k1=0.0, k2=0.0, dt=1.0 / 2400.0):
    """Stopping distance under dv/dt = -(mu g + k1 v + k2 v^2)."""
    x, v = 0.0, v0
    while v > 0:
        a = mu_eff * G + k1 * v + k2 * v * v
        v_new = v - a * dt
        if v_new <= 0:
            x += v * v / (2 * a)
            break
        x += 0.5 * (v + v_new) * dt
        v = v_new
    return x


def invert(v0, d_slide, k1=0.0, k2=0.0):
    lo, hi = 1e-4, 0.2
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if slide(v0, mid, k1, k2) > d_slide:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


rows = [r for r in d["E1"] if not r["off_table"] and r.get("d_slide")]
print("A  launch speed by effort (in-bounds and off-table rows):")
by_e = {}
for r in d["E1"]:
    if r.get("sep_speed") is not None:
        by_e.setdefault(r["effort"], []).append((r["mu"], r["sep_speed"], r["ee_speed_max"]))
for e in sorted(by_e):
    sp = [s for _, s, _ in by_e[e]]
    ee = [x for _, _, x in by_e[e]]
    print(f"   effort {e:.3f}: v_sep mean {np.mean(sp):.4f} sd {np.std(sp):.4f} "
          f"(n={len(sp)}), tool-tip max {np.mean(ee):.4f}, v_sep/effort {np.mean(sp)/e:.1f}")

models = {"coulomb": (0.0, 0.0), "lin 0.0408": (0.0408, 0.0), "lin+quad 0.04": (0.04, 0.04)}
print("\nB  mu_eff recovered from (v_sep, d_slide) / (0.1 * mu_puck), per model:")
summary = {}
for name, (k1, k2) in models.items():
    ratios = []
    for r in rows:
        m = invert(r["sep_speed"], r["d_slide"], k1, k2)
        ratios.append(m / (0.1 * r["mu"]))
    ratios = np.array(ratios)
    summary[name] = ratios
    print(f"   {name:14s}: ratio mean {ratios.mean():.4f}, min {ratios.min():.4f}, "
          f"max {ratios.max():.4f}, rms error {np.sqrt(np.mean((ratios - 1) ** 2)):.4f} (n={len(ratios)})")

best = min(summary, key=lambda k: np.sqrt(np.mean((summary[k] - 1) ** 2)))
print(f"   best: {best}")
k1b, k2b = models[best]
print("   per row (best model): mu, effort, v_sep, d_slide, mu_eff_hat/(0.1 mu)")
for r in rows:
    m = invert(r["sep_speed"], r["d_slide"], k1b, k2b)
    print(f"     {r['mu']:.3f} {r['effort']:.3f} {r['sep_speed']:.4f} {r['d_slide']:.4f} {m/(0.1*r['mu']):.4f}")

print("\nC  forward probe at effort 0.01 (rows of E1):")
for r in [r for r in rows if abs(r["effort"] - 0.01) < 1e-9]:
    m = invert(r["sep_speed"], r["d_slide"], k1b, k2b)
    # sensitivity: 3 mm pose error, 2 % launch-speed error
    m_d = invert(r["sep_speed"], r["d_slide"] + 0.003, k1b, k2b)
    m_v = invert(r["sep_speed"] * 1.02, r["d_slide"], k1b, k2b)
    print(f"   mu {r['mu']:.3f}: x_final {r['x']:.4f}, mu_eff_hat {m:.5f} (truth 0.1 mu = {0.1*r['mu']:.5f}), "
          f"rel err {m/(0.1*r['mu'])-1:+.3%}; +3 mm -> {m_d/m-1:+.2%}, +2 % speed -> {m_v/m-1:+.2%}")

print("\nD  goal window from the probe's end poses (centre must end in [1.19, 1.40]):")
for r in [r for r in rows if abs(r["effort"] - 0.01) < 1e-9]:
    lo, hi = 1.19 - r["x"], 1.40 - r["x"]
    print(f"   from x {r['x']:.3f}: slide window [{lo:.3f}, {hi:.3f}] m, ratio {hi/lo:.3f} "
          f"(a shot aimed at the window's geometric mean tolerates mu_eff within x/{math.sqrt(hi/lo):.3f})")
lo, hi = 1.19 - 0.39, 1.40 - 0.39
print(f"   from the start x 0.390: [{lo:.3f}, {hi:.3f}] m, ratio {hi/lo:.3f}, tolerance x/{math.sqrt(hi/lo):.3f}")

print("\nE  their 5-trial correction with an exact friction (E4):")
for r in d["E4"]:
    print(f"   mu {r['mu']:.3f}: trial x " + ", ".join(f"{t['x']:.3f}" for t in r["trials"])
          + f"; last in goal {r['last_trial_in_goal']}; first trial off table {r['trials'][0]['off_table']}; "
          f"returned effort {r['returned_effort']:.5f} vs last used {r['trials'][-1]['effort']:.5f}, "
          f"replay x {r['replay_at_returned_effort_x']:.3f} vs last x {r['last_trial_x']:.3f}")

print("\nF  ghost load (E2): real puck final x with ghosts minus without:")
e2 = d["E2"]
for e in sorted({r["effort"] for r in e2}):
    a = [r for r in e2 if r["effort"] == e and not r["ghosts"]][0]
    b = [r for r in e2 if r["effort"] == e and r["ghosts"]][0]
    print(f"   effort {e:.3f}: dx {1000*(b['x']-a['x']):+.1f} mm, dy {1000*(b['y']-a['y']):+.1f} mm, "
          f"off-table {a['off_table']}/{b['off_table']}, tool-tip max {a['ee_speed_max']:.4f}/{b['ee_speed_max']:.4f}")

print("\nG  E1 rows in goal, short, off table, by friction (single trial from the start):")
for mu in d["frictions"]:
    rr = [r for r in d["E1"] if r["mu"] == mu]
    print(f"   mu {mu:.3f}: " + ", ".join(
        f"e{r['effort']:.3f}:{'GOAL' if r['in_goal'] else ('OFF' if r['off_table'] else 'x%.2f' % r['x'])}"
        for r in rr))
print(f"\nrest pose after 480 steps: {d['rest_pose_after_480_steps'][0]}")
print(f"time step {d['time_step']}, solver iterations {d['solver_iterations']}, "
      f"robot link lateral friction {d['robot_link_lateral_friction']}")
