#!/bin/bash
#SBATCH --job-name=p4-b8
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=16:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B8: the campaign (P4.6): both arms on find_dice, seeds 0-19, two
# repetitions, serial, interleaved per seed, on an exclusive node, driven
# by tools/_bridge_campaign.py from an immutable snapshot (arm O's venv A,
# arm T's venv).  The per-run gates before the first episode (G13's trees,
# the T driver, the domain, the static gates), G13's tree compare and the
# static gates after the last.  No screenshots on the cluster (BF#17).
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1):
#   sbatch -w cn-110 $W/sb_<sha>/tools/cluster/b8_campaign.sbatch sb_<sha> smoke 1 0,1
#   sbatch -w cn-110 $W/sb_<sha>/tools/cluster/b8_campaign.sbatch sb_<sha> full 2 0-19
#   RESUME=<campaign dir> sbatch ...   continues a cut campaign in that directory
#   mode: full (plans and acts) or smoke (T --max-steps 1, O stop_before_planning)
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}   # P4_WORK: a local dry run
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
MODE=${2:?full or smoke}
REPS=${3:-2}
SEEDS=${4:-0-19}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
OUT=${RESUME:-$W/results/b8_${SB##*/sb_}_${MODE}_${SLURM_JOB_ID:-local}}
mkdir -p $OUT
case $MODE in full) CAP=900;; smoke) CAP=600;;
  *) echo "mode must be full or smoke"; exit 2;; esac
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  mode $MODE  reps $REPS  seeds $SEEDS  out $OUT"
grep -m1 'model name' /proc/cpuinfo
# The per-run gates before any episode (P4.6 PER-RUN GATES): their trees and
# arm T's installed tampura (G13), the T driver against run_planner.py, the
# domain hashes and the static gates.  A failure stops the campaign unrun.
(cd $SB && $VA/python tools/bridge_gates.py all --save $OUT/g13_before.json) > $OUT/gates_before.txt 2>&1
GRC=$?
cat $OUT/gates_before.txt
if [ $GRC -ne 0 ]; then
  echo "per-run gates FAILED before the campaign: nothing run"
  exit 1
fi
$VA/python -u $SB/tools/_bridge_campaign.py --snapshot $SB --tampura-work $TW \
  --venv-t $TW/.venv --venv-o $W/armO-venvA --pddlstream-lib $W/pddlstream_lib \
  --out $OUT --mode $MODE --reps $REPS --seeds $SEEDS --cap $CAP
HRC=$?
echo "harness rc $HRC (0 finished, 2 stopped by a rule)"
(cd $SB && $VA/python tools/bridge_gates.py tree --compare $OUT/g13_before.json) > $OUT/gates_after.txt 2>&1
cat $OUT/gates_after.txt
(cd $SB && $VA/python tools/bridge_gates.py static) > $OUT/static.txt 2>&1
tail -3 $OUT/static.txt
echo "results in $OUT"
# BF#49: the cluster's data hygiene after every campaign (this job's snapshot
# is referenced while it runs, so it stays; the fresh results stay for two days).
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo B8_DONE
