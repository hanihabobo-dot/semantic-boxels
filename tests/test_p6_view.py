"""Path 6, rule 15: tools/p6_view.py prints the commands for the visual check.

It prints only (no window, no wsl call, no episode); the cell's own command is
the argv of the arm's own eval_runner, and the line to watch it passes the same
flags through run.ps1.  The tool is run with Windows Python, and these tests
are meant for it; the one test that runs run.ps1 needs PowerShell 7 and skips
without it.  Under WSL (the integration trial of 14 Nov ran them there) two
kinds of test skip, each with its reason: the ones that read the pinned commits
when git here cannot read them (WSL git cannot open a Windows worktree; an
export has no history), and the recipe test, whose lines are Windows
PowerShell with Windows paths.
"""
import io
import os
import shutil
import subprocess
import sys
import tarfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'tools'))
sys.path.insert(0, os.path.join(REPO, 'tools', 'cluster'))
import p6_slots as ps  # noqa: E402
import p6_view as pv  # noqa: E402

TB = 'test_full_pipeline.py'
RP, STACK = (c for _, c in pv.WAVE1)
_PWSH = shutil.which('pwsh') or shutil.which('pwsh.exe')


def _git_reads(commit):
    """Can git, as this interpreter finds it, read the commit from this checkout?"""
    try:
        return subprocess.run(['git', '-C', REPO, 'cat-file', '-e', f'{commit}^{{commit}}'],
                              capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


needs_pinned = pytest.mark.skipif(
    not all(_git_reads(c) for c in (pv.THESIS, pv.APRIME)),
    reason=f'git here cannot read the pinned commits {pv.THESIS} and {pv.APRIME} from this checkout '
           '(WSL git cannot open a Windows worktree; an export has no history); the tool runs with Windows Python')
windows_only = pytest.mark.skipif(
    os.name != 'nt', reason='the recipe is Windows PowerShell with Windows paths, printed by Windows Python')


@needs_pinned
def test_cells_are_the_arms_own_runner_argv():
    # arm A: this checkout's runner (the tag's, with TB-8 and TB-20)
    assert pv.cell_argv('A', RP) == [
        TB, '--no-gui', '--scene', 'random-pairs', '--seed', '2', '--goal', 'find-and-tray-stack',
        '--baseline', 'semantic', '--log-level', 'quiet', '--no-telemetry', '--n-occluders', '2']
    assert pv.cell_argv('A', STACK) == [
        TB, '--no-gui', '--scene', 'stack', '--seed', '0', '--goal', 'stack',
        '--baseline', 'semantic', '--log-level', 'quiet', '--no-telemetry', '--stack-height', '2']
    # arm B: the thesis commit's runner: the seed retry on random-pairs, and no --no-telemetry (not there yet)
    assert pv.cell_argv('B', RP) == [
        TB, '--no-gui', '--scene', 'random-pairs', '--seed', '2', '--goal', 'find-and-tray-stack',
        '--baseline', 'semantic', '--log-level', 'quiet', '--n-occluders', '2', '--seed-retry']
    assert pv.cell_argv('B', STACK) == [
        TB, '--no-gui', '--scene', 'stack', '--seed', '0', '--goal', 'stack',
        '--baseline', 'semantic', '--log-level', 'quiet', '--stack-height', '2']


def test_cells_equal_the_cluster_scripts_dry_run_for_arm_a(monkeypatch, capsys):
    """p6_run.py --dry-run prints what the cluster runs for a cell; the tool must say the same."""
    import p6_run
    monkeypatch.chdir(REPO)
    assert p6_run.main(['--arm', 'A', '--set', 'smoke', '--out', 'unused', '--dry-run']) == 0
    lines = capsys.readouterr().out.splitlines()
    for _, cell in pv.WAVE1:
        line = next(ln for ln in lines if ln.strip().startswith(ps.expected_tag(cell) + ':'))
        assert line.split(': ', 1)[1].split() == pv.cell_argv('A', cell)


def test_watching_drops_only_the_window_and_the_quiet_console():
    flags = pv.flags_of(pv.cell_argv('A', RP))
    watch = pv.watch_flags(flags)
    assert set(flags) - set(watch) == {('--no-gui', None), ('--log-level', 'quiet')}
    assert watch == [f for f in flags if f not in (('--no-gui', None), ('--log-level', 'quiet'))]


@needs_pinned
def test_run_boxels_lines():
    def line(arm, cell):
        return pv.run_boxels_line('X\\run.ps1', pv.watch_flags(pv.flags_of(pv.cell_argv(arm, cell))))
    assert line('A', RP) == ("& X\\run.ps1 boxels -Seed 2 -Scene random-pairs -Goal find-and-tray-stack "
                             "-Occluders 2 -Args '--baseline semantic --no-telemetry'")
    assert line('A', STACK) == ("& X\\run.ps1 boxels -Seed 0 -Scene stack -Goal stack "
                                "-Args '--baseline semantic --no-telemetry --stack-height 2'")
    assert line('B', RP) == ("& X\\run.ps1 boxels -Seed 2 -Scene random-pairs -Goal find-and-tray-stack "
                             "-Occluders 2 -Args '--baseline semantic --seed-retry'")
    assert line('B', STACK) == ("& X\\run.ps1 boxels -Seed 0 -Scene stack -Goal stack "
                                "-Args '--baseline semantic --stack-height 2'")


@pytest.mark.skipif(_PWSH is None or os.name != 'nt', reason='needs PowerShell 7 on Windows')
@pytest.mark.parametrize('arm', ['A', 'B'])
def test_run_ps1_passes_exactly_the_cells_flags(arm):
    """The printed watch line, run through this checkout's run.ps1 with -DryRun (print only: it returns before
    any wsl call), builds a pipeline command with the cell's flags, window on and curated console."""
    for _, cell in pv.WAVE1:
        want = pv.watch_flags(pv.flags_of(pv.cell_argv(arm, cell)))
        line = pv.run_boxels_line(os.path.join(REPO, 'run.ps1'), want)
        proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', line + ' -DryRun'],
                              capture_output=True, text=True, timeout=120, cwd=REPO)
        assert proc.returncode == 0, proc.stderr
        printed = proc.stdout.strip()
        assert '\n' not in printed and 'wsl' not in printed.split('&&')[0].split()[0:1]
        got = pv.flags_of([TB] + printed.split(TB, 1)[1].split())
        if '--n-occluders' not in dict(want):       # run.ps1 always passes its own (default 2); the stack scene ignores it
            want = want + [('--n-occluders', '2')]
        assert sorted(got, key=lambda t: t[0]) == sorted(want, key=lambda t: t[0]), printed
        assert '--no-gui' not in printed and '--log-level' not in printed


