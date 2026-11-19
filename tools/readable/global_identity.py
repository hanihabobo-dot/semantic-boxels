"""global_identity: the identity half of pin 44 (PLAN 5.2 row 44).

For each cross-file row of MIGRATION_MAP.tsv (a `move` or `cut` whose new
file is not its old file) it finds every global the moved function reads
(symtable of the new file: the function's table and every table nested in
it, builtins resolved as at run time) and, in ONE child interpreter that
imports the old and the new module, checks that

    new.__dict__[g] is old.__dict__[g]

for every such global g. A module-level instance re-created in the new
module instead of imported (a `RenderingLock()`, a registry dict, a cache)
describes the same in pin 44's table but is a second object: that is the
failure this check exists for (REVIEW_PHASE0 B4). It also fails a global
the moved function declares `global` (a rebinding would no longer reach the
old module's name), a global neither module binds, and a row whose module
or function cannot be found.

Limits: `is` on an immutable value (a small int, an interned string) can
hold although the constant was written twice; twin constants are pin 48's.
Decorators, defaults and annotations of the def are read at module level,
not by the function, and are not listed.

Run (in WSL under the pipeline lock when the modules import pybullet):

  python tools/readable/global_identity.py --map tools/readable/MIGRATION_MAP.tsv \
      [--root .] [--json OUT.json]

Exit codes: 0 every global is the same object (or no cross-file row);
1 a global differs or a row failed; 2 the map could not be read.
"""
from __future__ import annotations

import argparse
import builtins
import json
import os
import subprocess
import symtable
import sys
from pathlib import Path

MAP_HEADER = ["old_file", "old_qualname", "new_file", "new_qualname",
              "phase", "kind", "old_lines", "new_lines", "entry", "status"]


class MapError(Exception):
    pass


def module_name(file: str) -> str:
    """`tampura_bridge/policy.py` -> `tampura_bridge.policy`."""
    p = file.replace("\\", "/")
    if not p.endswith(".py"):
        raise MapError(f"{file!r} is not a .py file")
    p = p[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def read_map(path: str) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MapError(f"{path}: {exc}") from exc
    if not lines or lines[0].split("\t") != MAP_HEADER:
        raise MapError(f"{path}: the first line is not move_check's MAP_HEADER")
    rows = []
    for k, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) != len(MAP_HEADER):
            raise MapError(f"{path}:{k}: {len(cols)} columns, not {len(MAP_HEADER)}")
        rows.append(dict(zip(MAP_HEADER, cols)))
    return rows


def cross_file_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["kind"] in ("move", "cut")
            and r["new_file"] and r["new_file"] != r["old_file"]]


def _find_table(top: symtable.SymbolTable, qualname: str) -> symtable.SymbolTable:
    tab = top
    for part in qualname.split("."):
        found = [c for c in tab.get_children() if c.get_name() == part
                 and c.get_type() in ("function", "class")]
        if not found:
            raise MapError(f"{qualname!r}: no {part!r} in {tab.get_name()!r}")
        if len(found) > 1:
            raise MapError(f"{qualname!r}: {part!r} is defined {len(found)} times")
        tab = found[0]
    if tab.get_type() != "function":
        raise MapError(f"{qualname!r} is not a function")
    return tab


def globals_read(source: str, filename: str, qualname: str) -> tuple[list[str], list[str]]:
    """(globals the function and its nested scopes read, names it declares
    `global`). Builtins stay in: they are resolved in the child as at run
    time (a module binding shadows the builtin)."""
    top = symtable.symtable(source, filename, "exec")
    fn = _find_table(top, qualname)
    read, declared = set(), set()
    stack = [fn]
    while stack:
        tab = stack.pop()
        for sym in tab.get_symbols():
            if sym.is_global():
                if sym.is_referenced() or sym.is_assigned():
                    read.add(sym.get_name())
                if sym.is_declared_global():
                    declared.add(sym.get_name())
        stack.extend(tab.get_children())
    return sorted(read), sorted(declared)


