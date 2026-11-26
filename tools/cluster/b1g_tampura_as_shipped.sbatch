#!/bin/bash
#SBATCH --job-name=p4-b1g-tampura
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=06:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# #P4 B1(g): TAMPURA as shipped, seeds 0-19, headless, once, under P4.6's
# MACHINE rule (an exclusive node, serial episodes, PYTHONHASHSEED 0, 900 s
# cap per episode).  Their run_planner.py and find_dice.yml run unchanged,
# through tools/tampura_sweep_cluster.py.  The node is pinned at submission
# (--nodelist) and named in the output.
set -euo pipefail
W=${P4_WORK:?the cluster work folder}
export TAMPURA_WORK=$W/tampura-work
export SWEEP_CONSOLE_DIR=$W/results/b1g/consoles
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0
mkdir -p $W/results/b1g $SWEEP_CONSOLE_DIR
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)"
grep -m1 'model name' /proc/cpuinfo
git -C $TAMPURA_WORK/tampura rev-parse HEAD
git -C $TAMPURA_WORK/tampura_environments rev-parse HEAD
git -C $TAMPURA_WORK/tampura_environments status --porcelain --untracked-files=no
sha256sum $TAMPURA_WORK/tampura_environments/tampura_environments/__init__.py
$TAMPURA_WORK/.venv/bin/python -m pip freeze | sha256sum
$TAMPURA_WORK/.venv/bin/python -u ${SWEEP_DRIVER:?path to tampura_sweep_cluster.py} \
  --seeds 0-19 --per-episode-timeout 900 \
  --out $W/results/b1g/tampura_as_shipped_seeds0-19.json
$TAMPURA_WORK/.venv/bin/python -m pip freeze | sha256sum
git -C $TAMPURA_WORK/tampura_environments status --porcelain --untracked-files=no
echo B1G_DONE
