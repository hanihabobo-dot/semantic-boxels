"""P1: read-only measurements of TAMPURA's slam_collect for ARGUMENT.md.

Modes (python p1_measure.py <mode> [args]):
  maps      seeds 0..19 of slam_collect, slam_collect_simple, slam_collect_custom:
            map summary, distances, and region/boxel counts (out/maps.json)
  variance  Monte Carlo of their motion model: population variance of 20 particles
            after k primitive steps and P(known_pose) (out/variance.json)
  ctrl      their controllers on seeds 0..19: primitives per action and where
            move_corner really ends (out/ctrl.json)
  policies  scripted (not planned) action sequences through their env, their
            belief and their reward, seeds 0..19 x reps (out/policies.json)
  vis       seed 0 with their vis on for two actions: frames into out/vis_seed0

Builds every env exactly as run_planner.py does (random.seed, np.random.seed,
load_config, get_env, initialize). Nothing is written under /root/tampura-work;
save_dir is under /root/sc_probe unless the mode says otherwise.
"""
import copy
import json
import math
import os
import random
import sys
import time

import numpy as np
from tampura.config import config as tconfig
import tampura_environments  # noqa: F401
import tampura_environments.slam_collect.env as E
from tampura.structs import Action

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
os.makedirs(OUT, exist_ok=True)
GAMMA = 0.98
CTRL = {'move_pick': E.move_pick, 'move_place': E.move_place, 'move_to': E.move_to,
        'move_look': E.move_look, 'move_corner': E.move_corner}


def build(task, seed, vis=False, save_dir=None):
    save_dir = save_dir or f'/root/sc_probe/run_review_{task}_{seed}'  # REVIEW COPY: new folders only
    os.makedirs(save_dir, exist_ok=True)
    cfg = f'./env_configs/{task}.yml'
    config = tconfig.load_config(config_file=cfg, arg_dict={
        'config': cfg, 'global_seed': seed, 'vis': vis, 'save_dir': save_dir})
    random.seed(config['global_seed'])
    np.random.seed(config['global_seed'])
    env = tconfig.get_env(config['task'])(config=config)
    b0, store = env.initialize()
    import matplotlib.pyplot as plt  # their initialize() opens a figure per call (E:939, 1345)
    plt.close('all')
    return env, b0, store, config


def rect_dist(px, py, pose, shape):
    """Distance from points (px, py) to a rotated rectangle (0 inside)."""
    c, s = math.cos(pose.theta), math.sin(pose.theta)
    dx, dy = px - pose.x, py - pose.y
    lx = c * dx + s * dy
    ly = -s * dx + c * dy
    ex = np.maximum(np.abs(lx) - shape.width / 2, 0)
    ey = np.maximum(np.abs(ly) - shape.height / 2, 0)
    return np.hypot(ex, ey)


R_IN = 0.15   # robot inscribed half extent: closer than this, the robot overlaps whatever its heading
R_OUT = math.hypot(0.15, 0.30)  # robot circumradius: farther than this, it cannot overlap


def signature_grid(state, n=256, regions=None):
    """Per grid point (n x n over the 10 m plane): a signature (named regions certainly
    overlapped, obstacles possibly touched). Returns (codes, distinct codes, n)."""
    res = 10.0 / n
    xs = (np.arange(n) + 0.5) * res
    X, Y = np.meshgrid(xs, xs, indexing='xy')
    regions = regions if regions is not None else list(state.regions) + list(state.targets)
    bits = []
    for r in regions:
        bits.append(rect_dist(X, Y, r.pose, r.shape) <= R_IN)
    for o in state.obstacles:
        bits.append(rect_dist(X, Y, o.pose, o.shape) <= R_OUT)
    if not bits:
        return np.zeros_like(X, dtype=np.int64), 1, n
    B = np.stack(bits, axis=-1)
    # pack bits into one integer key per point
    weights = (1 << np.arange(B.shape[-1], dtype=np.int64))
    codes = (B.astype(np.int64) * weights).sum(axis=-1)
    return codes, len(np.unique(codes)), n


def components(codes):
    from scipy import ndimage
    total = 0
    for c in np.unique(codes):
        _, k = ndimage.label(codes == c)
        total += k
    return total


