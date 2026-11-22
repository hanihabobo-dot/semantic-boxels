"""Tests of tools/readable/move_check.py (Phase 0 of the readable migration).

No pybullet, no pipeline import: move_check reads source text only. The
two real cases of the index (P1 deletion `build_tray_stack_goal`, P2 move
`BoxelTestEnv._assert_xys_in_reach`) read the worktree's own files; their
spans are found by `ast` here, so a test skips (not fails) once a later
phase has moved the function away. The planted bad cuts of PLAN 24.3 (f)
are one-edit changes to a clean case; each must be flagged.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "readable" / "move_check.py"
sys.path.insert(0, str(TOOL.parent))
import move_check as mc  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

# M5: a spec that maps names names its state classes. The fixtures' state
# module declares every field the synthetic and real cuts below map.
STATE_PY = '''\
"""State classes of the move_check fixtures (M5)."""
from dataclasses import dataclass


@dataclass
class Counts:
    plan_count: int = 0
    sense_count: int = 0


@dataclass
class Ending:
    exit_reason: object = None
    episode_over: bool = False


class Setup:
    def __init__(self):
        self.planner = None
        self.args = None
'''

STATE = {"file": "state.py",
         "groups": {"counts": "Counts", "ending": "Ending", "setup": "Setup"}}


def run(entries, old_files=None, new_files=None, tmp_path=None,
        old_root=None, state=STATE, extra=None):
    """Write the old and new trees and run the spec. With `state` (the
    default) the spec names the fixtures' state classes and state.py is
    written into the new tree unless the test brings its own."""
    old_dir = Path(old_root) if old_root else tmp_path / "old"
    new_dir = tmp_path / "new"
    new_files = dict(new_files or {})
    if state is not None and state["file"] not in new_files:
        new_files[state["file"]] = STATE_PY
    for d, files in ((old_dir, old_files), (new_dir, new_files)):
        if files:
            d.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                (d / name).write_text(text, encoding="utf-8")
    spec = {"spec_version": 1, "entries": entries}
    if state is not None:
        spec["state_classes"] = state
    spec.update(extra or {})
    return mc.run_spec(spec, mc.file_reader(str(old_dir), None, None),
                       mc.file_reader(str(new_dir), None, None))


def one(results):
    """The single entry result (the file accounts of M1 follow the entries
    in run_spec's list; tests of the accounts read them with accounts())."""
    entries = mc.entry_results(results)
    assert len(entries) == 1
    print(mc.format_result(entries[0]))
    return entries[0]


def accounts(results):
    out = {r.old_file: r for r in results if r.kind == "account"}
    for r in out.values():
        print(mc.format_result(r))
    return out


def real_text(rel):
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} not in this checkout")
    return p.read_text(encoding="utf-8")


def find_def(tree, qualname):
    node = tree
    for part in qualname.split("."):
        found = None
        for sub in ast.walk(node):
            if isinstance(sub, (ast.FunctionDef, ast.ClassDef)) \
                    and sub.name == part and sub is not node:
                found = sub
                break
        if found is None:
            return None
        node = found
    return node


def def_lines(text, qualname):
    node = find_def(ast.parse(text), qualname)
    if node is None:
        pytest.skip(f"{qualname} is no longer where refactor-checkpoint-1 "
                    f"had it")
    first = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return node, first, node.end_lineno


# ---------------------------------------------------------------------------
# real case 2: P2 move of BoxelTestEnv._assert_xys_in_reach
# ---------------------------------------------------------------------------

P2_ENTRY = {"id": "P2-assert-xys", "kind": "move", "phase": "P2",
            "old": {"file": "boxel_env.py",
                    "qualname": "BoxelTestEnv._assert_xys_in_reach"},
            "new": {"file": "world_placement.py",
                    "qualname": "WorldPlacement._assert_xys_in_reach"}}


def p2_method_lines():
    text = real_text("boxel_env.py")
    _node, first, last = def_lines(text,
                                   "BoxelTestEnv._assert_xys_in_reach")
    return text.splitlines()[first - 1:last], first, last


def p2_new(method_lines):
    return ('"""World placement (move_check test fixture)."""\n'
            "import numpy as np\n\n\n"
            "class WorldPlacement:\n"
            + "\n".join(method_lines) + "\n")


def run_p2(tmp_path, method_lines):
    return one(run([P2_ENTRY], new_files={"world_placement.py":
                                          p2_new(method_lines)},
                   tmp_path=tmp_path, old_root=ROOT))


def test_p2_clean_whole_function_move(tmp_path):
    lines, first, last = p2_method_lines()
    r = run_p2(tmp_path, lines)
    assert r.status == "clean", r.errors
    assert r.old_lines == f"{first}-{last}"
    assert r.rewrites_used == {}
    assert not r.code_residual and not r.comment_residual
    # every logical line is matched in the line map
    assert len(r.line_map) >= 8
    # the attributes that stay in BoxelTestEnv are listed for R
    assert any("_ROBOT_BASE_XY" in i and "MRO" in i for i in r.info)
    assert any("globals read" in i and "np" in i for i in r.info)


def test_p2_move_without_numpy_import_is_flagged(tmp_path):
    lines, _f, _l = p2_method_lines()
    text = p2_new(lines).replace("import numpy as np\n", "")
    r = one(run([P2_ENTRY], new_files={"world_placement.py": text},
                tmp_path=tmp_path, old_root=ROOT))
    assert "free-name" in r.rules_failed
    assert any("'np'" in m and "not bound" in m for _r, m in r.errors)


def _edit(lines, old, new, count=1):
    joined = "\n".join(lines)
    assert old in joined, old
    return joined.replace(old, new, count).split("\n")


def test_planted_two_statements_swapped(tmp_path):
    lines, _f, _l = p2_method_lines()
    i = next(k for k, s in enumerate(lines)
             if "bx, by = self._ROBOT_BASE_XY" in s)
    j = next(k for k, s in enumerate(lines)
             if "r_max = self._PANDA_REACH_RADIUS" in s)
    lines[i], lines[j] = lines[j], lines[i]
    r = run_p2(tmp_path, lines)
    assert r.status == "residual"
    assert "token-mismatch" in r.rules_failed


def test_planted_operator_changed(tmp_path):
    lines, _f, _l = p2_method_lines()
    r = run_p2(tmp_path, _edit(lines, "if d > r_max:", "if d >= r_max:"))
    assert "token-mismatch" in r.rules_failed
    assert any("if d >= r_max:" in c for c in r.code_residual)


def test_planted_literal_changed_in_fstring(tmp_path):
    lines, _f, _l = p2_method_lines()
    r = run_p2(tmp_path, _edit(lines, ":.3f}", ":.2f}"))
    assert "token-mismatch" in r.rules_failed


def test_planted_number_literal_changed(tmp_path):
    lines, _f, _l = p2_method_lines()
    r = run_p2(tmp_path, _edit(lines, "float(xy[0]) - bx",
                               "float(xy[1]) - bx"))
    assert "token-mismatch" in r.rules_failed


def test_planted_line_dropped(tmp_path):
    lines, _f, _l = p2_method_lines()
    lines = [s for s in lines if "d = float(np.hypot(" not in s]
    r = run_p2(tmp_path, lines)
    assert "token-mismatch" in r.rules_failed
    # the dropped binding also makes `d` a global the old code never read
    assert any("'d'" in m for rule, m in r.errors if rule == "free-name")


# ---------------------------------------------------------------------------
# real case 1: P1 deletion of build_tray_stack_goal (and the decorator trap)
# ---------------------------------------------------------------------------

