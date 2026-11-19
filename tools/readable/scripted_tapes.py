"""scripted_tapes.py: the scripted tapes of pin 47 (PLAN 5.2 row 47 "one
scripted sense-only plan per sense outcome", REVIEW_PHASE0 B3).

A scripted tape is made from a live tape of ``record_episode.py
--record-set`` (READABLE_TAPES) by rules over the live episode's normalised
ledger, never by hand-written stream objects: every action a scripted call
returns is one the live search returned (replay_stub.scripted_solution).
A scripted tape holds, in call order:

  live calls      copied as they are (solution, text, RNG, facts), so the
                  replay reaches the same world state as the live episode;
  scripted calls  a live call's plan cut to some of its actions (a plan
                  split before a sense, a sense alone, a pick alone), an
                  argument replaced by a text (a shadow no registry holds),
                  or no plan at all (the episode's end).

Some scenarios also name executor stubs (tests/readable/executor_stubs.py,
test-level, allowed by pin 47) that force a physical failure no live
episode is sure to reach.  The rules choose their source by the live
ledger (the first plan with a sense of a given outcome, the first plan with
a place, the last plan that ends with a move to q_home after a pick), so a
fresh ``--record-set`` on tag 2, whose searches differ from run to run,
still gives each scenario its branch; a set that has no source for a rule
makes the pin error with the rule's name, never pass.

    python tools/readable/scripted_tapes.py --tapes TAPES --scenario NAME --out DIR
    python tools/readable/scripted_tapes.py --list
"""
import argparse
import hashlib
import json
import pickle
import shutil
import sys
from pathlib import Path

# Candidate sources: the episodes ``record_episode.py --record-set`` records
# by default (PIN47_EPISODES), in the order a rule tries them.
BOXELS = ('rp0', 'rp1o3')
BRIDGE = ('br0', 'br5')
NO_SHADOW = 'shadow_of_no_such_body'


class NoSource(RuntimeError):
    """No live episode of the tape set gives this scenario its source."""


class Live:
    """One live episode of a tape set: its tape rows and its plans."""

    def __init__(self, root, name):
        self.name = name
        self.dir = Path(root) / name
        tape = self.dir / 'tape'
        if not (tape / 'calls.jsonl').exists():
            raise NoSource(f'no live tape {tape}')
        self.tape = tape
        self.calls = [json.loads(x) for x in (tape / 'calls.jsonl').read_text(encoding='utf-8').splitlines()
                      if x.strip()]
        ledger = json.loads((self.dir / 'norm' / 'ledger.json').read_text(encoding='utf-8'))
        self.plans = []
        cur = None
        for r in ledger:
            kind = r.get('kind')
            if kind == 'plan':
                cur = {'k': len(self.plans), 'plan_id': r.get('plan_id'), 'call': r.get('call'),
                       'actions': r.get('actions') or [], 'steps': {}}
                self.plans.append(cur)
            elif cur is not None and kind == 'step':
                cur['steps'][r['step']] = {'action': r.get('action'), 'args': r.get('args'),
                                           'status': None, 'sense': None}
            elif cur is not None and kind == 'step_end' and r.get('step') in cur['steps']:
                cur['steps'][r['step']]['status'] = r.get('status')
            elif cur is not None and kind == 'sense_result' and r.get('step') in cur['steps']:
                cur['steps'][r['step']]['sense'] = r.get('reason')
            elif cur is not None and kind == 'at_home_test' and r.get('step') in cur['steps']:
                cur['steps'][r['step']]['at_home'] = r.get('passed')
        if len(self.plans) != len(self.calls):
            raise NoSource(f'{name}: {len(self.plans)} plan rows but {len(self.calls)} solver calls')


def _sources(root, names):
    out = []
    for n in names:
        try:
            out.append(Live(root, n))
        except NoSource:
            continue
    return out


