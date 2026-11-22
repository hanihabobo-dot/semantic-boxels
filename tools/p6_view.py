#!/usr/bin/env python3
"""Path 6, rule 15 of the dev tracks (Hani, 2026-11-07): the commands for the
visual check of a comparison eval.

PRINT ONLY.  It opens no window, makes no wsl call and starts no episode: it
reads git objects and the arms' own eval_runner sources and prints text.  Hani
starts every run himself, one at a time, and approves in writing (rule 15);
the sessions only print the list.  Run it with Windows Python from any
checkout that holds it (tools/p6_view.ps1 is the same with PowerShell
parameters):

  python tools/p6_view.py --wave 1 [--arm A|B]           wave 1: arms A and B on the tabletop
  python tools/p6_view.py --wave 2 [--arm A|Aprime|T]    wave 2: arms A, A' and T on find_dice scenes 113 and 102

A tabletop cell is printed twice.  First its OWN command: the argv that the
arm's own eval_runner builds for it (cell_to_argv through the runner's own
matrix expansion, the way tools/cluster/p6_run.py does), which is what the
cluster runs.  Then the same flags as a `run.ps1 boxels` line, the way Hani
watches: the window on (no --no-gui) and the curated console (no
--log-level quiet); nothing else differs.  run.ps1 passes --n-occluders itself
(its default 2), which the stack scene does not read.  The thesis code (arm B)
has no launcher, so its line comes after the recipe that makes its code tree
beside the other checkouts, with run.ps1 and tools/run_procs.sh copied in
(A' needs the recipe too, without the copies); the export leaves out
eval_results, thesis, archive and notes, which no run reads (about 4 MiB for the
thesis commit instead of 305).  Arm T's line is the command
that tools/_bridge_campaign.py's episode_t runs, with --vis 1 for the window.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import p6_slots as ps  # noqa: E402

THESIS = '6b00cd7'      # arm B: the thesis code
APRIME = '51428d8'      # arm A': A plus TB-1 (path 3's commit), pipeline files as A' has them
B_DIR = os.path.join(os.path.dirname(REPO), 'sb-thesis')
APRIME_DIR = os.path.join(os.path.dirname(REPO), 'sb-aprime')
WAVE1 = [('random-pairs, find-and-tray-stack, 2 occluders, seed 2', ps.rp_cell(2, 2, 'find-and-tray-stack')),
         ('stack, tower height 2, 3 targets, seed 0', ps.stack_cell(2, 0))]
WAVE2_SEEDS = (113, 102)
RUN_PS1_FLAGS = {'--scene': '-Scene', '--seed': '-Seed', '--goal': '-Goal', '--n-occluders': '-Occluders'}
TAMPURA_WORK = '/root/tampura-work'
T_DIR = '/root/p6_view'
# the export leaves out what no run reads (the thesis commit's tree is 305 MiB, 300 of them these folders; the code is 4 MiB)
EXPORT_LEAVE_OUT = ('eval_results', 'thesis', 'archive', 'notes')


def git_show(commit, path):
    """A file of a commit, as text (Windows git: the pinned commits are read, never checked out)."""
    out = subprocess.run(['git', '-C', REPO, 'show', f'{commit}:{path}'], capture_output=True, check=True)
    return out.stdout.decode('utf-8')


def runner_source(arm):
    """The arm's own eval_runner source: A's is this checkout's, B's is the thesis commit's."""
    if arm == 'B':
        return git_show(THESIS, 'eval_runner.py'), f'eval_runner@{THESIS}'
    with open(os.path.join(REPO, 'evaluation', 'eval_runner.py'), encoding='utf-8') as f:
        return f.read(), 'eval_runner@checkout'


def cell_argv(arm, cell):
    """What the arm's own runner runs for a cell, without the interpreter:
    ['test_full_pipeline.py', '--no-gui', ...] (p6_run.py's way: through the runner's matrix expansion)."""
    src, label = runner_source(arm)
    # __package__ set: the runner's start-as-a-file line (the repository root onto sys.path, since the
    # folder move) reads it and does nothing for a module that is not started as a file
    ns = {'__name__': 'p6_view_runner', '__file__': label, '__package__': 'p6_view'}
    exec(compile(src, label, 'exec'), ns)
    cells = list(ns['iterate_matrix'](ps.as_matrix([cell])))
    if len(cells) != 1:
        raise SystemExit(f"{label}: the cell expands to {len(cells)} cells")
    return ns['cell_to_argv'](cells[0], [])[1:]


