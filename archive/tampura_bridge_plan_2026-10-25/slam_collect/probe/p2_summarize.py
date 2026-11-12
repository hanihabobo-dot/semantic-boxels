"""P2: summarise the JSON files written by p1_measure.py (reads out/, prints only)."""
import glob
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
GAMMA = 0.98


def q(xs):
    xs = sorted(xs)
    if not xs:
        return 'n/a'
    return f'n {len(xs)} min {xs[0]} median {st.median(xs)} mean {round(st.mean(xs), 2)} max {xs[-1]}'


def ctrl():
    rows = json.load(open(os.path.join(OUT, 'ctrl.json')))
    pick = [p[1] for r in rows for p in r['pick_from_start']]
    place = [p[1] for r in rows for p in r['place_from_target']]
    look = [p[1] for r in rows for p in r['look_from_start'] if p[1] is not None]
    look_fail = sum(1 for r in rows for p in r['look_from_start'] if p[1] is None)
    togoal = [r['to_goal_from_start'] for r in rows if r['to_goal_from_start'] is not None]
    print('primitives move_pick from start ', q(pick))
    print('primitives move_place target->goal', q(place))
    print('primitives move_look from start  ', q(look), 'rrt failures', look_fail)
    print('primitives move_to goal from start', q(togoal))
    secs = [p[2] for r in rows for p in r['pick_from_start'] + r['place_from_target']]
    print('controller seconds (pick, place)', q(secs))
    hits = sum(c['in_corner_region_of_10'] for r in rows for c in r['corner_from_start'])
    tot = 10 * sum(len(r['corner_from_start']) for r in rows)
    prim = sorted({c['primitives'] for r in rows for c in r['corner_from_start']})
    print('move_corner from start: runs ending in the named corner', hits, 'of', tot, 'primitive counts', prim)
    ends = {}
    for r in rows:
        for c in r['corner_from_start']:
            ends.setdefault(c['corner'] + str(c['corner_xy']), []).append(tuple(c['noise_free_end']))
    for k, v in ends.items():
        print('  corner', k, 'noise-free end (first 5 seeds)', v[:5])


def ratio():
    """Primitives per straight-line step count, for the S3 predictor."""
    rows = json.load(open(os.path.join(OUT, 'ctrl.json')))
    maps = {m['seed']: m for m in json.load(open(os.path.join(OUT, 'maps.json'))) if m['task'] == 'slam_collect'}
    rp, rg = [], []
    for r in rows:
        tx = {t['name']: t['xy'] for t in maps[r['seed']]['targets']}
        for name, n, _ in r['pick_from_start']:
            straight = max(abs(tx[name][0] - 1.0), abs(tx[name][1] - 1.0)) / 0.2
            if straight > 3:
                rp.append(round(n / straight, 3))
        for name, n, _ in r['place_from_target']:
            straight = max(abs(tx[name][0] - 8.0), abs(tx[name][1] - 8.0)) / 0.2
            if straight > 3:
                rg.append(round(n / straight, 3))
    print('primitives / (Chebyshev distance / 0.2): pick from start', q(rp))
    print('primitives / (Chebyshev distance / 0.2): place to goal  ', q(rg))


