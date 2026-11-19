"""Path 9, the arm camera only, step 3: the wiring (sources, the gate, the
launcher).  No episode.

1. main(): the follow is installed once, under --eye arm, between the start
   view and the first render (the bridge's read-only check included); the
   planner gets no camera with --eye arm (FACTS case 4); no blocker census
   runs with it; the frame is read only after the switch in the same test.
2. execution.py: every blocker census sits behind the switch.
3. The bridge (case 5): the driver takes --eye and passes arm alone, by a
   plain if after the switches literal; the policy declares no eye for G20
   with arm, as empty matrices.  On the gate itself: empty matrices let only
   the wrist at its FK pose through, while None would check nothing.
4. A planner without a camera makes no placement_hides (case 4).
5. The launcher: run tampura -Look boxel -Eye arm passes --eye arm.
"""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pybullet as p
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import robot_utils  # noqa: E402
import run_logger  # noqa: E402
from test_eye_switch import MAIN, _assigns, _calls, _under  # noqa: E402
from test_look_correspondence import (_dry, _home, _planner, needs_pwsh,  # noqa: E402
                                      world)  # noqa: F401  (fixture)

EXECUTION = ast.parse((ROOT / 'execution.py').read_text(encoding='utf-8'))
DRIVER = ast.parse((ROOT / 'tampura_bridge' / 'run_bridge_on_finddice.py')
                   .read_text(encoding='utf-8'))
POLICY = ast.parse((ROOT / 'tampura_bridge' / 'policy.py').read_text(encoding='utf-8'))


def _under_text(tree, text):
    """The ids of every node in the body of an ``if`` whose test contains
    ``text``."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and text in ast.unparse(node.test):
            for stmt in node.body:
                out.update(id(n) for n in ast.walk(stmt))
    return out


def _test_holding(tree, call):
    """The test of the ``if`` whose test holds ``call``."""
    (test,) = [node.test for node in ast.walk(tree) if isinstance(node, ast.If)
               and id(call) in {id(n) for n in ast.walk(node.test)}]
    return test


# ----- 1. main() --------------------------------------------------------------------

def test_main_follows_the_arm_from_the_start_view_on():
    arm = _under(MAIN, "eye == 'arm'")
    (follow,) = _calls(MAIN, 'follow_arm')
    (start,) = _calls(MAIN, 'use_start_view')
    (after,) = _calls(MAIN, 'after_settle')
    (first,) = _calls(MAIN, 'get_camera_observation')
    assert id(follow) in arm
    assert [ast.unparse(a) for a in follow.args] == ['env'] and not follow.keywords
    assert start.lineno < follow.lineno < after.lineno < first.lineno


def test_with_the_arm_camera_the_planner_gets_no_camera():
    (call,) = _calls(MAIN, 'PDDLStreamPlanner')
    assert {k.arg: ast.unparse(k.value) for k in call.keywords}['camera_pos'] == \
        'planner_camera_pos'
    arm = _under(MAIN, "eye == 'arm'")
    got = {ast.unparse(a.value): id(a) in arm for a in _assigns(MAIN, 'planner_camera_pos')}
    assert got == {'env.camera_position': False, 'None': True}


def test_main_runs_no_blocker_census_with_the_arm_camera():
    fixed = _under(MAIN, "eye != 'arm'")
    calls = _calls(MAIN, 'compute_shadow_blockers')
    assert len(calls) == 2 and all(id(c) in fixed for c in calls)
    (empty,) = [a for a in _assigns(MAIN, 'shadow_occluder_map')
                if ast.unparse(a.value) == '{}']
    assert empty.lineno < min(c.lineno for c in calls)


def test_main_reads_the_frame_only_after_the_arm_switch_in_the_same_test():
    calls = _calls(MAIN, 'in_frame')
    assert len(calls) == 2                       # the post-place carve, the post-stack re-pose
    for call in calls:
        test = _test_holding(MAIN, call)
        assert isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And)
        parts = [ast.unparse(v) for v in test.values]
        holds = [i for i, v in enumerate(test.values)
                 if id(call) in {id(n) for n in ast.walk(v)}]
        assert parts.index("eye == 'arm'") < holds[0]


# ----- 2. execution.py ----------------------------------------------------------------

def test_execution_runs_no_blocker_census_with_the_arm_camera():
    guarded = _under_text(EXECUTION, 'not arm_eye.following(env)')
    calls = _calls(EXECUTION, 'compute_shadow_blockers')
    assert len(calls) == 3 and all(id(c) in guarded for c in calls)


# ----- 3. the bridge ----------------------------------------------------------------

def test_the_driver_takes_eye_and_passes_arm_alone_by_a_plain_if():
    (flag,) = [c for c in _calls(DRIVER, 'add_argument') if c.args
               and isinstance(c.args[0], ast.Constant) and c.args[0].value == '--eye']
    assert {k.arg: ast.literal_eval(k.value) for k in flag.keywords} == {
        'choices': ('fixed', 'arm'), 'default': 'fixed'}
    (cfg,) = _calls(DRIVER, 'EpisodeConfig')
    (switches,) = [k.value for k in cfg.keywords if k.arg == 'switches']
    keys = [k.value for k in switches.keys if isinstance(k, ast.Constant)]
    spread = [ast.unparse(v) for k, v in zip(switches.keys, switches.values) if k is None]
    assert 'eye' not in keys and not any("'eye'" in s for s in spread)
    assert any("'look'" in s for s in spread)             # the look entry stays as it was
    (record,) = _assigns(DRIVER, "cfg.switches['eye']")
    assert ast.unparse(record.value) == 'a.eye'
    assert id(record) in _under(DRIVER, "a.eye != 'fixed'")
    assert cfg.lineno < record.lineno


def test_the_policy_declares_no_eye_for_g20_with_the_arm_camera():
    (gate,) = _calls(POLICY, 'GateConfig')
    kw = {k.arg: ast.unparse(k.value) for k in gate.keywords}
    assert kw['camera_view'] == 'camera_view' and kw['camera_proj'] == 'camera_proj'
    arm = _under(POLICY, "cfg.switches.get('eye', 'fixed') == 'arm'")
    for name, fixed in (('camera_view', 'tuple(view)'), ('camera_proj', 'tuple(proj)')):
        got = {ast.unparse(a.value): id(a) in arm for a in _assigns(POLICY, name)}
        assert got == {fixed: False, '()': True}, name


@pytest.fixture
def gate(tmp_path):
    """A DIRECT client with a Panda (tampura_bridge/tests/test_gate_hooks.py's
    set-up) and the ledger; install(view, proj) puts the gates on as
    policy.py does, the Panda's wrist declared for G20."""
    import pybullet_data
    from tampura_bridge import gate_hooks
    c0 = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c0)
    robot = p.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True,
                       physicsClientId=c0)
    run_logger.ledger_open(tmp_path)

    def install(view, proj):
        gate_hooks.install(gate_hooks.GateConfig(
            executing_client=c0, robot_id=robot, camera_view=view,
            camera_proj=proj, wrist_robots={c0: robot}))
        gate_hooks.set_phase('main')

    yield SimpleNamespace(c0=c0, robot=robot, gh=gate_hooks, install=install)
    gate_hooks.uninstall()
    run_logger.ledger_close()
    p.disconnect(c0)


