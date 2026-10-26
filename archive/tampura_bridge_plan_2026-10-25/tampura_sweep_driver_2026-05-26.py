#!/usr/bin/env python3
"""Headless multi-seed sweep of TAMPURA find_dice.

For each seed: run run_planner.py as an isolated subprocess (headless), time it,
then read success + timing from the saved RolloutHistory pickle. Writes an
incremental JSON after every seed (atomic), and is resumable (skips seeds already
recorded as complete in --out).
"""
import os, glob, json, time, pickle, subprocess, argparse, re, statistics, datetime

ROOT = "/root/tampura-work"
ENVREPO = os.path.join(ROOT, "tampura_environments")
RUNS = os.path.join(ENVREPO, "runs")
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
VENV_BIN = os.path.join(ROOT, ".venv", "bin")
CONFIG = "./env_configs/find_dice.yml"
CONSOLE_DIR = os.path.join(ROOT, "sweep_consoles")
ENV_CFG_SNAP = None


def log(*a):
    print(*a, flush=True)


def parse_seeds(s):
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def find_symk_times(text):
    return [float(x) for x in re.findall(r"Time:\s*([0-9]+\.?[0-9]*)", text)]


def load_history(run_dir):
    pks = sorted(glob.glob(os.path.join(run_dir, "*.pkl")), key=os.path.getmtime)
    if not pks:
        return None
    with open(pks[-1], "rb") as fh:
        return pickle.load(fh)


def summarize(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"mean": None, "std": None, "n": 0}
    return {
        "mean": round(statistics.fmean(vals), 3),
        "std": round(statistics.pstdev(vals), 3) if len(vals) > 1 else 0.0,
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
        "n": len(vals),
    }


