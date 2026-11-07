#!/bin/bash
# Read-only: where decision_strategy and learning_strategy values are used in their planner.
cd /root/tampura-work/tampura || exit 1
grep -rn -E 'decision_strategy|learning_strategy|"mlo"|"wao"|"prob"|bayes_optimistic|eps_greedy|"none"' --include=*.py tampura | head -60
echo "----- configs"
grep -n -E 'planner|decision_strategy|learning_strategy|max_steps|gamma' /root/tampura-work/tampura_environments/env_configs/find_dice.yml /root/tampura-work/tampura_environments/env_configs/tool_use.yml /root/tampura-work/tampura_environments/env_configs/class_uncertain.yml
