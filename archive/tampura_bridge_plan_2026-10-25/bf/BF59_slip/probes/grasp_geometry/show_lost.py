"""Print the first-loss record and the home state of every probe grip."""
import json
import sys

for f in sys.argv[1:]:
    for r in json.load(open(f))['rows']:
        if not r.get('grip'):
            continue
        print(f"d {r['delta_deg']:4.1f} k{r['k90']} {r['cell']} held {r['held']!s:5s} "
              f"steps {r.get('carry_steps')} lost {r.get('lost')} home {r.get('home_die')} "
              f"tiltmax {r.get('tilt_max')}")
