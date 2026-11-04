# Watch our pipeline in the PyBullet GUI (WSL, arm O venv).
#   pwsh tools/watch.ps1              find_dice seed 0 in TAMPURA's world (the bridge)
#   pwsh tools/watch.ps1 -Seed 7      another find_dice seed
#   pwsh tools/watch.ps1 -Seed 118 -Gen  a scene from their generator (BF#63, seeds 100-139)
#   pwsh tools/watch.ps1 -Ours        our own holding scene, seed 0
#   pwsh tools/watch.ps1 -Off         the same without M8-M10 (the old pipeline)
#   pwsh tools/watch.ps1 -Squeeze 3   the old 3 mm pick squeeze (0.5 mm is the default since BF#44)
#   pwsh tools/watch.ps1 -Squeeze 1   any pick squeeze in mm (larger = tighter; default 0.5; -LightGrip = 0.5)
#   pwsh tools/watch.ps1 -Screenshots also save the eye PNGs at every snapshot (debugging only; off since BF#50)
#   pwsh tools/watch.ps1 -ReturnHome  return the arm to a view spot before every sense (BF#52's fold off; the A/B)
#   pwsh tools/watch.ps1 -Before      the fold off and the search without BF#53's effort weighting and starting
#                                     complexity (pddlstream's own settings): the pipeline of the 2026-10-30 18:09 baseline
# Never start it while another pipeline run is going (pddlstream temp/ race).
param([int]$Seed = 0, [switch]$Ours, [switch]$Off, [switch]$LightGrip, [double]$Squeeze = 0,
      [switch]$Screenshots, [switch]$ReturnHome, [switch]$Before, [switch]$Gen)
$S = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
$sw = if ($Off) { '--m8 off --m9 off --m10 off --pick-aperture-from-pose off' } else { '' }
if ($LightGrip) { $Squeeze = 0.5 }
if ($Squeeze -gt 0) {
    $sw += ' --grip-squeeze-mm ' + $Squeeze.ToString([cultureinfo]::InvariantCulture)
}
if ($Screenshots) { $sw += ' --save-screenshots on' }
if ($ReturnHome) { $sw += ' --sense-over-region off' }
if ($Before) { $sw += ' --sense-over-region off --search-effort-weight off --search-initial-complexity 0' }
if ($Ours) {
    $cmd = "cd $S && PYTHONHASHSEED=0 /root/armO-venvA/bin/python test_full_pipeline.py " +
           "--scene random-pairs --seed $Seed --goal holding --n-occluders 2 $sw"
} else {
    $stamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
    $run = "PYTHONPATH=$S`:$S/pddlstream_lib`:`$TW/tampura`:`$TW/tampura_environments " +
           "PYTHONHASHSEED=0 /root/armO-venvA/bin/python $S/tampura_bridge/run_bridge_on_finddice.py " +
           "--global-seed $Seed --vis 1 --save-dir $S/archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/watch_s${Seed}_$stamp $sw"
    if ($Gen) {
        # BF#63: their loader picks a random file of tampura_environments/
        # find_dice/problems under the cwd, so the run starts in a directory
        # holding only this scene (as tools/gen_scene_eval.py does); the
        # manifest pins it for G19.  The directory goes when the run ends.
        $G = "$S/tampura_bridge/gen_scenes/find_dice"
        $D = "/root/watch_gen_s${Seed}_$stamp"
        $cmd = "TW=/root/tampura-work; trap 'rm -rf $D' EXIT; " +
               "mkdir -p $D/tampura_environments/find_dice/problems && " +
               "cp $G/find_dice_gen_s${Seed}.json $D/tampura_environments/find_dice/problems/ && " +
               "ln -s `$TW/tampura_environments/env_configs $D/env_configs && cd $D && " +
               "BRIDGE_SCENE_MANIFEST=$G/manifest.json $run"
    } else {
        $cmd = "TW=/root/tampura-work; cd `$TW/tampura_environments && $run"
    }
}
wsl -e bash -lc $cmd