def flags_of(argv):
    """['test_full_pipeline.py', '--seed', '2', '--no-gui'] -> [('--seed', '2'), ('--no-gui', None)]."""
    out, i = [], 1
    while i < len(argv):
        tok = argv[i]
        if not tok.startswith('--'):
            raise ValueError(f"unexpected token {tok!r} in {argv}")
        if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
            out.append((tok, argv[i + 1]))
            i += 2
        else:
            out.append((tok, None))
            i += 1
    return out


def watch_flags(flags):
    """The cell's flags for a window: --no-gui and --log-level quiet dropped, nothing else."""
    return [(f, v) for f, v in flags if f != '--no-gui' and (f, v) != ('--log-level', 'quiet')]


def run_boxels_line(run_ps1, flags):
    """The `run.ps1 boxels` call that passes the given flags (watch_flags of a cell)."""
    d = dict(flags)
    parts = [f"& {run_ps1} boxels", f"-Seed {d['--seed']}", f"-Scene {d['--scene']}", f"-Goal {d['--goal']}"]
    if '--n-occluders' in d:
        parts.append(f"-Occluders {d['--n-occluders']}")
    rest = [t for f, v in flags if f not in RUN_PS1_FLAGS for t in ((f,) if v is None else (f, v))]
    if rest:
        parts.append(f"-Args '{' '.join(rest)}'")
    return ' '.join(parts)


def wsl_path(path):
    """C:\\Users\\x -> /mnt/c/Users/x, as run.ps1 writes $S."""
    if len(path) > 2 and path[1] == ':':
        return '/mnt/' + path[0].lower() + path[2:].replace('\\', '/')
    return path.replace('\\', '/')


def export_recipe(commit, dest, copy_launcher):
    """Windows PowerShell lines (no wsl) that make a code tree of a commit beside the other checkouts."""
    zip_path = os.path.join('$env:TEMP', f'p6_view_{commit}.zip')
    leave_out = ' '.join(f"':(exclude){d}'" for d in EXPORT_LEAVE_OUT)
    lines = [f"git -C {REPO} -c core.autocrlf=false archive --format=zip -o {zip_path} {commit} -- . {leave_out}",
             f"Expand-Archive -LiteralPath {zip_path} -DestinationPath {dest}"]
    if copy_launcher:
        lines += [f"Copy-Item -LiteralPath {os.path.join(REPO, 'run.ps1')} -Destination {os.path.join(dest, 'run.ps1')}",
                  f"Copy-Item -LiteralPath {os.path.join(REPO, 'tools', 'run_procs.sh')} "
                  f"-Destination {os.path.join(dest, 'tools', 'run_procs.sh')}"]
    lines.append(f"Remove-Item -LiteralPath {zip_path}")
    return lines


def t_command(seed):
    """Arm T's episode as episode_t runs it (their driver copy with the timed policy, their venv, a folder holding
    the one scene), with --vis 1 for the window; one PowerShell line that hands it to bash."""
    s = wsl_path(REPO)
    d = f'{T_DIR}/T_s{seed}'
    scene = f'{s}/tampura_bridge/gen_scenes/find_dice/find_dice_gen_s{seed}.json'
    steps = [f'D={d}',
             'mkdir -p $D/tampura_environments/find_dice/problems $D/save',
             f'cp {scene} $D/tampura_environments/find_dice/problems/',
             f'ln -sfn {TAMPURA_WORK}/tampura_environments/env_configs $D/env_configs',
             'cd $D',
             (f'PATH={TAMPURA_WORK}/.venv/bin:$PATH VIRTUAL_ENV={TAMPURA_WORK}/.venv PYTHONPATH={s} '
              f'PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 BOXEL_EYE_IMAGES=0 TAMPURA_WORK={TAMPURA_WORK} '
              f'{TAMPURA_WORK}/.venv/bin/python -u {s}/tools/run_tampura_timed.py '
              f'--config ./env_configs/find_dice.yml --planner tampura_policy_timed '
              f'--global-seed {seed} --save-dir $D/save --vis 1')]
    return "wsl -e bash -c '" + ' && '.join(steps) + "'"


