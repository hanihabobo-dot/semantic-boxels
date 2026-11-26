#!/bin/bash
#SBATCH --job-name=p4-slipT
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=12:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# BF#59: TAMPURA (arm T, their planner as shipped) on the campaign's seeds
# with the same repetitions as our arms, on a shared node like them, driven
# by tools/_bridge_campaign.py --arms T with --drop-t-history (their 12 to
# 16 MB RolloutHistory pickle goes once its rewards and times are in the
# record, BF#49's cap).  The per-run gates run before the first episode.
# Usage (submit from the submit node, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w <node> $W/sb_<sha>/tools/cluster/slip_t.sbatch sb_<sha> 3 0-19 [OUT]
set -uo pipefail
W=${P4_WORK:?the cluster work folder}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
REPS=${2:-3}
SEEDS=${3:-0-19}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
OUT=${4:-$W/results/slipT_${SB##*/sb_}_${SLURM_JOB_ID:-local}}
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  arm T  reps $REPS  seeds $SEEDS  out $OUT"
grep -m1 'model name' /proc/cpuinfo
(cd $SB && $VA/python tools/bridge_gates.py all --save $OUT/g13_before.json) > $OUT/gates_before.txt 2>&1
GRC=$?
cat $OUT/gates_before.txt
if [ $GRC -ne 0 ]; then
  echo "per-run gates FAILED before the campaign: nothing run"
  exit 1
fi
$VA/python -u $SB/tools/_bridge_campaign.py --snapshot $SB --tampura-work $TW \
  --venv-t $TW/.venv --venv-o $W/armO-venvA --pddlstream-lib $W/pddlstream_lib \
  --out $OUT --mode full --reps $REPS --seeds $SEEDS --cap 600 --arms T --drop-t-history
echo "harness rc $? (0 finished, 2 stopped by a rule)"
(cd $SB && $VA/python tools/bridge_gates.py tree --compare $OUT/g13_before.json) > $OUT/gates_after.txt 2>&1
cat $OUT/gates_after.txt
echo "results in $OUT"
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo SLIPT_DONE
