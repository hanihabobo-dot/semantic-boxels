#!/bin/bash
# Read only (added after REVIEW.md O9): the slam_collect_1p config against slam_collect.yml,
# whether any env registers that name, and E:1265-1282 (beacon generation). Writes nothing.
C=/root/tampura-work/tampura_environments/env_configs
E=/root/tampura-work/tampura_environments/tampura_environments/slam_collect/env.py
for f in slam_collect.yml slam_collect_1p.yml; do
  echo "== $f"
  cat -n "$C/$f"
done
echo "== diff"
diff "$C/slam_collect.yml" "$C/slam_collect_1p.yml"
echo "== names registered or referenced as slam_collect_1p"
grep -rn "slam_collect_1p" /root/tampura-work/tampura_environments/tampura_environments/ /root/tampura-work/tampura/tampura/ 2>/dev/null
echo "== E:1265-1282"
sed -n '1265,1282p' "$E"
