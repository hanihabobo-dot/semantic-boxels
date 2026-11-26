#!/bin/bash
#SBATCH --job-name=p4-fd
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=4:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# Path 14 (worker B, 2026-11-13): the candidates for the frozen default on
# find_dice through the bridge, ours against ours, no TAMPURA arm
# (tracks/meeting_2026-11-13/cluster_requests/B_find_dice_defaults_DRAFT.md).
# One script for both scene sets:
#   S  the shipped scenes as BF#59 ran them (seeds 0 to 19, the driver runs
#      from their tampura_environments, cap 600 s);
#   G  BF#63's generated scenes (tampura_bridge/gen_scenes/find_dice, every
#      episode in a fresh folder that holds only its scene, G19 pinned by
#      BRIDGE_SCENE_MANIFEST, cap 900 s).
# The harness is tools/slip_eval.py: every seed's arms back to back on this
# node, the first arm rotating by seed and repetition, every seed run REPS
# times.  The frame is tools/cluster/gen_eval.sbatch's: the per-run gates
# before the first episode (a failure runs nothing) and the tree check after
# the last; with P4_LOCAL=1 the job's folder is on the node's own disk and
# becomes one tarball on $W at the end (BF#63's slow hour: the pipeline
# writes its planning files under the episode's folder); the I/O probe
# writes a row every 20 s to OUT/io_probe.tsv in both modes.
# Usage (submit from the submit node, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w <node> --export=ALL,P4_LOCAL=1 $W/sb_<sha>/tools/cluster/fd_defaults.sbatch sb_<sha> S <arms> 0-9 3 [OUT]
#   sbatch -w <node> --export=ALL,P4_LOCAL=1 $W/sb_<sha>/tools/cluster/fd_defaults.sbatch sb_<sha> G <arms> 100-109 2 [OUT]
#   arguments: snapshot, scene set, arms (slip_eval's syntax, comma
#   separated: a+b, a+b@corridor_object), seeds, repetitions, OUT (optional:
#   a results directory shared by the jobs; each job writes
#   OUT/<set>_<job id>, or with P4_LOCAL=1 OUT/<set>_<job id>.tar.gz; read
#   them together with tools/fd_defaults_table.py).
set -uo pipefail
W=${P4_WORK:?the cluster work folder}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
SET=${2:?scene set: S or G}
ARMS=${3:?arms, e.g. a+b,a+b@corridor_object}
SEEDS=${4:?seeds, e.g. 0-9 or 100-109}
REPS=${5:-1}
JOB=${SLURM_JOB_ID:-local}
OUT=${6:-$W/results/fd_defaults_${SB##*/sb_}}/${SET}_$JOB
TW=$W/tampura-work
VA=$W/armO-venvA/bin
P4_LOCAL=${P4_LOCAL:-0}
LD=${P4_LOCAL_DIR:-/tmp}
case $SET in
  S) CAP=600; SCENES_ARG= ;;
  G) CAP=900; SCENES_ARG="--scenes $SB/tampura_bridge/gen_scenes/find_dice" ;;
  *) echo "the scene set must be S or G, not $SET: nothing run"; exit 1 ;;
esac
FINAL=$OUT
if [ "$P4_LOCAL" = 1 ]; then
  OUT=$LD/p4fd_$JOB
  if [ -e $FINAL ] || [ -e $FINAL.tar.gz ] || [ -e $OUT ]; then
    echo "P4_LOCAL: $FINAL, $FINAL.tar.gz or $OUT exists already: nothing run"; exit 1
  fi
  FREE=$(df -Pk $LD | awk 'NR == 2 {print $4}')
  if [ "${FREE:-0}" -lt 1048576 ]; then
    echo "P4_LOCAL: under 1 GiB free on $LD: nothing run"; df -h $LD; exit 1
  fi
