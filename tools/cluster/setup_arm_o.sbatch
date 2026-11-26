#!/bin/bash
#SBATCH --job-name=p4-setup-armO
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
# Submit with the cluster's names on the command line, never in this file:
#   sbatch --partition=<partition> --output=$P4_WORK/logs/%x_%j.txt --export=ALL,P4_WORK=<work folder> ...
# #P4 BF#6: arm O on the chair's cluster.  Our code as immutable snapshots
# (git archive of one commit each, the CB#113 pattern), pddlstream_lib as
# used locally, and D12's candidate (A): its own venv holding exactly the
# local arm T's package set (a fresh install, not a copied venv, so no
# stale paths).  tampura_environments is installed editable from THEIR tree,
# read only, so every loaded tampura module lies inside the hashed trees
# (G13).  Runs after setup_arm_t.sbatch.
set -euo pipefail
W=${P4_WORK:?the cluster work folder}
TW=$W/tampura-work
IN=$W/inbox
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)"
export PATH=$W/tools/bin:$PATH UV_PYTHON_INSTALL_DIR=$W/python UV_CACHE_DIR=$W/uv-cache
PY=$(uv python find 3.11.15)

for tgz in $IN/sb_*.tar.gz; do
  name=$(basename $tgz .tar.gz)
  if [ ! -d $W/$name ]; then
    mkdir -p $W/$name && tar -xzf $tgz -C $W/$name
    cp $IN/_eval_ab.py $W/$name/tools/_eval_ab.py
    chmod -R a-w $W/$name/*.py
  fi
  echo "snapshot $name: $(ls $W/$name | wc -l) entries"
done
[ -d $W/pddlstream_lib ] || tar -xzf $IN/pddlstream_lib.tar.gz -C $W
$W/pddlstream_lib/downward/builds/release/bin/downward --help 2>&1 | head -2 || true

[ -d $W/armO-venvA ] || $PY -m venv $W/armO-venvA
VA=$W/armO-venvA/bin
$VA/python -m pip install -q --upgrade pip setuptools wheel
$VA/python -m pip install -q -r $W/logs/armT_pins.txt
$VA/python -m pip install -q --no-deps "tampura @ git+https://github.com/aidan-curtis/tampura.git@cdddf14b45d2608fc1d3bc9c72d8ee249c4638b2"
$VA/python -m pip install -q --no-deps -e $TW/tampura_environments
$VA/python -m pip install -q pygraphviz==1.14 || echo "[note] pygraphviz not installed: no graphviz headers on this node"
$VA/python -m pip freeze > $W/logs/armO_venvA_pip_freeze.txt
if diff <(sort $W/logs/armT_cluster_pip_freeze.txt) <(sort $W/logs/armO_venvA_pip_freeze.txt); then
  echo "ARM O VENV (A) HOLDS EXACTLY ARM T'S PACKAGE SET"
fi
sha256sum $W/logs/armO_venvA_pip_freeze.txt
echo SETUP_ARMO_DONE
