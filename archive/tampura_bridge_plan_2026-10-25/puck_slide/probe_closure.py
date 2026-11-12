"""Arithmetic for ARGUMENT.md 4.3 (2026-11-06), no simulation: the exact
literal of 2.3 with the damped slide law (probe_slide_track.slide, closed
form).  For a puck resting at x before the shot, the true effective friction
mu, a shot launch error e and a slide-law error m, the largest relative
half-width b of the interval [mu / (1 + b), mu / (1 - b)] for which
(friction_known o) holds, and the launch speed the shot then needs.
Window: the free-slide centre window [1.19, 1.40] (ARGUMENT 2.3), measured
from x (the separation offset of the shot is left to the calibration).
Run with the probes' run line (it imports probe_slide_track, which imports
their module); writes only stdout.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_slide_track as pst  # noqa: E402

W_NEAR_X, W_FAR_X = 1.19, 1.40


def dist(v, mu):
    return float(pst.slide(1e3, v, mu))


def v_for(d, mu):
    lo, hi = 1e-3, 3.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if dist(mid, mu) < d:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def literal(lo_mu, hi_mu, e, m, x):
    wn, wf = W_NEAR_X - x, W_FAR_X - x
    v_min = v_for(wn / (1 - m), hi_mu) / (1 - e)
    return dist(v_min * (1 + e), lo_mu) * (1 + m) <= wf, v_min


def b_max(mu, e, m, x):
    ok0, _ = literal(mu, mu, e, m, x)
    if not ok0:
        return 0.0, None
    lo, hi = 0.0, 0.6
    for _ in range(60):
        b = 0.5 * (lo + hi)
        ok, _v = literal(mu / (1 + b), mu / (1 - b), e, m, x)
        if ok:
            lo = b
        else:
            hi = b
    _ok, v = literal(mu / (1 + lo), mu / (1 - lo), e, m, x)
    return lo, v


def main():
    print("x_rest mu_eff e m -> b_max (largest interval half-width), v_shot (m/s)")
    for x in (0.39, 0.53, 0.60, 0.67, 0.77):
        for mu in (0.005, 0.010, 0.015):
            for e in (0.01, 0.02, 0.03):
                for m in (0.003, 0.010, 0.023, 0.026):
                    b, v = b_max(mu, e, m, x)
                    vs = f"{v:.3f}" if v else "none"
                    print(f"CL x={x:.2f} mu_eff={mu:.3f} e={e:.2f} m={m:.3f} b_max={b:.4f} v_shot={vs}")
    for x in (0.39, 0.53, 0.60, 0.67, 0.77):
        for mu in (0.005, 0.010, 0.015):
            v = v_for(0.5 * (W_NEAR_X + W_FAR_X) - x, mu)
            print(f"VC x={x:.2f} mu_eff={mu:.3f} v_to_window_centre={v:.3f}")


if __name__ == "__main__":
    main()
