"""BF#53, the optimistic search's settings: the two CLI values become
pddlstream solve() keyword arguments ('off' and 0 leave pddlstream's own),
and plan() hands them to solve()."""
import inspect

import pddlstream_planner


def test_the_settings_become_solve_arguments():
    f = pddlstream_planner.search_options_from
    assert f('off', 0) == {}
    assert f('1', 0) == {'effort_weight': 1.0}
    assert f('off', 3) == {'initial_complexity': 3}
    assert f('0.5', 3) == {'effort_weight': 0.5, 'initial_complexity': 3}


def test_plan_forwards_them_to_solve():
    src = inspect.getsource(pddlstream_planner.PDDLStreamPlanner.plan)
    call = src.split('solution = solve(')[1].split(')\n')[0]
    assert '**self.search_options' in call
