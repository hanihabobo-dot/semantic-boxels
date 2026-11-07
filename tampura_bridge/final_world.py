"""#P4 path 6, DV-1: arm T's world after their rollout, read for the standard test.

Hani (2026-11-07): "no, mkae our test the standard test."  On the fresh
find_dice scenes the standard success test is ours on both arms: the target
body held between both finger pads, the arm at home.  Our own arm's test reads
physical contact and force; TAMPURA's executor carries the held body
kinematically (their Attachment), so for arm T the same facts are read from
its live world in a geometric form:

  attached   their SceneState.grasp holds a body of the target category;
  pads       both finger pads within PAD_GAP_MAX_M of that body (their
             get_grasp closes the fingers to (1 + closed_fraction) times the
             contact position, closed_fraction 5e-2, so each pad can sit up
             to about 2 mm off the body: a 1 mm bound would sit on that gap);
  at home    the arm's 7 joints equal DEFAULT_ARM_POS under their own
             at-home test (np.allclose, rtol 1e-4, atol 1e-4), read from the
             joints, not from their belief (their go-home reports the home
             configuration even when its motion plan failed).

It runs once per episode, after their rollout has returned (the one reviewed
wrapper in timed_policy.py; G13's amendment, tampura_bridge/g13_runtime.py).
Evaluation only: nothing it reads reaches their policy, belief or history,
and a failure to read never raises; it is recorded in the file, and the
harness then does not count the episode (tools/gen_scene_eval.py).  The raw
gaps and joint readings go beside the verdict, so a threshold can be
re-judged from the records.
"""
import json
import os

FILE = 'final_world.json'
SCHEMA = 1
PAD_GAP_MAX_M = 0.002       # DV-1: each pad within 2 mm of the held body
SEARCH_DISTANCE_M = 0.05    # getClosestPoints radius; no point inside it = no gap
HOME_RTOL = 1e-4            # their at-home test, SceneBelief.abstract
HOME_ATOL = 1e-4


def body_id(value):
    """Their bodies are ints; a store symbol reads 'physical#N'."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return int(str(value).split('#')[-1])


def all_close(a, b, rtol=HOME_RTOL, atol=HOME_ATOL):
    """numpy.allclose on two sequences: |a - b| <= atol + rtol * |b|."""
    return len(a) == len(b) and all(
        abs(x - y) <= atol + rtol * abs(y) for x, y in zip(a, b))


def _their_defaults():
    """Their constants, read when a read happens (their packages are on the
    path of arm T's process; the unit tests pass fakes instead)."""
    from tampura_environments.find_dice.env import TARGET_OBJECT
    from tampura_environments.panda_utils.robot import (DEFAULT_ARM_POS,
                                                        GRIPPER_GROUP)
    return TARGET_OBJECT, list(DEFAULT_ARM_POS), GRIPPER_GROUP


def read_world(env, target_category=None, home=None, gripper_group=None,
               pad_gap_max_m=PAD_GAP_MAX_M, search_distance_m=SEARCH_DISTANCE_M):
    """The raw readings of their live world (a dict of plain numbers)."""
    if target_category is None or home is None or gripper_group is None:
        cat, home_default, group = _their_defaults()
        target_category = cat if target_category is None else target_category
        home = home_default if home is None else home
        gripper_group = group if gripper_group is None else gripper_group
    state = env.state
    world = state.world
    robot = world.robot
    client = world.client
    raw = {'schema': SCHEMA, 'target_category': target_category,
           'pad_gap_max_m': pad_gap_max_m, 'search_distance_m': search_distance_m}

    targets = [body_id(o) for o, c in zip(world.objects, world.categories)
               if c == target_category]
    raw['target_bodies'] = targets
    grasp = getattr(state, 'grasp', None)
    held = None if grasp is None else body_id(grasp.body)
    raw['grasp_body'] = held
    raw['attached'] = held is not None and held in targets

    joints = robot.get_group_joints(gripper_group, client=client)
    links = [int(k) for k in robot.get_finger_links(joints, client=client)]
    raw['pad_links'] = links
    probe = held if raw['attached'] else (targets[0] if len(targets) == 1 else None)
    raw['gap_body'] = probe
    gaps = []
    for link in links:
        if probe is None:
            gaps.append(None)
            continue
        points = client.getClosestPoints(bodyA=robot.body, bodyB=probe,
                                         distance=search_distance_m,
                                         linkIndexA=link)
        dist = [float(pt[8]) for pt in points]       # pybullet: contactDistance
        gaps.append(min(dist) if dist else None)
    raw['pad_gaps_m'] = gaps

    q = [float(v) for v in state.current_q]
    raw['arm_q'] = q
    raw['home_q'] = [float(v) for v in home]
    raw['home_dev_max_rad'] = (max(abs(a - b) for a, b in zip(q, home))
                               if len(q) == len(home) else None)
    raw['at_home'] = all_close(q, home)
    return raw


def verdict(raw):
    """The standard test on the raw readings."""
    gaps = raw.get('pad_gaps_m') or []
    limit = raw.get('pad_gap_max_m', PAD_GAP_MAX_M)
    pads = len(gaps) == 2 and all(g is not None and abs(g) <= limit for g in gaps)
    return {'pads_on_target': pads,
            'standard_success': bool(raw.get('attached') and pads and raw.get('at_home'))}


def record_after_rollout(env, save_dir, **kwargs):
    """Reads their world, writes save_dir/final_world.json, returns the record.
    Never raises: an unreadable world is {'ok': False, 'error': ...}."""
    rec = {'schema': SCHEMA, 'ok': False, 'standard_success': False}
    try:
        raw = read_world(env, **kwargs)
        rec.update(raw)
        rec.update(verdict(raw))
        rec['ok'] = True
    except Exception as e:          # evaluation only: a failed read must not touch their run
        rec['error'] = f'{type(e).__name__}: {e}'
    try:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, FILE)
        with open(path + '.tmp', 'w') as f:
            json.dump(rec, f, indent=1, default=str)
        os.replace(path + '.tmp', path)
    except Exception:               # whatever fails here (a None folder included): no file, never a raise
        pass                         # no file = unreadable; the harness does not count it
    return rec
