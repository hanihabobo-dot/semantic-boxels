#!/bin/bash
#SBATCH --job-name=p4-slip
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=12:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# BF#59: the eval of the die-slip campaign's fixes (tools/slip_eval.py), our
# arm alone on TAMPURA's find_dice, serial, from an immutable snapshot (arm
# O's venv A), on a SHARED node (8 CPUs, 24 GB; BF#53: an exclusive node
# never came free; the base arm runs in every job as the within-job
# control).  Submit one job per group of arms, each pinned to a different
# node (-w), so two of our pipelines never share a node.  No screenshots.
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w cn-1xx $W/sb_<sha>/tools/cluster/slip_eval.sbatch sb_<sha> base,a,b 0-19 3 1,2,5 [OUT]
#   arguments: snapshot, arms, seeds, reps, replicated seeds, OUT (optional:
#   a results directory shared by several jobs; each job's arms go to
#   OUT/<job id>; cat the jobs' results.jsonl files into one directory and
#   run slip_eval.py --out that --summary to read them together).
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
ARMS=${2:?arms, e.g. base,a,b}
SEEDS=${3:-0-19}
REPS=${4:-1}
REPSEEDS=${5:-}
OUT=${6:-$W/results/slip_${SB##*/sb_}}/${SLURM_JOB_ID:-local}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  arms $ARMS  seeds $SEEDS  reps $REPS on ${REPSEEDS:-none}  out $OUT"
grep -m1 'model name' /proc/cpuinfo
(cd $SB && $VA/python tools/bridge_gates.py static) > $OUT/static.txt 2>&1
tail -3 $OUT/static.txt
$VA/python -u $SB/tools/slip_eval.py --snapshot $SB --out $OUT --arms $ARMS \
  --seeds $SEEDS --reps $REPS --rep-seeds "$REPSEEDS" --cap 600 \
  --python $VA/python --cwd $TW/tampura_environments
echo "harness rc $?"
echo "results in $OUT"
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo SLIP_DONE
