# run: the pipeline in one word, flags optional (PowerShell).  Pointer
# scripts in ~/.local/bin (on the PATH) call this one, so `run` and `boxels`
# work from anywhere; from the repository root `.\run` works as well.
#   run                        the bridge episode on TAMPURA's find_dice, seed 0, in the GUI
#   run tampura -Seed 7        another seed
#   run tampura -Seed [118, 102, 103] -Gen   several seeds (also 118,102,103 or 118 102 103),
#                              one run after another, then a line for each; closing a GUI
#                              window goes on with the next seed, Ctrl-C stops the list
#   run tampura -Headless      no GUI: the console only (a diagnostic run, never scored;
#                              it goes on past a G19 scene mismatch like a GUI run)
#   run tampura -Seed 118 -Gen a scene from their own generator (seeds 100 to 339 are committed)
#   run boxels                 our own random-pairs holding scene, seed 0, in the GUI, the
#                              same console and planner;  `boxels` alone is the same word
#   run boxels -Seed 3 -Headless
#   run boxels -NoPage         PyBullet's own window as it was (its panels and three camera panes) and no page;
#                              without it a window run of boxels shows the simulator alone in its window and a
#                              page held against it, the two moving as one (the console's drawing and lines, the
#                              robot camera's three pictures; gui_page.py);  -LoosePage   the page as its own window
#   run boxels -Scene stack -Goal stack -Occluders 0
#   run tampura -Off           without M8-M10 (the old pipeline);  -Squeeze 1   a pick squeeze in mm
#   run boxels -Look boxel     one look action from a free-space boxel instead of sense and observe (path 9)
#   run boxels -Look centred   the object-centred look instead (no boxel model in the look; path 9's reference)
#   run boxels -Look boxel -Eye arm   every image from the arm camera (path 9; run tampura takes it too)
#   run tampura -Screenshots   also save the eye PNGs at every snapshot (debugging only; off since BF#50)
#   run tampura -Draw boxels   the GUI also draws the boxels (lines and labels, changing as the registry
#                              changes); adds nothing to the world and nothing to a camera image; with
#                              -Headless it is ignored (nothing is drawn); run boxels draws them as is
#   run tampura -Draw cameras  its own window (flush right; move it) with what each of our cameras (eye,
#                              wrist) saw at its latest render (image, depth, segmentation); the GUI also
#                              draws each view volume; the world is not touched; -Draw boxels,cameras: both
#   run tampura -Music         8-bit music and effects that follow the run (Windows plays them);
#                              -Sfx   the effects only;  -Voice   Windows' voice reads the narration too
#   run boxels -Args '--n-extra-distractors 1'   more pipeline flags, one quoted string, as is
#   run wumpus -Seed 3         the 3-D Wumpus world (path 4), explore test controller, GUI;  -Size 10 (default 5),
#                              -Headless;  [3, 4] runs a list as above
#   run ps                     the pipeline processes alive in WSL;  run kill   ends the ones run started
#   run help                   this text;  -DryRun prints the command instead of running it
# Every run takes the pipeline lock (rule 7: one episode at a time, pddlstream temp/ race): it
# waits while a track's episode or another run holds it, and says who; it refuses while
# another run it started is still alive.
# Closing the GUI window or pressing Ctrl-C ends the run for good.  A closed window
# leaves PyBullet's client busy-waiting in C and the process would outlive its
# terminal at full CPU (BF#51), so the run is a child process polled from here, its
# window is watched and tools/run_procs.sh ends what is left; Ctrl-C reaches the run
# as SIGINT, which the console makes lethal at once (wsl.exe holds the console in raw
# mode, so nothing on this side ever sees the key).
param(
    [Parameter(Position = 0)][string]$What = 'tampura',
    [string[]]$Seed = '0',
    [switch]$Headless,
    [int]$Size = 5,
    [switch]$Gen,
    [string]$Scene = 'random-pairs',
    [string]$Goal = 'holding',
    [int]$Occluders = 2,
    [switch]$Off,
    [ValidateSet('', 'boxel', 'centred', 'on')][string]$Look = '',
    [ValidateSet('', 'fixed', 'arm')][string]$Eye = '',
    [double]$Squeeze = 0,
    [switch]$Screenshots,
    [string[]]$Draw = @(),
    [switch]$NoPage,
    [switch]$LoosePage,
    [switch]$Music,
    [switch]$Sfx,
    [switch]$Voice,
    # -D and -Dr meant -DryRun before -Draw existed; the aliases keep them so
    [Alias('D', 'Dr')][switch]$DryRun,
    [string]$Args = '',
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
# The checkout this script lives in, as a WSL path (TB-16): `run` (the
# pointer in ~/.local/bin) calls the main checkout's copy, and a worktree's
# own run.ps1 runs that worktree's code, so the command, the save directory
# and the record read after the run all name the same checkout.
$S = '/mnt/' + $PSScriptRoot.Substring(0, 1).ToLowerInvariant() + ($PSScriptRoot.Substring(2) -replace '\\', '/')
$PY = '/root/armO-venvA/bin/python'
# tools/run_procs.sh (list, kill, kill-mine), fed to bash through tr so CRLF does no harm.
$PROCS = "tr -d '\r' < $S/tools/run_procs.sh | bash -s --"

if ($What -in 'help', '-h', '--help', '/?', '?') {
    Get-Content $PSCommandPath | Select-Object -First 37 | ForEach-Object { $_ -replace '^# ?', '' }
    return
}
if ($What -in 'ps', 'status') {
    $alive = wsl -e bash -c "$PROCS ps"
    if ($alive) { $alive } else { Write-Host 'run: no pipeline process is alive in WSL' -ForegroundColor DarkGray }
    return
}
if ($What -eq 'kill') {
    $gone = wsl -e bash -c "$PROCS kill"
    $rc = $LASTEXITCODE
    if ($gone) { $gone } else { Write-Host 'run: nothing to kill, no pipeline process is alive in WSL' -ForegroundColor DarkGray }
    exit $rc
}
if ($What -notin 'tampura', 'boxels', 'wumpus') {
    Write-Host "run: unknown target '$What' (tampura, boxels or wumpus; run help)" -ForegroundColor Yellow
    exit 2
}

# -Seed takes one seed or a list, run one after another: 7, 118,102 or
# [118, 102, 103] as typed (PowerShell hands the brackets over as text).
# Seeds with only spaces between them land in $Rest ahead of any pipeline
# flag (a flag's value never comes first) and join the list from there.
while ($Rest.Count -gt 0 -and "$($Rest[0])" -match '^[\[\]\d,\s]+$') {
    $Seed += $Rest[0]
    $Rest = @($Rest | Select-Object -Skip 1)
}
# -Draw (BF#68) takes the same: kinds with only spaces between them
# (-Draw boxels cameras) land in $Rest and join from there, when they are
# known kinds.  tests/test_run_draw_launcher.py pins this list to policy.py's.
$drawKinds = 'boxels', 'cameras'
$kindWords = '^(' + ($drawKinds -join '|') + ')([\s,]+(' + ($drawKinds -join '|') + '))*$'
while ($Draw.Count -gt 0 -and $Rest.Count -gt 0 -and "$($Rest[0])" -match $kindWords) {
    $Draw += $Rest[0]
    $Rest = @($Rest | Select-Object -Skip 1)
}
$seeds = @(($Seed -join ',') -split '[\s,\[\]]+' | Where-Object { $_ })
if ($seeds.Count -eq 0 -or @($seeds | Where-Object { $_ -notmatch '^\d+$' }).Count -gt 0) {
    Write-Host "run: -Seed takes a seed or a list (7, 118,102 or [118, 102, 103]), not '$($Seed -join ' ')'" -ForegroundColor Yellow
    exit 2
}
$seeds = @($seeds | ForEach-Object { [int]$_ })
if ($What -eq 'tampura' -and $Gen) {
    $missing = @($seeds | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "tampura_bridge/gen_scenes/find_dice/find_dice_gen_s$_.json")) })
    if ($missing.Count -gt 0) {
        $word = if ($missing.Count -gt 1) { 'seeds' } else { 'seed' }
        Write-Host "run: no generated scene for $word $($missing -join ', ') (committed are 100 to 339)" -ForegroundColor Yellow
        exit 2
    }
}

