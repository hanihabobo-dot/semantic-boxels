"""replay_stub.py: the solver stub of pin 47 (PLAN 5.2, 24.3 (c); test code,
PLAN D9).  It stands in for ``pddlstream_planner.solve`` inside a test
process and plays back a tape that tools/readable/record_episode.py wrote on
the checkpoint:

  call k (0-based) returns a fresh unpickled copy of solution k (the
  executor may change configurations in place, so no copy is shared between
  calls or runs); before returning it writes solution k's stored text, chunk
  by chunk, to ``sys.stdout``, which at that moment is plan()'s
  ``_StdoutTee`` (pddlstream_planner.py:1304-1336), so a recorded no-plan
  whose text names skeletons takes the binding-death branch (1348-1384) as
  it did live; with ``rng='restore'`` it then sets the global random and
  np.random states the live search left after call k, and the int
  attributes of ``planner.streams`` (the name counters _config_counter,
  _traj_counter, _grasp_counter and counts such as view_kin_skips) to their
  values after the live call (a test-level choice: the draws after the
  call, the motion re-solve and the next plan's shuffle, and the names the
  streams give at the next init, are then the live ones; 'keep' leaves the
  replay's own state).  The planner is found as ``self`` of the plan()
  frame up the stack.

A call beyond the tape raises ReplayTapeError, a BaseException, so no
``except Exception`` of the pipeline (the bridge's execute_fn has one) can
turn it into an ordinary failed episode.  Each call writes one row to
``<rec>/calls.jsonl`` at the time of the call: the init facts and goal the
replay passed, whether they equal the tape's, and whether the RNG state
before the call equals the live one.

``install`` must run before tampura_bridge.gate_hooks.install wraps
``solve`` (record_episode.py sets it when pddlstream_planner has been
executed), so the gate wrapper is the outermost and G11 still checks that
plan() is the caller.  Nothing here touches a pipeline file.
"""
import hashlib
import importlib.util
import json
import pickle
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _tool():
    """tools/readable/record_episode.py (shared tape format and helpers)."""
    mod = sys.modules.get('readable_record_episode')
    if mod is None:
        path = REPO / 'tools' / 'readable' / 'record_episode.py'
        spec = importlib.util.spec_from_file_location('readable_record_episode', str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['readable_record_episode'] = mod
        spec.loader.exec_module(mod)
    return mod


class ReplayTapeError(BaseException):
    """The replay asked the solver more often than the live episode did."""


class Tape:
    """A recorded tape folder: calls.jsonl, solution_k.pkl, text_k.json,
    rng_k.pkl.  pickle is read only from folders record_episode.py wrote on
    this machine (the stream objects carry numpy arrays)."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.calls = _tool().tape_calls(self.folder)

    def __len__(self):
        return len(self.calls)

    def solution(self, k):
        return pickle.loads((self.folder / f'solution_{k:04d}.pkl').read_bytes())

    def chunks(self, k):
        return json.loads((self.folder / f'text_{k:04d}.json').read_text(encoding='utf-8'))

    def rng_blob(self, k):
        p = self.folder / f'rng_{k:04d}.pkl'
        return p.read_bytes() if p.exists() else None


def make_stub(tape_dir, rec_dir, rng='restore'):
    """The stand-in for pddlstream_planner.solve."""
    if rng not in ('restore', 'keep'):
        raise ValueError(f'rng must be restore or keep, not {rng!r}')
    tool = _tool()
    tape = Tape(tape_dir)
    rec = Path(rec_dir)
    rec.mkdir(parents=True, exist_ok=True)
    log = rec / 'calls.jsonl'
    state = {'k': 0}

    def solve(problem, *args, **kwargs):
        k = state['k']
        state['k'] += 1
        facts, goal = tool.problem_facts(problem)
        row = {'k': k, 'rng_before': tool.rng_digest(), 'goal': goal,
               'facts_sha256': hashlib.sha256('\n'.join(facts).encode('utf-8')).hexdigest(),
               'facts': facts, 'kwargs': tool._plain_kwargs(kwargs)}
        if k >= len(tape):
            row['error'] = f'call {k + 1} but the tape holds {len(tape)} calls'
            tool.append_jsonl(log, row)
            raise ReplayTapeError(row['error'])
        live = tape.calls[k]
        if live.get('facts') is not None:
            row['facts_equal_tape'] = facts == live['facts']
            row['goal_equal_tape'] = goal == live['goal']
        if live.get('rng_before') is not None:
            row['rng_before_equal_tape'] = row['rng_before'] == live['rng_before']
        planner = tool.planner_on_stack()
        ints = tool.stream_ints(planner)
        if live.get('stream_ints_before') is not None:
            row['stream_ints_before_equal_tape'] = ints == live['stream_ints_before']
        if live.get('raised'):
            row['error'] = f"the live call raised: {live['raised']}"
        tool.append_jsonl(log, row)
        for chunk in tape.chunks(k):
            sys.stdout.write(chunk)
        blob = tape.rng_blob(k)
        if rng == 'restore' and blob is not None:
            tool.set_rng_states(blob)
        after = live.get('stream_ints_after')
        if rng == 'restore' and after and planner is not None:
            for name, value in after.items():
                setattr(planner.streams, name, value)
        if live.get('raised'):
            raise ReplayTapeError(row['error'])
        return tape.solution(k)
    solve.tape = tape
    solve.state = state
    return solve


def install(module, tape_dir, rec_dir, rng='restore'):
    """Set the stub as module.solve (module: pddlstream_planner)."""
    stub = make_stub(tape_dir, rec_dir, rng=rng)
    stub.__wrapped__ = getattr(module, 'solve', None)
    module.solve = stub
    return stub


def calls_used(rec_dir):
    p = Path(rec_dir) / 'calls.jsonl'
    if not p.exists():
        return 0
    return sum(1 for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip())
