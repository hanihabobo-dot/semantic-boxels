#!/bin/bash
#SBATCH --job-name=p6-genscenes
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# Path 6, phase 1b: the fresh find_dice scenes (seeds 140 to 339) from TAMPURA's
# own generator, unmodified (tools/gen_find_dice_scenes.py, the BF#63 tool: scene
# s is the first scene their env_generator.py accepts after random.seed(s) and
# numpy.random.seed(s); nothing filtered, a seed without a scene is listed and
# never replaced).  Their tree under $W/tampura-work is only read.  The folder
# lives on the node's own disk and becomes one small tarball on $W; the
# scene files and the manifest are merged into the repository
# (tools/p6_merge_scenes.py) and pinned there by sha256 before any episode runs.
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w cn-1xx $W/sb_<A1>/tools/cluster/p6_gen_scenes.sbatch sb_<A1> 140-339
#   Result: $W/results/p6_<A sha>/gen_<seeds>_<job>.tar.gz (scenes/, gen.log, header.txt)
set -uo pipefail
export LC_ALL=C
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
SEEDS=${2:?scene seeds, e.g. 140-339}
JOB=${SLURM_JOB_ID:-local}
LD=${P4_LOCAL_DIR:-/tmp}
TW=$W/tampura-work
OUT=$LD/p6_gen_$JOB
FINAL=$W/results/p6_${SB##*/sb_}/gen_${SEEDS}_$JOB
if [ -e $FINAL.tar.gz ] || [ -e $OUT ]; then
  echo "$FINAL.tar.gz or $OUT exists already: nothing run"; exit 1
fi
mkdir -p $OUT/scenes || { echo "cannot make $OUT: nothing run"; exit 1; }
FINISHED=0
finish() {
  [ $FINISHED = 1 ] && return
  FINISHED=1
  mkdir -p ${FINAL%/*}
  if tar -czf $FINAL.tar.gz -C $OUT --exclude=./scratch .; then
    echo "results in $FINAL.tar.gz ($(du -h $FINAL.tar.gz | cut -f1)), $OUT removed"
    rm -rf $OUT
  else
    echo "writing $FINAL.tar.gz FAILED; the results stay in $OUT on $(hostname)"
  fi
}
trap finish EXIT
trap 'exit 143' TERM
hdr() { echo "$@" | tee -a $OUT/header.txt; }
hdr "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  seeds $SEEDS  out $OUT"
hdr "cpu $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')  allowed $(nproc)"
hdr "their python $($TW/.venv/bin/python -c 'import sys, numpy; print(sys.version.split()[0], "numpy", numpy.__version__)' 2>&1 | tail -1)"
hdr "generator sha256 $(sha256sum $TW/tampura_environments/tampura_environments/find_dice/env_generator.py 2>/dev/null | cut -c1-16)  (their tree, read only)"
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$TW/tampura:$TW/tampura_environments
$TW/.venv/bin/python -u $SB/tools/gen_find_dice_scenes.py --seeds $SEEDS \
  --their-envs $TW/tampura_environments --out $OUT/scenes --scratch $OUT/scratch \
  --jobs 8 --timeout 600 > $OUT/gen.log 2>&1
hdr "generator rc $?  $(tail -n 1 $OUT/gen.log)"
hdr "job end $(date -Is)"
finish
echo P6_GEN_DONE
