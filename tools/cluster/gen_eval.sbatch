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
# P4_LOCAL=1 (BF#63's second run): the job's folder is on the node's own
# disk (P4_LOCAL_DIR, default /tmp) for the whole run, and at the end it
# becomes one tarball, OUT.tar.gz, on $W.  On 2026-11-03, from about 21:00
# to 22:00, the NFS volume under $W slowed the episodes' planning (it
# writes its files in the episode's folder) 15 to 24 times on all ten nodes
# at once while execution kept its speed, and all 14 of TAMPURA's timeouts
# began in that hour.  The code and the venvs stay on $W (only read, and
# cached after the first episode).  In both modes an I/O probe times, every
# 20 s, opening a file on $W, a 4 kB write with fsync on $W and the same
# write on the local disk (OUT/io_probe.tsv), so a slow volume shows in
# the record.
# Usage (submit from cn-04, after tools/cluster/push_snapshot.ps1 -CodeOnly):
#   sbatch -w cn-1xx [--export=ALL,P4_LOCAL=1] $W/sb_<sha>/tools/cluster/gen_eval.sbatch sb_<sha> 100-103 2 [OUT]
#   arguments: snapshot, scene seeds, repetitions, OUT (optional: a results
#   directory shared by the jobs; each job writes OUT/<job id>, or with
#   P4_LOCAL=1 OUT/<job id>.tar.gz; read them together with
#   tools/gen_scene_eval.py --report <the job folders>), and a second
#   snapshot (optional, path 6's arm O2: arm O's snapshot plus TB-1 only; the
#   job then runs T, O and O2 back to back on each scene, runs the gates on
#   that tree too, and the harness stops unless the two snapshots hold the same
#   scene files).  Pass OUT as '-' to keep its default when giving the fifth.
set -uo pipefail
W=${P4_WORK:-/work/rleap1/hani.alassiri.alhabboub/p4}
SB=$W/${1:?snapshot dir, e.g. sb_1234567}
SEEDS=${2:?scene seeds, e.g. 100-103}
REPS=${3:-2}
JOB=${SLURM_JOB_ID:-local}
OUTBASE=${4:--}
[ "$OUTBASE" = - ] && OUTBASE=$W/results/gen_${SB##*/sb_}
OUT=$OUTBASE/$JOB
SB2=${5:+$W/$5}
TW=$W/tampura-work
VA=$W/armO-venvA/bin
P4_LOCAL=${P4_LOCAL:-0}
LD=${P4_LOCAL_DIR:-/tmp}
FINAL=$OUT
if [ "$P4_LOCAL" = 1 ]; then
  OUT=$LD/p4gen_$JOB
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
    head -c 64 $SB/tools/gen_scene_eval.py > /dev/null
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
export BRIDGE_SCENE_MANIFEST=$SB/tampura_bridge/gen_scenes/find_dice/manifest.json
export PYTHONPATH=$SB:$W/pddlstream_lib:$TW/tampura:$TW/tampura_environments
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)  snapshot $SB  scenes $SEEDS  reps $REPS  out $OUT"
grep -m1 'model name' /proc/cpuinfo
# rule 16 (PLAN section 17): the memory at the start, the kind of file system under $LD (tmpfs is RAM) and the job's --mem
echo "memory at the start: $(awk '/^(MemTotal|MemAvailable):/ {printf "%s %s kB  ", $1, $2}' /proc/meminfo)local fs $LD $(df -PT $LD | awk 'NR == 2 {print $2}') (tmpfs is RAM), Slurm --mem ${SLURM_MEM_PER_NODE:-?} MB" | tee -a $OUT/memory_lines.txt
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
ARMS_ARGS=
if [ -n "$SB2" ]; then
  [ -d $SB2 ] || { echo "no second snapshot $SB2: nothing run"; exit 1; }
  (cd $SB2 && env -u PYTHONPATH $VA/python tools/bridge_gates.py all --save $OUT/g13_o2_before.json) > $OUT/gates_o2_before.txt 2>&1
  GRC2=$?
  cat $OUT/gates_o2_before.txt
  if [ $GRC2 -ne 0 ]; then
    echo "per-run gates FAILED on the second snapshot before the eval: nothing run"
    exit 1
  fi
  ARMS_ARGS="--arms T,O,O2 --snapshot-o2 $SB2"
  echo "arms T, O ($SB) and O2 ($SB2)"
fi
# The cap is B8's pre-registered 900 s (D10), the same for both arms: on
# the new scenes (up to five cups) TAMPURA's loop may run past BF#59's 600 s.
$VA/python -u $SB/tools/gen_scene_eval.py --snapshot $SB --out $OUT --seeds $SEEDS \
  --reps $REPS --cap 900 --python-o $VA/python --venv-t $TW/.venv --tampura-work $TW $ARMS_ARGS
HRC=$?
echo "harness rc $HRC"
# rule 16: exit code 4 is memwatch's stop (MemAvailable under 4 GB after an episode, STOPPED_LOW_MEMORY.txt in OUT)
[ $HRC = 4 ] && echo "STOPPED_LOW_MEMORY: the harness stopped on MemAvailable under 4 GB (rc 4), see $OUT/STOPPED_LOW_MEMORY.txt"
(cd $SB && env -u PYTHONPATH $VA/python tools/bridge_gates.py tree --compare $OUT/g13_before.json) > $OUT/gates_after.txt 2>&1
cat $OUT/gates_after.txt
if [ -n "$SB2" ]; then
  (cd $SB2 && env -u PYTHONPATH $VA/python tools/bridge_gates.py tree --compare $OUT/g13_o2_before.json) > $OUT/gates_o2_after.txt 2>&1
  cat $OUT/gates_o2_after.txt
fi
# rule 16: after the job nothing of ours alive and nothing in /dev/shm (counted here; a stray is reported, never
# ended by name)
echo "memory after the job: $(ps -u "$(id -un)" -o pid,args | grep -E 'downward|translate|test_full_pipeline|run_tampura_timed' | grep -vc grep) pipeline processes of ours alive, $(ls /dev/shm | wc -l) names in /dev/shm, MemAvailable $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) kB" | tee -a $OUT/memory_lines.txt
finish
# BF#49: the cluster's data hygiene after every run.
bash $SB/tools/cluster/prune_work.sh --apply || echo "prune_work rc $?"
echo GEN_DONE
