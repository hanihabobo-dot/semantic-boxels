#!/bin/bash
#SBATCH --job-name=p4-tc
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=06:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# BF#53: the per-fix eval of the time cuts (tools/time_cut_eval.py), our
# arm alone on TAMPURA's find_dice, serial on an exclusive node from an
# immutable snapshot (arm O's venv A).  No screenshots on the cluster.
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1):
#   sbatch $W/sb_<sha>/tools/cluster/time_cut_eval.sbatch sb_<sha> base,1,2,12 0-23 [OUT]
#   OUT (optional): a results directory shared by several jobs; each job's
#   arms go to OUT/<job id>.  To read them together, cat the jobs'
#   results.jsonl files into one directory and run
#   time_cut_eval.py --out that --summary.
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
ARMS=${2:?arms, e.g. base,1,2,12}
SEEDS=${3:-0-23}
OUT=${4:-$W/results/tc_${SB##*/sb_}}/${SLURM_JOB_ID:-local}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  arms $ARMS  seeds $SEEDS  out $OUT"
grep -m1 'model name' /proc/cpuinfo
(cd $SB && $VA/python tools/bridge_gates.py static) > $OUT/static.txt 2>&1
tail -3 $OUT/static.txt
$VA/python -u $SB/tools/time_cut_eval.py --snapshot $SB --out $OUT --arms $ARMS \
  --seeds $SEEDS --cap 600 --python $VA/python --cwd $TW/tampura_environments
echo "harness rc $?"
echo "results in $OUT"
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo TC_DONE
