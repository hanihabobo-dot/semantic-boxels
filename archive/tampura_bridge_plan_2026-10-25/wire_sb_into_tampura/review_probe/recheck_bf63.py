"""Reviewer's read-only recheck of ARGUMENT.md's BF#63 run 2 indicator.

Independent of the author's bf63_step_equiv.py: reads the same committed
records (eval2/5084*/results.jsonl), selects the final attempt per (arm,
seed, rep) as bf63_tables.py:29-33 does, and prints
  1. the author's figures recomputed (medians, maxima, mean returns);
  2. arm T's steps from rec['solve_step'] against the first index with
     rewards[i] == 1, and how many no-ops precede a success;
  3. arm O successes that dispatched no sense at all (under L2 the die can
     only be seen at a look, so each needs at least one more action);
  4. arm O successes whose picks exceed cups + 1 (an object picked twice or
     a failed pick retried: their pick needs not moved(o), and their
     kinematic pick does not miss);
  5. mean returns over the 76 paired (seed, rep) only, like for like.
Usage: python3 -I -B recheck_bf63.py <eval2 dir>
Writes nothing; prints to stdout.
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


def med(xs):
    return statistics.median(xs) if xs else None


def t_equiv(m, success, observes=True):
    t = m['picks'] + m['places'] + m['senses'] + (m['observes'] if observes else 0)
    return t + (1 if success else 0)


def t_steps(r):
    rw = r['rec'].get('rewards') or []
    hit = [i for i, v in enumerate(rw) if v == 1.0]
    return hit[0] if hit else None


counted = {k: r for k, r in final.items() if r['counts']}
O = {(s, rep): r for (a, s, rep), r in counted.items() if a == 'O'}
T = {(s, rep): r for (a, s, rep), r in counted.items() if a == 'T'}
print(f"counted: O {len(O)} (successes {sum(r['success'] for r in O.values())}), "
      f"T {len(T)} (successes {sum(r['success'] for r in T.values())})")

# 1. the author's figures
o_s = [t_equiv(r['rec']['metrics'], True) for r in O.values() if r['success']]
t_s = [t_steps(r) for r in T.values() if r['success']]
print(f"1. O successes t_equiv: median {med(o_s)}, min {min(o_s)}, max {max(o_s)}, "
      f">20: {sum(t > 20 for t in o_s)}, >15: {sum(t > 15 for t in o_s)}")
print(f"   T successes steps: median {med(t_s)}, min {min(t_s)}, max {max(t_s)}")
o_ret = [G ** t_equiv(r['rec']['metrics'], True) if r['success'] else 0.0 for r in O.values()]
t_ret = [G ** t_steps(r) if (r['success'] and t_steps(r) is not None) else 0.0 for r in T.values()]
print(f"   mean return: O {statistics.mean(o_ret):.3f} over {len(o_ret)}, "
      f"T {statistics.mean(t_ret):.3f} over {len(t_ret)}; "
      f"O today's harness {G * len(o_s) / len(O):.3f}")

# 2. arm T: solve_step against the first reward-1 index; no-ops before success
mismatch, noop_before = [], []
for k, r in sorted(T.items()):
    if not r['success']:
        continue
    t = t_steps(r)
    ss = r['rec'].get('solve_step')
    if ss != t:
        mismatch.append((k, ss, t))
    acts = r['rec'].get('get_action_actions') or []
    n_noop = sum(1 for a in acts[:t] if str(a).startswith('no-op'))
    if n_noop:
        noop_before.append((k, n_noop))
print(f"2. T successes with solve_step != first reward-1 index: {mismatch or 'none'}; "
      f"with no-ops before success: {noop_before or 'none'}")

# 3. arm O successes with no sense dispatched
no_sense = [(k, r['n_cups'], t_equiv(r['rec']['metrics'], True))
            for k, r in sorted(O.items()) if r['success'] and r['rec']['metrics']['senses'] == 0]
print(f"3. O successes with senses == 0: {len(no_sense)} of {len(o_s)}: {no_sense}")
adj = [t_equiv(r['rec']['metrics'], True) + (1 if r['rec']['metrics']['senses'] == 0 else 0)
       for r in O.values() if r['success']]
adj_ret = [G ** (t_equiv(r['rec']['metrics'], True) + (1 if r['rec']['metrics']['senses'] == 0 else 0))
           if r['success'] else 0.0 for r in O.values()]
print(f"   with one look added to each: median {med(adj)}, mean return {statistics.mean(adj_ret):.3f} over {len(adj_ret)}")
dist = {}
for r in O.values():
    if r['success']:
        s = r['rec']['metrics']['senses']
        dist[s] = dist.get(s, 0) + 1
print(f"   senses per O success: {dict(sorted(dist.items()))}")

# 4. arm O successes with more picks than cups + 1
extra = [(k, r['n_cups'], r['rec']['metrics']['picks'], r['rec']['metrics']['places'])
         for k, r in sorted(O.items())
         if r['success'] and r['rec']['metrics']['picks'] > r['n_cups'] + 1]
print(f"4. O successes with picks > cups + 1: {len(extra)}: {extra}")
extra2 = [(k, r['n_cups'], r['rec']['metrics']['picks'], r['rec']['metrics']['places'])
          for k, r in sorted(O.items())
          if r['success'] and r['rec']['metrics']['places'] > r['n_cups']]
print(f"   O successes with places > cups (some cup placed twice): {len(extra2)}: {extra2}")

# 5. like for like over the paired (seed, rep)
pairs = sorted(set(O) & set(T))
po = [G ** t_equiv(O[k]['rec']['metrics'], True) if O[k]['success'] else 0.0 for k in pairs]
pt = [G ** t_steps(T[k]) if (T[k]['success'] and t_steps(T[k]) is not None) else 0.0 for k in pairs]
po_today = [G if O[k]['success'] else 0.0 for k in pairs]
print(f"5. over {len(pairs)} pairs: O {statistics.mean(po):.3f}, T {statistics.mean(pt):.3f}, "
      f"O today's harness {statistics.mean(po_today):.3f}; "
      f"O successes {sum(O[k]['success'] for k in pairs)}, T successes {sum(T[k]['success'] for k in pairs)}")
po_adj = [G ** (t_equiv(O[k]['rec']['metrics'], True) + (1 if O[k]['rec']['metrics']['senses'] == 0 else 0))
          if O[k]['success'] else 0.0 for k in pairs]
print(f"   O over the pairs with one look added where no sense ran: {statistics.mean(po_adj):.3f}")
po_nobs = [G ** t_equiv(O[k]['rec']['metrics'], True, observes=False) if O[k]['success'] else 0.0 for k in pairs]
print(f"   O over the pairs without observes: {statistics.mean(po_nobs):.3f}")
