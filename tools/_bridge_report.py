#!/usr/bin/env python3
"""#P4 B8's report (PAPER_AUDIT.txt P4.6 STATISTICS, TIME, B8) from one
campaign directory written by tools/_bridge_campaign.py.

Primary evidence: the paired per-seed table of repetition 1 (seed, scene
file, T outcome, O outcome, both times).  Primary test: McNemar's exact test
on the discordant seeds; secondary: Fisher's exact test, two-sided; Wilson
95 % intervals on every rate.  Repetition 2 is the stability check (per-seed
flips), never pooled with repetition 1.  Per-layout rates without tests.
Times t1 to t5 as mean +/- std and median with n, over all episodes
(censored at the cap, flagged) and success-only.  The anytime figure
(cumulative success fraction against elapsed loop time up to the cap) and
the per-seed loop-time figure (CB#111) are written as NEW files named after
the campaign directory; no existing plot is overwritten.  Arm T's agreement
with B1(g) under P4.6 ARMS' pre-registered rule is listed.  Standard
library only; matplotlib only for the figures, skipped if absent.

  python tools/_bridge_report.py CAMPAIGN_DIR [--out-dir DIR] [--no-figures]
"""
import argparse
import importlib.util
import json
import math
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCH = os.path.join(REPO, 'archive', 'tampura_bridge_plan_2026-10-25')
B1G_JSON = os.path.join(ARCH, 'bf', 'BF9_b1g', 'tampura_as_shipped_seeds0-19.json')
LAPTOP_JSON = os.path.join(ARCH, 'tampura_sweep_2026-05-26.json')


def load_bridge_gates():
    spec = importlib.util.spec_from_file_location(
        '_report_bridge_gates', os.path.join(REPO, 'tools', 'bridge_gates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----- statistics (no scipy) ------------------------------------------------

def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 3), round(c + h, 3)]


def mcnemar_exact(b, c):
    """Two-sided exact McNemar on the discordant counts b (T success, O
    failure) and c (T failure, O success): X ~ Binomial(b + c, 1/2)."""
    n = b + c
    if n == 0:
        return {'b': b, 'c': c, 'n_discordant': 0, 'p': None,
                'note': 'no discordant seed: the test is undefined'}
    k = min(b, c)
    cdf = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {'b': b, 'c': c, 'n_discordant': n, 'p': round(min(1.0, 2 * cdf), 4)}


