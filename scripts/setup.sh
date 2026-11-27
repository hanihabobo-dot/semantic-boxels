#!/usr/bin/env bash
# One-step setup of everything the pipeline needs.  Idempotent: run it again
# after a pull, and it only does what is missing.
#
#   ./scripts/setup.sh              Python environment (.venv) and PDDLStream with FastDownward
#   ./scripts/setup.sh --tampura    also TAMPURA and its find_dice environment (the bridge, arm T);
#                                   later runs keep it once its workspace exists
#
# Needs: uv, git, cmake, make and a C++ compiler; with --tampura also
# autoconf, automake and libtool (TAMPURA's SymK planner builds CUDD).
#
# Where things go (environment variables, all optional):
#   SB_DEPS_DIR   where the third-party checkouts are built (default: <repo>/.deps).
#                 <repo>/pddlstream_lib links to the PDDLStream checkout there.
#   SB_TAMPURA    the TAMPURA workspace with tampura/ and tampura_environments/
#                 (default: $SB_DEPS_DIR/tampura-work; run.sh reads the same variable)
#   UV_PROJECT_ENVIRONMENT  where uv puts the virtual environment (default: <repo>/.venv)
set -euo pipefail

# Pinned third-party versions.
PDDLSTREAM_URL=https://github.com/caelan/pddlstream.git
PDDLSTREAM_REV=2c7d6f514b07ed018e18710192aa0f91c2e70ee2      # master, 2023-03-10
TAMPURA_URL=https://github.com/aidan-curtis/tampura.git
TAMPURA_REV=cdddf14b45d2608fc1d3bc9c72d8ee249c4638b2         # as in the paper's runs
TAMPURA_ENVS_URL=https://github.com/aidan-curtis/tampura_environments.git
TAMPURA_ENVS_REV=4167c35e41170beee48b108d4a6a64a69d4b555a    # as in the paper's runs

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPS=${SB_DEPS_DIR:-$REPO/.deps}
TW=${SB_TAMPURA:-$DEPS/tampura-work}
JOBS=$(nproc 2>/dev/null || echo 4)
with_tampura=0
for arg in "$@"; do
    case $arg in
        --tampura) with_tampura=1 ;;
        -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
        *) echo "setup: unknown argument '$arg' (--tampura, --help)" >&2; exit 2 ;;
    esac
done

say() { printf '\033[1m[setup]\033[0m %s\n' "$*"; }
need() {
    local missing=()
    for tool in "$@"; do command -v "$tool" >/dev/null || missing+=("$tool"); done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "setup: missing tools: ${missing[*]}" >&2
        echo "  Debian/Ubuntu: sudo apt install git cmake build-essential autoconf automake libtool" >&2
        echo "  Fedora:        sudo dnf install git cmake make gcc-c++ autoconf automake libtool" >&2
        echo "  uv:            https://docs.astral.sh/uv/getting-started/installation/" >&2
        exit 1
    fi
}

# Build settings for old C++ code on new toolchains:
# - cmake >= 4 refuses cmake_minimum_required(VERSION < 3.5), which FastDownward
#   and SymK still declare; this policy floor lets it configure them.
# - GCC >= 14 turns -Wtemplate-body into an error, which FastDownward's bundled
#   tl::optional triggers; the flag is only passed where the compiler knows it.
# - CUDD's Makefile builds its HTML docs with doxygen when doxygen is
#   installed, and recent doxygen versions crash on them; the docs are not needed.
export CMAKE_POLICY_VERSION_MINIMUM=3.5
export DOXYGEN=true
CXX_EXTRA=""
if echo 'int main(){}' | ${CXX:-c++} -x c++ -Werror -Wno-template-body -o /dev/null - 2>/dev/null; then
    CXX_EXTRA="-Wno-template-body"
fi
export CXXFLAGS="${CXXFLAGS:-} $CXX_EXTRA"

# checkout DIR URL REV: clone DIR at REV (or move an existing clone there).
checkout() {
    local dir=$1 url=$2 rev=$3
    if [ ! -d "$dir/.git" ]; then
        say "cloning $url into $dir"
        git clone --quiet "$url" "$dir"
    fi
    if [ "$(git -C "$dir" rev-parse HEAD)" != "$rev" ]; then
        git -C "$dir" fetch --quiet origin
        git -C "$dir" checkout --quiet "$rev"
    fi
}