$sw = if ($Off) { ' --m8 off --m9 off --m10 off --pick-aperture-from-pose off' } else { '' }
if ($Look) { $sw += " --look $Look" }
# -Eye arm (path 9): every image from the arm camera.  It needs a look (sense is
# the fixed camera's action); run boxels passes it to the pipeline, run tampura
# to the bridge's driver.
if ($Eye -eq 'arm') {
    if (-not $Look) {
        Write-Host "run: -Eye arm needs -Look boxel or -Look centred (sense is the fixed camera's action)" -ForegroundColor Yellow
        exit 2
    }
    $sw += ' --eye arm'
}
if ($Squeeze -gt 0) {
    $sw += ' --grip-squeeze-mm ' + $Squeeze.ToString([cultureinfo]::InvariantCulture)
}
if ($Screenshots) { $sw += ' --save-screenshots on' }
# -Draw (BF#68): what the GUI draws besides the scene, one word or a comma
# list, any case (kinds: $drawKinds above).  The bridge driver takes it as --draw;
# it draws nothing without the GUI and run boxels has its own display.
$draws = @($Draw | ForEach-Object { $_ -split '[\s,]+' } | Where-Object { $_ } |
           ForEach-Object { $_.ToLowerInvariant() } | Select-Object -Unique)
$badDraw = @($draws | Where-Object { $_ -notin $drawKinds })
if ($badDraw.Count -gt 0) {
    Write-Host "run: -Draw takes $($drawKinds -join ', ') (several: a comma list), not '$($badDraw -join ' ')'" -ForegroundColor Yellow
    exit 2
}
if ($draws.Count -gt 0 -and $What -ne 'tampura') {
    $own = if ($What -eq 'wumpus') { 'run wumpus paints what the robot knows' } else { 'run boxels has its own display' }
    Write-Host "run: -Draw ($($drawKinds -join ', ')) is for run tampura; $own and ignores it" -ForegroundColor Yellow
    $draws = @()
} elseif ($draws.Count -gt 0 -and $Headless) {
    Write-Host "run: -Draw is ignored with -Headless (there is no GUI), nothing is drawn" -ForegroundColor Yellow
    $draws = @()
}
if ($draws.Count -gt 0) { $sw += ' --draw ' + ($draws -join ',') }
# -NoPage and -LoosePage are about the page beside our own window, which only a window run of
# boxels has.
if (($NoPage -or $LoosePage) -and ($What -ne 'boxels' -or $Headless)) {
    $named = (@('-NoPage', '-LoosePage') | Where-Object { ($_ -eq '-NoPage' -and $NoPage) -or ($_ -eq '-LoosePage' -and $LoosePage) }) -join ' and '
    $why = if ($What -ne 'boxels') { "run $What has none" } else { 'this run has no window' }
    Write-Host "run: $named ignored: only a window run of boxels has the page beside its window ($why)" -ForegroundColor Yellow
}
$extra = (@($Args) + @($Rest) | Where-Object { $_ -and $_ -ne '--' }) -join ' '
if ($extra) { $extra = ' ' + $extra }
$audio = if ($Music) { 'on' } elseif ($Sfx) { 'sfx' } else { '' }

