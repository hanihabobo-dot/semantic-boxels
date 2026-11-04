# run: the pipeline in one word, flags optional (PowerShell).  Pointer
# scripts in ~/.local/bin (on the PATH) call this one, so `run` and `boxels`
# work from anywhere; from the repository root `.\run` works as well.
#   run                        the bridge episode on TAMPURA's find_dice, seed 0, in the GUI
#   run tampura -Seed 7        another seed
#   run tampura -Headless      no GUI: the console only (a diagnostic run, never scored;
#                              it goes on past a G19 scene mismatch like a GUI run)
#   run tampura -Seed 118 -Gen a scene from their own generator (BF#63's seeds 100 to 139)
#   run boxels                 our own random-pairs holding scene, seed 0, in the GUI, the
#                              same console and planner;  `boxels` alone is the same word
#   run boxels -Seed 3 -Headless
#   run boxels -Scene stack -Goal stack -Occluders 0
#   run tampura -Off           without M8-M10 (the old pipeline);  -Squeeze 1   a pick squeeze in mm
#   run tampura -Screenshots   also save the eye PNGs at every snapshot (debugging only; off since BF#50)
#   run tampura -Music         8-bit music and effects that follow the run (Windows plays them);
#                              -Sfx   the effects only;  -Voice   Windows' voice reads the narration too
#   run boxels -Args '--n-extra-distractors 1'   more pipeline flags, one quoted string, as is
#   run ps                     the pipeline processes alive in WSL;  run kill   ends every one of them
#   run help                   this text;  -DryRun prints the command instead of running it
# Never two pipeline runs at once (pddlstream temp/ race): it refuses while one is going.
# Closing the GUI window or pressing Ctrl-C ends the run for good.  A closed window
# leaves PyBullet's client busy-waiting in C and the process would outlive its
# terminal at full CPU (BF#51), so the run is a child process polled from here, its
# window is watched and tools/run_procs.sh ends what is left; Ctrl-C reaches the run
# as SIGINT, which the console makes lethal at once (wsl.exe holds the console in raw
# mode, so nothing on this side ever sees the key).
param(
    [Parameter(Position = 0)][string]$What = 'tampura',
    [int]$Seed = 0,
    [switch]$Headless,
    [switch]$Gen,
    [string]$Scene = 'random-pairs',
    [string]$Goal = 'holding',
    [int]$Occluders = 2,
    [switch]$Off,
    [double]$Squeeze = 0,
    [switch]$Screenshots,
    [switch]$Music,
    [switch]$Sfx,
    [switch]$Voice,
    [switch]$DryRun,
    [string]$Args = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$S = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
$PY = '/root/armO-venvA/bin/python'
# tools/run_procs.sh (list, kill, kill-mine), fed to bash through tr so CRLF does no harm.
$PROCS = "tr -d '\r' < $S/tools/run_procs.sh | bash -s --"

if ($What -in 'help', '-h', '--help', '/?', '?') {
    Get-Content $PSCommandPath | Select-Object -First 19 | ForEach-Object { $_ -replace '^# ?', '' }
    return
}
if ($What -in 'ps', 'status') {
    $alive = wsl -e bash -c "$PROCS list"
    if ($alive) { $alive } else { Write-Host 'run: no pipeline process is alive in WSL' -ForegroundColor DarkGray }
    return
}
if ($What -eq 'kill') {
    $gone = wsl -e bash -c "$PROCS kill"
    $rc = $LASTEXITCODE
    if ($gone) { $gone } else { Write-Host 'run: nothing to kill, no pipeline process is alive in WSL' -ForegroundColor DarkGray }
    exit $rc
}
if ($What -notin 'tampura', 'boxels') {
    Write-Host "run: unknown target '$What' (tampura or boxels; run help)" -ForegroundColor Yellow
    exit 2
}

$sw = if ($Off) { ' --m8 off --m9 off --m10 off --pick-aperture-from-pose off' } else { '' }
if ($Squeeze -gt 0) {
    $sw += ' --grip-squeeze-mm ' + $Squeeze.ToString([cultureinfo]::InvariantCulture)
}
if ($Screenshots) { $sw += ' --save-screenshots on' }
$extra = (@($Args) + @($Rest) | Where-Object { $_ -and $_ -ne '--' }) -join ' '
if ($extra) { $extra = ' ' + $extra }

# $mine: text found in this run's command line and no other's, for ending this run alone.
if ($What -eq 'tampura') {
    $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $vis = if ($Headless) { 0 } else { 1 }
    $kind = if ($Headless) { 'headless' } else { 'watch' }
    $g19 = if ($Headless) { ' --allow-g19-mismatch 1' } else { '' }
    $mine = "${kind}_s${Seed}_$stamp"
    $save = "$S/archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/$mine"
    $run = "PYTHONPATH=$S`:$S/pddlstream_lib`:`$TW/tampura`:`$TW/tampura_environments " +
           "PYTHONHASHSEED=0 $PY $S/tampura_bridge/run_bridge_on_finddice.py " +
           "--global-seed $Seed --vis $vis --save-dir $save$g19$sw$extra"
    if ($Gen) {
        # BF#63: their loader picks a random file of tampura_environments/
        # find_dice/problems under the cwd, so the run starts in a directory
        # holding only this scene (as tools/gen_scene_eval.py does); the
        # manifest pins it for G19.  The directory goes when the run ends
        # (run_procs.sh ends the python, never this bash, so the trap runs).
        $json = "tampura_bridge/gen_scenes/find_dice/find_dice_gen_s${Seed}.json"
        if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $json))) {
            Write-Host "run: no generated scene for seed $Seed (BF#63's are 100 to 139)" -ForegroundColor Yellow
            exit 2
        }
        $D = "/root/run_gen_$mine"
        $cmd = "TW=/root/tampura-work; trap 'rm -rf $D' EXIT; " +
               "mkdir -p $D/tampura_environments/find_dice/problems && " +
               "cp $S/$json $D/tampura_environments/find_dice/problems/ && " +
               "ln -s `$TW/tampura_environments/env_configs $D/env_configs && cd $D && " +
               "BRIDGE_SCENE_MANIFEST=$S/tampura_bridge/gen_scenes/find_dice/manifest.json $run"
    } else {
        $cmd = "TW=/root/tampura-work; cd `$TW/tampura_environments && $run"
    }
} else {
    $nogui = if ($Headless) { ' --no-gui' } else { '' }
    $mine = "test_full_pipeline.py$nogui --scene $Scene --seed $Seed --goal $Goal --n-occluders $Occluders"
    $cmd = "cd $S && PYTHONHASHSEED=0 $PY $mine$sw$extra"
}

