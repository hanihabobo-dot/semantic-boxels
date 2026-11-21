"""record_episode.py: one whole episode, headless, with the solver's answers
recorded or replayed (Phase 0 of the readable migration, PLAN 5.2 pin 47 and
24.3, pins 30, 34 and 46).

    python tools/readable/record_episode.py --episode rp0 --mode record --run-dir DIR
    python tools/readable/record_episode.py --episode rp0 --mode replay --run-dir DIR --tape DIR/tape
    python tools/readable/record_episode.py --episode br0 --mode first-plan --run-dir DIR
    python tools/readable/record_episode.py --episode f293 --mode record --run-dir DIR --set execution.M7_SUSPEND_S=1e9
    python tools/readable/record_episode.py --record-set SET --episodes rp0,rp1,stack0,br0,br5
    python tools/readable/record_episode.py --episode f140 --print-argv   # what it starts; starts nothing
    python tools/readable/record_episode.py --renorm DIR          # normalise a run folder again
    python tools/readable/record_episode.py --coverage TRACE [TRACE ...]
    python tools/readable/record_episode.py --coverage TRACE ... --baseline OLD.json --old-tfp OLD.py

Episodes: the table EPISODES (configuration D), f<seed> and r<seed> (the
paper's arms F and R on a generated find_dice scene: the harness's command
for arm O, then the declared string, see "Entries beyond the table"), a
boxels entry with _look (the tabletop start `run boxels -Headless -Look
boxel -Eye arm`), and any of these with _m7off (its --m7 off twin).  The
parent takes an episode's argv from its entry only; it refuses positional
arguments.
--record-set counts, at storing, the ledger rows SPEC D3 and D4 decide on
(STORED.json beside each tape, STORE.json over the set), records a run
that holds m7_suspension rows again at once with execution.M7_SUSPEND_S =
1e9 (D4; the first recording kept as <name>.as_recorded, the value in the
tape's META.json), and records the --m7 off twin D3 asks for right after,
unless the call names it or the set holds it from an earlier call (so a
twin can have a call, and a hold of the lock, of its own).

The tool never takes the pipeline lock itself: its caller runs it under
``flock /root/sb_pipeline.lock`` (a nested flock on the same file from a
child would wait for ever).  Whole episodes go through the health gate
(tracks/meeting_2026-11-13/scripts/gate_run.ps1).

The parent starts one child interpreter per episode (cwd, environment and
argv as ``run boxels -Headless`` and ``run tampura -Headless`` build them,
run.ps1:149-171, with ``--log-level normal`` so no console takes over the
terminal, and ``--no-telemetry`` for boxels as the eval runner passes it).
The child patches only inside its own process, never a pipeline file:

  record      ``pddlstream_planner.solve`` is wrapped when that module has
              been executed (an import hook, so the import order of the real
              entry is kept, PLAN rule 6).  Each call stores, at the time of
              the call, the returned solution (pickle), the text the solver
              printed into plan()'s ``_StdoutTee`` during the call (the chunks
              added by this call only), the init facts and goal of the
              problem, the RNG digests before and after, and the RNG states
              after.  The wrapper is set before tampura_bridge.gate_hooks
              wraps ``solve``, so the gate wrapper stays the outermost one and
              G11 still sees plan() as the caller.
  replay      tests/readable/replay_stub.py's stub is set the same way: call
              k returns a fresh unpickled copy of solution k, prints the
              stored text into the tee, and (``--rng restore``, the default)
              puts back the RNG states the live search left, so the draws
              after the call are the live ones.  A call beyond the tape stops
              the run (ReplayTapeError, a BaseException nothing in the
              pipeline catches).  ``--trace-main`` records the lines of
              test_full_pipeline.py that ran (sys.settrace, the coverage
              table of PLAN 24.3 (b)); it changes no value.
  first-plan  ``PDDLStreamPlanner.plan`` is replaced by a recorder that
              writes its keyword arguments, the module switches set by
              main's stage B (and the arm camera's follow flag on main's
              env), every attribute of the planner and of its streams (a
              plain value as itself, anything else by its type), the RNG
              digests and (bridge) the gate counts, then raises
              StopAtPlan.  main's parameters at entry come from a
              sys.setprofile hook that removes itself at main's first call.

Scripted tapes (tools/readable/scripted_tapes.py) replay like live ones;
``--stubs JSON`` sets the test-level executor stubs of
tests/readable/executor_stubs.py in the child, and ``--tfp-copy`` (or
READABLE_TFP_COPY) runs a planted copy of test_full_pipeline.py for the
planted-change checks of PLAN 24.3 (e) only.  ``--set NAME=VALUE`` (SPEC
D5, NAME from the closed list SET_NAMES, VALUE read by float()) sets a
module value in the child right after the module is executed; the applied
pair goes to rec/SET.json, to a recording's tape/META.json and to
result.json, and a replay takes it from the tape's META.json (a --set that
differs is refused).

After the child the parent writes RESULT.json and the normalised outputs
(``norm/``): times and wall clocks masked to ``<s>`` with their keys kept
(SPEC D6), the ledger's pid removed, ``plan_obj`` ints and ``Type@id``
strings mapped to their order of first use (PLAN 24.3 (d)), paths and
stamps masked.  Nothing here edits a plan between planner and executor in
the pipeline: the replay is test code (PLAN D9).
"""
import argparse
import ast
import contextlib
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import pickle
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve()
STUB_FILE = REPO / 'tests' / 'readable' / 'replay_stub.py'
TFP = REPO / 'test_full_pipeline.py'
DRIVER = REPO / 'tampura_bridge' / 'run_bridge_on_finddice.py'
TW = '/root/tampura-work'
TW_ENVS = TW + '/tampura_environments'
GEN_DIR = REPO / 'tampura_bridge' / 'gen_scenes' / 'find_dice'
EPISODE_TIMEOUT_S = 3600
EXEC_STUBS_FILE = REPO / 'tests' / 'readable' / 'executor_stubs.py'
TFP_COPY_VAR = 'READABLE_TFP_COPY'

_BOXELS = ['--no-gui', '--log-level', 'normal', '--no-telemetry']


def _rp(seed):
    # run.ps1:170 (run boxels: random-pairs, holding, 2 occluders) -Headless.
    return {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'random-pairs', '--seed', str(seed),
                                       '--goal', 'holding', '--n-occluders', '2',
                                       '--log-level', 'normal', '--no-telemetry']}


def _br(seed, gen=False):
    # run.ps1:142-166 (run tampura -Headless [-Gen]).
    return {'kind': 'bridge', 'gen': gen,
            'argv': ['--global-seed', str(seed), '--vis', '0', '--save-dir', '<SAVE>',
                     '--allow-g19-mismatch', '1', '--log-level', 'normal']}


EPISODES = {f'rp{s}': _rp(s) for s in range(5)}
# Seed 1 with run boxels' 2 occluders is rejected at the pre-flight ("Could
# not place 2 hidden targets"), so rp1 is a pre-flight crash; rp1o3 is seed 1
# with the CLI's default 3 occluders, a whole episode.
EPISODES['rp1o3'] = {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'random-pairs', '--seed', '1',
                                                '--goal', 'holding', '--n-occluders', '3',
                                                '--log-level', 'normal', '--no-telemetry']}
EPISODES['stack0'] = {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'stack', '--seed', '0',
                                                 '--goal', 'stack', '--log-level', 'normal',
                                                 '--no-telemetry']}
EPISODES.update({'br0': _br(0), 'br1': _br(1), 'br5': _br(5), 'br100': _br(100, gen=True)})
PIN47_EPISODES = ('rp0', 'rp1', 'rp1o3', 'stack0', 'br0', 'br5')


# ---------------------------------------------------------------------------
# Entries beyond the table: F and R, the tabletop look start, the --m7 off twins
# ---------------------------------------------------------------------------
# EPISODES above is configuration D (PLAN 5.8: the launcher's defaults).  The
# paper's two arms of ours run on TAMPURA's generated find_dice scenes:
#
#   f<seed>, r<seed>  the harness's command for arm O, copied from the
#                     module that builds it (tools/slip_eval.py run_episode,
#                     with tools/gen_scene_eval.py's ARM_O: the flags as its
#                     `cmd` list spells them, the --slip-fixes value and
#                     arm_args computed by its own functions, nothing typed
#                     here), then the string wave 2's declaration states for
#                     the arm (its P4_O_ARGS, read by text), then
#                     --log-level normal, the one departure (R_PHASE0 3.3:
#                     the recorder needs the entry's plain exit).  SPEC D2.
#   <rp entry>_look   a tabletop D entry (kind boxels) as `run boxels
#                     -Headless -Look boxel -Eye arm` starts it (PLAN 5.8's
#                     tabletop start in R; run.ps1:129 and 138 add ` --look
#                     boxel` and ` --eye arm` after the launcher's command):
#                     those four words before the recorder's own additions.
#                     Without --no-gui (-Headless's) and those additions it is
#                     run.ps1's `run boxels -Look boxel -Eye arm` (SPEC D18
#                     (1)).  run.ps1 has no switch for --interior-regions, so
#                     this start has none.
#   <entry>_m7off     the entry's --m7 off twin (SPEC D3): `--m7 off` after
#                     the command the entry reproduces (for F and R after
#                     the declared string, as tracks/evalfinal/m7/checks/
#                     episodes.sh spells it), before the recorder's own
#                     --log-level normal (and --no-telemetry).  An entry
#                     without the suffix passes no --m7: the trunk's default.
#
# The seed rule (which seeds are recorded) is SPEC D1's, not this tool's: an
# f or r entry exists for every seed whose generated scene is in GEN_DIR.

SLIP_EVAL = REPO / 'tools' / 'slip_eval.py'
GEN_SCENE_EVAL = REPO / 'tools' / 'gen_scene_eval.py'
DECLARATION = (REPO / 'archive' / 'tampura_bridge_plan_2026-10-25' / 'tracks' / 'evalfinal' / 'wave2'
               / 'DECLARATION.md')
CONFIG_ARMS = {'f': 'F', 'r': 'R'}          # entry prefix: the arm's letter in the declaration
TWIN_SUFFIX = '_m7off'
LOOK_SUFFIX = '_look'
LOOK_ARGV = ['--look', 'boxel', '--eye', 'arm']    # run.ps1:129 ($Look boxel) and :138 (-Eye arm)
HEADLESS_WORD = '--no-gui'      # run.ps1:214, what -Headless adds to run boxels (every boxels D entry)
_CONFIG_ENTRY = re.compile(r'(?P<cfg>[fr])(?P<seed>[1-9][0-9]*)$')
# The recorder's own additions at the end of every entry's argv (the
# departures from the command an entry reproduces); a twin's --m7 off goes
# before them.
DEPARTURE_FLAG = '--log-level'


class EntryError(ValueError):
    """An episode name the tool cannot resolve, or a source it cannot read
    exactly as this tool reads it (the tool fails, it never picks)."""


def rel(path):
    """`path` relative to the checkout, with forward slashes (a path outside
    the checkout as it is)."""
    try:
        return Path(path).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path)


def git_blob_sha1(data):
    """The git blob hash of a text file's bytes as git stores them: CRLF
    read as LF (the checkout's core.autocrlf turns LF into CRLF in the
    working tree), so it equals `git rev-parse <commit>:<path>`."""
    data = bytes(data).replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def declared_string(arm, path=DECLARATION):
    """The flag string the declaration states for `arm` (F or R): the value
    inside P4_O_ARGS='...' on the one line that starts the arm ("- F, ..."),
    which must also run the harness's arm O (P4_ARMS=O).  Exactly one such
    line and exactly one value on it, or EntryError.  Returns the value with
    the file, its git blob hash, the line number and the line."""
    path = Path(path)
    raw = path.read_bytes()
    lines = raw.decode('utf-8').replace('\r\n', '\n').split('\n')
    starts = [(i + 1, ln) for i, ln in enumerate(lines) if ln.startswith(f'- {arm}, ')]
    if len(starts) != 1:
        raise EntryError(f'{path}: {len(starts)} lines start the {arm} arm ("- {arm}, "), not one')
    lineno, line = starts[0]
    values = re.findall(r"P4_O_ARGS='([^']*)'", line)
    if len(values) != 1:
        raise EntryError(f"{path}:{lineno}: {len(values)} values P4_O_ARGS='...' on the {arm} arm's "
                         f"line, not one")
    arms = re.findall(r'P4_ARMS=(\w+)', line)
    if arms != ['O']:
        raise EntryError(f'{path}:{lineno}: the {arm} arm runs P4_ARMS={arms}, not the harness\'s arm O')
    return {'arm': arm, 'value': values[0], 'file': rel(path), 'git_blob_sha1': git_blob_sha1(raw),
            'line': lineno, 'text': line}


def _module_defs(path, names):
    """The named top-level functions and assignments of a module's source,
    executed in a namespace of their own (the module is not imported, so its
    imports and its sys.path edits do not run here).  EntryError when a
    name is not defined there at top level."""
    path = Path(path)
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    body, found = [], set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            body.append(node)
            found.add(node.name)
        elif isinstance(node, ast.Assign) and any(getattr(t, 'id', None) in names for t in node.targets):
            body.append(node)
            found.update(t.id for t in node.targets if getattr(t, 'id', None) in names)
    missing = sorted(set(names) - found)
    if missing:
        raise EntryError(f'{path}: no top-level {missing}')
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), ns)
    return ns, tree