# One seed's run, built when it starts (its folder is stamped with that time).
# Mine: text found in this run's command line and no other's, for ending this
# run alone; Record: its episode record (tampura only).  (Not $s: PowerShell
# names ignore case, and $S is the checkout.)
function New-Run([int]$seedNo) {
    $record = $null
    $cameras = $null
    $page = $null
    if ($What -eq 'tampura') {
        $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
        $vis = if ($Headless) { 0 } else { 1 }
        $kind = if ($Headless) { 'headless' } else { 'watch' }
        $g19 = if ($Headless) { ' --allow-g19-mismatch 1' } else { '' }
        $mine = "${kind}_s${seedNo}_$stamp"
        $save = "$S/archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/$mine"
        $record = Join-Path $PSScriptRoot "archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/$mine/bridge_episode.json"
        # -Draw cameras: the folder the run's pictures go to, which the camera window reads.
        if ('cameras' -in $draws) {
            $cameras = Join-Path $PSScriptRoot "archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/$mine/cameras"
        }
        $run = "PYTHONPATH=$S`:$S/pddlstream_lib`:`$TW/tampura`:`$TW/tampura_environments " +
               "PYTHONHASHSEED=0 $PY $S/tampura_bridge/run_bridge_on_finddice.py " +
               "--global-seed $seedNo --vis $vis --save-dir $save$g19$sw$extra"
        if ($Gen) {
            # BF#63: their loader picks a random file of tampura_environments/
            # find_dice/problems under the cwd, so the run starts in a directory
            # holding only this scene (as tools/gen_scene_eval.py does); the
            # manifest pins it for G19.  The directory goes when the run ends
            # (run_procs.sh ends the python, never this bash, so the trap runs).
            $json = "tampura_bridge/gen_scenes/find_dice/find_dice_gen_s${seedNo}.json"
            $D = "/root/run_gen_$mine"
            $cmd = "TW=/root/tampura-work; trap 'rm -rf $D' EXIT; " +
                   "mkdir -p $D/tampura_environments/find_dice/problems && " +
                   "cp $S/$json $D/tampura_environments/find_dice/problems/ && " +
                   "ln -s `$TW/tampura_environments/env_configs $D/env_configs && cd $D && " +
                   "BRIDGE_SCENE_MANIFEST=$S/tampura_bridge/gen_scenes/find_dice/manifest.json $run"
        } else {
            $cmd = "TW=/root/tampura-work; cd `$TW/tampura_environments && $run"
        }
    } elseif ($What -eq 'wumpus') {
        $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
        $vis = if ($Headless) { 0 } else { 1 }
        $kind = if ($Headless) { 'headless' } else { 'watch' }
        $mine = "wumpus_${kind}_n${Size}_s${seedNo}_$stamp"
        $save = "$S/archive/tampura_bridge_plan_2026-10-25/tracks/wumpus/runs/$mine"
        $record = Join-Path $PSScriptRoot "archive/tampura_bridge_plan_2026-10-25/tracks/wumpus/runs/$mine/episode.json"
        $cmd = "cd $S && PYTHONHASHSEED=0 $PY $S/wumpus/run_wumpus.py --size $Size --seed $seedNo --vis $vis --save-dir $save$extra"
    } else {
        $nogui = if ($Headless) { ' --no-gui' } else { '' }
        $mine = "test_full_pipeline.py$nogui --scene $Scene --seed $seedNo --goal $Goal --n-occluders $Occluders"
        # The page beside our own window (gui_page.py; Hani, 2026-11-22): a window run asks
        # for it unless -NoPage.  $page is a word of this run alone: the page's server gives
        # it back, so that the page opened below is this run's and no other's.
        $pageFlag = ''
        if (-not $Headless -and -not $NoPage) {
            $page = [guid]::NewGuid().ToString('N').Substring(0, 12)
            $pageFlag = ' --gui-page on'
        }
        $cmd = "cd $S && PYTHONHASHSEED=0 $PY $mine$pageFlag$sw$extra"
    }
    if ($page) { $cmd = "export SB_GUI_PAGE_TOKEN=$page; " + $cmd }
    if ($audio) { $cmd = "export SB_AUDIO=$audio; " + $cmd }
    if ($Voice) { $cmd = 'export SB_VOICE=on; ' + $cmd }
    # TB-17 and rule 7: the run holds the pipeline lock, so a track's episode
    # in another checkout and this run never overlap.  A batch takes the lock
    # one episode at a time, so the run waits at most for the episode going
    # now (a waiter blocked in the kernel takes the lock before the batch's
    # next episode can ask for it); while it waits, run ps says who holds it.  The
    # flock's command line keeps the run's own (run ps, run kill, kill-mine
    # find it by that).  RUN_PROCS_LOCK is a test's own lock.  No double
    # quotes: the command reaches bash through wsl.exe's command line.
    $q = $cmd.Replace("'", "'\''")
    $cmd = "L=`${RUN_PROCS_LOCK:-/root/sb_pipeline.lock}; flock -n `$L true || " +
           "{ echo run: waiting for the pipeline lock `$L, rule 7, one episode at a time. Now:; $PROCS ps; }; " +
           "exec flock `$L bash -c '$q'"
    # TB-17: the run and its children carry SB_RUN, so run kill ends what
    # run started and leaves a track's episode, probe or planner alone.
    $cmd = 'export SB_RUN=1; ' + $cmd
    [pscustomobject]@{ Seed = $seedNo; Cmd = $cmd; Mine = $mine; Record = $record; Cameras = $cameras; Page = $page }
}

