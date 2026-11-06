#!/bin/bash
# Read-only helper: print numbered line ranges of files.
# Usage: show.sh FILE START END [FILE START END ...]
# Paths without a leading / are taken relative to /root/tampura-work.
cd /root/tampura-work || exit 1
while [ $# -ge 3 ]; do
  f="$1"; s="$2"; e="$3"; shift 3
  echo "===== $f:$s-$e"
  awk -v s="$s" -v e="$e" 'NR>=s && NR<=e {printf "%d: %s\n", NR, $0}' "$f"
done
