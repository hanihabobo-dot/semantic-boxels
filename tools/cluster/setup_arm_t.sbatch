#!/bin/bash
#SBATCH --job-name=p4-setup-armT
#SBATCH --partition=cpu_modern
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --time=03:00:00
#SBATCH --output=/work/rleap1/hani.alassiri.alhabboub/p4/logs/%x_%j.txt
# #P4 BF#6: arm T (TAMPURA at the pinned commits) on the chair's cluster, in
# user space under /work.  Mirrors /root/tampura-work/tampura_setup.sh step
# for step, except: Python 3.11 from uv instead of apt, cmake from a pip
# wheel, and every package pinned to the local arm T's pip freeze.
set -euo pipefail
W=/work/rleap1/hani.alassiri.alhabboub/p4
TW=$W/tampura-work
IN=$W/inbox
echo "host $(hostname)  job ${SLURM_JOB_ID:-none}  $(date -Is)"
lscpu | grep -E 'Model name|Socket\(s\)|Core\(s\) per|Thread\(s\)'
which g++ make git

# 1. Tools on the system Python: uv (for Python 3.11) and cmake (for SymK).
if [ ! -x $W/tools/bin/uv ]; then
  python3 -m venv $W/tools
  $W/tools/bin/pip install -q uv cmake
fi
export PATH=$W/tools/bin:$PATH
export UV_PYTHON_INSTALL_DIR=$W/python UV_CACHE_DIR=$W/uv-cache
uv python install 3.11.15
PY=$(uv python find 3.11.15)
$PY -VV

# 2. Their repositories at the pinned commits.
mkdir -p $TW
[ -d $TW/tampura ] || git clone -q https://github.com/aidan-curtis/tampura.git $TW/tampura
[ -d $TW/tampura_environments ] || git clone -q https://github.com/aidan-curtis/tampura_environments.git $TW/tampura_environments
git -C $TW/tampura checkout -q cdddf14b45d2608fc1d3bc9c72d8ee249c4638b2
git -C $TW/tampura_environments checkout -q 4167c35e41170beee48b108d4a6a64a69d4b555a

# 3. BF#3: the one declared change to their tree, byte for byte.
cp $IN/tampura_environments__init__BF3.py $TW/tampura_environments/tampura_environments/__init__.py
echo "9a64bea00c9ef6dcea6a8ee5b26a1f071a4366f053895509ddc32e45fe7b8ec4  $TW/tampura_environments/tampura_environments/__init__.py" | sha256sum -c
git -C $TW/tampura status --porcelain --untracked-files=no
git -C $TW/tampura_environments status --porcelain --untracked-files=no

# 4. The venv, with the local arm T's exact versions.
[ -d $TW/.venv ] || $PY -m venv $TW/.venv
V=$TW/.venv/bin
$V/python -m pip install -q --upgrade pip setuptools wheel
grep -vE '^(tampura|-e |pygraphviz)' $IN/armT_local_pip_freeze.txt > $W/logs/armT_pins.txt
$V/python -m pip install -q -r $W/logs/armT_pins.txt
# tampura as locally: from GitHub at the pinned commit, non-editable; its
# setup.py runs SymK's build.py (needs the cmake above).
$V/python -m pip install -q --no-deps "tampura @ git+https://github.com/aidan-curtis/tampura.git@cdddf14b45d2608fc1d3bc9c72d8ee249c4638b2"
$V/python -m pip install -q --no-deps -e $TW/tampura_environments
# pygraphviz needs graphviz headers; TAMPURA imports it only to draw graphs
# (structs.py:68, solvers/sample_uct.py:56), which headless runs never do.
$V/python -m pip install -q pygraphviz==1.14 || echo "[note] pygraphviz not installed: no graphviz headers on this node"

# 5. Checks.
cd $TW/tampura_environments
$V/python -c "import tampura, tampura_environments, pybullet, numpy, torch; print('import ok', tampura.__file__, numpy.__version__, torch.__version__)"
ls "$($V/python -c 'import tampura, os; print(os.path.dirname(tampura.__file__))')/third_party/symk/builds/release/bin"
$V/python -m pip freeze > $W/logs/armT_cluster_pip_freeze.txt
if diff <(grep -vE '^(tampura|-e |pygraphviz)' $IN/armT_local_pip_freeze.txt | sort) \
        <(grep -vE '^(tampura|-e |pygraphviz)' $W/logs/armT_cluster_pip_freeze.txt | sort); then
  echo "FREEZE MATCHES THE LOCAL ARM T (tampura, tampura_environments and pygraphviz lines aside)"
fi
sha256sum $W/logs/armT_cluster_pip_freeze.txt
echo SETUP_ARMT_DONE
