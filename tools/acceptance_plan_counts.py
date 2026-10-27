#!/usr/bin/env python3
"""#P4 BF#13: the pre-registered plan-count test of the B5, M6 and M7
acceptances (PAPER_AUDIT P4.4 B3 ACCEPTANCE, replacing its per-seed
plan-count clause for those packages; fixed 2026-10-27, before any of
their runs).  Standard library only.

DATA.  Both arms, the reference (the commit the change applies to) and the
candidate (the change), run our holding scene on seeds 0-19 and 100-119
THREE times each, interleaved per seed (reference, candidate) in each
repetition, on one node with one harness file and one venv
(tools/cluster/acceptance_dist.sbatch, P4.6 MACHINE).

TEST.  A seed enters when all six of its runs reached the planner (a scene
the pre-flight rejects has no plan count and leaves on both arms alike; a
seed with any other missing count is listed and left out).  With R_s and
C_s the reference's and the candidate's three plan counts on seed s, the
statistic is T = sum over the seeds of (mean C_s - mean R_s).  Under the
null hypothesis that the change leaves each seed's plan-count distribution
unchanged, the six counts of a seed are exchangeable between the arms: T is
recomputed under 20000 random three-to-three splits of every seed's six
counts (random.Random(0)), and p is the share of draws with |T*| >= |T|.
The plan-count clause PASSES when p >= 0.05.  The outcome clause (flips up
to the A/A count; repetition 2 is each flipped seed's one re-run on both
arms; a flip that reproduces fails) and the identical-target clause are
unchanged.

Usage:
  acceptance_plan_counts.py --ref J [J ...] --cand J [J ...] [--out F]
where J are tools/_eval_ab.py result JSONs; every run of a seed in the
given files counts, in file order.
"""
import argparse
import json
import random

DRAWS = 20000
RNG_SEED = 0
ALPHA = 0.05
RUNS_PER_ARM = 3


def load_runs(paths):
    """seed -> [plans_executed of each run], in file order."""
    runs = {}
    for path in paths:
        with open(path) as f:
            for r in json.load(f)['results']:
                runs.setdefault(r['seed'], []).append(r['plans_executed'])
    return runs


def plan_count_test(ref, cand, draws=DRAWS, rng_seed=RNG_SEED):
    seeds, skipped, rejected = [], [], []
    for s in sorted(set(ref) | set(cand)):
        r, c = ref.get(s, []), cand.get(s, [])
        if r and c and all(v is None for v in r + c):
            rejected.append(s)            # the pre-flight rejected the scene
        elif (len(r) == RUNS_PER_ARM and len(c) == RUNS_PER_ARM
              and None not in r + c):
            seeds.append(s)
        else:
            skipped.append(s)
    n = RUNS_PER_ARM
    t_obs = sum(sum(cand[s]) / n - sum(ref[s]) / n for s in seeds)
    pools = [list(ref[s]) + list(cand[s]) for s in seeds]
    rng = random.Random(rng_seed)
    hits = 0
    for _ in range(draws):
        t = 0.0
        for pool in pools:
            pick = rng.sample(range(2 * n), n)
            a = sum(pool[i] for i in pick)
            t += (sum(pool) - a) / n - a / n
        if abs(t) >= abs(t_obs) - 1e-12:
            hits += 1
    p = hits / draws
    return {'seeds': seeds, 'preflight_rejected': rejected,
            'skipped_incomplete': skipped, 'T': t_obs,
            'mean_shift_per_seed': t_obs / len(seeds) if seeds else None,
            'p': p, 'alpha': ALPHA, 'draws': draws, 'rng_seed': rng_seed,
            'pass': p >= ALPHA}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ref', nargs='+', required=True)
    ap.add_argument('--cand', nargs='+', required=True)
    ap.add_argument('--out')
    a = ap.parse_args()
    res = plan_count_test(load_runs(a.ref), load_runs(a.cand))
    print(f"plan-count test (BF#13): {len(res['seeds'])} seeds, T = "
          f"{res['T']:+.3f} plans ({res['mean_shift_per_seed']:+.3f} per seed), "
          f"p = {res['p']:.4f} -> {'PASS' if res['pass'] else 'FAIL'}; "
          f"pre-flight rejected {res['preflight_rejected']}; incomplete "
          f"{res['skipped_incomplete']}")
    if a.out:
        with open(a.out, 'w') as f:
            json.dump(res, f, indent=1)


if __name__ == '__main__':
    main()
