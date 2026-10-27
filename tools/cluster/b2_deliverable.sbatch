#!/bin/bash
#SBATCH --job-name=p4-b2
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=02:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B2's deliverable (BF#12): seeds 0 and 1 through the bridge in arm O's
# venv (A), stop_before_planning, their tree checked before and after (G13),
# each run's ledger read by bridge_gates.py, the static gates on the snapshot.
# Usage: sbatch -w cn-110 b2_deliverable.sbatch <snapshot dir, e.g. sb_852b319>
set -uo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
SB=$W/${1:?snapshot dir}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
OUT=$W/results/b2_${1#sb_}
mkdir -p $OUT
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB"
grep -m1 'model name' /proc/cpuinfo
(cd $SB && $VA/python tools/bridge_gates.py tree) > $OUT/g13_before.txt 2>&1
for seed in 0 1; do
  (cd $TW/tampura_environments && \
   PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments \
   $VA/python $SB/tampura_bridge/run_bridge_on_finddice.py --global-seed $seed \
     --vis 0 --stop-before-planning 1 --save-dir $OUT/seed$seed \
     > $OUT/seed$seed.console 2>&1)
  echo "seed $seed rc=$? (1 expected: nothing is planned, their reward stays 0)"
  RUN=$(ls -d $OUT/seed$seed/ours/run_* 2>/dev/null | head -1)
  (cd $SB && $VA/python tools/bridge_gates.py ledger $RUN --m7 off) \
    > $OUT/seed${seed}_ledger_gates.txt 2>&1
  cat $OUT/seed${seed}_ledger_gates.txt
done
(cd $SB && $VA/python tools/bridge_gates.py tree) > $OUT/g13_after.txt 2>&1
diff $OUT/g13_before.txt $OUT/g13_after.txt && echo "G13 tree unchanged across the runs"
cat $OUT/g13_after.txt
(cd $SB && $VA/python tools/bridge_gates.py static) > $OUT/static.txt 2>&1
cat $OUT/static.txt
echo B2_DONE
