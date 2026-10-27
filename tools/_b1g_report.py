"""#P4 B1(g) report: TAMPURA as shipped on the chair's cluster beside the
2026-05-26 laptop block, per layout (PAPER_AUDIT.txt #P4, BF#8, BF#9).

The two blocks map seeds to scenes differently (BF#8): the laptop block's
layout per seed is tools/bridge_gates.py's SCENE_MAP_LAPTOP_2026_05_26 (from
that run's consoles), the cluster block's is each record's own scene_file.
Seeds are compared one to one only where both runs loaded the same scene;
everything else is compared per layout.

  python tools/_b1g_report.py CLUSTER_JSON [--laptop LAPTOP_JSON] [--out OUT_JSON]
"""
import argparse
import importlib.util
import json
import math
import os
import statistics

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'bridge_gates', os.path.join(REPO, 'tools', 'bridge_gates.py'))
bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bg)
LAPTOP_JSON = os.path.join(REPO, 'archive', 'tampura_bridge_plan_2026-10-25',
                           'tampura_sweep_2026-05-26.json')


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 3), round(c + h, 3)]


def layout_of(scene_file):
    return None if scene_file is None else str(scene_file)[:10]


def summary(rows):
    k = sum(1 for r in rows if r['success'])
    loops = [r['loop_s'] for r in rows if r.get('loop_s') is not None]
    ok = [r['loop_s'] for r in rows if r['success'] and r.get('loop_s') is not None]
    def stats(v):
        if not v:
            return None
        return {'mean': round(statistics.fmean(v), 1),
                'std': round(statistics.pstdev(v), 1) if len(v) > 1 else 0.0,
                'median': round(statistics.median(v), 1), 'n': len(v)}
    return {'n': len(rows), 'success': k, 'rate': round(k / len(rows), 3)
            if rows else None, 'wilson95': wilson(k, len(rows)),
            'loop_s_all': stats(loops), 'loop_s_success': stats(ok),
            'seeds': sorted(r['seed'] for r in rows)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cluster_json')
    ap.add_argument('--laptop', default=LAPTOP_JSON)
    ap.add_argument('--out')
    args = ap.parse_args()
    cl = json.load(open(args.cluster_json))
    lp = json.load(open(args.laptop))
    crow = {r['seed']: dict(r, layout=layout_of(r.get('scene_file')))
            for r in cl['per_seed']}
    lrow = {r['seed']: dict(r, layout=bg.SCENE_MAP_LAPTOP_2026_05_26.get(r['seed']))
            for r in lp['per_seed']}
    layouts = sorted({r['layout'] for r in list(crow.values()) + list(lrow.values())
                      if r['layout']})
    rep = {'cluster_machine': cl.get('machine'), 'per_layout': {},
           'pooled': {'cluster': summary(list(crow.values())),
                      'laptop_2026_05_26': summary(list(lrow.values()))},
           'same_scene_seeds': [], 'scene_check': []}
    for seed, r in sorted(crow.items()):
        pinned = bg.SCENE_MAP.get(seed)
        rep['scene_check'].append({'seed': seed, 'loaded': r['layout'],
                                   'pinned_cluster_map': pinned,
                                   'match': r['layout'] == pinned})
    for lay in layouts:
        rep['per_layout'][lay] = {
            'cluster': summary([r for r in crow.values() if r['layout'] == lay]),
            'laptop_2026_05_26': summary([r for r in lrow.values()
                                          if r['layout'] == lay])}
    for seed in sorted(set(crow) & set(lrow)):
        if crow[seed]['layout'] == lrow[seed]['layout']:
            rep['same_scene_seeds'].append({
                'seed': seed, 'layout': crow[seed]['layout'],
                'cluster_success': crow[seed]['success'],
                'laptop_success': lrow[seed]['success'],
                'cluster_loop_s': crow[seed].get('loop_s'),
                'laptop_loop_s': lrow[seed].get('loop_s')})

    print(f"cluster machine: {rep['cluster_machine']}")
    bad = [c for c in rep['scene_check'] if not c['match']]
    print(f"scene check against bridge_gates.SCENE_MAP: "
          f"{'all 20 match' if not bad and len(rep['scene_check']) == 20 else bad or 'incomplete'}")
    print(f"{'layout':<12}{'block':<20}{'success':>9}{'wilson95':>16}"
          f"{'loop_s all mean/median':>26}{'seeds':>40}")
    for lay, d in rep['per_layout'].items():
        for blk in ('cluster', 'laptop_2026_05_26'):
            s = d[blk]
            la = s['loop_s_all'] or {}
            print(f"{lay:<12}{blk:<20}{s['success']:>4}/{s['n']:<4}"
                  f"{str(s['wilson95']):>16}"
                  f"{str(la.get('mean')) + ' / ' + str(la.get('median')):>26}"
                  f"{str(s['seeds']):>40}")
    for blk in ('cluster', 'laptop_2026_05_26'):
        s = rep['pooled'][blk]
        print(f"{'pooled':<12}{blk:<20}{s['success']:>4}/{s['n']:<4}"
              f"{str(s['wilson95']):>16}  loop_s all {s['loop_s_all']}  "
              f"success {s['loop_s_success']}")
    flips = [x for x in rep['same_scene_seeds']
             if x['cluster_success'] != x['laptop_success']]
    print(f"same-scene seeds {[x['seed'] for x in rep['same_scene_seeds']]}: "
          f"{len(flips)} outcome flip(s) {[x['seed'] for x in flips]}")
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(rep, f, indent=1)
        print('wrote', args.out)


if __name__ == '__main__':
    main()