P1_ENTRY = {"id": "P1-tray-goal", "kind": "delete", "phase": "P1",
            "old": {"file": "test_full_pipeline.py",
                    "qualname": "build_tray_stack_goal"}}


def deleted(text, first, last):
    lines = text.splitlines(keepends=True)
    return "".join(lines[:first - 1] + lines[last:])


def test_p1_clean_deletion(tmp_path):
    text = real_text("test_full_pipeline.py")
    _n, first, last = def_lines(text, "build_tray_stack_goal")
    r = one(run([P1_ENTRY], new_files={"test_full_pipeline.py":
                                       deleted(text, first, last)},
                tmp_path=tmp_path, old_root=ROOT))
    assert r.status == "clean", (r.errors, r.code_residual[:2])
    assert r.old_lines == f"{first}-{last}"


def test_p1_deletion_with_a_reference_left_is_flagged(tmp_path):
    text = real_text("test_full_pipeline.py")
    _n, first, last = def_lines(text, "build_tray_stack_goal")
    new = deleted(text, first, last) + "_keep = build_tray_stack_goal\n"
    r = one(run([P1_ENTRY], new_files={"test_full_pipeline.py": new},
                tmp_path=tmp_path, old_root=ROOT))
    assert "reference-remains" in r.rules_failed


def test_p1_deletion_that_drops_another_line_is_flagged(tmp_path):
    text = real_text("test_full_pipeline.py")
    _n, first, last = def_lines(text, "build_tray_stack_goal")
    # also drop the module's first `import` line, outside the span
    lines = deleted(text, first, last).splitlines(keepends=True)
    k = next(i for i, s in enumerate(lines) if s.startswith("import "))
    new = "".join(lines[:k] + lines[k + 1:])
    r = one(run([P1_ENTRY], new_files={"test_full_pipeline.py": new},
                tmp_path=tmp_path, old_root=ROOT))
    assert "token-mismatch" in r.rules_failed


def test_decorated_def_span_starts_at_its_decorator(tmp_path):
    text = real_text("boxel_env.py")
    node, first, last = def_lines(text, "BoxelTestEnv._spawn_object")
    assert node.decorator_list, "the trap needs @staticmethod"
    entry = {"id": "P1-spawn-object", "kind": "delete", "phase": "P1",
             "old": {"file": "boxel_env.py",
                     "qualname": "BoxelTestEnv._spawn_object"}}
    new = deleted(text, first, last)
    r = one(run([entry], new_files={"boxel_env.py": new},
                tmp_path=tmp_path, old_root=ROOT))
    assert r.old_lines == f"{first}-{last}"
    assert first < node.lineno
    assert r.status in ("clean", "review"), r.errors
    # the banner comment above stays and is listed for R
    assert any("adjacent" in i for i in r.info)
    # a span written from the def line splits the decorator
    entry["old"]["start_line"] = node.lineno
    r2 = one(run([entry], new_files={"boxel_env.py": new},
                 tmp_path=tmp_path, old_root=ROOT))
    assert "span-splits-decorator" in r2.rules_failed


# ---------------------------------------------------------------------------
# a real closure-to-function cut: main._at_home, `planner` mapped
# ---------------------------------------------------------------------------

def test_real_closure_cut_at_home_is_clean(tmp_path):
    text = real_text("test_full_pipeline.py")
    node, _first, last = def_lines(text, "main._at_home")
    body = text.splitlines()[node.body[0].lineno - 1:last]
    body = textwrap.dedent("\n".join(body))
    assert body.count("planner.") == 1
    body = body.replace("planner.", "st.setup.planner.")
    new = ("import numpy as np\n\n\n"
           "def _at_home(st, joints) -> bool:\n"
           + textwrap.indent(body, "    ") + "\n")
    entry = {"id": "P5-at-home", "kind": "cut", "phase": "P5",
             "old": {"file": "test_full_pipeline.py",
                     "qualname": "main._at_home",
                     "start_anchor": "\"\"\"TAMPURA's at-home test",
                     "end_anchor": "return bool(np.allclose("},
             "new": {"file": "stages.py", "qualname": "_at_home"},
             "name_map": {"planner": "st.setup.planner"}}
    r = one(run([entry], new_files={"stages.py": new}, tmp_path=tmp_path,
                old_root=ROOT))
    assert r.status == "clean", (r.errors, r.code_residual)
    assert r.rewrites_used.get("R1 name map") == 1


def test_real_cut_through_a_try_of_main_is_flagged(tmp_path):
    # the try of main() this walk found at the checkpoint (the one around
    # the boxel counts of a replan, with the sync to the plan client after
    # it) stands in plan_or_stop since main was cut into functions, and the
    # same walk finds it there
    text = real_text("test_full_pipeline.py")
    main_node, _f, _l = def_lines(text, "plan_or_stop")
    pick = None
    for parent in ast.walk(main_node):
        for fld in ("body", "orelse"):
            seq = getattr(parent, fld, None)
            if not isinstance(seq, list):
                continue
            for k, s in enumerate(seq[:-1]):
                if isinstance(s, ast.Try):
                    pick = (s, seq[k + 1])
                    break
            if pick:
                break
        if pick:
            break
    assert pick, "main has Try nodes at the checkpoint"
    try_node, after = pick
    entry = {"id": "bad-try-cut", "kind": "cut", "phase": "P5",
             "old": {"file": "test_full_pipeline.py", "qualname": "plan_or_stop",
                     "start_line": try_node.body[0].lineno,
                     "end_line": after.lineno},
             "new": {"file": "stages.py", "qualname": "stage"}}
    r = one(run([entry], new_files={"stages.py": "def stage():\n    pass\n"},
                tmp_path=tmp_path, old_root=ROOT))
    assert "cut-crosses-block" in r.rules_failed
    assert any("try.body" in m for _r, m in r.errors)


# ---------------------------------------------------------------------------
# synthetic cuts: the rewrites R1-R4 and the planted bad cuts
# ---------------------------------------------------------------------------

OLD = '''\
import random

LIMIT = 5


def helper(x):
    return x


def main(n):
    plan_count = 0
    exit_reason = None
    episode_over = False
    if n < 0:
        return False

    def _finish(label):
        nonlocal exit_reason, episode_over
        # narration: the episode ends here
        exit_reason = label
        episode_over = True
        return True

    with open(__file__) as fh:
        head = fh.readline()
    tail = head.strip()

    while not episode_over:
        plan_count += 1
        # count one plan
        for k in range(3):
            if k == n:
                break
        if plan_count > LIMIT:
            exit_reason = "timeout"  # loop ends
            break
        if helper(plan_count) == 2:
            print(f"plan {plan_count} of {n}")
    return exit_reason
'''

NEW = '''\
import random

LIMIT = 5
BREAK = object()
EARLY_FALSE = object()


def helper(x):
    return x


def check_input(n):
    if n < 0:
        return EARLY_FALSE


def _finish(st, label):
    # narration: the episode ends here
    st.ending.exit_reason = label
    st.ending.episode_over = True
    return True


def run_one_plan(st, n):
    st.counts.plan_count += 1
    # count one plan
    for k in range(3):
        if k == n:
            break
    if st.counts.plan_count > LIMIT:
        st.ending.exit_reason = "timeout"  # loop ends
        return BREAK
    if helper(st.counts.plan_count) == 2:
        print(f"plan {st.counts.plan_count} of {n}")
'''

