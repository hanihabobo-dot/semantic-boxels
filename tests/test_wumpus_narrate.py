"""The Wumpus narration layer: wumpus/narrate.py and wumpus/console_words.py.

No simulator: the world's own percept rules answer through
wumpus/narrate_demo.StandInEnv.  What is checked: the words, the ledger rows
a controller's calls write (the plan a row announces is the plan that runs,
every action is closed, a perceive's percept comes before its end), that the
narration is never read back (the controller does the same with it and without
it), the runner's wiring (run_wumpus.main with a fake env), and the curated
console of a whole stand-in episode in a subprocess (captured mode).
"""
import json
import os
import subprocess
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from wumpus import console_words as cw          # noqa: E402
from wumpus import narrate                      # noqa: E402
from wumpus.explore import run_explore          # noqa: E402
from wumpus.narrate_demo import StandInEnv      # noqa: E402
from wumpus.world import WumpusWorld            # noqa: E402


# ----- the words ----------------------------------------------------------------

def test_describe():
    assert cw.describe('move', ['p1-2']) == 'Moving to `p1-2`'
    assert cw.describe('perceive', ['p3-1']) == 'Looking around `p3-1`'
    assert cw.describe('grab', []) == 'Grabbing the gold'
    assert cw.describe('open_gripper', []) is None


@pytest.mark.parametrize('actions,sentence', [
    ([], ''),
    ([('perceive', 'p1-1')], 'look around'),
    ([('move', 'p1-2')], 'go to `p1-2`'),
    ([('move', 'p1-2'), ('perceive', 'p1-2')], 'go to `p1-2`, then look around'),
    ([('move', 'p1-2'), ('move', 'p1-3'), ('perceive', 'p1-3'), ('grab', 'p1-3')],
     'go to `p1-3` through `p1-2`, look around, then grab the gold'),
    ([('move', c) for c in ('p1-2', 'p1-3', 'p1-4')], 'go to `p1-4` through `p1-2` and `p1-3`'),
    ([('move', c) for c in ('p1-2', 'p1-3', 'p1-4', 'p1-5', 'p2-5', 'p3-5')],
     'go to `p3-5` through `p1-2`, `p1-3` and 3 more cells'),
])
def test_plan_sentence(actions, sentence):
    assert cw.plan_sentence(actions) == sentence


def test_plan_sentence_is_short_for_long_plans():
    actions = [a for i in range(6) for a in (('move', f'p{i + 1}-1'), ('perceive', f'p{i + 1}-1'))]
    s = cw.plan_sentence(actions)
    assert s.count(', ') == 7 and s.endswith('and 5 more steps')


def test_percept_notes():
    assert cw.percept_notes() == []
    got = cw.percept_notes(stench=True, breeze=True, glitter=True)
    assert [t for t, _, _ in got] == ['I smell the wumpus', 'I feel a breeze', 'Something glitters here']
    assert [a for _, a, _ in got] == ['stench', 'breeze', 'glitter']
    assert [f for _, _, f in got] == ['warn', 'warn', 'found']


def test_knowledge_lines():
    first, second = cw.knowledge_lines(dict(visited=3, cells=25, safe=5, maybe_pit=20, maybe_wumpus=18))
    assert first == 'I have been to 3 of 25 cells, 5 are known safe'
    assert second == 'a pit may lie in 20 cells, the wumpus in 18, no sign of the gold yet'
    first, second = cw.knowledge_lines(dict(visited=1, cells=25, safe=1, maybe_pit=1, gold_known=True))
    assert first == 'I have been to 1 of 25 cells, 1 is known safe'
    assert second == 'a pit may lie in 1 cell, I know where the gold is'


class _Glyphs:
    """The part of a console that think_lines uses."""

    @staticmethod
    def g(name):
        return {'think': '*', 'ell': '...'}[name]