# The page beside our own window (gui_page.py).  Its server runs inside the run, in WSL, on
# 127.0.0.1 (WSL hands that port to Windows' localhost), on $pagePorts' first free port.
# Find-Page: the address of the page whose server gives this run's word back, or nothing yet.
$pagePorts = 8765..8774
function Find-Page([string]$word) {
    foreach ($port in $pagePorts) {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        try {
            if (-not $tcp.ConnectAsync('127.0.0.1', $port).Wait(150)) { continue }
        } catch { continue } finally { $tcp.Dispose() }
        try {
            $state = Invoke-RestMethod -Uri "http://127.0.0.1:$port/state" -TimeoutSec 2 -NoProxy
            if ($state.run.token -eq $word) { return "http://localhost:$port/" }
        } catch { }
    }
    return $null
}
# Test-PageShown: is a window open whose title is the page's ($whole), or starts with it (a
# browser window with tabs that shows the page adds its own name).  All windows are looked
# through, as the page's holder does it (tools/page_dock.cs, compiled here when first asked):
# a browser is one process with many windows, and a process's main window alone would miss a
# page window that stands behind another window of the same browser.
function Test-PageShown([string]$title, [bool]$whole) {
    try {
        if (-not ('PageDock' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'tools/page_dock.cs') -IgnoreWarnings }
        [PageDock]::WholeTitle = $whole
        return ([PageDock]::FindPage($title, '') -ne 0)
    } catch { return $false }
}
# Open-Page: a browser window on the page, Edge without its address bar where Edge is found,
# else the default browser.  A page left open by an earlier run on the same port takes up
# the new run by itself (it keeps asking its address), so no second window is opened for it.
# $own: only a window of the page's own counts as open (the holder never takes a browser
# window with tabs); without Edge there is no such window, and a tab that shows the page does.
function Open-Page([string]$url, [bool]$own) {
    $title = 'Semantic Boxels (page ' + ([uri]$url).Port + ')'
    if (Test-PageShown $title $own) { return }
    try {
        $edge = (Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction Stop).'(default)'
        Start-Process -FilePath $edge -ArgumentList "--app=$url", '--window-size=420,640'
    } catch {
        if ($own -and (Test-PageShown $title $false)) { return }
        try { Start-Process $url } catch {
            Write-Host "run: the page did not open ($($_.Exception.Message)); it is at $url" -ForegroundColor Yellow
        }
    }
}

