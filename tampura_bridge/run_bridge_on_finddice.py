"""#P4 B2: our pipeline on TAMPURA's find_dice, one seed (PAPER_AUDIT.txt
P4.4 B2).  Arm O's driver: run_planner.py's order (seed random and numpy
with the global seed, build FindDiceEnv, initialize), then the bridge's
only additions: assert the loaded scene against the pinned map (G19),
register the boxel_episode schema (G13's one arm-O registration) and run
their rollout with BoxelBridgePolicy.  It stamps its clock and records the
RNG state for G18 and G19, and writes one outcome field that combines
rewards[-1], the error and the ledger reader's gates (RG1.7).  Exit code 0
iff that outcome is success.  Run from their tampura_environments
directory in arm O's venv:

  PYTHONPATH=<repo>:<pddlstream_lib>:<their tampura>:<their envs> \\
    <arm O python> <repo>/tampura_bridge/run_bridge_on_finddice.py \\
    --global-seed 0 --vis 0
"""
import argparse
import importlib.util
import json
import logging
import os
import random
import sys
import time

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# The curated console (console_ui, 2026-10-30): installed only when this
# file runs as the script at --log-level smart, before pybullet's import
# banner; the raw stdout and stderr go to the run's console_debug.log.
import console_ui                                # noqa: E402
console_ui.install_early(__name__)

from tampura.config import config as tconfig    # noqa: E402
import tampura_environments                      # noqa: E402,F401

from tampura_bridge import g13_runtime              # noqa: E402
from tampura_bridge import policy as bridge_policy   # noqa: E402
import slip_fixes                                    # noqa: E402  (BF#59, BF#62)
import world_counts                                  # noqa: E402  (TB-22, rule 18)


