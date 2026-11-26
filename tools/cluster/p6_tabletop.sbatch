#!/bin/bash
#SBATCH --job-name=p6-tabletop
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=12G
#SBATCH --time=14:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# Path 6 (cluster eval of our code now, our thesis code and TAMPURA), phase 1a:
# the tabletop benchmark.  One job runs two seed slots (tools/p6_slots.py), in
# each slot both arms (A: our code now, B: the thesis commit 6b00cd7), the
# order alternating by slot parity, one pipeline at a time, each arm through its
# own eval_runner (tools/cluster/p6_run.py).  Everything of the job lives on the
# node's own disk (P4_LOCAL_DIR, default /tmp, as BF#63 run 2: the NFS volume
# under $W stalled on 2026-11-03) and becomes one tarball on $W at the end.
#   - the two snapshots are copied to the node (the pipeline writes logs/ and
#     temp/ in its working directory); each copy is checked against the sha256
#     of every file of its read-only snapshot before the first cell and after
#     the last (the pipeline must not edit its own code): a failed check marks
#     the job VOID and nothing from it is counted;
#   - an I/O probe times, every 20 s, opening a file on $W, a 4 kB write with
#     fsync on $W and the same on the local disk (io_probe.tsv, with the epoch):
#     the stall rule of PLAN section 11 reads it;
#   - at the end logs/ and temp/ of the copies are deleted (the cells keep
#     timing_summary.json, stdout.log and run_dir.txt).
# Usage (submit from the submit node, after tools/cluster/push_snapshot.ps1 -CodeOnly for
# both snapshots; -w pins the job to its own node, so two of our pipelines never
# share a node):
#   sbatch -w <node> $W/sb_<A1>/tools/cluster/p6_tabletop.sbatch sb_<A1> sb_6b00cd7 <job 0-14 | smoke>
#   arguments: A's snapshot (also holds this script and the tools), B's snapshot,
#   the job number (slots 2J and 2J+1), or 'smoke' (the cluster smoke: the three
#   cells of the laptop smoke through B then A, then tools/p6_smoke_check.py), or
#   'redo' with a list file (the final pass, PLAN section 11: one line "A tag1,tag2"
#   or "B tag1,..." per run; cells that did not count, never a pre-flight rejection):
#   sbatch -w <node> .../p6_tabletop.sbatch sb_<A1> sb_6b00cd7 redo $W/inbox/p6_redo.txt
#   Results: $W/results/p6_<A sha>/<job, smoke or redo>_<slurm job>.tar.gz
set -uo pipefail
export LC_ALL=C
W=${P4_WORK:?the cluster work folder}
SNAP_A=$W/${1:?A snapshot dir, e.g. sb_1234567}
SNAP_B=$W/${2:?B snapshot dir, e.g. sb_6b00cd7}
MODE=${3:?job number 0-14, smoke, or redo}
REDO_LIST=${4:-}
JOB=${SLURM_JOB_ID:-local}
LD=${P4_LOCAL_DIR:-/tmp}
CAP=${P6_CAP:-1800}
# TB-24: P6_FRESH_STATS=1 (sbatch --export=ALL,P6_FRESH_STATS=1) removes each arm's statistics/
# (pddlstream's stream statistics, in the arm's code copy) before every cell, so that no cell
# starts from the measured times of the cells before it; 0 carries the file through the job.
STATS_ARG=
[ "${P6_FRESH_STATS:-0}" = 1 ] && STATS_ARG=--fresh-stream-stats
VA=$W/armO-venvA/bin
OUT=$LD/p6_$JOB
if [ "$MODE" = smoke ] || [ "$MODE" = redo ]; then LABEL=$MODE; else LABEL=$(printf 'job%02d' "$((10#$MODE))"); fi
FINAL=$W/results/p6_${SNAP_A##*/sb_}/${LABEL}_$JOB
for d in $SNAP_A $SNAP_B; do
  [ -d $d ] || { echo "no snapshot $d: nothing run"; exit 1; }
done
if [ "$MODE" = redo ] && [ ! -f "$REDO_LIST" ]; then
  echo "redo needs the list file as the fourth argument ($REDO_LIST): nothing run"; exit 1
fi
if [ -e $FINAL.tar.gz ] || [ -e $OUT ]; then
  echo "$FINAL.tar.gz or $OUT exists already: nothing run"; exit 1
fi
FREE=$(df -Pk $LD | awk 'NR == 2 {print $4}')
if [ "${FREE:-0}" -lt 1048576 ]; then
  echo "under 1 GiB free on $LD: nothing run"; df -h $LD; exit 1
fi
mkdir -p $OUT || { echo "cannot make $OUT: nothing run"; exit 1; }

# The probe: one row every 20 s while OUT/.probe_on exists.
io_probe() {
  local f=$W/inbox/.io_$JOB g=$LD/.io_$JOB t e a b c d i
  printf 'time\tepoch\tw_open_s\tw_write_fsync_s\tlocal_write_fsync_s\n' > $OUT/io_probe.tsv
  while [ -e $OUT/.probe_on ]; do
    t=$(date '+%F %T'); e=$(date +%s); a=$(date +%s.%N)
    head -c 64 $SNAP_A/tools/p6_slots.py > /dev/null
    b=$(date +%s.%N)
    dd if=/dev/zero of=$f bs=4k count=1 conv=fsync status=none; rm -f $f
    c=$(date +%s.%N)
    dd if=/dev/zero of=$g bs=4k count=1 conv=fsync status=none; rm -f $g
    d=$(date +%s.%N)
    awk -v t="$t" -v e=$e -v a=$a -v b=$b -v c=$c -v d=$d \
      'BEGIN { printf "%s\t%s\t%.3f\t%.3f\t%.3f\n", t, e, b - a, c - b, d - c }' >> $OUT/io_probe.tsv
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      [ -e $OUT/.probe_on ] || break
      sleep 1
    done
  done
}
PROBE=
FINISHED=0
# Once, on every way out: the probe ends its row and stops (killed only if
# stuck past 10 s) and the folder becomes FINAL.tar.gz on $W (without the code
# copies).
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
  mkdir -p ${FINAL%/*}
  if tar -czf $FINAL.tar.gz -C $OUT --exclude=./codeA --exclude=./codeB .; then
    echo "results in $FINAL.tar.gz ($(du -h $FINAL.tar.gz | cut -f1)), $OUT removed"
    rm -rf $OUT
  else
    echo "writing $FINAL.tar.gz FAILED; the results stay in $OUT on $(hostname)"
  fi
}
trap finish EXIT
trap 'exit 143' TERM
touch $OUT/.probe_on
io_probe &
PROBE=$!

hdr() { echo "$@" | tee -a $OUT/header.txt; }
hdr "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  mode $MODE  A $SNAP_A  B $SNAP_B  cap ${CAP}s  out $OUT"
hdr "cpu $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')  threads $(nproc --all)  allowed $(nproc)  load $(cut -d' ' -f1-3 /proc/loadavg)"
# rule 16 (PLAN section 17): the memory at the start, the kind of file system under $LD (tmpfs is RAM) and the job's --mem
hdr "memory at the start: $(awk '/^(MemTotal|MemAvailable):/ {printf "%s %s kB  ", $1, $2}' /proc/meminfo)local fs $LD $(df -PT $LD | awk 'NR == 2 {print $2}') (tmpfs is RAM), Slurm --mem ${SLURM_MEM_PER_NODE:-?} MB"
hdr "stream statistics (TB-24): $([ -n "$STATS_ARG" ] && echo 'removed before every cell (P6_FRESH_STATS=1)' || echo 'carried through the cells of an arm in this job (P6_FRESH_STATS=0)')"
hdr "python $($VA/python -c 'import sys, numpy, pybullet; print(sys.version.split()[0], "numpy", numpy.__version__, "pybullet", pybullet.getAPIVersion())' 2>&1 | tail -1)"
$VA/python -m pip freeze > $OUT/pip_freeze.txt 2>&1
hdr "pip freeze sha256 $(sha256sum < $OUT/pip_freeze.txt | cut -c1-16)"
export PYTHONHASHSEED=0 BOXEL_EYE_IMAGES=0 PYTHONDONTWRITEBYTECODE=1 PDDLSTREAM_PATH=$W/pddlstream_lib
unset PYTHONPATH
if [ "$MODE" != smoke ] && [ "$MODE" != redo ]; then     # a job number outside 0-14 runs nothing
  $VA/python $SNAP_A/tools/p6_slots.py job-slots $MODE > /dev/null 2>&1 || { hdr "bad job number $MODE: nothing run"; exit 1; }
fi

# The reference: the sha256 of every file of each read-only snapshot.
for X in A B; do
  eval "S=\$SNAP_$X"
  ( cd $S && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > $OUT/tree_$X.sha256
  hdr "snapshot $X ${S##*/}: $(wc -l < $OUT/tree_$X.sha256) files, tree hash $(sha256sum < $OUT/tree_$X.sha256 | cut -c1-32)"
  cp -r --no-preserve=mode $S $OUT/code$X || { hdr "copy of $S failed: nothing run"; exit 1; }
done
VOID=0
tree_check() {   # tree_check <A|B> <before|after>: the copy equals its snapshot, file by file
  local bad
  bad=$( cd $OUT/code$1 && sha256sum -c --quiet $OUT/tree_$1.sha256 2>&1 | head -5 )
  if [ -n "$bad" ]; then
    hdr "TREE CHECK FAILED ($1, $2): $bad"
    echo "arm $1 $2: $bad" >> $OUT/VOID
    VOID=1
    return 1
  fi
  hdr "tree check $1 $2: every file equals its snapshot's"
}
tree_check A before && tree_check B before || { hdr "nothing run"; exit 1; }

STRAYS=$OUT/strays.txt
run_p6() {   # run_p6 <A|B> <label> <p6_run.py arguments>: one arm's cells into OUT/<arm>/<label>
  local arm=$1 label=$2 rc
  shift 2
  echo "[p6] $(date -Is) start arm $arm $label"
  ( cd $OUT/code$arm && $VA/python -u $SNAP_A/tools/cluster/p6_run.py --arm $arm "$@" $STATS_ARG \
      --out $OUT/$arm/$label --timeout $CAP ) < /dev/null > $OUT/log_${arm}_$label.txt 2>&1
  rc=$?
  tail -n 4 $OUT/log_${arm}_$label.txt
  echo "[p6] $(date -Is) end arm $arm $label rc $rc"
  # rule 16: p6_run.py's exit code 4 is memwatch's stop (MemAvailable under 4 GB after a cell); the caller's
  # "|| ... break" then ends the job's remaining runs
  [ $rc = 4 ] && hdr "STOPPED_LOW_MEMORY arm $arm $label (rc 4): MemAvailable under 4 GB, the job stops after this run, see $arm/$label/STOPPED_LOW_MEMORY.txt"
  # informational: processes of ours still alive after a run (a cell cut at the cap
  # may leave its planner's children behind; they end with the job)
  { echo "after arm $arm $label $(date -Is):"; ps -u "$(id -un)" -o pid,ppid,etimes,args \
      | grep -E 'downward|translate|test_full_pipeline' | grep -v grep; } >> $STRAYS 2>&1
  return $rc
}

if [ "$MODE" = smoke ]; then
  for ARM in B A; do run_p6 $ARM slot_smoke --set smoke || { hdr "p6_run failed for arm $ARM: stopping"; break; }; done
elif [ "$MODE" = redo ]; then
  # the final pass: one line of the list is "A tag1,tag2,..." or "B tag1,...", run in file order
  N=0
  while read -r ARM TAGS; do
    [ -n "$ARM" ] || continue
    N=$((N + 1))
    run_p6 $ARM redo_$N --set all --only-tags "$TAGS" || { hdr "p6_run failed for arm $ARM redo $N: stopping"; break; }
  done < "$REDO_LIST"
else
  for S in $($VA/python $SNAP_A/tools/p6_slots.py job-slots $MODE); do
    for ARM in $($VA/python $SNAP_A/tools/p6_slots.py arm-order $S); do
      run_p6 $ARM slot_$S --set slot --slot $S || { hdr "p6_run failed for arm $ARM slot $S: stopping"; break 2; }
    done
  done
fi

tree_check A after; tree_check B after
for X in A B; do
  hdr "size of $X's logs/ and temp/ before they are deleted: $(du -sh --apparent-size $OUT/code$X/logs $OUT/code$X/temp 2>/dev/null | tr '\n' ' ')"
  rm -rf $OUT/code$X/logs $OUT/code$X/temp
done
if [ "$MODE" = smoke ]; then
  $VA/python $SNAP_A/tools/p6_smoke_check.py $OUT 2>&1 | tee $OUT/smoke_check.txt
fi
# rule 16: after the job nothing of ours alive and nothing in /dev/shm (counted here, listed in strays.txt; a stray
# is reported, never ended by name)
hdr "memory after the job: $(ps -u "$(id -un)" -o pid,args | grep -E 'downward|translate|test_full_pipeline' | grep -vc grep) pipeline processes of ours alive, $(ls /dev/shm | wc -l) names in /dev/shm, MemAvailable $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) kB"
hdr "job end $(date -Is) void=$VOID"
finish
# BF#49: the cluster's data hygiene after every run.
bash $SNAP_A/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo P6_DONE