# A workspace made by an earlier --tampura run stays set up (a plain uv sync
# would remove TAMPURA's packages from the environment).
[ -d "$TW/tampura/.git" ] && with_tampura=1
need uv git cmake make
[ $with_tampura = 1 ] && need autoreconf libtoolize
mkdir -p "$DEPS"

# 1. The Python environment, from uv.lock.
groups=()
[ $with_tampura = 1 ] && groups+=(--group tampura)
say "Python environment (uv sync ${groups[*]:-})"
(cd "$REPO" && uv sync --locked "${groups[@]}")

# 2. PDDLStream with the FastDownward it bundles.
PS=$DEPS/pddlstream
checkout "$PS" "$PDDLSTREAM_URL" "$PDDLSTREAM_REV"
git -C "$PS" submodule update --init --quiet downward
if [ ! -x "$PS/downward/builds/release/bin/downward" ]; then
    say "building FastDownward (a few minutes)"
    (cd "$PS/downward" && uv run --project "$REPO" --no-sync python build.py -j"$JOBS" >"$DEPS/fastdownward_build.log" 2>&1) || {
        echo "setup: FastDownward build failed; see $DEPS/fastdownward_build.log" >&2; exit 1; }
fi
# The code looks for PDDLStream at <repo>/pddlstream_lib (PDDLSTREAM_PATH overrides it).
if [ ! -e "$REPO/pddlstream_lib" ] || [ -L "$REPO/pddlstream_lib" ]; then
    ln -sfn "$PS" "$REPO/pddlstream_lib"
elif [ "$(cd "$REPO/pddlstream_lib" && pwd -P)" != "$(cd "$PS" && pwd -P)" ]; then
    say "note: $REPO/pddlstream_lib is a directory of its own and is left as it is"
fi

# 3. TAMPURA (optional).
if [ $with_tampura = 1 ]; then
    mkdir -p "$TW"
    checkout "$TW/tampura" "$TAMPURA_URL" "$TAMPURA_REV"
    checkout "$TW/tampura_environments" "$TAMPURA_ENVS_URL" "$TAMPURA_ENVS_REV"
    # tampura_environments@4167c35 does not import as shipped: its __init__
    # star-imports toy_discrete, which that commit removed.  The declared fix
    # (BF#3 in docs/PAPER_AUDIT.txt) is the only change to their trees.
    cp "$REPO/tampura_bridge/patches/tampura_environments__init__.py" \
       "$TW/tampura_environments/tampura_environments/__init__.py"
    SYMK=$TW/tampura/tampura/third_party/symk
    if [ ! -x "$SYMK/builds/release/bin/downward" ]; then
        say "building TAMPURA's SymK planner (a few minutes)"
        (cd "$SYMK" && uv run --project "$REPO" --no-sync python build.py >"$DEPS/symk_build.log" 2>&1) || {
            echo "setup: SymK build failed; see $DEPS/symk_build.log" >&2; exit 1; }
    fi
fi

# 4. A quick check that everything imports.
say "checking imports"
export PYTHONPATH="$REPO:$REPO/pddlstream_lib${PYTHONPATH:+:$PYTHONPATH}"
[ $with_tampura = 1 ] && export PYTHONPATH="$PYTHONPATH:$TW/tampura:$TW/tampura_environments"
(cd "$REPO" && uv run --no-sync python - "$with_tampura" <<'EOF'
import sys, warnings
import numpy, pybullet  # noqa: F401
from planning import pddlstream_planner  # noqa: F401
import pddlstream  # noqa: F401
if sys.argv[1] == '1':
    warnings.simplefilter('ignore')
    import tampura, tampura_environments  # noqa: F401
    import tampura_environments.find_dice.env  # noqa: F401
    import tampura_bridge.policy  # noqa: F401
print('imports ok; numpy', numpy.__version__)
EOF
)
say "done.  Try:  ./run.sh boxels --headless"
[ $with_tampura = 1 ] && say "and:   ./run.sh tampura --seed 113 --gen --headless"
exit 0