def maps():
    rows = json.load(open(os.path.join(OUT, 'maps.json')))
    for task in ['slam_collect', 'slam_collect_simple', 'slam_collect_custom']:
        sub = [r for r in rows if r['task'] == task]
        print(task)
        print('  obstacles', q([r['n_obstacles'] for r in sub]), 'beacons', q([r['n_beacons'] for r in sub]),
              'targets', q([r['n_targets'] for r in sub]), 'regions', q([len(r['regions']) for r in sub]))
        print('  signatures distinct ', q([r['signatures_distinct'] for r in sub]))
        print('  signature components', q([r['signature_components'] for r in sub]))
        print('  quadtree leaves 0.078', q([r['quadtree_leaves_min_0.078m'] for r in sub]))
        print('  quadtree leaves 0.156', q([r['quadtree_leaves_min_0.156m'] for r in sub]))
        print('  box cover rectangles', q([r['box_cover_rectangles'] for r in sub]))
        if task == 'slam_collect':
            ds = [t['d_start'] for r in sub for t in r['targets']]
            dg = [t['d_goal'] for r in sub for t in r['targets']]
            db = [t['d_nearest_beacon'] for r in sub for t in r['targets']]
            gb = [r['goal_nearest_beacon'][1] for r in sub]
            print('  target dist from start', q(ds))
            print('  target dist to goal   ', q(dg))
            print('  target dist to nearest beacon centre', q(db))
            print('  goal dist to nearest beacon centre  ', q(gb))
            extra = [a for r in sub for a in r['abstract_b0'] if a not in ('known_pose', 'in(o_start_10)')]
            print('  extra atoms in b0 over 20 seeds', len(extra), extra[:8])


def policies():
    # policies_S0_S1_S2_S3.json is the 2-seed trial run; the full runs are one file per policy
    files = sorted(f for f in glob.glob(os.path.join(OUT, 'policies_*.json')) if 'S0_S1' not in f)
    for fn in files:
        rows = json.load(open(fn))
        for pol in sorted({r['policy'] for r in rows}):
            sub = [r for r in rows if r['policy'] == pol]
            n = len(sub)
            succ = [r for r in sub if r['success_belief']]
            steps = [r['steps_to_success'] for r in succ]
            seeds = sorted({r['seed'] for r in sub})
            per_seed = {s: sum(r['success_belief'] for r in sub if r['seed'] == s) for s in seeds}
            ret = [r['return'] for r in sub]
            # standard error of the mean return
            se = (st.pstdev(ret) / math.sqrt(n)) if n > 1 else 0
            looks = [r['looks'] for r in sub]
            coll = sum(1 for r in sub if r['world_collision'])
            inapp = sum(1 for r in sub for e in r['log'] if e.get('inapplicable'))
            belief_coll = sum(1 for r in sub if any('in_collision' in e.get('atoms', []) for e in r['log']))
            print(f'{os.path.basename(fn)} {pol}: n {n} success(belief) {len(succ)}/{n} = {round(len(succ)/n, 3)}'
                  f' mean return {round(st.mean(ret), 3)} +- {round(se, 3)} (se)'
                  f' world success {sum(r["world_success"] for r in sub)}/{n}'
                  f' world collision {coll} belief in_collision {belief_coll} inapplicable picks {inapp}')
            print('   steps to success', q(steps), '| looks', q(looks))
            print('   successes per seed', per_seed)
            fails = [r for r in sub if not r['success_belief']]
            for r in fails[:6]:
                last = r['log'][-1]
                acts = [e['action'] for e in r['log'] if e['action'] != 'no-op()']
                print('   FAIL seed', r['seed'], 'rep', r['rep'], 'actions', len(acts), acts[:14], 'last atoms', last['atoms'][:8])
            prims = [e['primitives'] for r in sub for e in r['log'] if e.get('primitives')]
            secs = [e['seconds'] for r in sub for e in r['log'] if e.get('primitives')]
            print('   primitives per executed move', q(prims), '| seconds per step (execute + update)', q(secs))
            errs = [e['err_mean_true'] for r in sub for e in r['log'] if e.get('primitives')]
            print('   |mean - true| after a move (m)', q(errs))
            bw = {(a, b): 0 for a in (True, False) for b in (True, False)}
            for r in sub:
                bw[(bool(r['success_belief']), bool(r['world_success']))] += 1
            print('   belief x world success: both', bw[(True, True)], 'belief only', bw[(True, False)],
                  'world only', bw[(False, True)], 'neither', bw[(False, False)])
            print('   episode seconds', q([r['seconds'] for r in sub]),
                  '| errors', sum(1 for r in sub if r.get('error')))
            # first failing reason: replica in_collision, pick without holding, place without target_in
            reasons = {}
            for r in fails:
                atoms = r['log'][-1]['atoms'] if r['log'] else []
                key = 'in_collision' if 'in_collision' in atoms else (
                    'holding at end' if any(a.startswith('holding') for a in atoms) else 'targets missing')
                reasons[key] = reasons.get(key, 0) + 1
            print('   failure end states', reasons)
            # where the belief's in_collision first appeared, and whether the true robot collided there
            firsts = {}
            phantom = real = 0
            for r in sub:
                for e in r['log']:
                    if 'in_collision' in e.get('atoms', []):
                        act = e['action'].split('(')[0]
                        firsts[act] = firsts.get(act, 0) + 1
                        if e.get('obs_collision'):
                            real += 1
                        else:
                            phantom += 1
                        break
            print('   episodes whose belief got in_collision:', sum(firsts.values()), 'by action', firsts,
                  '| true robot in collision at that step', real, '| particle only (phantom)', phantom)
            first_hold = [e['step'] for r in sub for e in r['log'] if e.get('inapplicable')]
            print('   inapplicable decisions (replaced by no-op)', len(first_hold))


