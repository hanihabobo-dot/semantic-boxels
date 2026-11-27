#!/bin/bash
# run.sh: the pipeline in one word on Linux (bash), the twin of run.ps1.  It
# starts the same commands as run.ps1 does inside WSL, without Windows or
# PowerShell, on a plain Linux machine or inside WSL.
#   ./run.sh                          the bridge episode on TAMPURA's find_dice, seed 0, in the GUI
#   ./run.sh tampura --seed 7         another seed
#   ./run.sh tampura --seed 118,102,103 --gen   several seeds (also "[118, 102, 103]" or 118 102 103),
#                                     one run after another, then a line for each; closing a GUI
#                                     window goes on with the next seed, Ctrl-C stops the list
#   ./run.sh tampura --headless       no GUI: the console only (a diagnostic run, never scored)
#   ./run.sh tampura --seed 118 --gen a scene from their own generator (BF#63's seeds 100 to 139)
#   ./run.sh boxels                   our own random-pairs holding scene, seed 0, in the GUI
#   ./run.sh boxels --seed 3 --headless
#   ./run.sh boxels --scene stack --goal stack --occluders 0
#   ./run.sh tampura --off            without M8-M10;  --squeeze 1   a pick squeeze in mm
#   ./run.sh boxels --look boxel --eye arm   one look action, every image from the arm camera
#   ./run.sh tampura --screenshots    also save the eye PNGs at every snapshot (debugging only)
#   ./run.sh tampura --draw boxels    the GUI also draws the boxels;  --draw cameras  draws each view
#                                     volume and saves what each camera saw into the run's cameras
#                                     folder (the separate camera window is Windows only)
#   ./run.sh boxels --args '--n-extra-distractors 1'   more pipeline flags, one quoted string, as is
#   ./run.sh wumpus --seed 3          the 3-D Wumpus world, GUI;  --size 10 (default 5), --headless
#   ./run.sh ps                       the pipeline processes alive;  ./run.sh kill   ends the ones run started
#   ./run.sh help                     this text;  --dry-run prints the command instead of running it
# Flags are case-blind and one or two dashes both work, so run.ps1's spellings do too
# (-Seed 7 -Headless -Gen).  A flag run.sh does not know goes to the pipeline as it is.
# One thing is run.ps1's alone: for a GUI run of boxels it asks for the page of our own
# beside the simulator's window, opens it and holds the two together (Windows' browser
# and windows); here such a run has PyBullet's own panels, and run.ps1's -NoPage and
# -LoosePage are not known.  ./run.sh boxels --gui-page on asks the pipeline for the
# page all the same: the run prints its address, to be opened in a browser by hand.
# Three settings come from the environment, each with a default:
#   SB_PYTHON    the Python that has numpy, pybullet and the rest (default: .venv/bin/python
#                in the checkout, then /root/armO-venvA/bin/python, then python3)
#   SB_TAMPURA   the TAMPURA workspace holding tampura/ and tampura_environments/, for
#                run tampura only (default: ~/.local/share/semantic-boxels/tampura-work, as
#                scripts/setup.sh --tampura makes it, then ~/tampura-work, then /root/tampura-work)
#   SB_LOCK      the pipeline lock file (default: /root/sb_pipeline.lock where /root can be
#                written, as run.ps1 uses, else $XDG_RUNTIME_DIR or /tmp)
# Every run takes the pipeline lock (one episode at a time): it waits while another episode
# holds it, and says who; it refuses while another run it started is still alive.
# Closing the GUI window or pressing Ctrl-C ends the run for good.  A closed window leaves
# PyBullet's client busy-waiting in C at full CPU (BF#51), so while a GUI run goes its
# window is watched (xwininfo, where there is one) and tools/run_procs.sh ends what is left.
# --music, --sfx and --voice set what run.ps1 sets; the sounds are played by Windows
# PowerShell through WSL, so on a machine without it the run is silent.

S=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DRAW_KINDS='boxels cameras'
GUI_RUNS=archive/tampura_bridge_plan_2026-10-25/bf/gui_runs
WUMPUS_RUNS=archive/tampura_bridge_plan_2026-10-25/tracks/wumpus/runs

say() { printf '%s\n' "$*" >&2; }

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

