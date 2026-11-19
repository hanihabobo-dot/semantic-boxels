"""paired_sets.py: the paired-set runner and its analysis (sets N, S, A, B).

Phase 0 tool of the readable migration (PLAN section 8 and 24.4; R's
PLAN_REVIEW S-o to S-r and note 3 of section 7). It never imports pybullet or
the pipeline: episodes run in WSL children through the health gate, and the
runner and the analysis only read the files those children leave.

    python tools/readable/paired_sets.py plan    --set-dir DIR
    python tools/readable/paired_sets.py scripts --set-dir DIR --out FOLDER
    python tools/readable/paired_sets.py run     --set-dir DIR
    python tools/readable/paired_sets.py analyse --set-dir DIR [--crash-reviews F] [--json OUT]

DIR is the set's folder (`evals/<id>/`); it holds `DECLARATION.md`, written
before the first run from `DECLARATION_TEMPLATE.md`. Its one fenced block
marked `json paired-set` is what this tool reads; the prose around it is for
people. `plan` checks the declaration and prints the run list (the ABBA
order with position numbers, to paste into the declaration's `runs`).
`scripts` writes every episode script into FOLDER for reading, launching
nothing. `run` runs the declared list once, one episode at a time, each
through `gate_run.ps1` (health gate, lock free at its start) and inside the
episode script under `flock` on the pipeline lock; it runs on Windows (pwsh
and wsl.exe). `analyse` recomputes everything from `results.jsonl`.

The episode of each world, as the launchers build it:

- boxels: cwd the arm's checkout, `PYTHONHASHSEED=0`, the argv of
  `eval_runner.cell_to_argv` (`test_full_pipeline.py --no-gui --scene
  random-pairs --seed S --goal holding --baseline semantic --log-level quiet
  --no-telemetry --n-occluders 2`). Before every boxels episode of both arms
  the stored copy of the statistics file is restored into
  `<checkout>/statistics/py3/boxel-streams.pkl` under the same hold of the
  lock as the episode, its sha256 checked against the declared one and
  written into the row (PLAN 24.4 (e)).
- bridge: cwd `$TW/tampura_environments`, `PYTHONPATH=<checkout>:<lib>:
  $TW/tampura:$TW/tampura_environments`, `PYTHONHASHSEED=0`,
  `tampura_bridge/run_bridge_on_finddice.py --global-seed S --vis 0
  --save-dir <fresh folder> --allow-g19-mismatch 1` (run.ps1 -Headless). The
  episode makes its own fresh `work/` folder (policy.py:185-189) and starts
  from no statistics file: the row's sha256 is null (R's note 3).
- both: `timeout -k 30 <cap>` around the child (GNU timeout signals the
  whole process group), MemAvailable checked with the lock held (rule 16:
  under the declared GB the episode does not start), stdin from /dev/null.

Statuses of a run (the `status` field of an end row):

- boxels: success, failure, timeout (killed at the cap), preflight_rejected
  (no summary, the `[pre-flight] seed N rejected: M` line, and no traceback
  but the re-raised one in stderr after the line that ends in `<type>: M`),
  crashed (rc not 0 or 1, no timing_summary.json in a new run directory, or
  any other traceback in stdout, stderr or the run directory's logs: PLAN 8,
  the C-01 bullet), wrong_scene (the summary's run_config is another cell's).
- bridge: success (reward 1.0 and no failed gate other than G19, PLAN_REVIEW
  S-q), failure, gate_failed (a failed gate other than G19, or the G19 or
  G13 stop before any bridge_episode.json), killed (at the cap), crashed
  (outcome.error, outcome status crashed, no bridge_episode.json without a
  gate stop, or a traceback), wrong_scene (bridge_episode.json names
  another seed).
- both: not_started (the gate stayed closed, memory low, restore failed:
  the runner stops the set there), vanished (a start row with no end row,
  found by the analysis).

Counting (PLAN 24.4 (f)): the first end row of a position counts; only
`success` is a success; a crash is a failure; nothing is re-run or replaced.
A set is full when every declared position has exactly one start and one
end row that match the declaration, no row is not_started, vanished or
wrong_scene, the declaration's sha256 is the one the rows carry, both
arms' checkouts stayed at their sha and clean, and every bridge pair saw
one scene file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from fractions import Fraction
from math import comb
from pathlib import Path

WORLDS = ("boxels", "bridge")
KINDS = ("N", "S", "A", "B")
ARMS = ("A", "B")
DECLARATION_NAME = "DECLARATION.md"
RESULTS_NAME = "results.jsonl"
STATS_REL = "statistics/py3/boxel-streams.pkl"
TRACEBACK = "Traceback (most recent call last)"
# test_full_pipeline.py prints this to stderr and exits 1 before any run
# directory (eval_runner.py:533-543).
PREFLIGHT_RE = re.compile(r"^\[pre-flight\] seed \S+ rejected: .*$", re.M)
# The driver's stop before any bridge_episode.json (run_bridge_on_finddice.py
# :265); NOT its note under --allow-g19-mismatch 1 (:274-277), which says
# "the campaign pins" and lets the run go on.
G19_STOP_RE = re.compile(r"^G19: seed \d+ loaded .*, pinned .*$", re.M)
G13_STOP_TEXT = "G13 runtime check failed"
SUCCESS = "success"
# Statuses that leave the set not full (they are no attempt of the pipeline,
# or not the declared cell).
NOT_FULL_STATUSES = {"not_started", "vanished", "wrong_scene"}
# Outcome kinds item 2 of 24.4 (b) compares; crashes are item 1's (a crash
# is judged by its review pair), the not-full statuses make no pass.
ITEM2_EXCLUDED = {"crashed"} | NOT_FULL_STATUSES
TIMEOUT_RCS = (124, 137)          # GNU timeout: TERM sent / KILL after -k
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SET_ID = re.compile(r"^[A-Za-z0-9_-]+$")
VALIDITY_NOTES = (
    "(1) an episode's first plan is not repeatable (TB-24): the arms are "
    "compared as distributions over paired seeds, never episode by episode",
    "(2) plan time caps are wall clock, so laptop load changes plans; "
    "times are not compared",
    "(3) the laptop's scene listing for the shipped bridge seeds differs "
    "from the cluster's pinned one: these numbers are not comparable with "
    "the paper's; both arms see the same scene per seed",
)


class DeclarationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Paths: the runner runs on Windows, the episodes in WSL
# ---------------------------------------------------------------------------

_WIN_PATH = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_MNT_PATH = re.compile(r"^/mnt/([a-z])/(.*)$")


def to_wsl(p) -> str:
    """`C:\\x\\y` to `/mnt/c/x/y`; a POSIX path is returned as it is."""
    s = str(p)
    m = _WIN_PATH.match(s)
    if m:
        return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")
    return s


def to_local(p) -> str:
    """The path in this interpreter's form (Windows or WSL)."""
    s = str(p)
    if os.name == "nt":
        m = _MNT_PATH.match(s)
        if m:
            return f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
        return s
    return to_wsl(s)