class Builder:
    """Writes a scripted tape folder call by call."""

    def __init__(self, out_dir, live):
        self.out = Path(out_dir)
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        self.live = live
        self.rows = []
        self.restored = set()

    def _copy(self, k_src, k, rng):
        src = self.live.tape
        shutil.copyfile(src / f'solution_{k_src:04d}.pkl', self.out / f'solution_{k:04d}.pkl')
        if rng and (src / f'rng_{k_src:04d}.pkl').exists():
            shutil.copyfile(src / f'rng_{k_src:04d}.pkl', self.out / f'rng_{k:04d}.pkl')

    def live_call(self, k_src):
        """Live call k_src as it is (its facts, goal and RNG are checked)."""
        k = len(self.rows)
        self._copy(k_src, k, rng=True)
        shutil.copyfile(self.live.tape / f'text_{k_src:04d}.json', self.out / f'text_{k:04d}.json')
        row = dict(self.live.calls[k_src], k=k, source_call=k_src, source=self.live.name)
        self.restored.add(k_src)
        self.rows.append(row)

    def cut(self, k_src, actions, replace_args=None, why=''):
        """Live call k_src's plan cut to `actions` (indices).  The first
        scripted call made from a live call restores that call's RNG and
        stream counters (the live state after it); later ones keep the
        replay's own."""
        k = len(self.rows)
        rng = k_src not in self.restored
        self.restored.add(k_src)
        self._copy(k_src, k, rng=rng)
        (self.out / f'text_{k:04d}.json').write_text('[]\n', encoding='utf-8', newline='\n')
        live = self.live.calls[k_src]
        names = [self.live.plans[k_src]['actions'][i][0] for i in actions]
        self.rows.append({
            'k': k, 'scripted': why or f'call {k_src} cut to actions {list(actions)} ({", ".join(names)})',
            'source': self.live.name, 'source_call': k_src, 'actions': [int(i) for i in actions],
            'replace_args': {str(p): {str(j): t for j, t in r.items()} for p, r in (replace_args or {}).items()},
            'action_names': names, 'plan_len': len(actions), 'facts': None, 'goal': None,
            'rng_before': None, 'stream_ints_before': None,
            'stream_ints_after': live.get('stream_ints_after') if rng else None})

    def no_plan(self, why='no plan: the episode ends'):
        k = len(self.rows)
        (self.out / f'solution_{k:04d}.pkl').write_bytes(pickle.dumps((None, float('inf'), None)))
        (self.out / f'text_{k:04d}.json').write_text('[]\n', encoding='utf-8', newline='\n')
        self.rows.append({'k': k, 'scripted': why, 'no_plan': True, 'plan_len': None, 'facts': None,
                          'goal': None, 'rng_before': None, 'stream_ints_before': None,
                          'stream_ints_after': None})

    def close(self, scenario, stubs=None):
        with open(self.out / 'calls.jsonl', 'w', encoding='utf-8', newline='\n') as f:
            for r in self.rows:
                f.write(json.dumps(r, ensure_ascii=False, allow_nan=True) + '\n')
        info = {'scenario': scenario, 'episode': self.live.name, 'stubs': stubs or {'stubs': []},
                'calls': [{k: r.get(k) for k in ('k', 'scripted', 'source_call', 'action_names', 'no_plan')}
                          for r in self.rows],
                'source_tape_sha256': hashlib.sha256(
                    (self.live.tape / 'calls.jsonl').read_bytes()).hexdigest()}
        (self.out / 'SCRIPT.json').write_text(json.dumps(info, indent=1) + '\n', encoding='utf-8',
                                             newline='\n')
        return info


def _steps(plan, action):
    return [i for i, a in enumerate(plan['actions']) if a and a[0] == action]


def _sense_plan(root, names, reason):
    """(live, plan, index of the sense action) of the first live sense with
    outcome `reason`."""
    for live in _sources(root, names):
        for plan in live.plans:
            for step, s in sorted(plan['steps'].items()):
                if s['action'] == 'sense' and s['sense'] == reason:
                    return live, plan, step - 1
    raise NoSource(f'no live sense with outcome {reason} in {list(names)}')


def _first_sense_at_start(root, names):
    for live in _sources(root, names):
        if live.plans:
            idx = _steps(live.plans[0], 'sense')
            if idx:
                return live, live.plans[0], idx[0]
    raise NoSource(f'no first plan with a sense in {list(names)}')


def _first_ok_step(root, names, actions, need_sense=False):
    """(live, plan, step) of the first live step of one of `actions` that
    ended ok (step is 1-based, as in the ledger); with need_sense, only in a
    plan that also holds a sense (its object is the goal object)."""
    for live in _sources(root, names):
        for plan in live.plans:
            if need_sense and not _steps(plan, 'sense'):
                continue
            for step, s in sorted(plan['steps'].items()):
                if s['action'] in actions and s['status'] == 'ok':
                    return live, plan, step
    raise NoSource(f'no live {"/".join(actions)} that ended ok in {list(names)}'
                   + (' (in a plan with a sense)' if need_sense else ''))


def _occluder_of(shadow):
    name = shadow[len('shadow_of_'):] if shadow.startswith('shadow_of_') else shadow
    return name.split('__')[0]


def sense_split(out, root, names, reason, stubs=None):
    """Live calls before the plan, its actions before the sense as one plan,
    the sense alone as the next plan, then no plan."""
    live, plan, i = _sense_plan(root, names, reason)
    b = Builder(out, live)
    for k in range(plan['k']):
        b.live_call(k)
    if i > 0:
        b.cut(plan['k'], range(i), why=f'call {plan["k"]}: the actions before its sense')
    b.cut(plan['k'], [i], why=f'call {plan["k"]}: its sense alone (live outcome {reason})')
    b.no_plan()
    return b, live, plan, i


