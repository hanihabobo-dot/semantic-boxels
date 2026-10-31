#!/bin/bash
# BF#59: the checks of one checkout (the main one or a campaign worktree) in
# WSL, arm O's venv: the unit tests, the bridge tests, the static gates and
# one headless find_dice episode, every run under the pipeline lock (two
# episode runs at once corrupt pddlstream's temp/; the lock serialises the
# campaign's worktrees).  Outputs under the checkout's
# archive/.../BF59_slip/checks/<stamp>/ (untracked; garbage once recorded).
#   bash tools/slip_check.sh <checkout, WSL path> [seed] [fixes]
#   e.g. bash tools/slip_check.sh /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-grasp_align 0 grasp_align
set -u
S=${1:?the checkout as a WSL path}
SEED=${2:-0}
FIXES=${3:-}
TW=/root/tampura-work
LIB=/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib
LOCK=/root/sb_pipeline.lock
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:$LIB:$TW/tampura:$TW/tampura_environments
PY=/root/armO-venvA/bin/python
OUT=$S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/checks/$(date +%Y-%m-%d_%H-%M-%S)_s${SEED}${FIXES:+_$FIXES}
mkdir -p $OUT
# The branch from the checkout's HEAD file (WSL git cannot follow a
# worktree's Windows gitdir; Windows git is the one that manages them).
GITDIR=$(sed -n 's/^gitdir: //p' $S/.git 2>/dev/null | sed 's#^\([A-Za-z]\):#/mnt/\L\1#')
[ -z "$GITDIR" ] && GITDIR=$S/.git
echo "== checkout $S  branch $(sed -n 's#^ref: refs/heads/##p' $GITDIR/HEAD 2>/dev/null)"
echo "== tests"
(cd $S && flock $LOCK $PY -m pytest tests -q 2>&1 | tail -4) | tee $OUT/tests.txt
echo "== bridge tests"
(cd $TW/tampura_environments && flock $LOCK $PY -m pytest -q $S/tampura_bridge/tests 2>&1 | tail -4) | tee $OUT/bridge_tests.txt
echo "== static gates"
(cd $S && $PY tools/bridge_gates.py static 2>&1 | tail -3) | tee $OUT/static.txt
echo "== episode seed $SEED, fixes '${FIXES}' (locked)"
cd $TW/tampura_environments
T0=$(date +%s)
flock $LOCK $PY $S/tampura_bridge/run_bridge_on_finddice.py --global-seed $SEED --vis 0 \
  --allow-g19-mismatch 1 --slip-fixes "$FIXES" --save-dir $OUT/ep > $OUT/ep_stdout.txt 2>&1
echo "rc $? after $(( $(date +%s) - T0 )) s: $(grep -o 'outcome [a-z_]*' $OUT/ep_stdout.txt | tail -1)"
grep -o '"slip_fixes": "[^"]*"' $OUT/ep/bridge_episode.json 2>/dev/null | head -1
grep -c 'firm grip on dice' $OUT/ep_stdout.txt | sed 's/^/die carries /'
echo "checks in $OUT"