if ($DryRun) {
    foreach ($one in $seeds) { Write-Output (New-Run $one).Cmd }
    return
}

# Each run is a child process polled from here, not a blocking call, so the
# GUI window can be watched meanwhile: WSLg shows it to Windows as an
# msrdc.exe window titled 'Bullet Physics ...'; once seen and then gone
# while the run goes on, the run is ended (BF#51).  Ctrl-C goes to wsl.exe,
# which holds the console in raw mode and forwards it to the run as SIGINT;
# the console (console_ui) lets SIGINT end the process at the kernel level,
# so a stuck run dies of it too and this script just sees the exit (130).
# In a list, a closed window ends that seed's run and the next one starts;
# Ctrl-C stops the list.
$many = $seeds.Count -gt 1
$done = @()
$code = 0
$viewer = $null     # -Draw cameras: the camera window of the seed before
for ($i = 0; $i -lt $seeds.Count; $i++) {
    # TB-17 (Go, 2026-11-08): only a run that run started refuses a new one;
    # a track's episode does not (the pipeline lock keeps the two apart, and
    # the new run says who holds it while it waits).
    $busy = wsl -e bash -c "$PROCS busy"
    if ($busy) {
        Write-Host "run: a run started by run is still going, never two at once:" -ForegroundColor Yellow
        $busy | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        Write-Host "  a ghost (its window closed, its terminal gone)?   run kill   ends the ones run started" -ForegroundColor Yellow
        $code = 2
        break
    }
    $r = New-Run $seeds[$i]
    if ($many) { Write-Host "run: seed $($r.Seed), $($i + 1) of $($seeds.Count)" -ForegroundColor Cyan }
    $psi = [System.Diagnostics.ProcessStartInfo]::new('wsl.exe')
    foreach ($a in '-e', 'bash', '-lc', $r.Cmd) { $psi.ArgumentList.Add($a) }
    $psi.UseShellExecute = $false
    $t0 = Get-Date
    $p = [System.Diagnostics.Process]::Start($psi)
    $seen = $false
    $seenAt = $null
    $ended = ''
    $viewerAt = $null
    $pageWord = $r.Page     # the page is looked for until its server answers (the run may wait for the lock first)
    $holder = $null
    $holderLog = Join-Path $PSScriptRoot 'logs\page_dock.log'
    # What the launcher has to say while the run goes on is kept here and said after the run:
    # the run's console redraws its live rows ten times a second from where the cursor stands
    # (console_screen.py), so a line written in between is wiped at once and leaves stale rows.
    $late = [System.Collections.Generic.List[string]]::new()
    try {
        if ($r.Page -and -not $LoosePage) {
            # The page is held against the simulator's window, the two as one (tools/page_dock.ps1;
            # Hani, 2026-11-22).  The holder waits for this run's two windows (the page by this
            # run's word, as Find-Page does, so a page left open by another run is never taken),
            # ends by itself when the window or the run is gone, and is never ended from here.
            # It writes down what it finds and does in $holderLog (one file, started anew by
            # every run that has a holder).  A failure to start it never touches the run: the
            # page then opens as a window of its own.
            try {
                $holdArgs = @('-NoProfile', '-File', ('"' + (Join-Path $PSScriptRoot 'tools/page_dock.ps1') + '"'), '-WatchPid', $p.Id,
                              '-PageWord', $r.Page, '-PortFrom', $pagePorts[0], '-PortTo', $pagePorts[-1],
                              '-Log', ('"' + $holderLog + '"'), '-Trace')
                $holder = Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList $holdArgs -WindowStyle Hidden -PassThru
                $null = $holder.Handle      # keeps the handle: HasExited and ExitCode stay readable
            } catch {
                $holder = $null
                Write-Host "run: the page is not held against the window ($($_.Exception.Message)); it opens as a window of its own" -ForegroundColor Yellow
            }
        }
        if ($r.Cameras) {
            # -Draw cameras: the window of what our cameras see (tools/camera_view.ps1).  It only
            # reads the run's cameras folder (at low priority), closes 20 s after this run's process
            # has ended, and a failure to start it never touches the run.  In a seed list the window
            # of the seed before goes first: its run is over.  Start-Process does not quote its
            # arguments.  It starts inside this try, so that a stopped launcher ends the run too.
            if ($viewer -and -not $viewer.HasExited) { Stop-Process -Id $viewer.Id -ErrorAction SilentlyContinue }
            $viewer = $null
            try {
                $viewerArgs = @('-NoProfile', '-File', ('"' + (Join-Path $PSScriptRoot 'tools/camera_view.ps1') + '"'),
                                '-Dir', ('"' + $r.Cameras + '"'), '-WatchPid', $p.Id)
                $viewer = Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList $viewerArgs `
                              -WindowStyle Hidden -PassThru
                $null = $viewer.Handle      # keeps the handle: HasExited and ExitCode stay readable
                $viewerAt = Get-Date
            } catch {
                Write-Host "run: the camera window did not start ($($_.Exception.Message)); the run goes on without it" -ForegroundColor Yellow
            }
        }
        while (-not $p.HasExited) {
            Start-Sleep -Milliseconds 700
            if ($viewerAt -and ((Get-Date) - $viewerAt).TotalSeconds -ge 6) {
                # a window that died after it started would otherwise be missing without a word
                $viewerAt = $null
                if ($viewer.HasExited) {
                    Write-Host ("run: the camera window ended at once (exit code $($viewer.ExitCode)); to see why, run: " +
                                "pwsh -NoProfile -File tools/camera_view.ps1 -Dir '$($r.Cameras)'") -ForegroundColor Yellow
                }
            }
            if ($holder -and $holder.HasExited) {
                # The holder ends by itself: with 0 after holding (the page's window was closed),
                # with 2 when the run ended first.  Any other code while the run goes on means
                # that the page is not held, which would otherwise show as a loose page without
                # a word.  The word is said after the run (see $late).
                if ($holder.ExitCode -notin 0, 2 -and -not $p.HasExited) {
                    $why = switch ($holder.ExitCode) {
                        5 { 'more than one simulator window was open and it could not tell which was this run''s' }
                        6 { 'it found no simulator window' }
                        7 { 'no browser window of its own showed the page' }
                        default { 'the holder stopped on an error' }
                    }
                    # the log this holder wrote: a file of its own when the first was in use (page_dock.ps1)
                    $wrote = [System.IO.Path]::ChangeExtension($holderLog, "$($holder.Id).log")
                    if (-not (Test-Path -LiteralPath $wrote)) { $wrote = $holderLog }
                    $late.Add("run: the page was not held against the window: $why (the holder's exit code $($holder.ExitCode)). " +
                              "It stayed a window of its own; the holder's log is $wrote")
                }
                $holder = $null
            }
            if ($pageWord -and $seenAt -and ((Get-Date) - $seenAt).TotalSeconds -ge 20) {
                # The run's window has been open this long and no page answers: this run has
                # none (no free port for it, or a flag of -Args took it away).  The ports are
                # asked no more; asking them slows this loop's watch of the window.
                $pageWord = $null
            }
            if ($pageWord) {
                # The page beside the window: opened once, as soon as this run's server answers.
                # A failure here never touches the run.
                try {
                    $pageUrl = Find-Page $pageWord
                    if ($pageUrl) { $pageWord = $null; Open-Page $pageUrl ([bool]$holder) }
                } catch { $pageWord = $null }
            }
            if ($Headless -or $ended) { continue }
            $open = @(Get-Process -Name msrdc -ErrorAction SilentlyContinue |
                      Where-Object { $_.MainWindowTitle -like '*Bullet Physics*' }).Count
            if ($open -gt 0) { $seen = $true; if (-not $seenAt) { $seenAt = Get-Date } }
            elseif ($seen) {
                # A run that is ending closes its own window: give it a moment.
                if (-not $p.WaitForExit(3000)) {
                    $ended = 'the window was closed'
                    $null = wsl -e bash -c "$PROCS kill-mine '$($r.Mine)' $([int]((Get-Date) - $t0).TotalSeconds + 60)"
                }
            }
        }
    } finally {
        if (-not $p.HasExited -and -not $p.WaitForExit(3000)) {
            # This script was stopped while the run goes on (a closed host, a
            # Stop-Process): the run gets 3 s to end by itself, then it is ended here.
            $ended = 'the launcher was stopped'
            $null = wsl -e bash -c "$PROCS kill-mine '$($r.Mine)' $([int]((Get-Date) - $t0).TotalSeconds + 60)"
            $null = $p.WaitForExit(5000)
        }
        # The console hides the cursor while a step runs; show it whatever happened.
        [Console]::Out.Write("`e[?25h")
        if ($ended) {
            [Console]::Out.WriteLine("run: $ended, so the run was ended from here; nothing of it is left in WSL")
        } elseif ($p.HasExited -and $p.ExitCode -eq 130) {
            [Console]::Out.WriteLine('run: interrupted (Ctrl-C ends the run at once; its files stay as they were)')
        }
        # what was kept while the run drew its console, in yellow
        foreach ($line in $late) { [Console]::Out.WriteLine("`e[33m$line`e[0m") }
    }
    $code = $p.ExitCode
    $done += [pscustomobject]@{ Seed = $r.Seed; Code = $code; Ended = $ended
                                Wall = [int]((Get-Date) - $t0).TotalSeconds; Record = $r.Record }
    if ($code -eq 130) { break }
}

if ($many) {
    # One line per seed: the record's outcome (success, failure, crashed,
    # gate_failed) where there is one, else what the exit says; then the
    # seeds a refusal or Ctrl-C left out.
    Write-Host ''
    Write-Host "run: $($done.Count) of $($seeds.Count) seeds run, one after another"
    foreach ($x in $done) {
        $status = if ($x.Ended) { 'window closed' } elseif ($x.Code -eq 130) { 'interrupted' }
                  elseif ($x.Code -eq 0) { 'success' } else { "exit $($x.Code)" }
        $folder = ''
        if ($x.Record) {
            $folder = Split-Path (Split-Path $x.Record -Parent) -Leaf
            if (-not $x.Ended -and $x.Code -ne 130 -and (Test-Path -LiteralPath $x.Record)) {
                try { $o = (Get-Content -Raw -LiteralPath $x.Record | ConvertFrom-Json).outcome; $status = if ($o.status) { $o.status } else { $o.outcome } } catch { }
            }
        }
        $color = if ($status -eq 'success') { 'Green' } else { 'Yellow' }
        Write-Host ("  seed {0,-5} {1,-14} {2,5} s   {3}" -f $x.Seed, $status, $x.Wall, $folder) -ForegroundColor $color
    }
    $left = @($seeds | Select-Object -Skip $done.Count)
    if ($left.Count -gt 0) { Write-Host "  not run: $($left -join ', ')" -ForegroundColor Yellow }
    # The list's exit: 2 refused, 130 interrupted, else 0 when every run succeeded.
    if ($code -notin 2, 130) { $code = [int](@($done | Where-Object { $_.Code -ne 0 }).Count -gt 0) }
}
exit $code
