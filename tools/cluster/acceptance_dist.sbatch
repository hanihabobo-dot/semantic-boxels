#!/bin/bash
#SBATCH --job-name=p4-accept
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=16:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# #P4 the acceptance runs of B5, M6 and M7 (BF#13): the reference and the
# candidate snapshot, our holding scene, seeds 0-19 and 100-119, THREE
# repetitions, interleaved per seed (reference, then candidate), on an
# exclusive node (submit with -w <node>), one harness file, armO-venvA,
# PYTHONHASHSEED 0.  Afterwards: tools/acceptance_plan_counts.py on the
# plan counts (rep 1 to 3 of each arm), and the outcome and target clauses
# with repetition 2 as each flipped seed's one re-run.
# Usage: sbatch -w <node> acceptance_dist.sbatch <ref snapshot> <cand snapshot>
set -uo pipefail
W=${P4_WORK:?the cluster work folder}
REF=${1:?reference snapshot dir, e.g. sb_852b319}
CAND=${2:?candidate snapshot dir}
VA=$W/armO-venvA/bin
OUT=$W/results/accept_${REF#sb_}_vs_${CAND#sb_}
mkdir -p $OUT
export PYTHONHASHSEED=0
# Sim screenshots are for local debugging only.  Off only when BOTH snapshots
# have the switch: an older reference would still render and save them, and
# the wall-clock budgets would then differ between the arms.  Deleted at the
# end either way.
# (world_eye.py lies in world/ since the folder move, at the root in an older snapshot: both are tried)
if grep -qs BOXEL_EYE_IMAGES $W/$REF/world/world_eye.py $W/$REF/world_eye.py && grep -qs BOXEL_EYE_IMAGES $W/$CAND/world/world_eye.py $W/$CAND/world_eye.py; then
  export BOXEL_EYE_IMAGES=0; echo "sim screenshots off on both arms"
else
  echo "sim screenshots ON on both arms (a snapshot predates the switch); deleted at the end"
fi
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  ref $REF  cand $CAND"
grep -m1 'model name' /proc/cpuinfo
cmp $W/$REF/tools/_eval_ab.py $W/$CAND/tools/_eval_ab.py && echo "one harness file"
sha256sum $W/$REF/tools/_eval_ab.py $W/$CAND/tools/_eval_ab.py
for rep in 1 2 3; do
  for s in $(seq 0 19) $(seq 100 119); do
    for arm in $REF $CAND; do
      (cd $W/$arm && $VA/python -u tools/_eval_ab.py \
         --tag r${rep}_${arm#sb_} --seeds $s --scene random-pairs \
         --goal holding --out-dir $OUT)
    done
  done
done
find $W/$REF $W/$CAND $OUT -type f \( -name 'eye_*_camera.png' -o -name 'eye_*_gui.png' \) -delete
echo ACCEPT_DONE