@windows_only
def test_recipes():
    b = pv.export_recipe(pv.THESIS, pv.B_DIR, True)
    leave_out = "-- . ':(exclude)eval_results' ':(exclude)thesis' ':(exclude)archive' ':(exclude)notes'"
    assert len(b) == 5 and b[0].endswith(
        f'archive --format=zip -o $env:TEMP\\p6_view_{pv.THESIS}.zip {pv.THESIS} {leave_out}')
    assert b[1].startswith('Expand-Archive -LiteralPath') and b[1].endswith(pv.B_DIR)
    assert 'run.ps1' in b[2] and 'run_procs.sh' in b[3] and b[4].startswith('Remove-Item -LiteralPath')
    a = pv.export_recipe(pv.APRIME, pv.APRIME_DIR, False)
    assert len(a) == 3 and a[2].startswith('Remove-Item -LiteralPath') and pv.APRIME in a[0]
    assert os.path.dirname(pv.B_DIR) == os.path.dirname(REPO)       # beside the checkouts: ..\pddlstream_lib is found


@needs_pinned
@pytest.mark.parametrize('commit,has_launcher', [(pv.THESIS, False), (pv.APRIME, True)])
def test_the_export_leaves_out_the_result_folders_and_keeps_the_code(commit, has_launcher):
    """The recipe's pathspecs, run for real on the commit (as a tar): the big folders are gone, the pipeline is there."""
    cmd = ['git', '-C', REPO, '-c', 'core.autocrlf=false', 'archive', '--format=tar', commit, '--', '.'] + \
          [f':(exclude){d}' for d in pv.EXPORT_LEAVE_OUT]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(out)) as t:
        members = [m for m in t.getmembers() if m.isfile()]
    names = {m.name for m in members}
    assert 'test_full_pipeline.py' in names and 'pddl' in {n.split('/')[0] for n in names}
    assert not [n for n in names if n.split('/')[0] in pv.EXPORT_LEAVE_OUT]
    assert sum(m.size for m in members) < 20 * 1024 * 1024
    # A' carries its launcher and the process guard; the thesis commit has neither (the recipe copies them in)
    assert ('run.ps1' in names) is has_launcher and ('tools/run_procs.sh' in names) is has_launcher