def sha256_file(path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(to_local(path), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------

_BLOCK = re.compile(r"^```json paired-set[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)


def read_declaration(path) -> tuple[dict, str]:
    """The declaration's JSON block (checked) and the file's sha256."""
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n")    # a CRLF checkout reads the same
    blocks = _BLOCK.findall(text)
    if len(blocks) != 1:
        raise DeclarationError(
            f"{path}: {len(blocks)} blocks marked ```json paired-set, want 1")
    try:
        decl = json.loads(blocks[0])
    except json.JSONDecodeError as e:
        raise DeclarationError(f"{path}: the json paired-set block: {e}") from e
    errors = validate_declaration(decl)
    if errors:
        raise DeclarationError(f"{path}:\n  " + "\n  ".join(errors))
    return decl, hashlib.sha256(raw).hexdigest()


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_declaration(d) -> list[str]:
    e: list[str] = []
    if not isinstance(d, dict):
        return ["the block is not a JSON object"]
    if d.get("declaration_version") != 1:
        e.append("declaration_version must be 1")
    if not isinstance(d.get("set_id"), str) or not SET_ID.match(d.get("set_id") or ""):
        e.append("set_id: letters, digits, _ and - only")
    kind = d.get("kind")
    if kind not in KINDS:
        e.append(f"kind must be one of {KINDS}")
    arms = d.get("arms")
    if not isinstance(arms, dict) or sorted(arms) != sorted(ARMS):
        e.append("arms: exactly A and B")
        arms = {}
    for name, a in list(arms.items()):
        if not isinstance(a, dict):
            e.append(f"arms.{name}: an object")
            arms = {k: v for k, v in arms.items() if k != name}
            continue
        if not isinstance(a.get("sha"), str) or not SHA40.match(a["sha"]):
            e.append(f"arms.{name}.sha: the full 40-hex sha")
        if not isinstance(a.get("checkout"), str) or not a["checkout"]:
            e.append(f"arms.{name}.checkout: the arm's frozen checkout")
    if arms.get("A", {}).get("role") != "old" or arms.get("B", {}).get("role") != "new":
        e.append("arms: A has role old and B role new (set N: B is the "
                 "second copy of the reference)")
    sa, sb = arms.get("A", {}).get("sha"), arms.get("B", {}).get("sha")
    if kind == "N" and sa != sb:
        e.append("kind N: both arms are the reference, one sha")
    if kind in ("S", "A", "B") and sa == sb:
        e.append(f"kind {kind}: the two arms have different shas")
    worlds = d.get("worlds")
    if not isinstance(worlds, dict) or not worlds or set(worlds) - set(WORLDS):
        e.append(f"worlds: a non-empty subset of {WORLDS}")
        worlds = {}
    for w, spec in worlds.items():
        if not isinstance(spec, dict):
            e.append(f"worlds.{w}: an object")
            continue
        seeds = spec.get("seeds")
        if (not isinstance(seeds, list) or not seeds
                or not all(isinstance(s, int) and not isinstance(s, bool) and s >= 0
                           for s in seeds)
                or len(set(seeds)) != len(seeds)):
            e.append(f"worlds.{w}.seeds: distinct non-negative integers, at least one")
        if not _is_num(spec.get("cap_s")) or spec["cap_s"] <= 0:
            e.append(f"worlds.{w}.cap_s: the per-episode wall cap in seconds")
        if w == "boxels":
            cell = spec.get("cell")
            want = {"scene": str, "goal": str, "baseline": str,
                    "n_occluders": int, "unit_costs": bool}
            if not isinstance(cell, dict) or set(cell) != set(want):
                e.append(f"worlds.boxels.cell: exactly the keys {sorted(want)}")
            else:
                for k, t in want.items():
                    if not isinstance(cell[k], t) or (t is int and isinstance(cell[k], bool)):
                        e.append(f"worlds.boxels.cell.{k}: a {t.__name__}")
                if cell.get("scene") != "random-pairs":
                    e.append("worlds.boxels.cell.scene: random-pairs (the "
                             "argv is eval_runner's random-pairs form)")
        elif set(spec) - {"seeds", "cap_s"}:
            e.append("worlds.bridge: only seeds and cap_s (launcher defaults)")
    order = d.get("world_order")
    if not isinstance(order, list) or sorted(order) != sorted(worlds):
        e.append("world_order: every declared world once")
    if d.get("pairing") != "by_seed":
        e.append("pairing: by_seed")
    if d.get("order") != "ABBA":
        e.append("order: ABBA")
    if d.get("switches") != []:
        e.append("switches: [] (launcher defaults, PLAN 8); another switch "
                 "is a change of the plan")
    m = d.get("machine")
    need = {"python": str, "pythonhashseed": str, "lock": str, "gate_script": str,
            "gate_max_minutes": int, "mem_available_min_gb": (int, float),
            "pause_s": (int, float), "wsl_distro": str, "tampura_work": str,
            "pddlstream_lib": str}
    if not isinstance(m, dict):
        e.append("machine: an object")
    else:
        for k, t in need.items():
            if k not in m or not isinstance(m[k], t) or isinstance(m[k], bool):
                e.append(f"machine.{k}: missing or of the wrong type")
        if m.get("pythonhashseed") != "0":
            e.append('machine.pythonhashseed: "0"')
    st = d.get("statistics_file")
    if not isinstance(st, dict):
        e.append("statistics_file: an object")
        st = {}
    if "boxels" in worlds:
        b = st.get("boxels")
        if (not isinstance(b, dict) or not isinstance(b.get("stored_copy"), str)
                or not SHA64.match(str(b.get("sha256")))):
            e.append("statistics_file.boxels: stored_copy and its sha256 "
                     "(64 hex), restored before every boxels episode")
    if "bridge" in worlds:
        b = st.get("bridge")
        if not isinstance(b, dict) or b.get("sha256", "x") is not None:
            e.append("statistics_file.bridge: sha256 null (each bridge "
                     "episode starts from no file in its fresh work folder)")
    if kind in ("A", "B"):
        if not isinstance(d.get("noise_set_dir"), str) or not d["noise_set_dir"]:
            e.append(f"kind {kind}: noise_set_dir, the folder of set N")
    elif d.get("noise_set_dir") is not None:
        e.append(f"kind {kind}: noise_set_dir null")
    if not _is_num(d.get("pair_gap_max_s")) or d["pair_gap_max_s"] <= 0:
        e.append("pair_gap_max_s: seconds between the two starts of a pair "
                 "above which the pair is flagged")
    if not e and d.get("runs") is not None and d["runs"] != run_list(d):
        e.append("runs: differs from the ABBA list `plan` prints")
    return e


def run_list(d) -> list[dict]:
    """The declared run sequence: worlds in world_order, seeds in their
    declared order; pair k runs A then B when k is even, B then A when odd
    (A B B A A B ...), the alternation carried across worlds."""
    runs, k, pos = [], 0, 1
    for w in d["world_order"]:
        for seed in d["worlds"][w]["seeds"]:
            for arm in (("A", "B") if k % 2 == 0 else ("B", "A")):
                runs.append({"pos": pos, "pair": k, "world": w, "seed": seed, "arm": arm})
                pos += 1
            k += 1
    return runs


def episode_name(r) -> str:
    return f"{r['pos']:03d}_{r['world']}_s{r['seed']}_{r['arm']}"


# ---------------------------------------------------------------------------
# The episode scripts (WSL, bash)
# ---------------------------------------------------------------------------

def boxels_argv(cell: dict, seed: int) -> list[str]:
    """eval_runner.cell_to_argv for a random-pairs cell, without
    sys.executable (eval_runner.py:401-467)."""
    argv = ["test_full_pipeline.py", "--no-gui", "--scene", str(cell["scene"]),
            "--seed", str(seed), "--goal", str(cell["goal"]),
            "--baseline", str(cell["baseline"]), "--log-level", "quiet",
            "--no-telemetry", "--n-occluders", str(cell["n_occluders"])]
    if cell["unit_costs"]:
        argv.append("--unit-costs")
    return argv


def bridge_argv(checkout_wsl: str, seed: int, save_dir_wsl: str) -> list[str]:
    """run.ps1:149-151 with -Headless (`--vis 0`, `--allow-g19-mismatch 1`)."""
    return [f"{checkout_wsl}/tampura_bridge/run_bridge_on_finddice.py",
            "--global-seed", str(seed), "--vis", "0",
            "--save-dir", save_dir_wsl, "--allow-g19-mismatch", "1"]


_UNSET = ("FORCE_COLOR", "NO_COLOR", "SB_CONSOLE_ASCII", "SB_AUDIO", "SB_VOICE",
          "PYTHONSTARTUP", "PYTHONINSPECT", "BOXEL_EYE_IMAGES",
          "BRIDGE_SCENE_MANIFEST", "PYTHONPATH", "TAMPURA_WORK")


def episode_script(d: dict, r: dict, ep_dir) -> str:
    """The bash script of one episode. It exits 0 whenever it ran to its
    end; what happened is in the episode folder (launch.txt, not_started.txt,
    stdout.txt, stderr.txt, runs_before.txt, runs_after.txt)."""
    m = d["machine"]
    arm = d["arms"][r["arm"]]
    q = shlex.quote
    ep = to_wsl(ep_dir)
    co = to_wsl(arm["checkout"])
    cap = d["worlds"][r["world"]]["cap_s"]
    min_kb = int(float(m["mem_available_min_gb"]) * 1024 * 1024)
    head = [
        "#!/bin/bash",
        f"# paired_sets.py: set {d['set_id']} run {r['pos']} ({r['world']} seed "
        f"{r['seed']} arm {r['arm']} {arm['sha']})",
        "set -u",
        f"EP={q(ep)}",
        f"L={q(m['lock'])}",
        'note() { echo "$1=$2" >> "$EP/launch.txt"; }',
        'stop() { echo "reason=$1" >> "$EP/not_started.txt"; exit 0; }',
        'exec 9>>"$L" || stop lock_unopenable',
        "flock 9",
        'note lock_taken "$(date +%s.%N)"',
        "MA=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)",
        'note mem_available_kb "$MA"',
        "note load_start \"$(cut -d' ' -f1-3 /proc/loadavg)\"",
        f'if [ "$MA" -lt {min_kb} ]; then stop mem_available_under_{m["mem_available_min_gb"]}_gb; fi',
        "unset " + " ".join(_UNSET),
        "export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1",
    ]
    if r["world"] == "boxels":
        st = d["statistics_file"]["boxels"]
        argv = " ".join(q(a) for a in boxels_argv(d["worlds"]["boxels"]["cell"], r["seed"]))
        body = [
            f"cd {q(co)} || stop no_checkout",
            "mkdir -p statistics/py3 || stop restore_failed",
            f"cp -f {q(to_wsl(st['stored_copy']))} {STATS_REL} || stop restore_failed",
            f"H=$(sha256sum {STATS_REL} | cut -d' ' -f1)",
            'note stats_sha256_before "$H"',
            f'if [ "$H" != {q(st["sha256"])} ]; then stop restore_failed; fi',
            'ls -1d "$PWD"/logs/run_* 2>/dev/null | sort > "$EP/runs_before.txt"',
            'note launched_at "$(date +%s.%N)"',
            f"timeout -k 30 {cap} {q(m['python'])} {argv} "
            '< /dev/null > "$EP/stdout.txt" 2> "$EP/stderr.txt"',
            "rc=$?",
            'note ended_at "$(date +%s.%N)"',
            'note rc "$rc"',
            'ls -1d "$PWD"/logs/run_* 2>/dev/null | sort > "$EP/runs_after.txt"',
            f"note stats_sha256_after \"$(sha256sum {STATS_REL} 2>/dev/null | cut -d' ' -f1)\"",
        ]
    else:
        tw = m["tampura_work"]
        save = f"{ep}/save"
        pp = ":".join([co, to_wsl(m["pddlstream_lib"]), f"{tw}/tampura",
                       f"{tw}/tampura_environments"])
        argv = " ".join(q(a) for a in bridge_argv(co, r["seed"], save))
        body = [
            f'if [ -e {q(save)} ]; then stop save_dir_exists; fi',
            f"cd {q(tw + '/tampura_environments')} || stop no_tampura_environments",
            f"export PYTHONPATH={q(pp)}",
            'note launched_at "$(date +%s.%N)"',
            f"timeout -k 30 {cap} {q(m['python'])} {argv} "
            '< /dev/null > "$EP/stdout.txt" 2> "$EP/stderr.txt"',
            "rc=$?",
            'note ended_at "$(date +%s.%N)"',
            'note rc "$rc"',
        ]
    tail = ["note load_end \"$(cut -d' ' -f1-3 /proc/loadavg)\"", "exit 0", ""]
    return "\n".join(head + body + tail)


# ---------------------------------------------------------------------------
# Launchers: the real one (gate_run.ps1) and the interface a test fakes
# ---------------------------------------------------------------------------

class GateLauncher:
    """Runs one episode script through gate_run.ps1 (Windows side)."""

    def __init__(self, decl: dict, set_dir: Path):
        self.d = decl
        self.set_dir = Path(set_dir)

    def gate_command(self, script: Path, label: str) -> list[str]:
        m = self.d["machine"]
        return ["pwsh", "-NoProfile", "-File", m["gate_script"], "-Script",
                to_wsl(script), "-Label", label, "-MaxMinutes",
                str(m["gate_max_minutes"])]

    def run_episode(self, r: dict, ep_dir: Path) -> dict:
        script = ep_dir / "episode.sh"
        script.write_bytes(episode_script(self.d, r, ep_dir).encode("utf-8"))
        cmd = self.gate_command(script, f"paired-{self.d['set_id']}-{r['pos']:03d}")
        limit = (self.d["machine"]["gate_max_minutes"] * 60
                 + self.d["worlds"][r["world"]]["cap_s"] + 300)
        with open(ep_dir / "gate.txt", "wb") as out:
            p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL)
            try:
                rc = p.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                p.kill()          # our own pwsh; the episode's timeout ends the child
                p.wait()
                return {"gate_rc": None, "gate_timed_out": True}
        return {"gate_rc": rc, "gate_timed_out": False}

    def probe(self) -> dict:
        """S-p: each arm's HEAD and `git status --porcelain`, the library's
        commit, the venv's pip freeze sha256 (Windows git, one WSL call)."""
        out = {"arms": {}, "library_commit": None, "venv": None}
        for name, a in self.d["arms"].items():
            win = to_local(a["checkout"])
            status = _git(win, "status", "--porcelain")
            out["arms"][name] = {"head": _git(win, "rev-parse", "HEAD"),
                                 "dirty": status is None or status != "",
                                 "status": (status or "")[:2000]}
        out["library_commit"] = _git(to_local(self.d["machine"]["pddlstream_lib"]),
                                     "rev-parse", "HEAD")
        m = self.d["machine"]
        probe = self.set_dir / "probe.sh"
        probe.write_bytes((
            "#!/bin/bash\n"
            f"echo \"pip_freeze_sha256=$({shlex.quote(m['python'])} -m pip freeze "
            "2>/dev/null | sha256sum | cut -d' ' -f1)\"\n"
            f"echo \"python_version=$({shlex.quote(m['python'])} -V 2>&1)\"\n"
        ).encode("utf-8"))
        try:
            p = subprocess.run(["wsl", "-d", m["wsl_distro"], "-u", "root", "--",
                                "bash", to_wsl(probe)], capture_output=True,
                               text=True, timeout=180)
            out["venv"] = _kv(p.stdout)
        except (OSError, subprocess.TimeoutExpired) as e:
            out["venv"] = {"error": repr(e)}
        return out


def _git(path: str, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", "-C", path, *args], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _kv(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


# ---------------------------------------------------------------------------
# Classification of one finished run, from its files only
# ---------------------------------------------------------------------------

def _read(path) -> str:
    try:
        return Path(to_local(path)).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_json(path):
    try:
        return json.loads(Path(to_local(path)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _tracebacks(files: dict) -> list[str]:
    return sorted(name for name, text in files.items() if TRACEBACK in text)


def _preflight_rejection(texts: dict) -> str | None:
    """The pre-flight line when the run is a real pre-flight rejection.

    test_full_pipeline.py:3335-3337 prints the line and re-raises the
    RuntimeError; under --log-level quiet no Console excepthook is installed,
    so the interpreter writes that exception's traceback to stderr. The run
    is a rejection when the line is there and the only traceback anywhere is
    one in stderr.txt, after the line, whose exception line is
    `<type>: <the line's message>`. Any other traceback (a second one, one
    before the line, one in stdout or a log, one that ends in another
    message) keeps the run a crash. eval_runner.py:671-683 classifies by the
    line alone.
    """
    line = PREFLIGHT_RE.search(texts["stderr.txt"]) or PREFLIGHT_RE.search(texts["stdout.txt"])
    if not line:
        return None
    found = line.group(0).strip()
    counts = {name: text.count(TRACEBACK) for name, text in texts.items()}
    if sum(counts.values()) == 0:
        return found
    if counts.get("stderr.txt") != 1 or sum(counts.values()) != 1:
        return None
    err = texts["stderr.txt"]
    m_line = PREFLIGHT_RE.search(err)
    if m_line is None or err.index(TRACEBACK) < m_line.end():
        return None
    message = found.split(" rejected: ", 1)[1]
    exc_line = None
    for x in err[err.index(TRACEBACK) + len(TRACEBACK):].splitlines()[1:]:
        if x and not x[0].isspace():
            exc_line = x.rstrip()
            break
    if exc_line is None:
        return None
    m_exc = re.match(r"^([A-Za-z_][\w.]*): (.*)$", exc_line)
    if m_exc is None or m_exc.group(2) != message.rstrip():
        return None
    return found


def _launch_facts(ep: Path, launch_info: dict) -> dict:
    launch = _kv(_read(ep / "launch.txt"))
    ns = _kv(_read(ep / "not_started.txt"))
    facts = {"launch": launch, "rc": None, "wall_s": None, "timed_out": False,
             "mem_available_kb": launch.get("mem_available_kb"),
             "launched_at": _float(launch.get("launched_at")),
             "ended_at": _float(launch.get("ended_at")),
             "gate_rc": launch_info.get("gate_rc")}
    if ns or "launched_at" not in launch:
        if ns.get("reason"):
            why = ns["reason"]
        elif launch_info.get("gate_timed_out"):
            why = "gate_wait_over_limit"
        elif launch_info.get("gate_rc") == 3:
            why = "gate_closed"
        else:
            why = "no_launch_record"
        facts["not_started"] = why
        return facts
    if "rc" in launch:
        try:
            facts["rc"] = int(launch["rc"])
        except ValueError:
            facts["rc"] = None
    if facts["launched_at"] is not None and facts["ended_at"] is not None:
        facts["wall_s"] = round(facts["ended_at"] - facts["launched_at"], 3)
    return facts


def _timed_out(facts: dict, cap: float) -> bool:
    return (facts["rc"] in TIMEOUT_RCS and facts["wall_s"] is not None
            and facts["wall_s"] >= cap - 1.0)


def classify_boxels(d: dict, r: dict, ep: Path, launch_info: dict) -> dict:
    cap = d["worlds"]["boxels"]["cap_s"]
    cell = d["worlds"]["boxels"]["cell"]
    f = _launch_facts(ep, launch_info)
    row = {"status": None, "success": False, "crash_cause": None,
           "exit_reason": None, "rc": f["rc"], "wall_s": f["wall_s"],
           "launched_at": f["launched_at"], "ended_at": f["ended_at"],
           "mem_available_kb": f["mem_available_kb"],
           "stats_sha256": f["launch"].get("stats_sha256_before"),
           "stats_sha256_after": f["launch"].get("stats_sha256_after"),
           "run_dir": None, "traceback_in": [], "plan_count": None,
           "total_planning_time_s": None, "gate_rc": f["gate_rc"]}
    if "not_started" in f:
        row.update(status="not_started", not_started=f["not_started"])
        return row
    texts = {"stdout.txt": _read(ep / "stdout.txt"),
             "stderr.txt": _read(ep / "stderr.txt")}
    before = {x.strip() for x in _read(ep / "runs_before.txt").splitlines() if x.strip()}
    after = [x.strip() for x in _read(ep / "runs_after.txt").splitlines() if x.strip()]
    new_dirs = [p for p in after if p not in before]
    summaries = []
    for p in new_dirs:
        ts = Path(to_local(p)) / "timing_summary.json"
        if ts.is_file():
            summaries.append((ts.stat().st_mtime, p, ts))
        for log in sorted(Path(to_local(p)).glob("*.log")):
            texts[f"{Path(to_local(p)).name}/{log.name}"] = _read(log)
    summaries.sort()
    row["new_run_dirs"] = new_dirs
    row["traceback_in"] = _tracebacks(texts)
    summary = None
    if summaries:
        _, run_dir, ts = summaries[-1]
        row["run_dir"] = run_dir
        summary = _read_json(ts)
        if summary is not None:
            (ep / "timing_summary.json").write_text(json.dumps(summary, indent=1),
                                                    encoding="utf-8")
            row["exit_reason"] = summary.get("exit_reason")
            row["plan_count"] = summary.get("plan_count")
            row["total_planning_time_s"] = summary.get("total_planning_time_s")
            row["summary_success"] = summary.get("success")
    if f["rc"] is None:
        row.update(status="crashed", crash_cause="the episode script left no rc")
    elif _timed_out(f, cap):
        row.update(status="timeout", timed_out=True)
    elif f["rc"] not in (0, 1):
        row.update(status="crashed", crash_cause=f"crash_exit{f['rc']}")
    elif summary is None:
        rejection = _preflight_rejection(texts)
        if rejection:
            row.update(status="preflight_rejected", preflight_message=rejection)
        else:
            row.update(status="crashed", crash_cause="no timing_summary.json in a new run directory")
    else:
        mismatch = _summary_mismatch(summary.get("run_config"), cell, r["seed"])
        if mismatch:
            row.update(status="wrong_scene", summary_mismatch=mismatch)
        elif row["traceback_in"]:
            row.update(status="crashed",
                       crash_cause="traceback in " + ", ".join(row["traceback_in"]))
        elif summary.get("success") is True:
            row.update(status=SUCCESS, success=True)
        else:
            row.update(status="failure")
    return row


def _summary_mismatch(run_config, cell: dict, seed: int) -> str | None:
    """eval_runner._summary_mismatch (eval_runner.py:510-530) for our cell."""
    if not isinstance(run_config, dict):
        return "no run_config"
    expected = {"scene": cell["scene"], "seed": seed, "goal": cell["goal"],
                "baseline": cell["baseline"], "unit_costs": bool(cell["unit_costs"])}
    diffs = [f"{k}={run_config.get(k)!r} (cell {v!r})"
             for k, v in expected.items() if run_config.get(k) != v]
    return ", ".join(diffs) or None


def classify_bridge(d: dict, r: dict, ep: Path, launch_info: dict) -> dict:
    cap = d["worlds"]["bridge"]["cap_s"]
    f = _launch_facts(ep, launch_info)
    row = {"status": None, "success": False, "crash_cause": None,
           "exit_reason": None, "rc": f["rc"], "wall_s": f["wall_s"],
           "launched_at": f["launched_at"], "ended_at": f["ended_at"],
           "mem_available_kb": f["mem_available_kb"], "stats_sha256": None,
           "run_dir": None, "traceback_in": [], "plan_count": None,
           "total_planning_time_s": None, "gate_rc": f["gate_rc"],
           "bridge_status": None, "reward": None, "gate_failures": [],
           "scene_file": None}
    if "not_started" in f:
        row.update(status="not_started", not_started=f["not_started"])
        return row
    save = ep / "save"
    texts = {"stdout.txt": _read(ep / "stdout.txt"),
             "stderr.txt": _read(ep / "stderr.txt")}
    console = texts["stdout.txt"] + "\n" + texts["stderr.txt"]
    be = _read_json(save / "bridge_episode.json")
    run_dir = (be or {}).get("run_dir")
    if not run_dir:
        found = sorted((save / "ours").glob("run_*")) if (save / "ours").is_dir() else []
        run_dir = str(found[-1]) if found else None
    if run_dir:
        row["run_dir"] = run_dir
        rd = Path(to_local(run_dir))
        ts = _read_json(rd / "timing_summary.json")
        if isinstance(ts, dict):
            row["exit_reason"] = ts.get("exit_reason")
            row["plan_count"] = ts.get("plan_count")
            row["total_planning_time_s"] = ts.get("total_planning_time_s")
        if rd.is_dir():
            for log in sorted(rd.glob("*.log")):
                texts[f"{rd.name}/{log.name}"] = _read(log)
    row["traceback_in"] = _tracebacks(texts)
    if be is not None:
        out = be.get("outcome") or {}
        gates = dict(out.get("gate_failures") or {})
        rewards = be.get("rewards") or []
        reward = out.get("reward", rewards[-1] if rewards else None)
        row.update(bridge_status=out.get("status"), reward=_float(reward),
                   gate_failures=sorted(gates), scene_file=be.get("scene_file"),
                   bridge_seed=be.get("seed"))
    if f["rc"] is None:
        row.update(status="crashed", crash_cause="the episode script left no rc")
    elif _timed_out(f, cap):
        row.update(status="killed", timed_out=True)
    elif be is None:
        g19 = G19_STOP_RE.search(console)
        g13 = _read_json(save / "g13_runtime.json")
        if g19:
            row.update(status="gate_failed", gate_failures=["G19"],
                       gate_stop=g19.group(0).strip())
        elif G13_STOP_TEXT in console or (isinstance(g13, dict) and g13.get("ok") is False):
            row.update(status="gate_failed", gate_failures=["G13"],
                       gate_stop=G13_STOP_TEXT)
        else:
            row.update(status="crashed", crash_cause=f"rc {f['rc']}, no bridge_episode.json")
    elif f["rc"] not in (0, 1):
        # the driver exits 0 or 1 (run_bridge_on_finddice.py:358); anything
        # else after the record (a signal, a crash in the overview) is a crash
        row.update(status="crashed", crash_cause=f"crash_exit{f['rc']}")
    else:
        out = be.get("outcome") or {}
        others = [g for g in row["gate_failures"] if g != "G19"]
        if out.get("error") or out.get("status") == "crashed":
            row.update(status="crashed", crash_cause=f"outcome error: {out.get('error')}")
        elif row["traceback_in"]:
            row.update(status="crashed",
                       crash_cause="traceback in " + ", ".join(row["traceback_in"]))
        elif be.get("seed") != r["seed"]:
            row.update(status="wrong_scene",
                       summary_mismatch=f"bridge_episode.json seed {be.get('seed')!r}")
        elif others:
            row.update(status="gate_failed")
        elif row["reward"] == 1.0:
            row.update(status=SUCCESS, success=True)
        else:
            row.update(status="failure")
    return row


CLASSIFY = {"boxels": classify_boxels, "bridge": classify_bridge}


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

def _append(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def preflight_problems(d: dict, env: dict) -> list[str]:
    """What stops a set before its first run (nothing is written then)."""
    p = []
    for name, a in d["arms"].items():
        if set(a["sha"]) == {"0"}:
            p.append(f"arm {name}: the template's placeholder sha")
        got = (env.get("arms") or {}).get(name) or {}
        if got.get("head") != a["sha"]:
            p.append(f"arm {name}: checkout HEAD {got.get('head')} is not {a['sha']}")
        if got.get("dirty"):
            p.append(f"arm {name}: checkout not clean (git status --porcelain not empty)")
    if "boxels" in d["worlds"]:
        st = d["statistics_file"]["boxels"]
        have = sha256_file(st["stored_copy"])
        if have != st["sha256"]:
            p.append(f"statistics stored copy {st['stored_copy']}: sha256 {have}, "
                     f"declared {st['sha256']}")
    return p


def run_set(set_dir, launcher=None, clock=time.time, sleep=time.sleep,
            out=print) -> int:
    set_dir = Path(set_dir)
    decl, dsha = read_declaration(set_dir / DECLARATION_NAME)
    launcher = launcher or GateLauncher(decl, set_dir)
    results = set_dir / RESULTS_NAME
    if results.exists():
        out(f"refused: {results} exists; a set runs once, a repeat is a new "
            "declaration (S-r)")
        return 2
    env0 = launcher.probe()
    problems = preflight_problems(decl, env0)
    if problems:
        out("refused before the first run:\n  " + "\n  ".join(problems))
        return 2
    runs = run_list(decl)
    base = {"set_id": decl["set_id"], "kind": decl["kind"], "declaration_sha256": dsha}
    _append(results, {**base, "event": "set_start", "t": clock(), "env": env0,
                      "runs_declared": len(runs)})
    stopped = None
    for i, r in enumerate(runs):
        if i:
            sleep(decl["machine"]["pause_s"])
        arm = decl["arms"][r["arm"]]
        ep = set_dir / "episodes" / episode_name(r)
        ident = {**base, **r, "role": arm["role"], "sha": arm["sha"],
                 "ep": f"episodes/{episode_name(r)}"}
        if ep.exists():
            _append(results, {**ident, "event": "start", "t": clock()})
            _append(results, {**ident, "event": "end", "t": clock(),
                              "status": "not_started",
                              "not_started": "episode folder exists", "success": False})
            stopped = r["pos"]
            break
        ep.mkdir(parents=True)
        _append(results, {**ident, "event": "start", "t": clock()})
        info = launcher.run_episode(r, ep) or {}
        res = CLASSIFY[r["world"]](decl, r, ep, info)
        _append(results, {**ident, **res, "event": "end", "t": clock()})
        out(f"[paired] {decl['set_id']} {r['pos']:3d}/{len(runs)} {r['world']} "
            f"seed {r['seed']} arm {r['arm']}: {res['status']}"
            + (f" ({res.get('exit_reason')})" if res.get("exit_reason") else ""))
        if res["status"] == "not_started":
            stopped = r["pos"]
            out(f"[paired] stopped at run {r['pos']}: {res.get('not_started')}; "
                "the set is not full, a repeat is a new declaration")
            break
    _append(results, {**base, "event": "set_end", "t": clock(),
                      "env": launcher.probe(), "stopped_at": stopped})
    return 4 if stopped else 0


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------

def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar (binomial, p = 1/2) on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(b, c) + 1))
    return float(min(Fraction(1), Fraction(2 * tail, 2 ** n)))


def load_rows(path: Path) -> tuple[list[dict], list[str]]:
    rows, problems = [], []
    if not path.exists():
        return rows, [f"{path.name} missing"]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            problems.append(f"{path.name} line {i}: not JSON")
    return rows, problems


def collate(decl: dict, dsha: str, rows: list[dict]) -> tuple[dict, list[str]]:
    """Per declared position the counted result (the first end row), and
    every reason the set is not full."""
    problems: list[str] = []
    runs = {r["pos"]: r for r in run_list(decl)}
    starts: dict[int, list] = {}
    ends: dict[int, list] = {}
    set_start = [r for r in rows if r.get("event") == "set_start"]
    set_end = [r for r in rows if r.get("event") == "set_end"]
    if len(set_start) != 1:
        problems.append(f"{len(set_start)} set_start rows, want 1")
    if len(set_end) != 1:
        problems.append(f"{len(set_end)} set_end rows, want 1")
    for r in rows:
        if r.get("declaration_sha256") != dsha:
            problems.append(f"a row ({r.get('event')} {r.get('pos')}) carries another "
                            "declaration's sha256: the declaration changed after the run")
            break
    for r in rows:
        if r.get("event") in ("start", "end"):
            (starts if r["event"] == "start" else ends).setdefault(r.get("pos"), []).append(r)
    for pos in sorted(set(starts) | set(ends), key=lambda x: (x is None, x)):
        if pos not in runs:
            problems.append(f"run {pos}: not in the declared list")
    results = {}
    for pos, want in runs.items():
        s, e = starts.get(pos, []), ends.get(pos, [])
        tag = f"run {pos} ({want['world']} seed {want['seed']} arm {want['arm']})"
        if not s and not e:
            problems.append(f"{tag}: missing (no row)")
            continue
        if len(s) > 1:
            problems.append(f"{tag}: {len(s)} start rows (doubled)")
        if len(e) > 1:
            problems.append(f"{tag}: {len(e)} end rows (doubled); the first counts")
        if not s:
            problems.append(f"{tag}: an end row without a start row")
        first = e[0] if e else {**s[0], "status": "vanished", "success": False}
        arm = decl["arms"][want["arm"]]
        for k, v in (("world", want["world"]), ("seed", want["seed"]),
                     ("arm", want["arm"]), ("sha", arm["sha"])):
            if first.get(k) != v:
                problems.append(f"{tag}: row {k} {first.get(k)!r}, declared {v!r}")
        if first.get("status") in NOT_FULL_STATUSES:
            problems.append(f"{tag}: {first['status']}"
                            + (f" ({first.get('not_started')})" if first.get("not_started") else "")
                            + (f" ({first.get('summary_mismatch')})" if first.get("summary_mismatch") else ""))
        if first.get("status") not in ("not_started", "vanished"):
            if want["world"] == "boxels":
                if first.get("stats_sha256") != decl["statistics_file"]["boxels"]["sha256"]:
                    problems.append(f"{tag}: started from statistics sha256 "
                                    f"{first.get('stats_sha256')}, not the declared copy")
            elif first.get("stats_sha256") is not None:
                problems.append(f"{tag}: a bridge row with a statistics sha256")
        results[pos] = {**first, "start_t": (s[0].get("t") if s else None)}
    if set_start and set_end:
        for name, a in decl["arms"].items():
            for when, row in (("start", set_start[0]), ("end", set_end[0])):
                got = ((row.get("env") or {}).get("arms") or {}).get(name) or {}
                if got.get("head") != a["sha"] or got.get("dirty"):
                    problems.append(f"arm {name} at the set's {when}: HEAD "
                                    f"{got.get('head')}, dirty {got.get('dirty')}")
        e0, e1 = set_start[0].get("env") or {}, set_end[0].get("env") or {}
        if e0.get("library_commit") != e1.get("library_commit"):
            problems.append("the pddlstream library commit changed during the set")
        if (e0.get("venv") or {}).get("pip_freeze_sha256") != (e1.get("venv") or {}).get("pip_freeze_sha256"):
            problems.append("the venv's pip freeze changed during the set")
    return results, problems


def _arm_facts(rows: list[dict]) -> dict:
    return {"statuses": Counter(r.get("status") for r in rows),
            "exit_reasons": Counter(r.get("exit_reason") for r in rows
                                    if r.get("exit_reason") is not None),
            "gates": Counter(g for r in rows for g in (r.get("gate_failures") or [])
                             if g != "G19"),
            "crashes": [r for r in rows if r.get("status") == "crashed"],
            "successes": sum(1 for r in rows if r.get("status") == SUCCESS)}


def world_table(decl: dict, results: dict, world: str) -> dict:
    """Pairs, flips and the per-arm facts of one world."""
    by = {}
    for pos, r in results.items():
        if r.get("world") == world:
            by.setdefault(r.get("seed"), {})[r.get("arm")] = r
    pairs, problems, flagged = [], [], []
    gap_max = decl["pair_gap_max_s"]
    for seed in decl["worlds"][world]["seeds"]:
        two = by.get(seed, {})
        a, b = two.get("A"), two.get("B")
        old_ok = bool(a and a.get("status") == SUCCESS)
        new_ok = bool(b and b.get("status") == SUCCESS)
        pairs.append({"seed": seed, "A": a and a.get("status"), "B": b and b.get("status"),
                      "old_success": old_ok, "new_success": new_ok,
                      "A_exit_reason": a and a.get("exit_reason"),
                      "B_exit_reason": b and b.get("exit_reason"),
                      "A_plan_count": a and a.get("plan_count"),
                      "B_plan_count": b and b.get("plan_count")})
        if a and b:
            if world == "bridge" and a.get("scene_file") and b.get("scene_file") \
                    and a["scene_file"] != b["scene_file"]:
                problems.append(f"bridge seed {seed}: the arms saw different scene "
                                f"files ({a['scene_file']} / {b['scene_file']})")
            ta, tb = a.get("start_t"), b.get("start_t")
            if ta is not None and tb is not None and abs(ta - tb) > gap_max:
                flagged.append({"seed": seed, "gap_s": round(abs(ta - tb), 1)})
    b_ = sum(1 for p in pairs if p["old_success"] and not p["new_success"])
    c_ = sum(1 for p in pairs if not p["old_success"] and p["new_success"])
    rows_a = [r for r in results.values() if r.get("world") == world and r.get("arm") == "A"]
    rows_b = [r for r in results.values() if r.get("world") == world and r.get("arm") == "B"]
    return {"pairs": pairs, "old_only_success": b_, "new_only_success": c_,
            "net_flips": b_ - c_, "mcnemar_p": mcnemar_exact(b_, c_),
            "A": _arm_facts(rows_a), "B": _arm_facts(rows_b),
            "problems": problems, "flagged_pairs": flagged}


def _kinds(facts: dict) -> set:
    return {s for s in facts["statuses"] if s not in ITEM2_EXCLUDED}


def analyse(set_dir, crash_reviews: dict | None = None) -> dict:
    set_dir = Path(set_dir)
    decl, dsha = read_declaration(set_dir / DECLARATION_NAME)
    rows, problems = load_rows(set_dir / RESULTS_NAME)
    results, p2 = collate(decl, dsha, rows)
    problems += p2
    reviews = {str(k): v for k, v in (crash_reviews or {}).items()}
    noise = None
    if decl["kind"] in ("A", "B"):
        nd = Path(decl["noise_set_dir"])
        if not nd.is_absolute():
            nd = (set_dir / nd).resolve()
        try:
            noise = analyse(nd)
        except (OSError, DeclarationError) as e:
            problems.append(f"noise set {nd}: {e}")
        else:
            if noise["kind"] != "N":
                problems.append(f"noise set {nd}: kind {noise['kind']}, not N")
            if not noise["full"]:
                problems.append(f"noise set {nd}: not full")
            for w in decl["worlds"]:
                if noise["seeds"].get(w) != decl["worlds"][w]["seeds"]:
                    problems.append(f"noise set: the {w} seeds differ from this set's")
    worlds = {}
    fail, pending = [], []
    for w in decl["world_order"]:
        t = world_table(decl, results, w)
        problems += t["problems"]
        old, new = t["A"], t["B"]
        items = {}
        if decl["kind"] == "N":
            t["n_count_for_item3"] = abs(t["net_flips"])
            t["tell_R"] = abs(t["net_flips"]) >= 3
        elif decl["kind"] == "S":
            crashes = old["crashes"] + new["crashes"]
            new_kinds = _kinds(new) - _kinds(old)
            new_exits = set(new["exit_reasons"]) - set(old["exit_reasons"])
            items["no_crash"] = {"fails": bool(crashes),
                                 "runs": [c.get("pos") for c in crashes]}
            items["new_kind_or_exit_reason"] = {
                "fails": bool(new_kinds or new_exits),
                "kinds": sorted(new_kinds), "exit_reasons": sorted(new_exits)}
        else:
            nw = (noise or {}).get("worlds", {}).get(w)
            seen_kinds = _kinds(old) | (set(nw["kinds_A"]) | set(nw["kinds_B"]) if nw else set())
            seen_exits = set(old["exit_reasons"]) | (set(nw["exit_reasons_A"]) | set(nw["exit_reasons_B"]) if nw else set())
            seen_gates = set(old["gates"]) | (set(nw["gates_A"]) | set(nw["gates_B"]) if nw else set())
            crash_items = []
            for c in new["crashes"]:
                verdict = reviews.get(str(c.get("pos")))
                crash_items.append({"run": c.get("pos"), "seed": c.get("seed"),
                                    "cause": c.get("crash_cause"), "review": verdict})
            items["1_crash_on_migration"] = {
                "fails": any(ci["review"] == "migration" for ci in crash_items),
                "pending": [ci["run"] for ci in crash_items
                            if ci["review"] not in ("migration", "not_migration")],
                "crashes": crash_items}
            nk = _kinds(new) - seen_kinds
            ne = set(new["exit_reasons"]) - seen_exits
            ng = set(new["gates"]) - seen_gates
            items["2_new_exit_reason_kind_or_gate"] = {
                "fails": bool(nk or ne or ng), "kinds": sorted(nk),
                "exit_reasons": sorted(ne), "gates": sorted(ng)}
            n_count = nw["n_count_for_item3"] if nw else None
            threshold = (n_count + 1) if (n_count is not None and n_count >= 3) else 3
            items["3_net_one_way_flips"] = {"fails": t["net_flips"] >= threshold,
                                            "net": t["net_flips"], "threshold": threshold,
                                            "noise_count": n_count}
            items["4_mcnemar"] = {"fails": t["mcnemar_p"] < 0.05, "p": t["mcnemar_p"]}
            pending += items["1_crash_on_migration"]["pending"]
        for name, it in items.items():
            if it["fails"]:
                fail.append(f"{w}: {name}")
        worlds[w] = {
            "pairs": t["pairs"], "old_only_success": t["old_only_success"],
            "new_only_success": t["new_only_success"], "net_flips": t["net_flips"],
            "mcnemar_p": t["mcnemar_p"], "items": items,
            "flagged_pairs": t["flagged_pairs"],
            "successes_A": old["successes"], "successes_B": new["successes"],
            "statuses_A": dict(old["statuses"]), "statuses_B": dict(new["statuses"]),
            "exit_reasons_A": dict(old["exit_reasons"]), "exit_reasons_B": dict(new["exit_reasons"]),
            "gates_A": dict(old["gates"]), "gates_B": dict(new["gates"]),
            "kinds_A": sorted(_kinds(old)), "kinds_B": sorted(_kinds(new)),
            "crashes_A": [c.get("pos") for c in old["crashes"]],
            "crashes_B": [c.get("pos") for c in new["crashes"]],
            **({"n_count_for_item3": t["n_count_for_item3"], "tell_R": t["tell_R"]}
               if decl["kind"] == "N" else {})}
    full = not problems
    if not full:
        verdict = "NOT FULL"
    elif decl["kind"] == "N":
        verdict = "RECORDED"
    elif fail:
        verdict = "FAIL"
    elif pending:
        verdict = "PENDING REVIEW"
    else:
        verdict = "PASS"
    return {"set_id": decl["set_id"], "kind": decl["kind"], "declaration_sha256": dsha,
            "full": full, "not_full": problems, "verdict": verdict, "fails": fail,
            "pending_reviews": pending, "worlds": worlds,
            "seeds": {w: decl["worlds"][w]["seeds"] for w in decl["worlds"]},
            "runs_declared": len(run_list(decl)),
            "runs_with_result": len(results), "validity_notes": list(VALIDITY_NOTES)}


EXIT_OF_VERDICT = {"PASS": 0, "RECORDED": 0, "FAIL": 1, "PENDING REVIEW": 3, "NOT FULL": 4}


def format_report(a: dict) -> str:
    L = [f"set {a['set_id']} (kind {a['kind']}), declaration sha256 {a['declaration_sha256']}",
         f"runs declared {a['runs_declared']}, with a result {a['runs_with_result']}"]
    L.append("full: yes" if a["full"] else
             f"full: NO ({len(a['not_full'])} problems)\n  " + "\n  ".join(a["not_full"]))
    for w, t in a["worlds"].items():
        L.append(f"\n[{w}] successes A {t['successes_A']}, B {t['successes_B']} of "
                 f"{len(t['pairs'])} pairs; A only {t['old_only_success']}, B only "
                 f"{t['new_only_success']}, net one-way flips {t['net_flips']}, exact "
                 f"McNemar p {t['mcnemar_p']:.4f}")
        L.append("  seed  A                   B                   A exit / B exit   plans A/B")
        for p in t["pairs"]:
            L.append(f"  {p['seed']:>4}  {str(p['A']):<19} {str(p['B']):<19} "
                     f"{p['A_exit_reason']} / {p['B_exit_reason']}   "
                     f"{p['A_plan_count']}/{p['B_plan_count']}")
        L.append(f"  statuses A {t['statuses_A']}  B {t['statuses_B']}")
        L.append(f"  exit reasons A {t['exit_reasons_A']}  B {t['exit_reasons_B']}")
        if w == "bridge":
            L.append(f"  failed gates without G19: A {t['gates_A']}  B {t['gates_B']}")
        L.append(f"  crashes: A runs {t['crashes_A']}, B runs {t['crashes_B']}")
        if t["flagged_pairs"]:
            L.append(f"  pairs far apart in time: {t['flagged_pairs']}")
        if "n_count_for_item3" in t:
            L.append(f"  noise count for item 3: {t['n_count_for_item3']}"
                     + ("  (3 or more: R is told before set A runs)" if t["tell_R"] else ""))
        for name, it in t["items"].items():
            L.append(f"  {name}: {'FAILS' if it['fails'] else 'holds'} "
                     + json.dumps({k: v for k, v in it.items() if k != 'fails'}, sort_keys=True))
    L.append("\nvalidity notes: " + "; ".join(a["validity_notes"]))
    L.append("plan counts are information only (PLAN 24.4 (c)); times are not compared")
    if a["fails"]:
        L.append("fails: " + "; ".join(a["fails"]))
    if a["pending_reviews"]:
        L.append(f"crashes of the new arm waiting for their review pair: runs {a['pending_reviews']}")
    L.append(f"verdict: {a['verdict']}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "scripts", "run", "analyse"):
        s = sub.add_parser(name)
        s.add_argument("--set-dir", required=True)
        if name == "scripts":
            s.add_argument("--out", required=True)
        if name == "analyse":
            s.add_argument("--crash-reviews", help="JSON: run position -> "
                           "'migration' or 'not_migration' (the review pair's verdict)")
            s.add_argument("--json", help="write the analysis as JSON here")
    a = ap.parse_args(argv)
    set_dir = Path(a.set_dir)
    try:
        if a.cmd == "plan":
            d, sha = read_declaration(set_dir / DECLARATION_NAME)
            runs = run_list(d)
            print(f"declaration ok, sha256 {sha}, {len(runs)} runs")
            print("| pos | pair | world | seed | arm | sha |\n|---|---|---|---|---|---|")
            for r in runs:
                print(f"| {r['pos']} | {r['pair']} | {r['world']} | {r['seed']} | "
                      f"{r['arm']} | {d['arms'][r['arm']]['sha'][:12]} |")
            print(json.dumps(runs))
            return 0
        if a.cmd == "scripts":
            d, _ = read_declaration(set_dir / DECLARATION_NAME)
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            for r in run_list(d):
                ep = set_dir / "episodes" / episode_name(r)
                (out / f"{episode_name(r)}.sh").write_bytes(
                    episode_script(d, r, ep).encode("utf-8"))
            print(f"{len(run_list(d))} scripts in {out}; nothing launched")
            return 0
        if a.cmd == "run":
            return run_set(set_dir)
        reviews = (json.loads(Path(a.crash_reviews).read_text(encoding="utf-8"))
                   if a.crash_reviews else None)
        res = analyse(set_dir, reviews)
        print(format_report(res))
        if a.json:
            Path(a.json).write_text(json.dumps(res, indent=1, sort_keys=True, default=str),
                                    encoding="utf-8")
        return EXIT_OF_VERDICT[res["verdict"]]
    except DeclarationError as e:
        print(f"declaration error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
