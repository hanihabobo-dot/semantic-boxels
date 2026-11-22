"""Path 9, step 3's completeness test: one tabletop episode with --eye arm and
every render it makes recorded (tracks/look/ARM_ONLY_DESIGN.md, step 3, part
5, and the look manager's addition: "the completeness test ... runs on a
tabletop episode too, not only on find_dice, and the renders it caught are
recorded").

The episode is test_full_pipeline.main in a DIRECT world with --no-gui --look
boxel --eye arm, on the scene `run boxels -Seed N` builds (run.ps1: --scene
random-pairs --goal holding --n-occluders 2).  A hook on
pybullet.getCameraImage records every render: its client, the functions on
the stack above it, and whether its view and projection matrices are the
wrist camera's at the forward kinematics of that client's robot at that
moment (G20's wrist clause, tampura_bridge/gate_hooks.py _make_camera, with
its tolerance GateConfig.camera_tol).  The robots are the env's own in
env.client_id and the plan twin's in env.plan_client_id; a render in any
other client has no robot and fails.

Writes renders.tsv (one row per render) and summary.json into --out, prints
every render that is not the wrist camera at its FK pose, and exits 1 when
there is one, 2 when every render passed but the episode raised, 0
otherwise.  Not a pytest test: an episode takes 10 to 40 s and runs under the
pipeline lock (tracks rule 7), which the caller takes, as run.ps1 does:

    cd <checkout> && PYTHONHASHSEED=0 flock /root/sb_pipeline.lock \\
        /root/armO-venvA/bin/python tools/eye_render_audit.py --out <dir> [--seed 0]

Pipeline flags after -- are appended as they are (argparse: the last wins).
"""
import argparse
import json
import os
import random
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np          # noqa: E402
import pybullet             # noqa: E402

from sensing import arm_eye              # noqa: E402
from acting import robot_utils          # noqa: E402
from tampura_bridge import gate_hooks   # noqa: E402

# G20's tolerance (tampura_bridge/gate_hooks.py, GateConfig.camera_tol).
CAMERA_TOL = gate_hooks.GateConfig.camera_tol
# The switches under audit, headless.
ARM_ONLY = ['--no-gui', '--look', 'boxel', '--eye', 'arm']
# The scene run.ps1's `run boxels` builds: its -Scene, -Goal and -Occluders
# defaults (the seed is --seed, run.ps1's -Seed).
RUN_BOXELS = ['--scene', 'random-pairs', '--goal', 'holding', '--n-occluders', '2']
# The frames named for each render, the caller of getCameraImage first.
STACK_DEPTH = 6


def wrist_rule(view, proj, robot, client, tol: float = CAMERA_TOL) -> bool:
    """G20's wrist clause: the render's matrices are the wrist camera's at
    the robot's forward kinematics in that client at the moment of the call,
    compared as the gate compares them (gate_hooks._close).  No robot:
    False."""
    if robot is None:
        return False
    wview, wproj = robot_utils.wrist_camera_matrices(
        robot_utils.wrist_camera_pose(robot, client))
    return (gate_hooks._close(view, wview, tol)
            and gate_hooks._close(proj, wproj, tol))


def _arg(args, kwargs, index, keyword):
    if keyword in kwargs:
        return kwargs[keyword]
    return args[index] if len(args) > index else None


def _callers(depth: int = STACK_DEPTH) -> str:
    """file:function:line of the frames above getCameraImage, innermost
    first."""
    frame = sys._getframe(2)
    names = []
    while frame is not None and len(names) < depth:
        code = frame.f_code
        names.append(f"{Path(code.co_filename).name}:{code.co_name}:{frame.f_lineno}")
        frame = frame.f_back
    return ' < '.join(names)


class RenderLog:
    """Every pybullet.getCameraImage while installed, judged by wrist_rule
    against ``robots`` (client -> robot id) at the moment of the render."""

    def __init__(self):
        self.rows = []
        self.robots = {}
        self.sides = {}
        self._real = None

    def watch(self, env):
        """The robots of an env: its own in env.client_id, the plan twin's
        in env.plan_client_id."""
        self.robots[env.client_id] = env.objects['robot'].object_id
        self.sides[env.client_id] = 'executing'
        if getattr(env, 'plan_robot_id', None) is not None:
            self.robots[env.plan_client_id] = env.plan_robot_id
            self.sides[env.plan_client_id] = 'plan twin'

    def install(self):
        real = self._real = pybullet.getCameraImage
        log = self

        def getCameraImage(*args, **kwargs):
            client = kwargs.get('physicsClientId', 0)
            view = _arg(args, kwargs, 2, 'viewMatrix')
            proj = _arg(args, kwargs, 3, 'projectionMatrix')
            robot = log.robots.get(client)
            eye = (arm_eye.view_pose(view)[:3, 3].round(4).tolist()
                   if view is not None else None)
            log.rows.append({'k': len(log.rows), 'client': client,
                             'side': log.sides.get(client, 'other'),
                             'wrist': wrist_rule(view, proj, robot, client),
                             'eye': eye, 'callers': _callers()})
            return real(*args, **kwargs)

        pybullet.getCameraImage = getCameraImage

    def uninstall(self):
        if self._real is not None:
            pybullet.getCameraImage = self._real
            self._real = None

    def bad(self):
        return [r for r in self.rows if not r['wrist']]


