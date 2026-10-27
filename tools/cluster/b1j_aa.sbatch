#!/bin/bash
#SBATCH --job-name=p4-b1j-aa
#SBATCH --partition=cpu_modern
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=16:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B1(j) test 5 (= the first half of B3's acceptance): an A/A run of
# c31cbdd against itself in arm O's venv (A), on our holding scene, seeds
# 0-19 and 100-119, serial on an exclusive node (P4.6 MACHINE).  The two
# repetitions run one after the other from the same immutable snapshot;
# their per-seed flips are the noise floor B3's A/B is judged against.
set -euo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
SB=$W/sb_c31cbdd
VA=$W/armO-venvA/bin
OUT=$W/results/b1j_aa
mkdir -p $OUT
export PYTHONHASHSEED=0
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)"
grep -m1 'model name' /proc/cpuinfo
cd $SB
for rep in 1 2; do
  for seeds in 0-19 100-119; do
    tag=aa${rep}_c31cbdd_armOvenvA_${seeds}
    $VA/python -u tools/_eval_ab.py --tag $tag --seeds $seeds \
      --scene random-pairs --goal holding --out-dir $OUT
  done
done
echo B1J_AA_DONE
