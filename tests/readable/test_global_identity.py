"""Tests of tools/readable/global_identity.py: the identity half of pin 44
(PLAN 5.2 row 44, REVIEW_PHASE0 B4).

Nothing of the pipeline has moved yet, so the check runs on synthetic old
and new module pairs written into a temp folder: one new module that
imports the globals of the moved function from the old one (passes), and
ones that re-create an instance (a lock object, a registry dict) instead of
importing it (fail). No pybullet, no pipeline import; Windows and WSL.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "readable" / "global_identity.py"
sys.path.insert(0, str(TOOL.parent))
import global_identity as gi  # noqa: E402
import move_check as mc  # noqa: E402

OLDMOD = textwrap.dedent('''\
    """The old module: a lock object, a registry and the function to move."""
    import os
    import threading


    class RenderingLock:
        def __init__(self):
            self.lock = threading.Lock()


    RENDER_LOCK = RenderingLock()
    REGISTRY = {}
    COUNT = 0


    def helper(x):
        return x.upper()


    def draw(name):
        with RENDER_LOCK.lock:
            REGISTRY[name] = os.path.join(name, str(len(name)))
        return [helper(c) for c in name]


    def bump():
        global COUNT
        COUNT += 1
    ''')

DRAW = textwrap.dedent('''\


    def draw(name):
        with RENDER_LOCK.lock:
            REGISTRY[name] = os.path.join(name, str(len(name)))
        return [helper(c) for c in name]
    ''')

# imports every global the moved function reads: passes
NEW_GOOD = "import os\nfrom oldmod import RENDER_LOCK, REGISTRY, helper\n" + DRAW
# re-creates the lock instance instead of importing it: fails on RENDER_LOCK
NEW_LOCK = ("import os\nfrom oldmod import RenderingLock, REGISTRY, helper\n\n"
            "RENDER_LOCK = RenderingLock()\n" + DRAW)
# re-creates the registry: fails on REGISTRY
NEW_REGISTRY = ("import os\nfrom oldmod import RENDER_LOCK, helper\n\n"
                "REGISTRY = {}\n" + DRAW)
# forgets an import: the global is not bound in the new module
NEW_MISSING = "import os\nfrom oldmod import RENDER_LOCK, REGISTRY\n" + DRAW
# moves bump(), which rebinds COUNT through `global`
NEW_BUMP = "from oldmod import COUNT\n\n\ndef bump():\n    global COUNT\n    COUNT += 1\n"


def row(new_file, new_qualname="draw", old_qualname="draw", kind="move",
        old_file="oldmod.py", entry=None):
    return {"old_file": old_file, "old_qualname": old_qualname,
            "new_file": new_file, "new_qualname": new_qualname, "phase": "P2",
            "kind": kind, "old_lines": "1-2", "new_lines": "3-4",
            "entry": entry or f"e-{new_file}", "status": "clean"}


@pytest.fixture
def tree(tmp_path):
    files = {"oldmod.py": OLDMOD, "newmod_good.py": NEW_GOOD,
             "newmod_lock.py": NEW_LOCK, "newmod_registry.py": NEW_REGISTRY,
             "newmod_missing.py": NEW_MISSING, "newmod_bump.py": NEW_BUMP}
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_globals_read_takes_nested_scopes_and_builtins():
    read, declared = gi.globals_read(OLDMOD, "oldmod.py", "draw")
    # the comprehension's helper is read too; `name`, `c` are locals
    assert read == ["REGISTRY", "RENDER_LOCK", "helper", "len", "os", "str"]
    assert declared == []
    read_b, declared_b = gi.globals_read(OLDMOD, "oldmod.py", "bump")
    assert read_b == ["COUNT"] and declared_b == ["COUNT"]
    meth = gi.globals_read(OLDMOD, "oldmod.py", "RenderingLock.__init__")
    assert meth == (["threading"], [])
    with pytest.raises(gi.MapError):
        gi.globals_read(OLDMOD, "oldmod.py", "nothere")


def test_module_name():
    assert gi.module_name("boxel_env.py") == "boxel_env"
    assert gi.module_name("tampura_bridge/policy.py") == "tampura_bridge.policy"
    assert gi.module_name("tampura_bridge\\__init__.py") == "tampura_bridge"


def test_imported_globals_are_the_same_objects(tree):
    (res,) = gi.check_rows([row("newmod_good.py")], tree)
    print(gi.format_results([res]))
    assert res["ok"], res
    assert res["globals"] == {g: "same" for g in
                              ["REGISTRY", "RENDER_LOCK", "helper", "len", "os", "str"]}


def test_recreated_lock_instance_fails(tree):
    (res,) = gi.check_rows([row("newmod_lock.py")], tree)
    print(gi.format_results([res]))
    assert not res["ok"]
    assert res["globals"]["RENDER_LOCK"].startswith("different objects: old RenderingLock")
    assert {g for g, v in res["globals"].items() if v != "same"} == {"RENDER_LOCK"}


def test_recreated_registry_fails(tree):
    (res,) = gi.check_rows([row("newmod_registry.py")], tree)
    assert not res["ok"]
    assert {g for g, v in res["globals"].items() if v != "same"} == {"REGISTRY"}


def test_global_not_bound_in_the_new_module_fails(tree):
    (res,) = gi.check_rows([row("newmod_missing.py")], tree)
    assert not res["ok"] and res["globals"]["helper"] == "not bound in the new module"


def test_declared_global_fails(tree):
    (res,) = gi.check_rows([row("newmod_bump.py", "bump", "bump")], tree)
    assert not res["ok"]
    assert res["globals"]["COUNT"].startswith("declared global")


def test_rows_go_through_one_interpreter_and_same_file_rows_are_skipped(tree):
    rows = [row("newmod_good.py"), row("newmod_lock.py"),
            row("oldmod.py", kind="cut", entry="same-file"),        # not cross-file
            {**row("newmod_good.py", entry="del"), "kind": "delete"}]
    res = gi.check_rows(rows, tree)
    assert [r["entry"] for r in res] == ["e-newmod_good.py", "e-newmod_lock.py"]
    assert [r["ok"] for r in res] == [True, False]


def test_missing_function_or_module_is_an_error(tree):
    res = gi.check_rows([row("newmod_good.py", new_qualname="nothere", entry="a"),
                         row("newmod_nofile.py", entry="b")], tree)
    assert [r["ok"] for r in res] == [False, False]
    assert all(r["error"] for r in res)


def _write_map(path, rows):
    path.write_text("\t".join(gi.MAP_HEADER) + "\n"
                    + "".join("\t".join(r[k] for k in gi.MAP_HEADER) + "\n" for r in rows),
                    encoding="utf-8")


def test_map_header_is_move_checks():
    assert gi.MAP_HEADER == mc.MAP_HEADER


def test_cli_exit_codes(tree):
    def cli(*args):
        p = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True,
                           text=True, timeout=300, cwd=str(tree))
        print(p.stdout, p.stderr)
        return p
    good, bad = tree / "good.tsv", tree / "bad.tsv"
    _write_map(good, [row("newmod_good.py")])
    _write_map(bad, [row("newmod_good.py"), row("newmod_lock.py")])
    p = cli("--map", str(good), "--root", str(tree), "--json", str(tree / "out.json"))
    assert p.returncode == 0 and "OK" in p.stdout
    assert json.loads((tree / "out.json").read_text(encoding="utf-8"))[0]["ok"] is True
    p = cli("--map", str(bad), "--root", str(tree))
    assert p.returncode == 1 and "DIFFERS RENDER_LOCK" in p.stdout
    (tree / "broken.tsv").write_text("not a header\n", encoding="utf-8")
    assert cli("--map", str(tree / "broken.tsv")).returncode == 2
    empty = tree / "empty.tsv"
    _write_map(empty, [])
    p = cli("--map", str(empty), "--root", str(tree))
    assert p.returncode == 0 and "nothing to check" in p.stdout


def test_move_check_map_feeds_the_identity_check(tmp_path):
    """move_check --map writes the row; the new checkout's old module takes
    the moved name back by import (rule 11) and the check reads that map."""
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "oldmod.py").write_text(OLDMOD, encoding="utf-8")
    new_old = OLDMOD.split("\n\ndef draw(name):")[0] + textwrap.dedent('''\


        def bump():
            global COUNT
            COUNT += 1


        from newmod import draw  # noqa: E402  (rule 11: the old name stays)
        ''')
    (new / "oldmod.py").write_text(new_old, encoding="utf-8")
    (new / "newmod.py").write_text(NEW_GOOD, encoding="utf-8")
    spec = {"spec_version": 1, "entries": [
        {"id": "P2-draw", "kind": "move", "phase": "P2",
         "old": {"file": "oldmod.py", "qualname": "draw"},
         "new": {"file": "newmod.py", "qualname": "draw"}}]}
    results = mc.run_spec(spec, mc.file_reader(str(old), None, None),
                          mc.file_reader(str(new), None, None))
    assert results[0].status == "clean", mc.format_result(results[0])
    mp = tmp_path / "MIGRATION_MAP.tsv"
    mc.write_map(str(mp), results)
    (res,) = gi.check_rows(gi.read_map(str(mp)), new)
    print(gi.format_results([res]))
    assert res["ok"] and res["globals"]["RENDER_LOCK"] == "same"
    # the same map against a new module that re-creates the lock fails
    (new / "newmod.py").write_text(NEW_LOCK, encoding="utf-8")
    (res2,) = gi.check_rows(gi.read_map(str(mp)), new)
    assert not res2["ok"] and res2["globals"]["RENDER_LOCK"].startswith("different")