def fisher_exact(a, b, c, d):
    """Two-sided Fisher on [[a, b], [c, d]] (rows T, O; columns success,
    failure): the sum of every table's probability at or below the
    observed one, margins fixed."""
    r1, r2, c1, n = a + b, c + d, a + c, a + b + c + d
    if n == 0:
        return None

    def pmf(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    p_obs = pmf(a)
    total = sum(pmf(x) for x in range(lo, hi + 1) if pmf(x) <= p_obs * (1 + 1e-9))
    return round(min(1.0, total), 4)


def stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {'mean': round(statistics.fmean(vals), 1),
            'std': round(statistics.pstdev(vals), 1) if len(vals) > 1 else 0.0,
            'median': round(statistics.median(vals), 1), 'n': len(vals)}


def layout_of(scene_file):
    return None if not scene_file else str(scene_file)[:10]


# ----- the campaign ---------------------------------------------------------

def load_campaign(d):
    recs = []
    with open(os.path.join(d, 'campaign.jsonl')) as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    latest = {}
    for r in recs:
        if not r.get('stalled'):
            latest[(r['arm'], r['rep'], r['seed'])] = r
    md = {}
    try:
        with open(os.path.join(d, 'campaign.json')) as f:
            md = json.load(f)
    except (OSError, ValueError):
        pass
    return latest, md, recs


def arm_rows(latest, arm, rep):
    return {k[2]: r for k, r in latest.items() if k[0] == arm and k[1] == rep}


def rate_block(rows):
    k = sum(1 for r in rows if r.get('success'))
    n = len(rows)
    statuses = {}
    for r in rows:
        statuses[r.get('status')] = statuses.get(r.get('status'), 0) + 1
    return {'n': n, 'success': k, 'rate': round(k / n, 3) if n else None,
            'wilson95': wilson(k, n), 'statuses': statuses,
            'seeds_success': sorted(r['seed'] for r in rows if r.get('success')),
            'censored': sum(1 for r in rows if r.get('censored')),
            'gate_failed': sorted(r['seed'] for r in rows if r.get('status') == 'gate_failed')}


def time_block(rows, cap):
    """t1 loop, t2 process wall, t3 time to the first reward 1.0, t4 macro
    actions (and O's raw dispatched count), t5 planning share (T: summed
    get_action spans; O: summed plan() spans, with the set-up share as its
    own column), all episodes (censored at the cap) and success-only."""
    ok = [r for r in rows if r.get('success')]
    return {
        't1_loop_s_all': stats([r.get('loop_s') for r in rows]),
        't1_loop_s_success': stats([r.get('loop_s') for r in ok]),
        't1_censored_at_cap': sum(1 for r in rows if r.get('censored')),
        't2_wall_s_all': stats([min(r.get('wall_s') or cap, cap) if r.get('censored')
                                else r.get('wall_s') for r in rows]),
        't2_wall_s_success': stats([r.get('wall_s') for r in ok]),
        't3_time_to_success_s': stats([r.get('time_to_success_s') for r in ok]),
        't4_macro_actions_success': stats([r.get('n_macro_actions') for r in ok]),
        't4_dispatched_success': stats([r.get('n_dispatched') for r in ok]),
        't5_planning_s_all': stats([r.get('planning_s') for r in rows]),
        't5_planning_s_success': stats([r.get('planning_s') for r in ok]),
        't5_setup_share_s_all': stats([r.get('setup_share_s') for r in rows]),
    }


def paired_table(t_rows, o_rows, seeds):
    rows = []
    for s in seeds:
        t, o = t_rows.get(s), o_rows.get(s)
        rows.append({
            'seed': s,
            'scene': layout_of((t or {}).get('scene_file') or (o or {}).get('scene_file')),
            'T': (t or {}).get('status'), 'O': (o or {}).get('status'),
            'T_success': bool((t or {}).get('success')), 'O_success': bool((o or {}).get('success')),
            'T_loop_s': (t or {}).get('loop_s'), 'O_loop_s': (o or {}).get('loop_s'),
            'T_censored': bool((t or {}).get('censored')), 'O_censored': bool((o or {}).get('censored')),
            'T_time_to_success_s': (t or {}).get('time_to_success_s'),
            'O_time_to_success_s': (o or {}).get('time_to_success_s'),
            'O_gate_failures': sorted(((o or {}).get('gate_failures') or {}).keys()),
            'O_scene_changed_by_settle': (o or {}).get('scene_changed_by_settle'),
        })
    return rows


def flips(rows1, rows2):
    out = []
    for s in sorted(set(rows1) & set(rows2)):
        if bool(rows1[s].get('success')) != bool(rows2[s].get('success')):
            out.append({'seed': s, 'rep1': rows1[s].get('status'), 'rep2': rows2[s].get('status')})
    return out


def b1g_agreement(t_rows, bg):
    """P4.6 ARMS: the timed block's per-seed outcomes may differ from B1(g)
    only on seeds that also flipped between the 2026-05-26 laptop block and
    B1(g) (per-seed comparable only on the same scene); otherwise both
    blocks are reported and neither is chosen."""
    try:
        b1g = {r['seed']: r for r in json.load(open(B1G_JSON))['per_seed']}
        lap = {r['seed']: r for r in json.load(open(LAPTOP_JSON))['per_seed']}
    except (OSError, ValueError, KeyError) as e:
        return {'error': f'reference blocks unavailable: {e!r}'}
    differ, allowed, not_allowed, no_reference = [], [], [], []
    for s, r in sorted(t_rows.items()):
        ref = b1g.get(s)
        if ref is None:
            continue
        if bool(r.get('success')) != bool(ref.get('success')):
            differ.append(s)
            same_scene = (bg.SCENE_MAP.get(s) == bg.SCENE_MAP_LAPTOP_2026_05_26.get(s))
            if not same_scene or s not in lap:
                no_reference.append(s)
            elif bool(lap[s].get('success')) != bool(ref.get('success')):
                allowed.append(s)
            else:
                not_allowed.append(s)
    verdict = ('the timed block agrees with B1(g) on every seed' if not differ else
               'every difference is on a seed that also flipped laptop vs B1(g): agreement holds'
               if not not_allowed and not no_reference else
               'both blocks are reported and neither is chosen (P4.6 ARMS fallback)')
    return {'b1g_success': sorted(s for s, r in b1g.items() if r.get('success')),
            'timed_success': sorted(s for s, r in t_rows.items() if r.get('success')),
            'differ': differ, 'allowed_by_laptop_flip': allowed,
            'not_allowed': not_allowed, 'no_per_seed_reference': no_reference,
            'verdict': verdict}


def anytime_curve(rows, n_seeds, cap, grid=400):
    times = sorted(r['time_to_success_s'] for r in rows.values()
                   if r.get('success') and r.get('time_to_success_s') is not None)
    xs = [cap * i / grid for i in range(grid + 1)]
    ys = [sum(1 for t in times if t <= x) / n_seeds for x in xs]
    return xs, ys


def figures(latest, seeds, cap, out_dir, tag):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return {'skipped': 'matplotlib not installed'}
    written = {}
    t1, o1 = arm_rows(latest, 'T', 1), arm_rows(latest, 'O', 1)
    # The anytime figure: cumulative success fraction against elapsed loop
    # time, both arms, repetition 1 (T: the time at solve_step; O: the time
    # of the final action), so a reader can apply any budget.
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for name, rows, color in (('TAMPURA (T)', t1, '#1f77b4'), ('Semantic Boxels (O)', o1, '#d62728')):
        xs, ys = anytime_curve(rows, len(seeds), cap)
        ax.step(xs, ys, where='post', label=name, color=color, linewidth=1.8)
    ax.set_xlim(0, cap)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel('elapsed loop time [s]')
    ax.set_ylabel(f'cumulative success fraction (n = {len(seeds)} seeds)')
    ax.set_title('find_dice, repetition 1: success against the time budget')
    ax.grid(alpha=0.3)
    ax.legend(loc='lower right')
    p = os.path.join(out_dir, f'anytime_{tag}.png')
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written['anytime'] = p
    # The per-seed loop-time figure (CB#111): both arms, repetition 1, the
    # cap as a line, censored episodes hatched, failures hollow.
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    width = 0.4
    for i, (name, rows, color) in enumerate((('T', t1, '#1f77b4'), ('O', o1, '#d62728'))):
        for j, s in enumerate(seeds):
            r = rows.get(s)
            if r is None:
                continue
            x = j + (i - 0.5) * width
            ax.bar(x, r.get('loop_s') or 0, width=width, color=color if r.get('success') else 'none',
                   edgecolor=color, hatch='//' if r.get('censored') else None,
                   label=name if j == 0 else None)
    ax.axhline(cap, color='k', linestyle='--', linewidth=0.8)
    ax.set_xticks(range(len(seeds)))
    ax.set_xticklabels([str(s) for s in seeds])
    ax.set_xlabel('seed')
    ax.set_ylabel('loop time [s] (time_deltas[-1])')
    ax.set_title('find_dice, repetition 1: loop time per seed (filled = success, hatched = censored)')
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)
    p = os.path.join(out_dir, f'looptime_{tag}.png')
    fig.tight_layout()
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written['looptime'] = p
    return written


