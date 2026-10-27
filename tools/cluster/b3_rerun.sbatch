#!/bin/bash
#SBATCH --job-name=p4-b3-rerun
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=06:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B3's acceptance, the pre-registered re-runs (BF#10): every seed whose
# outcome or plan count differed between the A/B arms gets ONE re-run on
# both arms, interleaved per seed (c31cbdd, then B3), same node, harness and
# venv as the A/A and the A/B.  Fixed before any re-run result was seen: a
# difference REPRODUCES when the re-run gives each arm the same outcome
# (for an outcome flip) or the same plan count (for a plan-count
# difference) it had in the A/B; an outcome flip that reproduces fails the
# acceptance, and so does a plan-count difference that reproduces.
# Usage: sbatch -w cn-110 b3_rerun.sbatch <B3 snapshot dir> <seed> [<seed> ...]
set -euo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
SA=$W/sb_c31cbdd
SB=$W/${1:?B3 snapshot dir name, e.g. sb_526b358}
shift
VA=$W/armO-venvA/bin
OUT=$W/results/b3_rerun
mkdir -p $OUT
export PYTHONHASHSEED=0
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  seeds $*"
grep -m1 'model name' /proc/cpuinfo
for s in "$@"; do
  (cd $SA && $VA/python -u tools/_eval_ab.py --tag rr_c31cbdd --seeds $s \
     --scene random-pairs --goal holding --out-dir $OUT)
  (cd $SB && $VA/python -u tools/_eval_ab.py --tag rr_${SB##*/sb_} --seeds $s \
     --scene random-pairs --goal holding --out-dir $OUT)
done
echo B3_RERUN_DONE