def write_json(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def build_payload(seeds, per_seed):
    succ = [r for r in per_seed if r.get("success")]
    done = len(per_seed)
    sr = (len(succ) / done) if done else None
    return {
        "config": os.path.basename(CONFIG),
        "task": "find_dice",
        "n_seeds_planned": len(seeds),
        "n_seeds_done": done,
        "per_seed": per_seed,
        "aggregate": {
            "success_rate": round(sr, 4) if sr is not None else None,
            "n_success": len(succ),
            "wall_s_all": summarize([r.get("wall_s") for r in per_seed]),
            "loop_s_all": summarize([r.get("loop_s") for r in per_seed]),
            "wall_s_success": summarize([r.get("wall_s") for r in succ]),
            "loop_s_success": summarize([r.get("loop_s") for r in succ]),
            "symk_solve_s_all": summarize([r.get("symk_solve_s") for r in per_seed]),
        },
        "metric_notes": {
            "wall_s": "Full subprocess wall-clock (process start to exit), perf_counter. Includes Python+pybullet startup/teardown.",
            "loop_s": "RolloutHistory.time_deltas[-1]: TAMPURA internal planner-loop elapsed (planning + pybullet action execution inside the policy loop). Closest analog to the paper per-episode time; excludes process startup/teardown.",
            "symk_solve_s": "Best-effort sum of SymK 'Time:' values parsed from console stdout. Approximate; null if not emitted.",
            "success": "True iff rewards[-1] == 1.0 (target die grasped AND robot at-home on terminal belief). Episode runs to max_steps doing no-op() after the goal.",
            "solve_step": "First step index where reward becomes 1.0 (None if never).",
        },
        "env_config_snapshot": ENV_CFG_SNAP,
        "paper_ref": {
            "planning_s": "57 +/- 38", "success_rate": ">= 0.63", "n_seeds": 20,
            "source": "Curtis et al. 2024 arXiv:2403.10454, Partial Observability task",
        },
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
    }


def main():
    global ENV_CFG_SNAP
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-19")
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-episode-timeout", type=int, default=900)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    seeds = parse_seeds(args.seeds)
    os.makedirs(CONSOLE_DIR, exist_ok=True)
    os.makedirs(RUNS, exist_ok=True)
    out = args.out
    log(f"[sweep] seeds={seeds}")
    log(f"[sweep] out={out}")

    fdp = os.path.join(ENVREPO, "env_configs", "find_dice.yml")
    ENV_CFG_SNAP = open(fdp).read() if os.path.isfile(fdp) else None

    # SymK's translate/search steps shell out to bare 'python', so the venv bin
    # MUST be on the child's PATH (equivalent to `source .venv/bin/activate`).
    child_env = os.environ.copy()
    child_env["PATH"] = VENV_BIN + os.pathsep + child_env.get("PATH", "")
    child_env["VIRTUAL_ENV"] = os.path.join(ROOT, ".venv")
    child_env.pop("PYTHONHOME", None)

    per_seed = []
    done_seeds = set()
    if (not args.no_resume) and os.path.isfile(out):
        try:
            prev = json.load(open(out))
            per_seed = prev.get("per_seed", [])
            done_seeds = {r["seed"] for r in per_seed if r.get("_complete")}
            log(f"[sweep] resuming; already done: {sorted(done_seeds)}")
        except Exception as e:
            log("[sweep] resume read failed:", repr(e))

    for seed in seeds:
        if seed in done_seeds:
            log(f"[seed {seed}] skip (already complete)")
            continue
        log(f"\n[seed {seed}] start {datetime.datetime.now().isoformat(timespec='seconds')}")
        before = set(glob.glob(os.path.join(RUNS, "run_*")))
        console_path = os.path.join(CONSOLE_DIR, f"seed_{seed}.log")
        cmd = [VENV_PY, "-u", "run_planner.py", f"--config={CONFIG}", f"--global-seed={seed}"]
        t0 = time.perf_counter()
        rc, timed_out = None, False
        try:
            with open(console_path, "w") as cf:
                proc = subprocess.run(cmd, cwd=ENVREPO, stdout=cf, env=child_env,
                                      stderr=subprocess.STDOUT, timeout=args.per_episode_timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out, rc = True, -1
            log(f"[seed {seed}] TIMEOUT after {args.per_episode_timeout}s")
        wall_s = time.perf_counter() - t0

        try:
            console_text = open(console_path, errors="replace").read()
        except Exception:
            console_text = ""

        after = set(glob.glob(os.path.join(RUNS, "run_*")))
        new_dirs = sorted(after - before, key=os.path.getmtime)
        run_dir = new_dirs[-1] if new_dirs else None

        rec = {
            "seed": seed, "success": False, "wall_s": round(wall_s, 3), "loop_s": None,
            "symk_solve_s": None, "solve_step": None, "max_reward": None, "n_actions": None,
            "rewards": None, "returncode": rc, "timed_out": timed_out, "run_dir": run_dir,
            "console_log": console_path, "note": "", "_complete": True,
        }

        hist = None
        if run_dir:
            try:
                hist = load_history(run_dir)
            except Exception as e:
                rec["note"] += f"pkl load failed: {e!r}; "
        if hist is not None:
            rewards = [float(r) for r in (getattr(hist, "rewards", []) or [])]
            td = list(getattr(hist, "time_deltas", []) or [])
            actions = list(getattr(hist, "actions", []) or [])
            rec["rewards"] = rewards
            rec["n_actions"] = len([a for a in actions if str(a) != "None"])
            rec["loop_s"] = round(td[-1], 3) if td else None
            if rewards:
                rec["success"] = rewards[-1] == 1.0
                rec["max_reward"] = max(rewards)
                rec["solve_step"] = next((i for i, r in enumerate(rewards) if r == 1.0), None)
        else:
            rec["note"] += "no run_dir/history found; "

        symk = find_symk_times(console_text)
        if symk:
            rec["symk_solve_s"] = round(sum(symk), 3)
        if timed_out:
            rec["note"] += "subprocess timed out; "
        if rc not in (0, None) and not rec["success"]:
            rec["note"] += f"nonzero rc={rc}; "
        if rc == 139:
            rec["note"] += "(pybullet teardown segfault, cosmetic); "

        per_seed = [r for r in per_seed if r.get("seed") != seed]
        per_seed.append(rec)
        per_seed.sort(key=lambda r: r["seed"])
        write_json(out, build_payload(seeds, per_seed))
        log(f"[seed {seed}] success={rec['success']} wall_s={rec['wall_s']} "
            f"loop_s={rec['loop_s']} solve_step={rec['solve_step']} rc={rc} "
            f"dir={os.path.basename(run_dir) if run_dir else None} note='{rec['note'].strip()}'")

    payload = build_payload(seeds, per_seed)
    write_json(out, payload)
    with open(out + ".DONE", "w") as fh:
        fh.write(datetime.datetime.now().isoformat())
    agg = payload["aggregate"]
    log("\n[sweep] DONE")
    log(f"[sweep] success_rate={agg['success_rate']}  loop_s_all={agg['loop_s_all']}")
    log(f"[sweep] wall_s_all={agg['wall_s_all']}")
    log(f"[sweep] wrote {out}")


if __name__ == "__main__":
    main()