LOOP = {"id": "loop", "kind": "cut", "phase": "P6",
        "old": {"file": "old.py", "qualname": "main",
                "start_anchor": "plan_count += 1",
                "end_anchor": "if helper(plan_count) == 2:"},
        "new": {"file": "new.py", "qualname": "run_one_plan"},
        "name_map": {"plan_count": "st.counts.plan_count",
                     "exit_reason": "st.ending.exit_reason"},
        "break_sentinel": "BREAK"}

EARLY = {"id": "early", "kind": "cut", "phase": "P5",
         "old": {"file": "old.py", "qualname": "main",
                 "start_anchor": "if n < 0:", "end_anchor": "if n < 0:"},
         "new": {"file": "new.py", "qualname": "check_input"},
         "sentinel_returns": {"False": "EARLY_FALSE"}}

FINISH = {"id": "finish", "kind": "cut", "phase": "P6",
          "old": {"file": "old.py", "qualname": "main._finish",
                  "start_anchor": "nonlocal exit_reason",
                  "end_anchor": "return True"},
          "new": {"file": "new.py", "qualname": "_finish"},
          "name_map": {"exit_reason": "st.ending.exit_reason",
                       "episode_over": "st.ending.episode_over"},
          "drop_nonlocal": True}


def copy(entry, **changes):
    e = json.loads(json.dumps(entry))
    for k, v in changes.items():
        e[k] = v
    return e


def syn(tmp_path, entry, new=NEW, old=OLD):
    return one(run([entry], old_files={"old.py": old},
                   new_files={"new.py": new}, tmp_path=tmp_path))


def test_clean_cut_with_name_map_and_break(tmp_path):
    r = syn(tmp_path, LOOP)
    assert r.status == "clean", (r.errors, r.code_residual)
    assert r.rewrites_used["R2 break to return"] == 1
    assert r.rewrites_used["R1 name map (in f-string)"] == 1
    assert r.rewrites_used["R1 name map"] >= 3


def test_clean_cut_with_sentinel_return(tmp_path):
    r = syn(tmp_path, EARLY)
    assert r.status == "clean", (r.errors, r.code_residual)
    assert r.rewrites_used == {"R3 sentinel return": 1}


def test_clean_closure_cut_drops_nonlocal(tmp_path):
    r = syn(tmp_path, FINISH)
    assert r.status == "clean", (r.errors, r.code_residual)
    assert r.rewrites_used["R4 nonlocal dropped"] == 1


def test_all_three_entries_in_one_spec(tmp_path):
    rs = run([LOOP, EARLY, FINISH], old_files={"old.py": OLD},
             new_files={"new.py": NEW}, tmp_path=tmp_path)
    assert [r.status for r in mc.entry_results(rs)] == ["clean"] * 3
    assert mc.exit_code(mc.entry_results(rs)) == 0
    # M1: the fixture's new tree has no main and no old.py, so the file
    # accounts print the rest of both files for R (exit 3, not 0)
    acc = accounts(rs)
    assert sorted(acc) == ["new.py", "old.py", "state.py"]
    assert acc["old.py"].status == "review" and acc["old.py"].outside
    assert mc.exit_code(rs) == 3


def test_dropped_comment_shows_as_residual(tmp_path):
    new = NEW.replace("    # count one plan\n", "")
    r = syn(tmp_path, LOOP, new=new)
    assert r.status == "review"
    assert not r.code_residual and not r.errors
    assert any("removed" in c and "count one plan" in c
               for c in r.comment_residual)
    assert mc.exit_code([r]) == 3


# B2 of REVIEW_PHASE0: the contiguous comment block directly above a cut
# span or a moved def is part of the comment diff (PLAN 24.3 (f), rule 19's
# narration comments). Dropped, it is a removed comment (residual, exit 3);
# kept above the new def or inside the new function, the entry is clean.

B2_OLD_CUT = '''\
def main(n):
    plan_count = 0
    # --- Stage B: the narration header of this block ---
    # (two lines, one block)
    plan_count += n
    plan_count += 2

    # separated by a blank line: not part of the block above the span
    return plan_count
'''

B2_CUT = {"id": "b2-cut", "kind": "cut", "phase": "P6",
          "old": {"file": "old.py", "qualname": "main",
                  "start_anchor": "plan_count += n",
                  "end_anchor": "plan_count += 2"},
          "new": {"file": "new.py", "qualname": "stage_b"},
          "name_map": {"plan_count": "st.counts.plan_count"}}

B2_HEADER = ("    # --- Stage B: the narration header of this block ---\n"
             "    # (two lines, one block)\n")
B2_BODY = ("    st.counts.plan_count += n\n"
           "    st.counts.plan_count += 2\n")

B2_OLD_MOVE = '''\
import os


# narration: why this helper exists
# (it joins one fixed part)
def helper(x):
    return os.path.join(x, "a")
'''

B2_MOVE = {"id": "b2-move", "kind": "move", "phase": "P2",
           "old": {"file": "a.py", "qualname": "helper"},
           "new": {"file": "b.py", "qualname": "helper"}}


def b2_move(tmp_path, new_text):
    return one(run([B2_MOVE], old_files={"a.py": B2_OLD_MOVE},
                   new_files={"b.py": new_text}, tmp_path=tmp_path))


def test_b2_move_dropping_the_comment_above_the_def_is_residual(tmp_path):
    new = B2_OLD_MOVE.replace("# narration: why this helper exists\n"
                              "# (it joins one fixed part)\n", "")
    r = b2_move(tmp_path, new)
    assert r.status == "review" and not r.code_residual and not r.errors
    assert sum("comment removed" in c for c in r.comment_residual) == 2
    assert any("why this helper exists" in c for c in r.comment_residual)
    assert mc.exit_code([r]) == 3


def test_b2_move_keeping_the_comment_above_the_def_is_clean(tmp_path):
    new = '"""b."""\nimport os\n\n\n' + B2_OLD_MOVE.split("\n\n\n", 1)[1]
    r = b2_move(tmp_path, new)
    assert r.status == "clean", (r.comment_residual, r.warnings)
    assert not any("adjacent" in i for i in r.info)
    assert mc.exit_code([r]) == 0


def test_b2_move_changing_the_comment_above_the_def_is_residual(tmp_path):
    r = b2_move(tmp_path, B2_OLD_MOVE.replace("why this helper", "why the helper"))
    assert r.status == "review"
    assert any("changed" in c and "why this helper" in c for c in r.comment_residual)


def b2_cut(tmp_path, new_text):
    return one(run([B2_CUT], old_files={"old.py": B2_OLD_CUT},
                   new_files={"new.py": new_text}, tmp_path=tmp_path))


def test_b2_cut_dropping_the_header_comment_is_residual(tmp_path):
    r = b2_cut(tmp_path, "def stage_b(st, n):\n" + B2_BODY)
    assert r.status == "review" and not r.code_residual and not r.errors
    assert sum("comment removed" in c for c in r.comment_residual) == 2
    assert any("Stage B" in c for c in r.comment_residual)
    assert mc.exit_code([r]) == 3
    # the comment after a blank line below the span stays information only
    assert any("adjacent" in i and "separated by a blank line" in i for i in r.info)
    assert not any("separated" in c for c in r.comment_residual)


def test_b2_cut_header_kept_as_the_new_functions_first_lines_is_clean(tmp_path):
    r = b2_cut(tmp_path, "def stage_b(st, n):\n" + B2_HEADER + B2_BODY)
    assert r.status == "clean", (r.comment_residual, r.warnings)
    assert mc.exit_code([r]) == 0


