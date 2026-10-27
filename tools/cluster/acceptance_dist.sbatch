#!/bin/bash
#SBATCH --job-name=p4-accept
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=16:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 the acceptance runs of B5, M6 and M7 (BF#13): the reference and the
# candidate snapshot, our holding scene, seeds 0-19 and 100-119, THREE
# repetitions, interleaved per seed (reference, then candidate), on an
# exclusive node (submit with -w cn-110), one harness file, armO-venvA,
# PYTHONHASHSEED 0.  Afterwards: tools/acceptance_plan_counts.py on the
# plan counts (rep 1 to 3 of each arm), and the outcome and target clauses
# with repetition 2 as each flipped seed's one re-run.
# Usage: sbatch -w cn-110 acceptance_dist.sbatch <ref snapshot> <cand snapshot>
set -uo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
REF=${1:?reference snapshot dir, e.g. sb_852b319}
CAND=${2:?candidate snapshot dir}
VA=$W/armO-venvA/bin
OUT=$W/results/accept_${REF#sb_}_vs_${CAND#sb_}
mkdir -p $OUT
export PYTHONHASHSEED=0
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
echo ACCEPT_DONE