def _harness_template(tree, path):
    """The driver's argv of tools/slip_eval.py run_episode: the `cmd = [...]`
    list after the interpreter and the driver's path, with str(seed),
    save_dir and arm_fixes(arm) as <SEED>, <SAVE> and <FIXES>, followed by
    `cmd += arm_args(arm) + list(extra_args)`.  Any other shape: EntryError
    (the harness changed; read it again)."""
    fn = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_episode'), None)
    if fn is None:
        raise EntryError(f'{path}: no run_episode')
    stmts = list(fn.body)
    cmd_i = next((i for i, s in enumerate(stmts) if isinstance(s, ast.Assign)
                  and [getattr(t, 'id', None) for t in s.targets] == ['cmd']), None)
    if cmd_i is None or not isinstance(stmts[cmd_i].value, ast.List):
        raise EntryError(f'{path}: run_episode has no `cmd = [...]`')
    elts = stmts[cmd_i].value.elts
    driver = elts[1] if len(elts) > 1 else None
    parts = ([a.value for a in driver.args if isinstance(a, ast.Constant)]
             if isinstance(driver, ast.Call) else [])
    if not (isinstance(elts[0], ast.Attribute) and parts == [DRIVER.parent.name, DRIVER.name]):
        raise EntryError(f'{path}:{stmts[cmd_i].lineno}: the command does not start the bridge driver '
                         f'{rel(DRIVER)} as this tool reads it')
    out = []
    for e in elts[2:]:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            out.append(e.value)
        elif (isinstance(e, ast.Call) and getattr(e.func, 'id', None) == 'str' and len(e.args) == 1
              and getattr(e.args[0], 'id', None) == 'seed'):
            out.append('<SEED>')
        elif isinstance(e, ast.Name) and e.id == 'save_dir':
            out.append('<SAVE>')
        elif (isinstance(e, ast.Call) and getattr(e.func, 'id', None) == 'arm_fixes' and len(e.args) == 1
              and getattr(e.args[0], 'id', None) == 'arm'):
            out.append('<FIXES>')
        else:
            raise EntryError(f'{path}:{e.lineno}: an element of the harness\'s command this tool does not '
                             f'read: {ast.unparse(e)}')
    nxt = stmts[cmd_i + 1] if cmd_i + 1 < len(stmts) else None
    if not (isinstance(nxt, ast.AugAssign) and getattr(nxt.target, 'id', None) == 'cmd'
            and ast.unparse(nxt.value) == 'arm_args(arm) + list(extra_args)'):
        raise EntryError(f'{path}: run_episode does not continue with `cmd += arm_args(arm) + '
                         f'list(extra_args)`')
    if [x for x in ('<SEED>', '<SAVE>', '<FIXES>') if out.count(x) != 1]:
        raise EntryError(f'{path}: the harness\'s command holds the seed, the save folder or the fixes '
                         f'other than once: {out}')
    return out, stmts[cmd_i].lineno


def harness_arm_o(slip_eval=SLIP_EVAL, gen_scene_eval=GEN_SCENE_EVAL):
    """The harness's command for arm O as its modules build it: ARM_O of
    tools/gen_scene_eval.py, its --slip-fixes value and arm_args computed by
    tools/slip_eval.py's own functions, and run_episode's argv template."""
    ns_gen, _ = _module_defs(gen_scene_eval, ('ARM_O',))
    ns_se, tree = _module_defs(slip_eval, ('ARM_FLAGS', 'split_arm', 'arm_fixes', 'arm_args'))
    arm = ns_gen['ARM_O']
    template, line = _harness_template(tree, slip_eval)
    return {'arm_o': arm, 'slip_fixes': ns_se['arm_fixes'](arm), 'arm_args': list(ns_se['arm_args'](arm)),
            'template': template, 'command_line': line,
            'files': {'harness': rel(slip_eval), 'arm_o': rel(gen_scene_eval)}}


def _config_entry(cfg, seed):
    scene = GEN_DIR / f'find_dice_gen_s{seed}.json'
    if not scene.exists():
        raise EntryError(f'{cfg}{seed}: no generated scene {rel(scene)}')
    h = harness_arm_o()
    d = declared_string(CONFIG_ARMS[cfg])
    sub = {'<SEED>': str(seed), '<FIXES>': h['slip_fixes']}
    argv = ([sub.get(x, x) for x in h['template']] + h['arm_args'] + shlex.split(d['value'])
            + [DEPARTURE_FLAG, 'normal'])
    return {'kind': 'bridge', 'gen': True, 'config': CONFIG_ARMS[cfg], 'seed': seed, 'argv': argv,
            'harness': h, 'declared': d}


def entry(name):
    """The spec of episode `name`: a D entry of EPISODES, f<seed> or
    r<seed> (configurations F and R on a generated scene), or any of these
    with TWIN_SUFFIX (its --m7 off twin).  A fresh dict on every call, with
    'kind', 'gen', 'config', 'argv', 'm7' ('default' or 'off') and, for a
    twin, 'twin_of'.  EntryError for any other name."""
    if not isinstance(name, str) or not name:
        raise EntryError(f'no episode {name!r}')
    twin = name.endswith(TWIN_SUFFIX)
    base = name[:-len(TWIN_SUFFIX)] if twin else name
    tabletop = base[:-len(LOOK_SUFFIX)] if base.endswith(LOOK_SUFFIX) else None
    if base in EPISODES:
        spec = dict(EPISODES[base], argv=list(EPISODES[base]['argv']), config='D')
    elif tabletop in EPISODES and EPISODES[tabletop]['kind'] == 'boxels':
        argv = list(EPISODES[tabletop]['argv'])
        i = argv.index(DEPARTURE_FLAG)
        spec = dict(EPISODES[tabletop], argv=argv[:i] + LOOK_ARGV + argv[i:], config='R',
                    tabletop_of=tabletop)
    else:
        m = _CONFIG_ENTRY.match(base)
        if m is None:
            raise EntryError(f'no episode {name!r}: the names are those of EPISODES ({", ".join(sorted(EPISODES))}), '
                             f'f<seed> and r<seed> for a generated scene, a boxels entry with {LOOK_SUFFIX}, '
                             f'each also with {TWIN_SUFFIX}')
        spec = _config_entry(m['cfg'], int(m['seed']))
    spec['m7'] = 'default'
    if twin:
        argv = spec['argv']
        if '--m7' in argv:
            raise EntryError(f'{base} passes --m7 already; it has no twin')
        i = argv.index(DEPARTURE_FLAG)
        spec['argv'] = argv[:i] + ['--m7', 'off'] + argv[i:]
        spec['m7'] = 'off'
        spec['twin_of'] = base
    spec['name'] = name
    return spec


def entry_name(name):
    """argparse type of --episode: a name entry() resolves."""
    try:
        entry(name)
    except EntryError as ex:
        raise argparse.ArgumentTypeError(str(ex)) from None
    return name


def _env_changes(spec):
    """(variables episode_env sets, variables it removes) for an entry."""
    unset = ['FORCE_COLOR', 'NO_COLOR', 'SB_CONSOLE_ASCII', 'SB_AUDIO', 'SB_VOICE', 'PYTHONSTARTUP',
             'PYTHONINSPECT', 'BOXEL_EYE_IMAGES', 'BRIDGE_SCENE_MANIFEST', 'PYTHONPATH']
    env = {'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1', 'COLUMNS': '80', 'LINES': '24',
           'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TERM': 'dumb', 'MPLBACKEND': 'Agg',
           'PYTHONIOENCODING': 'utf-8'}
    if spec['kind'] == 'bridge':
        # run.ps1:149, the pddlstream_lib entry included as it builds it.
        env['PYTHONPATH'] = f'{REPO}:{REPO}/pddlstream_lib:{TW}/tampura:{TW_ENVS}'
        if spec.get('gen'):
            env['BRIDGE_SCENE_MANIFEST'] = str(GEN_DIR / 'manifest.json')
    return env, unset


def describe_entry(name):
    """What the recorder starts for `name`, without starting it (SPEC D2:
    printed into RUNS.md before the first recording counts)."""
    spec = entry(name)
    env, unset = _env_changes(spec)
    boxels = spec['kind'] == 'boxels'
    seed = None if boxels else spec['argv'][spec['argv'].index('--global-seed') + 1]
    d = {'episode': name, 'configuration': spec['config'], 'kind': spec['kind'],
         'command': ['<python>', rel(TFP if boxels else DRIVER)] + spec['argv'],
         'cwd': ('<RUN>/work' if boxels else
                 '<RUN>/gen: tampura_environments/find_dice/problems/ holding only the scene '
                 f'{rel(GEN_DIR)}/find_dice_gen_s{seed}.json, env_configs linked to {TW_ENVS}/env_configs'
                 if spec.get('gen') else TW_ENVS),
         'save_dir': None if boxels else '<SAVE> is <RUN>/save',
         'environment': {'set': env, 'removed': unset},
         'm7': ('--m7 off (the twin of ' + spec['twin_of'] + ')' if spec['m7'] == 'off'
                else 'no --m7: the trunk\'s default (on)'),
         'departures': [x for x in spec['argv'][spec['argv'].index(DEPARTURE_FLAG):]],
         'child': ['<python>', rel(HERE), '--child', '--mode', '<mode>', '--rec', '<RUN>/rec', '--script',
                   rel(TFP if boxels else DRIVER), '--rng', '<rng>', '--', '<argv>']}
    if 'harness' in spec:
        h, dec = spec['harness'], spec['declared']
        d['sources'] = {
            'harness': f"{h['files']['harness']} run_episode (its cmd list at line {h['command_line']}): "
                       f"{h['template']} + arm_args",
            'arm_o': f"{h['files']['arm_o']} ARM_O = {h['arm_o']!r}: --slip-fixes {h['slip_fixes']}, "
                     f"arm_args {h['arm_args']}",
            'declared': {k: dec[k] for k in ('file', 'git_blob_sha1', 'line', 'text', 'value')}}
    d['notes'] = entry_notes(name)[1:]
    return d


def entry_notes(name):
    """The NOTES lines that say what entry `name` runs.  The first line of a
    D entry is the one the episode pins wrote before gate 7."""
    spec = entry(name)
    if spec['config'] == 'D':
        lines = [f'episode {name}: {spec["kind"]}, argv {spec["argv"]}']
    elif 'tabletop_of' in spec:
        argv = spec['argv']
        i = argv.index(DEPARTURE_FLAG)
        words = [x for x in argv[:i] if x == HEADLESS_WORD] + argv[i:]     # -Headless's, the departures
        lines = [f'episode {name}: configuration R on the tabletop, {spec["kind"]}, argv {spec["argv"]}',
                 f'the tabletop start of PLAN 5.8 (SPEC D18 (1)): {spec["tabletop_of"]} as run boxels -Headless '
                 f'-Look boxel -Eye arm starts it (run.ps1 adds --look boxel and --eye arm after the launcher\'s '
                 f'command); apart from the recorder\'s own words {" ".join(words)} ({words[0]} is -Headless\'s, '
                 f'as in every D entry), its argv is what run boxels -Look boxel -Eye arm builds for the seed, '
                 f'the line pin 32 holds for seed 0; no --interior-regions (run.ps1 has no switch for it)']
    else:
        h, dec = spec['harness'], spec['declared']
        lines = [f'episode {name}: configuration {spec["config"]}, bridge on the generated scene of seed '
                 f'{spec["seed"]}, argv {spec["argv"]}',
                 f'argv built by the tool, nothing typed (SPEC D2): the harness\'s command for arm O '
                 f'({h["files"]["harness"]} run_episode; ARM_O {h["arm_o"]!r} from {h["files"]["arm_o"]}: '
                 f'--slip-fixes {h["slip_fixes"]}, arm_args {h["arm_args"]}), then the string the declaration '
                 f'states for arm {spec["config"]} unchanged ({dec["value"]!r}: {dec["file"]} line '
                 f'{dec["line"]}, git blob {dec["git_blob_sha1"]}), then --log-level normal, the one '
                 f'departure (R_PHASE0 3.3)',
                 'the harness sets BOXEL_EYE_IMAGES=0, the recorder leaves it unset (no effect while '
                 'world_eye.SAVE_IMAGES is False); wave 2 ran with P4_SHOTS=none, so neither side passes '
                 '--save-screenshots']
    if spec['m7'] == 'off':
        lines.append(f'm7: the --m7 off twin of {spec["twin_of"]} (SPEC D3), --m7 off after the command it '
                     f'reproduces'
                     + (': the path of the paper\'s kept F rows (wave 2 ran before M7 existed)'
                        if spec['config'] == 'F' else ''))
    elif spec['config'] != 'D':
        # The twin exists only if D3's rule asks for it when the tape is
        # stored (twin_rule, STORED.json's twin), so the line says "if".
        lines.append('m7: no --m7, the trunk\'s default (on); its --m7 off twin, if D3\'s rule asks for one '
                     f'when the tape is stored (STORED.json twin), is {name}{TWIN_SUFFIX} (SPEC D3)')
    return lines


