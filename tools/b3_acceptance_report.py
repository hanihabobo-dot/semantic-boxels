#!/usr/bin/env python3
"""#P4 B3's acceptance (PAPER_AUDIT P4.4 B3, BF#10): the A/A of c31cbdd and
the A/B of a B3 commit against it, from tools/_eval_ab.py's JSONs and the
runs' own logs.  Standard library only.

Pre-registered rule: outcome flips between the A/B arms are accepted up to
the A/A's flip count; each flipped seed gets ONE re-run on both arms and a
flip that reproduces fails; plan-count differences follow the same rule;
Phase-4 target choices must be identical (they precede any wall-clock
search).  This script counts and lists; the re-runs are their own jobs.

Usage:
  b3_acceptance_report.py --aa1 J [J ...] --aa2 J [J ...] --aa-logs DIR
                          [--ab J [J ...] --ab-logs DIR] [--out report.json]
The A/A writes both repetitions' runs into one logs directory: a seed's
first run (by run-directory time) is repetition 1, its second repetition 2.
"""
import argparse
import json
import os
import re

SEED_RE = re.compile(r'^\s+seed\s+=\s+(\d+)\s*$', re.M)
TARGET_RE = re.compile(r'^\s+Target:\s+(\S+)', re.M)


def load_arm(paths):
    out = {}
    for path in paths:
        with open(path) as f:
            for r in json.load(f)['results']:
                out[r['seed']] = r
    return out


def run_targets(log_dir):
    """seed -> [Phase-4 target of each run, in run-directory time order]."""
    seen = {}
    for name in sorted(os.listdir(log_dir)):
        run = os.path.join(log_dir, name)
        log = os.path.join(run, name + '.log')
        if not (name.startswith('run_') and os.path.isfile(log)):
            continue
        with open(log, encoding='utf-8', errors='replace') as f:
            text = f.read()
        s, t = SEED_RE.search(text), TARGET_RE.search(text)
        if s:
            seen.setdefault(int(s.group(1)), []).append(t.group(1) if t else None)
    return seen