def twobelief():
    """Summarise out/twobelief_*.json written by p6_two_beliefs.py."""
    for fn in sorted(glob.glob(os.path.join(OUT, 'twobelief_*.json'))):
        rows = json.load(open(fn))
        n = len(rows)
        if n == 0:
            continue

        def mse(xs):
            return round(st.mean(xs), 3), round(st.pstdev(xs) / math.sqrt(len(xs)), 3) if len(xs) > 1 else 0

        rs = [r for r in rows if r['replica_success']]
        wf = [r for r in rows if r['world_first_steps'] is not None]
        print(f"{os.path.basename(fn)} n {n} | replica success {len(rs)}/{n} return {mse([r['replica_return'] for r in rows])}"
              f" steps {q([r['replica_steps'] for r in rs])}")
        print(f"   world test ever {len(wf)}/{n} return {mse([r['world_return'] for r in rows])}"
              f" steps {q([r['world_first_steps'] for r in wf])} | world at end {sum(r['world_success_end'] for r in rows)}/{n}"
              f" | true collision {sum(r['world_collision'] for r in rows)} | errors {sum(1 for r in rows if r.get('error'))}")
        both = sum(1 for r in rows if r['replica_success'] and r['world_first_steps'] is not None)
        print(f"   replica x world-ever: both {both} replica only {len(rs) - both} world only {len(wf) - both}"
              f" neither {n - len(rs) - len(wf) + both}")
        ever_rc = sum(1 for r in rows if any(e.get('replica_in_collision') for e in r['log']))
        print(f"   replica in_collision ever {ever_rc}, at end {sum(r['replica_in_collision_end'] for r in rows)}"
              f" | agent stopped (own goal belief) {sum(r['acting_done_step'] is not None for r in rows)}"
              f" | looks {q([r['looks'] for r in rows])}")
        lost = [r for r in rows if r['world_first_steps'] is not None and not r['world_success_end']]
        print(f"   world test held, then lost by the end: {len(lost)}", [(r['seed'], r['rep']) for r in lost][:10])

        def stable_first(r):
            """First step n (1-based) from which the world test holds at every later step."""
            w = [e.get('world', False) for e in r['log'] if not e.get('inapplicable')]
            if not w or not w[-1]:
                return None
            n = len(w)
            while n > 0 and w[n - 1]:
                n -= 1
            return n + 1

        stop_w = sum(1 for r in rows if r['acting_done_step'] is not None and r['world_success_end'])
        stop_nw = sum(1 for r in rows if r['acting_done_step'] is not None and not r['world_success_end'])
        go_w = sum(1 for r in rows if r['acting_done_step'] is None and r['world_success_end'])
        print(f"   acting belief's goal vs world at end: stopped and world true {stop_w}, stopped and world false {stop_nw},"
              f" never stopped and world true {go_w}, neither {n - stop_w - stop_nw - go_w}")
        sf = [stable_first(r) for r in rows]
        print(f"   world test held from step n to the end: {sum(s is not None for s in sf)}/{n}"
              f" return {mse([GAMMA ** s if s else 0.0 for s in sf])} steps {q([s for s in sf if s])}")
        stuck = [r for r in rows if not r['replica_success'] and not r['replica_in_collision_end']]
        print(f"   replica never rewarded and free of in_collision at the end: {len(stuck)}",
              [(r['seed'], r['rep']) for r in stuck][:10])
        rem = [e['removed_by_failed_pick'] for r in rows for e in r['log'] if e.get('removed_by_failed_pick')]
        print(f"   failed picks that removed particles: {len(rem)}, particles removed {q(rem)}")
        inap = sum(1 for r in rows for e in r['log'] if e.get('inapplicable'))
        print(f"   inapplicable decisions (replaced by no-op) {inap}")
        seeds = sorted({r['seed'] for r in rows})
        print('   replica successes per seed', {s: sum(r['replica_success'] for r in rows if r['seed'] == s) for s in seeds})
        print('   world-ever per seed       ', {s: sum(r['world_first_steps'] is not None for r in rows if r['seed'] == s) for s in seeds})
        print('   episode seconds', q([r['seconds'] for r in rows]))


