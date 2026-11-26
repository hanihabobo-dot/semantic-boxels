"""run.sh, the Linux twin of run.ps1, through its own --dry-run (it prints
the command instead of running it, so nothing starts).

  no hard paths            every path of a command comes from the script's own
                           folder and from SB_PYTHON, SB_TAMPURA and SB_LOCK
  the three targets        tampura (plain and --gen), boxels, wumpus: the
                           pipeline command run.ps1 builds, flag for flag
                           (but for the page beside the window, which a GUI
                           run of boxels has from run.ps1 alone)
  both spellings           --seed 7 and -Seed 7, --dry-run and -DryRun
  a seed list              118,102 or "[118, 102]" or 118 102: one command each
  --draw                   the kinds of policy.DRAW_KINDS that run.ps1 takes;
                           dropped with a note for --headless and run boxels
  a flag it does not know  goes to the pipeline as it is
  wrong input              exit 2 and no command

Needs bash (skips without it, as on Windows outside WSL).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / 'run.sh'
BASH = shutil.which('bash') if os.name == 'posix' else None
pytestmark = pytest.mark.skipif(BASH is None, reason='needs bash on a posix system')

ENV = {'SB_PYTHON': '/opt/py/bin/python', 'SB_TAMPURA': '/opt/tw', 'SB_LOCK': '/tmp/test_run_sh.lock'}


def run(*words):
    return subprocess.run([BASH, str(RUN_SH), *words], capture_output=True, text=True, timeout=60,
                          env=dict(os.environ, **ENV))


def dry(*words):
    proc = run(*words, '--dry-run')
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip().splitlines(), proc.stderr


def test_the_file_is_lf_and_names_no_checkout_path():
    raw = RUN_SH.read_bytes()
    assert b'\r' not in raw
    assert b'/mnt/c/' not in raw and ('Hani' + 'Alassiri').encode() not in raw


def test_tampura_plain_uses_only_the_given_paths():
    lines, _ = dry('tampura', '--seed', '7')
    assert len(lines) == 1
    cmd = lines[0]
    assert cmd.startswith("flock /tmp/test_run_sh.lock bash -c 'export SB_RUN=1; cd /opt/tw/tampura_environments && ")
    assert (f'PYTHONPATH={ROOT}:{ROOT}/pddlstream_lib:/opt/tw/tampura:/opt/tw/tampura_environments '
            f'PYTHONHASHSEED=0 /opt/py/bin/python {ROOT}/tampura_bridge/run_bridge_on_finddice.py '
            f'--global-seed 7 --vis 1 --save-dir {ROOT}/archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/watch_s7_') in cmd
    assert '--draw' not in cmd and '--allow-g19-mismatch' not in cmd
    assert '/root/' not in cmd


def test_tampura_gen_list_headless():
    lines, _ = dry('tampura', '--seed', '[118, 102]', '--gen', '--headless')
    assert len(lines) == 2
    for seed, cmd in zip((118, 102), lines):
        assert f'find_dice_gen_s{seed}.json' in cmd
        assert f'BRIDGE_SCENE_MANIFEST={ROOT}/tampura_bridge/gen_scenes/find_dice/manifest.json' in cmd
        assert f'--global-seed {seed} --vis 0 ' in cmd and cmd.rstrip("'").endswith('--allow-g19-mismatch 1')
        assert 'ln -s /opt/tw/tampura_environments/env_configs' in cmd and "trap '\\''rm -rf " in cmd


@pytest.mark.parametrize('words', [('--seed', '118,102'), ('--seed', '118', '102'), ('-Seed', '118', '-Seed', '102')])
def test_seed_lists(words):
    lines, _ = dry('boxels', *words, '--headless')
    assert [re.search(r'--seed (\d+)', ln).group(1) for ln in lines] == ['118', '102']


def test_boxels_flags_in_both_spellings():
    a, _ = dry('boxels', '--seed', '3', '--headless', '--scene', 'stack', '--goal', 'stack', '--occluders', '0',
               '--look', 'boxel', '--eye', 'arm', '--squeeze', '0.5', '--screenshots', '--off')
    b = run('boxels', '-Seed', '3', '-Headless', '-Scene', 'stack', '-Goal', 'stack', '-Occluders', '0',
            '-Look', 'boxel', '-Eye', 'arm', '-Squeeze', '0.5', '-Screenshots', '-Off', '-DryRun')
    assert b.returncode == 0 and b.stdout.strip().splitlines() == a
    assert a[0].endswith(f"cd {ROOT} && PYTHONHASHSEED=0 /opt/py/bin/python test_full_pipeline.py --no-gui "
                         "--scene stack --seed 3 --goal stack --n-occluders 0 --m8 off --m9 off --m10 off "
                         "--pick-aperture-from-pose off --look boxel --eye arm --grip-squeeze-mm 0.5 "
                         "--save-screenshots on'")


def test_unknown_flags_and_args_reach_the_pipeline():
    lines, _ = dry('boxels', '--n-extra-distractors', '1', '--args', '--foo bar')
    assert lines[0].endswith("--n-occluders 2 --n-extra-distractors 1 --foo bar'")


def test_the_page_beside_the_window_is_run_ps1s_and_its_flag_goes_through():
    """run.ps1 asks for the page of our own beside the window in a GUI run of
    boxels and holds the two together (Windows only).  run.sh does not: its
    GUI run of boxels is the command without the page, and its head says so.
    The pipeline's own flag goes through as any flag run.sh does not know."""
    lines, _ = dry('boxels', '--seed', '3')
    assert '--gui-page' not in lines[0] and 'SB_GUI_PAGE_TOKEN' not in lines[0]
    assert lines[0].endswith("--scene random-pairs --seed 3 --goal holding --n-occluders 2'")
    lines, _ = dry('boxels', '--seed', '3', '--gui-page', 'on')
    assert lines[0].endswith("--n-occluders 2 --gui-page on'")
    head = RUN_SH.read_text().split('\n\n')[0]
    assert "One thing is run.ps1's alone" in head and '--gui-page on' in head
    ps1 = (ROOT / 'run.ps1').read_text(encoding='utf-8')
    assert "' --gui-page on'" in ps1 and '[switch]$NoPage' in ps1 and '[switch]$LoosePage' in ps1


