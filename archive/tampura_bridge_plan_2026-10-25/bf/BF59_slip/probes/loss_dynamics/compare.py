"""Determinism check: compare two or more carry.jsonl recordings of the same
episode step by step from the die pick's start.  Prints the event lists,
whether the step rows are identical, and the first differing step.
Usage: python compare.py a.jsonl b.jsonl [c.jsonl ...]"""
import json
import sys


def load(path):
    rows = [json.loads(l) for l in open(path)]
    ev = [(r['kind'], r.get('step'), r.get('ok'), r.get('reason'), r.get('label'))
          for r in rows if r['kind'] in ('pick_start', 'pick_done', 'goal_check',
                                         'hold_done', 'end', 'phase')]
    st = [r for r in rows if r['kind'] == 's']
    return ev, st


def main(paths):
    base_ev, base_st = load(paths[0])
    print(paths[0], 'events', [e for e in base_ev if e[0] != 'phase'][-6:],
          'steps', len(base_st))
    for p in paths[1:]:
        ev, st = load(p)
        print(p, 'events', [e for e in ev if e[0] != 'phase'][-6:], 'steps', len(st))
        same_ev = ev == base_ev
        first = None
        for a, b in zip(base_st, st):
            if a != b:
                first = (a['step'], a['wp'],
                         {k: v for k, v in a.items() if a[k] != b.get(k)}.keys())
                break
        print('  events identical:', same_ev, ' step rows identical:',
              first is None and len(st) == len(base_st),
              ' first differing step:', first)
        if first is not None:
            a = next(r for r in base_st if r['step'] == first[0])
            b = next(r for r in st if r['step'] == first[0])
            for k in first[2]:
                print('   ', k, a[k], '|', b[k])


if __name__ == '__main__':
    main(sys.argv[1:])