def test_b2_cut_header_kept_above_the_new_def_is_clean(tmp_path):
    lead = "".join(x[4:] + "\n" for x in B2_HEADER.splitlines())
    r = b2_cut(tmp_path, "import os\n\n\n" + lead + "def stage_b(st, n):\n" + B2_BODY)
    assert r.status == "clean", (r.comment_residual, r.warnings)
    assert mc.exit_code([r]) == 0


def test_b2_cli_dropped_header_exits_nonzero(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    (tmp_path / "old" / "old.py").write_text(B2_OLD_CUT, encoding="utf-8")
    (tmp_path / "new" / "new.py").write_text("def stage_b(st, n):\n" + B2_BODY,
                                             encoding="utf-8")
    (tmp_path / "new" / "state.py").write_text(STATE_PY, encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_version": 1, "entries": [B2_CUT],
                                "state_classes": STATE}),
                    encoding="utf-8")
    p = subprocess.run([sys.executable, str(TOOL), str(spec),
                        "--old-root", str(tmp_path / "old"),
                        "--new-root", str(tmp_path / "new")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    print(p.stdout, p.stderr)
    assert p.returncode == 3
    assert "RESIDUAL comment removed" in p.stdout and "Stage B" in p.stdout


def test_changed_inline_comment_shows_as_residual(tmp_path):
    new = NEW.replace("# loop ends", "# the loop ends")
    r = syn(tmp_path, LOOP, new=new)
    assert r.status == "review"
    assert any("changed" in c and "loop ends" in c
               for c in r.comment_residual)


def test_planted_two_names_mapped_to_one_field(tmp_path):
    e = copy(LOOP, name_map={"plan_count": "st.counts.plan_count",
                             "sense_count": "st.counts.plan_count"})
    r = syn(tmp_path, e)
    assert "map-not-one-to-one" in r.rules_failed
    assert not r.code_residual       # flagged at map load, before compare


def test_planted_cut_through_a_with(tmp_path):
    e = copy(LOOP, old={"file": "old.py", "qualname": "main",
                        "start_anchor": "head = fh.readline()",
                        "end_anchor": "tail = head.strip()"})
    r = syn(tmp_path, e)
    assert "cut-crosses-block" in r.rules_failed
    assert any("with.body" in m for _r, m in r.errors)


def test_planted_break_one_level_off(tmp_path):
    new = NEW.replace("        if k == n:\n            break",
                      "        if k == n:\n            return BREAK")
    r = syn(tmp_path, LOOP, new=new)
    assert "token-mismatch" in r.rules_failed


def test_planted_string_literal_changed(tmp_path):
    r = syn(tmp_path, LOOP, new=NEW.replace('"timeout"', '"time-out"'))
    assert "token-mismatch" in r.rules_failed


def test_planted_fstring_field_changed(tmp_path):
    r = syn(tmp_path, LOOP,
            new=NEW.replace("{st.counts.plan_count} of",
                            "{st.counts.sense_count} of"))
    assert "token-mismatch" in r.rules_failed


def test_planted_indentation_changed(tmp_path):
    # the `if plan_count > LIMIT` block moved into the for loop body
    new = NEW.replace(
        "    if st.counts.plan_count > LIMIT:\n"
        "        st.ending.exit_reason = \"timeout\"  # loop ends\n"
        "        return BREAK\n",
        "        if st.counts.plan_count > LIMIT:\n"
        "            st.ending.exit_reason = \"timeout\"  # loop ends\n"
        "            return BREAK\n")
    r = syn(tmp_path, LOOP, new=new)
    assert "token-mismatch" in r.rules_failed


def test_break_leaving_span_without_sentinel_is_flagged(tmp_path):
    e = copy(LOOP)
    del e["break_sentinel"]
    r = syn(tmp_path, e)
    assert "break-leaves-span" in r.rules_failed


def test_return_in_cut_without_sentinel_is_flagged(tmp_path):
    e = copy(EARLY)
    del e["sentinel_returns"]
    r = syn(tmp_path, e)
    assert "return-in-cut" in r.rules_failed


def test_nonlocal_dropped_but_name_not_mapped(tmp_path):
    e = copy(FINISH, name_map={"exit_reason": "st.ending.exit_reason"})
    r = syn(tmp_path, e)
    assert "nonlocal-name-unmapped" in r.rules_failed


def test_name_mapped_to_the_wrong_group(tmp_path):
    e = copy(LOOP, name_map={"plan_count": "st.counts.plan_count",
                             "exit_reason": "st.counts.exit_reason"})
    r = syn(tmp_path, e)
    assert "map-wrong-group" in r.rules_failed


def test_name_map_must_keep_the_name(tmp_path):
    e = copy(LOOP, name_map={"plan_count": "st.counts.n_plans",
                             "exit_reason": "st.ending.exit_reason"})
    r = syn(tmp_path, e)
    assert "map-renames-name" in r.rules_failed


def test_ambiguous_anchor_is_flagged(tmp_path):
    e = copy(LOOP, old={"file": "old.py", "qualname": "main",
                        "start_anchor": "plan_count",
                        "end_anchor": "if helper(plan_count) == 2:"})
    r = syn(tmp_path, e)
    assert "anchor-ambiguous" in r.rules_failed


# ---------------------------------------------------------------------------
# free names (PLAN 24.3 (f))
# ---------------------------------------------------------------------------

def test_free_name_not_a_parameter_is_flagged(tmp_path):
    # tokens equal (the header is not compared) but `n` is no longer a
    # parameter: a branch no pin runs would end in a NameError
    new = NEW.replace("def run_one_plan(st, n):", "def run_one_plan(st):")
    r = syn(tmp_path, LOOP, new=new)
    assert not r.code_residual
    assert "free-name" in r.rules_failed
    assert any("'n'" in m for _r, m in r.errors)


def test_free_name_new_global_is_flagged(tmp_path):
    # `planner` is no parameter, local, mapped field, builtin or old global
    new = NEW.replace("    if helper(st.counts.plan_count) == 2:",
                      "    if helper(st.counts.plan_count) == planner:")
    r = syn(tmp_path, LOOP, new=new)
    assert any("'planner'" in m for rule, m in r.errors
               if rule == "free-name")


def test_free_name_old_global_and_builtin_pass(tmp_path):
    r = syn(tmp_path, LOOP)
    info = " ".join(r.info)
    assert "LIMIT" in info and "helper" in info
    assert not [m for rule, m in r.errors if rule == "free-name"]


def test_free_name_local_read_before_bind_is_flagged(tmp_path):
    new = NEW.replace("    st.counts.plan_count += 1\n",
                      "    st.counts.plan_count += 1\n"
                      "    print(late)\n    late = 1\n")
    r = syn(tmp_path, LOOP, new=new)
    assert any("'late'" in m and "before it is bound" in m
               for rule, m in r.errors if rule == "free-name")


def test_free_name_sentinel_must_be_bound(tmp_path):
    new = NEW.replace("BREAK = object()\n", "")
    r = syn(tmp_path, LOOP, new=new)
    assert any("'BREAK'" in m for rule, m in r.errors
               if rule == "free-name")


# ---------------------------------------------------------------------------
# tokenizer: one STRING token per f-string on every Python version
# ---------------------------------------------------------------------------

def test_fstring_is_one_token_on_this_python():
    src = mc.scan_source('x = f"a {y!r:>{w}} \'b\' {z}" + "c"\n', "t.py")
    toks = src.logical[0].toks
    assert [t.type for t in toks] == ["NAME", "OP", "STRING", "OP",
                                      "STRING"]
    assert toks[2].string == 'f"a {y!r:>{w}} \'b\' {z}"'


def test_non_ascii_source_is_read_as_utf8(tmp_path):
    old = 'def f():\n    return "robot base \u2014 outside"\n'
    entry = {"id": "u", "kind": "move", "phase": "P2",
             "old": {"file": "a.py", "qualname": "f"},
             "new": {"file": "b.py", "qualname": "f"}}
    r = one(run([entry], old_files={"a.py": old},
                new_files={"b.py": old}, tmp_path=tmp_path))
    assert r.status == "clean"


# ---------------------------------------------------------------------------
# the command line: exit codes, MIGRATION_MAP.tsv, line map
# ---------------------------------------------------------------------------

def _cli(tmp_path, entries, new=NEW, extra=()):
    (tmp_path / "old").mkdir(exist_ok=True)
    (tmp_path / "new").mkdir(exist_ok=True)
    (tmp_path / "old" / "old.py").write_text(OLD, encoding="utf-8")
    (tmp_path / "new" / "new.py").write_text(new, encoding="utf-8")
    (tmp_path / "new" / "state.py").write_text(STATE_PY, encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_version": 1, "entries": entries,
                                "state_classes": STATE}),
                    encoding="utf-8")
    cmd = [sys.executable, str(TOOL), str(spec),
           "--old-root", str(tmp_path / "old"),
           "--new-root", str(tmp_path / "new"), *extra]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    print(p.stdout, p.stderr)
    return p


