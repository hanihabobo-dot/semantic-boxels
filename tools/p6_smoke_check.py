#!/usr/bin/env python3
"""Path 6: the cluster smoke's verdict (PLAN.md section 11, stop and pause rules).

  python tools/p6_smoke_check.py <smoke folder>     (stdlib only; runs on the
  node at the end of tools/cluster/p6_tabletop.sbatch's smoke mode, and on the
  laptop on the pulled tarball)

The folder holds B/slot_smoke/ and A/slot_smoke/ (cells/<tag>/timing_summary.json
each).  Three rules, declared before the first run:

  STOP   arm B's first-replan boxel counts (object, shadow, free-space) differ
         from the thesis sweep's rows for the same cells (holding 2/2/13,
         tray-stack 4/5/16, stack 3/3/16), or a smoke cell of either arm
         produced no pipeline summary (crash, no summary, summary mismatch,
         pre-flight rejection, timeout): B's code and scenes are not reproduced
         in the cluster venv, or the job script is broken.  Nothing else is
         submitted; it goes to Hani.
  PAUSE  the median wall-time ratio of B's three cells to the sweep's rows for
         the same cells (holding 9.5 s, tray-stack 15.6 s, stack 5.4 s) is above
         3.0: the cost and the number of cells that reach the 1800 s cap both
         change, so wave 1 waits for Hani and Go.
  PASS   neither.

Exit code 0 PASS, 3 STOP, 4 PAUSE.  The verdict line starts with SMOKE_VERDICT.
"""
import json
import os
import statistics
import sys

# the thesis sweep's rows for the three cells (PLAN section 11 and 12)
EXPECTED_B = {
    'randpairs_occ2_seed2_holding_uc0_semantic':
        {'counts': (2, 2, 13), 'sweep_wall_s': 9.5, 'label': 'holding occ2 seed2'},
    'randpairs_occ2_seed2_find-and-tray-stack_uc0_semantic':
        {'counts': (4, 5, 16), 'sweep_wall_s': 15.6, 'label': 'tray-stack occ2 seed2'},
    'occ2_tgt3_hid0_seed0_stack_uc0_semantic':
        {'counts': (3, 3, 16), 'sweep_wall_s': 5.4, 'label': 'stack h2 seed0'},
}
PAUSE_RATIO = 3.0


def load_summary(folder, arm, tag):
    p = os.path.join(folder, arm, 'slot_smoke', 'cells', tag, 'timing_summary.json')
    if not os.path.isfile(p):
        return None
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def first_replan_counts(ts):
    per = ts.get('boxel_counts_per_replan') or []
    if not per:
        return None
    e = per[0]
    return (e.get('n_object_boxels'), e.get('n_shadow_boxels'), e.get('n_free_space_boxels'))


def is_pipeline_summary(ts):
    """A summary the pipeline wrote (it carries a run_config), not a runner stub."""
    return isinstance(ts, dict) and isinstance(ts.get('run_config'), dict)


def check(folder):
    lines, stop, ratios = [], [], []
    for arm in ('B', 'A'):
        lines.append(f"arm {arm}:")
        for tag, exp in EXPECTED_B.items():
            ts = load_summary(folder, arm, tag)
            if not is_pipeline_summary(ts):
                why = (ts or {}).get('exit_reason', 'no summary file') if ts is not None else 'no summary file'
                lines.append(f"  {exp['label']:24} NO PIPELINE SUMMARY ({why})")
                stop.append(f"arm {arm} {exp['label']}: no pipeline summary ({why})")
                continue
            counts = first_replan_counts(ts)
            wall = ts.get('wall_clock_s')
            row = (f"  {exp['label']:24} success {ts.get('success')}  plans {ts.get('plan_count')}  "
                   f"wall {wall} s  planning {ts.get('total_planning_time_s')} s  "
                   f"first-replan boxels object/shadow/free {counts}")
            if arm == 'B':
                ok = counts == exp['counts']
                row += (f"  = the sweep's {exp['counts']}" if ok
                        else f"  DIFFERS from the sweep's {exp['counts']}")
                if not ok:
                    stop.append(f"arm B {exp['label']}: first-replan counts {counts}, sweep {exp['counts']}")
                if wall:
                    ratios.append(wall / exp['sweep_wall_s'])
                    row += f"  wall ratio {wall / exp['sweep_wall_s']:.2f}"
            lines.append(row)
    median = statistics.median(ratios) if ratios else None
    lines.append(f"B's median wall-time ratio to the sweep's rows: "
                 + (f"{median:.2f} (pause above {PAUSE_RATIO})" if median is not None else 'not available'))
    if stop:
        verdict, rc = 'STOP', 3
        why = '; '.join(stop)
    elif median is not None and median > PAUSE_RATIO:
        verdict, rc = 'PAUSE', 4
        why = f"median wall ratio {median:.2f} above {PAUSE_RATIO}"
    else:
        verdict, rc = 'PASS', 0
        why = f"B's first-replan counts equal the sweep's in all {len(EXPECTED_B)} cells, median wall ratio " + (
            f"{median:.2f}" if median is not None else 'n/a')
    lines.append(f"SMOKE_VERDICT {verdict}: {why}")
    return rc, '\n'.join(lines)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    rc, text = check(argv[0])
    print(text)
    return rc


if __name__ == '__main__':
    sys.exit(main())