def write_rep_jsons(latest, out_dir, md):
    """P4.6 OUTPUT: {T,O}/rep<k>.json in the 2026-05-26 JSON's per-seed shape
    plus scene_file, and for O planning_time_s, plan_count, exit_reason,
    parked_count, settle_max_disp and scene_changed_by_settle."""
    written = []
    by_arm_rep = {}
    for (arm, rep, seed), r in latest.items():
        by_arm_rep.setdefault((arm, rep), []).append(r)
    for (arm, rep), rows in sorted(by_arm_rep.items()):
        per_seed = []
        for r in sorted(rows, key=lambda x: x['seed']):
            rec = {
                'seed': r['seed'], 'success': bool(r.get('success')),
                'status': r.get('status'), 'wall_s': r.get('wall_s'),
                'loop_s': r.get('loop_s'), 'censored': bool(r.get('censored')),
                'symk_solve_s': r.get('symk_solve_s'), 'solve_step': r.get('solve_step'),
                'max_reward': r.get('max_reward'), 'n_actions': r.get('n_actions'),
                'rewards': r.get('rewards'), 'returncode': r.get('returncode'),
                'timed_out': bool(r.get('timed_out')), 'run_dir': r.get('run_dir') or r.get('save_dir'),
                'console_log': r.get('console'), 'note': r.get('note', ''),
                'scene_file': r.get('scene_file'),
                'gate_failures': sorted((r.get('gate_failures') or {}).keys()),
                'time_to_success_s': r.get('time_to_success_s'),
                'planning_time_s': r.get('planning_s'),
            }
            if arm == 'O':
                rec.update({'plan_count': r.get('plan_count'), 'exit_reason': r.get('exit_reason'),
                            'parked_count': r.get('parked_count'),
                            'settle_max_disp': r.get('settle_max_dxy_m'),
                            'scene_changed_by_settle': r.get('scene_changed_by_settle'),
                            'setup_share_s': r.get('setup_share_s'),
                            'n_dispatched': r.get('n_dispatched'),
                            'n_macro_actions': r.get('n_macro_actions')})
            per_seed.append(rec)
        d = os.path.join(out_dir, arm)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f'rep{rep}.json')
        with open(p, 'w') as f:
            json.dump({'arm': arm, 'rep': rep, 'task': 'find_dice',
                       'n_seeds': len(per_seed), 'per_seed': per_seed,
                       'snapshot': md.get('snapshot'), 'machine': md.get('machine'),
                       'protocol': md.get('protocol')}, f, indent=1, default=str)
        written.append(p)
    return written