# ---------------------------------------------------------------------------
# Small helpers shared with tests/readable/replay_stub.py
# ---------------------------------------------------------------------------

_ADDR = re.compile(r' at 0x[0-9a-fA-F]+')


def atom_text(x):
    """One fact argument as stable text: names stay names, a stream object
    is Type:name, numbers by repr, anything else by repr with addresses
    masked."""
    if isinstance(x, str):
        return x
    if isinstance(x, (bool, int, float)):
        return repr(x)
    if isinstance(x, (tuple, list)):
        return '(' + ' '.join(atom_text(v) for v in x) + ')'
    name = getattr(x, 'name', None)
    if isinstance(name, str) and name:
        return f'{type(x).__name__}:{name}'
    if hasattr(x, 'tolist'):
        return repr(x.tolist())
    return _ADDR.sub(' at 0x?', repr(x))


def problem_facts(problem):
    """(init facts as text in list order, goal as text) of a PDDLProblem."""
    init = getattr(problem, 'init', None)
    goal = getattr(problem, 'goal', None)
    return ([atom_text(f) for f in (init or [])], atom_text(goal))


def rng_digest():
    """sha256 of the global random and np.random states."""
    import random
    import numpy as np
    n = np.random.get_state()
    h = hashlib.sha256(repr(random.getstate()).encode())
    h.update(repr((n[0], n[1].tolist(), n[2], n[3], n[4])).encode())
    return h.hexdigest()


def rng_states():
    import random
    import numpy as np
    return pickle.dumps((random.getstate(), np.random.get_state()))


def set_rng_states(blob):
    import random
    import numpy as np
    py, nps = pickle.loads(blob)
    random.setstate(py)
    np.random.set_state(nps)


def planner_on_stack(depth=8):
    """The PDDLStreamPlanner whose plan() frame is up the stack (the caller
    of solve, or of the gate wrapper around it), or None."""
    f = sys._getframe(1)
    for _ in range(depth):
        if f is None:
            return None
        if f.f_code.co_name == 'plan':
            me = f.f_locals.get('self')
            if me is not None and hasattr(me, 'streams'):
                return me
        f = f.f_back
    return None


def stream_ints(planner):
    """The int attributes of planner.streams (its name counters
    _config_counter, _traj_counter, _grasp_counter and counts such as
    view_kin_skips), sorted by name."""
    s = getattr(planner, 'streams', None)
    if s is None:
        return None
    return {k: v for k, v in sorted(vars(s).items()) if type(v) is int}


def tee_chunks():
    """The chunk list of plan()'s _StdoutTee if sys.stdout is one, else None."""
    s = sys.stdout
    if type(s).__name__ == '_StdoutTee' and isinstance(s.__dict__.get('chunks'), list):
        return s.__dict__['chunks']
    return None


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=True,
                                     default=_default) + '\n', encoding='utf-8', newline='\n')


def _default(o):
    if hasattr(o, 'tolist'):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(_default_key(v) for v in o)
    if isinstance(o, Path):
        return str(o)
    return _ADDR.sub(' at 0x?', repr(o))


def _default_key(v):
    return v if isinstance(v, (str, int, float)) else repr(v)


def append_jsonl(path, row):
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=True, default=_default) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _write_bytes(path, data):
    with open(path, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _plain_kwargs(kw):
    return {k: (v if isinstance(v, (str, int, float, bool, type(None))) else _default(v))
            for k, v in sorted(kw.items())}


# ---------------------------------------------------------------------------
# The tape: what the recorder writes, what the stub reads
# ---------------------------------------------------------------------------
# pickle, not JSON: a solution holds the streams' RobotConfig, Trajectory and
# Grasp objects with numpy arrays, and the stub must hand plan() the same
# kind of objects.  A tape is only ever read back from a folder this tool
# wrote on this machine (scratch, or the stored set made on the checkpoint),
# never from outside input.

def tape_calls(tape_dir):
    p = Path(tape_dir) / 'calls.jsonl'
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]


def tape_write_call(tape_dir, k, solution, chunks, facts, goal, rng_before, kwargs,
                    raised=None, streams_before=None, streams_after=None):
    """Store call k (0-based) at the time of the call."""
    tape = Path(tape_dir)
    tape.mkdir(parents=True, exist_ok=True)
    cert = 'kept'
    try:
        blob = pickle.dumps(solution)
    except Exception as ex:          # the certificate is not read by plan()
        plan, cost = solution[0], solution[1]
        blob = pickle.dumps((plan, cost, None))
        cert = f'dropped ({type(ex).__name__}: {ex})'
    _write_bytes(tape / f'solution_{k:04d}.pkl', blob)
    _write_bytes(tape / f'rng_{k:04d}.pkl', rng_states())
    write_json(tape / f'text_{k:04d}.json', list(chunks))
    plan = solution[0] if solution is not None else None
    append_jsonl(tape / 'calls.jsonl', {
        'k': k, 'plan_len': (None if plan is None else len(plan)),
        'cost': repr(solution[1]) if solution is not None else None,
        'certificate': cert, 'n_chunks': len(chunks),
        'text_sha256': hashlib.sha256(''.join(chunks).encode('utf-8')).hexdigest(),
        'rng_before': rng_before, 'rng_after': rng_digest(), 'raised': raised,
        'stream_ints_before': streams_before, 'stream_ints_after': streams_after,
        'kwargs': _plain_kwargs(kwargs), 'goal': goal,
        'facts_sha256': hashlib.sha256('\n'.join(facts).encode('utf-8')).hexdigest(),
        'facts': facts})


def write_synthetic_tape(tape_dir, calls):
    """A tape made by hand: calls = [(solution, chunks), ...].  No facts and
    no RNG states of a live search exist, so the stub keeps the RNG as it is
    for these calls (rng_after is None)."""
    tape = Path(tape_dir)
    if tape.exists():
        shutil.rmtree(tape)
    tape.mkdir(parents=True)
    for k, (solution, chunks) in enumerate(calls):
        _write_bytes(tape / f'solution_{k:04d}.pkl', pickle.dumps(solution))
        write_json(tape / f'text_{k:04d}.json', list(chunks))
        append_jsonl(tape / 'calls.jsonl', {
            'k': k, 'synthetic': True, 'plan_len': None if solution[0] is None else len(solution[0]),
            'cost': repr(solution[1]), 'n_chunks': len(chunks),
            'text_sha256': hashlib.sha256(''.join(chunks).encode('utf-8')).hexdigest(),
            'rng_before': None, 'rng_after': None, 'facts': None, 'goal': None})


# ---------------------------------------------------------------------------
# The child: patches inside its own process, then runs the entry as __main__
# ---------------------------------------------------------------------------

class StopAtPlan(BaseException):
    """First-plan mode: the run stops at the first plan() call."""


class _PatchOnLoad(importlib.abc.MetaPathFinder):
    """Call each fn(module), in the order given, right after `name` has been
    executed by its normal import, wherever and whenever the pipeline
    imports it."""

    def __init__(self, name, fn):
        self.name, self.fns = name, [fn]

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.name:
            return None
        sys.meta_path.remove(self)
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        loader, fns = spec.loader, list(self.fns)
        orig_exec = loader.exec_module

        def exec_module(module):
            orig_exec(module)
            for fn in fns:
                fn(module)
        loader.exec_module = exec_module
        return spec


def patch_on_load(name, fn):
    """Register fn for module `name` (_PatchOnLoad).  A second fn for a name
    joins the finder already waiting for it: a second finder would never
    see the import, since the first one answers it."""
    for finder in sys.meta_path:
        if isinstance(finder, _PatchOnLoad) and finder.name == name:
            finder.fns.append(fn)
            return
    sys.meta_path.insert(0, _PatchOnLoad(name, fn))


# SPEC D5: what a pin may set in the child, `--set NAME=VALUE` with NAME
# `module.ATTRIBUTE` from this closed list and VALUE read by float() and
# nothing else.  Applied right after the module is executed; the applied
# pairs go to rec/SET.json and, for a recording, to the tape's META.json,
# from which a replay takes them.
SET_NAMES = ('execution.M7_SUSPEND_S',)


class SetError(ValueError):
    """A --set the recorder refuses (SPEC D5)."""


def parse_set(text):
    """'NAME=VALUE' -> (NAME, float(VALUE))."""
    name, sep, value = str(text).partition('=')
    if not sep or name not in SET_NAMES:
        raise SetError(f'--set {text!r}: NAME=VALUE with NAME one of {", ".join(SET_NAMES)}')
    try:
        return name, float(value)
    except ValueError:
        raise SetError(f'--set {text!r}: the value is read by float(), which refuses {value!r}') from None


def _set_arg(text):
    try:
        return parse_set(text)
    except SetError as ex:
        raise argparse.ArgumentTypeError(str(ex)) from None


def _install_sets(sets, rec_dir):
    """In the child: each NAME=VALUE set on its module right after the
    module is executed, the applied pairs written to rec/SET.json.  A name
    the module does not hold is an error (a set that sets nothing)."""
    applied = {}
    by_module = {}
    for name, value in sets.items():
        module, attr = name.rsplit('.', 1)
        by_module.setdefault(module, []).append((name, attr, value))

    def apply(mod, items):
        for name, attr, value in items:
            if not hasattr(mod, attr):
                raise SetError(f'--set {name}: module {mod.__name__} has no attribute {attr}')
            setattr(mod, attr, value)
            applied[name] = getattr(mod, attr)
        write_json(Path(rec_dir) / 'SET.json', applied)
    for module, items in by_module.items():
        patch_on_load(module, lambda mod, items=items: apply(mod, items))


def tape_meta(tape_dir):
    """The tape's META.json ({"set": {...}, ...}), {} for a tape without one."""
    p = Path(tape_dir) / 'META.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


class _RedirectModule(importlib.abc.MetaPathFinder):
    """Import `name` from another file (the planted copy of a module)."""

    def __init__(self, name, path):
        self.name, self.path = name, path

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.name:
            return None
        return importlib.util.spec_from_file_location(fullname, self.path)