def test_wumpus():
    lines, _ = dry('wumpus', '--seed', '3', '--size', '10', '--headless')
    assert lines[0].endswith(f"cd {ROOT} && PYTHONHASHSEED=0 /opt/py/bin/python {ROOT}/wumpus/run_wumpus.py --size 10 "
                             f"--seed 3 --vis 0 --save-dir {ROOT}/archive/tampura_bridge_plan_2026-10-25/tracks/wumpus/"
                             f"runs/{lines[0].rsplit('/', 1)[1]}")
    assert '/runs/wumpus_headless_n10_s3_' in lines[0]


def test_draw_kinds_are_the_drivers_and_run_ps1s():
    text = RUN_SH.read_text()
    mine = re.search(r"^DRAW_KINDS='([^']*)'", text, re.M).group(1).split()
    ps1 = re.search(r"^\$drawKinds = (.+)$", (ROOT / 'run.ps1').read_text(), re.M).group(1)
    assert mine == re.findall(r"'(\w+)'", ps1)
    lines, _ = dry('tampura', '--draw', 'Boxels', 'cameras')
    assert ' --draw boxels,cameras' in lines[0]
    lines, note = dry('tampura', '--draw', 'boxels', '--headless')
    assert '--draw' not in lines[0] and 'ignored with --headless' in note
    lines, note = dry('boxels', '--draw', 'boxels')
    assert '--draw' not in lines[0] and 'is for run tampura' in note


def test_audio_switches():
    lines, _ = dry('boxels', '--music', '--voice')
    assert "bash -c 'export SB_RUN=1; export SB_VOICE=on; export SB_AUDIO=on; cd " in lines[0]


@pytest.mark.parametrize('words, said', [
    (('nonsense',), "unknown target 'nonsense'"),
    (('boxels', '--seed', 'x'), '--seed takes a seed or a list'),
    (('boxels', '--eye', 'arm'), '--eye arm needs --look'),
    (('boxels', '--look', 'sideways'), '--look takes'),
    (('tampura', '--draw', 'boxles'), "not 'boxles'"),
    (('tampura', '--gen', '--seed', '5'), 'no generated scene for seed 5'),
    (('boxels', '--size', 'big'), '--size and --occluders take a whole number'),
])
def test_wrong_input_exits_2_without_a_command(words, said):
    proc = run(*words, '--dry-run')
    assert proc.returncode == 2 and proc.stdout == '' and said in proc.stderr, (proc.stdout, proc.stderr)


def test_a_flag_without_its_value_exits_2():
    proc = run('boxels', '--seed')
    assert proc.returncode == 2 and proc.stdout == '' and '--seed needs a value' in proc.stderr


def test_help_prints_the_header():
    proc = run('help')
    assert proc.returncode == 0 and proc.stdout.startswith('run.sh: the pipeline in one word on Linux')
    assert 'SB_PYTHON' in proc.stdout and '#!/bin/bash' not in proc.stdout