def test_cli_clean_writes_map_and_line_map(tmp_path):
    mp = tmp_path / "out" / "MIGRATION_MAP.tsv"
    lm = tmp_path / "out" / "line_map.tsv"
    p = _cli(tmp_path, [LOOP, EARLY, FINISH],
             extra=("--map", str(mp), "--line-map", str(lm)))
    # the three entries are clean; the file accounts (M1) print the rest of
    # the fixture's files, so the exit is 3
    assert p.returncode == 3
    assert "RESULT: clean" in p.stdout and "OUTSIDE outside the entries" in p.stdout
    rows = mp.read_text(encoding="utf-8").splitlines()
    assert rows[0].split("\t") == mc.MAP_HEADER
    assert len(rows) == 4
    assert rows[1].split("\t")[:6] == ["old.py", "main", "new.py",
                                       "run_one_plan", "P6", "cut"]
    assert len(lm.read_text(encoding="utf-8").splitlines()) > 5
    # a second run of one entry replaces its row and keeps the others
    p2 = _cli(tmp_path, [EARLY], extra=("--map", str(mp)))
    assert p2.returncode == 3
    rows2 = mp.read_text(encoding="utf-8").splitlines()
    assert len(rows2) == 4
    assert sum(r.split("\t")[8] == "early" for r in rows2[1:]) == 1


def test_cli_bad_cut_exits_1(tmp_path):
    p = _cli(tmp_path, [LOOP], new=NEW.replace('"timeout"', '"time-out"'))
    assert p.returncode == 1
    assert "RESIDUAL" in p.stdout and "token-mismatch" in p.stdout


def test_cli_comment_only_exits_3(tmp_path):
    p = _cli(tmp_path, [LOOP], new=NEW.replace("    # count one plan\n", ""))
    assert p.returncode == 3
    assert "comment removed" in p.stdout