def _load_exec_stubs():
    spec = importlib.util.spec_from_file_location('readable_executor_stubs', str(EXEC_STUBS_FILE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['readable_executor_stubs'] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_stub():
    spec = importlib.util.spec_from_file_location('readable_replay_stub', str(STUB_FILE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['readable_replay_stub'] = mod
    spec.loader.exec_module(mod)
    return mod


def make_recorder(orig_solve, tape_dir):
    """The record-mode wrapper of pddlstream_planner.solve."""
    count = {'k': 0}

    def solve(problem, *args, **kwargs):
        k = count['k']
        count['k'] += 1
        facts, goal = problem_facts(problem)
        before = rng_digest()
        planner = planner_on_stack()
        s_before = stream_ints(planner)
        chunks = tee_chunks()
        n0 = len(chunks) if chunks is not None else 0
        try:
            solution = orig_solve(problem, *args, **kwargs)
        except BaseException as ex:
            added = list(chunks[n0:]) if chunks is not None else []
            tape_write_call(tape_dir, k, (None, float('inf'), None), added, facts, goal, before,
                            kwargs, raised=f'{type(ex).__name__}: {ex}',
                            streams_before=s_before, streams_after=stream_ints(planner))
            raise
        added = list(chunks[n0:]) if chunks is not None else []
        tape_write_call(tape_dir, k, solution, added, facts, goal, before, kwargs,
                        streams_before=s_before, streams_after=stream_ints(planner))
        return solution
    solve.__wrapped__ = orig_solve
    return solve


def _plain_value(v, depth=0):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if depth > 4:
        return type(v).__name__
    if isinstance(v, dict):
        return {str(k): _plain_value(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain_value(x, depth + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        return {'sorted_from_set': sorted(atom_text(x) for x in v)}
    if hasattr(v, 'joint_positions'):
        return {'type': type(v).__name__, 'name': getattr(v, 'name', None),
                'joint_positions': _plain_value(getattr(v, 'joint_positions'), depth + 1)}
    if hasattr(v, 'tolist'):
        return v.tolist()
    if callable(v):
        return f'<callable {getattr(v, "__qualname__", type(v).__name__)}>'
    if hasattr(v, '__dataclass_fields__'):
        return {'type': type(v).__name__,
                **{f: _plain_value(getattr(v, f, None), depth + 1) for f in v.__dataclass_fields__}}
    return {'type': type(v).__name__}


def main_frame(path=TFP, depth=12):
    """The frame of `main` of test_full_pipeline.py (path: the file that runs
    as that module) up the stack from the caller: plan()'s caller, or the
    caller of a wrapper around plan().  None when it is not there."""
    want = os.path.realpath(path)
    f = sys._getframe(1)
    for _ in range(depth):
        if f is None:
            return None
        code = f.f_code
        if code.co_name == 'main' and os.path.realpath(code.co_filename) == want:
            return f
        f = f.f_back
    return None


FOLLOW_KEY = "arm_eye.following(main's env)"
NO_MAIN_FRAME = "main's frame not found"


def module_switches(main_locals=None):
    """The module state main's stage B sets (test_full_pipeline.py 802-869),
    read at the first plan() call, with execution.M7, M7_SUSPEND_S and
    interior_regions.ENABLED as the modules hold them; and the arm camera's
    follow flag, which arm_eye.follow_arm sets on main's env, not on a
    module (arm_eye.py:184-211): main_locals are the locals of main's frame
    (None: that frame was not found, and the record says so)."""
    out = {}
    mods = sys.modules
    if 'pose_belief' in mods:
        out['pose_belief.SWITCHES'] = dict(mods['pose_belief'].SWITCHES)
    if 'robot_utils' in mods:
        ru = mods['robot_utils']
        out['robot_utils.GRIP_SQUEEZE'] = ru.GRIP_SQUEEZE
        try:
            out['robot_utils.robot_model_is_pybullet_data'] = ru.robot_model() == ru.PANDA_PYBULLET_DATA
        except Exception as ex:
            out['robot_utils.robot_model'] = f'{type(ex).__name__}'
    if 'world_eye' in mods:
        we = mods['world_eye']
        out['world_eye.SAVE_IMAGES'] = we.SAVE_IMAGES
        out['world_eye._ACTIVE'] = type(we._ACTIVE).__name__ if we._ACTIVE is not None else None
    if 'slip_fixes' in mods:
        sf = mods['slip_fixes']
        out['slip_fixes.ENABLED (sorted from a frozenset)'] = sorted(sf.ENABLED)
        out['slip_fixes.KNOWN (order of registration)'] = list(sf.KNOWN)
    if 'telemetry' in mods:
        act = mods['telemetry']._ACTIVE
        out['telemetry._ACTIVE'] = (None if act is None else
                                    {'type': type(act).__name__,
                                     'counts_only': getattr(act, 'counts_only', None)})
    if 'world_counts' in mods:
        wc = mods['world_counts']
        out['world_counts._noticed'] = dict(wc._noticed)
        out['world_counts._reported'] = dict(wc._reported)
    if 'interior_regions' in mods:
        out['interior_regions.ENABLED'] = mods['interior_regions'].ENABLED
    if 'execution' in mods:
        ex = mods['execution']
        out['execution.M7'] = ex.M7
        out['execution.M7_SUSPEND_S'] = ex.M7_SUSPEND_S
    if 'arm_eye' in mods:
        out[FOLLOW_KEY] = (NO_MAIN_FRAME if main_locals is None
                           else mods['arm_eye'].following(main_locals.get('env')))
    return out


# S-b (PLAN 5.2 row 34, SPEC D15): the attributes of the planner and of its
# streams at the first plan() call.  A plain value is recorded as itself; an
# object only by its type, so look_on and look_mode show by value and
# m8_views and look_views as null or set.

NOT_PLAIN = type('NotPlain', (), {'__repr__': lambda self: 'NOT_PLAIN'})()
PLAIN_DEPTH = 8


def _set_order(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return (0, x, '')
    return (1, 0, json.dumps(x, sort_keys=True, allow_nan=True))


def plain_form(v, depth=0):
    """v as JSON if it is plain, else NOT_PLAIN.  Plain: None, bool, int,
    float, str (one of more than one line as its line count and sha256), and
    lists, tuples, sets, dicts and numpy arrays made of plain values, nested
    at most PLAIN_DEPTH deep.  A list stays a list and a dict with str keys
    a dict (in its own order); any other container names its type:
    {"tuple": [...]}, {"frozenset": [sorted]}, {"ndarray": [...], "dtype":
    ...}, {"dict": [[key, value], ...]} for other keys.  An instance of any
    other class (the pipeline's RobotConfig, a registry, a views object) is
    not plain, and neither is a container that holds one."""
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        if '\n' in v:
            return {'str_lines': len(v.splitlines()),
                    'sha256': hashlib.sha256(v.encode('utf-8')).hexdigest()}
        return v
    if depth >= PLAIN_DEPTH:
        return NOT_PLAIN
    if isinstance(v, (list, tuple, set, frozenset)):
        items = [plain_form(x, depth + 1) for x in v]
        if any(x is NOT_PLAIN for x in items):
            return NOT_PLAIN
        if isinstance(v, (set, frozenset)):
            return {type(v).__name__: sorted(items, key=_set_order)}
        return items if type(v) is list else {type(v).__name__: items}
    if isinstance(v, dict):
        keys = [plain_form(k, depth + 1) for k in v]
        values = [plain_form(x, depth + 1) for x in v.values()]
        if any(x is NOT_PLAIN for x in keys + values):
            return NOT_PLAIN
        if type(v) is dict and all(isinstance(k, str) for k in v):
            return dict(zip(v.keys(), values))
        return {type(v).__name__: [[k, x] for k, x in zip(keys, values)]}
    if hasattr(v, 'dtype') and hasattr(v, 'shape') and hasattr(v, 'tolist'):   # numpy
        form = plain_form(v.tolist(), depth + 1)
        if form is NOT_PLAIN:
            return NOT_PLAIN
        return {type(v).__name__: form, 'dtype': str(v.dtype)}
    return NOT_PLAIN


def attribute_record(obj):
    """Every attribute of obj (vars(obj), sorted by name): a plain value as
    plain_form gives it; anything else as {"object": its type}, with "len"
    for a container and "qualname" for a callable.  None for None."""
    if obj is None:
        return None
    try:
        items = sorted(vars(obj).items())
    except TypeError:
        return {'object': type(obj).__name__, 'vars': None}
    out = {}
    for name, v in items:
        form = plain_form(v)
        if form is NOT_PLAIN:
            form = {'object': type(v).__name__}
            if isinstance(v, (list, tuple, dict, set, frozenset)):
                form['len'] = len(v)
            elif callable(v):
                form['qualname'] = getattr(v, '__qualname__', None)
        out[name] = form
    return out


def first_plan_notes():
    """The NOTES lines of the first-plan record's parts added in gate 7."""
    return [
        'first_plan.json module_switches: also execution.M7, execution.M7_SUSPEND_S and '
        'interior_regions.ENABLED as the modules hold them at the first plan() call (the recorder sets '
        f'none of them), and "{FOLLOW_KEY}": arm_eye.following of the env in main\'s frame (follow_arm '
        f'marks the env, not a module; "{NO_MAIN_FRAME}" if the frame is not up the stack)',
        'first_plan.json planner_attributes and streams_attributes (R\'s S-b, PLAN 5.2 row 34): every '
        'attribute of the planner and of planner.streams at the first plan() call, by name; a plain '
        'value as itself (a multi-line string as its line count and sha256, a container other than a '
        'list or a str-keyed dict by its type), any other value as {object: its type} with len or '
        'qualname: so look_on and look_mode by value, m8_views and look_views as null or set',
        'normalised: in planner_attributes and streams_attributes every number under a key that ends '
        'in _s (wall seconds, e.g. last_m8_stats.twin_render_s) is <s>, the key kept, null kept',
        'a list compared in an order that comes from a set (R\'s rule 4 as amended, REVIEW_PHASE0 item 5): '
        'first_plan.json planner_attributes.shadow_occluder_map, each shadow\'s blockers as '
        'execution.compute_shadow_blockers leaves them, list(blocker_set), compared in that order under '
        'PYTHONHASHSEED=0; a set or frozenset value itself is written sorted by the recorder',
    ]


def make_first_plan_recorder(orig_plan, rec_dir, main_file=TFP):
    import functools
    import inspect
    sig = inspect.signature(orig_plan)

    @functools.wraps(orig_plan)
    def plan(self, *args, **kwargs):
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {k: _plain_value(v) for k, v in bound.arguments.items() if k != 'self'}
        frame = main_frame(main_file)
        rec = {'plan_kwargs': arguments,
               'plan_kwargs_passed': sorted(kwargs),
               'module_switches': module_switches(None if frame is None else frame.f_locals),
               'rng_digest': rng_digest(),
               'planner': {'type': type(self).__name__,
                           'search_options': _plain_value(getattr(self, 'search_options', None)),
                           'search_sample_ratio': getattr(self, 'search_sample_ratio', None),
                           'domain_sha256': hashlib.sha256(
                               getattr(self, 'domain_pddl', '').encode('utf-8')).hexdigest(),
                           'stream_sha256': hashlib.sha256(
                               getattr(self, 'stream_pddl', '').encode('utf-8')).hexdigest()},
               'planner_attributes': attribute_record(self),
               'streams_attributes': attribute_record(getattr(self, 'streams', None))}
        del frame
        gh = sys.modules.get('tampura_bridge.gate_hooks')
        if gh is not None and gh.installed():
            rec['gate'] = {'counts': gh.counts(), 'info': dict(gh._info), 'steps': dict(gh._steps),
                           'solve_calls': gh._solve_calls}
        write_json(Path(rec_dir) / 'first_plan.json', rec)
        raise StopAtPlan('first plan() call reached')
    return plan


def _install_main_params_hook(rec_dir, tfp_path):
    """main's parameters at entry (sys.setprofile; removed at the call)."""
    target = os.path.realpath(tfp_path)
    seen = {}

    def prof(frame, event, arg):
        if event != 'call' or frame.f_code.co_name != 'main':
            return
        code = frame.f_code
        if code not in seen:
            seen[code] = os.path.realpath(code.co_filename) == target
        if not seen[code]:
            return
        sys.setprofile(None)
        names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
        params = {n: _plain_value(frame.f_locals.get(n)) for n in names}
        write_json(Path(rec_dir) / 'main_params.json', {'order': list(names), 'values': params})
    sys.setprofile(prof)


class _LineTrace:
    """Lines of one file that ran, per function (co_name, first line)."""

    def __init__(self, path):
        self.target = os.path.realpath(path)
        self.known = {}
        self.reached = {}

    def _glob(self, frame, event, arg):
        code = frame.f_code
        hit = self.known.get(code)
        if hit is None:
            hit = self.known[code] = (os.path.realpath(code.co_filename) == self.target)
        if not hit:
            return None
        lines = self.reached.setdefault(f'{code.co_name}:{code.co_firstlineno}', set())

        def local(frame, event, arg):
            if event == 'line':
                lines.add(frame.f_lineno)
            return local
        return local

    def start(self):
        sys.settrace(self._glob)

    def dump(self, path):
        sys.settrace(None)
        write_json(path, {k: sorted(v) for k, v in sorted(self.reached.items())})


def _absolute_log_dir(mod):
    """Boxels runs only: RunLogger's relative log_dir ('logs', the __main__
    block's default) resolved against the cwd.  The export joins a relative
    run directory to the code directory (pddlstream_planner.py:434-439), so
    a run started outside the checkout would stop there; a real `run boxels`
    starts in the checkout (run.ps1:171), where both resolve alike.  Only the
    path's spelling changes (it is masked in every output)."""
    import functools
    import inspect
    orig = mod.RunLogger.__init__
    sig = inspect.signature(orig)

    @functools.wraps(orig)
    def __init__(self, *args, **kwargs):
        b = sig.bind(self, *args, **kwargs)
        b.apply_defaults()
        b.arguments['log_dir'] = os.path.abspath(str(b.arguments['log_dir']))
        return orig(*b.args, **b.kwargs)
    mod.RunLogger.__init__ = __init__


# C-01 (test_full_pipeline.py:3681-3699): an exception out of main() is shown
# through sys.excepthook after the clean-up, then the entry exits 70; the
# eval runner files that ending as crash_exit70 (SPEC D7, trap 11).  A bridge
# episode does not pass C-01: the bridge calls main() inside its execute_fn,
# whose except Exception keeps the type and message as the episode's error
# and raises nothing (tampura_bridge/policy.py:291-301 and 315-319); the
# driver goes on, its outcome is crashed (tools/bridge_gates.py
# episode_outcome) and its main returns 1, so the child ends with
# SystemExit(1) and no hook is called (BRIDGE_CRASH_NOTE).
CRASH_EXIT_CODE = 70
CRASH_HOW = 'crash_exit70'


class CrashHook:
    """The child's sys.excepthook: writes the traceback to rec/CRASH.txt,
    then calls the hook it replaced, so stderr shows what it shows without
    the recorder.  `calls` counts the calls; a failed write never reaches
    the pipeline's own handler."""

    def __init__(self, path):
        self.path, self.calls, self.prev = Path(path), 0, None

    def install(self):
        self.prev = sys.excepthook
        sys.excepthook = self

    def __call__(self, etype, value, tb):
        self.calls += 1
        try:
            self.path.write_text(''.join(traceback.format_exception(etype, value, tb)), encoding='utf-8')
        except Exception as ex:
            print(f'[record_episode] CRASH.txt not written: {type(ex).__name__}: {ex}', file=sys.stderr)
        self.prev(etype, value, tb)


def child_main(a):
    rec = Path(a.rec)
    rec.mkdir(parents=True, exist_ok=True)
    script = os.path.abspath(a.script)
    trace = None
    is_tfp = os.path.realpath(script) == os.path.realpath(TFP)
    if is_tfp:
        patch_on_load('run_logger', _absolute_log_dir)
    if a.set:
        _install_sets(dict(a.set), rec)          # SPEC D5, before the stubs of the same module
    if a.stubs:
        _load_exec_stubs().install(a.stubs, rec, patch_on_load)
    if a.tfp_copy:
        # Planted-change checks (PLAN 24.3 (e)) only: the copy is run as the
        # entry (boxels) or imported as test_full_pipeline (bridge), with
        # the checkout on sys.path and the pddlstream path the checkout's
        # file computes (test_full_pipeline.py:52-55).
        copy = os.path.abspath(a.tfp_copy)
        os.environ.setdefault('PDDLSTREAM_PATH', os.path.join(
            os.path.dirname(os.path.abspath(TFP)), '..', 'pddlstream_lib'))
        sys.meta_path.insert(0, _RedirectModule('test_full_pipeline', copy))
        if is_tfp:
            script = copy
    if a.mode in ('record', 'replay'):
        if a.mode == 'record':
            def patch(mod):
                mod.solve = make_recorder(mod.solve, a.tape)
        else:
            stub = _load_stub()

            def patch(mod):
                stub.install(mod, a.tape, rec, rng=a.rng)
        patch_on_load('pddlstream_planner', patch)
    elif a.mode == 'first-plan':
        main_file = os.path.abspath(a.tfp_copy) if a.tfp_copy else TFP

        def patch(mod):
            mod.PDDLStreamPlanner.plan = make_first_plan_recorder(mod.PDDLStreamPlanner.plan, rec,
                                                                  main_file=main_file)
        patch_on_load('pddlstream_planner', patch)
        _install_main_params_hook(rec, TFP)
    else:
        raise SystemExit(f'unknown mode {a.mode}')
    if a.trace_main:
        trace = _LineTrace(TFP)
    sys.argv = [script] + list(a.argv)
    sys.path[0] = os.path.dirname(os.path.abspath(a.script))
    crash_hook = CrashHook(rec / 'CRASH.txt')
    crash_hook.install()
    code, how = 0, 'returned'
    try:
        if trace is not None:
            trace.start()
        import runpy
        runpy.run_path(script, run_name='__main__')
    except SystemExit as ex:
        how = 'system_exit'
        code = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
        if not isinstance(ex.code, (int, type(None))):
            how = f'system_exit: {ex.code}'
        elif code == CRASH_EXIT_CODE and crash_hook.calls:
            how = CRASH_HOW
    except StopAtPlan:
        how, code = 'stopped at the first plan() call', 0
    except BaseException as ex:
        name = type(ex).__name__
        how = f'raised {name}: {ex}'
        code = 5 if name == 'ReplayTapeError' else 1
        (rec / 'CRASH.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if trace is not None:
            trace.dump(rec / 'main_lines.json')
    write_json(rec / 'EXIT.json', {'code': code, 'how': how})
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


# ---------------------------------------------------------------------------
# The parent: one episode in a child, then RESULT.json and norm/
# ---------------------------------------------------------------------------

def episode_env(spec, extra=None):
    env = dict(os.environ)
    fixed, unset = _env_changes(spec)
    for k in unset:
        env.pop(k, None)
    env.update(fixed)
    env.update(extra or {})
    return env


def prepare(name, run_dir):
    """(spec, script, argv, cwd) of episode `name` in run_dir (made fresh)."""
    spec = entry(name)
    run_dir = Path(run_dir)
    if spec['kind'] == 'boxels':
        work = run_dir / 'work'
        work.mkdir(parents=True, exist_ok=True)
        return spec, TFP, list(spec['argv']), work
    if not os.path.isdir(TW_ENVS):
        raise RuntimeError(f'needs the bridge venv: TAMPURA tree {TW_ENVS} absent')
    save = run_dir / 'save'
    argv = [str(save) if x == '<SAVE>' else x for x in spec['argv']]
    if spec.get('gen'):
        seed = argv[argv.index('--global-seed') + 1]
        d = run_dir / 'gen'
        probs = d / 'tampura_environments' / 'find_dice' / 'problems'
        probs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(GEN_DIR / f'find_dice_gen_s{seed}.json', probs)
        link = d / 'env_configs'
        if not link.exists():
            os.symlink(TW_ENVS + '/env_configs', link)
        return spec, DRIVER, argv, d
    return spec, DRIVER, argv, Path(TW_ENVS)


def pipeline_run_dir(run_dir, spec):
    base = Path(run_dir) / ('work/logs' if spec['kind'] == 'boxels' else 'save/ours')
    runs = sorted(base.glob('run_*')) if base.is_dir() else []
    return runs[-1] if runs else None


def run_episode(name, mode, run_dir, tape=None, rng='restore', trace_main=False,
                timeout=EPISODE_TIMEOUT_S, log=print, stubs=None, tfp_copy=None, sets=None):
    """Run episode `name` in a child process; returns the RESULT dict.

    stubs: executor stubs (tests/readable/executor_stubs.py config, a dict
    or JSON text) for a scripted tape.  tfp_copy (default: the variable
    READABLE_TFP_COPY): a planted copy of test_full_pipeline.py run instead
    of the checkout's, for the planted-change checks of PLAN 24.3 (e) only;
    the copy is named in RESULT.json and INFO files only, never in a
    compared output.  sets: {NAME: VALUE} of SPEC D5, set in the child; a
    recording writes them to its tape's META.json, a replay takes them from
    there and refuses a sets that differs."""
    entry(name)                          # an unknown name fails before run_dir is touched
    sets = dict(parse_set(f'{k}={v}') for k, v in (sets or {}).items())
    if mode == 'replay' and tape is not None:
        meta_sets = tape_meta(tape).get('set') or {}
        if sets and sets != meta_sets:
            raise SetError(f'{name} replay: --set {sets} differs from the tape\'s META.json {meta_sets}')
        sets = meta_sets
    if tfp_copy is None:
        tfp_copy = os.environ.get(TFP_COPY_VAR) or None
    if isinstance(stubs, dict):
        stubs = json.dumps(stubs, sort_keys=True)
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    spec, script, argv, cwd = prepare(name, run_dir)
    rec = run_dir / 'rec'
    if mode == 'record':
        tape = run_dir / 'tape'
        tape.mkdir()
        (tape / 'calls.jsonl').touch()       # a run that never plans has an empty tape
        if sets:
            write_json(tape / 'META.json', {'set': sets})
    cmd = [sys.executable, str(HERE), '--child', '--mode', mode, '--rec', str(rec),
           '--script', str(script), '--rng', rng]
    if tape is not None:
        cmd += ['--tape', str(Path(tape).resolve())]
    if trace_main:
        cmd += ['--trace-main']
    for k, v in sets.items():
        cmd += ['--set', f'{k}={v}']
    if stubs:
        cmd += ['--stubs', stubs]
    if tfp_copy:
        cmd += ['--tfp-copy', str(Path(tfp_copy).resolve())]
    cmd += ['--'] + argv
    t0 = time.monotonic()
    status = 'ended'
    with open(run_dir / 'stdout.txt', 'wb') as out, open(run_dir / 'stderr.txt', 'wb') as err:
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=episode_env(spec), stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()                  # our own child only
            rc = proc.wait()
            status = 'timeout'
    seconds = time.monotonic() - t0
    pr = pipeline_run_dir(run_dir, spec)
    exit_info = {}
    if (rec / 'EXIT.json').exists():
        exit_info = json.loads((rec / 'EXIT.json').read_text(encoding='utf-8'))
    result = {'episode': name, 'mode': mode, 'rng': rng, 'status': status, 'rc': rc,
              'child_exit': exit_info, 'configuration': spec['config'], 'm7': spec['m7'],
              'argv': argv, 'script': str(script), 'cwd': str(cwd),
              'pipeline_run_dir': str(pr) if pr else None, 'seconds': round(seconds, 1),
              'tape': str(tape) if tape is not None else None,
              'stubs': json.loads(stubs) if stubs else None,
              'set': sets or None,
              'tfp_copy': str(tfp_copy) if tfp_copy else None}
    write_json(run_dir / 'RESULT.json', result)
    write_norm(run_dir)
    log(f'[record_episode] {name} {mode}: rc {rc}, {status}, {seconds:.0f} s, '
        f'{exit_info.get("how", "no EXIT.json")}')
    return result


# ---------------------------------------------------------------------------
# Normalisation (times, pids, addresses, paths) and comparison
# ---------------------------------------------------------------------------

TYPE_AT_ID = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)@(\d+)\b')
HEX_ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')
STAMP = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')
# Ledger fields that are times or clocks (index episode_path.md section 5):
# masked, the key kept (SPEC D6, R's ruling on the older time keys); every
# *_s field of a bridge_timing row too.
LEDGER_TIME_KEYS = {'t', 'wall'}
LEDGER_TIME_KEYS_BY_KIND = {'plan': {'plan_time_s'}}
# The process id is no time and not in that ruling: removed as before.
LEDGER_DROP_BY_KIND = {'ledger_open': {'pid'}}
# Console text that is a time (masked, the rest of the line kept).
CONSOLE_MASKS = [
    (re.compile(r'elapsed=\d+\.\d+s'), 'elapsed=<T>s'),
    (re.compile(r'(\[timing\] planner\.plan\(\) #\d+: )[\d.]+s \(cumulative [\d.]+s\)'),
     r'\1<T>s (cumulative <T>s)'),
    (re.compile(r'(Cumulative planning time : )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(Average per call\s+: )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(Per-call \(s\)\s+: )\[[^\]]*\]'), r'\1[<T>]'),
    (re.compile(r'(twin renders )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(over-region folds )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(total )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'( at 0x)[0-9a-fA-F]+'), r'\1?'),
    # G18's detail (tools/bridge_gates.py): the driver's clock stamps.
    (re.compile(r'(initialize return to rollout start )\d+\.\d+ s'), r'\1<T> s'),
    (re.compile(r'(_[a-z0-9]+ )\+\d+\.\d+ s'), r'\1+<T> s'),
]


class IdMap:
    """plan_obj ints and Type@id strings to their order of first use, keyed
    by (plan id, value) so a freed address reused by a later plan is a new
    token (index episode_path.md section 4); hex addresses likewise."""

    def __init__(self):
        self.objs, self.types, self.hexes = {}, {}, {}

    def obj(self, plan_id, value):
        if value is None:
            return None
        key = (plan_id, value)
        if key not in self.objs:
            self.objs[key] = f'obj#{len(self.objs) + 1}'
        return self.objs[key]

    def text(self, plan_id, s):
        def typ(m):
            key = (plan_id, m.group(0))
            if key not in self.types:
                self.types[key] = len(self.types) + 1
            return f'{m.group(1)}@#{self.types[key]}'

        def hx(m):
            if m.group(0) not in self.hexes:
                self.hexes[m.group(0)] = len(self.hexes) + 1
            return f'0x#{self.hexes[m.group(0)]}'
        return HEX_ADDR.sub(hx, TYPE_AT_ID.sub(typ, s))


class Masker:
    def __init__(self, pairs):
        self.pairs = sorted(((str(a), b) for a, b in pairs if a), key=lambda t: -len(t[0]))

    def __call__(self, s):
        for a, b in self.pairs:
            if a in s:
                s = s.replace(a, b)
        s = STAMP.sub('<STAMP>', s)
        for rx, rep in CONSOLE_MASKS:
            s = rx.sub(rep, s)
        return s


def _walk(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    if isinstance(obj, dict):
        return {fn(k) if isinstance(k, str) else k: _walk(v, fn) for k, v in obj.items()}
    return obj


def _read_jsonl(path):
    if not path or not Path(path).exists():
        return None
    rows = []
    for ln in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                rows.append({'unparsable_line': ln})
    return rows


SECONDS_MASK = '<s>'


def _seconds_masked(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return SECONDS_MASK
    if isinstance(v, list):
        return [_seconds_masked(x) for x in v]
    return mask_seconds(v)


def mask_seconds(obj):
    """Every number under a key that ends in _s (wall seconds, the
    pipeline's naming), also inside a list under such a key, replaced by
    '<s>': the key stays, null stays null, nothing is dropped (SPEC D6,
    PLAN 5.1)."""
    if isinstance(obj, dict):
        return {k: (_seconds_masked(v) if isinstance(k, str) and k.endswith('_s') else mask_seconds(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_seconds(v) for v in obj]
    return obj


def _ledger_time_key(kind, key):
    return (key in LEDGER_TIME_KEYS or key in LEDGER_TIME_KEYS_BY_KIND.get(kind, ())
            or (kind == 'bridge_timing' and key.endswith('_s')))


def _masked_event(e):
    """A driver clock event [name, t]: the name kept, the time masked."""
    return ([e[0]] + [_seconds_masked(x) for x in e[1:]]) if isinstance(e, list) and e else e


def norm_ledger(rows, mask):
    ids = IdMap()
    out = []
    for r in rows or []:
        kind = r.get('kind')
        r = {k: (_seconds_masked(v) if _ledger_time_key(kind, k) else v)
             for k, v in r.items() if k not in LEDGER_DROP_BY_KIND.get(kind, ())}
        if kind == 'driver_clock' and isinstance(r.get('events'), list):
            r['events'] = [_masked_event(e) for e in r['events']]
        pid = r.get('plan_id', r.get('plan'))
        if 'plan_obj' in r:
            r['plan_obj'] = ids.obj(pid, r['plan_obj'])
        r = _walk(r, lambda s: ids.text(pid, mask(s)))
        out.append(r)
    return out


# eye.jsonl's wall times (SPEC D6): masked, the key kept.  sim_t, the
# simulation's own clock, is compared.
EYE_TIME_KEYS = {'t_wall'}
EYE_EXTRA_TIME_KEYS = {'plan_time_s'}


def norm_eye(rows, mask):
    out = []
    for r in rows or []:
        r = {k: (_seconds_masked(v) if k in EYE_TIME_KEYS else v) for k, v in r.items()}
        if isinstance(r.get('extra'), dict):
            r['extra'] = {k: (_seconds_masked(v) if k in EYE_EXTRA_TIME_KEYS else v)
                          for k, v in r['extra'].items()}
        out.append(_walk(r, mask))
    return out


# timing_summary.json's M7 keys (SPEC D6, its first part, U2; written by
# run_logger.report_run_outcome, run_logger.py:711-713).  m7_suspend_s is
# the configured length, not a measurement: it stays with its value.  Each
# m7_suspensions row (run_logger.suspension_rows) keeps every key: those
# that end in _s (start_s, until_s, end_s) have a number masked and null
# kept; region, bodies and ended_by are compared as they are.
M7_LENGTH_KEY = 'm7_suspend_s'
M7_ROWS_KEY = 'm7_suspensions'


def _m7_row_masked(row):
    if not isinstance(row, dict):
        return mask_seconds(row)
    return {k: (_seconds_masked(v) if isinstance(k, str) and k.endswith('_s') else v) for k, v in row.items()}


def norm_times(obj):
    """timing_summary.json, world_counts.json and bridge_episode.json (SPEC
    D6, R's ruling on the older time keys): mask_seconds, so every number
    under a key that ends in _s, also in a list under such a key, becomes
    '<s>' and the key stays.  The three keys the normaliser dropped by name
    (total_planning_time_s, per_call_planning_time_s, counts_cost_s) end in
    _s and are among them.  The top-level M7 keys as D6 says: the length
    kept, the rows' own time keys masked."""
    if not isinstance(obj, dict):
        return mask_seconds(obj)
    out = {}
    for k, v in obj.items():
        if k == M7_LENGTH_KEY:
            out[k] = v
        elif k == M7_ROWS_KEY and isinstance(v, list):
            out[k] = [_m7_row_masked(r) for r in v]
        else:
            out.update(mask_seconds({k: v}))
    return out


# first_plan.json: the parts whose times are masked (the attribute records).
FIRST_PLAN_SECONDS_MASKED = ('planner_attributes', 'streams_attributes')


def norm_first_plan(obj):
    if not isinstance(obj, dict):
        return obj
    return {k: (mask_seconds(v) if k in FIRST_PLAN_SECONDS_MASKED else v) for k, v in obj.items()}


# R's rule 4 as amended (R_PHASE0 3.1, REVIEW_PHASE0 item 5): the lists of the
# episode pins compared in an order that comes from a set, read from the
# tag's code at gate 7 (WP-B item 9).
ORDER_NOTES = [
    'lists compared in an order that comes from a set (R\'s rule 4 as amended, REVIEW_PHASE0 item 5): '
    'facts.json, the facts of each plan call in the planner\'s order, which is the init list after '
    'random.shuffle(init) in PDDLStreamPlanner._build_init; before the shuffle that list takes the '
    'iteration order of sets of names: the blockers of each shadow (execution.compute_shadow_blockers '
    'keeps list(blocker_set), which the blocks_view_at loop over planner.shadow_occluder_map reads), '
    'the blocked (free cell, shadow) pairs (the set blocking of _compute_placement_view_blocks, read '
    'as placement_blocks) and the objects of the clear and on_table facts (the set all_obj_ids); '
    'compared in that order under PYTHONHASHSEED=0, and a red from it is real until shown to be '
    'order only',
    'ledger.json: look_reveals.named lists the reveals facts in the order of planner.last_init, that '
    'shuffled list (look boxel); run_logger._ledger_default writes a set handed to ledger_event in its '
    'iteration order, and no call site hands one. boxel_data.json: no list built from a set (the '
    'registry\'s insertion order, shadow_boxel_ids in append order). Both read from the code at gate 7',
]


# SPEC D7's two cases that keep today's record ("the NOTES say so"): a crash
# of main() in a bridge episode (see CRASH_EXIT_CODE), and an exception out
# of the entry, which child_main writes as before.
BRIDGE_CRASH_NOTE = (
    'a crash of main() in a bridge episode keeps today\'s record (SPEC D7): it does not pass the C-01 '
    'handler, since the bridge calls main() inside its execute_fn, whose except Exception '
    '(tampura_bridge/policy.py:315-319) keeps the type and message as the episode\'s error; the driver '
    'goes on to its own end, so child_exit is system_exit with code 1, no rec/CRASH.txt is written, and '
    'the error stands in result.json outcome (status crashed) and in bridge_episode.json')
RAISED_NOTE = (
    'an exception that leaves the entry keeps today\'s record too (SPEC D7): a pre-flight rejection, or '
    'an exception of the bridge driver\'s own code outside that handler; how "raised <type>: <message>", '
    'rec/CRASH.txt from its traceback')


def episode_notes():
    """The NOTES lines every episode pin writes after its entry's own
    (pin_outputs._episode_notes): what the normaliser does, the crash
    record, the lists compared in an order that comes from a set."""
    return [
        'normalised by record_episode.normalise: times masked to <s> with their keys kept, null kept '
        '(SPEC D6): ledger t and wall, plan.plan_time_s, every bridge_timing *_s and the time of each '
        'driver_clock event; eye t_wall and extra.plan_time_s; every number under a key ending in _s '
        'in timing_summary, world_counts and bridge_episode, and bridge_episode time_deltas; in '
        'timing_summary m7_suspend_s, the configured length, compared with its value, and in each '
        'm7_suspensions row start_s, until_s and end_s masked, region, bodies and ended_by compared; '
        'ledger_open.pid removed; plan_obj and Type@id mapped to their order of first use keyed by plan '
        'id; console times masked; paths and stamps masked',
        'rec/CRASH.txt (SPEC D7): the recorder\'s sys.excepthook writes it when the boxels entry shows a '
        'crash of main() (C-01, test_full_pipeline.py:3681-3699), then calls the hook it replaced; '
        f'child_exit.how is {CRASH_HOW} only for exit code {CRASH_EXIT_CODE} after that call (a '
        f'{CRASH_EXIT_CODE} without it stays system_exit); a run with rec/CRASH.txt has crash.json, its '
        'last line (type and message), compared, and INFO_crash.txt, the frames, which hold line numbers',
        BRIDGE_CRASH_NOTE,
        RAISED_NOTE,
        *ORDER_NOTES,
    ]


def crash_record(text, mask):
    """rec/CRASH.txt's compared part (SPEC D7): its last line, the
    exception's type and message.  The frames hold line numbers, so the
    whole text goes to INFO_crash.txt, which no compare reads."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return {'last_line': mask(lines[-1]) if lines else None}


def norm_console(text, mask):
    lines = []
    for ln in text.splitlines():
        ln = mask(ln)
        for rx, rep in CONSOLE_MASKS:          # also when mask is a plain function
            ln = rx.sub(rep, ln)
        lines.append(ln)
    return '\n'.join(lines) + '\n'


def norm_bridge_episode(obj, mask):
    if not isinstance(obj, dict):
        return obj
    obj = dict(obj)
    if 'time_deltas' in obj:              # the driver's wall clock per step: the list kept
        obj['time_deltas'] = _seconds_masked(obj['time_deltas'])
    key = 'driver_clock' if obj.get('driver_clock') else 'driver'
    drv = obj.get(key)
    if isinstance(drv, dict) and isinstance(drv.get('events'), list):
        obj[key] = dict(drv, events=[_masked_event(e) for e in drv['events']])
    return _walk(norm_times(obj), mask)


def normalise(run_dir):
    """{file name: content} of the normalised outputs of one run folder."""
    run_dir = Path(run_dir)
    res = json.loads((run_dir / 'RESULT.json').read_text(encoding='utf-8'))
    pr = Path(res['pipeline_run_dir']) if res.get('pipeline_run_dir') else None
    mask = Masker([(pr, '<PIPE_RUN>'), (run_dir, '<RUN>'), (os.path.realpath(run_dir), '<RUN>'),
                   (REPO, '<REPO>'), (TW, '<TW>')])
    out = {}
    if pr is not None:
        out['ledger.json'] = norm_ledger(_read_jsonl(pr / 'ledger.jsonl'), mask)
        eye = _read_jsonl(pr / 'eye.jsonl')
        if eye is not None:
            out['eye.json'] = norm_eye(eye, mask)
        for f in ('timing_summary.json', 'world_counts.json'):
            if (pr / f).exists():
                out[f] = _walk(norm_times(json.loads((pr / f).read_text(encoding='utf-8'))), mask)
        for f in ('boxel_data.json', 'problem_initial.pddl'):
            if (pr / f).exists():
                txt = (pr / f).read_text(encoding='utf-8')
                out[f] = json.loads(txt) if f.endswith('.json') else mask(txt)
    be = run_dir / 'save' / 'bridge_episode.json'
    if be.exists():
        out['bridge_episode.json'] = norm_bridge_episode(json.loads(be.read_text(encoding='utf-8')), mask)
    out['console.txt'] = norm_console((run_dir / 'stdout.txt').read_text(encoding='utf-8', errors='replace'), mask)
    calls = None
    if res['mode'] == 'record':
        calls = tape_calls(run_dir / 'tape')
        out['facts.json'] = [{'k': c['k'], 'goal': c['goal'], 'facts': c['facts']} for c in calls]
    elif res['mode'] == 'replay':
        calls = _read_jsonl(run_dir / 'rec' / 'calls.jsonl') or []
        out['facts.json'] = [{'k': c['k'], 'goal': c.get('goal'), 'facts': c.get('facts')} for c in calls]
        out['stub_checks.json'] = [{k: c.get(k) for k in ('k', 'facts_equal_tape', 'goal_equal_tape',
                                                          'rng_before_equal_tape',
                                                          'stream_ints_before_equal_tape', 'error')}
                                   for c in calls]
    stub_rows = _read_jsonl(run_dir / 'rec' / 'stubs.jsonl')
    if stub_rows is not None:
        out['stubs.json'] = _walk(stub_rows, mask)
    for f in ('first_plan.json', 'main_params.json'):
        p = run_dir / 'rec' / f
        if p.exists():
            obj = json.loads(p.read_text(encoding='utf-8'))
            out[f] = _walk(norm_first_plan(obj) if f == 'first_plan.json' else obj, mask)
    crash = run_dir / 'rec' / 'CRASH.txt'
    if crash.exists():
        text = crash.read_text(encoding='utf-8', errors='replace')
        out['crash.json'] = crash_record(text, mask)
        out['INFO_crash.txt'] = mask(text).rstrip('\n') + '\n'
    summary = out.get('timing_summary.json') or {}
    out['result.json'] = {
        'mode': res['mode'], 'status': res['status'], 'rc': res['rc'],
        'child_exit': _walk(res.get('child_exit', {}), mask),
        'exit_reason': summary.get('exit_reason'), 'success': summary.get('success'),
        'solve_calls': None if calls is None else len(calls),
        'tape_calls': (len(tape_calls(res['tape'])) if res.get('tape') and res['mode'] == 'replay'
                       else None),
        'outcome': (out.get('bridge_episode.json') or {}).get('outcome')}
    applied = run_dir / 'rec' / 'SET.json'
    if applied.exists():                 # SPEC D4, D5: what the child set, as it set it
        out['result.json']['set'] = json.loads(applied.read_text(encoding='utf-8'))
    return out


def run_notes(run_dir):
    """The NOTES lines of one run: a value set in the child (SPEC D5), and
    for a replay where it came from (the tape's META.json, with D4's reason
    when the recorder wrote one)."""
    if run_dir is None:
        return []
    run_dir = Path(run_dir)
    applied = run_dir / 'rec' / 'SET.json'
    if not applied.exists():
        return []
    res = json.loads((run_dir / 'RESULT.json').read_text(encoding='utf-8'))
    sets = json.loads(applied.read_text(encoding='utf-8'))
    line = ('set in the child (SPEC D5, --set): ' + ', '.join(f'{k} = {v!r}' for k, v in sets.items())
            + ', right after the module was executed (rec/SET.json; result.json set)')
    if res.get('mode') == 'replay' and res.get('tape'):
        meta = tape_meta(res['tape'])
        line += '; taken from the tape\'s META.json' + (f' ({meta["d4"]})' if meta.get('d4') else '')
    return [line]


def write_norm(run_dir):
    run_dir = Path(run_dir)
    norm = run_dir / 'norm'
    if norm.exists():
        shutil.rmtree(norm)
    norm.mkdir()
    for name, obj in normalise(run_dir).items():
        if isinstance(obj, str):
            (norm / name).write_text(obj, encoding='utf-8', newline='\n')
        else:
            write_json(norm / name, obj)
    return norm


def _load_norm(folder):
    out = {}
    for f in sorted(Path(folder).iterdir()):
        if f.is_file():
            out[f.name] = (f.read_text(encoding='utf-8') if f.suffix in ('.txt', '.pddl')
                           else json.loads(f.read_text(encoding='utf-8')))
    return out


def _rows_diff(a, b, limit=10):
    diffs = []
    for i in range(max(len(a), len(b))):
        ra = a[i] if i < len(a) else None
        rb = b[i] if i < len(b) else None
        if ra != rb:
            diffs.append({'index': i, 'live': ra, 'replay': rb})
            if len(diffs) >= limit:
                break
    return diffs


def _dict_diff(a, b, path=''):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f'{path}/{k}: only in {"replay" if k not in a else "live"}')
            else:
                out += _dict_diff(a[k], b[k], f'{path}/{k}')
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += _dict_diff(x, y, f'{path}[{i}]')
    elif a != b:
        out.append(f'{path}: live {json.dumps(a)[:160]} replay {json.dumps(b)[:160]}')
    return out


def compare_live(live_norm, replay_norm):
    """PLAN 24.3 (a): the replay's step and step_end rows against the live
    episode's, and a summary of every other difference."""
    live, rep = _load_norm(live_norm), _load_norm(replay_norm)
    out = {}
    la = [r for r in live.get('ledger.json', []) if r.get('kind') in ('step', 'step_end')]
    ra = [r for r in rep.get('ledger.json', []) if r.get('kind') in ('step', 'step_end')]
    out['steps'] = {'live_rows': len(la), 'replay_rows': len(ra), 'equal': la == ra,
                    'differences': _rows_diff(la, ra)}
    ll, rl = live.get('ledger.json', []), rep.get('ledger.json', [])
    out['ledger'] = {'live_rows': len(ll), 'replay_rows': len(rl), 'equal': ll == rl,
                     'kinds_live': _count([r.get('kind') for r in ll]),
                     'kinds_replay': _count([r.get('kind') for r in rl]),
                     'first_differences': _rows_diff(ll, rl, 5)}
    lf, rf = live.get('facts.json', []), rep.get('facts.json', [])
    out['facts'] = {'calls_live': len(lf), 'calls_replay': len(rf), 'equal': lf == rf,
                    'equal_per_call': [x == y for x, y in zip(lf, rf)]}
    for name in ('eye.json', 'timing_summary.json', 'world_counts.json', 'bridge_episode.json',
                 'boxel_data.json', 'problem_initial.pddl'):
        if name in live or name in rep:
            a, b = live.get(name), rep.get(name)
            if isinstance(a, list) and isinstance(b, list):
                out[name] = {'equal': a == b, 'n_live': len(a), 'n_replay': len(b),
                             'differing_records': [i for i in range(min(len(a), len(b))) if a[i] != b[i]][:20],
                             'first': _dict_diff(*next(((x, y) for x, y in zip(a, b) if x != y), (None, None)))[:10]}
            else:
                out[name] = {'equal': a == b, 'paths': _dict_diff(a, b)[:30]}
    lc = live.get('console.txt', '').splitlines()
    rc = rep.get('console.txt', '').splitlines()
    import difflib
    d = [x for x in difflib.unified_diff(lc, rc, 'live', 'replay', lineterm='', n=0)
         if not x.startswith(('---', '+++', '@@'))]
    out['console'] = {'equal': lc == rc, 'live_lines': len(lc), 'replay_lines': len(rc),
                      'changed_lines': len(d), 'first': d[:40]}
    out['result'] = {'live': live.get('result.json'), 'replay': rep.get('result.json')}
    return out


def _count(xs):
    c = {}
    for x in xs:
        c[str(x)] = c.get(str(x), 0) + 1
    return dict(sorted(c.items()))


# ---------------------------------------------------------------------------
# Coverage of test_full_pipeline.main (PLAN 24.3 (b))
# ---------------------------------------------------------------------------

def _str_arg(call):
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def main_sites(path=TFP):
    """From the source: every break, dispatch_end(...) and exit_reason = '...'
    inside main (nested functions included), and the dispatcher branches."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    sites = {'break': [], 'dispatch_end': [], 'exit_reason': [], 'branch': []}
    for node in ast.walk(main):
        if isinstance(node, ast.Break):
            sites['break'].append({'line': node.lineno})
        elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'dispatch_end':
            sites['dispatch_end'].append({'line': node.lineno, 'status': _str_arg(node)
                                          or ast.unparse(node.args[0]) if node.args else None})
        elif isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'exit_reason' for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                sites['exit_reason'].append({'line': node.lineno, 'value': node.value.value})
        elif isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Compare) and getattr(t.left, 'id', None) == 'action_name'
                    and all(isinstance(op, (ast.Eq, ast.In)) for op in t.ops)):
                vals = [c.value for c in ast.walk(t) if isinstance(c, ast.Constant)]
                sites['branch'].append({'line': node.lineno, 'body_line': node.body[0].lineno,
                                        'actions': vals})
    for v in sites.values():
        v.sort(key=lambda d: d['line'])
    return sites


def coverage_table(trace_files, path=TFP):
    reached = set()
    for tf in trace_files:
        for key, lines in json.loads(Path(tf).read_text(encoding='utf-8')).items():
            reached.update(lines)
    sites = main_sites(path)
    table = {}
    for kind, rows in sites.items():
        table[kind] = []
        for r in rows:
            line = r.get('body_line', r['line'])
            table[kind].append(dict(r, reached=line in reached))
    return table


# The map of sites between two versions of test_full_pipeline.py (SPEC D12):
# a line number names a site in one file only, kind and value alone do not
# name it (stale_precondition is passed at eight sites), so a site's anchor
# is its kind, its value, the dispatcher branch it is in and its ordinal
# among the sites with that kind, value and branch.  A break's value is the
# nearest site statement before it in its own block (the dispatch_end or
# exit_reason it closes), or none.

class SiteMapError(RuntimeError):
    """The two files' sites cannot be matched without picking."""


def _dispatcher_actions(node):
    """The actions of a dispatcher branch (main_sites' rule), else None."""
    if not isinstance(node, ast.If):
        return None
    t = node.test
    if (isinstance(t, ast.Compare) and getattr(t.left, 'id', None) == 'action_name'
            and all(isinstance(op, (ast.Eq, ast.In)) for op in t.ops)):
        return tuple(c.value for c in ast.walk(t) if isinstance(c, ast.Constant))
    return None


def _dispatch_status(call):
    return (_str_arg(call) or ast.unparse(call.args[0])) if call.args else None


def _statement_site(stmt):
    """'dispatch_end:<status>' or 'exit_reason:<value>' for a statement that
    is such a site, else None (a break's value)."""
    if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
            and getattr(stmt.value.func, 'id', None) == 'dispatch_end'):
        return f'dispatch_end:{_dispatch_status(stmt.value)}'
    if (isinstance(stmt, ast.Assign) and any(getattr(t, 'id', None) == 'exit_reason' for t in stmt.targets)
            and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)):
        return f'exit_reason:{stmt.value.value}'
    return None


def anchored_sites(path=TFP):
    """Every site of main_sites(path), with its anchor: [{kind, line, value,
    branch, ordinal}] in source order; branch is [actions..., ordinal] of
    the innermost dispatcher branch whose body holds the site (an elif or
    else part is not its branch's body), or None."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    found = []

    def site(node, siblings, index):
        if isinstance(node, ast.Break):
            before = [_statement_site(s) for s in (siblings or [])[:index]]
            return 'break', next((v for v in reversed(before) if v), None)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'dispatch_end':
            return 'dispatch_end', _dispatch_status(node)
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'exit_reason' for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return 'exit_reason', node.value.value
        actions = _dispatcher_actions(node)
        if actions is not None:
            return 'branch', list(actions)
        return None

    def visit(node, branch, siblings=None, index=None):
        s = site(node, siblings, index)
        if s is not None:
            found.append({'kind': s[0], 'line': node.lineno, 'col': node.col_offset, 'value': s[1],
                          'branch_node': branch, 'node': node})
        inner = node if _dispatcher_actions(node) is not None else None
        for field, value in ast.iter_fields(node):
            here = inner if (inner is not None and field == 'body') else branch
            if isinstance(value, list):
                for i, child in enumerate(value):
                    if isinstance(child, ast.AST):
                        visit(child, here, value, i)
            elif isinstance(value, ast.AST):
                visit(value, here)

    for i, stmt in enumerate(main.body):
        visit(stmt, None, main.body, i)
    found.sort(key=lambda d: (d['line'], d['col']))
    branch_anchor, seen = {}, {}
    for d in found:
        if d['kind'] == 'branch':
            key = tuple(d['value'])
            branch_anchor[id(d['node'])] = list(key) + [seen.get(key, 0)]
            seen[key] = seen.get(key, 0) + 1
    out, ordinals = [], {}
    for d in found:
        b = None if d['branch_node'] is None else branch_anchor[id(d['branch_node'])]
        key = (d['kind'], json.dumps(d['value']), json.dumps(b))
        out.append({'kind': d['kind'], 'line': d['line'], 'value': d['value'], 'branch': b,
                    'ordinal': ordinals.get(key, 0)})
        ordinals[key] = ordinals.get(key, 0) + 1
    return out


def _group_key(s):
    return (s['kind'], json.dumps(s['value']), json.dumps(s['branch']))


def site_map(old_path, new_path):
    """One to one and total: {"pairs": [(old, new)], "gone": [old], "new":
    [new]}.  Sites with the same kind, value and branch pair up by ordinal
    when both files hold as many of them; a group held by one file only is
    gone or new; a group whose counts differ cannot be paired without
    picking, and the tool fails (SiteMapError)."""
    old, new = anchored_sites(old_path), anchored_sites(new_path)
    groups = {}
    for side, sites in (('old', old), ('new', new)):
        for s in sites:
            groups.setdefault(_group_key(s), {'old': [], 'new': []})[side].append(s)
    pairs, gone, added, bad = [], [], [], []
    for key, g in groups.items():
        if g['old'] and g['new']:
            if len(g['old']) != len(g['new']):
                bad.append(f'{key[0]} value {key[1]} in branch {key[2]}: lines {[s["line"] for s in g["old"]]} '
                           f'in the old file, {[s["line"] for s in g["new"]]} in the new one')
                continue
            pairs += list(zip(g['old'], g['new']))
        elif g['old']:
            gone += g['old']
        else:
            added += g['new']
    if bad:
        raise SiteMapError('ambiguous anchors, not paired: ' + '; '.join(bad))
    by_line = lambda s: s['line']
    return {'pairs': sorted(pairs, key=lambda p: p[1]['line']), 'gone': sorted(gone, key=by_line),
            'new': sorted(added, key=by_line)}


def _trace_lines(trace_files):
    reached = set()
    for tf in trace_files:
        for lines in json.loads(Path(tf).read_text(encoding='utf-8')).values():
            reached.update(lines)
    return reached


def coverage_compare(trace_files, baseline, old_path, new_path=TFP):
    """The tag's coverage against checkpoint 1's baseline through the map:
    the baseline's sites must be the old file's main_sites (kind and line),
    each pair says whether the old pins and the new ones reach it, and a
    pair reached on the old file and not on the new one is named lost."""
    base = json.loads(Path(baseline).read_text(encoding='utf-8'))
    base_reached = {(s['kind'], s['line']): bool(s['reached']) for s in base['sites']}
    old_rows = main_sites(old_path)
    old_keys = {(k, r['line']) for k, rows in old_rows.items() for r in rows}
    if old_keys != set(base_reached):
        raise SiteMapError(f'the baseline {rel(Path(baseline))} is not of {old_path}: its sites differ '
                           f'from main_sites ({len(old_keys ^ set(base_reached))} sites)')
    reached = _trace_lines(trace_files)
    body = {r['line']: r['body_line'] for r in main_sites(new_path)['branch']}
    m = site_map(old_path, new_path)

    def new_reached(s):
        return body.get(s['line'], s['line']) in reached

    def anchor(s):
        return {'value': s['value'], 'branch': s['branch'], 'ordinal': s['ordinal']}
    rows = [{'kind': o['kind'], 'old_line': o['line'], 'new_line': n['line'], 'anchor': anchor(n),
             'old_reached': base_reached[(o['kind'], o['line'])], 'new_reached': new_reached(n)}
            for o, n in m['pairs']]
    new_rows = [{'kind': n['kind'], 'new_line': n['line'], 'anchor': anchor(n), 'new_reached': new_reached(n)}
                for n in m['new']]
    gone_rows = [{'kind': o['kind'], 'old_line': o['line'], 'anchor': anchor(o),
                  'old_reached': base_reached[(o['kind'], o['line'])]} for o in m['gone']]
    summary = {}
    for kind in ('break', 'dispatch_end', 'exit_reason', 'branch'):
        mine = [r for r in rows if r['kind'] == kind]
        summary[kind] = {
            'old': sum(1 for k, _ in base_reached if k == kind),
            'new': len(mine) + sum(1 for r in new_rows if r['kind'] == kind),
            'paired': len(mine), 'new_sites': sum(1 for r in new_rows if r['kind'] == kind),
            'gone': sum(1 for r in gone_rows if r['kind'] == kind),
            'old_reached': sum(1 for (k, _), v in base_reached.items() if k == kind and v),
            'new_reached': (sum(1 for r in mine if r['new_reached'])
                            + sum(1 for r in new_rows if r['kind'] == kind and r['new_reached']))}
    return {'old_file': {'path': str(old_path), 'git_blob_sha1': git_blob_sha1(Path(old_path).read_bytes())},
            'new_file': {'path': rel(Path(new_path)), 'git_blob_sha1': git_blob_sha1(Path(new_path).read_bytes())},
            'baseline': rel(Path(baseline)), 'trace_files': len(trace_files), 'summary': summary,
            'lost': [r for r in rows if r['old_reached'] and not r['new_reached']],
            'map': rows, 'new': new_rows, 'gone': gone_rows}


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

# At storing (SPEC D3, D4): the rows the two rules decide on, counted in the
# recording's ledger by the names the tag's code writes them with (each read
# again from that code by test_recorder.py's
# test_the_names_the_counts_rest_on_are_the_tag_s).
M7_SUSPENSION_KIND = 'm7_suspension'          # belief.py:134, 140 and 162
M7_SUSPENSION_START_OP = 'start'              # its op at belief.py:140
M7_SUSPENSION_END_OP = 'end'                  # its op at belief.py:134 and 162
SENSE_DISCOVERY_KIND = 'sense_discovery'      # execution.py:3689-3690, written with M7 on only
SENSE_RESULT_KIND = 'sense_result'            # test_full_pipeline.py:2461, reason=sense_result.reason
# A sense whose outcome is contains_nontarget and that reaches M7's code ends
# with this reason (execution.py:3743, reason=f"sense_{sense_outcome}"; M7's
# code starts at 3386); the unlocalizable case returns before it (3372-3373)
# and does not count.
NONTARGET_REASON = 'sense_contains_nontarget'


def ledger_counts(rows):
    """{m7_suspension_start, m7_suspension_end, sense_discovery,
    sense_result_contains_nontarget} of a ledger's rows."""
    c = {'m7_suspension_start': 0, 'm7_suspension_end': 0, 'sense_discovery': 0,
         'sense_result_contains_nontarget': 0}
    for r in rows or []:
        kind = r.get('kind')
        if kind == M7_SUSPENSION_KIND:
            c['m7_suspension_end' if r.get('op') == M7_SUSPENSION_END_OP else 'm7_suspension_start'] += 1
        elif kind == SENSE_DISCOVERY_KIND:
            c['sense_discovery'] += 1
        elif kind == SENSE_RESULT_KIND and r.get('reason') == NONTARGET_REASON:
            c['sense_result_contains_nontarget'] += 1
    return c


def twin_rule(name, counts):
    """SPEC D3: a tape whose ledger holds a sense_discovery row (M7 on writes
    it, execution.py:3686-3694) or a sense that reaches contains_nontarget
    gets an --m7 off twin, its own live recording.  {"name": the twin or
    None, "reasons": [...], "none_because": why there is none}."""
    reasons = []
    if counts['sense_discovery']:
        reasons.append(f"{counts['sense_discovery']} sense_discovery row(s)")
    if counts['sense_result_contains_nontarget']:
        reasons.append(f"{counts['sense_result_contains_nontarget']} sense_result row(s) with reason "
                       f"{NONTARGET_REASON}")
    spec = entry(name)
    if spec['m7'] == 'off' or '--m7' in spec['argv']:
        return {'name': None, 'reasons': reasons, 'none_because': 'the entry sets --m7 itself'}
    if not reasons:
        return {'name': None, 'reasons': [], 'none_because': 'no such row'}
    return {'name': name + TWIN_SUFFIX, 'reasons': reasons, 'none_because': None}


# SPEC D4 (U1): a live run that holds m7_suspension rows is recorded again
# with the suspended region never coming back (D5's --set in the child);
# the first recording stays beside it as <name>.as_recorded, for U1's test.
D4_SET = {'execution.M7_SUSPEND_S': 1e9}
AS_RECORDED_SUFFIX = '.as_recorded'
D4_REASON = ('SPEC D4: the live run held m7_suspension rows, so the tape was recorded again with '
             'execution.M7_SUSPEND_S = 1e9 (the region never comes back)')


def store_record(run_dir, name, result, as_recorded=None):
    """What the recorder writes beside a tape when it stores it
    (STORED.json): the counts, D3's twin and the rows D4 acts on;
    as_recorded, for D4's second recording, names the first one."""
    run_dir = Path(run_dir)
    norm = run_dir / 'norm' / 'ledger.json'
    rows = json.loads(norm.read_text(encoding='utf-8')) if norm.exists() else None
    counts = ledger_counts(rows)
    twin = (twin_rule(name, counts) if result['status'] == 'ended'
            else {'name': None, 'reasons': [], 'none_because': f'the recording ended as {result["status"]}'})
    suspensions = counts['m7_suspension_start'] + counts['m7_suspension_end']
    if as_recorded is not None:
        rule = f'{D4_REASON}; the first recording is {as_recorded["folder"]}'
    elif suspensions and result['status'] == 'ended':
        rule = 'D4: the live run holds m7_suspension rows; recorded again with execution.M7_SUSPEND_S set long'
    elif suspensions:
        rule = (f'D4: the live run holds m7_suspension rows; not recorded again, the recording ended as '
                f'{result["status"]}')
    else:
        rule = None
    d4 = {'m7_suspension_rows': suspensions, 'set': result.get('set') or None, 'rule': rule}
    if as_recorded is not None:
        d4['as_recorded'] = as_recorded
    stored = {'episode': name, 'status': result['status'], 'ledger_rows': None if rows is None else len(rows),
              'counts': counts, 'twin': twin, 'd4': d4}
    write_json(run_dir / 'STORED.json', stored)
    return stored


def move_run(run_dir, to):
    """Move a run folder to `to` (replaced if there); the paths RESULT.json
    holds into the folder follow it.  Its norm/ is the one written at the
    run, before the move."""
    run_dir, to = Path(run_dir).resolve(), Path(to).resolve()
    if to.exists():
        shutil.rmtree(to)
    run_dir.rename(to)
    res_path = to / 'RESULT.json'
    if res_path.exists():
        res = json.loads(res_path.read_text(encoding='utf-8'))
        old = str(run_dir)

        def moved(v):
            return str(to) + v[len(old):] if isinstance(v, str) and (v == old or v.startswith(old + '/')) else v
        for k in ('pipeline_run_dir', 'tape', 'cwd'):
            res[k] = moved(res.get(k))
        res['argv'] = [moved(x) for x in res.get('argv') or []]
        write_json(res_path, res)
    return to


def record_set(out_dir, episodes, log=print):
    """Record each live episode into out_dir/<name>/ (tape/, norm/, raw).
    At storing, the counts and the rules of D3 and D4 go beside the tape
    (STORED.json) and into out_dir/STORE.json; a recording D4 asks for is
    made again at once with D4_SET (the first kept as <name>.as_recorded);
    a twin D3 asks for is recorded right after, unless this call names it
    or the set holds its recording from an earlier call (its STORED.json):
    a set may be recorded one episode per call, a twin in a call of its
    own.  A name the call gives is always recorded (its folder replaced)."""
    for name in episodes:                # every name resolves before the first recording
        entry(name)
    worst = 0
    queue, store = list(episodes), {}
    while queue:
        name = queue.pop(0)
        folder = Path(out_dir) / name
        res = run_episode(name, 'record', folder, log=log)
        stored = store_record(folder, name, res)
        if stored['d4']['m7_suspension_rows'] and res['status'] == 'ended':
            kept = move_run(folder, Path(out_dir) / (name + AS_RECORDED_SUFFIX))
            log(f'[record_episode] {name}: D4, {stored["d4"]["m7_suspension_rows"]} m7_suspension row(s): '
                f'recorded again with {D4_SET}; the first recording is {kept.name}')
            res = run_episode(name, 'record', folder, log=log, sets=D4_SET)
            write_json(folder / 'tape' / 'META.json', dict(tape_meta(folder / 'tape'), d4=D4_REASON))
            stored = store_record(folder, name, res, as_recorded={
                'folder': kept.name, 'status': stored['status'],
                'm7_suspension_rows': stored['d4']['m7_suspension_rows']})
        if res['status'] != 'ended':
            worst = 1
        store[name] = stored
        twin = stored['twin']['name']
        if twin and twin not in episodes and twin not in store and twin not in queue:
            held = Path(out_dir) / twin / 'STORED.json'
            if held.exists():
                status = json.loads(held.read_text(encoding='utf-8')).get('status')
                log(f'[record_episode] {name}: D3 asks for the twin {twin}; the set holds its recording from '
                    f'an earlier call ({twin}/STORED.json, status {status}): not recorded again')
            else:
                log(f'[record_episode] {name}: D3 asks for the twin {twin} '
                    f'({"; ".join(stored["twin"]["reasons"])})')
                queue.insert(0, twin)
    path = Path(out_dir) / 'STORE.json'          # a set recorded in several calls keeps every entry
    earlier = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    write_json(path, dict(earlier, **store))
    return worst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--episode', type=entry_name,
                    help=f'{", ".join(sorted(EPISODES))} (configuration D), f<seed> or r<seed> '
                         f'(F or R on a generated scene), a boxels entry with {LOOK_SUFFIX} (run boxels '
                         f'-Headless -Look boxel -Eye arm), each also with {TWIN_SUFFIX} (its --m7 off twin)')
    ap.add_argument('--print-argv', action='store_true',
                    help='print what --episode starts (command, cwd, environment, sources) and start nothing')
    ap.add_argument('--mode', choices=('record', 'replay', 'first-plan'))
    ap.add_argument('--run-dir')
    ap.add_argument('--tape')
    ap.add_argument('--rng', choices=('restore', 'keep'), default='restore')
    ap.add_argument('--trace-main', action='store_true')
    ap.add_argument('--timeout', type=float, default=EPISODE_TIMEOUT_S)
    ap.add_argument('--record-set')
    ap.add_argument('--episodes', default=','.join(PIN47_EPISODES))
    ap.add_argument('--renorm')
    ap.add_argument('--coverage', nargs='+', metavar='TRACE',
                    help='trace files (rec/main_lines.json, a pin\'s INFO_main_lines.json): the table of '
                         'main_sites with what they reach')
    ap.add_argument('--baseline', help='with --coverage: an older coverage file (phase0/G1/coverage_41893d5.json) '
                                       'to compare with through the map of sites')
    ap.add_argument('--old-tfp', help='with --baseline: the test_full_pipeline.py the baseline is of '
                                      '(the file at that commit, written out by the caller)')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--rec', help=argparse.SUPPRESS)
    ap.add_argument('--script', help=argparse.SUPPRESS)
    ap.add_argument('--set', action='append', default=[], type=_set_arg, metavar='NAME=VALUE',
                    help=f'SPEC D5: set NAME ({", ".join(SET_NAMES)}) to float(VALUE) in the child right '
                         f'after its module is executed; with --episode (a replay takes it from the tape)')
    ap.add_argument('--stubs', help='JSON of tests/readable/executor_stubs.py (scripted tapes)')
    ap.add_argument('--tfp-copy', help='planted-change checks only: run this copy of '
                                       'test_full_pipeline.py instead of the checkout\'s')
    ap.add_argument('argv', nargs='*', help='the entry\'s argv: given to the child (--child) only')
    a = ap.parse_args(argv)
    if a.child:
        return child_main(a)
    if a.argv:
        # The parent takes its argv from the entry (EPISODES, f/r<seed>,
        # _m7off); positional arguments would be dropped, so they are refused.
        ap.error(f'positional arguments {a.argv} are not passed to the episode by the parent; an episode\'s '
                 f'argv is its entry\'s (--episode NAME --print-argv shows it)')
    if a.print_argv:
        if not a.episode:
            ap.error('--print-argv needs --episode')
        print(json.dumps(describe_entry(a.episode), indent=1, ensure_ascii=False))
        return 0
    if a.renorm:
        write_norm(a.renorm)
        return 0
    if a.baseline or a.old_tfp:
        if not (a.coverage and a.baseline and a.old_tfp):
            ap.error('--baseline and --old-tfp go together, with --coverage')
    if a.coverage:
        out = {'table': coverage_table(a.coverage)}
        if a.baseline:
            try:
                out['compare'] = coverage_compare(a.coverage, a.baseline, a.old_tfp)
            except SiteMapError as ex:
                print(f'[record_episode] {ex}', file=sys.stderr)
                return 3
        print(json.dumps(out if a.baseline else out['table'], indent=1))
        return 0
    if a.record_set:
        if a.set:
            ap.error('--set goes with --episode; --record-set sets what SPEC D4 asks for itself')
        return record_set(a.record_set, [e for e in a.episodes.split(',') if e])
    if not (a.episode and a.mode and a.run_dir):
        ap.error('--episode, --mode and --run-dir are needed (or --record-set, --renorm, --coverage)')
    if a.mode == 'replay' and not a.tape:
        ap.error('--mode replay needs --tape')
    try:
        res = run_episode(a.episode, a.mode, a.run_dir, tape=a.tape, rng=a.rng,
                          trace_main=a.trace_main, timeout=a.timeout, stubs=a.stubs,
                          tfp_copy=a.tfp_copy, sets=dict(a.set))
    except SetError as ex:
        ap.error(str(ex))
    return 0 if res['status'] == 'ended' and res['child_exit'].get('code') is not None else 1


if __name__ == '__main__':
    sys.exit(main())
