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

Rebound names (R's M6, R_PHASE0 section 6). A bare read of `g` in the new
module keeps the value `g` had when the new module bound it; when anything
rebinds `old.g` at run time, the moved reader no longer sees the change
(R's E5). So a global the moved function reads bare FAILS when the tree
under `--root` rebinds it in the old module:
  - a function of the old module that declares `global g` and binds it;
  - `<alias of old>.g = ...` (also `+=`, `del`, a for or with target), in
    any file, the alias taken from that file's imports of the old module;
  - `setattr(<alias>, "g", ...)`, `delattr`, `patch.object(<alias>, "g")`;
    with a name that is not a string constant, every name of the old
    module counts as rebound;
  - a string `"old.g"` as the first argument of `setattr`, `patch` or
    `delattr` (monkeypatch and mock);
  - a call whose first two arguments are the strings `"old"` and `"g"`
    (the gate hooks' `_rebind`), and the pairs of pin 42's `_REBOUND`
    (pin_outputs.py: the names gate_hooks.install replaces).
The correct form, `import old` and a read of `old.g`, is accepted: a
global whose new value IS the old module is "same (the old module, read
through it)", and each attribute the function reads on it must exist in
the old module.

Limits: `is` on an immutable value (a small int, an interned string) can
hold although the constant was written twice; twin constants are pin 48's.
Decorators, defaults and annotations of the def are read at module level,
not by the function, and are not listed. The rebinding scan reads source
text: a rebinding through a computed module (`sys.modules[name]`, a loop
over modules) is not seen unless pin 42's list names it. The scan skips
folders named `archive`, `_scratch`, `__pycache__`, `node_modules`,
`site-packages` and hidden folders.

Run (in WSL under the pipeline lock when the modules import pybullet):

  python tools/readable/global_identity.py --map tools/readable/MIGRATION_MAP.tsv \
      [--root .] [--json OUT.json]

Exit codes: 0 every global is the same object (or no cross-file row);
1 a global differs or a row failed; 2 the map could not be read.
"""
from __future__ import annotations

import argparse
import ast
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


def _find_def(tree: ast.Module, qualname: str) -> ast.AST:
    node: ast.AST = tree
    for part in qualname.split("."):
        found = [c for c in ast.walk(node) if c is not node
                 and isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)) and c.name == part]
        if not found:
            raise MapError(f"{qualname!r}: no def {part!r}")
        node = found[0]
    return node


def attributes_read(source: str, qualname: str) -> dict[str, list[str]]:
    """name -> the attributes the function (with its nested scopes) reads
    or writes on it, `g.attr`: for a global that is a module, the names the
    function reaches through the module."""
    fn = _find_def(ast.parse(source), qualname)
    out: dict[str, set] = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
            out.setdefault(n.value.id, set()).add(n.attr)
    return {k: sorted(v) for k, v in out.items()}


# ---------------------------------------------------------------------------
# M6: names the tree rebinds in the old module at run time
# ---------------------------------------------------------------------------

SKIP_DIRS = {"archive", "_scratch", "__pycache__", "node_modules",
             "site-packages"}
NOT_PATCHES = {"getattr", "hasattr"}


def _py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and not d.startswith("."))
        for f in sorted(filenames):
            if f.endswith(".py"):
                yield Path(dirpath) / f


def _resolve_from(rel: str, level: int, module: str | None) -> str:
    """The absolute module of `from <level dots><module> import ...` in the
    file `rel` (relative to the root)."""
    if not level:
        return module or ""
    try:
        parts = module_name(rel).split(".")
    except MapError:
        return module or ""
    pkg = parts if rel.replace("\\", "/").endswith("__init__.py") else parts[:-1]
    if level > 1:
        pkg = pkg[:max(0, len(pkg) - (level - 1))]
    base = ".".join(pkg)
    return ".".join(x for x in (base, module) if x)


def _dotted(expr: ast.AST) -> str | None:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        head = _dotted(expr.value)
        return f"{head}.{expr.attr}" if head else None
    return None


def _old_aliases(tree: ast.Module, rel: str, old: str) -> set[str]:
    """The spellings by which the file reaches the module `old`: an
    `import old [as x]`, `import old.sub` (the chain `old`), `from pkg
    import old [as x]`, relative imports resolved."""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.asname:
                    if a.name == old:
                        out.add(a.asname)
                elif a.name == old or a.name.startswith(old + "."):
                    out.add(old)
        elif isinstance(n, ast.ImportFrom):
            base = _resolve_from(rel, n.level, n.module)
            for a in n.names:
                if (f"{base}.{a.name}" if base else a.name) == old:
                    out.add(a.asname or a.name)
    return out


def _func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return ""


def _str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _global_rebinds(tree: ast.Module) -> list[tuple[str, int, str]]:
    """(name, line, function) for every function that declares `global
    name` and binds it in its own scope."""
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        declared, binds = set(), set()
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef, ast.Lambda)):
                if not isinstance(n, ast.Lambda):
                    binds.add(n.name)
                continue
            if isinstance(n, ast.Global):
                declared.update(n.names)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                binds.add(n.id)
            elif isinstance(n, ast.alias):
                binds.add((n.asname or n.name).split(".")[0])
            stack.extend(ast.iter_child_nodes(n))
        for g in sorted(declared & binds):
            out.append((g, fn.lineno, fn.name))
    return out


def gate_rebound(pin_outputs: Path | None = None) -> list[tuple[str, str]]:
    """Pin 42's `_REBOUND` (module, name) pairs, read from pin_outputs.py
    as text (no import): the names gate_hooks.install replaces."""
    path = pin_outputs or Path(__file__).with_name("pin_outputs.py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_REBOUND" for t in n.targets):
            try:
                return [tuple(x) for x in ast.literal_eval(n.value)]
            except ValueError:
                return []
    return []


def rebound_sites(root: str | os.PathLike, old: str,
                  extra: list[tuple[str, str]] = ()) -> dict:
    """{name: [site, ...]} of the names of module `old` that the tree under
    `root` rebinds at run time; the name "*" when a setattr on the module
    has a computed name. `extra` adds (module, name) pairs (pin 42's)."""
    root = Path(root)
    sites: dict[str, list[str]] = {}

    def add(name, where):
        sites.setdefault(name, []).append(where)

    for mod, name in extra:
        if mod == old and "." not in name:
            add(name, "pin 42 _REBOUND (gate_hooks.install)")
    for path in _py_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        try:
            is_old = module_name(rel) == old
        except MapError:
            is_old = False
        if is_old:
            for g, line, fn in _global_rebinds(tree):
                add(g, f"{rel}:{line} {fn}() declares global {g} and binds it")
        aliases = _old_aliases(tree, rel, old)
        for n in ast.walk(tree):
            if aliases and isinstance(n, ast.Attribute) \
                    and isinstance(n.ctx, (ast.Store, ast.Del)) \
                    and _dotted(n.value) in aliases:
                # an assignment, `+=`, `del` or a for/with target
                add(n.attr, f"{rel}:{n.lineno} {_dotted(n.value)}.{n.attr} assigned")
            if not isinstance(n, ast.Call) or not n.args:
                continue
            fname = _func_name(n)
            a0 = n.args[0]
            a1 = _str(n.args[1]) if len(n.args) > 1 else None
            if aliases and fname in ("setattr", "delattr", "object") \
                    and _dotted(a0) in aliases and len(n.args) > 1:
                add(a1 if a1 else "*",
                    f"{rel}:{n.lineno} {fname}({_dotted(a0)}, "
                    f"{repr(a1) if a1 else 'a computed name'})")
            s0 = _str(a0)
            if s0 and fname in ("setattr", "patch", "delattr") \
                    and s0.startswith(old + ".") and "." not in s0[len(old) + 1:]:
                add(s0[len(old) + 1:], f"{rel}:{n.lineno} {fname}({s0!r})")
            if s0 == old and a1 and a1.isidentifier() \
                    and fname not in NOT_PATCHES:
                add(a1, f"{rel}:{n.lineno} {fname}({old!r}, {a1!r})")
    return sites


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
    rebound = item.get("rebound", {})
    for g in item["globals"]:
        a = old.__dict__.get(g, builtins.__dict__.get(g, MISSING))
        b = new.__dict__.get(g, builtins.__dict__.get(g, MISSING))
        if b is MISSING:
            res["globals"][g] = "not bound in the new module"
        elif b is old:
            missing = [x for x in item.get("through", {}).get(g, [])
                       if not hasattr(old, x)]
            res["globals"][g] = ("read through the module, but %s is not bound "
                                 "in the old module" % ", ".join(missing)
                                 if missing else "same")
        elif g in rebound or "*" in rebound:
            sites = rebound.get(g) or rebound.get("*")
            res["globals"][g] = ("rebound at run time (%s): a bare read in the new "
                                 "module keeps the value of import time; read it "
                                 "through the module (import %s; %s.%s)"
                                 % ("; ".join(sites[:3]) + (" ..." if len(sites) > 3 else ""),
                                    item["old_module"], item["old_module"], g))
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


def build_payload(rows: list[dict], root: Path,
                  extra_rebound: list[tuple[str, str]] = ()) -> tuple[list[dict], list[dict]]:
    payload, failed = [], []
    scans: dict[str, dict] = {}
    for r in rows:
        entry = r["entry"] or f"{r['old_file']}::{r['old_qualname']}"
        try:
            old_mod, new_mod = module_name(r["old_file"]), module_name(r["new_file"])
            path = root / r["new_file"]
            src = path.read_text(encoding="utf-8")
            read, declared = globals_read(src, str(path), r["new_qualname"])
            through = attributes_read(src, r["new_qualname"])
        except (MapError, OSError, SyntaxError) as exc:
            failed.append({"entry": entry, "error": f"{type(exc).__name__}: {exc}",
                           "globals": {}})
            continue
        if old_mod not in scans:
            scans[old_mod] = rebound_sites(root, old_mod, extra_rebound)
        sites = scans[old_mod]
        payload.append({"entry": entry, "old_module": old_mod, "new_module": new_mod,
                        "qualname": r["new_qualname"], "globals": read,
                        "declared_global": declared,
                        "through": {g: through[g] for g in read if g in through},
                        "rebound": {g: s for g, s in sites.items()
                                    if g in read or g == "*"}})
    return payload, failed


def check_rows(rows: list[dict], root: str | os.PathLike, python: str = sys.executable,
               timeout: float = 600, extra_rebound: list[tuple[str, str]] | None = None
               ) -> list[dict]:
    """The identity check of every cross-file row, in one child interpreter
    (cwd `root`, PYTHONHASHSEED=0, no bytecode written). `extra_rebound`
    (module, name) pairs count as rebound; by default pin 42's list."""
    root = Path(root).resolve()
    if extra_rebound is None:
        extra_rebound = gate_rebound()
    payload, results = build_payload(cross_file_rows(rows), root, extra_rebound)
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
