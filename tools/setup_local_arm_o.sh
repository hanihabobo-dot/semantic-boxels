#!/bin/bash
# #P4 BF#15 (Q16): the laptop's arm O venv, the counterpart of the cluster's
# armO-venvA.  A fresh venv from the same base interpreter as the laptop's
# arm T venv, holding arm T's package set minus tampura and
# tampura_environments, which come from THEIR checkouts through PYTHONPATH
# (an editable install would write egg-info into their tree).  Nothing is
# installed into, or written to, arm T's venv or their tree.
# Usage (WSL): bash tools/setup_local_arm_o.sh <log dir on the Windows side>
set -euo pipefail
TW=/root/tampura-work
VT=$TW/.venv/bin/python
VO=/root/armO-venvA
LOG=${1:?log dir}
mkdir -p "$LOG"
BASE=$($VT -c 'import sys; print(sys._base_executable)')
echo "base interpreter $BASE ($($BASE --version))"
$VT -m pip freeze | sort > "$LOG/armT_local_freeze_before.txt"
grep -viE '^(tampura|tampura[-_]environments)( |=|@)|^-e ' "$LOG/armT_local_freeze_before.txt" > "$LOG/armO_local_pins.txt"
[ -d $VO ] || $BASE -m venv $VO
$VO/bin/python -m pip install -q --upgrade pip setuptools wheel
$VO/bin/python -m pip install -q -r "$LOG/armO_local_pins.txt"
$VO/bin/python -m pip freeze | sort > "$LOG/armO_local_freeze.txt"
$VT -m pip freeze | sort > "$LOG/armT_local_freeze_after.txt"
cmp -s "$LOG/armT_local_freeze_before.txt" "$LOG/armT_local_freeze_after.txt" && echo "ARM T FREEZE UNCHANGED"
diff <(grep -v -iE '^(pip|setuptools|wheel)=' "$LOG/armO_local_pins.txt") \
     <(grep -v -iE '^(pip|setuptools|wheel)=' "$LOG/armO_local_freeze.txt") && echo "ARM O VENV HOLDS THE PINS EXACTLY"
SB=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
cd $TW/tampura_environments
PYTHONPATH=$SB:$TW/tampura:$TW/tampura_environments $VO/bin/python - <<'EOF'
import numpy, pybullet  # noqa: F401
from planning import pddlstream_planner  # noqa: F401  (puts the sibling pddlstream_lib on sys.path)
import pddlstream, tampura, tampura_environments  # noqa: F401
import tampura_bridge.policy  # noqa: F401
print('imports ok:', tampura.__file__, pddlstream.__file__, 'numpy', numpy.__version__)
EOF
sha256sum "$LOG/armO_local_freeze.txt"
echo SETUP_LOCAL_ARMO_DONE
