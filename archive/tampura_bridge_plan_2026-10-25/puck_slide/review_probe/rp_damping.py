"""Review probe (REVIEW.md): is PyBullet's default velocity damping the law
ARGUMENT.md 4.1 uses, dv/dt = -(k1 v + k2 v^2) with k1 = k2 = 0.04 (marked
UNVERIFIED there as "my reading of PyBullet's multibody defaults")?

A puck-sized cylinder (their create_puck, mass 1) floats with gravity 0 and no
contact; it is given a speed along x and the speed is logged every step.  The
decay is then fitted by least squares to a = -(k1 v + k2 v^2).  Own world only.

Run: same line as the author's probes.  Writes only the JSON path given.
"""
import json
import sys

import numpy as np
import pybullet as p
import pybullet_utils.bullet_client as bc

import tampura_environments.puck_slide.env as ps

OUT = sys.argv[1]
c = bc.BulletClient(connection_mode=p.DIRECT)
c.setGravity(0, 0, 0)
puck = ps.create_puck(0.1, c)
dt = c.getPhysicsEngineParameters()["fixedTimeStep"]
res = {"dt": dt, "runs": []}
allv, alla = [], []
for v0 in (0.1, 0.2, 0.4, 0.7, 1.0):
    c.resetBasePositionAndOrientation(puck, [0, 0, 1.0], [0, 0, 0, 1])
    c.resetBaseVelocity(puck, [v0, 0, 0], [0, 0, 0])
    vs = [v0]
    for _ in range(960):
        c.stepSimulation()
        vs.append(c.getBaseVelocity(puck)[0][0])
    vs = np.array(vs)
    a = np.diff(vs) / dt
    vm = vs[:-1]
    allv.append(vm)
    alla.append(a)
    # per run, the instantaneous ratio -a / v at the start
    res["runs"].append(dict(v0=v0, v_after_4s=float(vs[-1]),
                            decel_over_v_first=float(-a[0] / vm[0])))
v = np.concatenate(allv)
a = np.concatenate(alla)
A = np.stack([v, v * v], axis=1)
k, *_ = np.linalg.lstsq(A, -a, rcond=None)
res["fit_k1"], res["fit_k2"] = float(k[0]), float(k[1])
pred = A @ np.array([0.04, 0.04])
res["max_rel_err_of_0.04_0.04"] = float(np.max(np.abs(pred - (-a)) / np.abs(a)))
print(json.dumps(res, indent=1))
with open(OUT, "w") as f:
    json.dump(res, f, indent=1)
