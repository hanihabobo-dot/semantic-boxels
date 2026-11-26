#!/bin/bash
# Our data on the i6 cluster (user policy 2026-10-30, PAPER_AUDIT BF#49):
# compacted after two days, deleted after ninety, and never more than 1 GiB
# over inbox/ + sb_*/ (snapshots) + results/ + logs/ under $W, counted in
# allocated bytes (what the volume holds; BF#55).  The
# environment (the venvs, tampura-work, pddlstream_lib, python, tools) is
# reported, not counted.
#   inbox:     the archive of an unpacked snapshot or lib goes at once; any
#              other file after DELETE_DAYS
#   results:   a campaign directory older than COMPACT_DAYS becomes one
#              <name>.tar.gz; a tarball older than DELETE_DAYS goes
#   logs:      job logs older than COMPACT_DAYS are gzipped; gz older than
#              DELETE_DAYS go
#   snapshots: an sb_<sha> no queued or running job of mine references
#              (scontrol's Command) and older than SNAP_DAYS goes
#   cap:       then, while used + reserve > CAP, the oldest unreferenced
#              snapshot goes, then the oldest results tarball; a referenced
#              snapshot or a results directory younger than COMPACT_DAYS never
# Dry run unless --apply.  --reserve BYTES makes room before an upload
# (tools/cluster/push_snapshot.ps1 passes twice the archive's size).  Exit 3
# when the cap cannot be met.  Runs at the end of every campaign job
# (b8_campaign.sbatch), weekly from the laptop (tools/cluster/prune_work.ps1)
# and weekly from the submit node's crontab ($W/prune_work.sh).
#   bash prune_work.sh [--apply] [--reserve BYTES] [--cap-gib N]
set -uo pipefail
W=${P4_WORK:?the cluster work folder}
CAP=$((1024 * 1024 * 1024)); APPLY=0; RESERVE=0
COMPACT_DAYS=2; SNAP_DAYS=14; DELETE_DAYS=90
while [ $# -gt 0 ]; do
  case $1 in
    --apply) APPLY=1 ;;
    --reserve) RESERVE=$2; shift ;;
    --cap-gib) CAP=$(($2 * 1024 * 1024 * 1024)); shift ;;
    *) echo "prune_work: unknown argument $1"; exit 2 ;;
  esac
  shift
done
run() { if [ $APPLY = 1 ]; then "$@"; else echo "  would: $*"; fi; }
# BF#55: allocated bytes (-B1), not apparent (-b): TAMPURA's per-episode
# pickles hold ten times less on the volume than their apparent size, and the
# apparent count refused a push at 690 MiB allocated.
used() { du -sc -B1 $W/inbox $W/sb_* $W/results $W/logs 2>/dev/null | tail -1 | cut -f1; }
newest_older_than() {   # dir days -> true when no file inside is younger than days
  [ -z "$(find "$1" -type f -mtime -"$2" -print -quit 2>/dev/null)" ]
}
REF=$(for j in $(squeue -u "$USER" -h -o %i 2>/dev/null); do
        scontrol show job "$j" 2>/dev/null | grep -oE 'sb_[0-9a-f]{7}'; done | sort -u)
protected() { echo "$REF" | grep -qx "$1"; }
echo "prune_work $(date -Is) apply=$APPLY cap=$CAP reserve=$RESERVE used=$(used) referenced=[$(echo $REF)]"

# 1 inbox
for f in $W/inbox/sb_*.tar.gz; do
  [ -e "$f" ] || continue
  n=$(basename "$f" .tar.gz)
  [ -d "$W/$n" ] && run rm -f "$f"
done
[ -d $W/pddlstream_lib ] && [ -e $W/inbox/pddlstream_lib.tar.gz ] && run rm -f $W/inbox/pddlstream_lib.tar.gz
find $W/inbox -type f -mtime +$DELETE_DAYS -print0 2>/dev/null | while IFS= read -r -d '' f; do run rm -f "$f"; done

# 2 results
for d in $W/results/*/; do
  [ -d "$d" ] || continue
  d=${d%/}; n=$(basename "$d")
  if newest_older_than "$d" $COMPACT_DAYS; then
    if [ $APPLY = 1 ]; then
      tar -czf "$W/results/$n.tar.gz" -C $W/results "$n" && touch -r "$d" "$W/results/$n.tar.gz" && rm -rf "$d"
    else
      echo "  would: tar -czf $W/results/$n.tar.gz $n && rm -rf $d"
    fi
  fi
done
find $W/results -maxdepth 1 -name '*.tar.gz' -mtime +$DELETE_DAYS -print0 2>/dev/null | while IFS= read -r -d '' f; do run rm -f "$f"; done

# 3 logs
find $W/logs -type f -name 'p4-*.txt' -mtime +$COMPACT_DAYS -print0 2>/dev/null | while IFS= read -r -d '' f; do run gzip -q "$f"; done
find $W/logs -type f -name '*.gz' -mtime +$DELETE_DAYS -print0 2>/dev/null | while IFS= read -r -d '' f; do run rm -f "$f"; done

# 4 snapshots
drop_snapshot() { run chmod -R u+w "$1"; run rm -rf "$1"; }
for d in $W/sb_*/; do
  [ -d "$d" ] || continue
  d=${d%/}; n=$(basename "$d")
  protected "$n" && continue
  if [ -z "$(find "$d" -maxdepth 0 -mtime -$SNAP_DAYS 2>/dev/null)" ]; then drop_snapshot "$d"; fi
done

# 5 the cap
over() { [ $(( $(used) + RESERVE )) -gt $CAP ]; }
while over; do
  victim=$(ls -dtr $W/sb_*/ 2>/dev/null | while read -r d; do n=$(basename "${d%/}"); protected "$n" || { echo "${d%/}"; break; }; done)
  if [ -n "$victim" ]; then echo "  cap: dropping the oldest unreferenced snapshot $(basename "$victim")"; drop_snapshot "$victim"; [ $APPLY = 1 ] || break; continue; fi
  victim=$(ls -tr $W/results/*.tar.gz 2>/dev/null | head -1)
  if [ -n "$victim" ]; then echo "  cap: dropping the oldest results tarball $(basename "$victim")"; run rm -f "$victim"; [ $APPLY = 1 ] || break; continue; fi
  break
done
echo "--- usage (counted) ---"; du -sh $W/inbox $W/sb_* $W/results $W/logs 2>/dev/null
echo "--- environment (not counted) ---"; du -sh $W/armO-venvA $W/tampura-work $W/pddlstream_lib $W/python $W/tools $W/uv-cache 2>/dev/null
u=$(used); echo "counted total $u bytes ($((u / 1048576)) MiB) of $((CAP / 1048576)) MiB, reserve $((RESERVE / 1048576)) MiB"
if over; then echo "prune_work: STILL OVER THE CAP"; exit 3; fi
exit 0
