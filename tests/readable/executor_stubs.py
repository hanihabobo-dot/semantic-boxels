"""executor_stubs.py: test-level executor stubs for pin 47's scripted tapes
(PLAN 5.2 row 47, REVIEW_PHASE0 B3).  Test code: nothing here edits a
pipeline file.  tools/readable/record_episode.py calls ``install(config)``
inside its episode child only, before the entry runs; each stub replaces a
module attribute right after that module has been executed by its normal
import (record_episode's import hook), so ``from execution import
execute_place`` in test_full_pipeline.py binds the stub.

A stub forces one branch of the dispatcher that no live episode is sure to
reach (a physical failure the search does not plan for), the same way each
time, so the branch's statements are run and their outputs pinned:

  place_empty_hand    execution.execute_place raises EmptyHandError at its
                      first call (the place entry assert: the empty-hand
                      path of the place branch).
  stack_empty_hand    execution.execute_stack the same (stack branch).
  carry_loss          execution.carry_hold_end reports a loss (held=False)
                      at the end of the first move made while holding (the
                      empty-hand path of the move branch).
  integrity_event     execution.world_integrity_check adds one event to its
                      real result at its first call (or, with "after", at
                      the first call whose label starts with that text,
                      e.g. "plan#2 place("): {"kind": "disturbed"} on the
                      first registered object that is not held (an
                      empty-hand replan), or {"kind": "knocked_off_table"}
                      on the goal object named in the config (the episode
                      ends).
  pick_fail           execution.execute_pick returns a failed PickResult
                      (nothing held, nothing touched) for the object named
                      in the config, at every call (the strike counter and
                      the give-up).
  place_fail          execution.execute_place returns None for the object
                      named in the config, at every call (the place
                      branch's failure path, test_full_pipeline.py:2884-2926
                      on the tag, SPEC D16).  "fingers": "closed" touches
                      nothing, so the fingers stay on the object (arm (a),
                      "IK failure during place"); "open" first opens the
                      gripper with the executor's own open_gripper, as the
                      release of a place does (placing=True), so the
                      dispatcher's finger probe finds them open (arm (b),
                      "drop-verify failed").
  sense_outcome       execution.sense_shadow_from_render runs for real; at
                      its first call the outcome is replaced by the one in
                      the config and the detected bodies by the pybullet id
                      of the named body (contains_nontarget: a body the
                      render shows; contains_unlocalizable: one it does not).
  home_offset         robot_utils.arm_joint_positions adds a fixed offset
                      to joint 0 when main() of test_full_pipeline reads it
                      (the at-home test fails; the start check is left).

Config: {"stubs": [{"name": ..., ...options}, ...]}.  Every stub writes one
row per call it changed to ``<rec>/stubs.jsonl``.
"""
import json
import sys
from pathlib import Path

NAMES = ('place_empty_hand', 'stack_empty_hand', 'carry_loss', 'integrity_event',
         'pick_fail', 'place_fail', 'sense_outcome', 'home_offset')
PLACE_FAIL_FINGERS = ('closed', 'open')


