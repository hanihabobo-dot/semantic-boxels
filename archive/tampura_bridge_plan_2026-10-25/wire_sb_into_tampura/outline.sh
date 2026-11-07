#!/bin/bash
# Read-only helper: outline a python file (defs, classes, action names, observations, rendering, reward).
# Usage: outline.sh FILE [FILE ...]   (relative to /root/tampura-work)
cd /root/tampura-work || exit 1
for f in "$@"; do
  echo "===== $f"
  grep -n -E '^(class|def) |^    def |name="|register_env|Observation\(|getCameraImage|get_image|def get_reward|reward = |setGravity|stepSimulation|sim_steps' "$f"
done
