#!/bin/bash
# Runs probe_slide_track.py read only, with the earlier probes' run line, and
# hashes their two trees before and after by both methods named in
# ARGUMENT.md 4.5 (shell: git ls-files -z | xargs -0 sha256sum | sha256sum;
# tools/bridge_gates.py:598-609's method via the review's rp_tree_hash.py,
# which writes only to stdout).  Outputs go to this folder only.
set -u
PS=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/puck_slide
PY=/root/tampura-work/.venv/bin/python
hashes() {
  for r in tampura tampura_environments; do
    (cd /root/tampura-work/$r && echo "$r shell: $(git ls-files -z | xargs -0 sha256sum | sha256sum | cut -c1-16)")
  done
  python3 $PS/review_probe/rp_tree_hash.py
}
echo "== before"; hashes
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments
cd /root/ps_probe || exit 1
ls -la /root/ps_probe
$PY -B $PS/probe_slide_track.py $PS/probe_slide_track_out.json > $PS/probe_slide_track_log.txt 2>&1
echo "probe rc=$?"
echo "== after"; hashes
ls -la /root/ps_probe