def text_report(rep, reps):
    lines = []
    lines.append(f"campaign {rep['campaign_dir']}  status {rep['campaign_status']}  "
                 f"stop {rep['stop']}")
    lines.append(f"machine {rep['machine']}")
    lines.append('')
    lines.append(f"{'seed':>4} {'scene':<11} {'T rep1':<12} {'O rep1':<12} "
                 f"{'T loop':>8} {'O loop':>8} {'T t3':>7} {'O t3':>7}  O gates")
    for r in rep['paired_table_rep1']:
        lines.append(f"{r['seed']:>4} {r['scene'] or '?':<11} {r['T'] or '-':<12} "
                     f"{r['O'] or '-':<12} "
                     f"{str(r['T_loop_s']) + ('*' if r['T_censored'] else ''):>8} "
                     f"{str(r['O_loop_s']) + ('*' if r['O_censored'] else ''):>8} "
                     f"{str(r['T_time_to_success_s'] or '-'):>7} "
                     f"{str(r['O_time_to_success_s'] or '-'):>7}  "
                     f"{','.join(r['O_gate_failures']) or '-'}")
    lines.append('(* censored at the cap)')
    lines.append('')
    for arm in ('T', 'O'):
        for k in range(1, reps + 1):
            b = rep['rates'].get(f'{arm}_rep{k}')
            if b:
                lines.append(f"{arm} rep{k}: {b['success']}/{b['n']}  Wilson95 {b['wilson95']}  "
                             f"statuses {b['statuses']}  censored {b['censored']}")
    lines.append('')
    m = rep['mcnemar_rep1']
    lines.append(f"McNemar exact (rep 1): b = T success & O failure = {m['b']}, "
                 f"c = T failure & O success = {m['c']}, p = {m['p']}  {m.get('note', '')}")
    lines.append(f"Fisher exact two-sided (rep 1): p = {rep['fisher_rep1']}")
    lines.append('')
    lines.append('per layout (rep 1, no tests):')
    for lay, d in sorted(rep['per_layout_rep1'].items()):
        lines.append(f"  {lay}: T {d['T']['success']}/{d['T']['n']}  O {d['O']['success']}/{d['O']['n']}  "
                     f"seeds {d['seeds']}")
    lines.append('')
    for arm in ('T', 'O'):
        fl = rep['rep2_flips'].get(arm)
        if fl is not None:
            lines.append(f"rep 2 flips {arm}: {len(fl)} {[f['seed'] for f in fl]}")
    lines.append('')
    for arm in ('T', 'O'):
        t = rep['times_rep1'].get(arm)
        if t:
            lines.append(f"times {arm} (rep 1): " + json.dumps(t))
    lines.append('')
    lines.append('arm T against B1(g): ' + json.dumps(rep['b1g_agreement']))
    lines.append('')
    lines.append('figures: ' + json.dumps(rep['figures']))
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('campaign_dir')
    ap.add_argument('--out-dir', help='default: the campaign directory')
    ap.add_argument('--no-figures', action='store_true')
    args = ap.parse_args()
    d = os.path.abspath(args.campaign_dir)
    out_dir = os.path.abspath(args.out_dir or d)
    os.makedirs(out_dir, exist_ok=True)
    tag = os.path.basename(d.rstrip('/\\'))
    latest, md, recs = load_campaign(d)
    reps = max([k[1] for k in latest] or [1])
    cap = float((md.get('protocol') or {}).get('cap_s') or 900)
    seeds = sorted({k[2] for k in latest})
    bg = load_bridge_gates()
    t1, o1 = arm_rows(latest, 'T', 1), arm_rows(latest, 'O', 1)
    table = paired_table(t1, o1, seeds)
    b = sum(1 for r in table if r['T_success'] and not r['O_success'])
    c = sum(1 for r in table if not r['T_success'] and r['O_success'])
    rates = {}
    for arm in ('T', 'O'):
        for k in range(1, reps + 1):
            rows = list(arm_rows(latest, arm, k).values())
            if rows:
                rates[f'{arm}_rep{k}'] = rate_block(rows)
    per_layout = {}
    for r in table:
        lay = r['scene'] or '?'
        d_ = per_layout.setdefault(lay, {'T': {'n': 0, 'success': 0},
                                         'O': {'n': 0, 'success': 0}, 'seeds': []})
        d_['seeds'].append(r['seed'])
        for arm in ('T', 'O'):
            if r[arm] is not None:
                d_[arm]['n'] += 1
                d_[arm]['success'] += 1 if r[f'{arm}_success'] else 0
    tn, on = rates.get('T_rep1', {}), rates.get('O_rep1', {})
    rep = {
        'campaign_dir': d, 'campaign_status': md.get('status'), 'stop': md.get('stop'),
        'machine': md.get('machine'), 'protocol': md.get('protocol'),
        'snapshot': md.get('snapshot'), 'their_commits': md.get('their_commits'),
        'pip_freeze_sha256': md.get('pip_freeze_sha256'),
        'n_records': len(recs), 'seeds': seeds, 'reps': reps, 'cap_s': cap,
        'paired_table_rep1': table,
        'rates': rates,
        'mcnemar_rep1': mcnemar_exact(b, c),
        'fisher_rep1': fisher_exact(tn.get('success', 0), tn.get('n', 0) - tn.get('success', 0),
                                    on.get('success', 0), on.get('n', 0) - on.get('success', 0))
        if tn and on else None,
        'per_layout_rep1': per_layout,
        'rep2_flips': {arm: flips(arm_rows(latest, arm, 1), arm_rows(latest, arm, 2))
                       for arm in ('T', 'O') if arm_rows(latest, arm, 2)},
        'times_rep1': {arm: time_block(list(arm_rows(latest, arm, 1).values()), cap)
                       for arm in ('T', 'O') if arm_rows(latest, arm, 1)},
        'times_rep2': {arm: time_block(list(arm_rows(latest, arm, 2).values()), cap)
                       for arm in ('T', 'O') if arm_rows(latest, arm, 2)},
        'b1g_agreement': b1g_agreement(t1, bg),
        'figures': {} if args.no_figures else figures(latest, seeds, cap, out_dir, tag),
        'rep_jsons': write_rep_jsons(latest, out_dir, md),
    }
    with open(os.path.join(out_dir, f'report_{tag}.json'), 'w') as f:
        json.dump(rep, f, indent=1, default=str)
    text = text_report(rep, reps)
    with open(os.path.join(out_dir, f'report_{tag}.txt'), 'w') as f:
        f.write(text + '\n')
    print(text)
    print(f"wrote {os.path.join(out_dir, f'report_{tag}.json')} and .txt")
    return 0


if __name__ == '__main__':
    sys.exit(main())
