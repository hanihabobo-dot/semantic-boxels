"""#P4 B0: runtime gate hooks (PAPER_AUDIT.txt #P4, P4.1).

install(cfg) wraps
  * every pybullet function that writes world or robot state (G14),
  * the motor commands and robot_utils.move_robot_smooth (G3),
  * stepSimulation (G6: no physics step during D9's set-up, after main()
    returns, or after the last dispatched action),
  * getAABB, getBasePositionAndOrientation, getClosestPoints,
    getContactPoints, rayTest and rayTestBatch (G8(b)),
  * getCameraImage (G20),
  * robot_utils.solve_ik (G14's net-zero exemption) and the two collision
    checks (task-body poses unchanged across them, G14),
  * PDDLStreamPlanner.plan (G10) and the solve() it calls (G11(ii)).

The pybullet wraps sit on the module.  BulletClient looks a function up on
the module at call time but injects its client id only into builtins, so
install() gives BulletClient.__getattr__ the same injection for the wrapped
functions; forwarding is otherwise unchanged.  Names bound with
`from robot_utils import solve_ik` are rebound in every loaded module of
this repository.

A hook that sees a violation increments a counter, writes a ledger row and
raises GateViolation.  The main pipeline's diagnostics swallow broad
exceptions (world_eye.py:172-176, telemetry.py:201-205), so the counters
decide: gate_record() writes them to the run ledger after the episode
(G21), and any count above 0 fails the episode.
"""

import functools
import hashlib
import inspect
import os
import sys
import weakref
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Optional

import pybullet

from console import run_logger

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class GateViolation(RuntimeError):
    """Raised by a runtime gate hook.  The counter, not the exception,
    decides the episode."""


@dataclass
class GateConfig:
    executing_client: int = 0
    robot_id: Optional[int] = None
    arm_joints: tuple = (0, 1, 2, 3, 4, 5, 6)
    # Task bodies in the executing world (the die and the cups).
    task_body_ids: frozenset = frozenset()
    # True when the body has an OBJECT boxel in the registry (G8(b)).
    has_object_boxel: Callable = field(default=lambda body_id: False)
    # The body the dispatcher holds, or None (tactile queries, G8(b)).
    held_body: Callable = field(default=lambda: None)
    # G20: the matrices every render must use (None: renders are logged
    # but not checked).
    camera_view: Optional[tuple] = None
    camera_proj: Optional[tuple] = None
    camera_tol: float = 1e-6
    # G20, M8 C2: client -> robot whose wrist camera may render there; a
    # render passes when its matrices are that camera's at the robot's
    # current forward kinematics (the declared mount, robot_utils).
    wrist_robots: dict = field(default_factory=dict)
    # G10: the mission goal and the target symbol T (None: not checked).
    mission_goal: Optional[tuple] = None
    target_symbol: Optional[str] = None
    domain_file: str = os.path.join(REPO, 'pddl', 'domain_pddlstream.pddl')
    stream_file: str = os.path.join(REPO, 'pddl', 'stream.pddl')


# Writers that name a body: name -> ((positional index, keyword), ...).
_BODY_WRITERS = {
    'resetBasePositionAndOrientation': ((0, 'bodyUniqueId'),),
    'resetBaseVelocity': ((0, 'objectUniqueId'),),
    'resetJointState': ((0, 'bodyUniqueId'),),
    'resetJointStateMultiDof': ((0, 'bodyUniqueId'),),
    'resetJointStatesMultiDof': ((0, 'bodyUniqueId'),),
    'changeDynamics': ((0, 'bodyUniqueId'),),
    'applyExternalForce': ((0, 'objectUniqueId'),),
    'applyExternalTorque': ((0, 'objectUniqueId'),),
    'setCollisionFilterGroupMask': ((0, 'bodyUniqueId'),),
    'setCollisionFilterPair': ((0, 'bodyUniqueIdA'), (1, 'bodyUniqueIdB')),
    'createConstraint': ((0, 'parentBodyUniqueId'), (2, 'childBodyUniqueId')),
    'removeBody': ((0, 'bodyUniqueId'),),
}
# Writers that take no body id fail on the executing client outright.
_BODYLESS_WRITERS = (
    'changeConstraint', 'removeConstraint', 'createMultiBody', 'loadURDF',
    'loadSDF', 'loadMJCF', 'loadBullet', 'loadSoftBody', 'saveState',
    'restoreState', 'resetSimulation', 'setRealTimeSimulation', 'setGravity',
    'setTimeStep', 'setPhysicsEngineParameter',
)
_MOTORS = ('setJointMotorControl2', 'setJointMotorControlArray',
           'setJointMotorControlMultiDof', 'setJointMotorControlMultiDofArray')
