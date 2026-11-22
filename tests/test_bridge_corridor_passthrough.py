"""TB-25: the bridge driver passes --corridor-test through to the pipeline.

The planner's corridor test (#P1 F32: 'cell+object', the default, or
'object') is a flag of the pipeline (run_logger).  The find_dice driver
(tampura_bridge/run_bridge_on_finddice.py) takes the same flag with the same
choices and the same default and puts it among the episode's switches;
policy.py turns every switch into a pipeline flag, and main() hands the
value to the planner.  No simulator and no episode: the driver and policy.py
are read from their source, the pipeline's argv is built the way policy.py
builds it and parsed by the pipeline's own parser; where their trees are
importable (WSL), the real driver's parser is asked for its help text and
for a refusal, two calls that argparse ends before any scene is loaded.
"""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from console import run_logger

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / 'tampura_bridge' / 'run_bridge_on_finddice.py'
POLICY = REPO / 'tampura_bridge' / 'policy.py'
PIPELINE = REPO / 'test_full_pipeline.py'

# A valid value for every switch the driver hands to policy.py, as the
# driver's own defaults give them (a new switch needs its value here).
SWITCH_VALUES = {
    'm8': 'on', 'm9': 'on', 'm10': 'on', 'pick_aperture_from_pose': 'on',
    'sense_over_region': 'on', 'grip_squeeze_mm': '0.5',
    'world_counts': 'auto', 'corridor_test': 'cell+object',
    'search_effort_weight': '1', 'search_initial_complexity': '3',
    'slip_fixes': 'force_hold,grasp_wrist_home,pose_radius_keep,solver_iters',
    'save_screenshots': 'off', 'interior_regions': 'off', 'm7': 'on',
}


def _driver_tree():
    return ast.parse(DRIVER.read_text(encoding='utf-8'))


def _add_argument(flag):
    """The keywords of the driver's ap.add_argument(flag, ...) call."""
    found = []
    for node in ast.walk(_driver_tree()):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'add_argument' and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == flag):
            found.append({k.arg: ast.literal_eval(k.value) for k in node.keywords})
    assert len(found) == 1, f"{flag}: {len(found)} add_argument calls"
    return found[0]


def _switches_dict():
    """The dict literal the driver passes as EpisodeConfig(switches=...)."""
    found = []
    for node in ast.walk(_driver_tree()):
        if isinstance(node, ast.Call):
            for k in node.keywords:
                if k.arg == 'switches' and isinstance(k.value, ast.Dict):
                    found.append(k.value)
    assert len(found) == 1, f"{len(found)} switches dicts"
    return found[0]


def _pipeline_argv(switches):
    """The pipeline's argv as policy.py builds it from an episode's switches."""
    return (['--no-gui', '--goal', 'holding', '--log-level', 'quiet',
             '--max-plan-time', '900.0']
            + [x for k, v in sorted(switches.items())
               for x in (f"--{k.replace('_', '-')}", v)])


def test_the_pipeline_flag_and_its_default():
    assert run_logger.parse_pipeline_args(['--no-gui']).corridor_test == 'cell+object'
    args = run_logger.parse_pipeline_args(['--no-gui', '--corridor-test', 'object'])
    assert args.corridor_test == 'object'
    with pytest.raises(SystemExit):
        run_logger.parse_pipeline_args(['--no-gui', '--corridor-test', 'cell'])


def test_the_driver_takes_the_same_flag_with_the_default_unchanged():
    kw = _add_argument('--corridor-test')
    assert tuple(kw['choices']) == ('cell+object', 'object')
    # The default is the pipeline's own: a bridge run without the flag plans
    # as every bridge run before it did.
    assert kw['default'] == 'cell+object'
    assert kw['default'] == run_logger.parse_pipeline_args(['--no-gui']).corridor_test
    for value in kw['choices']:
        run_logger.parse_pipeline_args(['--no-gui', '--corridor-test', value])


def test_the_driver_puts_it_among_the_switches():
    d = _switches_dict()
    # a None key is path 9's `**({'look': ...} if a.look != 'off' else {})`: absent in a default episode
    keys = [k.value if k is not None else None for k in d.keys]
    assert 'corridor_test' in keys
    value = d.values[keys.index('corridor_test')]
    # a.corridor_test, as parsed: no rewriting between the flag and the switch
    assert isinstance(value, ast.Attribute) and value.attr == 'corridor_test'
    assert isinstance(value.value, ast.Name) and value.value.id == 'a'
    # Every switch has a value in this file's table, so the argv below is the
    # one a default episode gets.
    assert sorted(k for k in keys if k is not None) == sorted(SWITCH_VALUES)


def test_policy_turns_every_switch_into_a_pipeline_flag():
    src = POLICY.read_text(encoding='utf-8')
    # The comprehension _pipeline_argv copies; if policy.py builds its argv
    # another way, this test and the copy above are out of date.
    assert "+ [x for k, v in sorted(cfg.switches.items())" in src
    assert """for x in (f"--{k.replace('_', '-')}", v)])""" in src


@pytest.mark.parametrize('value', ['cell+object', 'object'])
def test_the_pipeline_parses_the_bridge_argv(value):
    argv = _pipeline_argv(dict(SWITCH_VALUES, corridor_test=value))
    assert argv[argv.index('--corridor-test') + 1] == value
    args = run_logger.parse_pipeline_args(argv)
    assert args.corridor_test == value
    # The other switches arrive as before.
    assert args.world_counts == 'auto' and args.m8 == 'on'
    assert args.slip_fixes == SWITCH_VALUES['slip_fixes']


def test_main_hands_the_value_to_the_planner():
    # The statement moved with build_planner to planner_setup.py; the
    # pipeline calls build_planner once, with the parsed args.
    src = (REPO / 'planner_setup.py').read_text(encoding='utf-8')
    assert ("planner.corridor_test = getattr(args, 'corridor_test', 'cell+object')"
            in src)
    assert PIPELINE.read_text(encoding='utf-8').count(
        'build_planner(st, env, slip_fixes, args)') == 1


def test_the_episode_record_carries_the_switches():
    # bridge_episode.json is the record of a bridge run's switches (BF#41),
    # so the corridor test of an episode is read there.
    src = DRIVER.read_text(encoding='utf-8')
    assert "'switches': dict(cfg.switches)" in src


def _driver(tmp_path, *argv):
    """The real driver's own parser on argv.  Only calls that argparse ends
    itself (--help, a refused value): no scene is loaded, no episode runs.
    HOME in tmp_path: the console's start-up debug file stays out of
    ~/.cache (as tampura_bridge/tests/test_draw_boxels.py does)."""
    proc = subprocess.run([sys.executable, str(DRIVER), *argv],
                          capture_output=True, text=True, timeout=300,
                          env=dict(os.environ, HOME=str(tmp_path)))
    return proc.returncode, proc.stdout + proc.stderr


def test_the_real_driver_names_the_flag_and_refuses_another_value(tmp_path):
    pytest.importorskip('tampura')      # the driver imports their trees (WSL)
    rc, out = _driver(tmp_path, '--help')
    assert rc == 0, out
    assert '--corridor-test {cell+object,object}' in out, out
    rc, out = _driver(tmp_path, '--global-seed', '0', '--corridor-test', 'cell')
    assert rc == 2, out
    assert "invalid choice: 'cell'" in out, out