def build(scenario, tapes_root, out):
    """Write the scripted tape of `scenario` to `out`; returns the SCRIPT
    info dict (episode, stubs, calls)."""
    root = Path(tapes_root)
    stubs = None
    if scenario == 'sense_still_blocked':
        live, plan, i = _first_sense_at_start(root, BOXELS)
        b = Builder(out, live)
        b.cut(0, [i], why='call 0: its sense alone, at the start (the occluder in place)')
        b.no_plan()
    elif scenario == 'sense_missing_shadow':
        live, plan, i = _first_sense_at_start(root, BOXELS)
        b = Builder(out, live)
        b.cut(0, [i], replace_args={0: {1: NO_SHADOW}},
              why=f'call 0: its sense alone, the shadow replaced by {NO_SHADOW}')
        b.no_plan()
    elif scenario == 'sense_found_target':
        b, *_ = sense_split(out, root, BOXELS + BRIDGE, 'sense_found_target')
    elif scenario == 'sense_clear_but_empty':
        b, *_ = sense_split(out, root, BOXELS + BRIDGE, 'sense_clear_but_empty')
    elif scenario in ('sense_contains_nontarget', 'sense_contains_unlocalizable'):
        live, plan, i = _sense_plan(root, BOXELS, 'sense_found_target')
        shadow = plan['actions'][i][2]
        body = _occluder_of(shadow) if scenario == 'sense_contains_nontarget' else '#none'
        stubs = {'stubs': [{'name': 'sense_outcome', 'outcome': 'contains_nontarget', 'body': body}]}
        b, *_ = sense_split(out, root, (live.name,), 'sense_found_target')
    elif scenario in ('empty_hand_place', 'empty_hand_carry'):
        want = 'place' if scenario == 'empty_hand_place' else 'carry'
        found = None
        for live in _sources(root, BOXELS):
            for plan in live.plans:
                steps = plan['steps']
                for step in sorted(steps):
                    a = steps[step]['action']
                    if want == 'place' and a in ('place', 'place_hiding'):
                        found = (live, plan)
                    if (want == 'carry' and a == 'move' and step > 1
                            and steps.get(step - 1, {}).get('action') == 'pick'
                            and steps[step - 1]['status'] == 'ok'):
                        found = (live, plan)
                    if found:
                        break
                if found:
                    break
            if found:
                break
        if not found:
            raise NoSource(f'no live plan with a reached {want} in {list(BOXELS)}')
        live, plan = found
        b = Builder(out, live)
        for k in range(plan['k'] + 1):
            b.live_call(k)
        b.no_plan()
        stubs = {'stubs': [{'name': 'place_empty_hand' if want == 'place' else 'carry_loss'}]}
    elif scenario == 'empty_hand_stack':
        live = Live(root, 'stack0')
        if not any(_steps(p, 'stack') for p in live.plans):
            raise NoSource('stack0 has no plan with a stack')
        k = next(p['k'] for p in live.plans if _steps(p, 'stack'))
        b = Builder(out, live)
        for j in range(k + 1):
            b.live_call(j)
        b.no_plan()
        stubs = {'stubs': [{'name': 'stack_empty_hand'}]}
    elif scenario in ('integrity_replan', 'knocked_off_table'):
        live, plan, i = _first_sense_at_start(root, BOXELS)
        b = Builder(out, live)
        b.live_call(0)
        target = plan['actions'][i][1]
        if scenario == 'integrity_replan':
            b.no_plan()
            stubs = {'stubs': [{'name': 'integrity_event', 'kind': 'disturbed'}]}
        else:
            stubs = {'stubs': [{'name': 'integrity_event', 'kind': 'knocked_off_table',
                                'object': target}]}
    elif scenario in ('integrity_after_place', 'integrity_after_stack', 'knocked_after_pick'):
        want = {'integrity_after_place': ('place', 'place_hiding'),
                'integrity_after_stack': ('stack',), 'knocked_after_pick': ('pick',)}[scenario]
        names = ('stack0',) if scenario == 'integrity_after_stack' else BOXELS
        live, plan, step = _first_ok_step(root, names, want,
                                          need_sense=scenario == 'knocked_after_pick')
        b = Builder(out, live)
        for k in range(plan['k'] + 1):
            b.live_call(k)
        label = f'plan#{plan["plan_id"]} {plan["actions"][step - 1][0]}('
        if scenario == 'knocked_after_pick':
            target = plan['actions'][_steps(plan, 'sense')[0]][1]
            stubs = {'stubs': [{'name': 'integrity_event', 'kind': 'knocked_off_table',
                                'object': target, 'after': label}]}
        else:
            b.no_plan()
            stubs = {'stubs': [{'name': 'integrity_event', 'kind': 'disturbed', 'after': label}]}
    elif scenario == 'pick_giveup':
        live, plan, i = _sense_plan(root, BOXELS, 'sense_found_target')
        target = plan['actions'][i][1]
        picks = [j for j in _steps(plan, 'pick') if j > i and plan['actions'][j][1] == target]
        if not picks:
            raise NoSource(f'{live.name}: no pick of {target} after its sense')
        j = picks[0]
        b = Builder(out, live)
        for k in range(plan['k']):
            b.live_call(k)
        b.cut(plan['k'], range(j + 1), why=f'call {plan["k"]}: up to the pick of {target}')
        b.cut(plan['k'], [j], why=f'call {plan["k"]}: the pick of {target} alone (strike 2)')
        b.cut(plan['k'], [j], why=f'call {plan["k"]}: the pick of {target} alone (strike 3)')
        b.no_plan('no plan after the give-up (exit pick_giveup)')
        stubs = {'stubs': [{'name': 'pick_fail', 'object': target}]}
    elif scenario in ('home_split', 'home_not_reached'):
        found = None
        for live in _sources(root, BRIDGE):
            for plan in reversed(live.plans):
                acts = plan['actions']
                if (len(acts) >= 2 and acts[-1][0] == 'move' and 'q_home' in str(acts[-1][2])
                        and any(a[0] == 'pick' for a in acts[:-1])):
                    found = (live, plan)
                    break
            if found:
                break
        if not found:
            raise NoSource(f'no live plan ending with a move to q_home after a pick in {list(BRIDGE)}')
        live, plan = found
        n = len(plan['actions'])
        b = Builder(out, live)
        for k in range(plan['k']):
            b.live_call(k)
        if scenario == 'home_split':
            b.cut(plan['k'], range(n - 1), why=f'call {plan["k"]}: all but its final move to q_home')
            b.cut(plan['k'], [n - 1], why=f'call {plan["k"]}: its final move to q_home alone')
            b.no_plan('guard: no plan')
        else:
            b.cut(plan['k'], range(n), why=f'call {plan["k"]} as it is')
            b.cut(plan['k'], [n - 1], why=f'call {plan["k"]}: its final move to q_home again')
            b.cut(plan['k'], [n - 1], why=f'call {plan["k"]}: its final move to q_home again')
            b.no_plan('guard: no plan')
            stubs = {'stubs': [{'name': 'home_offset', 'offset_rad': 0.01}]}
    else:
        raise SystemExit(f'unknown scenario {scenario!r}; known: {list(SCENARIOS)}')
    return b.close(scenario, stubs)


