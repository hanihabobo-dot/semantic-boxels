#!/bin/bash
# BF#59 grasp_wrist_home: the GF9 gated episode test and B3s parameterisation tests alone, under the lock,
# full failure output (it plans a random-pairs episode).
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-grasp_wrist_home
TW=/root/tampura-work
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
cd $TW/tampura_environments && flock /root/sb_pipeline.lock /root/armO-venvA/bin/python -m pytest -q -p no:cacheprovider -x \
  $S/tampura_bridge/tests/test_gf9_gated_episode.py $S/tampura_bridge/tests/test_b3_parameterisation.py 2>&1 | grep -v '^\s*$' | grep -E 'assert|Error|error|FAILED|passed|failed|^E ' | head -40
