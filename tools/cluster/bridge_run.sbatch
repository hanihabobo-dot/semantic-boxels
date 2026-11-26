#!/bin/bash
#SBATCH --job-name=p4-bridge
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=12:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# #P4: our pipeline on TAMPURA's find_dice through the bridge (arm O), one
# episode per seed, serial (P4.6 MACHINE), in arm O's venv (A).  G13 checks
# their trees before and after; each episode's outcome field (GF5) and
# ledger gates are in its bridge_episode.json and console; the static gates
# run on the snapshot.  No screenshots on the cluster (BF#17).
# Usage (submit from the submit node, after tools/cluster/push_snapshot.ps1):
#   sbatch -w <node> $W/sb_<sha>/tools/cluster/bridge_run.sbatch sb_<sha> full 0 1
#   mode: full (plans and acts) or smoke (stop_before_planning)
#   CLEAN_STRAYS=1 sbatch ... first removes the two files earlier bridge
#   runs (before GF8) left in their tampura_environments, and nothing else.
set -uo pipefail
W=${P4_WORK:?the cluster work folder}   # P4_WORK: the cluster work folder, or a local folder for a dry run
SB=$W/${1:?snapshot dir, e.g. sb_bb20e83}
MODE=${2:?full or smoke}
shift 2
[ $# -ge 1 ] || { echo "give one or more seeds"; exit 2; }
SEEDS="$*"
TW=$W/tampura-work
VA=$W/armO-venvA/bin
OUT=$W/results/bridge_${SB##*/sb_}_${MODE}_${SLURM_JOB_ID:-local}
mkdir -p $OUT
case $MODE in full) STOP=0; CAP=1800;; smoke) STOP=1; CAP=600;;
  *) echo "mode must be full or smoke"; exit 2;; esac
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  mode $MODE  seeds $SEEDS"
grep -m1 'model name' /proc/cpuinfo
if [ "${CLEAN_STRAYS:-0}" = 1 ]; then
  for f in boxel_data.json statistics/py3/boxel-streams.pkl; do
    [ -f $TW/tampura_environments/$f ] && rm -v $TW/tampura_environments/$f
  done
  rmdir $TW/tampura_environments/statistics/py3 $TW/tampura_environments/statistics 2>/dev/null
fi
(cd $SB && $VA/python tools/bridge_gates.py tree) > $OUT/g13_before.txt 2>&1
G13_RC=$?
cat $OUT/g13_before.txt
if [ $G13_RC -ne 0 ]; then
  echo "G13 FAILED before the runs (per-run gate): campaign stops, nothing run"
  exit 1
fi
for seed in $SEEDS; do
  (cd $TW/tampura_environments && \
   PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments \
   timeout $CAP $VA/python $SB/tampura_bridge/run_bridge_on_finddice.py \
     --global-seed $seed --vis 0 --stop-before-planning $STOP \
     --save-dir $OUT/seed$seed > $OUT/seed$seed.console 2>&1)
  rc=$?
  echo "== seed $seed rc=$rc (0 success, 1 not success, 124 harness cap $CAP s)"
  $VA/python - $OUT/seed$seed/bridge_episode.json <<'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except OSError as e:
    print('  no bridge_episode.json:', e); sys.exit()
o = d.get('outcome', {})
print(f"  outcome {o.get('status')}  reward {o.get('reward')}  error {o.get('error')}"
      f"  gate failures {o.get('gate_failures')}")
for g, s, det in d.get('ledger_gates', []):
    print(f"  {g:<6} {s:<5} {det[:160]}")
EOF
done
(cd $SB && $VA/python tools/bridge_gates.py tree) > $OUT/g13_after.txt 2>&1
diff $OUT/g13_before.txt $OUT/g13_after.txt && echo "G13 tree unchanged across the runs"
cat $OUT/g13_after.txt
(cd $SB && $VA/python tools/bridge_gates.py static) > $OUT/static.txt 2>&1
cat $OUT/static.txt
echo "results in $OUT"
echo BRIDGE_DONE