def test_wsl_path():
    assert pv.wsl_path('C:\\Users\\x\\git\\sb-eval') == '/mnt/c/Users/x/git/sb-eval'
    assert pv.wsl_path('/root/x') == '/root/x'


def test_wave2_lines_and_arm_ts_command():
    text = pv.render(2)
    assert 'BF#63 seeds 113 (1 cup), 102 (3 cups)' in text
    assert 'tampura -Seed 113,102 -Gen' in text and pv.APRIME in text
    for seed in pv.WAVE2_SEEDS:
        cmd = pv.t_command(seed)
        assert cmd.startswith("wsl -e bash -c '") and cmd.endswith("--vis 1'") and cmd.count("'") == 2
        assert f'--planner tampura_policy_timed --global-seed {seed} --save-dir $D/save --vis 1' in cmd
        assert f'find_dice_gen_s{seed}.json' in cmd and 'PYTHONPATH=' + pv.wsl_path(REPO) + ' ' in cmd
    # the command is the harness's own: the same driver, config and planner as episode_t
    with open(os.path.join(REPO, 'tools', '_bridge_campaign.py'), encoding='utf-8') as f:
        src = f.read()
    episode_t = src.split('def episode_t', 1)[1].split('\ndef ', 1)[0]
    for token in ("'run_tampura_timed.py'", "'--config', './env_configs/find_dice.yml'",
                  "'--planner', 'tampura_policy_timed'", "'--global-seed'", "'--save-dir'"):
        assert token in episode_t, token


@needs_pinned
def test_it_prints_only(monkeypatch):
    calls = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        calls.append(cmd)
        return real(cmd, *a, **k)
    monkeypatch.setattr(subprocess, 'run', spy)
    for wave in (1, 2):
        assert pv.render(wave)
    assert calls and all(c[0] == 'git' for c in calls)               # it reads git objects and nothing else
    with open(pv.__file__, encoding='utf-8') as f:
        src = f.read()
    for banned in ('os.system', 'Popen', 'startfile', 'webbrowser'):
        assert banned not in src
    with open(os.path.join(REPO, 'tools', 'p6_view.ps1'), encoding='utf-8') as f:
        wrapper = f.read()
    code = [ln for ln in wrapper.splitlines() if not ln.lstrip().startswith('#')]
    assert any('p6_view.py' in ln for ln in code)
    assert not any('wsl' in ln.lower() for ln in code)                # the wrapper's code lines never name wsl


@needs_pinned
def test_arms_belong_to_their_waves(capsys):
    with pytest.raises(SystemExit):
        pv.main(['--wave', '1', '--arm', 'T'])
    with pytest.raises(SystemExit):
        pv.main(['--wave', '2', '--arm', 'B'])
    assert pv.main(['--wave', '1', '--arm', 'B']) == 0
    out = capsys.readouterr().out
    assert '== arm B' in out and '== arm A' not in out
