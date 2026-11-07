"""P6: design (c)'s estimator changes sketched on their particle code, scored by a replica.

REVIEW COPY (slam_collect/REVIEW.md): identical to ../probe/p6_two_beliefs.py except one added rule,
S4n (S4o without the clearance clause), marked REVIEW ADDITION below; outputs go to review_probe/out
through the review copy of p1_measure.py.

Usage: python p6_two_beliefs.py <rule[,rule]> [reps] [n_seeds] [first_seed]
Rules: S0o (never look), S1o (look before every commit), S2o (look when the acting
belief's known_pose is false), S4o (S4_risk of p1_measure.py); S2x and S4x are S2o and S4o on
OursLikeX (two more estimator pieces, below). Writes out/twobelief_<rule>[_seedsN].json.

The ACTING belief is their SlamBelief (20 particles) with the two changes ARGUMENT.md 4.6 makes:
 (i)  a move_pick whose observation holds nothing removes the particles whose robot overlaps
      that target at the end (their update keeps them, E:194-198);
 (ii) in_collision is the observation's own collision flag, sticky like the true flag (E:887,
      909), instead of "any particle collided" (E:276-277).
The controllers get the acting belief (D-2). The REPLICA is an unchanged SlamBelief updated with
the same (action, observation) pairs; it gives their reward (3.3); its random draws are isolated
from the global streams (D-3). Decisions read only the acting belief and the static map of the
initial observation (b0.particles[0], D-1); env.state is read after each step by the evaluator,
for the world test only. Scripted rules, not a planner: a measurement of the task.
"""
import copy
import json
import math
import os
import random
import sys
import time

import numpy as np
import tampura_environments  # noqa: F401
import tampura_environments.slam_collect.env as E
from tampura.structs import AbstractBelief, Action
from tampura.symbolic import Atom

import p1_measure as P

GAMMA = 0.98


def overlaps(p, tname):
    for t in p.targets:
        if t.name == tname:
            return bool(np.any(E.collides(E.unsqueeze(p.robot.pose.to_array()), E.unsqueeze(E.ROBOT_SHAPE.to_array()),
                                          E.unsqueeze(t.pose.to_array()), E.unsqueeze(t.shape.to_array()))))
    return False


class OursLike(E.SlamBelief):
    true_coll = False
    removed = 0

    def update(self, action, observation, store):
        nb = E.SlamBelief.update(self, action, observation, store)  # a deep copy of self, so an OursLike
        if observation is None:
            return nb
        nb.true_coll = bool(self.true_coll or observation.collision)
        nb.removed = 0
        if action.name == 'move_pick' and observation.holding is None:
            keep = [p for p in nb.particles if not overlaps(p, action.args[0])]
            nb.removed = len(nb.particles) - len(keep)
            if keep and nb.removed:
                nb.particles = nb.particle_replenish(keep)
        return nb

    def abstract(self, store):
        ab = E.SlamBelief.abstract(self, store)
        items = [a for a in ab.items if a.pred_name != 'in_collision']
        if self.true_coll:
            items.append(Atom('in_collision'))
        return AbstractBelief(items)


def consistent(p, obs, action):
    """Their filter's test (E:165-201): same overlapped-region set, and the held target overlapped;
    plus change (i): after a pick that holds nothing, the picked target not overlapped."""
    rp = np.array([r.pose.to_array() for r in p.regions])
    rs = np.array([r.shape.to_array() for r in p.regions])
    c = np.atleast_1d(np.squeeze(E.collides(E.unsqueeze(p.robot.pose.to_array()), E.unsqueeze(E.ROBOT_SHAPE.to_array()), rp, rs)))
    ins = {p.regions[i].name for i in np.where(c == 1)[0]}
    if ins != set(obs.regions_in):
        return False
    if obs.holding is None:
        return not (action.name == 'move_pick' and overlaps(p, action.args[0]))
    return overlaps(p, obs.holding.target)


