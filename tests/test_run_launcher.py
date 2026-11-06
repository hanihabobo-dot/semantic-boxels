"""TB-16: run.ps1 runs the code of the checkout it lives in.

run.ps1 builds every WSL command from $S (the bridge driver, PYTHONPATH,
the -Gen scene copy, the save directory, tools/run_procs.sh), while its
-Gen scene check and the record it reads after a run use $PSScriptRoot.
Until TB-16, $S was the main checkout's path written out, so a worktree's
own run.ps1 ran the main checkout's code and saved into its archive.  Now
$S is $PSScriptRoot as a WSL path, which for the main checkout (Hani's
`run`, through ~/.local/bin/run.ps1) is the same string as before.

The first test needs nothing.  The other two share one PowerShell 7 call
through WSL's interop (pwsh.exe, with -NoProfile) and skip without it.
"""
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_PS1 = ROOT / 'run.ps1'
# $PSScriptRoot -> $S: the main checkout keeps its old string.
CASES = [(r'C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels',
          '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'),
         (r'C:\Users\HaniAlassiriAlhabbou\git\sb-fixes',
          '/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-fixes'),
         (r'D:\work\sb', '/mnt/d/work/sb')]


def _s_line() -> str:
    lines = [ln for ln in RUN_PS1.read_text().splitlines()
             if re.match(r'^\$S\s*=', ln)]
    assert len(lines) == 1, lines
    return lines[0]


def test_s_is_derived_from_the_scripts_own_folder():
    line = _s_line()
    assert '$PSScriptRoot' in line
    assert '/mnt/c/Users' not in line, line


# run.ps1 runs from a Windows folder; a checkout outside /mnt/<drive>
# (a copy under /root, a cluster snapshot) has no Windows path to give it.
_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason='needs pwsh.exe through WSL interop and a checkout '
                          'on a Windows drive')


@pytest.fixture(scope='module')
def launcher_output():
    """One pwsh.exe call: two dry runs of this checkout's run.ps1, then the
    $S expression evaluated for each of CASES (pwsh.exe starts slowly)."""
    win = subprocess.run(['wslpath', '-w', str(RUN_PS1)], capture_output=True,
                         text=True, check=True).stdout.strip()
    rhs = _s_line().split('=', 1)[1].strip()
    script = '; '.join(
        [f"& '{win}' tampura -Seed 118 -Gen -Headless -DryRun", "'@@'",
         f"& '{win}' boxels -Seed 3 -Headless -DryRun", "'@@'"]
        + [rhs.replace('$PSScriptRoot', f"'{w}'") for w, _ in CASES])
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command',
                           script], capture_output=True, text=True,
                          timeout=180, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    tampura, boxels, paths = proc.stdout.split('@@')
    return {'tampura': tampura, 'boxels': boxels, 'paths': paths.split()}


@needs_pwsh
def test_the_main_checkout_keeps_its_path_and_a_worktree_gets_its_own(
        launcher_output):
    assert launcher_output['paths'] == [wsl for _, wsl in CASES]


@needs_pwsh
def test_a_dry_run_names_this_checkout_and_no_other(launcher_output):
    here = str(ROOT)
    for kind in ('tampura', 'boxels'):
        out = launcher_output[kind]
        assert here in out, out
        named = set(re.findall(r'/mnt/[a-z]/Users/[^/\s]+/git/[^/\s:]+', out))
        assert named == {here}, (kind, named)