_BODY_QUERIES = ('getAABB', 'getBasePositionAndOrientation')
_PAIR_QUERIES = ('getClosestPoints', 'getContactPoints')
_RAYS = ('rayTest', 'rayTestBatch')
_PHASES = ('setup', 'main', 'post')

_cfg: Optional[GateConfig] = None
_counts = Counter()
_info = Counter()
_steps = Counter()
_phase = 'setup'
_scoring = 0
_write_only = []
_captures = []
_ik_exempt = []
_ik_steps = []
_seen_dispatch = False
_steps_since_dispatch = 0
_solve_calls = 0
_pybullet_originals = {}
_rebound = []
_patched_attrs = []
_orig_plan_code = None
_planner_cls = None
_streams_cls = None
_expected_sha = {}


# ----- helpers -----------------------------------------------------------

def _client(kwargs):
    return kwargs.get('physicsClientId', 0)


def _arg(args, kwargs, idx, kw):
    if kw in kwargs:
        return kwargs[kw]
    if len(args) > idx:
        return args[idx]
    return None


def _violation(gate, fn, detail):
    _counts[gate] += 1
    run_logger.ledger_event('gate_violation', gate=gate, fn=fn, detail=detail)
    raise GateViolation(f"{gate}: {fn}: {detail}")


def _executing(kwargs):
    return _cfg is not None and _client(kwargs) == _cfg.executing_client


def _hidden(body):
    return (body is not None and body in _cfg.task_body_ids
            and not _cfg.has_object_boxel(body))


def _read_exempt():
    return _scoring > 0 or bool(_write_only)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _norm(goal):
    if isinstance(goal, (list, tuple)):
        return tuple(_norm(g) for g in goal)
    return str(goal)


def _close(a, b, tol):
    if a is None or b is None:
        return False
    a, b = list(a), list(b)
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol
                                    for x, y in zip(a, b))


def _arm_positions(client, robot_id):
    return tuple(pybullet.getJointState(robot_id, j, physicsClientId=client)[0]
                 for j in _cfg.arm_joints)


def _task_poses(client):
    get = _pybullet_originals.get('getBasePositionAndOrientation',
                                  pybullet.getBasePositionAndOrientation)
    return {b: get(b, physicsClientId=client)
            for b in sorted(_cfg.task_body_ids)}


# ----- pybullet hooks ----------------------------------------------------

def _check_body_write(name, body, args, kwargs):
    if body == _cfg.robot_id:
        if (name == 'resetJointState' and _ik_exempt
                and _ik_exempt[-1] == (_cfg.executing_client, body)
                and _arg(args, kwargs, 1, 'jointIndex') in _cfg.arm_joints):
            return
        _violation('G14', name, f'write to the executing robot (body {body})')
    if body in _cfg.task_body_ids:
        _violation('G14', name, f'write to task body {body}')
    _info['other_body_write'] += 1
    run_logger.ledger_event('gate_info', note='other_body_write', fn=name,
                            body=body)


def _make_writer(name, orig, slots):
    def hook(*args, **kwargs):
        if _executing(kwargs) and _phase != 'setup':
            if slots is None:
                enabling = (name != 'setRealTimeSimulation'
                            or _arg(args, kwargs, 0, 'enableRealTimeSimulation'))
                if enabling:
                    _violation('G14', name,
                               'body-less state write on the executing client')
            else:
                for idx, kw in slots:
                    body = _arg(args, kwargs, idx, kw)
                    if body is not None and body >= 0:
                        _check_body_write(name, body, args, kwargs)
        return orig(*args, **kwargs)
    return hook


def _make_motor(name, orig):
    def hook(*args, **kwargs):
        if (_executing(kwargs) and _phase != 'setup'
                and _arg(args, kwargs, 0, 'bodyUniqueId') == _cfg.robot_id
                and run_logger.current_dispatch() is None):
            _violation('G3', name, 'motor command on the executing robot '
                                   'outside a dispatched action')
        return orig(*args, **kwargs)
    return hook


