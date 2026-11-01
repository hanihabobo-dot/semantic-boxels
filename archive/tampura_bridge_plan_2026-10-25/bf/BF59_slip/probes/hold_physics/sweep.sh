#!/bin/bash
# usage: [BODY=<body>] sweep.sh <tag> <trials> <carry> <parallel> <lever> [<lever> ...]
# runs hp_probe.py once per lever, <parallel> at a time, outputs out/<tag>_<lever>.json
H=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics
tag=$1; n=$2; carry=$3; par=$4; shift 4
body=${BODY:-dice}
printf '%s\n' "$@" | xargs -P "$par" -I{} bash -c "bash $H/run.sh --lever {} --body $body --trials $n --carry $carry --out $H/out/${tag}_{}.json > $H/out/${tag}_{}.log 2>&1"
/root/armO-venvA/bin/python $H/show.py --summary $(for l in "$@"; do echo $H/out/${tag}_$l.json; done)
