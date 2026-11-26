#!/bin/bash
#SBATCH --job-name=C-bf70-time
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=02:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# BF#70's timing check on a cluster node (worker C; the pairs declared in tracks/eval/STATE.md,
# trunk c21f73f; the request: tracks/meeting_2026-11-13/cluster_requests/C_bf70_timing.md).
# PREPARED, NOT RUN: no job of this script may be submitted before the coordinator's word.
# What it measures: does the final-world wrapper (tampura_bridge/timed_policy.py, one read after
# their rollout) cost arm T wall time?  Eight arm T episodes on generated scene 113, one after
# the other on one node:
#   00 W, 01 N    one warm-up per snapshot, discarded as declared
#   02 W, 03 N    pair 1
#   04 N, 05 W    pair 2 (the order alternates)
#   06 W, 07 N    pair 3
# W = the snapshot with the wrapper (track/eval), N = a snapshot without it whose arm T files are
# the tag's byte for byte (sb_51428d8 is one).  The episode is the harness's arm T episode
# (tools/_bridge_campaign.py episode_t: their driver copy, find_dice.yml, planner
# tampura_policy_timed, the scene pinned in the working directory, PYTHONPATH = the snapshot,
# PYTHONHASHSEED=0), wrapped in tools/cluster/rusage_run.py, which records wall, CPU, peak RSS and
# blocks read per episode (its own interpreter runs isolated, -I, so the episode's PYTHONPATH
# reaches the episode only).  The header prints sha256 of the files arm T's process loads from each
# snapshot.  The episode folders are on the node's own disk (P4_LOCAL_DIR, default /tmp); at the
# end one tarball on $W without their history pickles (the check reads the console, the spans,
# final_world.json, g13_runtime.json and rusage.json).  This job does NOT call prune_work.sh: it
# touches nothing on $W but its own tarball and its own log.
# Usage (from the submit node, after tools/cluster/push_snapshot.ps1 -CodeOnly for the W snapshot):
#   sbatch -w <node> $W/sb_<W sha>/tools/cluster/bf70_timing.sbatch sb_<W sha> sb_51428d8 [113] [OUT]
#   BF70_ORDER (default "00_W 01_N 02_W 03_N 04_N 05_W 06_W 07_N"), BF70_CAP (s, default 960, the
#   laptop batch's cap), BF70_PAUSE (s between episodes, default 30).
set -uo pipefail
W=${P4_WORK:?the cluster work folder}
SNAP_W=$W/${1:?the snapshot with the wrapper, e.g. sb_1234567}
SNAP_N=$W/${2:?the snapshot without it, e.g. sb_51428d8}
SEED=${3:-113}
JOB=${SLURM_JOB_ID:-local}
OUTBASE=${4:--}
[ "$OUTBASE" = - ] && OUTBASE=$W/results/bf70_${SNAP_W##*/sb_}
FINAL=$OUTBASE/$JOB
LD=${P4_LOCAL_DIR:-/tmp}
OUT=$LD/p4bf70_$JOB
TW=$W/tampura-work
VA=$W/armO-venvA/bin
ORDER=${BF70_ORDER:-00_W 01_N 02_W 03_N 04_N 05_W 06_W 07_N}
CAP=${BF70_CAP:-960}
PAUSE=${BF70_PAUSE:-30}
SCENE=tampura_bridge/gen_scenes/find_dice/find_dice_gen_s$SEED.json
for d in $SNAP_W $SNAP_N $TW/.venv/bin; do
  [ -d $d ] || { echo "$d is missing: nothing run"; exit 1; }
done
for f in $SNAP_W/tools/cluster/rusage_run.py $SNAP_W/$SCENE $SNAP_N/$SCENE $SNAP_W/tampura_bridge/final_world.py; do
  [ -f $f ] || { echo "$f is missing: nothing run"; exit 1; }
done
if [ -e $SNAP_N/tampura_bridge/final_world.py ]; then
  echo "$SNAP_N holds tampura_bridge/final_world.py, so it has the wrapper too: nothing run"; exit 1
fi
cmp -s $SNAP_W/$SCENE $SNAP_N/$SCENE || { echo "the two snapshots hold different files for scene $SEED: nothing run"; exit 1; }
if [ -e $FINAL.tar.gz ] || [ -e $OUT ]; then
  echo "$FINAL.tar.gz or $OUT exists already: nothing run"; exit 1
fi
FREE=$(df -Pk $LD | awk 'NR == 2 {print $4}')
if [ "${FREE:-0}" -lt 1048576 ]; then
  echo "under 1 GiB free on $LD: nothing run"; df -h $LD; exit 1
fi
mkdir -p $OUT || { echo "cannot make $OUT: nothing run"; exit 1; }
FINISHED=0
# Once, on every way out: the folder becomes one tarball on $W (without their history pickles).
finish() {
  [ $FINISHED = 1 ] && return
  FINISHED=1
  mkdir -p ${FINAL%/*}
  if tar -czf $FINAL.tar.gz --exclude='*.pkl' -C $OUT .; then
    echo "results in $FINAL.tar.gz ($(du -h $FINAL.tar.gz | cut -f1)), $OUT removed"
    rm -rf $OUT
  else
    echo "writing $FINAL.tar.gz FAILED; the results stay in $OUT on $(hostname)"
  fi
}
trap finish EXIT
trap 'exit 143' TERM
{
  echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  W $SNAP_W  N $SNAP_N  scene $SEED  order $ORDER  cap $CAP s  pause $PAUSE s  out $OUT"
  grep -m1 'model name' /proc/cpuinfo
  echo "memory at the start: $(awk '/^(MemTotal|MemAvailable):/ {printf "%s %s kB  ", $1, $2}' /proc/meminfo)local fs $LD $(df -PT $LD | awk 'NR == 2 {print $2}') (tmpfs is RAM), Slurm --mem ${SLURM_MEM_PER_NODE:-?} MB, load $(cut -d' ' -f1-3 /proc/loadavg)"
  echo "the files arm T's process loads, sha256 per snapshot:"
  for s in $SNAP_W $SNAP_N; do
    for f in tools/run_tampura_timed.py tampura_bridge/__init__.py tampura_bridge/timed_policy.py tampura_bridge/g13_runtime.py tampura_bridge/final_world.py; do
      if [ -f $s/$f ]; then echo "  $(sha256sum < $s/$f | cut -d' ' -f1)  ${s##*/}/$f"; else echo "  (not in this snapshot)  ${s##*/}/$f"; fi
    done
  done
} | tee $OUT/header.txt
printf 'episode\tarm\trc\twall_s\tuser_s\tsys_s\tmax_rss_kb\tinblock\tmajflt\tsteps\tactions_sha\trewards\n' > $OUT/episodes.tsv
for e in $ORDER; do
  IDX=${e%%_*}
  ARM=${e##*_}
  case "$ARM" in
    W) SNAP=$SNAP_W ;;
    N) SNAP=$SNAP_N ;;
    *) echo "bad episode name $e in the order: stopped"; exit 2 ;;
  esac
  D=$OUT/$e
  mkdir -p $D/tampura_environments/find_dice/problems $D/save
  cp $SNAP_W/$SCENE $D/tampura_environments/find_dice/problems/
  ln -sfn $TW/tampura_environments/env_configs $D/env_configs
  echo "episode $e ($(date '+%T'), load $(cut -d' ' -f1-3 /proc/loadavg)) ..."
  (cd $D && PATH=$TW/.venv/bin:$PATH VIRTUAL_ENV=$TW/.venv PYTHONPATH=$SNAP PYTHONHASHSEED=0 \
     PYTHONDONTWRITEBYTECODE=1 BOXEL_EYE_IMAGES=0 TAMPURA_WORK=$TW \
     $VA/python -I -B $SNAP_W/tools/cluster/rusage_run.py $D/rusage.json $CAP $D/console.txt -- \
     $TW/.venv/bin/python -u $SNAP/tools/run_tampura_timed.py --config ./env_configs/find_dice.yml \
     --planner tampura_policy_timed --global-seed $SEED --save-dir $D/save)
  STEPS=$(grep -c '^==========t=' $D/console.txt)
  ASHA=$(grep '^Action:' $D/console.txt | sha256sum | cut -c1-12)
  REW=$(grep '^Next Reward:' $D/console.txt | awk '{print $3}' | tr '\n' ' ')
  $VA/python -B -c "import json, sys; r = json.load(open(sys.argv[1])); print('\t'.join(str(x) for x in (sys.argv[2], sys.argv[3], r['rc'], r['wall_s'], r['user_s'], r['sys_s'], r['max_rss_kb'], r['inblock'], r['majflt'], sys.argv[4], sys.argv[5], sys.argv[6])))" \
    $D/rusage.json $IDX $ARM "$STEPS" "$ASHA" "$REW" >> $OUT/episodes.tsv
  tail -n 1 $OUT/episodes.tsv
  [ -e $D/save/final_world.json ] && echo "  final_world.json written (the wrapper ran)"
  sleep $PAUSE
done
echo "--- the episodes"
cat $OUT/episodes.tsv
echo "after the job: $(ps -u "$(id -un)" -o pid,args | grep -E 'run_tampura_timed|symk|downward' | grep -vc grep) planner processes of ours alive, $(ls /dev/shm | wc -l) names in /dev/shm, MemAvailable $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) kB"
finish
echo BF70_TIMING_DONE
