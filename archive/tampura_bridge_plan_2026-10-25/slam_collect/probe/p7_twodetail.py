"""P7: print the step log of two-belief episodes (reads out/twobelief_<R>.json, prints only).
Usage: python3 p7_twodetail.py <file tag, e.g. S2o or S4o_seeds100> <seed> <rep> [<seed> <rep> ...]"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
rows = json.load(open(os.path.join(OUT, f'twobelief_{sys.argv[1]}.json')))
args = sys.argv[2:]
for i in range(0, len(args), 2):
    seed, rep = int(args[i]), int(args[i + 1])
    r = next(x for x in rows if x['seed'] == seed and x['rep'] == rep)
    print(f"== {sys.argv[1]} seed {seed} rep {rep} replica {r['replica_success']} world_end {r['world_success_end']}"
          f" stopped {r['acting_done_step']}")
    for e in r['log']:
        if e.get('inapplicable'):
            print(f"  t{e['step']:>2} {e['action']:<34} INAPPLICABLE on the acting abstraction -> no-op")
            continue
        atoms = [a for a in e['acting_atoms'] if not a.startswith('target_in(o_target') or 'goal' in a]
        print(f"  t{e['step']:>2} {e['action']:<34} prim {e['primitives']:>3} hold {e['obs_holding']} coll {e['obs_collision']}"
              f" removed {e['removed_by_failed_pick']} var {e['acting_var']} err {e['err_mean_true']}"
              f" replica_coll {e['replica_in_collision']} r {e['replica_reward']} world {e['world']} atoms {atoms}")