def quadtree_leaves(codes, res, min_cells=2):
    """Leaves of a quadtree over the grid that splits a cell while it holds more than
    one signature, down to min_cells x min_cells grid points (min_cells*res metres)."""
    n = codes.shape[0]
    leaves = 0
    stack = [(0, 0, n)]
    while stack:
        i, j, s = stack.pop()
        block = codes[i:i + s, j:j + s]
        if block.size == 0:
            continue
        if s <= min_cells or np.all(block == block.flat[0]):
            leaves += 1
            continue
        h = s // 2  # n is a power of two, so every split is exact
        stack += [(i, j, h), (i + h, j, h), (i, j + h, h), (i + h, j + h, h)]
    return leaves


def free_rectangles(codes):
    """Greedy maximal-rectangle cover of each signature class (row runs merged
    downwards while the run is identical): a box-boxel count with shared faces."""
    n = codes.shape[0]
    used = np.zeros_like(codes, dtype=bool)
    rects = 0
    for i in range(n):
        j = 0
        while j < n:
            if used[i, j]:
                j += 1
                continue
            c = codes[i, j]
            k = j
            while k < n and codes[i, k] == c and not used[i, k]:
                k += 1
            # extend downwards while the whole run matches and is unused
            m = i + 1
            while m < n and np.all(codes[m, j:k] == c) and not np.any(used[m, j:k]):
                m += 1
            used[i:m, j:k] = True
            rects += 1
            j = k
    return rects


def map_summary(task, seed):
    env, b0, store, config = build(task, seed)
    s = env.state
    ab0 = sorted(str(a) for a in b0.abstract(store).items)
    goal = s.goal.pose
    start = s.robot.pose
    d = lambda a, b: math.hypot(a.x - b.x, a.y - b.y)  # noqa: E731
    tg = []
    for t in s.targets:
        nb = min(s.beacons, key=lambda b: d(b.pose, t.pose)) if s.beacons else None
        tg.append({'name': t.name, 'xy': [round(t.pose.x, 3), round(t.pose.y, 3)],
                   'd_start': round(d(start, t.pose), 3), 'd_goal': round(d(t.pose, goal), 3),
                   'nearest_beacon': None if nb is None else nb.name,
                   'd_nearest_beacon': None if nb is None else round(d(nb.pose, t.pose), 3)})
    nbg = min(s.beacons, key=lambda b: d(b.pose, goal)) if s.beacons else None
    codes, nsig, n = signature_grid(s, 256)
    res = 10.0 / n
    out = {
        'task': task, 'seed': seed,
        'n_obstacles': len(s.obstacles), 'n_beacons': len(s.beacons), 'n_targets': len(s.targets),
        'n_corners': len(s.corners), 'regions': [r.name for r in s.regions],
        'obstacles': [[round(o.pose.x, 3), round(o.pose.y, 3), round(o.pose.theta, 3),
                       round(o.shape.width, 3), round(o.shape.height, 3)] for o in s.obstacles],
        'beacons': [[r.name, round(r.pose.x, 3), round(r.pose.y, 3), round(r.pose.theta, 3)] for r in s.beacons],
        'targets': tg,
        'goal_nearest_beacon': None if nbg is None else [nbg.name, round(d(nbg.pose, goal), 3)],
        'abstract_b0': ab0,
        'grid_res_m': round(res, 5), 'grid_points': int(n * n),
        'signatures_distinct': int(nsig),
        'signature_components': int(components(codes)),
        'quadtree_leaves_min_0.078m': int(quadtree_leaves(codes, res, min_cells=2)),
        'quadtree_leaves_min_0.156m': int(quadtree_leaves(codes, res, min_cells=4)),
        'box_cover_rectangles': int(free_rectangles(codes)),
    }
    return out


def mode_maps():
    rows = []
    for task in ['slam_collect', 'slam_collect_simple', 'slam_collect_custom']:
        for seed in range(20):
            t1 = time.time()
            r = map_summary(task, seed)
            r['seconds'] = round(time.time() - t1, 2)
            rows.append(r)
            print(task, seed, 'obs', r['n_obstacles'], 'sig', r['signatures_distinct'],
                  'comp', r['signature_components'], 'qt', r['quadtree_leaves_min_0.156m'],
                  'rects', r['box_cover_rectangles'], 'b0', r['abstract_b0'], flush=True)
    with open(os.path.join(OUT, 'maps.json'), 'w') as f:
        json.dump(rows, f, indent=1)


