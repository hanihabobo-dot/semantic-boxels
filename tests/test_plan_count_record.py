"""C-07: the record's plan_count is the number of planning rounds.

main()'s loop adds one to plan_count at the head of every round.  A round
that ends as all_searched (or as target_lost, its relabel) breaks before
any planner.plan() call, and a no_plan_while_holding round broke before
its planning time went into total_plan_time and plan_times.  So both
endings filed a plan_count one above len(plan_times), and the second lost
the time of its last two plan() calls.  The record now takes plan_count
from len(plan_times), and the no_plan_while_holding round's time counts.

main() builds a whole scene, so these tests run the loop's own statements
from its head to the classification of a failed plan (the dispatch of a
plan is left out): taken from the source by ast, compiled as they are, and
run with stand-ins for the names they use.  The record's plan_count is the
expression main() passes to report_run_outcome, evaluated after the loop.
"""
import ast
import types
import typing
from pathlib import Path

import interior_regions

SOURCE_PATH = Path(__file__).resolve().parents[1] / 'test_full_pipeline.py'
TARGET = 'green_object'
HELD = 7
GOAL = ('holding', TARGET)


def _main():
    tree = ast.parse(SOURCE_PATH.read_text(encoding='utf-8'))
    (main,) = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'main']
    return main


def _planning_rounds(main):
    """main()'s loop up to the dispatch of a plan, compiled with the
    file's own name and line numbers."""
    (loop,) = [n for n in main.body if isinstance(n, ast.While)
               and ast.unparse(n.test) == 'not _loop_done()']
    (cut,) = [i for i, s in enumerate(loop.body)
              if isinstance(s, ast.Expr)
              and ast.unparse(s).startswith("print(f'Plan: ")]
    rounds = ast.copy_location(
        ast.While(test=loop.test, body=loop.body[:cut], orelse=[]), loop)
    return compile(ast.Module(body=[rounds], type_ignores=[]),
                   str(SOURCE_PATH), 'exec')


def _record_plan_count(main):
    """The plan_count main() passes to report_run_outcome."""
    (call,) = [n for n in ast.walk(main) if isinstance(n, ast.Call)
               and ast.unparse(n.func) == 'report_run_outcome']
    (value,) = [k.value for k in call.keywords if k.arg == 'plan_count']
    return compile(ast.Expression(body=value), str(SOURCE_PATH), 'eval')


class _Clock:
    """time.perf_counter; only the planner moves it on."""
    def __init__(self):
        self.now = 0.0

    def perf_counter(self):
        return self.now


class _Planner:
    """planner.plan returns the given plans in turn, and each call takes
    the given seconds on the clock."""
    def __init__(self, clock, plans, seconds):
        self.clock, self.plans, self.seconds = clock, list(plans), list(seconds)
        self.goals = []
        self.m8_views = self.last_m8_stats = self.last_init = None
        self.last_look_stats = None            # path 9's per-plan look stats (track/look)
        self.last_no_plan_binding_death = None
        self.streams = types.SimpleNamespace(ungraspable_objects=set())

    def plan(self, goal, **kwargs):
        self.goals.append(goal)
        self.clock.now += self.seconds.pop(0)
        return self.plans.pop(0)


def _ignore(*args, **kwargs):
    return None


def _run(unknown_shadows, plans, seconds, held_body_id=None):
    """The rounds of a holding goal; unknown_shadows is what the belief
    reports at the head of each round.  Returns the names after the loop,
    the record's plan_count and the planner."""
    main = _main()
    clock = _Clock()
    planner = _Planner(clock, plans, seconds)
    heads = iter(unknown_shadows)
    names = {
        '_loop_done': lambda: False,
        'plan_count': 0, 'plan_times': [], 'total_plan_time': 0.0,
        'exit_reason': None, 'gui': False,
        'disturbed_counts': {}, 'pick_giveup_marked_at': {},
        'pick_giveup_objects': set(), 'pick_parole_counts': {},
        'observe_strikes': {}, 'm8_per_plan': [],
        'boxel_counts_per_replan': [],
        'belief': types.SimpleNamespace(
            get_unknown_shadows=lambda: next(heads),
            get_known_empty_shadows=lambda: [],
            get_parked_shadows=lambda: [], occluders_moved={}),
        'registry': types.SimpleNamespace(
            dirty=False, get_boxel=lambda name: None,
            get_object_boxels=lambda: [], get_shadow_boxels=lambda: [],
            get_free_space_boxels=lambda: []),
        'planner': planner,
        'env': types.SimpleNamespace(sync_to_plan_client=_ignore),
        'world_eye': types.SimpleNamespace(snapshot=_ignore),
        'ledger_event': _ignore, 'ledger_plan': _ignore,
        'time': clock, 'Optional': typing.Optional,
        'goal_kind': 'holding', 'goal': GOAL, 'target_name': TARGET,
        'planner_target_objects': [TARGET], 'stack_target_objects': [],
        'on_relations': {}, 'shadows': ['s1', 's2'],
        'blocked_giveup_shadows': set(), 'shadow_occluder_map': {},
        'held_body_id': held_body_id, 'body_id_to_name': {HELD: 'red_object'},
        'current_config': None, 'visible_target_locations': {},
        'unit_costs': False,
        # BF#65's module (merged with C-07 on track/evalfinal): the rounds call it; off by default
        'interior_regions': interior_regions,
        'args': types.SimpleNamespace(max_plan_time=60.0, log_level='quiet',
                                      planner='default'),
    }
    exec(_planning_rounds(main), names)
    return names, eval(_record_plan_count(main), names), planner


def test_all_searched_files_only_the_rounds_that_planned(capsys):
    # round 1 plans a sense; round 2 finds no unknown shadow and stops
    names, record, planner = _run([['s1'], []], [[('sense', 's1')]], [2.5])
    assert names['exit_reason'] == 'all_searched'
    assert planner.goals == [GOAL]
    assert names['plan_times'] == [2.5] and names['total_plan_time'] == 2.5
    assert record == len(names['plan_times']) == 1
    # inside the loop the count is as it was: the last round is PLAN #2
    assert names['plan_count'] == 2
    out = capsys.readouterr().out
    assert '=== PLAN #2 ===' in out and 'Searched all shadows' in out


def test_no_plan_while_holding_counts_its_last_round():
    # no mission plan (3 s) with an object held, and no disposal (1.25 s)
    names, record, planner = _run([['s1']], [None, None], [3.0, 1.25],
                                  held_body_id=HELD)
    assert names['exit_reason'] == 'no_plan_while_holding'
    assert planner.goals == [GOAL, ('handempty',)]
    assert names['plan_times'] == [4.25]          # both calls of the round
    assert names['total_plan_time'] == 4.25
    assert record == len(names['plan_times']) == 1
    assert names['plan_count'] == 1


def test_planner_failed_counts_agree_as_before():
    # the endings after the time is counted are unchanged
    names, record, planner = _run([['s1'], ['s1']], [[('sense', 's1')], None],
                                  [1.0, 2.0])
    assert names['exit_reason'] == 'planner_failed'
    assert names['plan_times'] == [1.0, 2.0] and names['total_plan_time'] == 3.0
    assert record == names['plan_count'] == 2