def test_g20_with_empty_eye_matrices_passes_only_the_wrist_at_fk(gate):
    gh = gate.gh
    eye_view = p.computeViewMatrix([0.1, -0.8, 0.7], [0.5, 0, 0], [0, 0, 1])
    eye_proj = p.computeProjectionMatrixFOV(49.1, 640 / 480, 0.02, 5.0)
    cam = robot_utils.wrist_camera_pose(gate.robot, gate.c0)
    wview, wproj = robot_utils.wrist_camera_matrices(cam)
    cam[:3, 3] += [0.0, 0.0, 0.05]
    moved, _ = robot_utils.wrist_camera_matrices(cam)
    gate.install((), ())                                  # policy.py with --eye arm
    p.getCameraImage(32, 24, wview, wproj, physicsClientId=gate.c0)
    for view, proj in ((eye_view, eye_proj), (moved, wproj)):
        before = gh.counts().get('G20', 0)
        with pytest.raises(gh.GateViolation):
            p.getCameraImage(32, 24, view, proj, physicsClientId=gate.c0)
        assert gh.counts().get('G20', 0) == before + 1
    gh.uninstall()
    gate.install(None, None)                              # None: nothing is checked
    p.getCameraImage(32, 24, eye_view, eye_proj, physicsClientId=gate.c0)
    p.getCameraImage(32, 24, moved, wproj, physicsClientId=gate.c0)
    assert gh.counts().get('G20', 0) == 0


# ----- 4. the planner ---------------------------------------------------------------

def test_a_planner_without_a_camera_makes_no_placement_hides(world, monkeypatch):
    pl = _planner(world)                                  # the look init, with a camera
    tested = []
    real = pl._compute_placement_hides
    monkeypatch.setattr(pl, '_compute_placement_hides',
                        lambda held: tested.append(held) or real(held))
    pl._build_init(['blue'], _home(), known_empty_shadows=[], moved_occluders={},
                   observed_clear_regions=None)
    assert len(tested) == 1                               # --eye fixed: as before
    pl.camera_pos = None                                  # what main() gives with --eye arm
    init = pl._build_init(['blue'], _home(), known_empty_shadows=[], moved_occluders={},
                          observed_clear_regions=None)
    assert len(tested) == 1
    assert not [f for f in init if f[0] == 'placement_hides']


# ----- 5. the launcher --------------------------------------------------------------

@needs_pwsh
def test_run_tampura_passes_the_arm_camera_to_the_driver():
    off = _dry(ROOT / 'run.ps1', 'tampura -Seed 5 -Look boxel')
    on = _dry(ROOT / 'run.ps1', 'tampura -Seed 5 -Look boxel -Eye arm')
    assert on.count('--eye') == 1
    assert on.replace(' --eye arm', '', 1) == off
    assert 'run_bridge_on_finddice.py' in on and '--look boxel --eye arm' in on
