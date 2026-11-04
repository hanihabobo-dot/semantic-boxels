#!/bin/bash
# BF#64 local check: the bridge from the checkout (the shadow caster on their
# shortened table), one headless episode per seed, in order, under the
# pipeline lock.  A generated scene (tampura_bridge/gen_scenes) runs from a
# directory holding only that scene with the manifest's G19 pin, as
# run.ps1 -Gen and tools/gen_scene_eval.py do; any other seed is a shipped
# scene, run as `run tampura -Headless` does.  The 900 s cap is BF#63's.
#   tr -d '\r' < check.sh | bash -s -- OUT SEED...
# Writes OUT/s<seed>/ (the run directory and console.txt) and OUT/SUMMARY.txt.
set -u
S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
TW=/root/tampura-work
PY=/root/armO-venvA/bin/python
G=$S/tampura_bridge/gen_scenes/find_dice
OUT=${1:?out dir}
shift
mkdir -p "$OUT"
exec 9>/root/sb_pipeline.lock
flock 9
for s in "$@"; do
    d=$OUT/s$s
    rm -rf "$d"
    mkdir -p "$d"
    if [ -f "$G/find_dice_gen_s$s.json" ]; then
        c=$OUT/cwd_s$s
        rm -rf "$c"
        mkdir -p "$c/tampura_environments/find_dice/problems"
        cp "$G/find_dice_gen_s$s.json" "$c/tampura_environments/find_dice/problems/"
        ln -s "$TW/tampura_environments/env_configs" "$c/env_configs"
        man=$G/manifest.json
    else
        c=$TW/tampura_environments
        man=
    fi
    t0=$(date +%s)
    (cd "$c" && env ${man:+BRIDGE_SCENE_MANIFEST=$man} \
        PYTHONPATH=$S:$S/pddlstream_lib:$TW/tampura:$TW/tampura_environments PYTHONHASHSEED=0 \
        timeout -s INT 900 "$PY" "$S/tampura_bridge/run_bridge_on_finddice.py" --global-seed "$s" \
        --vis 0 --save-dir "$d" --allow-g19-mismatch 1 > "$d/console.txt" 2>&1)
    rc=$?
    wall=$(( $(date +%s) - t0 ))
    [ -n "$man" ] && rm -rf "$c"
    scene=$(grep -o 'Loading scene from [^ ]*' "$d/console.txt" | head -1 | cut -d' ' -f4)
    seen=$(grep -o 'I see [0-9]* objects on the table and [0-9a-z]* spaces\? hidden' "$d/console.txt" | head -1)
    degen=$(grep -c 'degenerate shadow AABB' "$d/console.txt")
    end=$(grep -E '^(✔|✘)' "$d/console.txt" | tail -1)
    outcome=$(grep -o 'outcome [a-z_]*' "$d/console.txt" | tail -1)
    printf 'seed %s  rc %s  wall %ss  %s  degenerate %s  %s  | %s | %s\n' \
        "$s" "$rc" "$wall" "${scene:-?}" "$degen" "${outcome:-no outcome}" "${seen:-?}" "${end:-?}" \
        | tee -a "$OUT/SUMMARY.txt"
done
