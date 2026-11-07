"""P3: two more read-only measurements for ARGUMENT.md.

  boxes   slam_collect seeds 0..19: an axis-aligned box decomposition of the plane.
          Every rotated rectangle (obstacles grown by the robot's circumradius,
          named regions and targets shrunk to the zone where the robot overlaps
          them whatever its heading, i.e. grown by its inscribed half extent) is
          replaced by its bounding box; the plane is cut along every box edge
          (an arrangement grid); cells with equal signature are merged greedily
          into maximal rectangles. Prints cells, merged boxes, free boxes.
  corner  where move_corner ends from 200 random known start poses per seed
          (seeds 0..4): fraction of noise-free and noisy runs that end in the
          named corner region (the only way it returns an exact pose).
Writes out/boxes.json and out/corner.json.
"""
import copy
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p1_measure import OUT, R_IN, R_OUT, build  # noqa: E402
import tampura_environments.slam_collect.env as E  # noqa: E402
from tampura.structs import Action  # noqa: E402


def aabb(pose, shape, grow=0.0):
    c, s = abs(math.cos(pose.theta)), abs(math.sin(pose.theta))
    hx = (c * shape.width + s * shape.height) / 2 + grow
    hy = (s * shape.width + c * shape.height) / 2 + grow
    return (max(0.0, pose.x - hx), max(0.0, pose.y - hy), min(10.0, pose.x + hx), min(10.0, pose.y + hy))


def merge_rects(sig):
    """Greedy maximal rectangles over an arrangement grid of signatures."""
    nx, ny = sig.shape
    used = np.zeros_like(sig, dtype=bool)
    rects = []
    for i in range(nx):
        j = 0
        while j < ny:
            if used[i, j]:
                j += 1
                continue
            v = sig[i, j]
            k = j
            while k < ny and sig[i, k] == v and not used[i, k]:
                k += 1
            m = i + 1
            while m < nx and np.all(sig[m, j:k] == v) and not np.any(used[m, j:k]):
                m += 1
            used[i:m, j:k] = True
            rects.append((i, j, m, k, int(v)))
            j = k
    return rects


def mode_boxes():
    rows = []
    for seed in range(20):
        env, b0, store, config = build('slam_collect', seed)
        s = env.state
        named = list(s.regions) + list(s.targets)
        boxes = [aabb(r.pose, r.shape, R_IN) for r in named]
        obs = [aabb(o.pose, o.shape, R_OUT) for o in s.obstacles]
        xs = sorted({0.0, 10.0} | {b[0] for b in boxes + obs} | {b[2] for b in boxes + obs})
        ys = sorted({0.0, 10.0} | {b[1] for b in boxes + obs} | {b[3] for b in boxes + obs})
        nx, ny = len(xs) - 1, len(ys) - 1
        sig = np.zeros((nx, ny), dtype=np.int64)
        free = np.ones((nx, ny), dtype=bool)
        for i in range(nx):
            cx = (xs[i] + xs[i + 1]) / 2
            for j in range(ny):
                cy = (ys[j] + ys[j + 1]) / 2
                code = 0
                for k, b in enumerate(boxes):
                    if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                        code |= 1 << k
                for k, b in enumerate(obs):
                    if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                        code |= 1 << (len(boxes) + k)
                        free[i, j] = False
                sig[i, j] = code
        rects = merge_rects(sig)
        n_free = sum(1 for r in rects if not (r[4] >> len(boxes)))
        n_plain_free = sum(1 for r in rects if r[4] == 0)
        row = {'seed': seed, 'arrangement_cells': nx * ny, 'merged_boxes': len(rects),
               'free_boxes': n_free, 'plain_free_boxes': n_plain_free,
               'distinct_signatures': int(len(np.unique(sig)))}
        rows.append(row)
        print(row, flush=True)
    with open(os.path.join(OUT, 'boxes.json'), 'w') as f:
        json.dump(rows, f, indent=1)


def mode_corner():
    rows = []
    for seed in range(5):
        env, b0, store, config = build('slam_collect', seed)
        s = env.state
        rng = random.Random(seed)
        hit_free, hit_noisy, total = {}, {}, {}
        for _ in range(200):
            x, y, th = rng.uniform(0.3, 9.7), rng.uniform(0.3, 9.7), rng.uniform(-math.pi, math.pi)
            b = copy.deepcopy(b0)
            for p in b.particles:
                p.robot.pose = E.Pose(x, y, th)
            st = copy.deepcopy(s)
            st.robot.pose = E.Pose(x, y, th)
            for c in s.corners:
                prims = E.move_corner(Action('move_corner', [c.name]), b, store)
                _, o0 = E.generate_trajectory([copy.deepcopy(st)], prims, std=0.0)
                _, o1 = E.generate_trajectory([copy.deepcopy(st)], prims, std=E.ACTION_STD)
                total[c.name] = total.get(c.name, 0) + 1
                hit_free[c.name] = hit_free.get(c.name, 0) + int(c.name in o0[0].regions_in)
                hit_noisy[c.name] = hit_noisy.get(c.name, 0) + int(c.name in o1[0].regions_in)
        row = {'seed': seed, 'starts': 200,
               'noise_free_in_corner': hit_free, 'noisy_in_corner': hit_noisy}
        rows.append(row)
        print(row, flush=True)
    with open(os.path.join(OUT, 'corner.json'), 'w') as f:
        json.dump(rows, f, indent=1)


if __name__ == '__main__':
    {'boxes': mode_boxes, 'corner': mode_corner}[sys.argv[1]]()