SCENARIOS = {
    'sense_still_blocked': 'the first plan\'s sense alone at the start, its occluder in place',
    'sense_missing_shadow': 'the same sense with a shadow no registry holds',
    'sense_found_target': 'a live found_target sense, split off as a sense-only plan',
    'sense_clear_but_empty': 'a live clear_but_empty sense, split off as a sense-only plan',
    'sense_contains_nontarget': 'the found_target split, the outcome forced to contains_nontarget '
                                '(the moved occluder as the detected body; executor stub)',
    'sense_contains_unlocalizable': 'the found_target split, the outcome forced to contains_nontarget '
                                    'with a body the render does not show (executor stub)',
    'empty_hand_place': 'the first plan with a place, the place entry raising EmptyHandError (stub)',
    'empty_hand_carry': 'the first plan with a move after a pick, the carry check reporting a loss (stub)',
    'empty_hand_stack': 'stack0, the stack entry raising EmptyHandError (stub)',
    'integrity_replan': 'the first plan, a disturbed bystander after its first move (stub)',
    'knocked_off_table': 'the first plan, the goal object knocked off the table after its first move (stub)',
    'integrity_after_place': 'the first plan with a place that ended ok, a disturbed bystander '
                             'after that place (stub)',
    'integrity_after_stack': 'stack0, a disturbed bystander after its stack (stub)',
    'knocked_after_pick': 'the first plan with a sense and a pick that ended ok, the goal object '
                          'knocked off the table after that pick, while holding (stub)',
    'pick_giveup': 'a found_target plan, three failed picks of the target (stub), then no plan',
    'home_split': 'the last bridge plan split before its final move to q_home (at_home_ok)',
    'home_not_reached': 'the last bridge plan with every at-home readback off by 0.01 rad (stub)',
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--tapes')
    ap.add_argument('--scenario')
    ap.add_argument('--out')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args(argv)
    if a.list:
        for k, v in SCENARIOS.items():
            print(f'{k}: {v}')
        return 0
    info = build(a.scenario, a.tapes, a.out)
    print(json.dumps(info, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