def stopreturn():
    """World return without per-step world reads (added after REVIEW.md U-2): success = the world test
    on the final world; n = the agent's own stop step (its first no-op, from its action log)."""
    for fn in sorted(glob.glob(os.path.join(OUT, 'twobelief_*.json'))):
        rows = json.load(open(fn))
        n = len(rows)
        if n < 10:
            continue
        ret = [GAMMA ** r['acting_done_step'] if (r['world_success_end'] and r['acting_done_step'] is not None) else 0.0
               for r in rows]
        wins = sum(1 for x in ret if x > 0)
        se = st.pstdev(ret) / math.sqrt(n)
        print(f"{os.path.basename(fn)}: n {n} final-world wins with a stop {wins}/{n},"
              f" return {round(st.mean(ret), 3)} +- {round(se, 3)}")


def tworow():
    """One table row per rule over seeds 0 to 19, merging the split runs (twobelief_<R>.json and
    twobelief_<R>_seeds10.json), for the S1y and S4y rows of ARGUMENT.md 3.6."""
    for rule in ['S1y', 'S4y']:
        rows = []
        for tag in ['', '_seeds10']:
            fn = os.path.join(OUT, f'twobelief_{rule}{tag}.json')
            if os.path.isfile(fn):
                rows += json.load(open(fn))
        n = len(rows)
        if n == 0:
            continue
        rr = [r['replica_return'] for r in rows]

        def stable(r):
            w = [e.get('world', False) for e in r['log'] if not e.get('inapplicable')]
            if not w or not w[-1]:
                return None
            k = len(w)
            while k > 0 and w[k - 1]:
                k -= 1
            return k + 1

        sf = [stable(r) for r in rows]
        wr = [GAMMA ** s if s else 0.0 for s in sf]
        se = lambda xs: round(st.pstdev(xs) / math.sqrt(len(xs)), 3)
        wonly = sum(1 for r, s in zip(rows, sf) if r['world_first_steps'] is not None and not r['replica_success'])
        ronly = sum(1 for r in rows if r['replica_success'] and r['world_first_steps'] is None)
        print(f"{rule}: n {n} seeds {sorted({r['seed'] for r in rows})[0]}-{sorted({r['seed'] for r in rows})[-1]}"
              f" | replica {sum(r['replica_success'] for r in rows)}/{n} return {round(st.mean(rr), 3)} +- {se(rr)}"
              f" | world {sum(s is not None for s in sf)}/{n} return {round(st.mean(wr), 3)} +- {se(wr)}"
              f" steps median {st.median([s for s in sf if s])}"
              f" | true collisions {sum(r['world_collision'] for r in rows)} | world only {wonly} replica only {ronly}"
              f" | looks {sum(r['looks'] for r in rows)} | false stops"
              f" {sum(1 for r in rows if r['acting_done_step'] is not None and not r['world_success_end'])}")