def mode_variance():
    reps = 400
    np.random.seed(12345)
    res = {}
    for name, act, start in [('diagonal', E.SlamAction(0.2, 0.2), (1.0, 1.0)),
                             ('axis', E.SlamAction(0.2, 0.0), (0.5, 5.0))]:
        rows = []
        for k in [1, 5, 10, 15, 20, 25, 30, 32, 35, 40]:
            vs, known = [], 0
            for _ in range(reps):
                arr = np.zeros((20, 3 + 6 * 3))
                arr[:, 0], arr[:, 1] = start
                for _ in range(k):
                    arr = E.apply_action_with_noise(arr, act)
                vx = np.std(arr[:, 0]) ** 2
                vy = np.std(arr[:, 1]) ** 2
                vs.append(max(vx, vy))
                known += int(vx < E.KNOWN_VAR_THRESH and vy < E.KNOWN_VAR_THRESH)
            rows.append({'k': k, 'mean_max_var': round(float(np.mean(vs)), 5),
                         'model_0.95x0.0016k': round(0.95 * 0.0016 * k, 5),
                         'p_known_pose': round(known / reps, 3)})
            print(name, rows[-1], flush=True)
        res[name] = rows
    with open(os.path.join(OUT, 'variance.json'), 'w') as f:
        json.dump(res, f, indent=1)


def belief_at(b0, x, y, theta=0.0):
    b = copy.deepcopy(b0)
    for p in b.particles:
        p.robot.pose = E.Pose(x, y, theta)
    return b


def mode_ctrl():
    rows = []
    for seed in range(20):
        env, b0, store, config = build('slam_collect', seed)
        s = env.state
        rec = {'seed': seed, 'pick_from_start': [], 'place_from_target': [], 'look_from_start': [],
               'to_goal_from_start': None, 'corner_from_start': []}
        for t in s.targets:
            t1 = time.time()
            pr = E.move_pick(Action('move_pick', [t.name]), b0, store)
            rec['pick_from_start'].append([t.name, len(pr), round(time.time() - t1, 3)])
            bt = belief_at(b0, t.pose.x, t.pose.y)
            t1 = time.time()
            pr = E.move_place(Action('move_place', [t.name, s.goal.name]), bt, store)
            rec['place_from_target'].append([t.name, len(pr), round(time.time() - t1, 3)])
        for b in s.beacons:
            pr = E.move_look(Action('move_look', [b.name]), b0, store)
            rec['look_from_start'].append([b.name, None if pr is None else len(pr)])
        pr = E.move_to(Action('move_to', [s.goal.name]), b0, store)
        rec['to_goal_from_start'] = None if pr is None else len(pr)
        # where does move_corner end? noise-free mean path and 10 noisy true-state runs
        for c in s.corners:
            pr = E.move_corner(Action('move_corner', [c.name]), b0, store)
            st = copy.deepcopy(s)
            arr = np.array([st.to_array()])
            for a in pr:
                arr = E.apply_action_with_noise(arr, a, noise_std_dev=0.0)
            hits = 0
            ends = []
            for _ in range(10):
                trajs, obs = E.generate_trajectory([copy.deepcopy(s)], pr, std=E.ACTION_STD)
                hits += int(c.name in obs[0].regions_in)
                ends.append([round(trajs[0][-1].robot.pose.x, 2), round(trajs[0][-1].robot.pose.y, 2)])
            rec['corner_from_start'].append({'corner': c.name, 'corner_xy': [c.pose.x, c.pose.y],
                                             'primitives': len(pr),
                                             'noise_free_end': [round(arr[0, 0], 3), round(arr[0, 1], 3)],
                                             'noisy_ends': ends, 'in_corner_region_of_10': hits})
        rows.append(rec)
        print(json.dumps(rec), flush=True)
    with open(os.path.join(OUT, 'ctrl.json'), 'w') as f:
        json.dump(rows, f, indent=1)


# ---------------------------------------------------------------- scripted policies
def mean_pose(b):
    a = np.array([p.robot.pose.to_array() for p in b.particles])
    return a[:, 0].mean(), a[:, 1].mean(), max(np.std(a[:, 0]) ** 2, np.std(a[:, 1]) ** 2)


