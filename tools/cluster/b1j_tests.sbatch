#!/bin/bash
#SBATCH --job-name=p4-b1j-tests
#SBATCH --partition=cpu_modern
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 B1(j): D12's tests 1 to 4 for candidate (A).  Test 5, the A/A of
# c31cbdd, is b1j_aa.sbatch.  Usage: sbatch b1j_tests.sbatch <head snapshot>
set -uo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
TW=$W/tampura-work
SB=$W/${1:?head snapshot dir name, e.g. sb_030ef7e}
VT=$TW/.venv/bin
VA=$W/armO-venvA/bin
OUT=$W/results/b1j
mkdir -p $OUT
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)"
grep -m1 'model name' /proc/cpuinfo
status() { echo "TEST $1: $2"; echo "$1 $2" >> $OUT/summary.txt; }
: > $OUT/summary.txt

# Test 1: 'import tampura', their full import set, and our modules, in (A).
cd $TW/tampura_environments
if $VA/python -c "import tampura, tampura_environments, torch, gymnasium, stable_baselines3, tensorboard; from tampura.policies.policy import Policy; from tampura.environment import TampuraEnv; import tampura_environments.find_dice.env; print('their import set ok')" \
   && (cd $SB && $VA/python -c "import test_full_pipeline, execution, streams, boxel_env, pddlstream_planner, perception, world_eye, telemetry, run_logger; from tampura_bridge import gate_hooks; print('our import set ok')"); then
  status 1 PASS; else status 1 FAIL; fi
(cd $SB && $VA/python -m pytest -q -p no:cacheprovider tampura_bridge/tests/test_gate_hooks.py tampura_bridge/tests/test_ledger_reader.py 2>&1 | tail -3)

# Test 2: the three layouts built under (A) and under arm T's venv: identical
# per-body AABBs and t=0 segmentation id sets.
ok=1
for pair in "1747173591 0" "1747173590 1" "1747173593 5"; do
  set -- $pair
  $VT/python $SB/tools/_probe_b1_tampura.py --layout-sig $1 $2 2>/dev/null | grep '^{' > $OUT/t2_armT_$1.json
  $VA/python $SB/tools/_probe_b1_tampura.py --layout-sig $1 $2 2>/dev/null | grep '^{' > $OUT/t2_armO_$1.json
  $VT/python - $OUT/t2_armT_$1.json $OUT/t2_armO_$1.json <<'PY' || ok=0
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop('numpy'); b.pop('numpy')
print(a['scene'], 'identical' if a == b else 'DIFFERENT', len(a['aabbs']), 'bodies, seg ids', a['seg_ids'])
sys.exit(0 if a == b else 1)
PY
done
[ $ok = 1 ] && status 2 PASS || status 2 FAIL

# Test 3: a RolloutHistory pickled under (A) loads in arm T's venv, with
# nothing of ours on the path.
rm -rf $OUT/t3_run
(cd $TW/tampura_environments && PATH=$VA:$PATH $VA/python -u run_planner.py \
   --config=./env_configs/find_dice.yml --global-seed=0 --max-steps=1 \
   --save-dir=$OUT/t3_run > $OUT/t3_console.txt 2>&1)
PKL=$(find $OUT/t3_run -name '*.pkl' | head -1)
if [ -n "$PKL" ] && (cd /tmp && env -u PYTHONPATH $VT/python -c "
import pickle, sys
h = pickle.load(open('$PKL', 'rb'))
print(type(h).__name__, 'rewards', list(h.rewards), 'steps', len(h.time_deltas))
assert not any('tampura_bridge' in m for m in sys.modules)
"); then status 3 PASS; else status 3 FAIL; fi

# Test 4: a smoke run of our holding scene under (A), then the ledger reader.
(cd $SB && $VA/python test_full_pipeline.py --no-gui --scene random-pairs \
   --seed 0 --goal holding --log-level quiet > $OUT/t4_console.txt 2>&1)
RUN=$(ls -td $SB/logs/run_* 2>/dev/null | head -1)
grep -E 'SUCCESS|FAILED' $OUT/t4_console.txt | tail -2
if grep -q 'SUCCESS' $OUT/t4_console.txt && \
   (cd $SB && $VA/python tools/bridge_gates.py ledger $RUN --m7 off); then
  status 4 PASS; else status 4 FAIL; fi
[ -n "$RUN" ] && cp $RUN/ledger.jsonl $OUT/t4_ledger.jsonl
cat $OUT/summary.txt
echo B1J_TESTS_DONE