def test_thinking_block_says_what_the_robot_knows():
    t = cw.WumpusTask()
    t.know = dict(visited=3, cells=25, safe=5, maybe_pit=20, maybe_wumpus=18)
    head, info = t.think_lines(_Glyphs, 4)
    assert ''.join(text for text, _ in head) == '* Thinking... how to find the gold'
    assert info == ['I have been to 3 of 25 cells, 5 are known safe',
                    'a pit may lie in 20 cells, the wumpus in 18, no sign of the gold yet']
    t.know['gold_known'] = True
    head, info = t.think_lines(_Glyphs, 5)
    assert ''.join(text for text, _ in head).endswith('how to reach the gold')
    assert info[1].endswith('I know where the gold is')
    # a controller that tells no numbers still gets a line on the gold, and no empty row
    t.know = {}
    assert t.think_lines(_Glyphs, 6)[1] == ['no sign of the gold yet']


def test_speech_reads_cells_aloud():
    assert cw.WumpusTask().speech(None, 'Moving to p1-2') == 'Moving to cell 1 2'


def test_failure_and_stat_sentences():
    t = cw.WumpusTask()
    t.final = dict(outcome='death', reason='pit', cell='p4-3', visited=5, cells=25)
    assert t.summary_failed(None, 'death') == 'I fell into a pit at p4-3'
    t.final['reason'] = 'wumpus'
    assert t.summary_failed(None, 'death') == 'The wumpus got me at p4-3'
    t.final = dict(outcome='stuck', reason='no safe unvisited cell is left')
    assert t.summary_failed(None, 'stuck') == 'I am stuck: no safe unvisited cell is left'
    t.final = dict(outcome='step_limit', reason='500 steps')
    assert t.summary_failed(None, 'step_limit') == 'I ran out of steps (500 steps)'
    t.final = dict(visited=14, cells=25)
    assert t.summary_stats(None, []) == ['14 of 25 cells visited']
    assert t.summary_done(None, []) == 'I am holding the gold'


@pytest.mark.parametrize('name,seconds,peak', [('death', 1.7, 0.42), ('gold', 1.9, 0.40)])
def test_new_sounds_render_cleanly(tmp_path, name, seconds, peak):
    """The two effects only the Wumpus world needs: a mono 16-bit file of the
    right length, normalized like the other effects (no clipping), ending faded."""
    import struct
    import wave
    import console_audio
    assert {'act', 'think', 'startup', 'found', 'warn', 'fail', 'success', 'failure'} <= set(console_audio.PIECES)
    path = str(tmp_path / f'{name}.wav')
    console_audio.PIECES[name]().write(path)
    with wave.open(path) as w:
        n, rate, width, ch = w.getnframes(), w.getframerate(), w.getsampwidth(), w.getnchannels()
        samples = struct.unpack(f'<{n}h', w.readframes(n))
    assert (rate, width, ch) == (console_audio.RATE, 2, 1)
    assert abs(n / rate - seconds) < 0.01
    assert abs(max(abs(s) for s in samples) / 32767 - peak) < 0.01
    assert max(abs(s) for s in samples[-int(0.05 * rate):]) / 32767 < 0.05


# ----- the rows a controller's calls write -------------------------------------

@pytest.fixture
def logger(tmp_path):
    from run_logger import RunLogger
    lg = RunLogger(verbosity='quiet', log_dir=str(tmp_path / 'logs'))
    yield lg
    lg.close()


