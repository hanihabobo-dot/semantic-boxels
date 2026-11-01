"""Peek at a loss_dynamics carry.jsonl: the non-step records and one step record."""
import json
import sys

path = sys.argv[1]
n_s = 0
for line in open(path):
    d = json.loads(line)
    if d.get('kind') == 's':
        n_s += 1
        if n_s in (1, 400):
            print('STEP', json.dumps(d)[:1500])
        continue
    print(json.dumps(d)[:300])
print('steps', n_s)