# The child: one interpreter, both modules imported, `is` per global.
_CHILD = r'''
import builtins, importlib, json, sys
root, payload = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, root)
MISSING = object()
out = []
for item in payload:
    res = {"entry": item["entry"], "old_module": item["old_module"],
           "new_module": item["new_module"], "globals": {}, "error": None}
    try:
        old = importlib.import_module(item["old_module"])
        new = importlib.import_module(item["new_module"])
    except BaseException as ex:
        res["error"] = "import: " + type(ex).__name__ + ": " + str(ex)
        out.append(res)
        continue
    for g in item["globals"]:
        a = old.__dict__.get(g, builtins.__dict__.get(g, MISSING))
        b = new.__dict__.get(g, builtins.__dict__.get(g, MISSING))
        if b is MISSING:
            res["globals"][g] = "not bound in the new module"
        elif a is MISSING:
            res["globals"][g] = "not bound in the old module"
        elif a is b:
            res["globals"][g] = "same"
        else:
            res["globals"][g] = ("different objects: old %s, new %s"
                                 % (type(a).__qualname__, type(b).__qualname__))
    out.append(res)
print("@@JSON " + json.dumps(out))
'''


def build_payload(rows: list[dict], root: Path) -> tuple[list[dict], list[dict]]:
    payload, failed = [], []
    for r in rows:
        entry = r["entry"] or f"{r['old_file']}::{r['old_qualname']}"
        try:
            old_mod, new_mod = module_name(r["old_file"]), module_name(r["new_file"])
            path = root / r["new_file"]
            src = path.read_text(encoding="utf-8")
            read, declared = globals_read(src, str(path), r["new_qualname"])
        except (MapError, OSError, SyntaxError) as exc:
            failed.append({"entry": entry, "error": f"{type(exc).__name__}: {exc}",
                           "globals": {}})
            continue
        payload.append({"entry": entry, "old_module": old_mod, "new_module": new_mod,
                        "qualname": r["new_qualname"], "globals": read,
                        "declared_global": declared})
    return payload, failed


def check_rows(rows: list[dict], root: str | os.PathLike, python: str = sys.executable,
               timeout: float = 600) -> list[dict]:
    """The identity check of every cross-file row, in one child interpreter
    (cwd `root`, PYTHONHASHSEED=0, no bytecode written)."""
    root = Path(root).resolve()
    payload, results = build_payload(cross_file_rows(rows), root)
    if payload:
        env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([python, "-c", _CHILD, str(root), json.dumps(payload)],
                           capture_output=True, text=True, cwd=str(root), env=env,
                           timeout=timeout)
        line = next((x for x in p.stdout.splitlines() if x.startswith("@@JSON ")), None)
        if line is None:
            for item in payload:
                results.append({"entry": item["entry"], "globals": {},
                                "error": f"child rc {p.returncode}: {p.stderr[-400:]}"})
        else:
            by_entry = {x["entry"]: x for x in payload}
            for res in json.loads(line[7:]):
                item = by_entry[res["entry"]]
                res["qualname"] = item["qualname"]
                for g in item["declared_global"]:
                    res["globals"][g] = ("declared global: a rebinding in the new "
                                         "module does not reach the old module's name")
                results.append(res)
    for res in results:
        res["ok"] = res.get("error") is None and all(
            v == "same" for v in res["globals"].values())
    return sorted(results, key=lambda x: x["entry"])


def format_results(results: list[dict]) -> str:
    if not results:
        return "no cross-file row in the map: nothing to check"
    lines = []
    for res in results:
        head = (f"entry {res['entry']}: {res.get('old_module', '?')} -> "
                f"{res.get('new_module', '?')}.{res.get('qualname', '?')}")
        lines.append(head + ("  OK" if res["ok"] else "  FAILED"))
        if res.get("error"):
            lines.append(f"  ERROR {res['error']}")
        for g, v in sorted(res["globals"].items()):
            lines.append(f"  {'same' if v == 'same' else 'DIFFERS'} {g}"
                         + ("" if v == "same" else f": {v}"))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--map", required=True, help="MIGRATION_MAP.tsv (move_check --map)")
    ap.add_argument("--root", default=".", help="the checkout holding old and new modules")
    ap.add_argument("--json", help="write the results here")
    a = ap.parse_args(argv)
    try:
        rows = read_map(a.map)
    except MapError as exc:
        print(f"global_identity: {exc}", file=sys.stderr)
        return 2
    results = check_rows(rows, a.root)
    print(format_results(results))
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1, sort_keys=True),
                                encoding="utf-8")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
