"""How TAMPURA's find_dice carries the held die: runs their run_planner.py
unchanged, with read-only counters around SceneState.apply_sequence.

For every apply_sequence call made while state.grasp is set (the carry),
records the physics steps, joint resets, motor commands and die pose
resets issued during it, the die's pose in the tool-tip frame before and
after, and the finger pad contacts with the die at the end.  Nothing in
their code path is changed; the wrappers only count and read.

  (arm O venv, cwd tampura_environments)
  python tools/_probe_tampura_carry.py <out json> --config ./env_configs/find_dice.yml \\
      --global-seed 0 --save-dir <dir>
"""
import collections
import json
import runpy
import sys

import numpy as np
from pybullet_utils import bullet_client

OUT = sys.argv.pop(1)
counts = collections.Counter()
die_resets = collections.Counter()
calls = []
TRACKED = ('stepSimulation', 'resetJointState', 'setJointMotorControl2',
           'setJointMotorControlArray', 'resetBasePositionAndOrientation')

# Count at the client's attribute lookup: the bound call (with its
# physicsClientId) is returned unchanged, only wrapped to count.
_orig_getattr = bullet_client.BulletClient.__getattr__


def _counting_getattr(self, name):
    attr = _orig_getattr(self, name)
    if name not in TRACKED:
        return attr

    def counted(*a, **k):
        counts[name] += 1
        if name == 'resetBasePositionAndOrientation':
            die_resets[int(a[0] if a else k.get('objectUniqueId'))] += 1
        return attr(*a, **k)
    return counted


bullet_client.BulletClient.__getattr__ = _counting_getattr

from tampura_environments.panda_utils import panda_env_utils as peu   # noqa: E402
from tampura_environments.panda_utils import pb_utils as pbu          # noqa: E402

_orig_apply = peu.SceneState.apply_sequence


def tool_frame_pose(state, body):
    c = state.world.client
    tool = pbu.link_from_name(state.world.robot, peu.PANDA_TOOL_TIP, client=c)
    tp = pbu.get_link_pose(state.world.robot, tool, client=c)
    bp = pbu.get_pose(body, client=c)
    rel = pbu.multiply(pbu.invert(tp), bp)
    return [round(float(v), 6) for v in rel[0]], [round(float(v), 6) for v in rel[1]], \
        [round(float(v), 4) for v in bp[0]]


def apply_sequence(self, sequence, *a, **k):
    if self.grasp is None:
        return _orig_apply(self, sequence, *a, **k)
    body = int(self.grasp.body)
    before_counts, before_resets = counts.copy(), die_resets[body]
    rel0, quat0, world0 = tool_frame_pose(self, body)
    out = _orig_apply(self, sequence, *a, **k)
    rel1, quat1, world1 = tool_frame_pose(self, body)
    c = self.world.client
    pads = [cp for cp in c.getContactPoints(bodyA=int(self.world.robot), bodyB=body)]
    calls.append({
        'teleport_arg': k.get('teleport', a[0] if a else False),
        'sim_steps_arg': k.get('sim_steps', 0),
        'die_body': body,
        'die_world_start': world0, 'die_world_end': world1,
        'die_in_tool_frame_start': rel0, 'die_in_tool_frame_end': rel1,
        'die_quat_in_tool_frame_start': quat0, 'die_quat_in_tool_frame_end': quat1,
        'die_pose_resets_during': die_resets[body] - before_resets,
        'calls_during': {kk: counts[kk] - before_counts[kk] for kk in counts},
        'robot_die_contacts_at_end': len(pads),
        'robot_die_normal_force_at_end': round(sum(cp[9] for cp in pads), 3),
    })
    print('[carry probe]', json.dumps(calls[-1]), flush=True)
    return out


peu.SceneState.apply_sequence = apply_sequence

sys.argv = ['run_planner.py'] + sys.argv[1:]
try:
    runpy.run_path('run_planner.py', run_name='__main__')
finally:
    with open(OUT, 'w') as f:
        json.dump(calls, f, indent=1)
