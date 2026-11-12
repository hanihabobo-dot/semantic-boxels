#!/bin/bash
#SBATCH --job-name=p4-cu
#SBATCH --partition=rleap_cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=12:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# Q42: TAMPURA (arm T) on its own task class_uncertain, seeds 0 to 19, for path 7's table.
# PREPARED, NOT RUN: no job of this script may be submitted before Hani's yes to the cluster
# question, asked alone by the coordinator (tracks/eval/RUN_SHEET.md).
# One job per group of seeds, each pinned to a node of its own (-w), 8 CPUs and 24 GB as
# find_dice's jobs (gen_eval.sbatch), so the node's load is the job's own.  Every episode is one
# process: their run_planner.py through tools/cluster/cu_t.py (their file run as it is, one read
# of their world after their rollout), started by tools/cu_eval.py in THEIR venv from a scratch
# directory of its own on the node's disk.  Their tree on $W is read, never written: the files
# an episode reads are hashed before the first and after the last episode, and a difference is
# printed as TREE CHANGED.
# P4_LOCAL=1 (as BF#63's second run): the job's folder is on the node's own disk (P4_LOCAL_DIR,
# default /tmp) for the whole run and becomes one tarball, OUT.tar.gz, on $W at the end; the
# I/O probe of gen_eval.sbatch runs in both modes (OUT/io_probe.tsv).
# The other arms of path 7's table (A1, A0, their random policy: minutes each) are NOT in this
# script yet: their command lines are worker S's sheet of 13 Nov, and the snapshot must hold
# tasks_probe/ (track/tasks merged before the freeze); this script needs tasks_probe/cu_rand.py
# for the world-state test and stops before the first episode without it.
# Usage (from cn-04, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w cn-1xx --export=ALL,P4_LOCAL=1 $W/sb_<sha>/tools/cluster/cu_eval.sbatch sb_<sha> 0-4 3 [OUT]
#   arguments: snapshot, seeds, repetitions (default 3), OUT (optional: a results directory shared
#   by the jobs; each job writes OUT/<job id>, or with P4_LOCAL=1 OUT/<job id>.tar.gz; count them
#   together with tools/cu_eval.py --report <the job folders>).
#   CU_CAP (s, default 3600): the wall cap of one episode.  CU_HASHSEED (default 0, or unset):
#   PYTHONHASHSEED of every episode.  CU_DRY=1: print the episodes and their commands, run nothing.
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
SEEDS=${2:?seeds, e.g. 0-4}
REPS=${3:-3}
JOB=${SLURM_JOB_ID:-local}
OUTBASE=${4:--}
[ "$OUTBASE" = - ] && OUTBASE=$W/results/cu_${SB##*/sb_}
OUT=$OUTBASE/$JOB
TW=$W/tampura-work
VA=$W/armO-venvA/bin
CAP=${CU_CAP:-3600}
HASHSEED=${CU_HASHSEED:-0}
P4_LOCAL=${P4_LOCAL:-0}
LD=${P4_LOCAL_DIR:-/tmp}
FINAL=$OUT
if [ "${CU_DRY:-0}" = 1 ]; then
  $VA/python -u $SB/tools/cu_eval.py --snapshot $SB --out $OUT --seeds $SEEDS --reps $REPS --cap $CAP \
    --venv-t $TW/.venv --tampura-work $TW --scratch $LD --hashseed $HASHSEED --dry-run
  exit $?
fi
if [ "$P4_LOCAL" = 1 ]; then
  OUT=$LD/p4cu_$JOB
  if [ -e $FINAL ] || [ -e $FINAL.tar.gz ] || [ -e $OUT ]; then
    echo "P4_LOCAL: $FINAL, $FINAL.tar.gz or $OUT exists already: nothing run"; exit 1
  fi
  FREE=$(df -Pk $LD | awk 'NR == 2 {print $4}')
  if [ "${FREE:-0}" -lt 1048576 ]; then
    echo "P4_LOCAL: under 1 GiB free on $LD: nothing run"; df -h $LD; exit 1
  fi
fi
mkdir -p $OUT || { echo "cannot make $OUT: nothing run"; exit 1; }
# The probe: one row every 20 s while OUT/.probe_on exists, in seconds: to open a file on $W, to
# write 4 kB with fsync there, and the same locally (gen_eval.sbatch's, unchanged).
io_probe() {
  local f=$W/inbox/.io_$JOB g=$LD/.io_$JOB t a b c d i
  printf 'time\tw_open_s\tw_write_fsync_s\tlocal_write_fsync_s\n' > $OUT/io_probe.tsv
  while [ -e $OUT/.probe_on ]; do
    t=$(date '+%F %T'); a=$(date +%s.%N)
    head -c 64 $SB/tools/cu_eval.py > /dev/null
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
# Once, on every way out: the probe ends its row and stops (ended only if stuck past 10 s); with
# P4_LOCAL=1 the folder becomes OUT.tar.gz on $W.
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
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  seeds $SEEDS  reps $REPS  cap $CAP s  hash seed $HASHSEED  out $OUT"
grep -m1 'model name' /proc/cpuinfo
# rule 16 (PLAN section 17): the memory at the start, the kind of file system under $LD (tmpfs is RAM) and the job's --mem
echo "memory at the start: $(awk '/^(MemTotal|MemAvailable):/ {printf "%s %s kB  ", $1, $2}' /proc/meminfo)local fs $LD $(df -PT $LD | awk 'NR == 2 {print $2}') (tmpfs is RAM), Slurm --mem ${SLURM_MEM_PER_NODE:-?} MB" | tee -a $OUT/memory_lines.txt
# Their tree, as the episodes read it: one hash over the files of their two packages, their
# driver and their configs.  The same list after the last episode must give the same hash.
tree_hash() {
  ( cd $TW && find tampura/tampura tampura_environments/tampura_environments tampura_environments/env_configs \
      tampura_environments/run_planner.py -type f \( -name '*.py' -o -name '*.yml' -o -name '*.json' -o -name '*.pddl' \) \
      -print0 | sort -z | xargs -0 sha256sum ) > $OUT/$1
  echo "$(sha256sum < $OUT/$1 | cut -d' ' -f1)  $(wc -l < $OUT/$1) files"
}
TREE_BEFORE=$(tree_hash tree_before.txt)
echo "their tree before: $TREE_BEFORE"
$TW/.venv/bin/python -m pip freeze > $OUT/pip_freeze_t.txt 2>&1 || echo "pip freeze of their venv failed (recorded, not a stop)"
$VA/python -u $SB/tools/cu_eval.py --snapshot $SB --out $OUT --seeds $SEEDS --reps $REPS --cap $CAP \
  --venv-t $TW/.venv --tampura-work $TW --scratch $LD --hashseed $HASHSEED
HRC=$?
echo "harness rc $HRC"
# rule 16: exit code 4 is memwatch's stop (MemAvailable under 4 GB after an episode, STOPPED_LOW_MEMORY.txt in OUT)
[ $HRC = 4 ] && echo "STOPPED_LOW_MEMORY: the harness stopped on MemAvailable under 4 GB (rc 4), see $OUT/STOPPED_LOW_MEMORY.txt"
TREE_AFTER=$(tree_hash tree_after.txt)
if [ "$TREE_AFTER" = "$TREE_BEFORE" ]; then
  echo "their tree after: unchanged ($TREE_AFTER)"
else
  echo "TREE CHANGED: before $TREE_BEFORE, after $TREE_AFTER (diff $OUT/tree_before.txt $OUT/tree_after.txt)"
fi
# rule 16: after the job nothing of ours alive and nothing in /dev/shm (counted here; a stray is reported, never
# ended by name)
echo "memory after the job: $(ps -u "$(id -un)" -o pid,args | grep -E 'cu_t\.py|run_planner|symk|downward' | grep -vc grep) planner processes of ours alive, $(ls /dev/shm | wc -l) names in /dev/shm, MemAvailable $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) kB" | tee -a $OUT/memory_lines.txt
finish
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo CU_DONE