def _log(rec, row):
    with open(Path(rec) / 'stubs.jsonl', 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


def _caller_is_main_of_tfp(depth=1):
    f = sys._getframe(depth + 1)
    return (f is not None and f.f_code.co_name == 'main'
            and f.f_code.co_filename.replace('\\', '/').endswith('test_full_pipeline.py'))


def _patch_execution(mod, stubs, rec):
    for s in stubs:
        name = s['name']
        if name in ('place_empty_hand', 'stack_empty_hand'):
            attr = 'execute_place' if name == 'place_empty_hand' else 'execute_stack'
            orig = getattr(mod, attr)
            state = {'n': 0}

            def stub(*a, _orig=orig, _state=state, _attr=attr, _limit=int(s.get('times', 1)), **k):
                _state['n'] += 1
                if _state['n'] <= _limit:
                    _log(rec, {'stub': _attr, 'call': _state['n'], 'raised': 'EmptyHandError'})
                    raise mod.EmptyHandError(f'{_attr}: empty hand at entry (executor stub)')
                return _orig(*a, **k)
            setattr(mod, attr, stub)
        elif name == 'carry_loss':
            orig = mod.carry_hold_end
            state = {'done': False}

            def stub(robot_id, held_body_id, start, obj_name, dest, gui=False,
                     _orig=orig, _state=state):
                if held_body_id is not None and not _state['done']:
                    _state['done'] = True
                    _log(rec, {'stub': 'carry_hold_end', 'obj': str(obj_name), 'dest': str(dest),
                               'held': False})
                    print(f"    carry_hold_check: move to {dest} holding {obj_name}: "
                          f"LOSS (executor stub)")
                    return mod.CarryHold(False, frozenset(), 0.0, 0, 0.0)
                return _orig(robot_id, held_body_id, start, obj_name, dest, gui)
            mod.carry_hold_end = stub
        elif name == 'integrity_event':
            orig = mod.world_integrity_check
            state = {'done': False}
            kind = s.get('kind', 'disturbed')
            target = s.get('object')
            after = s.get('after')

            def stub(*a, _orig=orig, _state=state, _kind=kind, _target=target, _after=after, **k):
                events, dets, render = _orig(*a, **k)
                if _state['done'] or (_after and not str(k.get('label', '')).startswith(_after)):
                    return events, dets, render
                held = k.get('held_name')
                if _kind == 'knocked_off_table':
                    obj = _target
                else:
                    reg = k['registry']
                    names = sorted(bd.id for bd in reg.get_boxels_by_type(mod.BoxelType.OBJECT)
                                   if bd.id != held and not getattr(k['env'].objects.get(bd.id),
                                                                    'is_tray', False))
                    obj = names[0] if names else None
                if obj is None:
                    return events, dets, render
                _state['done'] = True
                ev = {'kind': _kind, 'object': obj, 'label': k.get('label', '')}
                if _kind == 'disturbed':
                    ev['shift_mm'] = 0.0
                _log(rec, {'stub': 'world_integrity_check', 'event': ev})
                print(f"    [integrity] {_kind}: {obj} after {k.get('label', '')} (executor stub)")
                return list(events) + [ev], dets, render
            mod.world_integrity_check = stub
        elif name == 'pick_fail':
            orig = mod.execute_pick
            obj_name = s['object']

            def stub(robot_id, env, name_, *a, _orig=orig, _obj=obj_name, **k):
                if name_ == _obj:
                    _log(rec, {'stub': 'execute_pick', 'obj': name_, 'result': 'failed'})
                    print(f"    pick of {name_}: failed (executor stub)")
                    return mod.PickResult(None, None, frozenset())
                return _orig(robot_id, env, name_, *a, **k)
            mod.execute_pick = stub
        elif name == 'place_fail':
            import inspect
            orig = mod.execute_place
            sig = inspect.signature(orig)

            def stub(robot_id, env, name_, *a, _orig=orig, _sig=sig, _obj=s['object'],
                     _fingers=s['fingers'], **k):
                if name_ != _obj:
                    return _orig(robot_id, env, name_, *a, **k)
                if _fingers == 'open':
                    gui = _sig.bind(robot_id, env, name_, *a, **k).arguments.get('gui', False)
                    mod.open_gripper(robot_id, gui, placing=True)
                _log(rec, {'stub': 'execute_place', 'obj': name_, 'fingers': _fingers, 'result': None})
                print(f"    place of {name_}: failed, fingers {_fingers} (executor stub)")
                return None
            mod.execute_place = stub
        elif name == 'sense_outcome':
            orig = mod.sense_shadow_from_render
            state = {'done': False}
            outcome = s['outcome']
            body = s['body']

            def stub(*a, _orig=orig, _state=state, _outcome=outcome, _body=body, **k):
                res = _orig(*a, **k)
                # only the sense action's classification, not the other
                # callers (the lost-region check reads it too)
                if _state['done'] or sys._getframe(1).f_code.co_name != 'handle_sense_action':
                    return res
                _state['done'] = True
                # '#none': a pybullet id no body has (nothing in the render)
                ids = NO_BODY_ID if _body == '#none' else _BODY_IDS.get(_body)
                if ids is None:
                    raise RuntimeError(f'sense_outcome stub: body {_body!r} unknown')
                new = (_outcome, res[1], {ids}, res[3], res[4])
                _log(rec, {'stub': 'sense_shadow_from_render', 'outcome_real': res[0],
                           'outcome': _outcome, 'body': _body})
                return new
            mod.sense_shadow_from_render = stub


# pybullet ids of named bodies, filled when BoxelTestEnv has built its scene
_BODY_IDS = {}
NO_BODY_ID = 10 ** 6


def _patch_boxel_env(mod, rec):
    cls = mod.BoxelTestEnv
    orig = cls.__init__

    def __init__(self, *a, **k):
        orig(self, *a, **k)
        # the last scene built wins (the pre-flight probe builds the same
        # scene first, in its own client; the run's scene comes after)
        for n, info in self.objects.items():
            _BODY_IDS[n] = info.object_id
    cls.__init__ = __init__


def _patch_robot_utils(mod, stubs, rec):
    for s in stubs:
        if s['name'] != 'home_offset':
            continue
        orig = mod.arm_joint_positions
        delta = float(s.get('offset_rad', 0.01))
        state = {'n': 0}

        def stub(robot_id, _orig=orig, _delta=delta, _state=state):
            q = _orig(robot_id)
            if not _caller_is_main_of_tfp():
                return q
            _state['n'] += 1
            if _state['n'] == 1:          # the start check (D7 (v)) is left as it is
                return q
            q = q.copy()
            q[0] = q[0] + _delta
            _log(rec, {'stub': 'arm_joint_positions', 'call': _state['n'], 'offset_rad': _delta})
            return q
        mod.arm_joint_positions = stub


def install(config, rec, patch_on_load):
    """Register the stubs of ``config`` (a dict or JSON text).
    ``patch_on_load(name, fn)`` is record_episode's import hook."""
    if isinstance(config, str):
        config = json.loads(config)
    stubs = list(config.get('stubs', []))
    for s in stubs:
        if s.get('name') not in NAMES:
            raise ValueError(f'unknown executor stub {s.get("name")!r}; known: {NAMES}')
        if s['name'] == 'place_fail' and (not s.get('object') or s.get('fingers') not in PLACE_FAIL_FINGERS):
            raise ValueError(f'place_fail needs "object" and "fingers" (one of {PLACE_FAIL_FINGERS}): {s}')
    Path(rec).mkdir(parents=True, exist_ok=True)
    (Path(rec) / 'stubs.json').write_text(json.dumps(config, indent=1, sort_keys=True) + '\n',
                                          encoding='utf-8', newline='\n')
    ex = [s for s in stubs if s['name'] != 'home_offset']
    if ex:
        patch_on_load('execution', lambda mod: _patch_execution(mod, ex, rec))
    if any(s['name'] == 'sense_outcome' for s in stubs):
        patch_on_load('boxel_env', lambda mod: _patch_boxel_env(mod, rec))
    if any(s['name'] == 'home_offset' for s in stubs):
        patch_on_load('robot_utils', lambda mod: _patch_robot_utils(mod, stubs, rec))
    return stubs