class OursLikeX(OursLike):
    """OursLike plus two more pieces of ARGUMENT.md 4.6:
    (iii) holding is the observation's own field for every particle (their belief takes it from the
          particles, and keeps simulated attachments when no particle fits, E:199-208);
    (iv)  when no particle fits the observation, re-seed: jitter the particles with a growing spread
          (0.1 to 0.8 m) and keep the ones that fit (their filter keeps the unfitted set, E:207-208).
    Its jitter draws come from its own generator, not from the global stream."""
    rng = None

    def update(self, action, observation, store):
        nb = OursLike.update(self, action, observation, store)
        if observation is None:
            return nb
        if nb.rng is None:
            nb.rng = np.random.default_rng(12345)
        nb.reseeded = 0
        if not any(consistent(p, observation, action) for p in nb.particles):
            for s in (0.1, 0.2, 0.4, 0.8):
                cands = []
                for p in nb.particles:
                    for _ in range(5):
                        q = copy.deepcopy(p)
                        dx, dy = nb.rng.normal(0.0, s, 2)
                        q.robot.pose = E.Pose(float(np.clip(p.robot.pose.x + dx, 0, E.ENV_SIZE)),
                                              float(np.clip(p.robot.pose.y + dy, 0, E.ENV_SIZE)), p.robot.pose.theta)
                        if consistent(q, observation, action):
                            cands.append(q)
                if cands:
                    idx = nb.rng.choice(len(cands), size=min(len(cands), nb.num_particles), replace=False)
                    nb.particles = nb.particle_replenish([cands[i] for i in idx])
                    nb.reseeded = s
                    break
        for p in nb.particles:
            p.attachments = [] if observation.holding is None else [copy.deepcopy(observation.holding)]
        return nb


def has(ab, pred, *args):
    return any(a.pred_name == pred and tuple(a.args) == tuple(args) for a in ab.items)


def run(rule, seed, rep, k_ratio=1.07):
    env, b0, store, config = P.build('slam_collect', seed)
    random.seed(seed * 1000 + rep + 7)          # the same noise seeds as p1_measure.py
    np.random.seed(seed * 1000 + rep + 7)
    spec = env.problem_spec
    m0 = b0.particles[0]                        # the initial observation's map (D-1)
    goal = m0.goal
    b = copy.deepcopy(b0)
    orig = rule
    b.__class__ = OursLikeX if rule.endswith('x') else OursLike
    if rule.endswith('x'):                      # S2x, S4x: the rules of S2o, S4o on OursLikeX
        rule = rule[:-1] + 'o'
        b.rng = np.random.default_rng(seed * 1000 + rep + 99)
    rb = b0                                     # the scoring replica, their belief unchanged
    log = []
    first_rep = first_world = first_done = None
    looks = 0
    for step in range(config['max_steps']):
        ab = b.abstract(store)
        if spec.get_reward(ab, store) > 0:
            action = Action('no-op')
            if first_done is None:
                first_done = step
        else:
            held = [a.args[0] for a in ab.items if a.pred_name == 'holding']
            done = {a.args[0] for a in ab.items if a.pred_name == 'target_in' and a.args[1] == goal.name}
            mx, my, var = P.mean_pose(b)
            todo = [t.name for t in m0.targets if t.name not in done]
            commit = None
            if held:
                commit = Action('move_place', [held[0], goal.name])
                dest = (goal.pose.x, goal.pose.y)
            elif todo:
                tp = {t: P.target_pose_in_belief(b, t) for t in todo}
                tn = min(todo, key=lambda t: math.hypot(tp[t].x - mx, tp[t].y - my))
                commit = Action('move_pick', [tn])
                dest = (tp[tn].x, tp[tn].y)
            look = False
            last = log[-1]['action'] if log else ''
            if commit is not None and not last.startswith('move_look'):
                if rule == 'S1o':
                    look = True
                elif rule == 'S2o':
                    look = not has(ab, 'known_pose')
                elif rule == 'S4o':
                    k_pred = k_ratio * max(abs(dest[0] - mx), abs(dest[1] - my)) / E.STEP_SIZE
                    var_end = var + 0.95 * E.ACTION_STD ** 2 * k_pred
                    look = var_end >= E.KNOWN_VAR_THRESH or \
                        P.clearance(m0, dest) - P.R_OUT < 2.0 * math.sqrt(var_end)
                elif rule == 'S4n':
                    # REVIEW ADDITION: S4o without the clearance clause (no `tight` term),
                    # same beacon choice, so the pair S4o / S4n isolates the obstacle term.
                    k_pred = k_ratio * max(abs(dest[0] - mx), abs(dest[1] - my)) / E.STEP_SIZE
                    var_end = var + 0.95 * E.ACTION_STD ** 2 * k_pred
                    look = var_end >= E.KNOWN_VAR_THRESH
            action = commit if commit is not None else Action('no-op')
            if look:
                if rule in ('S4o', 'S4n'):
                    bc = min(m0.beacons, key=lambda c: math.hypot(c.pose.x - dest[0], c.pose.y - dest[1]))
                else:
                    bc = P.best_beacon(m0, mx, my, dest)
                action = Action('move_look', [bc.name])
                looks += 1
        inapplicable = action.name != 'no-op' and action not in spec.applicable_actions(ab, store)
        if inapplicable:
            log.append({'step': step, 'action': str(action), 'inapplicable': True,
                        'atoms': sorted(str(a) for a in ab.items)})
            action = Action('no-op')
        t1 = time.time()
        obs = None
        if action.name != 'no-op':
            obs = env.step(action, b, store)
            b = b.update(action, obs, store)
            s_np, s_py = np.random.get_state(), random.getstate()
            rb = rb.update(action, obs, store)
            np.random.set_state(s_np)
            random.setstate(s_py)
        dt = time.time() - t1
        rab = rb.abstract(store)
        rr = spec.get_reward(rab, store)
        st = env.state                          # evaluator only
        world = all(bool(E.collides_regions(t, st.goal)) for t in st.targets) and not st.in_collision
        mx, my, var = P.mean_pose(b)
        log.append({'step': step, 'action': str(action), 'primitives': 0 if obs is None else len(obs.primitives),
                    'seconds': round(dt, 3), 'obs_collision': None if obs is None else bool(obs.collision),
                    'obs_holding': None if (obs is None or obs.holding is None) else obs.holding.target,
                    'removed_by_failed_pick': b.removed if obs is not None else 0,
                    'reseeded': getattr(b, 'reseeded', 0) if obs is not None else 0,
                    'acting_var': round(var, 4), 'err_mean_true': round(math.hypot(mx - st.robot.pose.x, my - st.robot.pose.y), 3),
                    'acting_atoms': sorted(str(a) for a in b.abstract(store).items),
                    'replica_in_collision': has(rab, 'in_collision'), 'replica_reward': rr, 'world': world})
        if rr > 0 and first_rep is None:
            first_rep = step + 1
        if world and first_world is None:
            first_world = step + 1
    st = env.state
    world_in = [bool(E.collides_regions(t, st.goal)) for t in st.targets]
    return {'rule': orig, 'seed': seed, 'rep': rep,
            'replica_success': first_rep is not None, 'replica_steps': first_rep,
            'replica_return': GAMMA ** first_rep if first_rep else 0.0,
            'world_first_steps': first_world, 'world_return': GAMMA ** first_world if first_world else 0.0,
            'world_success_end': all(world_in) and not st.in_collision, 'world_collision': bool(st.in_collision),
            'acting_done_step': first_done, 'looks': looks,
            'replica_in_collision_end': has(rb.abstract(store), 'in_collision'), 'log': log}


