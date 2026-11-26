#!/bin/bash
#SBATCH --job-name=p4-b3-ab
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=16:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# #P4 B3's acceptance, second half (BF#10): the A/B of the B3 commit against
# c31cbdd in arm O's venv (A), on our holding scene, seeds 0-19 and 100-119,
# serial on an exclusive node (P4.6 MACHINE), submitted with -w <node> like
# the A/A (b1j_aa.sbatch), with the same harness.  The c31cbdd arm is the
# A/A's first repetition; its two repetitions give the noise floor.
# Usage: sbatch -w <node> b3_ab.sbatch <snapshot dir, e.g. sb_526b358>
set -euo pipefail
W=${P4_WORK:?the cluster work folder}
SB=$W/${1:?snapshot dir name, e.g. sb_526b358}
VA=$W/armO-venvA/bin
OUT=$W/results/b3_ab
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB"
grep -m1 'model name' /proc/cpuinfo
cd $SB
for seeds in 0-19 100-119; do
  tag=ab_${1#sb_}_armOvenvA_${seeds}
  $VA/python -u tools/_eval_ab.py --tag $tag --seeds $seeds \
    --scene random-pairs --goal holding --out-dir $OUT
done
echo B3_AB_DONE