def watch_envs(log):
    """main() builds its env inside: every BoxelTestEnv built while this is
    on gives its robots to ``log``.  Returns the undo."""
    from world import boxel_env
    cls = boxel_env.BoxelTestEnv
    real = cls.__init__

    def __init__(self, *args, **kwargs):
        real(self, *args, **kwargs)
        log.watch(self)

    cls.__init__ = __init__
    return lambda: setattr(cls, '__init__', real)


def run_episode(argv):
    """test_full_pipeline.main as its __main__ block calls it for this
    command line: every process-global RNG from --seed, the random-pairs
    scene.  Left out: the pre-flight probe (it builds an env of its own) and
    the run_config record (main() reads it only for its log and the run
    summary)."""
    from console import run_logger
    from console import telemetry
    import test_full_pipeline as pipeline
    from world import world_eye
    args = run_logger.parse_pipeline_args(argv)
    pipeline.args = args
    random.seed(args.seed)
    np.random.seed(args.seed)
    scene = pipeline.random_pairs_scene(n_occluders=args.n_occluders,
                                        extra_distractors=args.n_extra_distractors,
                                        seed=args.seed)
    logger = run_logger.RunLogger(verbosity=args.log_level)
    try:
        return pipeline.main(
            gui=False, run_logger=logger, scene_config=scene,
            draw_boxel_overlays=not args.no_boxel_viz, show_free=args.show_free,
            goal_kind=args.goal, stack_height=args.stack_height,
            unit_costs=args.unit_costs, baseline=args.baseline,
            uniform_cell_size=args.uniform_cell_size,
            min_boxel_size=args.min_boxel_size,
            telemetry_enabled=args.telemetry,
            telemetry_period=args.telemetry_period,
            telemetry_heartbeat=args.telemetry_heartbeat)
    finally:
        telemetry.disable()
        world_eye.disable()
        logger.close()


def write(log, out: Path, argv, returned, error) -> dict:
    """renders.tsv and summary.json in ``out``; returns the summary."""
    with open(out / 'renders.tsv', 'w', encoding='utf-8', newline='\n') as f:
        f.write('k\tclient\tside\twrist_at_fk\teye_x\teye_y\teye_z\tcallers\n')
        for r in log.rows:
            eye = r['eye'] or ['', '', '']
            f.write(f"{r['k']}\t{r['client']}\t{r['side']}\t"
                    f"{'yes' if r['wrist'] else 'no'}\t{eye[0]}\t{eye[1]}\t{eye[2]}\t"
                    f"{r['callers']}\n")
    by_caller, by_side = {}, {}
    for r in log.rows:
        frames = r['callers'].split(' < ')[:2]
        key = ' < '.join(fr.rsplit(':', 1)[0] for fr in frames)
        for table, k in ((by_caller, key), (by_side, r['side'])):
            entry = table.setdefault(k, {'renders': 0, 'not_wrist': 0})
            entry['renders'] += 1
            entry['not_wrist'] += int(not r['wrist'])
    summary = {'argv': list(argv), 'renders': len(log.rows),
               'not_wrist': len(log.bad()), 'by_side': by_side,
               'by_caller': by_caller,
               'episode': {'returned': returned, 'error': error}}
    with open(out / 'summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=1)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', required=True,
                    help='the folder for renders.tsv and summary.json')
    ap.add_argument('--seed', type=int, default=0, help="run boxels' -Seed (default 0)")
    ap.add_argument('pipeline', nargs=argparse.REMAINDER,
                    help='more pipeline flags after --, as they are')
    a = ap.parse_args(argv)
    extra = [x for x in a.pipeline if x != '--']
    pipeline_argv = ARM_ONLY + RUN_BOXELS + ['--seed', str(a.seed)] + extra
    if os.environ.get('PYTHONHASHSEED') != '0':
        print("eye_render_audit: PYTHONHASHSEED is not 0 (run.ps1 sets it), so "
              "the episode may differ from run boxels'", file=sys.stderr)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)            # pddlstream's temp/ where run boxels has it (cd $S)
    log = RenderLog()
    undo = watch_envs(log)
    log.install()
    returned, error = None, None
    try:
        returned = run_episode(pipeline_argv)
    except Exception as e:    # the record is written either way
        error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        log.uninstall()
        undo()
    summary = write(log, out, pipeline_argv, returned, error)
    for r in log.bad():
        print(f"NOT THE WRIST AT FK: render {r['k']}, client {r['client']} "
              f"({r['side']}), eye at {r['eye']}: {r['callers']}")
    print(f"eye_render_audit: {summary['renders']} renders, "
          f"{summary['not_wrist']} not the wrist camera at its FK pose; the "
          f"episode {'raised ' + error if error else 'returned ' + repr(returned)}; "
          f"{out / 'renders.tsv'}")
    if summary['not_wrist']:
        return 1
    return 2 if error else 0


if __name__ == '__main__':
    sys.exit(main())