def main():
    rules = sys.argv[1].split(',')
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    first_seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    tag = '' if first_seed == 0 else f'_seeds{first_seed}'
    for rule in rules:
        rows = []
        for seed in range(first_seed, first_seed + n):
            for rep in range(reps):
                t1 = time.time()
                try:
                    r = run(rule, seed, rep)
                except Exception as e:  # noqa: BLE001  record and go on
                    r = {'rule': rule, 'seed': seed, 'rep': rep, 'replica_success': False, 'replica_steps': None,
                         'replica_return': 0.0, 'world_first_steps': None, 'world_return': 0.0,
                         'world_success_end': False, 'world_collision': False, 'acting_done_step': None,
                         'looks': 0, 'replica_in_collision_end': False, 'error': repr(e), 'log': []}
                r['seconds'] = round(time.time() - t1, 2)
                rows.append(r)
                print(rule, seed, rep, 'replica', r['replica_success'], r['replica_steps'], 'world_first', r['world_first_steps'],
                      'world_end', r['world_success_end'], 'looks', r['looks'], 'replica_coll_end', r['replica_in_collision_end'],
                      's', r['seconds'], flush=True)
        k = len(rows)
        print('SUMMARY', rule, 'n', k, 'replica success', sum(r['replica_success'] for r in rows), 'return',
              round(sum(r['replica_return'] for r in rows) / k, 3), '| world first', sum(r['world_first_steps'] is not None for r in rows),
              'return', round(sum(r['world_return'] for r in rows) / k, 3), 'world end', sum(r['world_success_end'] for r in rows), flush=True)
        with open(os.path.join(P.OUT, f'twobelief_{rule}{tag}.json'), 'w') as f:
            json.dump(rows, f, indent=1)


if __name__ == '__main__':
    main()