def cups(seed):
    """n_cups of a BF#63 scene, from the manifest in this checkout."""
    import json
    path = os.path.join(REPO, 'tampura_bridge', 'gen_scenes', 'find_dice', 'manifest.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)['details'][str(seed)]['n_cups']


def wave1_lines(arm):
    L = []
    if arm in ('all', 'A'):
        L += ['== arm A: our code now (this checkout, the tag with TB-8, TB-20, TB-16 and the path 6 tools) ==']
        for title, cell in WAVE1:
            argv = cell_argv('A', cell)
            L += [f'cell: {title}',
                  "  the cell's own command (what the cluster runs):",
                  '    python ' + ' '.join(argv),
                  '  to watch it (window on, curated console):',
                  '    ' + run_boxels_line(os.path.join(REPO, 'run.ps1'), watch_flags(flags_of(argv))), '']
    if arm in ('all', 'B'):
        L += [f'== arm B: our thesis code, commit {THESIS} ==',
              f"once (Windows PowerShell, no wsl): the thesis code as a tree beside the other checkouts, with the "
              f"launcher and its process guard copied in (the pipeline files stay byte-equal to {THESIS}):"]
        L += ['    ' + x for x in export_recipe(THESIS, B_DIR, True)] + ['']
        for title, cell in WAVE1:
            argv = cell_argv('B', cell)
            L += [f'cell: {title}',
                  "  the cell's own command (what the cluster runs):",
                  '    python ' + ' '.join(argv),
                  '  to watch it (window on, curated console):',
                  '    ' + run_boxels_line(os.path.join(B_DIR, 'run.ps1'), watch_flags(flags_of(argv))), '']
    return L


def wave2_lines(arm):
    L = []
    seeds = ','.join(str(s) for s in WAVE2_SEEDS)
    what = ', '.join(f'{s} ({cups(s)} cup{"" if cups(s) == 1 else "s"})' for s in WAVE2_SEEDS)
    L.append(f'scenes: BF#63 seeds {what}')
    if arm in ('all', 'A'):
        L += ['', '== arm A: our code now (this checkout) ==',
              f"    & {os.path.join(REPO, 'run.ps1')} tampura -Seed {seeds} -Gen", '']
    if arm in ('all', 'Aprime'):
        L += ['', f"== arm A': A plus TB-1, commit {APRIME} (path 3's BF#64 fix; its tree has run.ps1 and the guard) ==",
              'once (Windows PowerShell, no wsl):']
        L += ['    ' + x for x in export_recipe(APRIME, APRIME_DIR, False)]
        L += [f"    & {os.path.join(APRIME_DIR, 'run.ps1')} tampura -Seed {seeds} -Gen", '']
    if arm in ('all', 'T'):
        L += ['', "== arm T: TAMPURA's planner on the same scenes (their driver with the timed policy and the "
                  "reviewed final-world wrapper, this checkout as the snapshot) ==",
              "not in run_procs.sh's list: `run ps` does not show it, so let each run end by itself (the console "
              "prints its summary) before closing the window; the run leaves its folder under "
              f"{T_DIR} (final_world.json is in its save/), deleted by path afterwards"]
        for s in WAVE2_SEEDS:
            L += ['    ' + t_command(s)]
        L += ['']
    return L


def render(wave, arm='all'):
    head = [f'p6_view, rule 15, wave {wave}: PRINT ONLY. No window, no wsl call, no episode here. Hani starts '
            'each run himself, one at a time; a GUI run shows behaviour, not cluster times.', '']
    return '\n'.join(head + (wave1_lines(arm) if wave == 1 else wave2_lines(arm)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--wave', type=int, choices=(1, 2), default=1)
    ap.add_argument('--arm', default='all', choices=('all', 'A', 'B', 'Aprime', 'T'))
    a = ap.parse_args(argv)
    if (a.wave == 1 and a.arm in ('Aprime', 'T')) or (a.wave == 2 and a.arm == 'B'):
        ap.error(f'arm {a.arm} is not in wave {a.wave}')
    print(render(a.wave, a.arm))
    return 0


if __name__ == '__main__':
    sys.exit(main())
