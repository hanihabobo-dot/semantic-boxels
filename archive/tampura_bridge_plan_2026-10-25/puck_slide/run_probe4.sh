#!/bin/bash
# Runs probe_shot_law.py read only, with the run line of the earlier probes,
# and hashes their two trees before and after by both methods (as run_probe3.sh).
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
$PY -B $PS/probe_shot_law.py $PS/probe_shot_law_out.json > $PS/probe_shot_law_log.txt 2>&1
echo "probe rc=$?"
echo "== after"; hashes
ls -la /root/ps_probe
