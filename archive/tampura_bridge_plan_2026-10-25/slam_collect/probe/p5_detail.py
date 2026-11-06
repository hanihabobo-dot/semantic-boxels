"""P5: print the step log of scripted episodes (reads out/policies_<P>.json, prints only).
Usage: python3 p5_detail.py <policy> <seed> <rep> [<seed> <rep> ...]"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
rows = json.load(open(os.path.join(OUT, f'policies_{sys.argv[1]}.json')))
args = sys.argv[2:]
for i in range(0, len(args), 2):
    seed, rep = int(args[i]), int(args[i + 1])
    r = next(x for x in rows if x['seed'] == seed and x['rep'] == rep)
    print(f"== {sys.argv[1]} seed {seed} rep {rep} success {r['success_belief']} world {r['world_success']}")
    for e in r['log']:
        if e.get('inapplicable'):
            print(f"  t{e['step']:>2} {e['action']:<34} INAPPLICABLE on their spec -> no-op")
            continue
        atoms = [a for a in e['atoms'] if not a.startswith('target_in(o_target') or 'goal' in a]
        print(f"  t{e['step']:>2} {e['action']:<34} prim {e['primitives']:>3} regions {e['obs_regions']} "
              f"hold {e['obs_holding']} pose {e['obs_pose']} coll {e['obs_collision']} "
              f"var {e['belief_var']} err {e['err_mean_true']} r {e['reward']} atoms {atoms}")