class _SceneFile(logging.Handler):
    """Their get_scene_data logs the scene file it loaded (env.py:806); the
    bridge reads that line and nothing of the file."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.name_seen = None

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith('Loading scene from '):
            self.name_seen = msg[len('Loading scene from '):].strip()


def _bridge_gates():
    """tools/bridge_gates.py: G19's pinned map (one place only) and the
    ledger reader behind the outcome field."""
    path = os.path.join(REPO, 'tools', 'bridge_gates.py')
    spec = importlib.util.spec_from_file_location('_bridge_gates', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rng_untouched(seed):
    """G19: both global RNGs are in the state their seeding left."""
    s, t = np.random.get_state(), np.random.RandomState(seed).get_state()
    return {'random': random.getstate() == random.Random(seed).getstate(),
            'numpy': (s[0] == t[0] and bool(np.array_equal(s[1], t[1]))
                      and tuple(s[2:]) == tuple(t[2:]))}


# BF#63 (Hani, 2026-11-03: a failed run keeps the screenshot that explains
# it): the final scene from two fixed cameras over the table, one oblique
# and one from above (the robot at the bottom); (file, eye, target, up).
OVERVIEW_VIEWS = (
    ('overview_final.png', (1.45, -0.35, 1.25), (0.40, 0.0, 0.15), (0, 0, 1)),
    ('overview_final_top.png', (0.45, 0.01, 0.94), (0.45, 0.01, 0.0), (1, 0, 0)),
)
OVERVIEW_SIZE = (1024, 768)


def _eye_target(run_dir):
    """(name, true position) of the target in the world eye's last record
    (eye.jsonl, its final snapshot; the eye's own logging-only read of the
    simulator, so the bridge makes no read of its own, G2), or None."""
    try:
        with open(os.path.join(run_dir, 'eye.jsonl'), 'r', encoding='utf-8') as f:
            last = [line for line in f if line.strip()][-1]
        for o in json.loads(last).get('objects', []):
            if o.get('role') == 'target' and o.get('true_pos') is not None:
                return o['name'], o['true_pos']
    except (OSError, TypeError, ValueError, IndexError, KeyError, AttributeError):
        pass
    return None


def _target_ring(img, target, view, proj):
    """A red ring round the target's true position, named: the die is 3 cm
    of grey on a grey table, a few pixels in a view of the whole table, and
    may sit under a cup (the ring is then on the cup)."""
    from PIL import ImageDraw
    name, pos = target
    V = np.asarray(view, dtype=float).reshape(4, 4).T
    P = np.asarray(proj, dtype=float).reshape(4, 4).T
    clip = P @ V @ np.append(np.asarray(pos, dtype=float), 1.0)
    if clip[3] <= 0:
        return
    x = (clip[0] / clip[3] + 1) / 2 * img.width
    y = (1 - clip[1] / clip[3]) / 2 * img.height
    r = 18
    d = ImageDraw.Draw(img)
    d.ellipse([x - r, y - r, x + r, y + r], outline=(220, 0, 0), width=3)
    d.text((x + r + 4, y - r), str(name), fill=(220, 0, 0))


def _save_overview(client, save_dir, target):
    """The final scene from OVERVIEW_VIEWS into save_dir, after the rollout
    and its record, so a run keeps a picture of where the die, the cups and
    the arm ended up (the eye images are the robot's own camera, which may
    not see a dropped die), the target ringed where the eye's final record
    puts it (_eye_target).  Only when the eye images are wanted
    (world_eye.images_wanted(): --save-screenshots on and BOXEL_EYE_IMAGES
    not 0); TinyRenderer, so headless runs make it too; a failure here
    never touches the episode."""
    import world_eye
    if not world_eye.images_wanted():
        return []
    import pybullet as p
    from PIL import Image
    W, H = OVERVIEW_SIZE
    proj = p.computeProjectionMatrixFOV(fov=55, aspect=W / H, nearVal=0.05, farVal=5.0)
    names = []
    for name, eye, look_at, up in OVERVIEW_VIEWS:
        try:
            view = p.computeViewMatrix(eye, look_at, up)
            w, h, rgba, _, _ = client.getCameraImage(W, H, viewMatrix=view, projectionMatrix=proj,
                                                     renderer=p.ER_TINY_RENDERER)
            img = Image.fromarray(np.asarray(rgba, dtype=np.uint8).reshape(h, w, 4)[:, :, :3])
            if target is not None:
                _target_ring(img, target, view, proj)
            img.save(os.path.join(save_dir, name))
            names.append(name)
        except Exception:
            pass
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='./env_configs/find_dice.yml')
    ap.add_argument('--global-seed', type=int, required=True)
    ap.add_argument('--vis', type=int, default=0)
    ap.add_argument('--save-dir', default=os.path.join(
        os.getcwd(), 'runs', f'bridge_{time.time()}'))
    ap.add_argument('--stop-before-planning', type=int, default=0)
    ap.add_argument('--log-level', default='smart')
    ap.add_argument('--max-plan-time', type=float, default=900.0)
    # BF#45: a headless diagnostic run on a scene the laptop maps to another
    # seed than the campaign does (BF#8, BF#39) continues past G19 like a
    # GUI run, never scored; the ledger's G19 gate records the mismatch.
    ap.add_argument('--allow-g19-mismatch', type=int, default=0)
    # M8-M10 (P4.5 model tweaks), passed through to main()'s CLI flags.
    # (--sense-over-region, BF#52: sense from the pick configuration over
    # the region when the arm there does not block the eye's view, then pick
    # from there; off returns to a view spot before every sense as before.)
    for flag in ('--m8', '--m9', '--m10', '--pick-aperture-from-pose',
                 '--sense-over-region'):
        ap.add_argument(flag, choices=('off', 'on'), default='on')
    # Path 9 (BF#68): one look action from a free-space boxel in place of
    # sense and observe; passed through only when on, so an off run's switches
    # (and its record) are those of before.
    ap.add_argument('--look', choices=('off', 'on', 'boxel', 'centred'), default='off')
    # Path 9, the arm camera only (arm_eye): every image from the arm camera
    # (main() refuses it without a look); passed through only when arm, so a
    # fixed run's switches (and its record) are those of before.
    ap.add_argument('--eye', choices=('fixed', 'arm'), default='fixed')
    # GF10 (BF#38): the pick close's squeeze (0.5 mm since BF#44), passed through like the switches.
    ap.add_argument('--grip-squeeze-mm', type=float, default=0.5)
    # BF#53: the optimistic search's settings (run_logger's flags of the
    # same names and defaults), passed through like the switches.
    ap.add_argument('--search-effort-weight', default='1')
    ap.add_argument('--search-initial-complexity', type=int, default=3)
    # BF#59: the die-slip campaign's switches (slip_fixes.py; run_logger's
    # --slip-fixes), passed through like the switches.  BF#62: an empty
    # value is the four defaults, 'none' the base arm; the episode's record
    # carries the effective set.
    ap.add_argument('--slip-fixes', default='')
    # BF#50 (user rule, 2026-10-30): the eye images are for debugging only,
    # off unless asked; passed through like the switches.
    ap.add_argument('--save-screenshots', choices=('off', 'on'), default='off')
    # TB-22 (tracks rule 18): the drop and collision counts of the episode's
    # record (run_logger's --world-counts: auto is on in a headless run),
    # passed through like the switches; off is the arm that measures their
    # cost.
    ap.add_argument('--world-counts', choices=('auto', 'on', 'off'), default='auto')
    # TB-25 (#P1 F32): how the planner tests a place cell against a look's
    # corridor (run_logger's --corridor-test, same choices and default),
    # passed through like the switches.  The default is the pipeline's own;
    # 'object' is the arm of an A/B, never set by the bridge itself.
    ap.add_argument('--corridor-test', choices=('cell+object', 'object'),
                    default='cell+object')
    # BF#68 (run tampura -Draw): what the GUI shows besides the scene, a comma
    # list of policy.DRAW_KINDS.  Nothing here reaches the executing world or
    # the result of a camera render (cameras only reads it); it is ignored
    # without --vis 1.
    ap.add_argument('--draw', default='',
                    help='comma list of what the GUI draws: '
                         + ', '.join(bridge_policy.DRAW_KINDS))
    a = ap.parse_args()
    draw = [d.strip() for d in a.draw.split(',') if d.strip()]
    unknown = [d for d in draw if d not in bridge_policy.DRAW_KINDS]
    if unknown:
        ap.error(f"--draw takes {', '.join(bridge_policy.DRAW_KINDS)} "
                 f"(a comma list), not {', '.join(unknown)}")
    arg_dict = {'config': a.config, 'global_seed': a.global_seed,
                'vis': bool(a.vis), 'save_dir': a.save_dir}
    config = tconfig.load_config(config_file=a.config, arg_dict=arg_dict)

    # G18: the driver's clock stamps (perf_counter, the ledger's clock),
    # written to the episode's ledger by execute_fn.
    events = []

    def stamp(name):
        events.append((name, time.perf_counter()))

    # G19: the global RNG is seeded exactly as run_planner.py does, and
    # nothing consumes it before their get_scene_data.
    random.seed(config['global_seed'])
    np.random.seed(config['global_seed'])
    stamp('seeded')
    tconfig.setup_logger(config['save_dir'], log_level=logging.INFO)
    scene = _SceneFile()
    logging.getLogger().addHandler(scene)

    rng_untouched = _rng_untouched(config['global_seed'])
    stamp('initialize_call')
    env = tconfig.get_env(config['task'])(config=config)
    b0, store = env.initialize()
    stamp('initialize_return')
    # Their initialize draws the visibility grid's boxes as GUI debug lines
    # (voxel_utils.draw_intervals, cloud_vis False); clear them so the GUI
    # shows the scene alone.  Debug lines are not in camera renders, so the
    # eye images are the same either way.
    def clear_debug_lines():
        for w in {id(x): x for x in (env.world, getattr(env, 'sim_world', None))
                  if x is not None}.values():
            w.client.removeAllUserDebugItems()

    if a.vis:
        clear_debug_lines()
        # BF#41: their rollout redraws the grid after every step
        # (Policy.rollout calls env.vis_updated_belief), so our get_action
        # clears it before each step and the driver once more after the
        # rollout.  Nothing is set when headless.
        bridge_policy.GUI_CLEANUP = clear_debug_lines

    gates = _bridge_gates()
    pinned = gates.SCENE_MAP.get(a.global_seed)
    mismatch = (scene.name_seen is None or pinned is None
                or pinned not in scene.name_seen)
    # The console's start-up note names their scene file the way their
    # logger does, before the G19 check, so a console reader finds
    # "Loading scene from" in every captured console as before.
    if scene.name_seen is not None:
        console_ui.startup(f"Loading scene from {scene.name_seen}"
                           + ('' if mismatch else " (the campaign's pinned scene for this seed)"))
    if mismatch and not a.vis and not a.allow_g19_mismatch:
        raise SystemExit(f"G19: seed {a.global_seed} loaded {scene.name_seen}, "
                         f"pinned {pinned}")
    if mismatch:
        # BF#39: a GUI run is for watching only and is never scored (P4.6
        # MODE).  Their problems/ listing order differs between the laptop
        # and the cluster (BF#8), so most seeds load another scene here than
        # the campaign map pins; the run goes on with the scene this machine
        # gave the seed, and the ledger's G19 gate records the mismatch (the
        # outcome field then says gate_failed).  Headless runs still stop.
        g19_note = (f"G19: seed {a.global_seed} loaded {scene.name_seen}, the campaign "
                    f"pins {pinned}: a watching or diagnostic run, never scored "
                    f"(the ledger's G19 gate records the mismatch)")
        print(g19_note, flush=True)
        console_ui.warn(g19_note)       # verbatim on the console as well
    if draw and not a.vis:
        draw_note = (f"--draw {','.join(draw)} is ignored without the GUI "
                     f"(--vis 0): nothing is drawn")
        print(draw_note, flush=True)
        console_ui.warn(draw_note)
        draw = []
    console_ui.set_context(scene=f"find_dice seed {a.global_seed}")
    stamp('scene_map_asserted')
    cfg = bridge_policy.EpisodeConfig(
        seed=a.global_seed, scene_file=scene.name_seen,
        log_dir=os.path.join(config['save_dir'], 'ours'), vis=bool(a.vis),
        draw=frozenset(draw),
        # BF#68, --draw cameras: the observer's pictures go here (absolute:
        # execute_fn changes into the run's work directory).
        camera_dir=(os.path.abspath(os.path.join(config['save_dir'], 'cameras'))
                    if 'cameras' in draw else ''),
        stop_before_planning=bool(a.stop_before_planning),
        log_level=a.log_level, max_plan_time=a.max_plan_time,
        switches={'m8': a.m8, 'm9': a.m9, 'm10': a.m10,
                  'pick_aperture_from_pose': a.pick_aperture_from_pose,
                  'sense_over_region': a.sense_over_region,
                  'grip_squeeze_mm': str(a.grip_squeeze_mm),
                  'world_counts': a.world_counts,
                  'corridor_test': a.corridor_test,
                  'search_effort_weight': a.search_effort_weight,
                  'search_initial_complexity': str(a.search_initial_complexity),
                  'slip_fixes': slip_fixes.resolve(a.slip_fixes),
                  'save_screenshots': a.save_screenshots,
                  **({'look': a.look} if a.look != 'off' else {})})
    if a.eye != 'fixed':                                  # path 9, the arm camera only
        cfg.switches['eye'] = a.eye
    cfg.driver = {'events': events, 'seed': config['global_seed'],
                  'rng_untouched': rng_untouched,
                  'pythonhashseed': os.environ.get('PYTHONHASHSEED')}
    execute_fn = bridge_policy.make_execute_fn(env, cfg)
    bridge_policy.register_schema(env, execute_fn)
    stamp('schema_registered')
    policy = bridge_policy.bridge_policy_class()(config, env.problem_spec)
    stamp('policy_built')
    # G13's runtime half (GF1): recorded, and the run stops here on a failure
    g13 = g13_runtime.check_arm_o(env, policy, b0, bridge_policy.SCHEMA_NAME, execute_fn)
    cfg.out['g13_runtime'] = g13
    g13_runtime.write_and_enforce(g13, config['save_dir'])
    stamp('g13_checked')
    stamp('rollout_start')
    history, _ = policy.rollout(env, b0, store)
    if a.vis:
        clear_debug_lines()

    cfg.out['rewards'] = [float(r) for r in history.rewards]
    cfg.out['time_deltas'] = [float(t) for t in history.time_deltas]
    # The outcome field (RG1.7): rewards[-1], the error and the ledger
    # reader's per-episode gates; success is never rewards[-1] alone.
    report = gates.Report()
    try:
        gates.run_ledger(report, cfg.out['run_dir'])
    except Exception as e:
        report.add('ledger', 'FAIL', f"{type(e).__name__}: {e}")
    cfg.out['ledger_gates'] = report.rows
    cfg.out['outcome'] = gates.episode_outcome(
        cfg.out['rewards'], cfg.out.get('error'), report)
    # TB-22 (tracks rule 18): drops, collisions, the two detector texts and
    # clean_success in the episode's record, from the pipeline's run (its
    # summary, or the counts file of a run that wrote none) under this
    # record's own success.
    cfg.out.update(world_counts.from_run_dir(
        cfg.out.get('run_dir'), success=cfg.out['outcome']['success']))
    with open(os.path.join(config['save_dir'], 'bridge_episode.json'), 'w') as f:
        # BF#41: the switches (M8 to M10, the aperture rule, the squeeze)
        # travel with the episode; bridge runs leave main()'s run_config
        # empty, so this is the one record of them.
        json.dump({'seed': a.global_seed, 'scene_file': scene.name_seen,
                   'switches': dict(cfg.switches), **cfg.out}, f, indent=1,
                  default=str)
    try:
        _save_overview(env.world.client, config['save_dir'],
                       _eye_target(cfg.out.get('run_dir') or ''))
    except Exception:
        pass
    # The gate table and the outcome line are curated output: on the
    # terminal (and mirrored into console_debug.log) under the console.
    with console_ui.terminal():
        report.show()
        print(f"seed {a.global_seed}: outcome {cfg.out['outcome']['status']}, their "
              f"RolloutHistory rewards[-1] = {history.rewards[-1]}; details in "
              f"{config['save_dir']}")
    return 0 if cfg.out['outcome']['success'] else 1


if __name__ == '__main__':
    # sys.exit(main()), except that with the console installed the process
    # ends right after the flush: pybullet's GUI teardown segfaults at
    # interpreter exit (bash's 'Segmentation fault' line under the console).
    console_ui.finish(main())
