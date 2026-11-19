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

def run(entries, old_files=None, new_files=None, tmp_path=None,
        old_root=None):
    old_dir = Path(old_root) if old_root else tmp_path / "old"
    new_dir = tmp_path / "new"
    for d, files in ((old_dir, old_files), (new_dir, new_files)):
        if files:
            d.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                (d / name).write_text(text, encoding="utf-8")
    spec = {"spec_version": 1, "entries": entries}
    return mc.run_spec(spec, mc.file_reader(str(old_dir), None, None),
                       mc.file_reader(str(new_dir), None, None))


def one(results):
    assert len(results) == 1
    print(mc.format_result(results[0]))
    return results[0]


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
    text = real_text("test_full_pipeline.py")
    main_node, _f, _l = def_lines(text, "main")
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
             "old": {"file": "test_full_pipeline.py", "qualname": "main",
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
    assert [r.status for r in rs] == ["clean"] * 3
    assert mc.exit_code(rs) == 0


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
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_version": 1, "entries": [B2_CUT]}),
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
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"spec_version": 1, "entries": entries}),
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
    assert p.returncode == 0
    rows = mp.read_text(encoding="utf-8").splitlines()
    assert rows[0].split("\t") == mc.MAP_HEADER
    assert len(rows) == 4
    assert rows[1].split("\t")[:6] == ["old.py", "main", "new.py",
                                       "run_one_plan", "P6", "cut"]
    assert len(lm.read_text(encoding="utf-8").splitlines()) > 5
    # a second run of one entry replaces its row and keeps the others
    p2 = _cli(tmp_path, [EARLY], extra=("--map", str(mp)))
    assert p2.returncode == 0
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