def _make_step(orig):
    def hook(*args, **kwargs):
        global _seen_dispatch, _steps_since_dispatch
        if _executing(kwargs):
            if _ik_steps:
                _ik_steps[-1] += 1
            if _phase == 'setup':
                _steps['setup'] += 1
                _violation('G6', 'stepSimulation',
                           "physics step during D9's set-up")
            elif _phase == 'post':
                _steps['post'] += 1
                _violation('G6', 'stepSimulation',
                           'physics step after main() returned')
            elif run_logger.current_dispatch() is not None:
                _steps['main_in_dispatch'] += 1
                _seen_dispatch = True
                _steps_since_dispatch = 0
            else:
                _steps['main_outside_dispatch'] += 1
                if _seen_dispatch:
                    _steps_since_dispatch += 1
        return orig(*args, **kwargs)
    return hook


def _make_body_query(name, orig):
    def hook(*args, **kwargs):
        if _executing(kwargs) and not _read_exempt():
            body = _arg(args, kwargs, 0, 'bodyUniqueId')
            if _hidden(body):
                _violation('G8', name, f'query of task body {body} that has '
                                       f'no OBJECT boxel')
        return orig(*args, **kwargs)
    return hook


def _make_pair_query(name, orig):
    def hook(*args, **kwargs):
        if _executing(kwargs) and not _read_exempt():
            a = _arg(args, kwargs, 0, 'bodyA')
            b = _arg(args, kwargs, 1, 'bodyB')
            if a is None or a < 0:
                _violation('G8', name, 'unfiltered contact query on the '
                                       'executing client')
            tactile = a == _cfg.robot_id or (a == _cfg.held_body()
                                             and a is not None)
            if not tactile:
                for body in (a, b):
                    if _hidden(body):
                        _violation('G8', name, f'query of task body {body} '
                                               f'that has no OBJECT boxel')
        return orig(*args, **kwargs)
    return hook


def _make_ray(name, orig):
    def hook(*args, **kwargs):
        if _executing(kwargs) and not _read_exempt():
            _violation('G8', name, 'ray cast on the executing client')
        _info[f'{name}_client_{_client(kwargs)}'] += 1
        return orig(*args, **kwargs)
    return hook


def _make_camera(orig):
    def hook(*args, **kwargs):
        view = _arg(args, kwargs, 2, 'viewMatrix')
        proj = _arg(args, kwargs, 3, 'projectionMatrix')
        capture = _captures[-1] if _captures else None
        matched = None
        camera = None
        if _cfg.camera_view is not None and capture is None:
            matched = (_close(view, _cfg.camera_view, _cfg.camera_tol)
                       and _close(proj, _cfg.camera_proj, _cfg.camera_tol))
            camera = 'eye' if matched else None
            robot = _cfg.wrist_robots.get(_client(kwargs))
            if not matched and robot is not None:
                from acting import robot_utils
                wv, wp = robot_utils.wrist_camera_matrices(
                    robot_utils.wrist_camera_pose(robot, _client(kwargs)))
                matched = (_close(view, wv, _cfg.camera_tol)
                           and _close(proj, wp, _cfg.camera_tol))
                camera = 'wrist' if matched else None
        run_logger.ledger_event(
            'render', client=_client(kwargs), capture=capture, matched=matched,
            camera=camera,
            view=list(view) if view is not None else None,
            proj=list(proj) if proj is not None else None)
        if matched is False:
            _violation('G20', 'getCameraImage',
                       'render with matrices other than the declared eye or '
                       'the wrist camera at its FK pose')
        return orig(*args, **kwargs)
    return hook


# ----- repository hooks --------------------------------------------------

def _make_solve_ik(orig):
    @functools.wraps(orig)
    def solve_ik(robot_id, *args, **kwargs):
        client = kwargs.get('physics_client', args[2] if len(args) > 2 else 0)
        if (client != _cfg.executing_client or robot_id != _cfg.robot_id
                or _phase == 'setup'):
            return orig(robot_id, *args, **kwargs)
        if run_logger.current_dispatch() is None:
            _violation('G14', 'solve_ik', 'IK on the executing robot outside '
                                          'a dispatched action')
        before = _arm_positions(client, robot_id)
        _ik_exempt.append((client, robot_id))
        _ik_steps.append(0)
        result = None
        try:
            result = orig(robot_id, *args, **kwargs)
        finally:
            _ik_exempt.pop()
            steps = _ik_steps.pop()
            after = _arm_positions(client, robot_id)
            if steps or before != after:
                _violation('G14', 'solve_ik',
                           f'not net-zero: {steps} physics step(s), arm '
                           f'restored bit-identically: {before == after}')
        return result
    return solve_ik


