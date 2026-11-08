#!/bin/bash
# run_procs.sh: the pipeline's processes in WSL, behind run.ps1 (run ps, run
# kill, its busy refusal and the clean-up after every run).  Each one is a
# python running test_full_pipeline.py, run_bridge_on_finddice.py or
# run_planner.py.
#   bash run_procs.sh list                     one line each; nothing when none
#   bash run_procs.sh ps                       list's lines, then the jobs under the pipeline lock
#   bash run_procs.sh kill                     TERM, then KILL, every one run.ps1 started (SB_RUN
#                                              in its environment); the others are named, left alone
#   bash run_procs.sh kill-mine TEXT MAXAGE    the same for those whose command line
#                                              contains TEXT and that are at most MAXAGE s old
# A ghost run (BF#51): its GUI window was closed, PyBullet's client busy-waits
# in C at full CPU, no Python code (so no Ctrl-C) ever runs again, and the
# process outlives its terminal.  list marks one 'window closed' (its
# console_debug.log holds Xlib's "X connection ... broken" line) or 'quiet'
# (nothing written to its run directory for 12 min; a long plan search looks
# the same, so that one is only a hint).
# run.ps1 feeds this file to bash through tr -d '\r', so CRLF does no harm.
PAT='test_full_pipeline\.py|run_bridge_on_finddice\.py|run_planner\.py'

pipeline_pids() {
    local p
    for p in $(pgrep -f "$PAT"); do
        [ "$p" = "$$" ] && continue
        case "$(cat /proc/$p/comm 2>/dev/null)" in python*) echo "$p" ;; esac
    done
}

cmdline() { tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null; }

age_text() {   # seconds -> 1h18m, 3m20s, 12s
    local s=${1:-0}
    if [ "$s" -ge 3600 ]; then printf '%dh%02dm' $((s / 3600)) $((s % 3600 / 60))
    elif [ "$s" -ge 60 ]; then printf '%dm%02ds' $((s / 60)) $((s % 60))
    else printf '%ds' "$s"; fi
}

run_dir() {   # the run directory, from the log files the process holds open
    ls -l "/proc/$1/fd" 2>/dev/null | grep -o '/[^ ]*/run_[0-9][0-9-]*_[0-9-]*' | head -1
}

# TB-17: run.ps1 exports SB_RUN in every run's command, so its runs and
# their children carry it; a track's episode, probe or TAMPURA process does
# not, and run kill leaves those alone.
from_run() {   # true when run.ps1 started the process
    tr '\0' '\n' < "/proc/$1/environ" 2>/dev/null | grep -q '^SB_RUN='
}

what() {   # a short name from the command line
    local c="$1" seed vis save scene
    if [[ "$c" == *run_bridge_on_finddice.py* ]]; then
        seed=$(sed -n 's/.*--global-seed \([0-9]*\).*/\1/p' <<< "$c")
        vis=$(sed -n 's/.*--vis \([0-9]\).*/\1/p' <<< "$c")
        save=$(sed -n 's/.*--save-dir \([^ ]*\).*/\1/p' <<< "$c")
        printf 'bridge find_dice seed %s, %s, %s' "${seed:-?}" \
            "$([ "$vis" = 1 ] && echo GUI || echo headless)" "$(basename "${save:-?}")"
    elif [[ "$c" == *test_full_pipeline.py* ]]; then
        scene=$(sed -n 's/.*--scene \([^ ]*\).*/\1/p' <<< "$c")
        seed=$(sed -n 's/.*--seed \([0-9]*\).*/\1/p' <<< "$c")
        printf 'boxels %s seed %s, %s' "${scene:-?}" "${seed:-?}" \
            "$([[ "$c" == *--no-gui* ]] && echo headless || echo GUI)"
    else
        printf 'run_planner (TAMPURA)'
    fi
}

