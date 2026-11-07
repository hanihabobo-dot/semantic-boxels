"""BF#68 (run tampura -Draw cameras): tools/camera_view.ps1 is a Windows Forms
script that a run starts hidden in the background, where a mistake shows as no
window at all.  Most checks here need no window: the script parses, the C#
block that carries its Win32 calls compiles (a missing `using System;` once
left [ViewDpi] undefined, so the script lost DPI awareness and the call that
makes its window visible), and the pieces that matter are in its text.  What
only a real window shows (visible after a hidden start, the captions, the close
after the run ends) was checked by hand and with real runs
(tracks/draw/evidence/cameras in the main checkout);
test_the_window_is_visible_after_a_hidden_start checks the first of them again
when SB_WINDOW_TESTS=1 is set: it opens a window on the desktop for a few
seconds.

pwsh.exe through WSL's interop, with -NoProfile; skipped without it, like
tests/test_run_draw_launcher.py (pytest -rs says which skipped, and why)."""
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / 'tools' / 'camera_view.ps1'

_IN_WSL = 'microsoft' in platform.uname().release.lower()
_ON_DRIVE = re.match(r'^/mnt/[a-z]/', str(ROOT)) is not None
_PWSH = shutil.which('pwsh.exe') if _IN_WSL and _ON_DRIVE else None
needs_pwsh = pytest.mark.skipif(
    _PWSH is None, reason='needs pwsh.exe through WSL interop and a checkout '
                          'on a Windows drive')


def _pwsh(script):
    proc = subprocess.run([_PWSH, '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    return proc.returncode, proc.stdout + proc.stderr


def _win(path):
    return subprocess.run(['wslpath', '-w', str(path)], capture_output=True,
                          text=True, check=True).stdout.strip()


@needs_pwsh
def test_the_viewer_script_parses():
    code, out = _pwsh(
        f"$e = $null; $t = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{_win(VIEWER)}', [ref]$t, [ref]$e); "
        f"\"errors=$($e.Count)\"; $e | ForEach-Object {{ $_.Message }}")
    assert code == 0 and 'errors=0' in out, out


@needs_pwsh
def test_its_win32_block_compiles_and_carries_the_calls_the_window_needs():
    # the first Add-Type block of the script, compiled in a fresh pwsh (no window is made)
    code, out = _pwsh(
        f"$src = Get-Content -Raw -LiteralPath '{_win(VIEWER)}'; "
        "$m = [regex]::Match($src, \"(?s)Add-Type -TypeDefinition @'\\r?\\n(.*?)\\r?\\n'@\"); "
        "if (-not $m.Success) { 'no block'; exit 3 }; "
        "Add-Type -TypeDefinition $m.Groups[1].Value; "
        "'methods=' + (([ViewDpi].GetMethods() | Where-Object { $_.IsStatic } | ForEach-Object { $_.Name } | Sort-Object) -join ',')")
    assert code == 0, out
    for name in ('SetProcessDPIAware', 'GetDpiForSystem', 'ShowWindow', 'IsWindowVisible'):
        assert name in out, out


def test_the_script_shows_its_window_while_a_hidden_start_leaves_it_invisible():
    """run.ps1 starts it with -WindowStyle Hidden; Windows hands that state to
    the first ShowWindow call of the process (which may be the form's own), so
    while the form is not visible the script spends one throwaway call
    (SW_SHOWDEFAULT) and then shows it without activation (SW_SHOWNOACTIVATE),
    on every tick for ten seconds."""
    text = VIEWER.read_text(encoding='utf-8')
    block = re.search(r'if \(-not \$script:visible -and \$script:shows -lt (\d+)\) \{(.*?)\n    \}',
                      text, re.S)
    assert block, 'the show-while-invisible block is gone'
    assert int(block.group(1)) * 200 >= 8000            # 200 ms ticks: at least 8 s of tries
    body = block.group(2)
    assert 'IsWindowVisible($h)' in body and '$script:visible = $true' in body
    assert re.findall(r'ShowWindow\(\$h, (\d+)\)', body) == ['10', '4']
    # the script's only other ShowWindow users: none
    assert len(re.findall(r'\]::ShowWindow\(', text)) == 2


def test_the_run_is_watched_through_one_process_object_and_the_countdown_is_latched():
    text = VIEWER.read_text(encoding='utf-8')
    # a freed PID can go to another process within seconds; the object's handle pins it
    assert 'GetProcessById($WatchPid)' in text and 'Get-Process -Id' not in text
    # once the run is seen gone the countdown continues whatever a later lookup says
    assert re.search(r'\$null -ne \$script:runGone -or \$script:watch\.HasExited', text)


def test_the_viewer_only_reads_the_folder():
    text = VIEWER.read_text(encoding='utf-8')
    for writer in ('New-Item', 'Set-Content', 'Add-Content', 'Out-File', 'Remove-Item',
                   'Copy-Item', 'Move-Item', 'Rename-Item', 'WriteAll', 'FileMode]::Create',
                   'FileAccess]::Write'):
        assert writer not in text, writer
    # it reads with a share mode that lets the run replace the file meanwhile
    assert 'FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete' in text


_PROBE = r"""
Add-Type -TypeDefinition @'
using System; using System.Text; using System.Runtime.InteropServices;
public static class WinProbe {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  public static string State(uint pid, string prefix) {
    string state = "none";
    EnumWindows((h, l) => {
      uint p; GetWindowThreadProcessId(h, out p);
      if (p != pid) return true;
      var s = new StringBuilder(512); GetWindowText(h, s, 512);
      if (s.ToString().StartsWith(prefix)) { state = IsWindowVisible(h) ? "visible" : "hidden"; return false; }
      return true; }, IntPtr.Zero);
    return state;
  }
}
'@
$viewer = '__VIEWER__'
$folder = '__FOLDER__'
$argv = @('-NoProfile', '-File', ('"' + $viewer + '"'), '-Dir', ('"' + $folder + '"'))
$proc = Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList $argv -WindowStyle Hidden -PassThru
try {
    $state = 'none'
    for ($i = 0; $i -lt 60 -and $state -ne 'visible'; $i++) {
        Start-Sleep -Milliseconds 500
        $state = [WinProbe]::State([uint32]$proc.Id, 'Our cameras')
    }
    "window=$state"
} finally {
    Stop-Process -Id $proc.Id -ErrorAction SilentlyContinue
}
"""


@needs_pwsh
@pytest.mark.skipif(os.environ.get('SB_WINDOW_TESTS') != '1',
                    reason='opens a window on the desktop for a few seconds; '
                           'set SB_WINDOW_TESTS=1')
def test_the_window_is_visible_after_a_hidden_start(tmp_path):
    """The real thing: the viewer started the way run.ps1 starts it
    (-WindowStyle Hidden), its form checked with IsWindowVisible; then it is
    stopped (its own process id)."""
    probe = tmp_path / 'probe.ps1'
    probe.write_text(_PROBE.replace('__VIEWER__', _win(VIEWER))
                     .replace('__FOLDER__', _win(tmp_path / 'cameras')), encoding='utf-8')
    code, out = _pwsh(f"& '{_win(probe)}'")
    assert code == 0 and 'window=visible' in out, out