def _rows(lg):
    with open(os.path.join(str(lg.run_dir), 'ledger.jsonl'), encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def _play(size, seed, narrated=True, max_steps=500):
    """run_explore on the stand-in env; returns (outcome, the env's calls)."""
    world = WumpusWorld.random(size, seed)
    base = StandInEnv(world)
    calls = []

    class Recording:
        def __getattr__(self, name):
            return getattr(base, name)

        def _log(self, name, arg=None):
            calls.append((name, arg))

        def perceive(self):
            self._log('perceive')
            return base.perceive()

        def move(self, cell):
            self._log('move', cell)
            return base.move(cell)

        def grab(self):
            self._log('grab')
            return base.grab()

    env = Recording()
    if narrated:
        narrate.begin(size, seed, start=world.start, wumpuses=world.wumpuses, pits=world.pits)
        env = narrate.NarratedEnv(env)
    out = run_explore(env, max_steps=max_steps, narrate=narrate if narrated else None)
    return out, calls


def test_rows_of_a_whole_episode(logger):
    out, calls = _play(5, 3)
    narrate.outcome(out['outcome'], out['reason'], visited=14, held=out['outcome'] == 'success')
    rows = _rows(logger)
    kinds = [r['kind'] for r in rows]
    assert kinds[:2] == ['ledger_open', 'wumpus_mission']
    assert kinds[-1] == 'wumpus_result'
    mission = rows[1]
    assert (mission['size'], mission['seed'], mission['cells']) == (5, 3, 25)
    assert mission['wumpuses'] == 1 and mission['pace_s'] == 0.0
    # every action is closed, with a status the ledger knows
    begins = [r for r in rows if r['kind'] == 'step']
    ends = [r for r in rows if r['kind'] == 'step_end']
    assert len(begins) == len(ends) == len(calls)
    assert {r['status'] for r in ends} <= {'ok', 'action_failed', 'dead'}
    # every plan is thought about first, and what it announces is what then runs
    plans = [r for r in rows if r['kind'] == 'plan']
    thinks = [r for r in rows if r['kind'] == 'wumpus_think']
    assert len(thinks) == len(plans) and all(r['call'] == 'mission' for r in plans)
    assert [r['plan_no'] for r in thinks] == [r['plan_id'] for r in plans]
    ran = {}
    for r in begins:
        ran.setdefault(r['plan'], []).append([r['action']] + list(r['args']))
    for p in plans:
        got = ran.get(p['plan_id'], [])
        if out['outcome'] == 'success':
            assert got == (p['actions'] or [])
        else:
            assert got == (p['actions'] or [])[:len(got)]
    # a perceive's percept comes before its end, stamped with its plan and step
    for b, e in zip(begins, ends):
        if b['action'] == 'perceive':
            i0, i1 = rows.index(b), rows.index(e)
            inside = [r for r in rows[i0:i1] if r['kind'] == 'wumpus_percept']
            assert len(inside) == 1 and inside[0]['step'] == b['step']
    # the knowledge only grows
    assert [r['visited'] for r in thinks] == sorted(r['visited'] for r in thinks)
    final = rows[-1]
    assert final['outcome'] == out['outcome'] and final['plans'] == len(plans)


def test_death_is_told_and_closed(logger):
    world = WumpusWorld.random(4, 1)
    env = narrate.NarratedEnv(StandInEnv(world))
    narrate.begin(4, 1, start=world.start, wumpuses=world.wumpuses, pits=world.pits)
    hazard = sorted(world.pits)[0]
    here = env.robot_cell()
    path, seen, frontier = {here: None}, {here}, [here]
    while frontier:
        c = frontier.pop(0)
        for n in world.neighbors(c):
            if n not in seen:
                seen.add(n)
                path[n] = c
                frontier.append(n)
    steps, c = [], hazard
    while path[c] is not None:
        steps.append(c)
        c = path[c]
    narrate.thinking(visited=1, safe=1, maybe_pit=15, maybe_wumpus=15)
    narrate.plan([('move', c) for c in reversed(steps)], 0.0)
    for c in reversed(steps):
        r = env.move(c)
        if r['dead']:
            break
    rows = _rows(logger)
    ends = [r for r in rows if r['kind'] == 'step_end']
    assert ends[-1]['status'] == 'dead'
    res = [r for r in rows if r['kind'] == 'wumpus_action_result'][-1]
    assert res['dead'] == 'pit' and res['ok'] is True


def test_calls_without_a_logger_are_no_ops():
    narrate.begin(5, 0)
    narrate.thinking(visited=1)
    narrate.plan([('move', 'p1-2')])
    assert narrate.action_begin('move', 'p1-2') == 1
    narrate.action_end(ok=True)
    narrate.percept('p1-2', False, True, False)
    narrate.outcome('stuck', 'no safe unvisited cell is left')


def test_narration_is_never_read_back(logger):
    """The controller makes the same calls with its narration on and off."""
    for size, seed in ((5, 3), (5, 0), (5, 1), (4, 2)):
        with_it, calls_with = _play(size, seed, narrated=True)
        without, calls_without = _play(size, seed, narrated=False)
        assert with_it == without
        assert calls_with == calls_without


# ----- the runner --------------------------------------------------------------

class FakeWumpusEnv(StandInEnv):
    """What run_wumpus needs from WumpusEnv beyond StandInEnv (no PyBullet)."""

    def __init__(self, world, gui=False, save_dir=None):
        super().__init__(world)
        self.sim_steps, self.registry = 0, {}

    def truth(self, cell):
        w = self.world
        return {'stench': w.stench(cell), 'breeze': w.breeze(cell), 'glitter': w.glitter(cell)}

    def pose(self):
        return [0.0, 0.0, 0.0]

    def close(self):
        pass


def test_runner_wiring(tmp_path, monkeypatch):
    fake = types.ModuleType('wumpus.env')
    fake.WumpusEnv = FakeWumpusEnv
    monkeypatch.setitem(sys.modules, 'wumpus.env', fake)
    from wumpus import run_wumpus
    code = run_wumpus.main(['--size', '5', '--seed', '3', '--vis', '0', '--quiet', '--log-level', 'quiet',
                            '--log-dir', str(tmp_path / 'logs'), '--save-dir', str(tmp_path / 'save')])
    assert code == 0
    with open(tmp_path / 'save' / 'episode.json', encoding='utf-8') as f:
        rec = json.load(f)
    assert rec['outcome']['outcome'] == 'success'
    assert rec['wall']['pace_s'] == 0.0 and rec['wall']['paced_s'] == 0.0
    run_dir = rec['run_dir']
    with open(os.path.join(run_dir, 'ledger.jsonl'), encoding='utf-8') as f:
        kinds = [json.loads(line)['kind'] for line in f if line.strip()]
    assert kinds[:2] == ['ledger_open', 'wumpus_mission']
    assert kinds[-2:] == ['wumpus_result', 'ledger_close']       # the logger closes after the verdict
    assert kinds.count('step') == rec['n_actions']


def test_runner_refuses_a_missing_hidden_file(tmp_path, capsys):
    from wumpus import run_wumpus
    code = run_wumpus.main(['--source', 'hidden', '--log-dir', str(tmp_path / 'logs')])
    assert code == 2
    assert 'needs --hidden-file' in capsys.readouterr().err
    assert not (tmp_path / 'logs').exists()      # a refusal opens no run directory


# ----- the curated console of a whole episode ----------------------------------

def _demo(tmp_path, *flags):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'wumpus', 'narrate_demo.py'), *flags,
                        '--log-dir', str(tmp_path / 'logs')],
                       capture_output=True, text=True, timeout=300, cwd=ROOT, encoding='utf-8')
    return r


def test_console_of_a_success(tmp_path):
    r = _demo(tmp_path, '--size', '5', '--seed', '3')
    out = r.stdout
    assert r.returncode == 0 and r.stderr == ''
    for phrase in ('Mission: find the gold and grab it.', 'in a 5x5 world of 25 cells',
                   'Thinking', 'how to find the gold', 'I will go to',
                   'Moving to p', 'Looking around p', 'All quiet: no breeze, no stench, no glitter',
                   'Grabbing the gold', 'Done.', 'I am holding the gold', 'cells visited'):
        assert phrase in out, phrase
    assert 'Traceback' not in out and 'pybullet' not in out.lower()
    run_dirs = os.listdir(tmp_path / 'logs')
    assert len(run_dirs) == 1
    assert os.path.exists(tmp_path / 'logs' / run_dirs[0] / 'console_debug.log')


def test_console_of_a_death(tmp_path):
    r = _demo(tmp_path, '--size', '4', '--seed', '1', '--die', 'pit')
    assert r.returncode == 1 and r.stderr == ''
    assert 'I fell into a pit' in r.stdout and 'Failed.' in r.stdout
    assert 'Done.' not in r.stdout