list() {
    local now p c age cpu dir newest quiet flag f pstart by
    now=$(date +%s)
    for p in $(pipeline_pids); do
        c=$(cmdline "$p")
        age=$(ps -o etimes= -p "$p" 2>/dev/null | tr -d ' ')
        cpu=$(ps -o pcpu= -p "$p" 2>/dev/null | tr -d ' ')
        dir=$(run_dir "$p")
        flag=''
        if [ -n "$dir" ] && [ -d "$dir" ]; then
            newest=$(find "$dir" -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1 | cut -d. -f1)
            quiet=''
            [ -n "$newest" ] && quiet=$((now - newest))
            if grep -qs 'X connection to .* broken' "$dir/console_debug.log"; then flag='window closed'
            elif [ -n "$quiet" ] && [ "$quiet" -ge 720 ]; then flag="quiet $(age_text "$quiet")"; fi
        else
            # Before the run directory exists the console's debug file is in
            # the cache: the newest one, if written since this process began.
            pstart=$(stat -c %Y "/proc/$p" 2>/dev/null)
            f=$(ls -t "$HOME/.cache/semantic_boxels"/console_debug_*.log 2>/dev/null | head -1)
            if [ -n "$f" ] && [ -n "$pstart" ] && [ "$(stat -c %Y "$f")" -ge "$pstart" ]; then
                grep -qs 'X connection to .* broken' "$f" && flag='window closed'
            fi
        fi
        if from_run "$p"; then by='run'; else by='not run'; fi
        printf 'pid %-7s %7s old  %5s%% cpu  %-15s %-8s %s\n' "$p" "$(age_text "$age")" "${cpu:-?}" "$flag" "$by" "$(what "$c")"
    done
}

locked() {   # what holds or waits for the pipeline lock (rule 7), never ended here
    local f c kid age
    for f in $(pgrep -x flock); do
        c=$(cmdline "$f")
        [[ "$c" == *"$LOCK"* ]] || continue
        kid=$(pgrep -P "$f" | head -1)
        if [ -z "$kid" ]; then
            age=$(ps -o etimes= -p "$f" 2>/dev/null | tr -d ' ')
            printf 'pid %-7s %7s old  waiting for the lock:  %s\n' "$f" "$(age_text "$age")" "${c:0:110}"
        else
            age=$(ps -o etimes= -p "$kid" 2>/dev/null | tr -d ' ')
            printf 'pid %-7s %7s old  holds the lock:       %s\n' "$kid" "$(age_text "$age")" "$(cmdline "$kid" | cut -c1-110)"
        fi
    done
}

# TB-17: a process that has ended but whose parent has not reaped it yet
# (a zombie, state Z) still has its /proc entry; it is gone all the same.
alive() {
    local s
    s=$(sed -n 's/^State:[[:space:]]*\([A-Z]\).*/\1/p' "/proc/$1/status" 2>/dev/null)
    [ -n "$s" ] && [ "$s" != Z ] && [ "$s" != X ]
}

kill_pids() {   # TERM, then KILL for the survivors
    local pids="$*" p left i
    [ -z "${pids// /}" ] && return 0
    for p in $pids; do printf 'ending pid %s: %s\n' "$p" "$(what "$(cmdline "$p")")"; done
    kill -TERM $pids 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 0.3
        left=''
        for p in $pids; do alive "$p" && left="$left $p"; done
        [ -z "$left" ] && break
    done
    if [ -n "$left" ]; then
        kill -KILL $left 2>/dev/null
        sleep 0.5
        for p in $left; do alive "$p" && printf 'pid %s would not die\n' "$p"; done
    fi
}

# A test points these at its own dummy processes and lock (TB-17); run.ps1
# never sets them.
PAT=${RUN_PROCS_PAT:-$PAT}
LOCK=${RUN_PROCS_LOCK:-/root/sb_pipeline.lock}

case "$1" in
    list)
        list ;;
    ps)
        list
        held=$(locked)
        if [ -n "$held" ]; then echo 'under the pipeline lock (run kill leaves these alone):'; echo "$held"; fi ;;
    kill)
        mine=''; others=''
        for p in $(pipeline_pids); do
            if from_run "$p"; then mine="$mine $p"; else others="$others $p"; fi
        done
        kill_pids $mine
        for p in $others; do
            printf 'left alone, not started by run: pid %s: %s\n' "$p" "$(what "$(cmdline "$p")")"
        done
        left=''
        for p in $mine; do alive "$p" && left="$left $p"; done
        if [ -n "$left" ]; then echo "still there:$left"; exit 1; fi ;;
    kill-mine)
        text="$2"; maxage="${3:-100000}"; mine=''
        for p in $(pipeline_pids); do
            c=$(cmdline "$p"); age=$(ps -o etimes= -p "$p" 2>/dev/null | tr -d ' ')
            [[ "$c" == *"$text"* ]] && [ "${age:-0}" -le "$maxage" ] && mine="$mine $p"
        done
        kill_pids $mine ;;
    *)
        echo 'usage: run_procs.sh list | ps | kill | kill-mine TEXT MAXAGE' >&2; exit 2 ;;
esac
