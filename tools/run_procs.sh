#!/bin/bash
# run_procs.sh: the pipeline's processes in WSL, behind run.ps1 (run ps, run
# kill, its busy refusal and the clean-up after every run).  Each one is a
# python running test_full_pipeline.py, run_bridge_on_finddice.py or
# run_planner.py.
#   bash run_procs.sh list                     one line each; nothing when none
#   bash run_procs.sh kill                     TERM, then KILL, every one of them
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
    local now p c age cpu dir newest quiet flag f pstart
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
        printf 'pid %-7s %7s old  %5s%% cpu  %-15s %s\n' "$p" "$(age_text "$age")" "${cpu:-?}" "$flag" "$(what "$c")"
    done
}

kill_pids() {   # TERM, then KILL for the survivors
    local pids="$*" p alive i
    [ -z "${pids// /}" ] && return 0
    for p in $pids; do printf 'ending pid %s: %s\n' "$p" "$(what "$(cmdline "$p")")"; done
    kill -TERM $pids 2>/dev/null
    for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 0.3
        alive=''
        for p in $pids; do [ -d "/proc/$p" ] && alive="$alive $p"; done
        [ -z "$alive" ] && break
    done
    if [ -n "$alive" ]; then
        kill -KILL $alive 2>/dev/null
        sleep 0.5
        for p in $alive; do [ -d "/proc/$p" ] && printf 'pid %s would not die\n' "$p"; done
    fi
}

case "$1" in
    list)
        list ;;
    kill)
        kill_pids $(pipeline_pids)
        left=$(list)
        if [ -n "$left" ]; then echo 'still there:'; echo "$left"; exit 1; fi ;;
    kill-mine)
        text="$2"; maxage="${3:-100000}"; mine=''
        for p in $(pipeline_pids); do
            c=$(cmdline "$p"); age=$(ps -o etimes= -p "$p" 2>/dev/null | tr -d ' ')
            [[ "$c" == *"$text"* ]] && [ "${age:-0}" -le "$maxage" ] && mine="$mine $p"
        done
        kill_pids $mine ;;
    *)
        echo 'usage: run_procs.sh list | kill | kill-mine TEXT MAXAGE' >&2; exit 2 ;;
esac