fi
mkdir -p $OUT || { echo "cannot make $OUT: nothing run"; exit 1; }
# The probe: one row every 20 s while OUT/.probe_on exists, in seconds: to
# open a file on $W, to write 4 kB with fsync there, and the same locally.
io_probe() {
  local f=$W/inbox/.io_$JOB g=$LD/.io_$JOB t a b c d i
  printf 'time\tw_open_s\tw_write_fsync_s\tlocal_write_fsync_s\n' > $OUT/io_probe.tsv
  while [ -e $OUT/.probe_on ]; do
    t=$(date '+%F %T'); a=$(date +%s.%N)
    head -c 64 $SB/tools/slip_eval.py > /dev/null
    b=$(date +%s.%N)
    dd if=/dev/zero of=$f bs=4k count=1 conv=fsync status=none; rm -f $f
    c=$(date +%s.%N)
    dd if=/dev/zero of=$g bs=4k count=1 conv=fsync status=none; rm -f $g
    d=$(date +%s.%N)
    awk -v t="$t" -v a=$a -v b=$b -v c=$c -v d=$d \
      'BEGIN { printf "%s\t%.3f\t%.3f\t%.3f\n", t, b - a, c - b, d - c }' >> $OUT/io_probe.tsv
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      [ -e $OUT/.probe_on ] || break
      sleep 1
    done
  done
}
PROBE=
FINISHED=0
# Once, on every way out: the probe ends its row and stops (killed only if
# stuck past 10 s); with P4_LOCAL=1 the folder becomes OUT.tar.gz on $W.
finish() {
  [ $FINISHED = 1 ] && return
  FINISHED=1
  rm -f $OUT/.probe_on
  if [ -n "$PROBE" ]; then
    ( sleep 10; kill $PROBE 2>/dev/null ) &
    local dog=$!
    wait $PROBE 2>/dev/null
    kill $dog 2>/dev/null
    wait $dog 2>/dev/null
  fi
  rm -f $W/inbox/.io_$JOB $LD/.io_$JOB
  if [ "$P4_LOCAL" = 1 ]; then
    mkdir -p ${FINAL%/*}
    if tar -czf $FINAL.tar.gz -C $OUT .; then
      echo "results in $FINAL.tar.gz ($(du -h $FINAL.tar.gz | cut -f1)), $OUT removed"
      rm -rf $OUT
    else
      echo "P4_LOCAL: writing $FINAL.tar.gz FAILED; the results stay in $OUT on $(hostname)"
    fi
  else
    echo "results in $OUT"
  fi
}
trap finish EXIT
trap 'exit 143' TERM
touch $OUT/.probe_on
io_probe &
PROBE=$!
[ "$P4_LOCAL" = 1 ] && echo "P4_LOCAL: the job's folder is $OUT on $(hostname) ($(df -h $LD | awk 'NR == 2 {print $4}') free), then $FINAL.tar.gz"
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
# Set G alone: the manifest pins the generated scenes' seeds for G19.  Set S
# runs without it, as the BF#59 jobs did.
[ "$SET" = G ] && export BRIDGE_SCENE_MANIFEST=$SB/tampura_bridge/gen_scenes/find_dice/manifest.json
export PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  set $SET  arms $ARMS  seeds $SEEDS  reps $REPS  cap $CAP  out $OUT"
grep -m1 'model name' /proc/cpuinfo
# The gates run without arm O's PYTHONPATH, as in gen_eval.sbatch (with
# $TW/tampura on it G13's import check finds the checkout).  Their whole
# output goes to the job's log: a tail hid two FAIL lines on 2026-11-03.
(cd $SB && env -u PYTHONPATH $VA/python tools/bridge_gates.py all --save $OUT/g13_before.json) > $OUT/gates_before.txt 2>&1
GRC=$?
cat $OUT/gates_before.txt
if [ $GRC -ne 0 ]; then
  echo "per-run gates FAILED before the eval (exit $GRC): nothing run"
  exit 1
fi
$VA/python -u $SB/tools/slip_eval.py --snapshot $SB --out $OUT --arms "$ARMS" \
  --seeds $SEEDS --reps $REPS --rep-seeds $SEEDS --cap $CAP --rotate \
  --python $VA/python --cwd $TW/tampura_environments $SCENES_ARG
echo "harness rc $?"
(cd $SB && env -u PYTHONPATH $VA/python tools/bridge_gates.py tree --compare $OUT/g13_before.json) > $OUT/gates_after.txt 2>&1
echo "tree check rc $?"
cat $OUT/gates_after.txt
finish
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo FD_DONE