def pilotref():
    """Per-seed wins (out of 3 repetitions) on the pilot seeds 0, 1, 2, 5, 6, 10, for the
    reference numbers of ARGUMENT.md section 11 (their reward through the replica; world at the end)."""
    pilot = [0, 1, 2, 5, 6, 10]
    for rule in ['S1o', 'S4o', 'S1y', 'S4y']:
        rows = []
        for tag in ['', '_seeds10']:
            fn = os.path.join(OUT, f'twobelief_{rule}{tag}.json')
            if os.path.isfile(fn):
                rows += json.load(open(fn))
        rew = {s: sum(r['replica_success'] for r in rows if r['seed'] == s) for s in pilot}
        wld = {s: sum(r['world_success_end'] for r in rows if r['seed'] == s) for s in pilot}
        print(f"{rule}: reward wins per seed {rew} (seeds won in most repetitions: {sum(v >= 2 for v in rew.values())});"
              f" world wins per seed {wld} ({sum(v >= 2 for v in wld.values())})")
    for pol in ['S1_always', 'S4_risk']:
        rows = json.load(open(os.path.join(OUT, f'policies_{pol}.json')))
        rew = {s: sum(r['success_belief'] for r in rows if r['seed'] == s) for s in pilot}
        print(f"{pol} (their belief acting): reward wins per seed {rew} ({sum(v >= 2 for v in rew.values())})")


def twofail():
    """The episodes of out/twobelief_*.json that fail the world test at the end, one line each."""
    for fn in sorted(glob.glob(os.path.join(OUT, 'twobelief_*.json'))):
        rows = json.load(open(fn))
        print(os.path.basename(fn))
        for r in rows:
            if r['world_success_end']:
                continue
            steps = [e for e in r['log'] if not e.get('inapplicable')]
            first_true = next((e['step'] for e in steps if e.get('obs_collision')), None)
            at = next((e['action'] for e in steps if e.get('obs_collision')), None)
            acts = [e['action'].split('(')[0].replace('move_', '') for e in steps if e['action'] != 'no-op()']
            print(f"   seed {r['seed']} rep {r['rep']} true collision {r['world_collision']} (step {first_true}, {at})"
                  f" agent stopped {r['acting_done_step']} replica {r['replica_success']} actions {len(acts)} {acts[:12]}")


def rect_dist(px, py, ox, oy, th, w, h):
    c, s = math.cos(th), math.sin(th)
    dx, dy = px - ox, py - oy
    lx, ly = c * dx + s * dy, -s * dx + c * dy
    ex, ey = max(abs(lx) - w / 2, 0), max(abs(ly) - h / 2, 0)
    return math.hypot(ex, ey)


def clear():
    """Clearance of the goal centre and of each target centre to the nearest obstacle."""
    rows = [m for m in json.load(open(os.path.join(OUT, 'maps.json'))) if m['task'] == 'slam_collect']
    for m in rows:
        obs = m['obstacles']
        cg = min(rect_dist(8.0, 8.0, *o) for o in obs)
        ct = [round(min(rect_dist(t['xy'][0], t['xy'][1], *o) for o in obs), 2) for t in m['targets']]
        print('seed', m['seed'], 'goal clearance', round(cg, 2), 'target clearances', ct)


if __name__ == '__main__':
    for m in sys.argv[1:]:
        {'ctrl': ctrl, 'maps': maps, 'policies': policies, 'ratio': ratio, 'clear': clear,
         'twobelief': twobelief, 'twofail': twofail, 'stopreturn': stopreturn, 'tworow': tworow,
         'pilotref': pilotref}[m]()