def test_cli_unreadable_spec_exits_2(tmp_path):
    cmd = [sys.executable, str(TOOL), str(tmp_path / "missing.json")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert p.returncode == 2


# ---------------------------------------------------------------------------
# R's conditions M1 to M8 (R_PHASE0 section 6): one planted bad case each,
# which must exit nonzero, and a clean twin. The E numbers are R's cases
# (15 Nov: review/phase0/NOTES_move_check.md and mc_probe.py; 20 Nov:
# R_PHASE0 section 1.3).
# ---------------------------------------------------------------------------

def d(text):
    return textwrap.dedent(text).lstrip("\n")


def mv(eid, old_file, old_q, new_file, new_q, **kw):
    e = {"id": eid, "kind": "move", "phase": "P2",
         "old": {"file": old_file, "qualname": old_q},
         "new": {"file": new_file, "qualname": new_q}}
    e.update(kw)
    return e


def cut(eid, old_q, start, end, new_q, old_file="a.py", new_file="a.py",
        **kw):
    e = {"id": eid, "kind": "cut", "phase": "P4",
         "old": {"file": old_file, "qualname": old_q,
                 "start_anchor": start, "end_anchor": end},
         "new": {"file": new_file, "qualname": new_q}}
    e.update(kw)
    return e


def rules(r):
    return set(r.rules_failed)


# --- M1: the whole-file account -------------------------------------------

E1_OLD = d("""
    def f(x):
        return x + 1


    def g(x):
        return x * 2
    """)
E1_B = d("""
    def f(x):
        return x + 1
    """)


def test_m1_e1_move_with_another_function_changed_is_outside(tmp_path):
    new_a = d("""
        def g(x):
            return x * 3
        """)
    rs = run([mv("E1", "a.py", "f", "b.py", "f")], {"a.py": E1_OLD},
             {"a.py": new_a, "b.py": E1_B}, tmp_path, state=None)
    assert one(rs).status == "clean"
    acc = accounts(rs)
    assert acc["a.py"].status == "review"
    assert any("x * 2" in o and "x * 3" in o for o in acc["a.py"].outside)
    assert acc["b.py"].status == "clean"
    assert mc.exit_code(rs) == 3


def test_m1_e1_twin_move_alone_is_clean(tmp_path):
    new_a = d("""
        def g(x):
            return x * 2
        """)
    rs = run([mv("E1", "a.py", "f", "b.py", "f")], {"a.py": E1_OLD},
             {"a.py": new_a, "b.py": E1_B}, tmp_path, state=None)
    assert [r.status for r in rs] == ["clean"] * 3
    assert mc.exit_code(rs) == 0


E2_OLD = d("""
    def main(n):
        print("a", n)
        print("b", n)
        print("done")
        return n
    """)


def test_m1_e2_cut_with_a_statement_dropped_and_no_call_is_outside(tmp_path):
    new = d("""
        def step(n):
            print("a", n)
            print("b", n)


        def main(n):
            return n
        """)
    rs = run([cut("E2", "main", 'print("a"', 'print("b"', "step")],
             {"a.py": E2_OLD}, {"a.py": new}, tmp_path, state=None)
    assert one(rs).status == "clean"
    acc = accounts(rs)["a.py"]
    assert any('print("done")' in o and "only in old" in o for o in acc.outside)
    assert mc.exit_code(rs) == 3


def test_m1_e2_twin_the_call_alone_is_printed(tmp_path):
    new = d("""
        def step(n):
            print("a", n)
            print("b", n)


        def main(n):
            step(n)
            print("done")
            return n
        """)
    rs = run([cut("E2", "main", 'print("a"', 'print("b"', "step")],
             {"a.py": E2_OLD}, {"a.py": new}, tmp_path, state=None)
    assert one(rs).status == "clean"
    acc = accounts(rs)["a.py"]
    # the call that replaces the cut is the one line R reads
    assert len(acc.outside) == 1 and "step(n)" in acc.outside[0]
    assert "only in new" in acc.outside[0] and 'print("done")' not in acc.outside[0]


def test_m1_account_files_take_a_file_no_entry_names(tmp_path):
    other_old = "import os\nLIMIT = 3\n"
    for other_new, status in (("import os\nLIMIT = 4\n", "review"),
                              (other_old, "clean")):
        rs = run([mv("E1", "a.py", "f", "b.py", "f")],
                 {"a.py": E1_OLD, "c.py": other_old},
                 {"a.py": d("""
                     def g(x):
                         return x * 2
                     """), "b.py": E1_B, "c.py": other_new},
                 tmp_path, state=None, extra={"account_files": ["c.py"]})
        assert accounts(rs)["c.py"].status == status


def test_m1_cli_exits_3_and_prints_outside(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "new").mkdir()
    (tmp_path / "old" / "a.py").write_text(E1_OLD, encoding="utf-8")
    (tmp_path / "new" / "a.py").write_text("def g(x):\n    return x * 3\n",
                                           encoding="utf-8")
    (tmp_path / "new" / "b.py").write_text(E1_B, encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_version": 1, "entries": [
        mv("E1", "a.py", "f", "b.py", "f")]}), encoding="utf-8")
    mp = tmp_path / "MIGRATION_MAP.tsv"
    p = subprocess.run([sys.executable, str(TOOL), str(spec),
                        "--old-root", str(tmp_path / "old"),
                        "--new-root", str(tmp_path / "new"), "--map", str(mp)],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    print(p.stdout, p.stderr)
    assert p.returncode == 3
    assert "account a.py" in p.stdout and "OUTSIDE" in p.stdout
    # the accounts are no rows of MIGRATION_MAP.tsv
    assert len(mp.read_text(encoding="utf-8").splitlines()) == 2


# --- M2: every comment of a touched file matched or residual ---------------

E10A_OLD = d("""
    def f(x):
        y = x + 1
        return y
        # the end of f: y is never None here


    def g():
        return 0
    """)


def test_m2_e10a_trailing_comment_of_a_moved_def_dropped(tmp_path):
    rs = run([mv("E10a", "a.py", "f", "b.py", "f")], {"a.py": E10A_OLD},
             {"a.py": "def g():\n    return 0\n",
              "b.py": "def f(x):\n    y = x + 1\n    return y\n"},
             tmp_path, state=None)
    r = one(rs)
    assert r.status == "review" and not r.code_residual
    assert any("removed" in c and "never None" in c for c in r.comment_residual)
    assert mc.exit_code(rs) == 3


def test_m2_e10a_twin_trailing_comment_kept_is_clean(tmp_path):
    rs = run([mv("E10a", "a.py", "f", "b.py", "f")], {"a.py": E10A_OLD},
             {"a.py": "def g():\n    return 0\n",
              "b.py": "def f(x):\n    y = x + 1\n    return y\n"
                      "    # the end of f: y is never None here\n"},
             tmp_path, state=None)
    assert [r.status for r in rs] == ["clean"] * 3
    assert mc.exit_code(rs) == 0


E10B_OLD = d("""
    def main(n):
        if n:
            print("a", n)
            print("b", n)
            # the end of the n branch
        return n
    """)


def e10b_new(trailing):
    return ("def step(n):\n    print(\"a\", n)\n    print(\"b\", n)\n"
            + ("    # the end of the n branch\n" if trailing else "")
            + "\n\ndef main(n):\n    if n:\n        step(n)\n    return n\n")


def test_m2_e10b_comment_ending_the_cut_block_dropped(tmp_path):
    rs = run([cut("E10b", "main", 'print("a"', 'print("b"', "step")],
             {"a.py": E10B_OLD}, {"a.py": e10b_new(False)}, tmp_path,
             state=None)
    r = one(rs)
    assert r.status == "review"
    assert any("removed" in c and "end of the n branch" in c
               for c in r.comment_residual)


def test_m2_e10b_twin_kept_at_the_end_of_the_new_function(tmp_path):
    rs = run([cut("E10b", "main", 'print("a"', 'print("b"', "step")],
             {"a.py": E10B_OLD}, {"a.py": e10b_new(True)}, tmp_path,
             state=None)
    assert one(rs).status == "clean"
    acc = accounts(rs)["a.py"]
    assert not acc.comment_residual          # the comment is the entry's
    assert len(acc.outside) == 1 and "step(n)" in acc.outside[0]


def test_m2_a_comment_leading_the_next_statement_is_not_the_cuts(tmp_path):
    old = d("""
        def main(n):
            print("a", n)
            # about the return
            return n
        """)
    new = ("def step(n):\n    print(\"a\", n)\n\n\n"
           "def main(n):\n    step(n)\n    # about the return\n    return n\n")
    rs = run([cut("lead", "main", 'print("a"', 'print("a"', "step")],
             {"a.py": old}, {"a.py": new}, tmp_path, state=None)
    assert one(rs).status == "clean"
    assert not accounts(rs)["a.py"].comment_residual


E11_OLD = d("""
    import os

    # narration: why f joins one fixed part
    # (one blank line below)

    def f(x):
        return os.path.join(x, "a")
    """)


def test_m2_e11_comment_block_a_blank_line_above_a_moved_def_dropped(tmp_path):
    rs = run([mv("E11", "a.py", "f", "b.py", "f")], {"a.py": E11_OLD},
             {"a.py": "import os\n",
              "b.py": "import os\n\n\ndef f(x):\n    return os.path.join(x, \"a\")\n"},
             tmp_path, state=None)
    r = one(rs)
    assert r.status == "review"
    assert sum("comment removed" in c for c in r.comment_residual) == 2
    assert mc.exit_code(rs) == 3


def test_m2_e11_twin_block_kept_a_blank_line_above_the_new_def(tmp_path):
    rs = run([mv("E11", "a.py", "f", "b.py", "f")], {"a.py": E11_OLD},
             {"a.py": "import os\n", "b.py": E11_OLD}, tmp_path, state=None)
    r = one(rs)
    assert r.status == "clean", r.comment_residual
    # b.py's `import os` is the one line outside the entries
    acc = accounts(rs)
    assert acc["a.py"].status == "clean"
    assert not acc["b.py"].comment_residual


def test_m2_a_comment_no_entry_owns_is_the_accounts(tmp_path):
    old = "import os\n# a module note\nLIMIT = 3\n\n\n" + E1_OLD
    for note, status in (("# a module note, changed\n", "review"),
                         ("# a module note\n", "clean")):
        new_a = "import os\n" + note + "LIMIT = 3\n\n\ndef g(x):\n    return x * 2\n"
        rs = run([mv("E1", "a.py", "f", "b.py", "f")], {"a.py": old},
                 {"a.py": new_a, "b.py": E1_B}, tmp_path, state=None)
        acc = accounts(rs)["a.py"]
        assert acc.status == status
        if status == "review":
            assert any("a module note" in c for c in acc.comment_residual)


# --- M3: disjoint spans, one home per new function --------------------------

def test_m3_e6_one_old_function_to_two_homes(tmp_path):
    rs = run([mv("E6a", "a.py", "f", "b.py", "f"),
              mv("E6b", "a.py", "f", "c.py", "f")],
             {"a.py": E1_B}, {"a.py": "", "b.py": E1_B, "c.py": E1_B},
             tmp_path, state=None)
    ents = mc.entry_results(rs)
    assert all("spans-overlap" in rules(r) for r in ents)
    assert mc.exit_code(rs) == 1


def test_m3_two_entries_one_new_function(tmp_path):
    rs = run([mv("Ef", "a.py", "f", "b.py", "f"),
              mv("Eg", "a.py", "g", "b.py", "f")],
             {"a.py": E1_OLD}, {"a.py": "", "b.py": E1_B}, tmp_path, state=None)
    assert all("new-home-shared" in rules(r) for r in mc.entry_results(rs))


def test_m3_twin_two_functions_two_homes(tmp_path):
    rs = run([mv("Ef", "a.py", "f", "b.py", "f"),
              mv("Eg", "a.py", "g", "c.py", "g")],
             {"a.py": E1_OLD},
             {"a.py": "", "b.py": E1_B, "c.py": "def g(x):\n    return x * 2\n"},
             tmp_path, state=None)
    assert [r.status for r in rs] == ["clean"] * 5
    assert mc.exit_code(rs) == 0


# --- M4: a mapped name is a local of the old container --------------------

E3_OLD = d("""
    args = None


    def main():
        limit = 3
        if args is not None:
            limit = args.limit
        return limit
    """)


def test_m4_e3_a_module_global_mapped_to_a_field(tmp_path):
    new = d("""
        args = None


        def pick_limit(st):
            limit = 3
            if st.setup.args is not None:
                limit = st.setup.args.limit
            return limit


        def main():
            return pick_limit(None)
        """)
    rs = run([cut("E3", "main", "limit = 3", "return limit", "pick_limit",
                  name_map={"args": "st.setup.args"})],
             {"a.py": E3_OLD}, {"a.py": new}, tmp_path)
    r = one(rs)
    assert "map-not-local" in rules(r)
    assert any("'args'" in m and "global" in m for _r, m in r.errors)


def test_m4_a_builtin_mapped_to_a_field(tmp_path):
    old = "def main(n):\n    print(n)\n    print(n)\n"
    new = ("def step(st, n):\n    st.setup.print(n)\n    st.setup.print(n)\n\n\n"
           "def main(n):\n    step(None, n)\n")
    # print(n) is on two lines: the anchors name the occurrences
    e = cut("B", "main", "print(n)", "print(n)", "step",
            name_map={"print": "st.setup.print"})
    e["old"]["start_occurrence"], e["old"]["end_occurrence"] = 1, 2
    r = one(run([e], {"a.py": old}, {"a.py": new}, tmp_path))
    assert "map-not-local" in rules(r)


F4X_OLD = d("""
    def first(n):
        plan_count = 0
        plan_count += n
        return 1


    def second(n):
        plan_count = 0
        plan_count += n
        return 2
    """)
F4X_NEW = d("""
    def bump1(st, n):
        st.counts.plan_count += n


    def bump2(st, n):
        st.counts.plan_count += n


    def first(n):
        plan_count = 0
        bump1(None, n)
        return 1


    def second(n):
        plan_count = 0
        bump2(None, n)
        return 2
    """)


def test_m4_f4x_two_locals_of_two_functions_to_one_field(tmp_path):
    m = {"plan_count": "st.counts.plan_count"}
    rs = run([cut("F1", "first", "plan_count += n", "plan_count += n",
                  "bump1", name_map=m),
              cut("F2", "second", "plan_count += n", "plan_count += n",
                  "bump2", name_map=m)],
             {"a.py": F4X_OLD}, {"a.py": F4X_NEW}, tmp_path)
    ents = mc.entry_results(rs)
    assert all("map-field-two-scopes" in rules(r) for r in ents)
    assert mc.exit_code(rs) == 1


def test_m4_twin_a_closure_nonlocal_is_owned_by_its_function(tmp_path):
    rs = run([LOOP, FINISH], old_files={"old.py": OLD},
             new_files={"new.py": NEW}, tmp_path=tmp_path)
    ents = mc.entry_results(rs)
    assert [r.status for r in ents] == ["clean", "clean"]
    assert ents[0].map_owners["st.ending.exit_reason"] == ("exit_reason", "old.py:main")
    assert ents[1].map_owners["st.ending.exit_reason"] == ("exit_reason", "old.py:main")


# --- M5: the state classes are named and declare every mapped field --------

E7_OLD = d("""
    def main():
        plan_count = 0
        plan_count += 1
        return plan_count
    """)
E7_NEW = d("""
    def bump(st):
        st.counts.plan_count += 1


    def main():
        return 0
    """)
E7_ENTRY = cut("E7", "main", "plan_count += 1", "plan_count += 1", "bump",
               name_map={"plan_count": "st.counts.plan_count"})


def test_m5_e7_mapped_field_the_state_class_does_not_declare(tmp_path):
    state_py = STATE_PY.replace("    plan_count: int = 0\n",
                                "    plan_total: int = 0\n")
    r = one(run([E7_ENTRY], {"a.py": E7_OLD},
                {"a.py": E7_NEW, "state.py": state_py}, tmp_path))
    assert "map-field-not-declared" in rules(r)


def test_m5_spec_without_state_classes(tmp_path):
    r = one(run([E7_ENTRY], {"a.py": E7_OLD}, {"a.py": E7_NEW}, tmp_path,
                state=None))
    assert "state-classes-not-named" in rules(r)


def test_m5_group_without_a_class(tmp_path):
    state = {"file": "state.py", "groups": {"ending": "Ending"}}
    r = one(run([E7_ENTRY], {"a.py": E7_OLD}, {"a.py": E7_NEW}, tmp_path,
                state=state))
    assert "map-field-not-declared" in rules(r)


def test_m5_twin_declared_field_is_clean(tmp_path):
    r = one(run([E7_ENTRY], {"a.py": E7_OLD}, {"a.py": E7_NEW}, tmp_path))
    assert r.status == "clean", r.errors


# --- M7: cuts ----------------------------------------------------------------

E8_OLD = d("""
    def main(n):
        total = n
        label = str(n)
        total += 1
        print(label)
        return total
    """)


def test_m7_e8_live_out_local(tmp_path):
    new = d("""
        def step(n):
            label = str(n)


        def main(n):
            total = n
            step(n)
            total += 1
            print(label)
            return total
        """)
    rs = run([cut("E8", "main", "label = str(n)", "label = str(n)", "step")],
             {"a.py": E8_OLD}, {"a.py": new}, tmp_path, state=None)
    r = one(rs)
    assert "live-out-local" in rules(r)
    assert any("'label'" in m and "5" in m for _r, m in r.errors)
    assert mc.exit_code(rs) == 1


def test_m7_e8_twin_a_local_not_read_after_the_span(tmp_path):
    old = E8_OLD.replace("    print(label)\n", "")
    new = ("def step(n):\n    label = str(n)\n\n\n"
           "def main(n):\n    total = n\n    step(n)\n    total += 1\n"
           "    return total\n")
    r = one(run([cut("E8", "main", "label = str(n)", "label = str(n)", "step")],
                {"a.py": old}, {"a.py": new}, tmp_path, state=None))
    assert r.status == "clean", r.errors


LOOP_CARRY_OLD = d("""
    def main(items):
        note = ""
        for x in items:
            print(note)
            note = str(x)
        return 0
    """)


def test_m7_live_out_through_the_loop_around_the_span(tmp_path):
    new = ("def step(x):\n    note = str(x)\n\n\n"
           "def main(items):\n    note = \"\"\n    for x in items:\n"
           "        print(note)\n        step(x)\n    return 0\n")
    r = one(run([cut("L", "main", "note = str(x)", "note = str(x)", "step")],
                {"a.py": LOOP_CARRY_OLD}, {"a.py": new}, tmp_path, state=None))
    assert "live-out-local" in rules(r)


def test_m7_twin_a_read_before_the_span_outside_any_loop(tmp_path):
    old = d("""
        def main(items):
            note = ""
            print(note)
            note = str(items)
            return 0
        """)
    new = ("def step(items):\n    note = str(items)\n\n\n"
           "def main(items):\n    note = \"\"\n    print(note)\n"
           "    step(items)\n    return 0\n")
    r = one(run([cut("L", "main", "note = str(items)", "note = str(items)",
                     "step")], {"a.py": old}, {"a.py": new}, tmp_path,
                state=None))
    assert r.status == "clean", r.errors


def test_m7_live_out_through_a_closure(tmp_path):
    old = d("""
        def main(n):
            def show():
                return label
            label = str(n)
            return show()
        """)
    new = ("def step(n):\n    label = str(n)\n\n\n"
           "def main(n):\n    def show():\n        return label\n"
           "    step(n)\n    return show()\n")
    r = one(run([cut("C", "main", "label = str(n)", "label = str(n)", "step")],
                {"a.py": old}, {"a.py": new}, tmp_path, state=None))
    assert "live-out-local" in rules(r)


def test_m7_e9_span_binds_a_name_declared_global_outside(tmp_path):
    old = d("""
        COUNTER = 0


        def main(n):
            global COUNTER
            print(n)
            COUNTER = n
            return 0
        """)
    new = ("COUNTER = 0\n\n\ndef step(n):\n    COUNTER = n\n\n\n"
           "def main(n):\n    global COUNTER\n    print(n)\n    step(n)\n"
           "    return 0\n")
    r = one(run([cut("E9", "main", "COUNTER = n", "COUNTER = n", "step")],
                {"a.py": old}, {"a.py": new}, tmp_path, state=None))
    assert "span-binds-global" in rules(r)


def test_m7_e9_twin_without_the_global(tmp_path):
    old = "def main(n):\n    print(n)\n    counter = n\n    return 0\n"
    new = ("def step(n):\n    counter = n\n\n\n"
           "def main(n):\n    print(n)\n    step(n)\n    return 0\n")
    r = one(run([cut("E9", "main", "counter = n", "counter = n", "step")],
                {"a.py": old}, {"a.py": new}, tmp_path, state=None))
    assert r.status == "clean", r.errors


E17_OLD = d("""
    def main(items):
        for x in items:
            if x is None:
                return False
            if x == 0:
                break
            if x < 0:
                return None
        return True
    """)


def e17(names):
    new = ("BREAK = object()\nEARLY = object()\nNONE_OUT = object()\n\n\n"
           "def check(x):\n    if x is None:\n        return {f}\n"
           "    if x == 0:\n        return {b}\n    if x < 0:\n"
           "        return {n}\n").format(f=names[0], b=names[1], n=names[2])
    entry = cut("E17", "main", "if x is None:", "if x < 0:", "check",
                break_sentinel=names[1],
                sentinel_returns={"False": names[0], "None": names[2]})
    return entry, new


def test_m7_e17_three_ways_out_to_one_sentinel(tmp_path):
    entry, new = e17(["BREAK", "BREAK", "BREAK"])
    r = one(run([entry], {"a.py": E17_OLD}, {"a.py": new}, tmp_path,
                state=None))
    assert "sentinels-not-distinct" in rules(r)
    assert not r.code_residual


def test_m7_e17_twin_three_distinct_sentinels(tmp_path):
    entry, new = e17(["EARLY", "BREAK", "NONE_OUT"])
    r = one(run([entry], {"a.py": E17_OLD}, {"a.py": new}, tmp_path,
                state=None))
    assert r.status == "clean", (r.errors, r.code_residual)


@pytest.mark.parametrize("header, what", [
    ("@staticmethod\ndef step(n):", "decorators"),
    ("def step(n=1):", "default of 'n'"),
    ("async def step(n):", "async"),
    ("def step(n) -> int:", "return annotation"),
    ("def step(n: int):", "annotation of 'n'"),
])
def test_m7_cut_header_carries_more_than_def_name_params(tmp_path, header,
                                                         what):
    new = (header + '\n    print("a", n)\n    print("b", n)\n\n\n'
           'def main(n):\n    step(n)\n    print("done")\n    return n\n')
    r = one(run([cut("H", "main", 'print("a"', 'print("b"', "step")],
                {"a.py": E2_OLD}, {"a.py": new}, tmp_path, state=None))
    assert "cut-header" in rules(r)
    assert any(what in m for rule, m in r.errors if rule == "cut-header")


def test_m7_cut_header_twin_plain_header_is_clean(tmp_path):
    new = ('def step(n):\n    print("a", n)\n    print("b", n)\n\n\n'
           'def main(n):\n    step(n)\n    print("done")\n    return n\n')
    r = one(run([cut("H", "main", 'print("a"', 'print("b"', "step")],
                {"a.py": E2_OLD}, {"a.py": new}, tmp_path, state=None))
    assert r.status == "clean", r.errors


def test_m7_whole_body_cut_keeps_the_old_header_parts_only(tmp_path):
    # FINISH is a whole closure body: `def _finish(st, label):` is clean
    # (test_clean_closure_cut_drops_nonlocal); a default the closure did
    # not have is not
    new = NEW.replace("def _finish(st, label):", "def _finish(st, label='x'):")
    r = syn(tmp_path, FINISH, new=new)
    assert "cut-header" in rules(r)


# --- M8: class-bound names, and the span's Name loads ----------------------

E4_OLD = d("""
    class Env:
        def __init__(self):
            self.__count = 0

        def bump(self):
            self.__count += 1
            return self.__count
    """)


def test_m8_e4_private_attribute_moved_to_another_class(tmp_path):
    new_b = "class Placement:\n    def bump(self):\n        self.__count += 1\n        return self.__count\n"
    r = one(run([mv("E4", "a.py", "Env.bump", "b.py", "Placement.bump")],
                {"a.py": E4_OLD},
                {"a.py": "class Env:\n    def __init__(self):\n        self.__count = 0\n",
                 "b.py": new_b}, tmp_path, state=None))
    assert "class-bound-name" in rules(r)


@pytest.mark.parametrize("body", ["return super().bump()",
                                  "return __class__.__name__"])
def test_m8_super_and_class_cell_moved_to_another_class(tmp_path, body):
    old = f"class Env:\n    def bump(self):\n        {body}\n"
    r = one(run([mv("S", "a.py", "Env.bump", "b.py", "Placement.bump")],
                {"a.py": old},
                {"a.py": "class Env:\n    pass\n",
                 "b.py": f"class Placement:\n    def bump(self):\n        {body}\n"},
                tmp_path, state=None))
    assert "class-bound-name" in rules(r)


def test_m8_twin_method_without_class_bound_names(tmp_path):
    old = "class Env:\n    def bump(self):\n        self.count += 1\n        return self.count\n"
    r = one(run([mv("S", "a.py", "Env.bump", "b.py", "Placement.bump")],
                {"a.py": old},
                {"a.py": "class Env:\n    pass\n",
                 "b.py": "class Placement:\n    def bump(self):\n        self.count += 1\n        return self.count\n"},
                tmp_path, state=None))
    assert "class-bound-name" not in rules(r)
    assert not r.code_residual


def test_m8_item6_an_attribute_spelling_is_no_global_read(tmp_path):
    # the old span spells LIMIT only as an attribute; the old function reads
    # the global LIMIT elsewhere. A new body reading the bare global LIMIT
    # is a free-name failure now (before item 6 the NAME token passed it).
    old = d("""
        LIMIT = 3


        def main(cfg):
            print(LIMIT)
            n = cfg.LIMIT
            print(n)
            return 0
        """)
    new = ("LIMIT = 3\n\n\ndef step(cfg):\n    n = LIMIT\n    print(n)\n\n\n"
           "def main(cfg):\n    print(LIMIT)\n    step(cfg)\n    return 0\n")
    r = one(run([cut("I6", "main", "n = cfg.LIMIT", "print(n)", "step")],
                {"a.py": old}, {"a.py": new}, tmp_path, state=None))
    assert any("'LIMIT'" in m for rule, m in r.errors if rule == "free-name")