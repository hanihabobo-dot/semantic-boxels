# Watch the carry of a pinched body home in TAMPURA's GUI (WSL, arm T venv)
# with the hold detector's verdict and the body's true position printed side
# by side (tools/_probe_carry_watch.py).  Never start it while a pipeline
# run is going.
#   pwsh tools/watch_carry.ps1 -Squeeze 3              five carries of the die at 3 mm
#   pwsh tools/watch_carry.ps1 -Squeeze 0.5 -Tilt 10   the die 10 deg tilted in the grasp
#   pwsh tools/watch_carry.ps1 -Squeeze 0.5 -Payload a_cups_ud -Trials 3
param([double]$Squeeze = 0.5, [int]$Trials = 5, [double]$Tilt = 0,
      [string]$Payload = 'dice', [string]$Cell = '0.673,0.216', [double]$Slow = 4)
$S = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
$ic = [cultureinfo]::InvariantCulture
$stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$out = "$S/archive/tampura_bridge_plan_2026-10-25/bf/carry_watch/${stamp}_${Payload}_sq$($Squeeze.ToString($ic))mm_tilt$($Tilt.ToString($ic)).json"
$cmd = "mkdir -p $S/archive/tampura_bridge_plan_2026-10-25/bf/carry_watch; TW=/root/tampura-work; cd `$TW/tampura_environments && " +
       "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=`$TW/tampura:.:$S`:$S/tools " +
       "`$TW/.venv/bin/python $S/tools/_probe_carry_watch.py --squeeze-mm $($Squeeze.ToString($ic)) " +
       "--trials $Trials --tilt-deg $($Tilt.ToString($ic)) --payload $Payload --cell $Cell " +
       "--slow $($Slow.ToString($ic)) --vis 1 --out $out"
wsl -e bash -lc $cmd
