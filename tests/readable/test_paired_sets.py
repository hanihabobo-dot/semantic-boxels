"""Tests of tools/readable/paired_sets.py (Phase 0 of the readable migration).

No pybullet, no pipeline import, no real episode: a fake launcher writes the
files an episode script would leave (launch.txt, stdout, stderr, the run
directories, bridge_episode.json), and the runner and the analysis read
them. The planted cases of PLAN_REVIEW S-o each end in their status and,
where they make the set not full, in the "not full" list: an exception
before the summary, one after it, a killed process, no record file, a
pre-flight rejection, a missing row, a doubled row, a wrong scene. On
WSL/Linux the generated bash scripts are also run for real with a fake
python and a private lock file (never the pipeline lock); on Windows no
bash is ever spawned.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "readable" / "paired_sets.py"
TEMPLATE = ROOT / "tools" / "readable" / "DECLARATION_TEMPLATE.md"
sys.path.insert(0, str(TOOL.parent))
import paired_sets as ps  # noqa: E402

SHA_OLD = "a0948fe" + "1" * 33
SHA_NEW = "b" * 40


# ---------------------------------------------------------------------------
# Fixtures: a declaration in a temp folder, and a fake launcher
# ---------------------------------------------------------------------------

def make_decl(tmp: Path, kind="A", boxels_seeds=(0, 1, 2, 3), bridge_seeds=(0, 1),
              noise_dir=None, same_sha=None) -> dict:
    stored = tmp / "stored" / "boxel-streams.pkl"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"stats-copy")
    for arm in ("armA", "armB"):
        (tmp / arm / "logs").mkdir(parents=True, exist_ok=True)
    same = kind == "N" if same_sha is None else same_sha
    worlds = {}
    order = []
    if boxels_seeds:
        worlds["boxels"] = {"seeds": list(boxels_seeds), "cap_s": 300,
                            "cell": {"scene": "random-pairs", "goal": "holding",
                                     "n_occluders": 2, "baseline": "semantic",
                                     "unit_costs": False}}
        order.append("boxels")
    if bridge_seeds:
        worlds["bridge"] = {"seeds": list(bridge_seeds), "cap_s": 1200}
        order.append("bridge")
    stats = {"boxels": {"stored_copy": str(stored),
                        "sha256": hashlib.sha256(b"stats-copy").hexdigest()},
             "bridge": {"start": "fresh", "sha256": None}}
    return {
        "declaration_version": 1, "set_id": f"T{kind}", "kind": kind,
        "arms": {"A": {"role": "old", "sha": SHA_OLD, "checkout": str(tmp / "armA")},
                 "B": {"role": "new", "sha": SHA_OLD if same else SHA_NEW,
                       "checkout": str(tmp / ("armA" if same else "armB"))}},
        "worlds": worlds, "world_order": order, "pairing": "by_seed", "order": "ABBA",
        "switches": [],
        "machine": {"python": "/root/armO-venvA/bin/python", "pythonhashseed": "0",
                    "lock": "/root/sb_pipeline.lock", "gate_script": "C:\\gate_run.ps1",
                    "gate_max_minutes": 180, "mem_available_min_gb": 4, "pause_s": 60,
                    "wsl_distro": "Ubuntu", "tampura_work": "/root/tampura-work",
                    "pddlstream_lib": "/mnt/c/Users/x/git/pddlstream_lib"},
        "statistics_file": stats,
        "noise_set_dir": (str(noise_dir) if noise_dir else None) if kind in ("A", "B") else None,
        "pair_gap_max_s": 3600, "runs": None,
    }


def write_decl(set_dir: Path, decl: dict) -> Path:
    set_dir.mkdir(parents=True, exist_ok=True)
    p = set_dir / ps.DECLARATION_NAME
    p.write_text("# DECLARATION\n\nprose\n\n```json paired-set\n"
                 + json.dumps(decl, indent=1) + "\n```\n", encoding="utf-8")
    return p


def good_env(decl):
    return {"arms": {k: {"head": a["sha"], "dirty": False, "status": ""}
                     for k, a in decl["arms"].items()},
            "library_commit": "c" * 40, "venv": {"pip_freeze_sha256": "d" * 64}}


def _launch(ep: Path, rc, wall=10.0, stats=None, start=100.0):
    lines = ["lock_taken=99.0", "mem_available_kb=9000000", "load_start=0.1 0.1 0.1"]
    if stats is not None:
        lines.append(f"stats_sha256_before={stats}")
    lines.append(f"launched_at={start}")
    if rc is not None:
        lines += [f"ended_at={start + wall}", f"rc={rc}"]
    (ep / "launch.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def boxels_ep(fl, r, ep, *, rc=0, success=True, exit_reason=None, make_dir=True,
              summary=True, run_config=None, stdout="", stderr="", log_text="",
              wall=10.0, stats="declared"):
    d = fl.d
    checkout = Path(ps.to_local(d["arms"][r["arm"]]["checkout"]))
    logs = checkout / "logs"
    before = sorted(str(p) for p in logs.glob("run_*"))
    (ep / "runs_before.txt").write_text("\n".join(before) + "\n", encoding="utf-8")
    after = list(before)
    if make_dir:
        rd = logs / f"run_{len(before):04d}"
        rd.mkdir(parents=True)
        cell = d["worlds"]["boxels"]["cell"]
        rc_cfg = run_config or {"scene": cell["scene"], "seed": r["seed"],
                                "goal": cell["goal"], "baseline": cell["baseline"],
                                "unit_costs": cell["unit_costs"]}
        if summary:
            (rd / "timing_summary.json").write_text(json.dumps(
                {"run_config": rc_cfg, "success": success, "exit_reason":
                 None if success else (exit_reason or "pick_giveup"), "plan_count": 2,
                 "total_planning_time_s": 3.5}), encoding="utf-8")
        (rd / f"{rd.name}.log").write_text(log_text or "run log\n", encoding="utf-8")
        after.append(str(rd))
    (ep / "runs_after.txt").write_text("\n".join(sorted(after)) + "\n", encoding="utf-8")
    (ep / "stdout.txt").write_text(stdout, encoding="utf-8")
    (ep / "stderr.txt").write_text(stderr, encoding="utf-8")
    sha = d["statistics_file"]["boxels"]["sha256"] if stats == "declared" else stats
    _launch(ep, rc, wall=wall, stats=sha)


def bridge_ep(fl, r, ep, *, rc=0, reward=1.0, gates=None, error=None, record=True,
              seed=None, scene="find_dice/problems/p_a.json", stdout="", stderr="",
              exit_reason=None, wall=20.0, status=None):
    save = ep / "save"
    rd = save / "ours" / "run_0001"
    rd.mkdir(parents=True)
    (rd / "timing_summary.json").write_text(json.dumps(
        {"exit_reason": exit_reason, "plan_count": 3, "total_planning_time_s": 9.0}),
        encoding="utf-8")
    (rd / "run_0001.log").write_text("log\n", encoding="utf-8")
    if record:
        gates = dict(gates or {})
        st = status or ("crashed" if error else "gate_failed" if gates
                        else "success" if reward == 1.0 else "failure")
        (save / "bridge_episode.json").write_text(json.dumps({
            "seed": r["seed"] if seed is None else seed, "scene_file": scene,
            "rewards": [0.0, reward], "run_dir": ps.to_wsl(rd) if os.name == "nt" else str(rd),
            "outcome": {"status": st, "success": st == "success", "reward": reward,
                        "error": error, "gate_failures": gates}}), encoding="utf-8")
    (ep / "stdout.txt").write_text(stdout, encoding="utf-8")
    (ep / "stderr.txt").write_text(stderr, encoding="utf-8")
    _launch(ep, rc, wall=wall)


def not_started(fl, r, ep, reason="mem_available_under_4_gb"):
    (ep / "launch.txt").write_text("lock_taken=1.0\nmem_available_kb=100\n", encoding="utf-8")
    (ep / "not_started.txt").write_text(f"reason={reason}\n", encoding="utf-8")


class FakeLauncher:
    """Writes what an episode would leave; checks the start row came first."""

    def __init__(self, decl, set_dir, plan=None, env=None, env_end=None):
        self.d = decl
        self.results = Path(set_dir) / ps.RESULTS_NAME
        self.plan = plan or {}
        self.env = env or good_env(decl)
        self.env_end = env_end
        self.probes = 0
        self.calls = []
        self.counter = 0

    def probe(self):
        self.probes += 1
        if self.probes > 1 and self.env_end is not None:
            return copy.deepcopy(self.env_end)
        return copy.deepcopy(self.env)

    def run_episode(self, r, ep):
        last = json.loads(self.results.read_text(encoding="utf-8").splitlines()[-1])
        assert last["event"] == "start" and last["pos"] == r["pos"], "start row first"
        self.calls.append(r["pos"])
        spec = self.plan.get((r["world"], r["seed"], r["arm"]))
        if callable(spec):
            return spec(self, r, ep)
        kwargs = dict(spec or {})
        (boxels_ep if r["world"] == "boxels" else bridge_ep)(self, r, ep, **kwargs)
        return {"gate_rc": 0}


def run_fake(tmp, decl, plan=None, env=None, env_end=None, name="set"):
    set_dir = tmp / name
    write_decl(set_dir, decl)
    fl = FakeLauncher(decl, set_dir, plan, env, env_end)
    lines = []
    rc = ps.run_set(set_dir, launcher=fl, sleep=lambda s: None, out=lines.append)
    return set_dir, fl, rc, lines


def end_rows(set_dir):
    rows = [json.loads(x) for x in (set_dir / ps.RESULTS_NAME).read_text().splitlines()]
    return {r["pos"]: r for r in rows if r.get("event") == "end"}


def noise_set(tmp, plan=None, seeds=(0, 1, 2, 3), bridge=(0, 1)):
    d = make_decl(tmp / "n_src", kind="N", boxels_seeds=seeds, bridge_seeds=bridge)
    set_dir, _, rc, _ = run_fake(tmp, d, plan, name="setN")
    assert rc == 0
    return set_dir


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------

def test_template_parses_and_validates():
    d, sha = ps.read_declaration(TEMPLATE)
    assert d["kind"] == "N" and len(sha) == 64
    runs = ps.run_list(d)
    assert len(runs) == 80                       # PLAN 24.4 (a): 20 + 20 pairs
    assert d["machine"]["python"] == "/root/armO-venvA/bin/python"
    assert d["statistics_file"]["bridge"]["sha256"] is None


def test_abba_order_across_worlds(tmp_path):
    d = make_decl(tmp_path, boxels_seeds=(0, 1, 2), bridge_seeds=(5, 7))
    runs = ps.run_list(d)
    assert [r["arm"] for r in runs] == list("ABBAABBAAB")
    assert [r["pos"] for r in runs] == list(range(1, 11))
    assert [(r["world"], r["seed"]) for r in runs[6:8]] == [("bridge", 5)] * 2
    assert runs[6]["arm"] == "B" and runs[8]["arm"] == "A"    # pair 3 is B A, pair 4 A B
    assert [r["pair"] for r in runs] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_crlf_declaration_reads_like_lf(tmp_path):
    p = write_decl(tmp_path / "s", make_decl(tmp_path, kind="N"))
    lf = p.read_bytes().replace(b"\r\n", b"\n")
    p.write_bytes(lf.replace(b"\n", b"\r\n"))
    d_crlf, sha_crlf = ps.read_declaration(p)
    p.write_bytes(lf)
    d_lf, sha_lf = ps.read_declaration(p)
    assert d_crlf == d_lf and sha_crlf != sha_lf        # the sha is of the bytes


@pytest.mark.parametrize("change, needle", [
    (lambda d: d["arms"]["B"].update(sha=SHA_NEW), "kind N"),
    (lambda d: d.update(switches=["--m8"]), "switches"),
    (lambda d: d["statistics_file"]["boxels"].update(sha256="xyz"), "statistics_file.boxels"),
    (lambda d: d["statistics_file"]["bridge"].update(sha256="ab" * 32), "statistics_file.bridge"),
    (lambda d: d.update(order="AB"), "order"),
    (lambda d: d["worlds"]["boxels"].update(seeds=[0, 0]), "seeds"),
    (lambda d: d["worlds"]["bridge"].update(max_plan_time=100), "launcher defaults"),
    (lambda d: d["arms"]["A"].update(role="new"), "role"),
    (lambda d: d.update(runs=[{"pos": 1}]), "runs"),
    (lambda d: d["machine"].update(pythonhashseed="1"), "pythonhashseed"),
])
def test_declaration_rejects(tmp_path, change, needle):
    d = make_decl(tmp_path, kind="N")
    change(d)
    errors = ps.validate_declaration(d)
    assert any(needle in e for e in errors), errors


def test_declaration_kind_rules(tmp_path):
    d = make_decl(tmp_path, kind="A", same_sha=True)
    assert any("different shas" in e for e in ps.validate_declaration(d))
    d = make_decl(tmp_path, kind="A")
    d["noise_set_dir"] = None
    assert any("noise_set_dir" in e for e in ps.validate_declaration(d))
    d = make_decl(tmp_path, kind="S")
    assert ps.validate_declaration(d) == []
    d["runs"] = ps.run_list(d)
    assert ps.validate_declaration(d) == []


def test_declaration_needs_exactly_one_block(tmp_path):
    p = write_decl(tmp_path / "s", make_decl(tmp_path, kind="N"))
    text = p.read_text(encoding="utf-8")
    p.write_text(text + "\n" + text[text.index("```json"):], encoding="utf-8")
    with pytest.raises(ps.DeclarationError, match="2 blocks"):
        ps.read_declaration(p)


# ---------------------------------------------------------------------------
# The episode commands
# ---------------------------------------------------------------------------

def test_boxels_argv_is_eval_runners():
    sys.path.insert(0, str(ROOT))
    try:
        from evaluation import eval_runner  # no pybullet at import (json, os, world_counts)
    finally:
        sys.path.remove(str(ROOT))
    cell = {"scene": "random-pairs", "seed": 7, "goal": "holding", "baseline": "semantic",
            "unit_costs": False, "n_occluders": 2, "n_targets": 0, "n_hidden": 0}
    want = eval_runner.cell_to_argv(cell, [])[1:]
    d_cell = {k: cell[k] for k in ("scene", "goal", "baseline", "n_occluders", "unit_costs")}
    assert ps.boxels_argv(d_cell, 7) == want
    cell["unit_costs"] = True
    assert ps.boxels_argv({**d_cell, "unit_costs": True}, 7) == eval_runner.cell_to_argv(cell, [])[1:]


def test_bridge_argv_is_run_ps1_headless():
    run_ps1 = (ROOT / "run.ps1").read_text(encoding="utf-8")
    assert "--global-seed $seedNo --vis $vis --save-dir $save$g19" in run_ps1
    assert "$g19 = if ($Headless) { ' --allow-g19-mismatch 1' }" in run_ps1
    argv = ps.bridge_argv("/c", 5, "/s")
    assert argv == ["/c/tampura_bridge/run_bridge_on_finddice.py", "--global-seed", "5",
                    "--vis", "0", "--save-dir", "/s", "--allow-g19-mismatch", "1"]


def test_episode_scripts(tmp_path):
    d = make_decl(tmp_path, kind="A")
    runs = ps.run_list(d)
    ep = Path("C:\\x\\set\\episodes\\001")
    box = ps.episode_script(d, runs[0], ep)
    assert "\r" not in box and box.startswith("#!/bin/bash\n")
    assert "EP=/mnt/c/x/set/episodes/001" in box
    assert "flock 9" in box and "exec 9>>\"$L\"" in box
    assert box.index("flock 9") < box.index("cp -f") < box.index("timeout -k 30 300")
    assert d["statistics_file"]["boxels"]["sha256"] in box
    assert "test_full_pipeline.py --no-gui --scene random-pairs --seed 0 --goal holding " \
           "--baseline semantic --log-level quiet --no-telemetry --n-occluders 2 " in box
    assert "export PYTHONHASHSEED=0" in box and "unset " in box
    assert "-lt 4194304" in box                          # 4 GB in kB, rule 16
    br = ps.episode_script(d, [r for r in runs if r["world"] == "bridge"][0], ep)
    assert "cd /root/tampura-work/tampura_environments" in br
    assert "--vis 0 --save-dir /mnt/c/x/set/episodes/001/save --allow-g19-mismatch 1" in br
    assert "PYTHONPATH=" in br and "/mnt/c/Users/x/git/pddlstream_lib" in br
    assert "statistics" not in br                        # no restore on the bridge
    gl = ps.GateLauncher(d, tmp_path)
    cmd = gl.gate_command(Path("C:\\x\\ep.sh"), "paired-TA-001")
    assert cmd[:4] == ["pwsh", "-NoProfile", "-File", "C:\\gate_run.ps1"]
    assert cmd[4:] == ["-Script", "/mnt/c/x/ep.sh", "-Label", "paired-TA-001",
                       "-MaxMinutes", "180"]


def test_scripts_command_launches_nothing(tmp_path):
    d = make_decl(tmp_path, kind="N")
    set_dir = tmp_path / "s"
    write_decl(set_dir, d)
    out = tmp_path / "scripts"
    assert ps.main(["scripts", "--set-dir", str(set_dir), "--out", str(out)]) == 0
    assert len(list(out.glob("*.sh"))) == len(ps.run_list(d))
    assert not (set_dir / ps.RESULTS_NAME).exists()


def test_path_mapping():
    assert ps.to_wsl("C:\\Users\\a\\b") == "/mnt/c/Users/a/b"
    assert ps.to_wsl("/root/x") == "/root/x"
    if os.name == "nt":
        assert ps.to_local("/mnt/c/Users/a") == "C:\\Users\\a"
        assert ps.to_local("/root/x") == "/root/x"
    else:
        assert ps.to_local("C:\\Users\\a") == "/mnt/c/Users/a"


# ---------------------------------------------------------------------------
# The runner with a fake launcher
# ---------------------------------------------------------------------------

def test_clean_run_rows_and_order(tmp_path):
    d = make_decl(tmp_path, kind="N")
    set_dir, fl, rc, lines = run_fake(tmp_path, d)
    assert rc == 0
    assert fl.calls == list(range(1, len(ps.run_list(d)) + 1))
    rows = [json.loads(x) for x in (set_dir / ps.RESULTS_NAME).read_text().splitlines()]
    assert rows[0]["event"] == "set_start" and rows[-1]["event"] == "set_end"
    assert [r["event"] for r in rows[1:-1]] == ["start", "end"] * len(fl.calls)
    ends = end_rows(set_dir)
    assert all(e["status"] == "success" for e in ends.values())
    box = [e for e in ends.values() if e["world"] == "boxels"]
    assert all(e["stats_sha256"] == d["statistics_file"]["boxels"]["sha256"] for e in box)
    assert all(e["stats_sha256"] is None for e in ends.values() if e["world"] == "bridge")
    assert all((set_dir / e["ep"] / "timing_summary.json").is_file() for e in box)
    a = ps.analyse(set_dir)
    assert a["full"] and a["verdict"] == "RECORDED"


def test_runner_refuses_second_run_and_bad_start(tmp_path):
    d = make_decl(tmp_path, kind="N")
    set_dir, _, rc, _ = run_fake(tmp_path, d)
    assert rc == 0
    fl = FakeLauncher(d, set_dir)
    out = []
    assert ps.run_set(set_dir, launcher=fl, sleep=lambda s: None, out=out.append) == 2
    assert "a set runs once" in out[0]
    # a dirty checkout, a wrong HEAD and a stored copy that is not the declared one
    d2 = make_decl(tmp_path / "b", kind="N")
    Path(d2["statistics_file"]["boxels"]["stored_copy"]).write_bytes(b"changed")
    env = good_env(d2)
    env["arms"]["A"]["dirty"] = True
    env["arms"]["B"]["head"] = "e" * 40
    s2, fl2, rc2, out2 = run_fake(tmp_path, d2, env=env, name="set2")
    assert rc2 == 2 and fl2.calls == [] and not (s2 / ps.RESULTS_NAME).exists()
    text = out2[0]
    assert "not clean" in text and "is not" in text and "stored copy" in text
    d3 = make_decl(tmp_path / "c", kind="N")
    d3["arms"]["A"]["sha"] = d3["arms"]["B"]["sha"] = "0" * 40
    _, fl3, rc3, out3 = run_fake(tmp_path, d3, name="set3")
    assert rc3 == 2 and "placeholder" in out3[0]


# B1 (REVIEW_PHASE0): the stderr and stdout of a real pre-flight rejection,
# seed 1 of random-pairs with 2 occluders under the runner's argv
# (--log-level quiet, rc 1, no run directory), captured on the checkpoint
# code 2026-11-19. test_full_pipeline.py:3335-3337 prints the line and
# re-raises; without a Console excepthook the interpreter writes the
# traceback.
PREFLIGHT_MESSAGE = ("Could not place 2 hidden targets with 2 occluders at seed=1. "
                     "Try --n-occluders higher, --n-hidden lower, or a different --seed.")
PREFLIGHT_LINE = f"[pre-flight] seed 1 rejected: {PREFLIGHT_MESSAGE}\n"
REAL_PREFLIGHT_STDERR = (
    "pybullet build time: Jan 29 2025 23:17:20\n"
    + PREFLIGHT_LINE
    + "Traceback (most recent call last):\n"
    '  File "/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-readable/test_full_pipeline.py", '
    "line 3277, in <module>\n"
    "    probe_env = BoxelTestEnv(gui=False, scene_config=scene_cfg)\n"
    "                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n"
    '  File "/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-readable/boxel_env.py", '
    "line 611, in __init__\n"
    "    self._setup_scene()\n"
    '  File "/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-readable/boxel_env.py", '
    "line 998, in _setup_scene\n"
    "    self._create_targets()\n"
    '  File "/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-readable/boxel_env.py", '
    "line 1546, in _create_targets\n"
    "    raise RuntimeError(\n"
    f"RuntimeError: {PREFLIGHT_MESSAGE}\n")
REAL_PREFLIGHT_STDOUT = "  solver_iters: numSolverIterations 200 on our world (client 0)\n\n"
UNRELATED_TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/mnt/c/x/test_full_pipeline.py", line 3340, in <module>\n'
    "    logger = RunLogger(verbosity=args.log_level)\n"
    "KeyError: 'log_dir'\n")
# The line, the re-raised traceback, then a second, unrelated one.
PREFLIGHT_THEN_OTHER_TRACEBACK = REAL_PREFLIGHT_STDERR + UNRELATED_TRACEBACK


@pytest.mark.parametrize("plan, status, extra", [
    ({"rc": 1, "make_dir": False, "stderr": "Traceback (most recent call last):\n  x\nValueError\n"},
     "crashed", "no timing_summary.json"),                        # exception before the summary
    ({"rc": 1, "success": False, "stderr": "Traceback (most recent call last):\nKeyError\n"},
     "crashed", "traceback in stderr.txt"),                       # exception after the summary
    ({"rc": 1, "success": False, "log_text": "Traceback (most recent call last):\n"},
     "crashed", "traceback in run_"),                             # only the run log has it
    ({"rc": 124, "make_dir": False, "wall": 300.2}, "timeout", None),   # killed at the cap
    ({"rc": 137, "make_dir": False, "wall": 12.0}, "crashed", "crash_exit137"),  # killed early
    ({"rc": 0, "summary": False}, "crashed", "no timing_summary.json"),    # no record file
    ({"rc": 2, "make_dir": False}, "crashed", "crash_exit2"),
    ({"rc": 1, "make_dir": False, "stderr": "[pre-flight] seed 1 rejected: no scene\n"},
     "preflight_rejected", None),
    ({"rc": 1, "make_dir": False, "stderr": REAL_PREFLIGHT_STDERR,
      "stdout": REAL_PREFLIGHT_STDOUT},
     "preflight_rejected", None),                                 # B1: the real stderr
    ({"rc": 1, "make_dir": False, "stderr": PREFLIGHT_THEN_OTHER_TRACEBACK},
     "crashed", "no timing_summary.json"),                        # B1: another traceback
    ({"rc": 1, "make_dir": False, "stderr": PREFLIGHT_LINE + UNRELATED_TRACEBACK},
     "crashed", "no timing_summary.json"),                        # B1: line, other message
    ({"rc": 1, "make_dir": False, "stderr": UNRELATED_TRACEBACK + REAL_PREFLIGHT_STDERR},
     "crashed", "no timing_summary.json"),                        # B1: one before the line
    ({"rc": 1, "make_dir": False, "stderr": REAL_PREFLIGHT_STDERR,
      "stdout": "Traceback (most recent call last):\n  x\nValueError: y\n"},
     "crashed", "no timing_summary.json"),                        # B1: one in stdout too
    ({"rc": 1, "success": False, "exit_reason": "all_searched"}, "failure", None),
    ({"rc": None}, "crashed", "left no rc"),
])
def test_boxels_planted_statuses(tmp_path, plan, status, extra):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, _, rc, _ = run_fake(tmp_path, d, {("boxels", 1, "B"): plan})
    assert rc == 0
    ends = end_rows(set_dir)
    row = [e for e in ends.values() if e["seed"] == 1 and e["arm"] == "B"][0]
    assert row["status"] == status and row["success"] is False
    if extra:
        assert extra in (row["crash_cause"] or "")
    if status == "preflight_rejected":
        assert row["preflight_message"].startswith("[pre-flight] seed 1 rejected: ")
    others = [e for e in ends.values() if not (e["seed"] == 1 and e["arm"] == "B")]
    assert all(e["status"] == "success" for e in others)
    a = ps.analyse(set_dir)
    assert a["full"], a["not_full"]                     # crashes are counted, not missing
    pair = [p for p in a["worlds"]["boxels"]["pairs"] if p["seed"] == 1][0]
    assert pair["B"] == status and pair["new_success"] is False


def test_boxels_wrong_scene_is_not_full(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    cfg = {"scene": "random-pairs", "seed": 9, "goal": "holding", "baseline": "semantic",
           "unit_costs": False}
    set_dir, _, _, _ = run_fake(tmp_path, d, {("boxels", 2, "A"): {"run_config": cfg}})
    row = [e for e in end_rows(set_dir).values() if e["seed"] == 2 and e["arm"] == "A"][0]
    assert row["status"] == "wrong_scene" and "seed=9" in row["summary_mismatch"]
    a = ps.analyse(set_dir)
    assert not a["full"] and a["verdict"] == "NOT FULL"
    assert any("wrong_scene" in p for p in a["not_full"])


def test_boxels_wrong_statistics_start_is_not_full(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, _, _, _ = run_fake(tmp_path, d, {("boxels", 0, "B"): {"stats": "f" * 64}})
    a = ps.analyse(set_dir)
    assert any("statistics sha256" in p for p in a["not_full"])


@pytest.mark.parametrize("plan, status, gates", [
    ({}, "success", []),
    ({"gates": {"G19": "seed 0 loaded p_b"}}, "success", ["G19"]),     # S-q: G19 alone
    ({"gates": {"G19": "x", "G7": "y"}, "reward": 1.0}, "gate_failed", ["G19", "G7"]),
    ({"reward": 0.0}, "failure", []),
    ({"error": "ValueError: x"}, "crashed", []),
    ({"stderr": "Traceback (most recent call last):\n"}, "crashed", []),
    ({"rc": 124, "wall": 1200.5, "record": False}, "killed", []),
    ({"rc": 1, "record": False}, "crashed", []),                        # no record file
    ({"rc": 1, "record": False, "stdout": "G19: seed 0 loaded p_b, pinned p_a\n"},
     "gate_failed", ["G19"]),
    # the note under --allow-g19-mismatch 1 is not a stop: still a crash
    ({"rc": 1, "record": False, "stdout": "G19: seed 0 loaded p_b, the campaign pins p_a: "
      "a watching or diagnostic run, never scored\n"}, "crashed", []),
    ({"rc": 1, "record": False, "stdout": "G13 runtime check failed: x\n"},
     "gate_failed", ["G13"]),
    ({"seed": 3}, "wrong_scene", []),
    ({"rc": 139}, "crashed", []),                       # a signal after the record
])
def test_bridge_planted_statuses(tmp_path, plan, status, gates):
    d = make_decl(tmp_path, kind="N", boxels_seeds=())
    set_dir, _, _, _ = run_fake(tmp_path, d, {("bridge", 0, "A"): plan})
    row = [e for e in end_rows(set_dir).values() if e["seed"] == 0 and e["arm"] == "A"][0]
    assert row["status"] == status, row
    assert row["gate_failures"] == gates
    assert row["stats_sha256"] is None
    if plan.get("record", True) and status != "killed":
        assert row["plan_count"] == 3                        # from the run dir's summary


def test_bridge_scene_differs_in_a_pair(tmp_path):
    d = make_decl(tmp_path, kind="N", boxels_seeds=())
    set_dir, _, _, _ = run_fake(tmp_path, d, {("bridge", 1, "B"): {"scene": "p_z.json"}})
    a = ps.analyse(set_dir)
    assert any("different scene files" in p for p in a["not_full"])


def test_not_started_stops_the_set(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, fl, rc, lines = run_fake(tmp_path, d, {("boxels", 1, "B"): not_started})
    assert rc == 4
    stop_pos = [r for r in ps.run_list(d) if r["seed"] == 1 and r["arm"] == "B"][0]["pos"]
    assert fl.calls[-1] == stop_pos
    rows = [json.loads(x) for x in (set_dir / ps.RESULTS_NAME).read_text().splitlines()]
    assert rows[-1]["event"] == "set_end" and rows[-1]["stopped_at"] == stop_pos
    assert end_rows(set_dir)[stop_pos]["not_started"] == "mem_available_under_4_gb"
    a = ps.analyse(set_dir)
    assert a["verdict"] == "NOT FULL"
    assert any("not_started" in p for p in a["not_full"])
    assert any("missing" in p for p in a["not_full"])     # the runs after the stop


def test_gate_closed_is_not_started(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, _, rc, _ = run_fake(tmp_path, d, {("boxels", 0, "A"): lambda fl, r, ep: {"gate_rc": 3}})
    assert rc == 4
    assert end_rows(set_dir)[1]["not_started"] == "gate_closed"


def test_checkout_changed_during_the_set(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    env_end = good_env(d)
    env_end["arms"]["B"]["dirty"] = True
    env_end["venv"]["pip_freeze_sha256"] = "0" * 64
    set_dir, _, rc, _ = run_fake(tmp_path, d, env_end=env_end)
    assert rc == 0
    a = ps.analyse(set_dir)
    assert any("arm B at the set's end" in p for p in a["not_full"])
    assert any("pip freeze" in p for p in a["not_full"])


# ---------------------------------------------------------------------------
# The analysis: rows that are missing, doubled or vanished
# ---------------------------------------------------------------------------

def _rewrite(set_dir, keep):
    p = set_dir / ps.RESULTS_NAME
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    rows = keep(rows)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_missing_doubled_vanished_rows(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, _, _, _ = run_fake(tmp_path, d)
    assert ps.analyse(set_dir)["full"]
    _rewrite(set_dir, lambda rows: [r for r in rows if r.get("pos") != 3])
    a = ps.analyse(set_dir)
    assert a["verdict"] == "NOT FULL" and any("run 3" in p and "missing" in p for p in a["not_full"])

    set_dir, _, _, _ = run_fake(tmp_path, d, name="dbl")
    def double(rows):
        e = [r for r in rows if r.get("event") == "end" and r["pos"] == 2][0]
        return rows + [{**e, "status": "failure", "success": False}]
    _rewrite(set_dir, double)
    a = ps.analyse(set_dir)
    assert any("run 2" in p and "doubled" in p for p in a["not_full"])
    pair = [p for p in a["worlds"]["boxels"]["pairs"] if p["seed"] == 0][0]
    assert pair["B"] == "success"                          # the first end row counts

    set_dir, _, _, _ = run_fake(tmp_path, d, name="van")
    _rewrite(set_dir, lambda rows: [r for r in rows
                                    if not (r.get("event") == "end" and r["pos"] == 4)])
    a = ps.analyse(set_dir)
    assert any("run 4" in p and "vanished" in p for p in a["not_full"])
    pair = [p for p in a["worlds"]["boxels"]["pairs"] if p["seed"] == 1][0]
    assert pair["A"] == "vanished" and pair["old_success"] is False


def test_declaration_changed_after_the_run(tmp_path):
    d = make_decl(tmp_path, kind="N", bridge_seeds=())
    set_dir, _, _, _ = run_fake(tmp_path, d)
    p = set_dir / ps.DECLARATION_NAME
    p.write_text(p.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
    a = ps.analyse(set_dir)
    assert any("declaration changed" in x for x in a["not_full"])


# ---------------------------------------------------------------------------
# The pass rule of 24.4 (b), PLAN 8's rule for S, and the CLI exit codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("b, c, p", [(0, 0, 1.0), (6, 0, 0.03125), (5, 0, 0.0625),
                                     (4, 0, 0.125), (3, 3, 1.0), (7, 1, 0.0703125)])
def test_mcnemar_exact(b, c, p):
    assert ps.mcnemar_exact(b, c) == pytest.approx(p, abs=1e-12)
    assert ps.mcnemar_exact(c, b) == pytest.approx(p, abs=1e-12)


SEEDS20 = tuple(range(20))
FAIL_B = {"rc": 1, "success": False}          # boxels failure, exit reason pick_giveup


def _flips(old_wins, new_wins):
    plan = {}
    for s in old_wins:
        plan[("boxels", s, "B")] = FAIL_B
    for s in new_wins:
        plan[("boxels", s, "A")] = FAIL_B
    return plan


def _set_a(tmp, plan, noise_plan=None, name="setA"):
    # Set N fails seed 19 in both arms (no flip), so a plain failure with
    # pick_giveup is an outcome kind and exit reason set N shows.
    base = {("boxels", 19, "A"): FAIL_B, ("boxels", 19, "B"): FAIL_B}
    nd = noise_set(tmp, {**base, **(noise_plan or {})}, seeds=SEEDS20, bridge=())
    d = make_decl(tmp / (name + "_src"), kind="A", boxels_seeds=SEEDS20, bridge_seeds=(),
                  noise_dir=nd)
    set_dir, _, rc, _ = run_fake(tmp, d, plan, name=name)
    assert rc == 0
    return set_dir


def test_pass_rule_net_flips(tmp_path):
    a = ps.analyse(_set_a(tmp_path, _flips([0, 1], [])))
    w = a["worlds"]["boxels"]
    assert w["net_flips"] == 2 and a["verdict"] == "PASS"          # one or two seeds pass
    a = ps.analyse(_set_a(tmp_path / "t3", _flips([0, 1, 2], [])))
    assert a["verdict"] == "FAIL" and "boxels: 3_net_one_way_flips" in a["fails"]
    assert not a["worlds"]["boxels"]["items"]["4_mcnemar"]["fails"]   # p 0.25
    a = ps.analyse(_set_a(tmp_path / "t4", _flips([0, 1, 2, 3], [4])))
    assert a["worlds"]["boxels"]["net_flips"] == 3 and a["verdict"] == "FAIL"
    a = ps.analyse(_set_a(tmp_path / "t6", _flips([0, 1, 2, 3, 4, 5], [])))
    assert {"boxels: 3_net_one_way_flips", "boxels: 4_mcnemar"} <= set(a["fails"])


def test_pass_rule_noise_threshold(tmp_path):
    noise = _flips([10, 11, 12], [])                      # N shows 3 net flips
    a = ps.analyse(_set_a(tmp_path, _flips([0, 1, 2], []), noise_plan=noise))
    it = a["worlds"]["boxels"]["items"]["3_net_one_way_flips"]
    assert it["noise_count"] == 3 and it["threshold"] == 4 and not it["fails"]
    assert a["verdict"] == "PASS"


def test_noise_set_reports_its_count(tmp_path):
    nd = noise_set(tmp_path, _flips([0], [1, 2, 3, 4]), seeds=SEEDS20, bridge=())
    a = ps.analyse(nd)
    w = a["worlds"]["boxels"]
    assert a["verdict"] == "RECORDED" and w["net_flips"] == -3
    assert w["n_count_for_item3"] == 3 and w["tell_R"] is True
    assert "R is told" in ps.format_report(a)


def test_pass_rule_new_exit_reason(tmp_path):
    new_reason = {("boxels", 3, "B"): {"rc": 1, "success": False, "exit_reason": "drop_failed"},
                  ("boxels", 3, "A"): FAIL_B}
    a = ps.analyse(_set_a(tmp_path, new_reason))
    it = a["worlds"]["boxels"]["items"]["2_new_exit_reason_kind_or_gate"]
    assert it["fails"] and it["exit_reasons"] == ["drop_failed"]
    # the same reason seen in set N passes item 2
    noise = {("boxels", 9, "A"): {"rc": 1, "success": False, "exit_reason": "drop_failed"}}
    a = ps.analyse(_set_a(tmp_path / "n", new_reason, noise_plan=noise))
    assert not a["worlds"]["boxels"]["items"]["2_new_exit_reason_kind_or_gate"]["fails"]


def test_pass_rule_new_outcome_kind_and_gate(tmp_path):
    nd = noise_set(tmp_path, {}, seeds=(), bridge=(0, 1, 2))
    plan = {("bridge", 1, "B"): {"gates": {"G19": "x", "G7": "y"}},
            ("bridge", 2, "B"): {"rc": 124, "wall": 1300.0, "record": False}}
    d = make_decl(tmp_path / "a_src", kind="A", boxels_seeds=(), bridge_seeds=(0, 1, 2),
                  noise_dir=nd)
    set_dir, _, _, _ = run_fake(tmp_path, d, plan, name="setA")
    it = ps.analyse(set_dir)["worlds"]["bridge"]["items"]["2_new_exit_reason_kind_or_gate"]
    assert it["fails"] and it["gates"] == ["G7"] and set(it["kinds"]) == {"gate_failed", "killed"}


def test_pass_rule_crash_review(tmp_path):
    plan = {("boxels", 5, "B"): {"rc": 1, "make_dir": False,
                                 "stderr": "Traceback (most recent call last):\n"},
            ("boxels", 5, "A"): FAIL_B}
    set_dir = _set_a(tmp_path, plan)
    a = ps.analyse(set_dir)
    pos = a["worlds"]["boxels"]["crashes_B"][0]
    assert a["verdict"] == "PENDING REVIEW" and a["pending_reviews"] == [pos]
    assert ps.analyse(set_dir, {pos: "not_migration"})["verdict"] == "PASS"
    a = ps.analyse(set_dir, {str(pos): "migration"})
    assert a["verdict"] == "FAIL" and "boxels: 1_crash_on_migration" in a["fails"]
    rev = tmp_path / "rev.json"
    rev.write_text(json.dumps({str(pos): "migration"}))
    out = tmp_path / "a.json"
    assert ps.main(["analyse", "--set-dir", str(set_dir), "--crash-reviews", str(rev),
                    "--json", str(out)]) == 1
    assert json.loads(out.read_text())["verdict"] == "FAIL"
    assert ps.main(["analyse", "--set-dir", str(set_dir)]) == 3


def test_set_a_needs_a_full_noise_set_with_its_seeds(tmp_path):
    nd = noise_set(tmp_path, {}, seeds=(0, 1), bridge=())
    d = make_decl(tmp_path / "a_src", kind="A", boxels_seeds=(0, 1, 2), bridge_seeds=(),
                  noise_dir=nd)
    set_dir, _, _, _ = run_fake(tmp_path, d, name="setA")
    a = ps.analyse(set_dir)
    assert a["verdict"] == "NOT FULL"
    assert any("seeds differ" in p for p in a["not_full"])


def test_set_s_rule(tmp_path):
    d = make_decl(tmp_path, kind="S", boxels_seeds=(0, 1, 2, 3, 4, 5), bridge_seeds=(0, 1, 5))
    set_dir, _, _, _ = run_fake(tmp_path, d, name="ok")
    assert ps.analyse(set_dir)["verdict"] == "PASS"
    # a crash in the OLD arm also fails S ("no crash")
    set_dir, _, _, _ = run_fake(tmp_path, d, {("boxels", 2, "A"): {"rc": 2, "make_dir": False}},
                                name="crash")
    a = ps.analyse(set_dir)
    assert a["verdict"] == "FAIL" and "boxels: no_crash" in a["fails"]
    # an outcome kind the old arm never shows
    set_dir, _, _, _ = run_fake(tmp_path, d, {("bridge", 5, "B"): {"reward": 0.0}}, name="kind")
    a = ps.analyse(set_dir)
    assert a["verdict"] == "FAIL"
    assert a["worlds"]["bridge"]["items"]["new_kind_or_exit_reason"]["kinds"] == ["failure"]
    assert ps.main(["analyse", "--set-dir", str(set_dir)]) == 1


def test_report_and_plan_cli(tmp_path, capsys):
    d = make_decl(tmp_path, kind="N")
    set_dir, _, _, _ = run_fake(tmp_path, d)
    assert ps.main(["plan", "--set-dir", str(set_dir)]) == 0
    out = capsys.readouterr().out
    assert "declaration ok" in out and "| 1 | 0 | boxels | 0 | A |" in out
    assert ps.main(["analyse", "--set-dir", str(set_dir)]) == 0
    out = capsys.readouterr().out
    assert "full: yes" in out and "verdict: RECORDED" in out and "validity notes" in out
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / ps.DECLARATION_NAME).write_text("no block", encoding="utf-8")
    assert ps.main(["plan", "--set-dir", str(bad)]) == 2


# ---------------------------------------------------------------------------
# The bash scripts, for real, with a fake python (WSL/Linux only)
# ---------------------------------------------------------------------------

FAKE_PY = r"""#!/bin/bash
# a stand-in for the venv's python: no pipeline, no pybullet
if [ "$1" = test_full_pipeline.py ]; then
    seed=$6
    if [ "$seed" = 1 ]; then sleep 30; fi
    d=logs/run_fake_$seed
    mkdir -p "$d"
    printf '{"run_config": {"scene": "random-pairs", "seed": %s, "goal": "holding", "baseline": "semantic", "unit_costs": false}, "success": true, "exit_reason": null, "plan_count": 1}' "$seed" > "$d/timing_summary.json"
    echo "argv: $*"
    exit 0