def compare(a, b, field):
    return sorted(s for s in a if s in b and a[s].get(field) != b[s].get(field))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aa1', nargs='+', required=True)
    ap.add_argument('--aa2', nargs='+', required=True)
    ap.add_argument('--aa-logs', required=True)
    ap.add_argument('--ab', nargs='*', default=[])
    ap.add_argument('--ab-logs')
    ap.add_argument('--rerun-a', help="the re-runs' c31cbdd JSON")
    ap.add_argument('--rerun-b', help="the re-runs' B3 JSON")
    ap.add_argument('--out')
    args = ap.parse_args()

    a1, a2 = load_arm(args.aa1), load_arm(args.aa2)
    aa_t = run_targets(args.aa_logs)
    for s, r in a1.items():
        runs = aa_t.get(s, [])
        r['target'] = runs[0] if runs else None
    for s, r in a2.items():
        runs = aa_t.get(s, [])
        r['target'] = runs[1] if len(runs) > 1 else None
    rep = {
        'seeds': sorted(a1),
        'aa': {
            'success_rep1': sum(r['success'] for r in a1.values()),
            'success_rep2': sum(r['success'] for r in a2.values()),
            'outcome_flips': compare(a1, a2, 'success'),
            'plan_count_diffs': compare(a1, a2, 'plans_executed'),
            'target_diffs': compare(a1, a2, 'target'),
            'no_run': sorted(s for s in a1 if a1[s]['plans_executed'] is None
                             and not a1[s]['success']),
        },
        'per_seed': {s: {'rep1': [a1[s]['success'], a1[s]['plans_executed'],
                                  a1[s]['target']],
                         'rep2': [a2[s]['success'], a2[s]['plans_executed'],
                                  a2[s]['target']]}
                     for s in sorted(a1)},
    }
    print(f"A/A c31cbdd: rep1 {rep['aa']['success_rep1']}/{len(a1)}, "
          f"rep2 {rep['aa']['success_rep2']}/{len(a2)}; outcome flips "
          f"{len(rep['aa']['outcome_flips'])} {rep['aa']['outcome_flips']}; "
          f"plan-count diffs {len(rep['aa']['plan_count_diffs'])} "
          f"{rep['aa']['plan_count_diffs']}; target diffs "
          f"{rep['aa']['target_diffs']}; no run (pre-flight) "
          f"{rep['aa']['no_run']}")

    if args.ab:
        b = load_arm(args.ab)
        ab_t = run_targets(args.ab_logs)
        for s, r in b.items():
            runs = ab_t.get(s, [])
            r['target'] = runs[0] if runs else None
        flips = compare(a1, b, 'success')
        plans = compare(a1, b, 'plans_executed')
        targets = compare(a1, b, 'target')
        n_aa, n_aa_p = len(rep['aa']['outcome_flips']), len(rep['aa']['plan_count_diffs'])
        rep['ab'] = {
            'success_b3': sum(r['success'] for r in b.values()),
            'outcome_flips': flips,
            'outcome_flip_directions': {s: [a1[s]['success'], b[s]['success']]
                                        for s in flips},
            'plan_count_diffs': plans,
            'target_diffs': targets,
            'outcome_within_noise': len(flips) <= n_aa,
            'plan_counts_within_noise': len(plans) <= n_aa_p,
            'targets_identical': not targets,
            'rerun_seeds': flips,
        }
        for s in sorted(b):
            rep['per_seed'].setdefault(s, {})['b3'] = [
                b[s]['success'], b[s]['plans_executed'], b[s]['target']]
        print(f"A/B B3 vs c31cbdd rep1: B3 {rep['ab']['success_b3']}/{len(b)}; "
              f"outcome flips {len(flips)} {rep['ab']['outcome_flip_directions']} "
              f"(A/A {n_aa}); plan-count diffs {len(plans)} (A/A {n_aa_p}); "
              f"target diffs {targets}")
        ok = (rep['ab']['outcome_within_noise'] and rep['ab']['plan_counts_within_noise']
              and rep['ab']['targets_identical'])
        print(f"within the pre-registered noise: {ok}; one re-run on both arms "
              f"for seeds {sorted(set(flips) | set(plans))}")

        if args.rerun_a and args.rerun_b:
            # A difference REPRODUCES when the re-run gives each arm the
            # same outcome (an outcome flip) or the same plan count (a
            # plan-count difference) it had in the A/B (b3_rerun.sbatch).
            ra, rb = load_arm([args.rerun_a]), load_arm([args.rerun_b])
            rows, rep_flips, rep_plans = {}, [], []
            for s in sorted(set(flips) | set(plans)):
                if s not in ra or s not in rb:
                    rows[s] = 'not re-run'
                    continue
                pair_ab = ((a1[s]['success'], a1[s]['plans_executed']),
                           (b[s]['success'], b[s]['plans_executed']))
                pair_rr = ((ra[s]['success'], ra[s]['plans_executed']),
                           (rb[s]['success'], rb[s]['plans_executed']))
                if s in flips and (pair_rr[0][0], pair_rr[1][0]) == \
                        (pair_ab[0][0], pair_ab[1][0]):
                    rep_flips.append(s)
                if s in plans and (pair_rr[0][1], pair_rr[1][1]) == \
                        (pair_ab[0][1], pair_ab[1][1]):
                    rep_plans.append(s)
                rows[s] = {'ab': pair_ab, 'rerun': pair_rr}
            rep['rerun'] = {'per_seed': rows, 'reproduced_outcome_flips': rep_flips,
                            'reproduced_plan_count_diffs': rep_plans,
                            'pass': not rep_flips and not rep_plans}
            for s, r in rows.items():
                print(f"  seed {s}: A/B {r['ab'] if isinstance(r, dict) else r}"
                      f"  re-run {r['rerun'] if isinstance(r, dict) else ''}")
            print(f"re-runs: reproduced outcome flips {rep_flips}, reproduced "
                  f"plan-count differences {rep_plans}; acceptance "
                  f"{'PASSES' if (ok and rep['rerun']['pass']) else 'FAILS'}")
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(rep, f, indent=1)


if __name__ == '__main__':
    main()