def _make_collision_check(name, orig):
    sig = inspect.signature(orig)

    @functools.wraps(orig)
    def check(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        client = bound.arguments.get('physics_client', 0)
        if client != _cfg.executing_client or not _cfg.task_body_ids:
            return orig(*args, **kwargs)
        before = _task_poses(client)
        result = orig(*args, **kwargs)
        if _task_poses(client) != before:
            _violation('G14', name, 'task-body poses changed across a '
                                    'collision check')
        return result
    return check


def _make_move_smooth(orig):
    @functools.wraps(orig)
    def move_robot_smooth(robot_id, *args, **kwargs):
        if (_phase != 'setup' and robot_id == _cfg.robot_id
                and run_logger.current_dispatch() is None):
            _violation('G3', 'move_robot_smooth', 'arm motion outside a '
                                                  'dispatched action')
        return orig(robot_id, *args, **kwargs)
    return move_robot_smooth


def check_plan_call(planner, goal, target_objects):
    """G10 at one plan() call: planner and streams types exactly, domain and
    stream text, the goal and the target pin.  Writes the call to the
    ledger; a mismatch is a violation."""
    problems = []
    if type(planner) is not _planner_cls:
        problems.append(f'planner type {type(planner).__name__}')
    if type(getattr(planner, 'streams', None)) is not _streams_cls:
        problems.append('streams type '
                        f'{type(getattr(planner, "streams", None)).__name__}')
    if _sha(getattr(planner, 'domain_pddl', '')) != _expected_sha['domain']:
        problems.append('domain text differs from the declared domain file')
    if _sha(getattr(planner, 'stream_pddl', '')) != _expected_sha['stream']:
        problems.append('stream text differs from pddl/stream.pddl')
    if _cfg.mission_goal is not None:
        allowed = (_norm(_cfg.mission_goal), _norm(('handempty',)))
        if _norm(goal) not in allowed:
            problems.append(f'goal {goal!r}')
    targets = list(target_objects or [])
    if _cfg.target_symbol is not None and targets != [_cfg.target_symbol]:
        problems.append(f'target_objects {targets!r}')
    run_logger.ledger_event('plan_call', goal=goal, targets=targets,
                            problems=problems)
    if problems:
        _violation('G10', 'plan', '; '.join(problems))


def _make_plan(orig):
    sig = inspect.signature(orig)

    @functools.wraps(orig)
    def plan(self, *args, **kwargs):
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        check_plan_call(self, bound.arguments.get('goal'),
                        bound.arguments.get('target_objects'))
        return orig(self, *args, **kwargs)
    return plan


def _make_solve(orig):
    @functools.wraps(orig)
    def solve(*args, **kwargs):
        global _solve_calls
        _solve_calls += 1
        caller = sys._getframe(1).f_code
        if caller is not _orig_plan_code:
            _violation('G11', 'solve', f'called from {caller.co_name} '
                                       f'({caller.co_filename}:'
                                       f'{caller.co_firstlineno})')
        return orig(*args, **kwargs)
    return solve


def _make_observer(name, orig):
    @functools.wraps(orig)
    def observer(*args, **kwargs):
        with write_only(name), capture(name):
            return orig(*args, **kwargs)
    return observer


_registry_ref = None
_bodies_at_install = None
_TWIN_TOL = 1e-9
# G8(c), GF7: a twin's collision AABB centre against its registry centre.
# Gate 1's feasibility check measured at most 4.7 mm over every find_dice
# class (the YCB mesh origin is not its AABB centre); 1.3 mm of headroom.
TWIN_AABB_TOL_M = 0.006


def _make_sync_check(orig):
    @functools.wraps(orig)
    def sync_to_plan_client(self, held_body_id=None, registry=None):
        out = orig(self, held_body_id=held_body_id, registry=registry)
        if registry is not None and self.client_id == _cfg.executing_client:
            _check_twin(self, held_body_id, registry)
        return out
    return sync_to_plan_client


def _far(a, b, tol):
    return max(abs(float(x) - float(y)) for x, y in zip(a, b)) > tol


def _check_twin(env, held_body_id, registry):
    """G8(c) on the plan twin (plan-client reads; the held body's EE is
    proprioception).  Every non-static twin is upright (identity
    quaternion); a boxel-less body sits at the park pose, the held body at
    the EE, every other body at its registry centre, and that twin's
    collision AABB centre lies within TWIN_AABB_TOL_M of the registry
    centre (YCB twins are posed by their origin, not their AABB centre)."""
    get = _pybullet_originals.get('getBasePositionAndOrientation',
                                  pybullet.getBasePositionAndOrientation)
    aabb = _pybullet_originals.get('getAABB', pybullet.getAABB)
    park = env._PLAN_CLIENT_PARK
    for name, info in env.objects.items():
        if name in ('plane', 'table', 'robot') or info.is_tray:
            continue
        pid = env._gui_to_plan.get(info.object_id)
        if pid is None:
            continue
        pos, orn = get(pid, physicsClientId=env.plan_client_id)
        _info['G8c_bodies_checked'] += 1
        if _far(orn, (0.0, 0.0, 0.0, 1.0), _TWIN_TOL):
            _violation('G8', 'sync_to_plan_client',
                       f'{name}: plan twin not upright ({list(orn)})')
        if info.object_id == held_body_id:
            _info['G8c_held_checked'] += 1
            ee = pybullet.getLinkState(
                _cfg.robot_id, _ee_link(),
                physicsClientId=_cfg.executing_client)[0]
            if _far(pos, ee, _TWIN_TOL):
                _violation('G8', 'sync_to_plan_client',
                           f'{name}: held twin at {list(pos)}, not at the EE')
            continue
        bd = registry.get_boxel(name)
        want = bd.center if bd is not None else park
        if _far(pos, want, _TWIN_TOL):
            _violation('G8', 'sync_to_plan_client',
                       f'{name}: plan twin at {list(pos)}, expected '
                       f'{"its registry centre" if bd is not None else "the park pose"}')
        elif bd is not None:
            lo, hi = aabb(pid, physicsClientId=env.plan_client_id)
            centre = [(a + b) / 2.0 for a, b in zip(lo, hi)]
            off = max(abs(c - float(w)) for c, w in zip(centre, want))
            _info['G8c_aabb_offset_max_um'] = max(
                _info['G8c_aabb_offset_max_um'], int(round(off * 1e6)))
            if off > TWIN_AABB_TOL_M:
                _violation('G8', 'sync_to_plan_client',
                           f'{name}: twin AABB centre {off * 1e3:.2f} mm from '
                           f'the registry centre')
    _info['G8c_syncs'] += 1


def _ee_link():
    from acting import robot_utils
    return robot_utils.robot_model().ee_link


def _make_registry_init(orig):
    @functools.wraps(orig)
    def __init__(self, *args, **kwargs):
        global _registry_ref
        orig(self, *args, **kwargs)
        _registry_ref = weakref.ref(self)
    return __init__


def latest_registry():
    """The BoxelRegistry most recently created while the hooks were
    installed (main()'s), or None."""
    return _registry_ref() if _registry_ref is not None else None


def _rebind(module_name, attr, wrapper):
    """Replace module_name.attr and every binding of the same object in a
    loaded module of this repository."""
    original = getattr(sys.modules[module_name], attr)
    for mod in list(sys.modules.values()):
        path = os.path.abspath(getattr(mod, '__file__', None) or '')
        if not path.startswith(REPO + os.sep):
            continue
        if getattr(mod, attr, None) is original:
            setattr(mod, attr, wrapper)
            _rebound.append((mod, attr, original))


def _patch_bullet_client():
    try:
        from pybullet_utils import bullet_client
    except ImportError:
        return
    cls = bullet_client.BulletClient
    original = cls.__getattr__

    def __getattr__(self, name):
        attribute = getattr(pybullet, name)
        if getattr(attribute, '_gate_wrapped', False):
            return functools.partial(attribute, physicsClientId=self._client)
        return original(self, name)

    cls.__getattr__ = __getattr__
    _patched_attrs.append((cls, '__getattr__', original))


# ----- public API --------------------------------------------------------

def install(cfg: GateConfig) -> None:
    """Install every hook.  Call before the episode starts; the phase starts
    at 'setup' (D9's set-up)."""
    global _cfg, _orig_plan_code, _planner_cls, _streams_cls
    if _cfg is not None:
        raise RuntimeError('gate hooks already installed')
    from planning import pddlstream_planner
    from acting import robot_utils
    from planning import streams
    _cfg = cfg
    reset_counts()
    set_phase('setup')

    def wrap(name, hook):
        hook._gate_wrapped = True
        hook.__name__ = name
        _pybullet_originals[name] = getattr(pybullet, name)
        setattr(pybullet, name, hook)

    for name, slots in _BODY_WRITERS.items():
        if hasattr(pybullet, name):
            wrap(name, _make_writer(name, getattr(pybullet, name), slots))
    for name in _BODYLESS_WRITERS:
        if hasattr(pybullet, name):
            wrap(name, _make_writer(name, getattr(pybullet, name), None))
    for name in _MOTORS:
        if hasattr(pybullet, name):
            wrap(name, _make_motor(name, getattr(pybullet, name)))
    for name in _BODY_QUERIES:
        wrap(name, _make_body_query(name, getattr(pybullet, name)))
    for name in _PAIR_QUERIES:
        wrap(name, _make_pair_query(name, getattr(pybullet, name)))
    for name in _RAYS:
        wrap(name, _make_ray(name, getattr(pybullet, name)))
    wrap('stepSimulation', _make_step(pybullet.stepSimulation))
    wrap('getCameraImage', _make_camera(pybullet.getCameraImage))
    _patch_bullet_client()

    _rebind('acting.robot_utils', 'solve_ik', _make_solve_ik(robot_utils.solve_ik))
    _rebind('acting.robot_utils', 'move_robot_smooth',
            _make_move_smooth(robot_utils.move_robot_smooth))
    # BF#2 (g): world_eye and telemetry are pure observers that read the
    # simulator (every body, the hidden die included) and render their own
    # images; they run as the declared write-only set and captures.
    from console import telemetry
    from world import world_eye
    for mod, names in ((world_eye, ('enable', 'snapshot', 'disable')),
                       (telemetry, ('enable', 'tick', 'phase', 'note',
                                    'disable', 'attach_robot',
                                    'register_bodies'))):
        for name in names:
            if hasattr(mod, name):
                _rebind(mod.__name__, name,
                        _make_observer(f'{mod.__name__.rpartition(".")[2]}.{name}',
                                       getattr(mod, name)))
    # G8(c): after every belief-posed sync, each body with an OBJECT boxel
    # sits at its registry centre in the plan twin and every boxel-less
    # body at the park pose.
    from world import boxel_env
    _patched_attrs.append((boxel_env.BoxelTestEnv, 'sync_to_plan_client',
                           boxel_env.BoxelTestEnv.sync_to_plan_client))
    boxel_env.BoxelTestEnv.sync_to_plan_client = _make_sync_check(
        boxel_env.BoxelTestEnv.sync_to_plan_client)
    global _bodies_at_install
    _bodies_at_install = pybullet.getNumBodies(
        physicsClientId=cfg.executing_client)
    # G8(b) asks whether a task body has an OBJECT boxel: the registry
    # main() builds is recorded here as it is created.
    from world import boxel_data
    _patched_attrs.append((boxel_data.BoxelRegistry, '__init__',
                           boxel_data.BoxelRegistry.__init__))
    boxel_data.BoxelRegistry.__init__ = _make_registry_init(
        boxel_data.BoxelRegistry.__init__)
    for name in ('is_config_collision_free', 'is_path_collision_free'):
        _rebind('acting.robot_utils', name,
                _make_collision_check(name, getattr(robot_utils, name)))

    _planner_cls = pddlstream_planner.PDDLStreamPlanner
    _streams_cls = streams.BoxelStreams
    _orig_plan_code = _planner_cls.plan.__code__
    _patched_attrs.append((_planner_cls, 'plan', _planner_cls.plan))
    _planner_cls.plan = _make_plan(_planner_cls.plan)
    _patched_attrs.append((pddlstream_planner, 'solve',
                           pddlstream_planner.solve))
    pddlstream_planner.solve = _make_solve(pddlstream_planner.solve)
    for key, path in (('domain', cfg.domain_file), ('stream', cfg.stream_file)):
        with open(path, 'r') as f:
            _expected_sha[key] = _sha(f.read())


def installed() -> bool:
    return _cfg is not None


def declare_wrist_robot(client: int, robot_id: int) -> None:
    """G20: a robot whose wrist camera may render in this client (the plan
    twin's, known only once the env adapter has built it)."""
    _cfg.wrist_robots[client] = robot_id
    run_logger.ledger_event('gate_info', note='wrist_robot', client=client,
                            robot=robot_id)


def uninstall() -> None:
    global _cfg, _registry_ref
    _registry_ref = None
    for name, original in _pybullet_originals.items():
        setattr(pybullet, name, original)
    _pybullet_originals.clear()
    for mod, attr, original in reversed(_rebound):
        setattr(mod, attr, original)
    _rebound.clear()
    for owner, attr, original in reversed(_patched_attrs):
        setattr(owner, attr, original)
    _patched_attrs.clear()
    _cfg = None


def reset_counts() -> None:
    global _seen_dispatch, _steps_since_dispatch, _solve_calls
    _counts.clear()
    _info.clear()
    _steps.clear()
    _seen_dispatch = False
    _steps_since_dispatch = 0
    _solve_calls = 0


def set_phase(phase: str) -> None:
    """'setup' (D9's set-up only), 'main' (the env adapter build and
    main()), 'post' (after main() returned, while the observation is
    built)."""
    global _phase
    if phase not in _PHASES:
        raise ValueError(phase)
    _phase = phase
    run_logger.ledger_event('gate_phase', phase=phase)


@contextmanager
def scoring():
    """The scoring adapter's contact and joint readback (G2, G8(b))."""
    global _scoring
    _scoring += 1
    try:
        yield
    finally:
        _scoring -= 1


@contextmanager
def write_only(name: str):
    """A declared write-only reader (G2): world_eye, telemetry, the
    print-only diagnostics, the scoring-only verifiers, the after_settle
    hook.  G2's leak test checks that nothing read here reaches a
    decision."""
    _write_only.append(name)
    try:
        yield
    finally:
        _write_only.pop()


@contextmanager
def capture(name: str):
    """A declared write-only render (G20): world_eye images, GUI panes."""
    _captures.append(name)
    try:
        yield
    finally:
        _captures.pop()


def check_readback(at_main_return, observation_conf) -> bool:
    """G6: the arm readback taken when main() returned equals the
    observation's conf bit for bit.  A mismatch counts against the episode
    (no exception: the observation is still returned and scored)."""
    same = [float(v) for v in at_main_return] == [float(v) for v in observation_conf]
    run_logger.ledger_event('readback_check', identical=same,
                            at_main_return=list(at_main_return),
                            observation_conf=list(observation_conf))
    if not same:
        _counts['G6'] += 1
        run_logger.ledger_event('gate_violation', gate='G6', fn='readback',
                                detail='observation conf differs from the '
                                       'readback at main() return')
    return same


def count_update_object_positions() -> None:
    """G16: the env adapter's update_object_positions is a counted no-op."""
    _info['G16_update_object_positions_noop'] += 1


def oracle_called(name: str = 'oracle_detect_objects') -> None:
    """G16: the env adapter's oracle path raises."""
    _violation('G16', name, 'oracle path called')


def counts() -> dict:
    return dict(_counts)


def gate_record() -> dict:
    """G21: write the episode's counts to the ledger.  Physics steps after
    the last dispatched action are added to G6 here."""
    if _steps_since_dispatch:
        _counts['G6'] += _steps_since_dispatch
    if _cfg is not None and _bodies_at_install is not None:
        # B3(b) / B2: the executing world neither gained nor lost a body.
        now = pybullet.getNumBodies(physicsClientId=_cfg.executing_client)
        _info['executing_bodies_at_install'] = _bodies_at_install
        _info['executing_bodies_now'] = now
        if now != _bodies_at_install:
            _counts['G14'] += 1
            run_logger.ledger_event('gate_violation', gate='G14',
                                    fn='getNumBodies',
                                    detail=f'{_bodies_at_install} -> {now}')
    rec = {'counts': dict(_counts), 'info': dict(_info),
           'steps': dict(_steps),
           'steps_after_last_dispatch': _steps_since_dispatch,
           'solve_calls': _solve_calls}
    run_logger.ledger_event('gate_record', **rec)
    return rec