if [ -n "${SB_PYTHON:-}" ]; then PY=$SB_PYTHON
elif [ -x "$S/.venv/bin/python" ]; then PY=$S/.venv/bin/python
elif [ -x /root/armO-venvA/bin/python ]; then PY=/root/armO-venvA/bin/python
else PY=python3; fi
if [ -n "${SB_TAMPURA:-}" ]; then TW=$SB_TAMPURA
elif [ -d "${SB_DEPS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/semantic-boxels}/tampura-work" ]; then   # scripts/setup.sh --tampura
    TW=${SB_DEPS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/semantic-boxels}/tampura-work
elif [ -d "$HOME/tampura-work" ]; then TW=$HOME/tampura-work
else TW=/root/tampura-work; fi
if [ -n "${SB_LOCK:-}" ]; then LOCK=$SB_LOCK
elif [ -n "${RUN_PROCS_LOCK:-}" ]; then LOCK=$RUN_PROCS_LOCK
elif [ -w /root ]; then LOCK=/root/sb_pipeline.lock
else LOCK=${XDG_RUNTIME_DIR:-/tmp}/sb_pipeline.lock; fi
export RUN_PROCS_LOCK=$LOCK      # tools/run_procs.sh reads the lock's name from here
procs() { bash "$S/tools/run_procs.sh" "$@"; }

what=tampura
case "${1:-}" in
    '') ;;
    -*) ;;
    *) what=$1; shift ;;
esac
case "$what" in
    help|-h|--help|'?') usage; exit 0 ;;
    ps|status)
        alive=$(procs ps)
        if [ -n "$alive" ]; then printf '%s\n' "$alive"; else say 'run: no pipeline process is alive'; fi
        exit 0 ;;
    kill)
        gone=$(procs kill); rc=$?
        if [ -n "$gone" ]; then printf '%s\n' "$gone"; else say 'run: nothing to kill, no pipeline process is alive'; fi
        exit $rc ;;
    tampura|boxels|wumpus) ;;
    *) say "run: unknown target '$what' (tampura, boxels or wumpus; ./run.sh help)"; exit 2 ;;
esac

seed_words=() draw_words=() extra=()
headless=0 size=5 gen=0 scene=random-pairs goal=holding occluders=2 off=0
look='' eye='' squeeze='' screenshots=0 music=0 sfx=0 voice=0 dry=0
taking=''        # the list a bare word joins: seed or draw (as -Seed 118 102 does in run.ps1)
need() { [ "$1" -ge 2 ] || { say "run: $2 needs a value"; exit 2; }; }
while [ $# -gt 0 ]; do
    arg=$1
    key=$(printf '%s' "$arg" | tr '[:upper:]' '[:lower:]')
    case "$key" in
        -h|-help|--help) usage; exit 0 ;;
        -seed|--seed) need $# "$arg"; seed_words+=("$2"); taking=seed; shift 2; continue ;;
        -draw|--draw) need $# "$arg"; draw_words+=("$2"); taking=draw; shift 2; continue ;;
        -headless|--headless) headless=1 ;;
        -gen|--gen) gen=1 ;;
        -off|--off) off=1 ;;
        -screenshots|--screenshots) screenshots=1 ;;
        -music|--music) music=1 ;;
        -sfx|--sfx) sfx=1 ;;
        -voice|--voice) voice=1 ;;
        -dryrun|--dryrun|-dry-run|--dry-run|-d|-dr) dry=1 ;;
        -size|--size) need $# "$arg"; size=$2; shift ;;
        -scene|--scene) need $# "$arg"; scene=$2; shift ;;
        -goal|--goal) need $# "$arg"; goal=$2; shift ;;
        -occluders|--occluders) need $# "$arg"; occluders=$2; shift ;;
        -look|--look) need $# "$arg"; look=$2; shift ;;
        -eye|--eye) need $# "$arg"; eye=$2; shift ;;
        -squeeze|--squeeze) need $# "$arg"; squeeze=$2; shift ;;
        -args|--args) need $# "$arg"; extra+=("$2"); shift ;;
        --) shift; extra+=("$@"); break ;;
        *)
            if [ "$taking" = seed ] && [[ "$arg" =~ ^[][0-9,[:space:]]+$ ]]; then seed_words+=("$arg")
            elif [ "$taking" = draw ] && [[ " $DRAW_KINDS " == *" $key "* ]]; then draw_words+=("$arg")
            else extra+=("$arg"); taking=''; fi
            shift; continue ;;
    esac
    taking=''
    shift
