"""Read-only: BF#63 run 2 (eval2/5084*/results.jsonl), counted final rows.

For arm O, map each episode's dispatched primitives onto TAMPURA's find_dice
action vocabulary (pick, place, look, go-home; their actions include the
motion, so our moves are absorbed):
    t_equiv = picks + places + senses + observes (+ 1 go-home on a success)
For arm T, the number of their actions until the first reward 1
(rewards[i] is the reward of the belief before action i, policy.py:105-108,
so the first i with rewards[i] == 1 is the count of actions executed).
Prints distributions, how many exceed max_steps 20, and the discounted
return gamma**t (gamma 0.98, find_dice.yml) under that convention.
Usage: python -I -B bf63_step_equiv.py <eval2 dir>
"""
import glob
import json
import os
import statistics
import sys

ev = sys.argv[1]
rows = []
for d in sorted(glob.glob(os.path.join(ev, '5084*'))):
    with open(os.path.join(d, 'results.jsonl'), encoding='utf-8') as f:
        rows += [json.loads(l) for l in f if l.strip()]
final = {}
for r in rows:
    k = (r['arm'], r['seed'], r['rep'])
    if k not in final or r['attempt'] >= final[k]['attempt']:
        final[k] = r

G = 0.98


def q(xs):
    xs = sorted(xs)
    if not xs:
        return 'n/a'
    return (f"n {len(xs)}, median {statistics.median(xs)}, min {xs[0]}, max {xs[-1]}, "
            f"mean {statistics.mean(xs):.2f}")


o_succ, o_fail, t_succ = [], [], []
o_ret, t_ret = [], []
for (arm, s, rep), r in sorted(final.items()):
    if not r['counts']:
        continue
    if arm == 'O':
        m = r['rec'].get('metrics') or {}
        need = ('picks', 'places', 'senses', 'observes')
        if not all(k in m for k in need):
            print(f"  O s{s} r{rep}: metrics missing {need}")
            continue
        t = sum(m[k] for k in need) + (1 if r['success'] else 0)
        (o_succ if r['success'] else o_fail).append(t)
        o_ret.append(G ** t if r['success'] else 0.0)
    else:
        rw = r['rec'].get('rewards') or []
        hit = [i for i, v in enumerate(rw) if v == 1.0]
        if r['success'] and hit:
            t_succ.append(hit[0])
            t_ret.append(G ** hit[0])
        else:
            t_ret.append(0.0)

print("arm O counted successes with t_equiv > 15 (seed, rep, cups, picks/places/senses/observes):")
for (arm, s, rep), r in sorted(final.items()):
    if arm == 'O' and r['counts'] and r['success']:
        m = r['rec'].get('metrics') or {}
        t = m['picks'] + m['places'] + m['senses'] + m['observes'] + 1
        if t > 15:
            print(f"  s{s} r{rep} cups {r['n_cups']}: t_equiv {t} "
                  f"({m['picks']}/{m['places']}/{m['senses']}/{m['observes']}), "
                  f"plan_calls {m.get('plan_calls')}, wall {r['wall_s']}")
by_cups = {}
for (arm, s, rep), r in sorted(final.items()):
    if r['counts'] and r['success']:
        if arm == 'O':
            m = r['rec'].get('metrics') or {}
            t = m['picks'] + m['places'] + m['senses'] + m['observes'] + 1
        else:
            rw = r['rec'].get('rewards') or []
            t = [i for i, v in enumerate(rw) if v == 1.0][0]
        by_cups.setdefault((arm, r['n_cups']), []).append(t)
print("successes by cup count, actions (O: t_equiv; T: their actions), median [min, max]:")
for c in sorted({c for (_, c) in by_cups}):
    cells = []
    for arm in ('O', 'T'):
        xs = sorted(by_cups.get((arm, c), []))
        cells.append(f"{arm} n {len(xs)} " + (f"{statistics.median(xs)} [{xs[0]}, {xs[-1]}]" if xs else '-'))
    print(f"  {c} cups: " + '   '.join(cells))
print("arm O counted successes, t_equiv:", q(o_succ))
no_obs = []
for (arm, s, rep), r in sorted(final.items()):
    if arm == 'O' and r['counts'] and r['success']:
        m = r['rec'].get('metrics') or {}
        no_obs.append(m['picks'] + m['places'] + m['senses'] + 1)
print("arm O counted successes, t_equiv without observes:", q(no_obs))
print("  of those > 20:", sum(t > 20 for t in no_obs),
      " mean return:", f"{sum(G ** t for t in no_obs) / len(o_ret):.3f} over {len(o_ret)}")
print("  successes with t_equiv > 20:", sum(t > 20 for t in o_succ))
print("  successes with t_equiv > 15:", sum(t > 15 for t in o_succ))
print("arm O counted failures, primitives so far (no go-home):", q(o_fail))
print("arm T counted successes, actions to first reward 1:", q(t_succ))
print(f"mean discounted return over counted episodes, gamma {G}:")
print(f"  O (t_equiv convention): {statistics.mean(o_ret):.3f} over {len(o_ret)}")
print(f"  T (their actions):      {statistics.mean(t_ret):.3f} over {len(t_ret)}")
print(f"  O under today's one-action harness would read {G:.2f} per success "
      f"(rewards[1] == 1): {G * len(o_succ) / len(o_ret):.3f}")
