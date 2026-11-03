#!/bin/bash
#SBATCH --job-name=p4-gen
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=12:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# BF#63: both arms (TAMPURA as shipped, then ours with BF#62's defaults) on
# find_dice scenes made by their own generator (tampura_bridge/gen_scenes/,
# tools/gen_scene_eval.py), interleaved per scene on one shared node like
# the BF#59 jobs (8 CPUs, 24 GB).  One job per group of scenes, each pinned
# to a different node (-w), so two of our pipelines never share a node.
# The per-run gates run before the first episode and the tree check after
# the last.  Failure screenshots: the harness's default (--shots failures)
# keeps every run that is not a counted success under OUT/failures/ with
# its metadata (arm O's episodes get BOXEL_EYE_IMAGES=1 from the harness);
# pull them into archive/ before the results compact (two days).
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w cn-1xx $W/sb_<sha>/tools/cluster/gen_eval.sbatch sb_<sha> 100-103 2 [OUT]
#   arguments: snapshot, scene seeds, repetitions, OUT (optional: a results
#   directory shared by the jobs; each job writes OUT/<job id>; read them
#   together with tools/gen_scene_eval.py --report OUT).
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
SEEDS=${2:?scene seeds, e.g. 100-103}
REPS=${3:-2}
OUT=${4:-$W/results/gen_${SB##*/sb_}}/${SLURM_JOB_ID:-local}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
mkdir -p $OUT
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export BRIDGE_SCENE_MANIFEST=$SB/tampura_bridge/gen_scenes/find_dice/manifest.json
export PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  scenes $SEEDS  reps $REPS  out $OUT"
grep -m1 'model name' /proc/cpuinfo
# The gates run without arm O's PYTHONPATH, as in slip_t.sbatch: with
# $TW/tampura on it, G13's import check finds the checkout instead of arm
# T's install and fails (it failed jobs 5061712 to 5061721), and pip freeze
# lists the path's packages too.  Arm T's episodes never see it (child_env
# sets their PYTHONPATH to the snapshot); arm O's need it.
(cd $SB && env -u PYTHONPATH $VA/python tools/bridge_gates.py all --save $OUT/g13_before.json) > $OUT/gates_before.txt 2>&1
GRC=$?
cat $OUT/gates_before.txt
if [ $GRC -ne 0 ]; then
  echo "per-run gates FAILED before the eval: nothing run"
  exit 1
fi
# The cap is B8's pre-registered 900 s (D10), the same for both arms: on
# the new scenes (up to five cups) TAMPURA's loop may run past BF#59's 600 s.
$VA/python -u $SB/tools/gen_scene_eval.py --snapshot $SB --out $OUT --seeds $SEEDS \
  --reps $REPS --cap 900 --python-o $VA/python --venv-t $TW/.venv --tampura-work $TW
echo "harness rc $?"
(cd $SB && env -u PYTHONPATH $VA/python tools/bridge_gates.py tree --compare $OUT/g13_before.json) > $OUT/gates_after.txt 2>&1
cat $OUT/gates_after.txt
echo "results in $OUT"
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo GEN_DONE