def target_pose_in_belief(b, tname):
    for t in b.particles[0].targets:
        if t.name == tname:
            return t.pose
    return None


def clearance(state, dest):
    """Distance from a point to the nearest obstacle rectangle (inf without obstacles)."""
    if not state.obstacles:
        return float('inf')
    return min(float(rect_dist(np.array(dest[0]), np.array(dest[1]), o.pose, o.shape))
               for o in state.obstacles)


def best_beacon(state, x, y, dest):
    return min(state.beacons, key=lambda bc: math.hypot(bc.pose.x - x, bc.pose.y - y)
               + math.hypot(bc.pose.x - dest[0], bc.pose.y - dest[1]))


def run_policy(policy, seed, rep, k_ratio=1.07):
    """k_ratio: median primitives per Chebyshev step measured by ctrl (p2 ratio)."""
    env, b, store, config = build('slam_collect', seed)
    # vary the motion noise per repetition; the map is already fixed by the seed
    random.seed(seed * 1000 + rep + 7)
    np.random.seed(seed * 1000 + rep + 7)
    spec = env.problem_spec
    s0 = env.state
    goal = s0.goal
    log = []
    first = None
    looks = 0
    for step in range(config['max_steps']):
        ab = b.abstract(store)
        atoms = {str(a) for a in ab.items}
        if spec.get_reward(ab, store) > 0:
            action = Action('no-op')
        else:
            held = [a.args[0] for a in ab.items if a.pred_name == 'holding']
            done = {a.args[0] for a in ab.items if a.pred_name == 'target_in' and a.args[1] == goal.name}
            mx, my, var = mean_pose(b)
            todo = [t.name for t in s0.targets if t.name not in done]
            commit = None
            if held:
                commit = Action('move_place', [held[0], goal.name])
                dest = (goal.pose.x, goal.pose.y)
            elif todo:
                tp = {t: target_pose_in_belief(b, t) for t in todo}
                tn = min(todo, key=lambda t: math.hypot(tp[t].x - mx, tp[t].y - my))
                commit = Action('move_pick', [tn])
                dest = (tp[tn].x, tp[tn].y)
            # nothing left to commit (every target in the goal, reward still 0 because
            # of in_collision): no-op, as no move would be applicable in their spec
            look = False
            last = log[-1]['action'] if log else ''
            if commit is not None and not last.startswith('move_look'):
                if policy == 'S1_always':
                    look = True
                elif policy == 'S2_when_unknown':
                    look = 'known_pose()' not in atoms and 'known_pose' not in atoms
                elif policy == 'S3_predictive':
                    k_pred = k_ratio * max(abs(dest[0] - mx), abs(dest[1] - my)) / E.STEP_SIZE
                    look = var + 0.95 * E.ACTION_STD ** 2 * k_pred >= E.KNOWN_VAR_THRESH
                elif policy == 'S4_risk':
                    # predictive, and obstacle aware: look if the commit is predicted to end
                    # with the pose unknown, or with the spread of 20 particles (about 2 sigma)
                    # reaching an obstacle (clearance less the robot's circumradius)
                    k_pred = k_ratio * max(abs(dest[0] - mx), abs(dest[1] - my)) / E.STEP_SIZE
                    var_end = var + 0.95 * E.ACTION_STD ** 2 * k_pred
                    look = var_end >= E.KNOWN_VAR_THRESH or \
                        clearance(s0, dest) - R_OUT < 2.0 * math.sqrt(var_end)
                elif policy == 'S5_unknown_near':
                    look = 'known_pose' not in atoms
            action = commit if commit is not None else Action('no-op')
            if look:
                if policy in ('S4_risk', 'S5_unknown_near'):
                    bc = min(s0.beacons, key=lambda c: math.hypot(c.pose.x - dest[0], c.pose.y - dest[1]))
                else:
                    bc = best_beacon(s0, mx, my, dest)
                action = Action('move_look', [bc.name])
                looks += 1
        applicable = action.name == 'no-op' or action in spec.applicable_actions(ab, store)
        if not applicable:
            log.append({'step': step, 'action': str(action), 'inapplicable': True,
                        'atoms': sorted(atoms)})
            action = Action('no-op')
        t1 = time.time()
        if action.name == 'no-op':
            obs = None
            bp = copy.deepcopy(b)
            nprim = 0
        else:
            obs = env.step(action, b, store)
            nprim = len(obs.primitives)
            bp = b.update(action, obs, store)
        dt = time.time() - t1
        b = bp
        abp = b.abstract(store)
        r = spec.get_reward(abp, store)
        mx, my, var = mean_pose(b)
        st = env.state
        log.append({'step': step, 'action': str(action), 'primitives': nprim, 'seconds': round(dt, 3),
                    'obs_regions': None if obs is None else list(obs.regions_in),
                    'obs_holding': None if (obs is None or obs.holding is None) else obs.holding.target,
                    'obs_pose': None if (obs is None or obs.robot_pose is None) else 'exact',
                    'obs_collision': None if obs is None else bool(obs.collision),
                    'belief_var': round(var, 4), 'err_mean_true': round(math.hypot(mx - st.robot.pose.x, my - st.robot.pose.y), 3),
                    'atoms': sorted(str(a) for a in abp.items), 'reward': r})
        if r > 0 and first is None:
            first = step + 1
    st = env.state
    world_in = [bool(E.collides_regions(t, st.goal)) for t in st.targets]
    return {'policy': policy, 'seed': seed, 'rep': rep, 'success_belief': first is not None,
            'steps_to_success': first, 'return': (GAMMA ** first) if first else 0.0,
            'looks': looks, 'world_targets_in_goal': world_in,
            'world_success': all(world_in) and not st.in_collision, 'world_collision': bool(st.in_collision),
            'log': log}


