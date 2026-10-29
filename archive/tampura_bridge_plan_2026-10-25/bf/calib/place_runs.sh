cd /mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
source wsl_env/bin/activate
date +%s > archive/tampura_bridge_plan_2026-10-25/bf/calib/place_runs.start
for g in holding find-and-tray-stack; do for n in 2 3 4; do for s in 0 1 2 3 4; do
  echo "== $g n=$n seed=$s"
  timeout 600 python test_full_pipeline.py --no-gui --scene random-pairs --seed $s --goal $g --baseline semantic --log-level quiet --no-telemetry --n-occluders $n > /dev/null 2>&1
  echo "exit $?"
done; done; done