fi
save=$7
mkdir -p "$save/ours/run_x"
printf '{"seed": %s, "scene_file": "p.json", "rewards": [1.0], "run_dir": "%s/ours/run_x", "outcome": {"status": "success", "success": true, "reward": 1.0, "error": null, "gate_failures": {}}}' "$3" "$save" > "$save/bridge_episode.json"
echo "cwd $PWD PYTHONPATH $PYTHONPATH HASHSEED $PYTHONHASHSEED"
exit 0
"""


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None or
                    shutil.which("flock") is None or shutil.which("timeout") is None,
                    reason="bash scripts run on WSL/Linux only; no bash is spawned on Windows")
def test_episode_scripts_run_for_real(tmp_path):
    d = make_decl(tmp_path, kind="N", boxels_seeds=(0, 1), bridge_seeds=(4,))
    fake = tmp_path / "fakepy"
    fake.write_text(FAKE_PY)
    fake.chmod(0o755)
    tw = tmp_path / "tw"
    (tw / "tampura_environments").mkdir(parents=True)
    d["machine"].update(python=str(fake), lock=str(tmp_path / "private.lock"),
                        mem_available_min_gb=0.001, tampura_work=str(tw))
    d["worlds"]["boxels"]["cap_s"] = 2
    set_dir = tmp_path / "set"
    write_decl(set_dir, d)

    class BashLauncher(FakeLauncher):
        def run_episode(self, r, ep):
            script = ep / "episode.sh"
            script.write_bytes(ps.episode_script(self.d, r, ep).encode())
            p = subprocess.run(["timeout", "120", "bash", str(script)], timeout=150)
            return {"gate_rc": p.returncode}

    rc = ps.run_set(set_dir, launcher=BashLauncher(d, set_dir), sleep=lambda s: None,
                    out=lambda s: None)
    assert rc == 0
    ends = end_rows(set_dir)
    by = {(e["world"], e["seed"], e["arm"]): e for e in ends.values()}
    assert by[("boxels", 0, "A")]["status"] == "success"
    assert by[("boxels", 0, "A")]["stats_sha256"] == d["statistics_file"]["boxels"]["sha256"]
    assert by[("boxels", 1, "B")]["status"] == "timeout"        # sleep 30 under a 2 s cap
    assert by[("boxels", 1, "B")]["rc"] == 124
    assert by[("bridge", 4, "A")]["status"] == "success"
    stdout = (set_dir / by[("bridge", 4, "A")]["ep"] / "stdout.txt").read_text()
    assert f"cwd {tw}/tampura_environments" in stdout and "HASHSEED 0" in stdout
    box_out = (set_dir / by[("boxels", 0, "A")]["ep"] / "stdout.txt").read_text()
    assert ("argv: test_full_pipeline.py --no-gui --scene random-pairs --seed 0 --goal "
            "holding --baseline semantic --log-level quiet --no-telemetry --n-occluders 2"
            ) in box_out
    restored = Path(d["arms"]["A"]["checkout"]) / ps.STATS_REL
    assert restored.read_bytes() == b"stats-copy"
    # memory under the limit: the episode does not start
    d2 = copy.deepcopy(d)
    d2["machine"]["mem_available_min_gb"] = 10 ** 6
    d2["set_id"] = "mem"
    s2 = tmp_path / "set2"
    write_decl(s2, d2)
    assert ps.run_set(s2, launcher=BashLauncher(d2, s2), sleep=lambda s: None,
                      out=lambda s: None) == 4
    assert end_rows(s2)[1]["not_started"].startswith("mem_available_under_")
