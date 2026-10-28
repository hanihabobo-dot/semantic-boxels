#!/bin/bash
#SBATCH --job-name=p4-b3-diag
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=02:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B3's acceptance (BF#10), DIAGNOSTIC runs outside the pre-registered
# acceptance: which snapshot first changes a reproduced plan-count
# difference.  Usage: sbatch -w cn-110 b3_diag.sbatch <reps> <seed> <snap>...
# Each repetition runs the seed once per snapshot, interleaved.
set -euo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
REPS=$1; SEED=$2; shift 2
VA=$W/armO-venvA/bin
OUT=$W/results/b3_diag
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  seed $SEED  snapshots $*"
for r in $(seq 1 $REPS); do
  for snap in "$@"; do
    (cd $W/$snap && $VA/python -u tools/_eval_ab.py --tag diag_${SEED}_${snap#sb_}_r$r \
       --seeds $SEED --scene random-pairs --goal holding --out-dir $OUT)
  done
done
echo B3_DIAG_DONE
