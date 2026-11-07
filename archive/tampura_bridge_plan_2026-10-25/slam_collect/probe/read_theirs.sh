#!/bin/bash
# Read-only listing of TAMPURA files used by ARGUMENT.md (prints to stdout; writes nothing).
T=/root/tampura-work
cd $T/tampura_environments || exit 1
echo "== run_planner.py (numbered)"
cat -n run_planner.py
for f in env_configs/slam_collect*.yml; do
  echo "== $f"
  cat -n "$f"
done
echo "== tampura_policy.py (numbered)"
cat -n $T/tampura/tampura/policies/tampura_policy.py
echo "== spec.py get_reward and verify"
grep -n "def get_reward\|def verify\|eval_expr\|def get_action_schema" $T/tampura/tampura/spec.py
