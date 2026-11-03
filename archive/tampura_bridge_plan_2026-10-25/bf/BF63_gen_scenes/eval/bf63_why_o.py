"""BF#63: for each arm O run that is not a counted success, where the die
truly was (the world eye's last record) and what the pipeline believed
about the object hiding it.  Usage: python -I bf63_why_o.py <eval dir>"""
import collections, glob, json, os, sys

ev = sys.argv[1]
tally = collections.Counter()
for d in sorted(glob.glob(os.path.join(ev, '50630*', 'failures', 'O_s*'))):
    meta = json.load(open(os.path.join(d, 'meta.json'), encoding='utf-8'))
    if meta.get('counts') is False:
        continue
    eye_p = os.path.join(d, 'eye_last.json')
    if not os.path.isfile(eye_p):
        print(os.path.basename(d), 'no eye_last.json'); continue
    e = json.loads(open(eye_p, encoding='utf-8').read().strip().splitlines()[-1])
    objs = {o['name']: o for o in e.get('objects', [])}
    die = next((o for o in objs.values() if o.get('role') == 'target'), None)
    hb = die.get('hidden_by') if die else None
    host = objs.get(hb, {}) if hb else {}
    b = e.get('belief') or {}
    outcome = 'timeout' if meta.get('timed_out') else meta.get('outcome_pipeline')
    key = (outcome, 'die hidden_by ' + ('none (visible)' if not hb else 'a cup'),
           'that cup is_occluder=' + str(host.get('is_occluder')) if hb else '-',
           'shadows ' + ('none' if hb and not host.get('shadow_ids') else 'some' if hb else '-'))
    tally[key] += 1
    # the die under its cup: its true xy inside the cup's true footprint
    under = None
    if hb and host.get('true_aabb') and die.get('true_pos'):
        (x0, y0, _), (x1, y1, _) = host['true_aabb']
        under = x0 <= die['true_pos'][0] <= x1 and y0 <= die['true_pos'][1] <= y1
    print(f"{os.path.basename(d):16} cups {meta.get('n_cups')}  {outcome:28} die tilt {die.get('tilt_deg') if die else '?'}"
          f"  z {die['true_pos'][2] if die and die.get('true_pos') else '?'}  inside the cup's footprint {under}"
          f"  visible_px {die.get('visible_px') if die else '?'}  hidden_by {hb}  host is_occluder {host.get('is_occluder')}"
          f"  host shadows {host.get('shadow_ids')}  unknown {b.get('unknown')}  known_empty {len(b.get('known_empty') or [])}"
          f"  moved {len(b.get('occluders_moved') or {})}")
print()
for k, n in tally.most_common():
    print(n, ' | '.join(k))