done

# --seed takes one seed or a list, run one after another: 7, 118,102 or "[118, 102, 103]".
[ ${#seed_words[@]} -eq 0 ] && seed_words=(0)
read -r -a seeds <<< "$(printf '%s ' "${seed_words[@]}" | tr ',[]' '   ')"
bad=0
for one in "${seeds[@]}"; do [[ "$one" =~ ^[0-9]+$ ]] || bad=1; done
if [ ${#seeds[@]} -eq 0 ] || [ $bad = 1 ]; then
    say "run: --seed takes a seed or a list (7, 118,102 or \"[118, 102, 103]\"), not '${seed_words[*]}'"
    exit 2
fi
for i in "${!seeds[@]}"; do seeds[i]=$((10#${seeds[i]})); done
[[ "$size" =~ ^[0-9]+$ && "$occluders" =~ ^[0-9]+$ ]] || { say 'run: --size and --occluders take a whole number'; exit 2; }
if [ "$what" = tampura ] && [ $gen = 1 ]; then
    missing=()
    for one in "${seeds[@]}"; do
        [ -f "$S/tampura_bridge/gen_scenes/find_dice/find_dice_gen_s$one.json" ] || missing+=("$one")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        word=seed; [ ${#missing[@]} -gt 1 ] && word=seeds
        list=$(printf '%s, ' "${missing[@]}")
        say "run: no generated scene for $word ${list%, } (BF#63's are 100 to 139)"
        exit 2
    fi
fi

sw=''
[ $off = 1 ] && sw=' --m8 off --m9 off --m10 off --pick-aperture-from-pose off'
case "$look" in
    ''|boxel|centred|on) ;;
    *) say "run: --look takes boxel, centred or on, not '$look'"; exit 2 ;;
esac
[ -n "$look" ] && sw+=" --look $look"
case "$eye" in
    ''|fixed) ;;
    arm)
        if [ -z "$look" ]; then
            say "run: --eye arm needs --look boxel or --look centred (sense is the fixed camera's action)"
            exit 2
        fi
        sw+=' --eye arm' ;;
    *) say "run: --eye takes fixed or arm, not '$eye'"; exit 2 ;;
esac
if [ -n "$squeeze" ]; then
    [[ "$squeeze" =~ ^[0-9]+([.][0-9]+)?$ ]] || { say "run: --squeeze takes millimetres (1 or 0.5), not '$squeeze'"; exit 2; }
    [[ "$squeeze" =~ ^0+([.]0+)?$ ]] || sw+=" --grip-squeeze-mm $squeeze"
fi
[ $screenshots = 1 ] && sw+=' --save-screenshots on'
# --draw: what the GUI draws besides the scene, one word or a comma list, any case.
draws=()
for one in $(printf '%s ' "${draw_words[@]}" | tr ',[:upper:]' ' [:lower:]'); do
    if [[ " $DRAW_KINDS " != *" $one "* ]]; then
        say "run: --draw takes ${DRAW_KINDS// /, } (several: a comma list), not '$one'"
        exit 2
    fi
    [[ " ${draws[*]} " == *" $one "* ]] || draws+=("$one")
done
if [ ${#draws[@]} -gt 0 ] && [ "$what" != tampura ]; then
    own='run boxels has its own display'
    [ "$what" = wumpus ] && own='run wumpus paints what the robot knows'
    say "run: --draw (${DRAW_KINDS// /, }) is for run tampura; $own and ignores it"
    draws=()
elif [ ${#draws[@]} -gt 0 ] && [ $headless = 1 ]; then
    say 'run: --draw is ignored with --headless (there is no GUI), nothing is drawn'
    draws=()
fi
if [ ${#draws[@]} -gt 0 ]; then
    joined=$(printf '%s,' "${draws[@]}")
    sw+=" --draw ${joined%,}"
fi
xtra=''
[ ${#extra[@]} -gt 0 ] && xtra=" ${extra[*]}"
audio=''
[ $sfx = 1 ] && audio=sfx
[ $music = 1 ] && audio=on

# One seed's run, built when it starts (its folder is stamped with that time).  Sets
# CMD, MINE (text found in this run's command line and no other's, for ending this
# run alone), RECORD (its episode record) and CAMERAS (the --draw cameras folder).
new_run() {
    local seed_no=$1 stamp vis kind g19 save run json D nogui
    RECORD='' CAMERAS=''
    stamp=$(date +%Y-%m-%d_%H-%M-%S)
    vis=1 kind=watch
    [ $headless = 1 ] && vis=0 kind=headless
    if [ "$what" = tampura ]; then
        g19=''
        [ $headless = 1 ] && g19=' --allow-g19-mismatch 1'
        MINE="${kind}_s${seed_no}_$stamp"
        save="$S/$GUI_RUNS/$MINE"
        RECORD="$save/bridge_episode.json"
        [[ " ${draws[*]} " == *' cameras '* ]] && CAMERAS="$save/cameras"
        run="PYTHONPATH=$S:$S/pddlstream_lib:$TW/tampura:$TW/tampura_environments "
        run+="PYTHONHASHSEED=0 $PY $S/tampura_bridge/run_bridge_on_finddice.py "
        run+="--global-seed $seed_no --vis $vis --save-dir $save$g19$sw$xtra"
        if [ $gen = 1 ]; then
            # BF#63: their loader picks a random file of tampura_environments/find_dice/
            # problems under the cwd, so the run starts in a directory holding only this
            # scene; the manifest pins it for G19.  The directory goes when the run ends.
            json="tampura_bridge/gen_scenes/find_dice/find_dice_gen_s$seed_no.json"
            D="${TMPDIR:-$HOME}/run_gen_$MINE"
            CMD="trap 'rm -rf $D' EXIT; mkdir -p $D/tampura_environments/find_dice/problems && "
            CMD+="cp $S/$json $D/tampura_environments/find_dice/problems/ && "
            CMD+="ln -s $TW/tampura_environments/env_configs $D/env_configs && cd $D && "
            CMD+="BRIDGE_SCENE_MANIFEST=$S/tampura_bridge/gen_scenes/find_dice/manifest.json $run"
        else
            CMD="cd $TW/tampura_environments && $run"
        fi
    elif [ "$what" = wumpus ]; then
        MINE="wumpus_${kind}_n${size}_s${seed_no}_$stamp"
        save="$S/$WUMPUS_RUNS/$MINE"
        RECORD="$save/episode.json"
        CMD="cd $S && PYTHONHASHSEED=0 $PY $S/wumpus/run_wumpus.py --size $size --seed $seed_no --vis $vis --save-dir $save$xtra"
    else
        nogui=''
        [ $headless = 1 ] && nogui=' --no-gui'
        MINE="test_full_pipeline.py$nogui --scene $scene --seed $seed_no --goal $goal --n-occluders $occluders"
        CMD="cd $S && PYTHONHASHSEED=0 $PY $MINE$sw$xtra"
    fi
    [ -n "$audio" ] && CMD="export SB_AUDIO=$audio; $CMD"
    [ $voice = 1 ] && CMD="export SB_VOICE=on; $CMD"
    # The run and its children carry SB_RUN, so run kill ends what run started and
    # leaves any other episode, probe or planner alone.
    CMD="export SB_RUN=1; $CMD"
}

if [ $dry = 1 ]; then
    for one in "${seeds[@]}"; do
        new_run "$one"
        printf "flock %s bash -c '%s'\n" "$LOCK" "${CMD//\'/\'\\\'\'}"
    done
    exit 0
fi

command -v flock >/dev/null || { say 'run: flock is not installed (package util-linux)'; exit 2; }
if ! "$PY" -c 'pass' 2>/dev/null; then
    say "run: the Python '$PY' does not start; set SB_PYTHON to the one with numpy and pybullet"
    exit 2
fi
if [ "$what" = tampura ] && [ ! -d "$TW/tampura_environments" ]; then
    say "run: no TAMPURA workspace at $TW (tampura/ and tampura_environments/); set SB_TAMPURA"
    exit 2
fi

# The GUI window as X sees it: PyBullet titles it 'Bullet Physics ...'.
window_open() { xwininfo -root -tree 2>/dev/null | grep -q 'Bullet Physics'; }

# While a GUI run goes: once its window was seen and is then gone while the run goes
# on, the run is ended (BF#51).  A run that is ending closes its own window, so it
# gets 3 s first.  Runs beside the run; the flag file tells the launcher it acted.
watch_window() {
    local mine=$1 t0=$2 flag=$3 seen=0
    while sleep 0.7; do
        if window_open; then seen=1
        elif [ $seen = 1 ]; then
            sleep 3
            [ -n "$(procs busy)" ] || return 0
            : > "$flag"
            procs kill-mine "$mine" $(( $(date +%s) - t0 + 60 )) >/dev/null
            return 0
        fi
    done
}

outcome_of() {   # the record's outcome (success, failure, crashed, gate_failed), or nothing
    "$PY" -c 'import json, sys
o = json.load(open(sys.argv[1])).get("outcome")
print((o.get("status") or o.get("outcome") or "") if isinstance(o, dict) else (o or ""))' "$1" 2>/dev/null
}

interrupted=0
trap 'interrupted=1' INT
many=0; [ ${#seeds[@]} -gt 1 ] && many=1
summary=() code=0 ran=0
for i in "${!seeds[@]}"; do
    # Only a run that run started refuses a new one; another episode does not (the
    # pipeline lock keeps the two apart, and the new run says who holds it while it waits).
    busy=$(procs busy)
    if [ -n "$busy" ]; then
        say 'run: a run started by run is still going, never two at once:'
        printf '%s\n' "$busy" | sed 's/^/  /' >&2
        say '  a ghost (its window closed, its terminal gone)?   ./run.sh kill   ends the ones run started'
        code=2
        break
    fi
    new_run "${seeds[i]}"
    [ $many = 1 ] && say "run: seed ${seeds[i]}, $((i + 1)) of ${#seeds[@]}"
    [ -n "$CAMERAS" ] && say "run: the cameras' pictures go to $CAMERAS (the camera window is Windows only)"
    t0=$(date +%s)
    flag=$(mktemp "${TMPDIR:-/tmp}/sb_run_closed.XXXXXX"); rm -f "$flag"
    watcher=''
    if [ $headless = 0 ] && [ -n "${DISPLAY:-}" ] && command -v xwininfo >/dev/null; then
        watch_window "$MINE" "$t0" "$flag" &
        watcher=$!
    fi
    if ! flock -n "$LOCK" true; then
        say "run: waiting for the pipeline lock $LOCK, one episode at a time. Now:"
        procs ps >&2
    fi
    flock "$LOCK" bash -c "$CMD"
    code=$?
    ended=''
    if [ -n "$watcher" ]; then
        # the watcher may be ending the run this moment: let it finish its sentence
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            kill -0 "$watcher" 2>/dev/null && [ -e "$flag" ] && sleep 0.5 || break
        done
        kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
    fi
    [ -e "$flag" ] && ended='the window was closed'
    rm -f "$flag"
    printf '\033[?25h'      # the console hides the cursor while a step runs; show it whatever happened
    [ $interrupted = 1 ] && [ $code = 0 ] && code=130
    if [ -n "$ended" ]; then
        say "run: $ended, so the run was ended from here; nothing of it is left"
    elif [ $code = 130 ]; then
        say 'run: interrupted (Ctrl-C ends the run at once; its files stay as they were)'
    fi
    ran=$((ran + 1))
    status="exit $code"
    [ $code = 0 ] && status=success
    [ $code = 130 ] && status=interrupted
    [ -n "$ended" ] && status='window closed'
    folder=''
    if [ -n "$RECORD" ]; then
        folder=$(basename "$(dirname "$RECORD")")
        if [ -z "$ended" ] && [ $code != 130 ] && [ -f "$RECORD" ]; then
            o=$(outcome_of "$RECORD"); [ -n "$o" ] && status=$o
        fi
    fi
    summary+=("$(printf '  seed %-5s %-14s %5s s   %s' "${seeds[i]}" "$status" "$(( $(date +%s) - t0 ))" "$folder")")
    [ $code = 130 ] && break
    [ $code != 0 ] && failed=1
done

if [ $many = 1 ]; then
    # One line per seed, then the seeds a refusal or Ctrl-C left out.
    echo
    echo "run: $ran of ${#seeds[@]} seeds run, one after another"
    [ ${#summary[@]} -gt 0 ] && printf '%s\n' "${summary[@]}"
    left=("${seeds[@]:$ran}")
    if [ ${#left[@]} -gt 0 ]; then
        list=$(printf '%s, ' "${left[@]}"); echo "  not run: ${list%, }"
    fi
    # The list's exit: 2 refused, 130 interrupted, else 0 when every run succeeded.
    if [ $code != 2 ] && [ $code != 130 ]; then code=${failed:-0}; fi
fi
exit $code