def mode_policies():
    policies = sys.argv[2].split(',') if len(sys.argv) > 2 else ['S0_none', 'S1_always', 'S2_when_unknown', 'S3_predictive']
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    first_seed = int(sys.argv[5]) if len(sys.argv) > 5 else 0   # 100: the held-out set
    seeds = range(first_seed, first_seed + (int(sys.argv[4]) if len(sys.argv) > 4 else 20))
    tag = '' if first_seed == 0 else f'_seeds{first_seed}'
    rows = []
    for pol in policies:
        for seed in seeds:
            for rep in range(reps):
                t1 = time.time()
                try:
                    r = run_policy(pol, seed, rep)
                except Exception as e:  # noqa: BLE001  record and go on
                    r = {'policy': pol, 'seed': seed, 'rep': rep, 'success_belief': False,
                         'steps_to_success': None, 'return': 0.0, 'looks': 0,
                         'world_targets_in_goal': [], 'world_success': False,
                         'world_collision': False, 'error': repr(e), 'log': []}
                r['seconds'] = round(time.time() - t1, 2)
                rows.append(r)
                print(pol, seed, rep, 'succ', r['success_belief'], 'steps', r['steps_to_success'],
                      'ret', round(r['return'], 3), 'looks', r['looks'], 'world', r['world_success'],
                      'coll', r['world_collision'], 's', r['seconds'], flush=True)
        sub = [r for r in rows if r['policy'] == pol]
        n = len(sub)
        print('SUMMARY', pol, 'n', n, 'success', sum(r['success_belief'] for r in sub) / n,
              'mean_return', round(sum(r['return'] for r in sub) / n, 3),
              'world_success', sum(r['world_success'] for r in sub) / n, flush=True)
        with open(os.path.join(OUT, f'policies_{pol}{tag}.json'), 'w') as f:
            json.dump(sub, f, indent=1)


def mode_vis():
    save_dir = os.path.join(OUT, 'vis_seed0')
    env, b, store, config = build('slam_collect', 0, vis=True, save_dir=save_dir)
    s = env.state
    seq = [Action('move_pick', [s.targets[2].name]), Action('move_place', [s.targets[2].name, s.goal.name])]
    for a in seq:
        obs = env.step(a, b, store)
        b = b.update(a, obs, store)
        print(a, 'primitives', len(obs.primitives), 'regions', obs.regions_in,
              'holding', None if obs.holding is None else obs.holding.target, 'abstract', b.abstract(store))
    print('frames', len(os.listdir(os.path.join(save_dir, 'frames'))))


if __name__ == '__main__':
    mode = sys.argv[1]
    {'maps': mode_maps, 'variance': mode_variance, 'ctrl': mode_ctrl,
     'policies': mode_policies, 'vis': mode_vis}[mode]()