$audio = if ($Music) { 'on' } elseif ($Sfx) { 'sfx' } else { '' }
if ($audio) { $cmd = "export SB_AUDIO=$audio; " + $cmd }
if ($Voice) { $cmd = 'export SB_VOICE=on; ' + $cmd }
if ($DryRun) {
    Write-Output $cmd
    return
}
$busy = wsl -e bash -c "$PROCS list"
if ($busy) {
    Write-Host "run: another pipeline run is going, never two at once (pddlstream temp/ race):" -ForegroundColor Yellow
    $busy | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    Write-Host "  a ghost (its window closed, its terminal gone)?   run kill   ends them all" -ForegroundColor Yellow
    exit 2
}

# The run is a child process polled from here, not a blocking call, so the
# GUI window can be watched meanwhile: WSLg shows it to Windows as an
# msrdc.exe window titled 'Bullet Physics ...'; once seen and then gone
# while the run goes on, the run is ended (BF#51).  Ctrl-C goes to wsl.exe,
# which holds the console in raw mode and forwards it to the run as SIGINT;
# the console (console_ui) lets SIGINT end the process at the kernel level,
# so a stuck run dies of it too and this script just sees the exit.
$psi = [System.Diagnostics.ProcessStartInfo]::new('wsl.exe')
foreach ($a in '-e', 'bash', '-lc', $cmd) { $psi.ArgumentList.Add($a) }
$psi.UseShellExecute = $false
$t0 = Get-Date
$p = [System.Diagnostics.Process]::Start($psi)
$seen = $false
$ended = ''
try {
    while (-not $p.HasExited) {
        Start-Sleep -Milliseconds 700
        if ($Headless -or $ended) { continue }
        $open = @(Get-Process -Name msrdc -ErrorAction SilentlyContinue |
                  Where-Object { $_.MainWindowTitle -like '*Bullet Physics*' }).Count
        if ($open -gt 0) { $seen = $true }
        elseif ($seen) {
            # A run that is ending closes its own window: give it a moment.
            if (-not $p.WaitForExit(3000)) {
                $ended = 'the window was closed'
                $null = wsl -e bash -c "$PROCS kill-mine '$mine' $([int]((Get-Date) - $t0).TotalSeconds + 60)"
            }
        }
    }
} finally {
    if (-not $p.HasExited -and -not $p.WaitForExit(3000)) {
        # This script was stopped while the run goes on (a closed host, a
        # Stop-Process): the run gets 3 s to end by itself, then it is ended here.
        $ended = 'the launcher was stopped'
        $null = wsl -e bash -c "$PROCS kill-mine '$mine' $([int]((Get-Date) - $t0).TotalSeconds + 60)"
        $null = $p.WaitForExit(5000)
    }
    # The console hides the cursor while a step runs; show it whatever happened.
    [Console]::Out.Write("`e[?25h")
    if ($ended) {
        [Console]::Out.WriteLine("run: $ended, so the run was ended from here; nothing of it is left in WSL")
    } elseif ($p.HasExited -and $p.ExitCode -eq 130) {
        [Console]::Out.WriteLine('run: interrupted (Ctrl-C ends the run at once; its files stay as they were)')
    }
}
exit $p.ExitCode
