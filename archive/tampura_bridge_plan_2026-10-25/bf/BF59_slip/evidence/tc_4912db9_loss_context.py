#!/usr/bin/env python3
"""BF#59 recon: for every episode of the per-fix eval that ended
'failure' (the lost die) print the lines of its stdout.txt that tell where
the die was lost, plus the tail; and for a few successes the same lines, as
the contrast.  Read only.  Usage: python loss_context.py <job dir>... > out"""
import json
import os
import re
import sys

PAT = re.compile(r"Picking dice|grip verified|half-width|\[F24\]|post-lift|re-verify|"
                 r"\[integrity\]|\[release-obs\]|finger-pad|physics_mismatch|lost|LOST|"
                 r"slip|drop verif|Moving to|move\(|direct path|hold_at_config|at home|"
                 r"goal check|outcome|pick_giveup|strike|Placing|released|GOAL|home",
                 re.I)

for job in sys.argv[1:]:
    rows = [json.loads(l) for l in open(os.path.join(job, 'results.jsonl')) if l.strip()]
    for r in rows:
        if r.get('bridge_status') not in ('failure',):
            continue
        sd = r['save_dir']
        if not os.path.isdir(sd):
            sd = os.path.join(job, r['arm'], f"seed{r['seed']:02d}")
        so = os.path.join(sd, 'stdout.txt')
        print(f"\n===== seed {r['seed']} arm {r['arm']} wall {r['process_wall_s']} "
              f"outcome {r.get('metrics', {}).get('outcome')} =====")
        try:
            lines = open(so, errors='replace').read().splitlines()
        except OSError as e:
            print(f"  (no stdout: {e})")
            continue
        hits = [(i, l) for i, l in enumerate(lines) if PAT.search(l)]
        # the last 60 matching lines are where the die went
        for i, l in hits[-60:]:
            print(f"{i:5d}: {l[:220]}")
        print("  --- tail ---")
        for l in lines[-12:]:
            print(f"       {l[:220]}")
