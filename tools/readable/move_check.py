"""move_check: the token checker of the readable migration (Phase 0).

It does not apply a cut. It reads a cut spec (JSON) whose entries name an
old span (old file, function, and for a cut a run of statements inside it)
and a new home (new file, function), and checks that the new body's tokens
equal the old span's tokens after a CLOSED list of allowed rewrites:

  R1 name map      a name `x` becomes `st.<group>.x` (per-name map, one
                   field per name, the field keeps the name)
  R2 break         a `break` that leaves the cut span (its loop is outside
                   the span) becomes `return <break_sentinel>`
  R3 sentinels     `return False` / `return None` of the old function inside
                   the span become `return <SENTINEL>` (PLAN: the two early
                   returns of `main`)
  R4 nonlocal      `nonlocal` lines are dropped (their names must be mapped)
  R5 indentation   compared relative to the span's first statement
  R6 comments      may differ, but every removed, changed or added comment
                   is printed as residual (rule 19: narration comments stay);
                   the old comments are those inside the span plus the
                   contiguous comment block directly above it (to the first
                   blank or code line), the new ones those inside the new
                   function plus the block directly above the new def

Everything else that differs is printed as residual. Beside the token
compare it checks:
  - a cut is a contiguous run of sibling statements of ONE block (no cut
    through a `try`, `with`, `if` or loop), and a def span carries its
    decorators;
  - free names (PLAN 24.3 (f)): every name the new function reads is a
    parameter, a local bound before use, a mapped field (through its
    parameter `st`), a builtin, or a global that the old span also read as
    a Name (and the new module binds it);
  - for a deletion: the rest of the file is unchanged and no NAME token of
    the deleted function remains;
  - R's conditions of R_PHASE0 section 6:
    M1 a whole-file account: for every file the spec touches (the old and
       new file of each entry, the state class file, `account_files`), the
       old logical lines minus all old spans against the new logical lines
       minus all new functions, by the same token keys; what differs is
       printed as "outside the entries" (exit 3 at least);
    M2 every comment of a touched file is diffed by one entry (inside the
       span, the block directly above it, the block that ends it, and for
       a move the block above the def after blank lines) or by the account;
    M3 the old spans of a spec are pairwise disjoint, the new functions
       too, and a new function is the home of one entry;
    M4 a mapped name is a local of the old container (or a nonlocal of a
       closure in it, owned by the enclosing function); a mapped global or
       builtin fails; one target field in two entries comes from one
       owning scope;
    M5 the spec names the state classes (`state_classes`) and every mapped
       target `st.<group>.<field>` is a field the group's class declares;
    M7 a cut: a name the span binds and the map does not hold is not read
       after the span in the old function (nor before it inside a loop
       around the span, nor in a nested function), and is not declared
       `global` or `nonlocal` outside the span; the sentinels of one entry
       differ pairwise; the new header is `def name(params):` only (or,
       for a cut of a whole body, the old header's decorators, defaults,
       annotations and `async`);
    M8 cheap flags: a `__x` name or attribute, `super()` without arguments
       and `__class__` in code whose class changes.
It writes MIGRATION_MAP.tsv rows and a per-entry line map.

Run (any Python 3.11+, no pybullet, no pipeline import):
  python tools/readable/move_check.py SPEC.json --old-root OLD --new-root NEW
      [--map tools/readable/MIGRATION_MAP.tsv] [--line-map LINEMAP.tsv]
      [--json RESULT.json]
  (--old-ref REF --repo DIR reads the old files from a git ref instead.)

Exit codes: 0 clean; 3 only comment residual, warnings or lines outside the
entries (R reads them); 1 a code residual or a failed rule; 2 the spec or a
file could not be read.

f-strings: Python 3.11 tokenizes an f-string as one STRING token, 3.12+
splits it. This tool merges the 3.12+ pieces back into one STRING token,
so both versions compare the same. An f-string is compared by its prefix,
quote and `ast.dump` (so a mapped name inside `{...}` is rewritten by R1,
and spaces inside `{...}` do not count); every other string is compared
by its exact text.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import difflib
import io
import json
import os
import re
import subprocess
import symtable
import sys
import tokenize
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

SPEC_VERSION = 1

# The draft's state groups (synthesis_draft.md section 4.2, "What carries the
# state"). `setup` is open: any setup product may go there.
DEFAULT_GROUPS: Dict[str, Optional[List[str]]] = {
    "counts": ["plan_count", "sense_count", "observe_count",
               "observe_strikes", "m8_per_plan", "plan_times",
               "total_plan_time", "boxel_counts_per_replan",
               "integrity_events"],
    "hand": ["held_body_id", "held_object_boxel_id", "held_grasp_xy"],
    "arm": ["current_config", "at_home_ok", "home_misses", "readback_count"],
    "strikes": ["blocked_counts", "blocked_giveup_shadows",
                "pick_fail_counts", "pick_giveup_objects",
                "pick_giveup_marked_at", "pick_parole_counts",
                "transit_loss_counts", "nontarget_rediscovery_counts",
                "stack_fail_counts", "disturbed_counts"],
    "ending": ["exit_reason", "episode_over", "target_lost_seen"],
    "setup": None,
}

MODULE_DUNDERS = {"__name__", "__file__", "__doc__", "__spec__",
                  "__loader__", "__package__", "__builtins__",
                  "__annotations__", "__dict__"}

_TARGET_RE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
_STRING_PREFIX_RE = re.compile(r"^([A-Za-z]*)('''|\"\"\"|'|\")")

_FSTART = {getattr(tokenize, n) for n in ("FSTRING_START", "TSTRING_START")
           if hasattr(tokenize, n)}
_FEND = {getattr(tokenize, n) for n in ("FSTRING_END", "TSTRING_END")
         if hasattr(tokenize, n)}


class SpecError(Exception):
    """The spec or a file it names cannot be read (exit 2)."""


# ---------------------------------------------------------------------------
# Source scanning: tokens grouped into logical lines, comments, ast
# ---------------------------------------------------------------------------

@dataclass
class Tok:
    type: str
    string: str
    row: int
    col: int  # in characters


@dataclass
class LogicalLine:
    start: int
    end: int
    depth: int
    toks: List[Tok]


@dataclass
class Source:
    path: str
    text: str
    lines: List[str]          # without line ends, index 0 is line 1
    tree: ast.Module
    logical: List[LogicalLine]
    comments: List[Tuple[int, str]]  # (row, text)

    def line(self, row: int) -> str:
        return self.lines[row - 1] if 0 < row <= len(self.lines) else ""

    def char_col(self, row: int, byte_col: int) -> int:
        raw = self.line(row).encode("utf-8")
        return len(raw[:byte_col].decode("utf-8", errors="replace"))

    def logical_text(self, ll: LogicalLine) -> str:
        first = self.line(ll.start).strip()
        if ll.end > ll.start:
            return f"{first} ... (to {ll.end})"
        return first


def scan_source(text: str, path: str) -> Source:
    if text.startswith("﻿"):
        text = text[1:]
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        raise SpecError(f"{path}: does not parse: {exc}") from exc
    keep_lines = text.splitlines(keepends=True)
    logical: List[LogicalLine] = []
    comments: List[Tuple[int, str]] = []
    depth = 0
    cur: List[Tok] = []
    cur_start = 0
    cur_depth = 0
    toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.type in _FSTART:
            nest, j = 1, i + 1
            while j < len(toks) and nest:
                if toks[j].type in _FSTART:
                    nest += 1
                elif toks[j].type in _FEND:
                    nest -= 1
                j += 1
            end = toks[j - 1].end
            s_row, s_col = t.start
            if s_row == end[0]:
                piece = keep_lines[s_row - 1][s_col:end[1]]
            else:
                piece = keep_lines[s_row - 1][s_col:]
                for r in range(s_row + 1, end[0]):
                    piece += keep_lines[r - 1]
                piece += keep_lines[end[0] - 1][:end[1]]
            if not cur:
                cur_start, cur_depth = s_row, depth
            cur.append(Tok("STRING", piece, s_row, s_col))
            i = j
            continue
        i += 1
        if t.type in (tokenize.ENCODING, tokenize.NL, tokenize.ENDMARKER):
            continue
        if t.type == tokenize.COMMENT:
            comments.append((t.start[0], t.string))
            continue
        if t.type == tokenize.INDENT:
            depth += 1
            continue
        if t.type == tokenize.DEDENT:
            depth -= 1
            continue
        if t.type == tokenize.NEWLINE:
            if cur:
                logical.append(LogicalLine(cur_start, t.start[0], cur_depth,
                                           cur))
            cur = []
            continue
        if not cur:
            cur_start, cur_depth = t.start[0], depth
        cur.append(Tok(tokenize.tok_name[t.type], t.string, t.start[0],
                       t.start[1]))
    if cur:
        logical.append(LogicalLine(cur_start, cur[-1].row, cur_depth, cur))
    return Source(path, text, text.splitlines(), tree, logical, comments)


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------

_DEF = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_COMPS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)


def first_line(node: ast.AST) -> int:
    decs = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decs])


@dataclass
class StmtInfo:
    node: ast.stmt
    parent: ast.AST
    field: str
    index: int
    depth: int


def statements_under(fn: ast.AST) -> List[StmtInfo]:
    """Every statement inside fn's body, not entering nested def bodies."""
    out: List[StmtInfo] = []

    def visit(parent: ast.AST, depth: int) -> None:
        for fld in ("body", "orelse", "finalbody", "handlers", "cases"):
            seq = getattr(parent, fld, None)
            if not isinstance(seq, list):
                continue
            for idx, child in enumerate(seq):
                if isinstance(child, (ast.ExceptHandler,)) or (
                        hasattr(ast, "match_case")
                        and isinstance(child, ast.match_case)):
                    visit(child, depth + 1)
                    continue
                if not isinstance(child, ast.stmt):
                    continue
                out.append(StmtInfo(child, parent, fld, idx, depth))
                if not isinstance(child, _DEF):
                    visit(child, depth + 1)

    visit(fn, 0)
    return out


def find_qualname(tree: ast.Module, qualname: str) -> ast.AST:
    node: ast.AST = tree
    for part in qualname.split("."):
        if isinstance(node, ast.Module) or isinstance(node, ast.ClassDef):
            pool = [s for s in node.body if isinstance(s, _DEF)]
            # also defs inside top-level if/try blocks of a module or class
            for s in node.body:
                if not isinstance(s, _DEF):
                    for sub in ast.walk(s):
                        if isinstance(sub, _DEF):
                            pool.append(sub)
        else:
            pool = [si.node for si in statements_under(node)
                    if isinstance(si.node, _DEF)]
        cands = [d for d in pool if d.name == part]
        if not cands:
            raise SpecError(f"qualname {qualname!r}: no def or class "
                            f"{part!r}")
        if len(cands) > 1:
            rows = ", ".join(str(c.lineno) for c in cands)
            raise SpecError(f"qualname {qualname!r}: {part!r} is defined "
                            f"{len(cands)} times (lines {rows})")
        node = cands[0]
    return node


@dataclass
class Span:
    first: int
    last: int
    stmts: List[ast.stmt]
    container: ast.AST        # the def whose body holds the span
    whole_def: bool


class RuleFailure(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


def _anchor_row(src: Source, lo: int, hi: int, anchor: Optional[str],
                row: Optional[int], occurrence: Optional[int],
                which: str) -> int:
    if row is not None:
        return int(row)
    if anchor is None:
        raise SpecError(f"{which}: give an anchor text or a line")
    hits = [r for r in range(lo, hi + 1) if anchor in src.line(r)]
    if not hits:
        raise RuleFailure("anchor-not-found",
                          f"{which} anchor {anchor!r} not found in lines "
                          f"{lo}-{hi}")
    if occurrence is None:
        if len(hits) > 1:
            raise RuleFailure("anchor-ambiguous",
                              f"{which} anchor {anchor!r} matches lines "
                              f"{hits}; give an occurrence")
        return hits[0]
    if not 1 <= occurrence <= len(hits):
        raise RuleFailure("anchor-not-found",
                          f"{which} anchor {anchor!r} has {len(hits)} "
                          f"matches, occurrence {occurrence} asked")
    return hits[occurrence - 1]


def _stmt_at(infos: List[StmtInfo], row: int, which: str) -> StmtInfo:
    starting = [si for si in infos if first_line(si.node) == row]
    if starting:
        return min(starting, key=lambda si: si.depth)
    for si in infos:
        if isinstance(si.node, _DEF) and si.node.lineno == row \
                and first_line(si.node) < row:
            raise RuleFailure(
                "span-splits-decorator",
                f"{which} line {row} is the def line of "
                f"{si.node.name!r}; its decorators start at "
                f"{first_line(si.node)}, the span must start there")
    raise RuleFailure("anchor-not-statement-start",
                      f"{which} line {row} does not start a statement")


def _block_name(parent: ast.AST, fld: str) -> str:
    kind = type(parent).__name__
    if isinstance(parent, ast.ExceptHandler):
        return f"except (line {parent.lineno})"
    return f"{kind.lower()}.{fld} (line {getattr(parent, 'lineno', 0)})"


def resolve_old_span(src: Source, old: dict, kind: str) -> Span:
    fn = find_qualname(src.tree, old["qualname"])
    has_bounds = any(k in old for k in ("start_anchor", "start_line",
                                        "end_anchor", "end_line"))
    if kind in ("move", "delete"):
        f0, f1 = first_line(fn), fn.end_lineno
        if "start_line" in old and int(old["start_line"]) != f0:
            if int(old["start_line"]) == fn.lineno and f0 < fn.lineno:
                raise RuleFailure(
                    "span-splits-decorator",
                    f"start line {old['start_line']} is the def line of "
                    f"{old['qualname']!r}; its decorators start at {f0}")
            raise RuleFailure("span-not-whole-def",
                              f"start line {old['start_line']} is not the "
                              f"first line {f0} of {old['qualname']!r}")
        if "end_line" in old and int(old["end_line"]) != f1:
            raise RuleFailure("span-not-whole-def",
                              f"end line {old['end_line']} is not the last "
                              f"line {f1} of {old['qualname']!r}")
        return Span(f0, f1, [fn], fn, True)
    if not has_bounds:
        raise SpecError(f"cut of {old['qualname']!r}: give start and end "
                        f"anchors (or lines)")
    infos = statements_under(fn)
    lo, hi = first_line(fn), fn.end_lineno
    r0 = _anchor_row(src, lo, hi, old.get("start_anchor"),
                     old.get("start_line"), old.get("start_occurrence"),
                     "start")
    r1 = _anchor_row(src, lo, hi, old.get("end_anchor"),
                     old.get("end_line"), old.get("end_occurrence"), "end")
    s0 = _stmt_at(infos, r0, "start")
    s1 = _stmt_at(infos, r1, "end")
    if s0.parent is not s1.parent or s0.field != s1.field:
        raise RuleFailure(
            "cut-crosses-block",
            f"the span starts in {_block_name(s0.parent, s0.field)} and "
            f"ends in {_block_name(s1.parent, s1.field)}: a cut must be a "
            f"run of siblings of one block (no cut through a try, with, "
            f"if or loop)")
    if s0.index > s1.index:
        raise RuleFailure("cut-reversed",
                          f"start line {r0} comes after end line {r1}")
    seq = getattr(s0.parent, s0.field)[s0.index:s1.index + 1]
    return Span(first_line(seq[0]), seq[-1].end_lineno, seq, fn, False)


# ---------------------------------------------------------------------------
# Scope-aware name helpers
# ---------------------------------------------------------------------------

def _arg_names(args: ast.arguments) -> Set[str]:
    out = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
    if args.vararg:
        out.add(args.vararg.arg)
    if args.kwarg:
        out.add(args.kwarg.arg)
    return out


def _target_names(node: ast.AST) -> Set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _local_binds(fn: ast.AST) -> Set[str]:
    """Names a def binds in its own scope (no nested scopes), minus the
    names it declares nonlocal or global."""
    binds: Set[str] = set()
    declared: Set[str] = set()

    def visit(n: ast.AST) -> None:
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.Global, ast.Nonlocal)):
                declared.update(c.names)
            elif isinstance(c, _DEF):
                binds.add(c.name)
            elif isinstance(c, (ast.Lambda,) + _COMPS):
                continue
            elif isinstance(c, ast.Name) and isinstance(c.ctx, (ast.Store,
                                                                ast.Del)):
                binds.add(c.id)
            elif isinstance(c, ast.alias):
                binds.add((c.asname or c.name).split(".")[0])
            elif isinstance(c, ast.ExceptHandler) and c.name:
                binds.add(c.name)
                visit(c)
            else:
                visit(c)

    for s in fn.body:
        if isinstance(s, (ast.Global, ast.Nonlocal)):
            declared.update(s.names)
        elif isinstance(s, _DEF):
            binds.add(s.name)
        else:
            visit(ast.Module(body=[s], type_ignores=[]))
    return binds - declared


def mapped_name_nodes(stmts: Sequence[ast.AST],
                      name_map: Dict[str, str]) -> List[ast.Name]:
    """Name nodes the name map rewrites: not inside an f-string (those are
    compared through the STRING key) and not shadowed by a lambda,
    comprehension or nested def that binds the same name."""
    out: List[ast.Name] = []

    def visit(n: ast.AST, shadow: frozenset) -> None:
        if isinstance(n, ast.Name):
            if n.id in name_map and n.id not in shadow:
                out.append(n)
            return
        if isinstance(n, ast.JoinedStr):
            return
        if isinstance(n, ast.Lambda):
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow)
            visit(n.body, shadow | _arg_names(n.args))
            return
        if isinstance(n, _FUNC):
            for d in n.decorator_list:
                visit(d, shadow)
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow)
            inner = shadow | _arg_names(n.args) | _local_binds(n)
            for s in n.body:
                visit(s, inner)
            return
        if isinstance(n, _COMPS):
            gens = n.generators
            visit(gens[0].iter, shadow)
            inner = shadow | set().union(*[_target_names(g.target)
                                           for g in gens])
            for k, g in enumerate(gens):
                if k:
                    visit(g.iter, inner)
                for c in g.ifs:
                    visit(c, inner)
            if isinstance(n, ast.DictComp):
                visit(n.key, inner)
                visit(n.value, inner)
            else:
                visit(n.elt, inner)
            return
        for c in ast.iter_child_nodes(n):
            visit(c, shadow)

    for s in stmts:
        visit(s, frozenset())
    return out


def leaving_jumps(stmts: Sequence[ast.stmt]):
    """break/continue whose loop is outside the statements; returns of the
    function the statements belong to."""
    brk: List[ast.Break] = []
    cont: List[ast.Continue] = []
    rets: List[ast.Return] = []
    yields: List[ast.AST] = []

    def visit(n: ast.AST, in_loop: bool) -> None:
        if isinstance(n, _SCOPES):
            return
        if isinstance(n, ast.Break) and not in_loop:
            brk.append(n)
        elif isinstance(n, ast.Continue) and not in_loop:
            cont.append(n)
        elif isinstance(n, ast.Return):
            rets.append(n)
        elif isinstance(n, (ast.Yield, ast.YieldFrom)):
            yields.append(n)
        if isinstance(n, _LOOPS):
            for fld in ("target", "iter", "test"):
                sub = getattr(n, fld, None)
                if sub is not None:
                    visit(sub, in_loop)
            for s in n.body:
                visit(s, True)
            for s in n.orelse:
                visit(s, in_loop)
            return
        for c in ast.iter_child_nodes(n):
            visit(c, in_loop)

    for s in stmts:
        visit(s, False)
    return brk, cont, rets, yields


# ---------------------------------------------------------------------------
# Token keys and rewrites
# ---------------------------------------------------------------------------

class _MapNames(ast.NodeTransformer):
    def __init__(self, name_map: Dict[str, str]):
        self.name_map = name_map

    def visit_Name(self, node: ast.Name) -> ast.AST:
        target = self.name_map.get(node.id)
        if target is None:
            return node
        parts = target.split(".")
        expr: ast.expr = ast.Name(id=parts[0], ctx=ast.Load())
        for p in parts[1:-1]:
            expr = ast.Attribute(value=expr, attr=p, ctx=ast.Load())
        return ast.Attribute(value=expr, attr=parts[-1], ctx=node.ctx)


def string_key(text: str, name_map: Optional[Dict[str, str]]) -> tuple:
    m = _STRING_PREFIX_RE.match(text)
    prefix = m.group(1).lower() if m else ""
    if "f" not in prefix and "t" not in prefix:
        return ("STRING", text)
    try:
        expr = ast.parse("(" + text + ")", mode="eval")
    except SyntaxError:
        return ("STRING", text)
    if name_map:
        expr = _MapNames(name_map).visit(expr)
    return ("FSTRING", "".join(sorted(prefix)), m.group(2), ast.dump(expr))


def tok_key(t: Tok, name_map: Optional[Dict[str, str]]) -> tuple:
    if t.type == "STRING":
        return string_key(t.string, name_map)
    return (t.type, t.string)


@dataclass
class Rewrites:
    name_pos: Dict[Tuple[int, int], str] = field(default_factory=dict)
    break_pos: Set[Tuple[int, int]] = field(default_factory=set)
    break_sentinel: str = ""
    const_pos: Dict[Tuple[int, int], str] = field(default_factory=dict)
    drop_rows: Set[int] = field(default_factory=set)
    name_map: Dict[str, str] = field(default_factory=dict)
    used: Dict[str, int] = field(default_factory=dict)

    def count(self, what: str) -> None:
        self.used[what] = self.used.get(what, 0) + 1


def keys_for(src: Source, lines: List[LogicalLine], base_depth: int,
             rw: Optional[Rewrites]) -> List[tuple]:
    out = []
    for ll in lines:
        if rw and ll.start in rw.drop_rows:
            rw.count("R4 nonlocal dropped")
            continue
        keys: List[tuple] = []
        for t in ll.toks:
            pos = (t.row, t.col)
            if rw and t.type == "NAME" and pos in rw.name_pos:
                parts = rw.name_pos[pos].split(".")
                for k, p in enumerate(parts):
                    if k:
                        keys.append(("OP", "."))
                    keys.append(("NAME", p))
                rw.count("R1 name map")
                continue
            if rw and t.type == "NAME" and t.string == "break" \
                    and pos in rw.break_pos:
                keys += [("NAME", "return"), ("NAME", rw.break_sentinel)]
                rw.count("R2 break to return")
                continue
            if rw and t.type == "NAME" and pos in rw.const_pos:
                keys.append(("NAME", rw.const_pos[pos]))
                rw.count("R3 sentinel return")
                continue
            if rw and t.type == "STRING" and rw.name_map:
                k_plain = string_key(t.string, None)
                k_map = string_key(t.string, rw.name_map)
                if k_plain != k_map:
                    rw.count("R1 name map (in f-string)")
                keys.append(k_map)
                continue
            keys.append(tok_key(t, None))
        out.append((ll.depth - base_depth, tuple(keys)))
    return out


# ---------------------------------------------------------------------------
# Free names (PLAN 24.3 (f))
# ---------------------------------------------------------------------------

def _st_type(t: symtable.SymbolTable) -> str:
    return str(t.get_type()).lower().split(".")[-1]


def find_table(top: symtable.SymbolTable, path: List[ast.AST]):
    t = top
    for node in path:
        cands = [c for c in t.get_children()
                 if c.get_name() == node.name
                 and _st_type(c) in ("function", "class")]
        if not cands:
            return None
        exact = [c for c in cands if c.get_lineno() in (node.lineno,
                                                         first_line(node))]
        t = (exact or cands)[0]
    return t


def def_path(tree: ast.Module, qualname: str) -> List[ast.AST]:
    parts = qualname.split(".")
    return [find_qualname(tree, ".".join(parts[:k + 1]))
            for k in range(len(parts))]


def _descendants(t: symtable.SymbolTable):
    yield t
    for c in t.get_children():
        yield from _descendants(c)


def global_reads(t: symtable.SymbolTable) -> Dict[str, None]:
    out: Dict[str, None] = {}
    for sub in _descendants(t):
        for s in sub.get_symbols():
            if s.is_referenced() and s.is_global():
                out[s.get_name()] = None
    return out


def names_read(node: ast.AST) -> List[Tuple[str, int]]:
    """(name, row) loads in node, respecting lambda and comprehension
    scopes; nested def bodies are not entered (they read at call time)."""
    out: List[Tuple[str, int]] = []

    def visit(n: ast.AST, shadow: frozenset) -> None:
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Load) and n.id not in shadow:
                out.append((n.id, n.lineno))
            return
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            if n.target.id not in shadow:
                out.append((n.target.id, n.target.lineno))
            visit(n.value, shadow)
            return
        if isinstance(n, ast.Lambda):
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow)
            visit(n.body, shadow | _arg_names(n.args))
            return
        if isinstance(n, _FUNC):
            for d in n.decorator_list:
                visit(d, shadow)
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow)
            return
        if isinstance(n, ast.ClassDef):
            for d in n.decorator_list + n.bases:
                visit(d, shadow)
            return
        if isinstance(n, _COMPS):
            gens = n.generators
            visit(gens[0].iter, shadow)
            inner = shadow | set().union(*[_target_names(g.target)
                                           for g in gens])
            for k, g in enumerate(gens):
                if k:
                    visit(g.iter, inner)
                for c in g.ifs:
                    visit(c, inner)
            if isinstance(n, ast.DictComp):
                visit(n.key, inner)
                visit(n.value, inner)
            else:
                visit(n.elt, inner)
            return
        for c in ast.iter_child_nodes(n):
            visit(c, shadow)

    visit(node, frozenset())
    return out


def names_bound(stmt: ast.stmt) -> Set[str]:
    if isinstance(stmt, _DEF):
        return {stmt.name}
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in stmt.names}
    out: Set[str] = set()
    for n in ast.walk(stmt):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.NamedExpr):
            out.add(n.target.id)
    return out


class _BindCheck:
    """Straight-line 'bound before read' walk over a function body."""

    def __init__(self, locals_: Set[str]):
        self.locals = locals_
        self.sure_bad: Dict[Tuple[str, int], None] = {}
        self.maybe_bad: Dict[Tuple[str, int], None] = {}

    def check(self, node: ast.AST, sure: Set[str], maybe: Set[str]) -> None:
        for name, row in names_read(node):
            if name in self.locals and name not in sure:
                if name in maybe:
                    self.maybe_bad[(name, row)] = None
                else:
                    self.sure_bad[(name, row)] = None

    def block(self, stmts, sure, maybe):
        for s in stmts:
            sure, maybe, term = self.stmt(s, sure, maybe)
            if term:
                return sure, maybe, True
        return sure, maybe, False

    def _join(self, before, results):
        falls = [s for s, _m, t in results if not t]
        maybe = set().union(*[m | s for s, m, _t in results]) \
            if results else set()
        if not falls:
            return set(before), maybe, True
        sure = set(falls[0])
        for s in falls[1:]:
            sure &= s
        return sure | before, maybe, False

    def _loop_body(self, body, sure, maybe):
        # two passes: names bound late in the body are 'maybe' on the
        # second pass (loop-carried); only second-pass problems count
        saved = (dict(self.sure_bad), dict(self.maybe_bad))
        s1, m1, _t = self.block(body, set(sure), set(maybe))
        self.sure_bad, self.maybe_bad = saved
        return self.block(body, set(sure), set(maybe) | s1 | m1)

    def stmt(self, s, sure, maybe):
        sure, maybe = set(sure), set(maybe)
        if isinstance(s, ast.If):
            self.check(s.test, sure, maybe)
            r1 = self.block(s.body, sure, maybe)
            r2 = self.block(s.orelse, sure, maybe)
            js, jm, jt = self._join(sure, [r1, r2])
            return js, maybe | jm, jt
        if isinstance(s, _LOOPS):
            if isinstance(s, ast.While):
                self.check(s.test, sure, maybe)
                inner = set(sure)
            else:
                self.check(s.iter, sure, maybe)
                inner = sure | _target_names(s.target)
            bs, bm, _bt = self._loop_body(s.body, inner, maybe)
            es, em, et = self.block(s.orelse, sure, maybe | bs | bm)
            infinite = (isinstance(s, ast.While)
                        and isinstance(s.test, ast.Constant)
                        and s.test.value is True)
            return es, maybe | bs | bm | em | inner, et and not infinite
        if isinstance(s, (ast.Try,) + ((ast.TryStar,)
                                       if hasattr(ast, "TryStar") else ())):
            rb = self.block(s.body, sure, maybe)
            if not rb[2]:
                rb = self.block(s.orelse, rb[0], rb[1])
            results = [rb]
            for h in s.handlers:
                if h.type is not None:
                    self.check(h.type, sure, maybe | rb[0] | rb[1])
                hs = sure | ({h.name} if h.name else set())
                results.append(self.block(h.body, hs, maybe | rb[0] | rb[1]))
            js, jm, jt = self._join(sure, results)
            fs, fm, ft = self.block(s.finalbody, js, maybe | jm)
            return fs, maybe | jm | fm, jt or ft
        if isinstance(s, (ast.With, ast.AsyncWith)):
            for it in s.items:
                self.check(it.context_expr, sure, maybe)
                if it.optional_vars is not None:
                    sure |= _target_names(it.optional_vars)
            return self.block(s.body, sure, maybe)
        if hasattr(ast, "Match") and isinstance(s, ast.Match):
            self.check(s.subject, sure, maybe)
            res = [self.block(c.body, sure | _target_names(c.pattern), maybe)
                   for c in s.cases]
            allm = set().union(*[r[0] | r[1] for r in res]) if res else set()
            return sure, maybe | allm, False
        if isinstance(s, (ast.Global, ast.Nonlocal)):
            return sure, maybe, False
        self.check(s, sure, maybe)
        sure |= names_bound(s)
        term = isinstance(s, (ast.Return, ast.Raise, ast.Break, ast.Continue))
        return sure, maybe, term


@dataclass
class FreeNameReport:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


def check_free_names(new_src: Source, new_qualname: str, old_src: Source,
                     old_table_qualname: str, old_span_names: Set[str],
                     sentinels: Set[str],
                     old_class_qualname: Optional[str]) -> FreeNameReport:
    rep = FreeNameReport()
    new_path = def_path(new_src.tree, new_qualname)
    fn = new_path[-1]
    top_new = symtable.symtable(new_src.text, new_src.path, "exec")
    t_new = find_table(top_new, new_path)
    top_old = symtable.symtable(old_src.text, old_src.path, "exec")
    t_old = find_table(top_old, def_path(old_src.tree, old_table_qualname))
    if t_new is None or t_old is None:
        rep.errors.append("symbol table of the new or old function not "
                          "found")
        return rep
    old_globals = set(global_reads(t_old))
    if old_span_names is not None:
        old_globals &= old_span_names
    module_bound = {s.get_name() for s in top_new.get_symbols()
                    if s.is_assigned() or s.is_imported()}
    star = any(isinstance(n, ast.ImportFrom)
               and any(a.name == "*" for a in n.names)
               for n in new_src.tree.body)
    builtin_names = set(dir(builtins)) | MODULE_DUNDERS
    params = [s.get_name() for s in t_new.get_symbols() if s.is_parameter()]
    globals_seen = []
    for name in global_reads(t_new):
        if name in builtin_names:
            continue
        if name in sentinels:
            if name not in module_bound and not star:
                rep.errors.append(f"sentinel {name!r} is read but the new "
                                  f"module does not bind it")
            continue
        if name not in old_globals:
            rep.errors.append(
                f"{name!r} is read as a global, but it is not a parameter, "
                f"a local, a mapped field, a builtin or a global the old "
                f"code read")
            continue
        globals_seen.append(name)
        if name not in module_bound:
            if star:
                rep.warnings.append(f"global {name!r}: the new module has a "
                                    f"star import; binding not checked")
            else:
                rep.errors.append(f"global {name!r} (read by the old code "
                                  f"too) is not bound in the new module")
    locals_ = {s.get_name() for s in t_new.get_symbols()
               if s.is_local() and not s.is_parameter()
               and not s.is_global()}
    bc = _BindCheck(locals_)
    bc.block(fn.body, set(params), set())
    for (name, row) in bc.sure_bad:
        rep.errors.append(f"local {name!r} is read at new line {row} before "
                          f"it is bound")
    for (name, row) in bc.maybe_bad:
        rep.warnings.append(f"local {name!r} at new line {row} is bound "
                            f"only on some paths before this read (R reads)")
    rep.info.append("parameters: " + (", ".join(params) or "(none)"))
    rep.info.append("globals read (old code read them too): "
                    + (", ".join(sorted(globals_seen)) or "(none)"))
    # self.<attr> reads of a method (the P2 trap: attributes that stay in
    # the host class and arrive only through the MRO)
    if len(new_path) >= 2 and isinstance(new_path[-2], ast.ClassDef):
        reads = sorted({n.attr for n in ast.walk(fn)
                        if isinstance(n, ast.Attribute)
                        and isinstance(n.value, ast.Name)
                        and n.value.id == "self"
                        and isinstance(n.ctx, ast.Load)})
        own = _class_defines(new_path[-2])
        missing = [a for a in reads if a not in own]
        if missing:
            host = ""
            if old_class_qualname:
                try:
                    old_cls = find_qualname(old_src.tree, old_class_qualname)
                    old_own = _class_defines(old_cls)
                    gone = [a for a in missing if a not in old_own]
                    host = f" (old class {old_class_qualname} defines " \
                           f"{', '.join(a for a in missing if a in old_own) or 'none'})"
                    for a in gone:
                        rep.warnings.append(f"self.{a} is defined neither "
                                            f"in the new nor the old class")
                except SpecError:
                    pass
            rep.info.append("self attributes read but not defined in "
                            f"{new_path[-2].name}: {', '.join(missing)}; "
                            f"they must come through the MRO{host}")
    return rep


def _class_defines(cls: ast.ClassDef) -> Set[str]:
    out: Set[str] = set()
    for s in cls.body:
        if isinstance(s, _DEF):
            out.add(s.name)
        elif isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tgts = s.targets if isinstance(s, ast.Assign) else [s.target]
            for t in tgts:
                out |= _target_names(t)
    for n in ast.walk(cls):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) \
                and isinstance(n.value, ast.Name) and n.value.id == "self":
            out.add(n.attr)
    return out


# ---------------------------------------------------------------------------
# Name map validation
# ---------------------------------------------------------------------------

def validate_map(name_map: Dict[str, str],
                 groups: Dict[str, Optional[List[str]]]):
    errors: List[Tuple[str, str]] = []
    warnings: List[str] = []
    seen: Dict[str, str] = {}
    for name, target in name_map.items():
        if not isinstance(target, str) or not _TARGET_RE.match(target):
            errors.append(("map-bad-target",
                           f"{name!r} -> {target!r} is not a dotted field"))
            continue
        if target in seen:
            errors.append(("map-not-one-to-one",
                           f"{seen[target]!r} and {name!r} are both mapped "
                           f"to {target!r}"))
        seen[target] = name
        parts = target.split(".")
        if parts[-1] != name:
            errors.append(("map-renames-name",
                           f"{name!r} -> {target!r}: the field must keep "
                           f"the name (`x` to `st.<group>.x`)"))
        if len(parts) == 3:
            group = parts[1]
            if group not in groups:
                errors.append(("map-unknown-group",
                               f"{name!r} -> {target!r}: group {group!r} "
                               f"is not one of {sorted(groups)}"))
            else:
                home = [g for g, fs in groups.items() if fs and name in fs]
                if home and group not in home:
                    errors.append(("map-wrong-group",
                                   f"{name!r} -> {target!r}: the group "
                                   f"table puts it in {home[0]!r}"))
                elif not home and groups[group] is not None:
                    warnings.append(f"{name!r} -> {target!r}: not in the "
                                    f"group table of {group!r}")
        else:
            warnings.append(f"{name!r} -> {target!r}: not of the form "
                            f"st.<group>.{name}")
    return errors, warnings


# ---------------------------------------------------------------------------
# R's conditions inside one entry: M4 (mapped names), M7 (cuts), M8 (flags)
# ---------------------------------------------------------------------------

def _scope_chain(src: Source, qualname: str):
    """[(def node, its symbol table)] from the outermost def to `qualname`."""
    top = symtable.symtable(src.text, src.path, "exec")
    path = def_path(src.tree, qualname)
    return [(path[k], find_table(top, path[:k + 1]))
            for k in range(len(path))]


def map_owner(src: Source, container_q: str,
              name: str) -> Tuple[Optional[str], str]:
    """M4: the qualname of the function scope that owns `name` as a local,
    seen from the old container (a nonlocal or free name of a closure is
    owned by the enclosing function that binds it). (None, why) for a
    global, a builtin, or a name the container does not know."""
    chain = _scope_chain(src, container_q)
    names = [n.name for n, _t in chain]
    for k in range(len(chain) - 1, -1, -1):
        node, table = chain[k]
        if table is None:
            return None, "the symbol table of the old function is not found"
        inner = k == len(chain) - 1
        if not inner and _st_type(table) == "class":
            continue          # a class body is no enclosing scope
        try:
            sym = table.lookup(name)
        except KeyError:
            if inner:
                return None, (f"{name!r} is not a name of the old function "
                              f"{container_q}")
            continue
        if sym.is_global():
            return None, (f"{name!r} is a module global or a builtin in the "
                          f"old code, not a local of {container_q}")
        nonlocal_ = getattr(sym, "is_nonlocal", lambda: False)()
        if sym.is_free() or nonlocal_:
            continue
        if sym.is_local() or sym.is_parameter():
            return ".".join(names[:k + 1]), ""
        return None, f"{name!r}: not a local of {names[k]}"
    return None, f"{name!r} is bound by no enclosing function"


def _span_binds(stmts: Sequence[ast.stmt]) -> Tuple[Set[str], Set[str]]:
    """(names the statements bind in their own scope, names they declare
    global or nonlocal). Nested scopes are not entered, but a walrus inside
    a comprehension binds in this scope and is taken."""
    binds: Set[str] = set()
    declared: Set[str] = set()

    def visit(n: ast.AST) -> None:
        for c in ast.iter_child_nodes(n):
            if isinstance(c, (ast.Global, ast.Nonlocal)):
                declared.update(c.names)
            elif isinstance(c, _DEF):
                binds.add(c.name)
            elif isinstance(c, ast.Lambda):
                continue
            elif isinstance(c, _COMPS):
                for w in ast.walk(c):
                    if isinstance(w, ast.NamedExpr) \
                            and isinstance(w.target, ast.Name):
                        binds.add(w.target.id)
            elif isinstance(c, ast.Name) and isinstance(c.ctx, (ast.Store,
                                                                ast.Del)):
                binds.add(c.id)
            elif isinstance(c, ast.alias):
                if c.name != "*":
                    binds.add((c.asname or c.name).split(".")[0])
            elif isinstance(c, ast.ExceptHandler):
                if c.name:
                    binds.add(c.name)
                visit(c)
            elif hasattr(ast, "MatchAs") and isinstance(
                    c, (ast.MatchAs, ast.MatchStar)):
                if c.name:
                    binds.add(c.name)
                visit(c)
            elif hasattr(ast, "MatchMapping") and isinstance(
                    c, ast.MatchMapping):
                if c.rest:
                    binds.add(c.rest)
                visit(c)
            else:
                visit(c)

    for s in stmts:
        visit(ast.Module(body=[s], type_ignores=[]))
    return binds, declared


def _declared_outside(container: ast.AST, span: Span) -> Dict[str, int]:
    """`global` and `nonlocal` names of the container's own scope declared
    outside the span: name -> line."""
    out: Dict[str, int] = {}
    inside = {id(s) for s in span.stmts}

    def visit(n: ast.AST) -> None:
        for c in ast.iter_child_nodes(n):
            if id(c) in inside or isinstance(c, _SCOPES + _COMPS):
                continue
            if isinstance(c, (ast.Global, ast.Nonlocal)):
                for nm in c.names:
                    out.setdefault(nm, c.lineno)
            visit(c)

    for s in container.body:
        if id(s) in inside:
            continue
        if isinstance(s, (ast.Global, ast.Nonlocal)):
            for nm in s.names:
                out.setdefault(nm, s.lineno)
        elif not isinstance(s, _SCOPES):
            visit(s)
    return out


def _reads_outside(container: ast.AST, span: Span,
                   names: Set[str]) -> Dict[str, List[int]]:
    """M7: reads of `names` in the old container outside the span that can
    see a value the span bound: a read after the span, a read before it
    inside a loop around the span (the next pass sees it), and any read in
    a nested function or class of the container (it may run later). Names
    a nested scope binds itself are not its reads. Reads inside f-strings
    count."""
    lo, hi = span.first, span.last
    inside = {id(s) for s in span.stmts}
    hits: Dict[str, List[int]] = {}

    def hit(name: str, row: int, shadow: frozenset, nested: bool,
            loops: list) -> None:
        if name not in names or name in shadow:
            return
        if nested or row > hi or any(lp.lineno <= lo and lp.end_lineno >= hi
                                     for lp in loops):
            hits.setdefault(name, []).append(row)

    def visit(n: ast.AST, shadow: frozenset, nested: bool,
              loops: list) -> None:
        if id(n) in inside:
            return
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, (ast.Load, ast.Del)):
                hit(n.id, n.lineno, shadow, nested, loops)
            return
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
            hit(n.target.id, n.target.lineno, shadow, nested, loops)
            visit(n.value, shadow, nested, loops)
            return
        if isinstance(n, ast.Lambda):
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow, nested, loops)
            visit(n.body, shadow | _arg_names(n.args), True, loops)
            return
        if isinstance(n, _FUNC):
            for d in n.decorator_list + n.args.defaults \
                    + [d for d in n.args.kw_defaults if d]:
                visit(d, shadow, nested, loops)
            inner = shadow | _arg_names(n.args) | _local_binds(n)
            for s in n.body:
                visit(s, inner, True, loops)
            return
        if isinstance(n, ast.ClassDef):
            for d in n.decorator_list + n.bases:
                visit(d, shadow, nested, loops)
            for s in n.body:
                visit(s, shadow, True, loops)
            return
        if isinstance(n, _COMPS):
            gens = n.generators
            visit(gens[0].iter, shadow, nested, loops)
            inner = shadow | set().union(*[_target_names(g.target)
                                           for g in gens])
            for k, g in enumerate(gens):
                if k:
                    visit(g.iter, inner, nested, loops)
                for c in g.ifs:
                    visit(c, inner, nested, loops)
            if isinstance(n, ast.DictComp):
                visit(n.key, inner, nested, loops)
                visit(n.value, inner, nested, loops)
            else:
                visit(n.elt, inner, nested, loops)
            return
        sub_loops = loops + [n] if isinstance(n, _LOOPS) else loops
        for c in ast.iter_child_nodes(n):
            visit(c, shadow, nested, sub_loops)

    for s in container.body:
        visit(s, frozenset(), False, [])
    return hits


def _param_table(fn: ast.AST) -> Dict[str, Tuple[Optional[str],
                                                 Optional[str]]]:
    """name -> (annotation dump, default dump) of every parameter."""
    a = fn.args
    pos = a.posonlyargs + a.args
    out: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    pad = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    dump = (lambda x: ast.dump(x) if x is not None else None)
    for arg, d in zip(pos, pad):
        out[arg.arg] = (dump(arg.annotation), dump(d))
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        out[arg.arg] = (dump(arg.annotation), dump(d))
    for arg in (a.vararg, a.kwarg):
        if arg is not None:
            out[arg.arg] = (dump(arg.annotation), None)
    return out


def header_problems(new_fn: ast.AST, ref: Optional[ast.AST]) -> List[str]:
    """M7: what a cut's new header carries beyond `def name(params):`.
    With `ref` (a cut of a whole function body: a closure becoming a module
    function) the old header's decorators, return annotation, `async` and
    each kept parameter's annotation and default are allowed, nothing
    more; a parameter the old header lacks (`st`) carries neither."""
    probs: List[str] = []
    is_async = isinstance(new_fn, ast.AsyncFunctionDef)
    if is_async != (isinstance(ref, ast.AsyncFunctionDef) if ref else False):
        probs.append("async" if is_async else "async dropped")
    dec = [ast.dump(d) for d in new_fn.decorator_list]
    if dec != ([ast.dump(d) for d in ref.decorator_list] if ref else []):
        probs.append("decorators " + (", ".join(ast.unparse(d) for d in
                                                 new_fn.decorator_list)
                                       or "dropped"))
    ret = ast.dump(new_fn.returns) if new_fn.returns is not None else None
    ref_ret = (ast.dump(ref.returns) if ref is not None
               and ref.returns is not None else None)
    if ret != ref_ret:
        probs.append("return annotation "
                     + (ast.unparse(new_fn.returns) if new_fn.returns
                        is not None else "dropped"))
    tp = [ast.dump(t) for t in getattr(new_fn, "type_params", [])]
    if tp != ([ast.dump(t) for t in getattr(ref, "type_params", [])]
              if ref else []):
        probs.append("type parameters")
    old_params = _param_table(ref) if ref is not None else {}
    for name, (ann, dflt) in _param_table(new_fn).items():
        want = old_params.get(name, (None, None))
        if ann != want[0]:
            probs.append(f"annotation of {name!r}")
        if dflt != want[1]:
            probs.append(f"default of {name!r}")
    return probs


def _enclosing_class(tree: ast.Module, qualname: str) -> Optional[str]:
    """The qualname of the innermost class that holds the def `qualname`
    (its nearest def ancestor that is a class), or None."""
    path = def_path(tree, qualname)
    for k in range(len(path) - 2, -1, -1):
        if isinstance(path[k], ast.ClassDef):
            return ".".join(p.name for p in path[:k + 1])
        if isinstance(path[k], _FUNC):
            # a def inside a function: zero-argument super and __class__
            # still see the class around that function
            continue
    return None


def class_bound_uses(stmts: Sequence[ast.AST]) -> List[str]:
    """M8 (E4): names whose meaning comes from the class the code sits in:
    a private `__x` name or attribute (mangled with the class name),
    `super()` without arguments and `__class__`. Nested classes are not
    entered (they bind their own)."""
    out: List[str] = []

    def private(s: str) -> bool:
        return s.startswith("__") and not s.endswith("__")

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.ClassDef):
            return
        if isinstance(n, ast.Attribute) and private(n.attr):
            out.append(f"attribute .{n.attr} at old line {n.lineno}")
        elif isinstance(n, ast.Name) and (private(n.id)
                                          or n.id == "__class__"):
            out.append(f"name {n.id} at old line {n.lineno}")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "super" and not n.args and not n.keywords:
            out.append(f"super() without arguments at old line {n.lineno}")
        for c in ast.iter_child_nodes(n):
            visit(c)

    for s in stmts:
        if isinstance(s, _FUNC):
            for c in ast.iter_child_nodes(s):
                visit(c)
        else:
            visit(s)
    return out


# ---------------------------------------------------------------------------
# Entry check
# ---------------------------------------------------------------------------

@dataclass
class EntryResult:
    entry_id: str
    kind: str
    phase: str
    old_file: str
    old_qualname: str
    new_file: str
    new_qualname: str
    old_lines: str = ""
    new_lines: str = ""
    errors: List[Tuple[str, str]] = field(default_factory=list)
    code_residual: List[str] = field(default_factory=list)
    comment_residual: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    rewrites_used: Dict[str, int] = field(default_factory=dict)
    line_map: List[Tuple[int, int]] = field(default_factory=list)
    # M1: code lines outside every entry (kind "account" only)
    outside: List[str] = field(default_factory=list)
    # what the entry owns, for the spec-level checks (M1 to M4)
    own_old: Optional[Tuple[int, int]] = field(default=None, repr=False)
    own_new: Optional[Tuple[int, int]] = field(default=None, repr=False)
    own_old_comments: Set[int] = field(default_factory=set, repr=False)
    own_new_comments: Set[int] = field(default_factory=set, repr=False)
    map_owners: Dict[str, Tuple[str, str]] = field(default_factory=dict,
                                                   repr=False)

    @property
    def status(self) -> str:
        if self.errors or self.code_residual:
            return "residual"
        if self.comment_residual or self.warnings or self.outside:
            return "review"
        return "clean"

    @property
    def rules_failed(self) -> List[str]:
        out = [r for r, _m in self.errors]
        if self.code_residual:
            out.append("token-mismatch")
        if self.outside:
            out.append("outside-the-entries")
        return sorted(set(out))


def _lines_in(src: Source, lo: int, hi: int) -> List[LogicalLine]:
    return [ll for ll in src.logical if lo <= ll.start <= hi]


def _comments_in(src: Source, lo: int, hi: int) -> List[Tuple[int, str]]:
    return [(r, t) for r, t in src.comments if lo <= r <= hi]


def _code_rows(src: Source) -> set:
    rows = set()
    for ll in src.logical:
        rows.update(range(ll.start, ll.end + 1))
    return rows


def _leading_comments(src: Source, first: int) -> List[Tuple[int, str]]:
    """The contiguous comment block directly above row `first`: comment-only
    lines up to the first blank line, code line or the top of the file
    (B2 of REVIEW_PHASE0: the narration header of a cut block or of a moved
    def belongs to the span's comment diff, PLAN 24.3 (f))."""
    text = {r: t for r, t in src.comments}
    code_rows = _code_rows(src)
    out: List[Tuple[int, str]] = []
    r = first - 1
    while r > 0 and r in text and r not in code_rows:
        out.append((r, text[r]))
        r -= 1
    return out[::-1]


def _row_indent(src: Source, row: int) -> int:
    line = src.line(row)
    return len(line) - len(line.lstrip())


def _trailing_comments(src: Source, last: int,
                       body_col: int) -> List[Tuple[int, str]]:
    """M2: the comment block that ends a span: comment-only lines directly
    below row `last` (no blank line between), indented at least as the
    span's statements, when the code line after them (or the end of the
    file) is indented less, i.e. the block closes the span's block. A
    comment followed by a sibling statement leads that statement and is
    not taken."""
    text = {r: t for r, t in src.comments}
    code_rows = _code_rows(src)
    out: List[Tuple[int, str]] = []
    r = last + 1
    while r <= len(src.lines) and r in text and r not in code_rows \
            and _row_indent(src, r) >= body_col:
        out.append((r, text[r]))
        r += 1
    if not out:
        return []
    while r <= len(src.lines) and r not in code_rows:
        r += 1
    if r <= len(src.lines) and _row_indent(src, r) >= body_col:
        return []
    return out


def _detached_leading(src: Source, first: int,
                      def_col: int) -> List[Tuple[int, str]]:
    """M2 for a moved def: the comment lines above the def's contiguous
    leading block, across blank lines, up to the code line before, that
    stand at the def's own indentation (a deeper comment there ends the
    def before and is that def's trailing block)."""
    text = {r: t for r, t in src.comments}
    code_rows = _code_rows(src)
    r = first - 1
    while r > 0 and r in text and r not in code_rows:
        r -= 1
    out: List[Tuple[int, str]] = []
    while r > 0 and r not in code_rows:
        if r in text:
            if _row_indent(src, r) != def_col:
                break
            out.append((r, text[r]))
        elif src.line(r).strip():
            break
        r -= 1
    return out[::-1]


def _adjacent_comments(src: Source, lo: int, hi: int) -> List[int]:
    rows: List[int] = []
    crow = {r for r, _t in src.comments}
    code_rows = _code_rows(src)
    for step, r in ((-1, lo - 1), (1, hi + 1)):
        while 0 < r <= len(src.lines):
            if r in code_rows:
                break
            if r in crow:
                rows.append(r)
            elif src.line(r).strip():
                break
            r += step
    return sorted(rows)


def _diff_comments(res: EntryResult, old: List[Tuple[int, str]],
                   new: List[Tuple[int, str]]) -> None:
    a = [t.rstrip() for _r, t in old]
    b = [t.rstrip() for _r, t in new]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for k in range(i1, i2):
            what = "changed" if op == "replace" else "removed"
            res.comment_residual.append(
                f"comment {what}: old {res.old_file}:{old[k][0]}: {a[k]}")
        for k in range(j1, j2):
            what = "changed to" if op == "replace" else "added"
            res.comment_residual.append(
                f"comment {what}: new {res.new_file}:{new[k][0]}: {b[k]}")


def _diff_code(res: EntryResult, old_src: Source, old_ll: List[LogicalLine],
               old_keys: List[tuple], new_src: Source,
               new_ll: List[LogicalLine], new_keys: List[tuple]) -> None:
    # old_ll may hold lines R4 dropped; align old_ll with old_keys
    sm = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                res.line_map.append((old_ll[i1 + k].start,
                                     new_ll[j1 + k].start))
            continue
        head = {"replace": "differs", "delete": "only in old",
                "insert": "only in new"}[op]
        parts = [f"code {head}:"]
        for k in range(i1, i2):
            parts.append(f"    - old {old_src.path}:{old_ll[k].start}: "
                         f"{old_src.logical_text(old_ll[k])}")
        for k in range(j1, j2):
            parts.append(f"    + new {new_src.path}:{new_ll[k].start}: "
                         f"{new_src.logical_text(new_ll[k])}")
        res.code_residual.append("\n".join(parts))


def _rewrites(src: Source, span: Span, entry: dict, res: EntryResult,
              name_map: Dict[str, str]) -> Rewrites:
    rw = Rewrites(name_map=dict(name_map))
    for n in mapped_name_nodes(span.stmts, name_map):
        rw.name_pos[(n.lineno, src.char_col(n.lineno, n.col_offset))] = \
            name_map[n.id]
    if span.whole_def:
        return rw
    brk, cont, rets, yields = leaving_jumps(span.stmts)
    sentinel = entry.get("break_sentinel")
    for b in brk:
        if not sentinel:
            res.errors.append(("break-leaves-span",
                               f"break at old line {b.lineno} leaves the "
                               f"span's loop and the spec has no "
                               f"break_sentinel"))
        else:
            rw.break_pos.add((b.lineno, src.char_col(b.lineno,
                                                     b.col_offset)))
    rw.break_sentinel = sentinel or ""
    for c in cont:
        res.errors.append(("continue-leaves-span",
                           f"continue at old line {c.lineno} leaves the "
                           f"span's loop (not on the allowed list)"))
    sentinels = entry.get("sentinel_returns", {}) or {}
    whole_body = list(span.stmts) == list(span.container.body)
    if whole_body:
        # the span is the container's whole body (a closure becoming a
        # function): its returns return from the new function as before
        rets = [r for r in rets if isinstance(r.value, ast.Constant)
                and repr(r.value.value) in sentinels]
    for r in rets:
        v = r.value
        if isinstance(v, ast.Constant) and repr(v.value) in sentinels \
                and v.value in (True, False, None) \
                and type(v.value) in (bool, type(None)):
            rw.const_pos[(v.lineno, src.char_col(v.lineno, v.col_offset))] \
                = sentinels[repr(v.value)]
        else:
            res.errors.append(("return-in-cut",
                               f"return at old line {r.lineno} returns from "
                               f"{getattr(span.container, 'name', '?')}; in "
                               f"the new function it would return from the "
                               f"new function (only declared sentinel "
                               f"returns are allowed)"))
    for y in yields:
        res.errors.append(("yield-in-cut",
                           f"yield at old line {y.lineno} in a cut span"))
    for n in span.stmts:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Nonlocal):
                if entry.get("drop_nonlocal"):
                    rw.drop_rows.add(sub.lineno)
                    for nm in sub.names:
                        if nm not in name_map:
                            res.errors.append(
                                ("nonlocal-name-unmapped",
                                 f"nonlocal {nm!r} (old line {sub.lineno}) "
                                 f"is dropped but {nm!r} is not mapped to "
                                 f"a field"))
    return rw


def _check_cut_bindings(res: EntryResult, entry: dict, span: Span,
                        name_map: Dict[str, str]) -> None:
    """M7 for a cut: distinct sentinels (E17), no live-out local (E8), no
    binding of a name the container declares global or nonlocal (E9)."""
    sentinels: List[Tuple[str, str]] = []
    if entry.get("break_sentinel"):
        sentinels.append(("break", entry["break_sentinel"]))
    for k, v in (entry.get("sentinel_returns") or {}).items():
        sentinels.append((f"return {k}", v))
    seen: Dict[str, str] = {}
    for what, name in sentinels:
        if name in seen:
            res.errors.append((
                "sentinels-not-distinct",
                f"{seen[name]} and {what} both become `return {name}`: the "
                f"caller can no longer tell the two ways out apart"))
        else:
            seen[name] = what
    if list(span.stmts) == list(span.container.body):
        return       # a whole body: its locals were never visible outside
    binds, declared_in = _span_binds(span.stmts)
    free = binds - set(name_map) - declared_in
    declared_out = _declared_outside(span.container, span)
    for name in sorted(free & set(declared_out)):
        res.errors.append((
            "span-binds-global",
            f"the span binds {name!r}, which the old function declares "
            f"global or nonlocal at old line {declared_out[name]}: in the "
            f"new function it would be a local and the old binding is lost"))
    reads = _reads_outside(span.container, span, free - set(declared_out))
    for name in sorted(reads):
        rows = ", ".join(str(r) for r in sorted(set(reads[name])))
        res.errors.append((
            "live-out-local",
            f"the span binds {name!r} (not in the name map) and the old "
            f"function reads it outside the span (old lines {rows}): in the "
            f"new function the binding stays local and is lost"))


def check_entry(entry: dict, read_old, read_new,
                groups: Dict[str, Optional[List[str]]]) -> EntryResult:
    for k in ("id", "kind", "old"):
        if k not in entry:
            raise SpecError(f"entry {entry.get('id', '?')}: missing {k!r}")
    kind = entry["kind"]
    if kind not in ("move", "cut", "delete"):
        raise SpecError(f"entry {entry['id']}: kind {kind!r} is not move, "
                        f"cut or delete")
    old = entry["old"]
    new = entry.get("new") or {}
    new_file = new.get("file", old["file"] if kind == "delete" else "")
    res = EntryResult(entry["id"], kind, str(entry.get("phase", "")),
                      old["file"], old["qualname"], new_file,
                      new.get("qualname", ""))
    if kind != "delete" and not (new.get("file") and new.get("qualname")):
        raise SpecError(f"entry {entry['id']}: a {kind} needs new.file and "
                        f"new.qualname")
    name_map = entry.get("name_map", {}) or {}
    map_errors, map_warnings = validate_map(name_map, groups)
    res.errors += map_errors
    res.warnings += map_warnings
    if map_errors:
        return res          # flagged at map load, before comparing
    old_src = read_old(old["file"])
    new_src = read_new(new_file)
    try:
        span = resolve_old_span(old_src, old, kind)
    except RuleFailure as rf:
        res.errors.append((rf.rule, rf.message))
        return res
    res.old_lines = f"{span.first}-{span.last}"
    res.own_old = (span.first, span.last)
    # B2: the comment block directly above the span is diffed with the span
    # (a delete diffs every comment outside the span with the new file).
    # M2: so are the block that ends the span and, for a move, the block
    # above the def across blank lines; every other comment of the file is
    # the account's (run_spec).
    old_inside = _comments_in(old_src, span.first, span.last)
    if kind == "delete":
        old_lead: List[Tuple[int, str]] = []
        old_trail: List[Tuple[int, str]] = []
    else:
        old_lead = _leading_comments(old_src, span.first)
        body0 = span.stmts[0].body[0] if span.whole_def else span.stmts[0]
        old_trail = _trailing_comments(
            old_src, span.last, old_src.char_col(body0.lineno,
                                                 body0.col_offset))
        if kind == "move":
            old_lead = _detached_leading(
                old_src, span.first, _row_indent(old_src, span.first)) \
                + old_lead
    owned_old = old_lead + old_inside + old_trail
    res.own_old_comments = {r for r, _t in owned_old}
    for r in _adjacent_comments(old_src, span.first, span.last):
        if r in res.own_old_comments:
            continue
        res.info.append(f"comment adjacent to the old span, outside it "
                        f"(the file account diffs it): {old_src.path}:{r}: "
                        f"{old_src.line(r).strip()}")
    if kind == "delete":
        _check_delete(res, entry, old_src, new_src, span, read_new)
        return res
    container_q = _qualname_of(old_src.tree, span.container)
    # M4: every mapped name is a local of the old container (or a nonlocal
    # of a closure in it); its owning scope is kept for the spec-level test
    # that one field comes from one scope.
    for name, target in name_map.items():
        owner, why = map_owner(old_src, container_q, name)
        if owner is None:
            res.errors.append(("map-not-local", f"{name!r} -> {target!r}: "
                               f"{why}"))
        else:
            res.map_owners[target] = (name, f"{old['file']}:{owner}")
    if kind == "cut":
        _check_cut_bindings(res, entry, span, name_map)
    rw = _rewrites(old_src, span, entry, res, name_map)
    old_ll = _lines_in(old_src, span.first, span.last)
    base_old = old_ll[0].depth
    old_keys = keys_for(old_src, old_ll, base_old, rw)
    old_ll_kept = [ll for ll in old_ll if ll.start not in rw.drop_rows]
    try:
        new_fn = find_qualname(new_src.tree, new["qualname"])
    except SpecError as exc:
        res.errors.append(("new-function-missing", str(exc)))
        return res
    if not isinstance(new_fn, _FUNC) and kind == "cut":
        res.errors.append(("new-function-missing",
                           f"{new['qualname']!r} is a class, not a function"))
        return res
    res.own_new = (first_line(new_fn), new_fn.end_lineno)
    if kind == "move":
        n0, n1 = first_line(new_fn), new_fn.end_lineno
        new_ll = _lines_in(new_src, n0, n1)
        c0 = n0
    else:
        header = [ll for ll in new_src.logical if ll.start == new_fn.lineno]
        header_end = header[0].end if header else new_fn.lineno
        n0 = first_line(new_fn.body[0])
        n1 = new_fn.end_lineno
        new_ll = _lines_in(new_src, n0, n1)
        c0 = header_end + 1
        # M7: the header of a cut adds nothing that runs at def time or
        # changes the call: `def name(params):` only, or for a cut of a
        # whole function body the old function's own header parts
        whole_body = list(span.stmts) == list(span.container.body) \
            and isinstance(span.container, _FUNC)
        probs = header_problems(new_fn, span.container if whole_body
                                else None)
        if probs:
            res.errors.append((
                "cut-header",
                f"the new header of a cut is `def name(params):` only"
                + (" (with the old header's own parts)" if whole_body
                   else "") + "; it carries: " + "; ".join(probs)))
        res.info.append("new header (compared for decorators, defaults, "
                        "annotations and async; the free-name check reads "
                        "its parameters): "
                        + " ".join(new_src.line(r).strip() for r in
                                   range(first_line(new_fn), header_end + 1)))
    res.new_lines = f"{n0}-{n1}"
    new_keys = keys_for(new_src, new_ll, new_ll[0].depth, None)
    _diff_code(res, old_src, old_ll_kept, old_keys, new_src, new_ll,
               new_keys)
    res.rewrites_used = dict(rw.used)
    # B2: the old span's leading comment block counts as kept when it stands
    # directly above the new def or inside the new function; dropped, it is
    # a removed comment (residual). M2: the same for the trailing block and
    # a move's block above the def across blank lines.
    new_lead = _leading_comments(new_src, first_line(new_fn))
    if kind == "move":
        new_lead = _detached_leading(new_src, first_line(new_fn),
                                     _row_indent(new_src, first_line(new_fn))) \
            + new_lead
    nbody0 = new_fn.body[0]
    new_trail = _trailing_comments(
        new_src, n1, new_src.char_col(nbody0.lineno, nbody0.col_offset))
    owned_new = new_lead + _comments_in(new_src, c0, n1) + new_trail
    res.own_new_comments = {r for r, _t in owned_new}
    _diff_comments(res, owned_old, owned_new)
    for r in _adjacent_comments(new_src, first_line(new_fn), n1):
        if r in res.own_new_comments:
            continue
        res.info.append(f"comment adjacent to the new function, outside it: "
                        f"{new_src.path}:{r}: {new_src.line(r).strip()}")
    # M8 (E4): code whose class changes must not lean on the class
    old_cls_key = _enclosing_class(old_src.tree, container_q)
    new_cls_key = _enclosing_class(new_src.tree, new["qualname"])
    if (old["file"], old_cls_key) != (new_file, new_cls_key) \
            and (old_cls_key or new_cls_key):
        for use in class_bound_uses(span.stmts):
            res.errors.append((
                "class-bound-name",
                f"{use}: its meaning comes from the class, and the class "
                f"changes ({old['file']}:{old_cls_key or '(none)'} -> "
                f"{new_file}:{new_cls_key or '(none)'})"))
    # free names. REVIEW_PHASE0 item 6 narrowed (M8): the globals the old
    # span read are its Name loads (and augmented targets), not every NAME
    # token (attribute and keyword spellings are no reads of a global).
    old_names: Set[str] = set()
    for s in span.stmts:
        for n in ast.walk(s):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                old_names.add(n.id)
            elif isinstance(n, ast.AugAssign) \
                    and isinstance(n.target, ast.Name):
                old_names.add(n.target.id)
    old_cls = None
    parts = old["qualname"].split(".")
    if kind == "move" and len(parts) >= 2:
        try:
            if isinstance(find_qualname(old_src.tree, ".".join(parts[:-1])),
                          ast.ClassDef):
                old_cls = ".".join(parts[:-1])
        except SpecError:
            old_cls = None
    sentinel_names = set((entry.get("sentinel_returns") or {}).values())
    if entry.get("break_sentinel"):
        sentinel_names.add(entry["break_sentinel"])
    fr = check_free_names(new_src, new["qualname"], old_src, container_q,
                          old_names, sentinel_names, old_cls)
    res.errors += [("free-name", m) for m in fr.errors]
    res.warnings += fr.warnings
    res.info += fr.info
    return res


def _qualname_of(tree: ast.Module, target: ast.AST) -> str:
    def walk(node, prefix):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, _DEF):
                q = f"{prefix}.{c.name}" if prefix else c.name
                if c is target:
                    return q
                got = walk(c, q)
                if got:
                    return got
            elif not isinstance(c, (ast.Lambda,) + _COMPS):
                got = walk(c, prefix)
                if got:
                    return got
        return None
    return walk(tree, "") or ""


def _check_delete(res: EntryResult, entry: dict, old_src: Source,
                  new_src: Source, span: Span, read_new) -> None:
    res.new_qualname = ""
    rest = [ll for ll in old_src.logical
            if not span.first <= ll.start <= span.last]
    old_keys = keys_for(old_src, rest, 0, None)
    new_keys = keys_for(new_src, new_src.logical, 0, None)
    _diff_code(res, old_src, rest, old_keys, new_src, new_src.logical,
               new_keys)
    inside = _comments_in(old_src, span.first, span.last)
    for r, t in inside:
        res.comment_residual.append(f"comment removed with the deleted "
                                    f"span: old {old_src.path}:{r}: {t}")
    outside = [(r, t) for r, t in old_src.comments
               if not span.first <= r <= span.last]
    _diff_comments(res, outside, new_src.comments)
    name = span.container.name
    files = [res.new_file] + list(entry.get("reference_scan", []) or [])
    for f in files:
        src = new_src if f == res.new_file else read_new(f)
        hits = [ll.start for ll in src.logical for t in ll.toks
                if t.type == "NAME" and t.string == name]
        for row in hits:
            res.errors.append(("reference-remains",
                               f"NAME {name!r} still appears at "
                               f"{src.path}:{row}"))


# ---------------------------------------------------------------------------
# Spec, outputs, CLI
# ---------------------------------------------------------------------------

def load_spec(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SpecError(f"spec {path}: {exc}") from exc
    if not isinstance(spec, dict) or not isinstance(spec.get("entries"),
                                                    list):
        raise SpecError(f"spec {path}: needs an 'entries' list")
    if spec.get("spec_version", SPEC_VERSION) != SPEC_VERSION:
        raise SpecError(f"spec {path}: spec_version "
                        f"{spec.get('spec_version')} is not {SPEC_VERSION}")
    ids = [e.get("id") for e in spec["entries"]]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise SpecError(f"spec {path}: duplicate entry ids {dup}")
    return spec


def file_reader(root: Optional[str], ref: Optional[str], repo: Optional[str]):
    cache: Dict[str, Source] = {}

    def read(rel: str) -> Source:
        if rel in cache:
            return cache[rel]
        if ref:
            try:
                raw = subprocess.run(
                    ["git", "-C", repo or ".", "show", f"{ref}:{rel}"],
                    check=True, capture_output=True).stdout
            except (OSError, subprocess.CalledProcessError) as exc:
                raise SpecError(f"git show {ref}:{rel}: {exc}") from exc
            # universal newlines, as Python compiles source: a CRLF
            # checkout and an LF one give the same tokens
            text = raw.decode("utf-8").replace("\r\n", "\n")
            shown = f"{ref}:{rel}"
        else:
            p = os.path.join(root or ".", rel)
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as exc:
                raise SpecError(f"{p}: {exc}") from exc
            shown = rel
        cache[rel] = scan_source(text, shown)
        return cache[rel]

    return read


def _overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def check_disjoint(results: List[EntryResult]) -> None:
    """M3 (E6): old spans of one spec are pairwise disjoint, new functions
    too, and a new function is the home of one entry."""
    for i, a in enumerate(results):
        for b in results[i + 1:]:
            if a.own_old and b.own_old and a.old_file == b.old_file \
                    and _overlap(a.own_old, b.own_old):
                for x, y in ((a, b), (b, a)):
                    x.errors.append((
                        "spans-overlap",
                        f"old span {x.old_file}:{x.own_old[0]}-"
                        f"{x.own_old[1]} overlaps entry {y.entry_id} "
                        f"({y.own_old[0]}-{y.own_old[1]}): one old line "
                        f"has one new home"))
            if a.kind != "delete" and b.kind != "delete" \
                    and a.new_file == b.new_file and (
                        a.new_qualname == b.new_qualname
                        or (a.own_new and b.own_new
                            and _overlap(a.own_new, b.own_new))):
                for x, y in ((a, b), (b, a)):
                    x.errors.append((
                        "new-home-shared",
                        f"{x.new_file}:{x.new_qualname} is also the home "
                        f"(or holds the home) of entry {y.entry_id}: a new "
                        f"function is the home of one entry"))


def check_map_owners(results: List[EntryResult]) -> None:
    """M4 (F4x): one target field in two entries comes from one owning
    scope (the same local of the same old function)."""
    by_target: Dict[str, List[Tuple[EntryResult, str, str]]] = {}
    for r in results:
        for target, (name, owner) in r.map_owners.items():
            by_target.setdefault(target, []).append((r, name, owner))
    for target, uses in sorted(by_target.items()):
        owners = sorted({o for _r, _n, o in uses})
        if len(owners) > 1:
            for r, name, owner in uses:
                r.errors.append((
                    "map-field-two-scopes",
                    f"{target!r} is mapped from {name!r} of {owner} here and "
                    f"from locals of {', '.join(o for o in owners if o != owner)}"
                    f" in other entries: two variables would become one "
                    f"field"))


def _state_fields(src: Source, cls: ast.ClassDef, depth: int = 0) -> Set[str]:
    """Fields a state class declares: names assigned or annotated in its
    body, `self.<x>` stores in its methods, and the same of a base class
    of the same file."""
    out: Set[str] = set()
    for s in cls.body:
        if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
            out.add(s.target.id)
        elif isinstance(s, ast.Assign):
            for t in s.targets:
                out |= _target_names(t)
    for n in ast.walk(cls):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) \
                and isinstance(n.value, ast.Name) and n.value.id == "self":
            out.add(n.attr)
    if depth < 8:
        for b in cls.bases:
            if isinstance(b, ast.Name):
                try:
                    base = find_qualname(src.tree, b.id)
                except SpecError:
                    continue
                if isinstance(base, ast.ClassDef):
                    out |= _state_fields(src, base, depth + 1)
    return out


def check_state_classes(spec: dict, results: List[EntryResult],
                        read_new) -> None:
    """M5 (E7): the spec names the state classes, `state_classes`:
    {"file": ..., "groups": {group: class qualname}, "root": optional class
    that must declare each group}; every mapped target st.<group>.<field>
    is a field its group's class declares."""
    entries = spec["entries"]
    mapped = [(e, r) for e, r in zip(entries, results) if e.get("name_map")]
    if not mapped:
        return
    sc = spec.get("state_classes")
    if not isinstance(sc, dict) or not sc.get("file") \
            or not isinstance(sc.get("groups"), dict):
        for _e, r in mapped:
            r.errors.append((
                "state-classes-not-named",
                "the entry maps names to fields, but the spec names no "
                "state classes (`state_classes`: file, groups, optional "
                "root)"))
        return
    try:
        src = read_new(sc["file"])
    except SpecError as exc:
        for _e, r in mapped:
            r.errors.append(("state-class-missing", str(exc)))
        return
    fields: Dict[str, Optional[Set[str]]] = {}
    for group, qual in sc["groups"].items():
        try:
            cls = find_qualname(src.tree, qual)
            fields[group] = (_state_fields(src, cls)
                             if isinstance(cls, ast.ClassDef) else None)
        except SpecError:
            fields[group] = None
    root_fields = None
    if sc.get("root"):
        try:
            root = find_qualname(src.tree, sc["root"])
            root_fields = (_state_fields(src, root)
                           if isinstance(root, ast.ClassDef) else set())
        except SpecError:
            root_fields = set()
    for e, r in mapped:
        for name, target in e["name_map"].items():
            parts = str(target).split(".")
            if len(parts) != 3:
                r.errors.append(("map-field-not-declared",
                                 f"{target!r}: a state target is "
                                 f"st.<group>.<field>"))
                continue
            group, fld = parts[1], parts[2]
            if group not in fields:
                r.errors.append(("map-field-not-declared",
                                 f"{target!r}: the spec's state_classes "
                                 f"name no class for group {group!r}"))
            elif fields[group] is None:
                r.errors.append(("state-class-missing",
                                 f"{target!r}: class "
                                 f"{sc['groups'][group]!r} of group "
                                 f"{group!r} is not in {sc['file']}"))
            elif fld not in fields[group]:
                r.errors.append(("map-field-not-declared",
                                 f"{target!r}: class "
                                 f"{sc['groups'][group]} ({sc['file']}) "
                                 f"declares no field {fld!r}"))
            if root_fields is not None and group not in root_fields:
                r.errors.append(("map-field-not-declared",
                                 f"{target!r}: the root class "
                                 f"{sc['root']} declares no group "
                                 f"{group!r}"))


def _read_or_empty(read, rel: str) -> Source:
    try:
        return read(rel)
    except SpecError:
        return scan_source("", f"{rel} (absent)")


def account_files(spec: dict, results: List[EntryResult], read_old,
                  read_new) -> List[EntryResult]:
    """M1 and M2: one account per touched file. The old logical lines
    minus every old span against the new logical lines minus every new
    function, by the same token keys and no rewrite; the comments no entry
    owns, old against new. Each difference is printed "outside the
    entries" (status review, exit 3), so every changed line of the phase is
    either matched by an entry or printed for R."""
    files: List[str] = []
    for r in results:
        for f in (r.old_file, r.new_file):
            if f and f not in files:
                files.append(f)
    sc = spec.get("state_classes")
    if isinstance(sc, dict) and sc.get("file") and sc["file"] not in files:
        files.append(sc["file"])
    for f in spec.get("account_files", []) or []:
        if f not in files:
            files.append(f)
    out: List[EntryResult] = []
    for f in sorted(files):
        old_src = _read_or_empty(read_old, f)
        new_src = _read_or_empty(read_new, f)
        acc = EntryResult(f"outside:{f}", "account", "", f, "", f, "")
        old_ex = [r.own_old for r in results
                  if r.old_file == f and r.own_old]
        new_ex = [r.own_new for r in results
                  if r.kind != "delete" and r.new_file == f and r.own_new]
        old_ll = [ll for ll in old_src.logical
                  if not any(a <= ll.start <= b for a, b in old_ex)]
        new_ll = [ll for ll in new_src.logical
                  if not any(a <= ll.start <= b for a, b in new_ex)]
        tmp = EntryResult(acc.entry_id, "account", "", f, "", f, "")
        _diff_code(tmp, old_src, old_ll, keys_for(old_src, old_ll, 0, None),
                   new_src, new_ll, keys_for(new_src, new_ll, 0, None))
        acc.outside = ["outside the entries, " + c for c in tmp.code_residual]
        old_owned: Set[int] = set()
        new_owned: Set[int] = set()
        for r in results:
            if r.old_file == f:
                old_owned |= r.own_old_comments
            if r.kind != "delete" and r.new_file == f:
                new_owned |= r.own_new_comments
        _diff_comments(acc, [(r, t) for r, t in old_src.comments
                             if r not in old_owned],
                       [(r, t) for r, t in new_src.comments
                        if r not in new_owned])
        acc.comment_residual = ["outside the entries, " + c
                                for c in acc.comment_residual]
        acc.old_lines = f"{len(old_ll)} lines outside the old spans"
        acc.new_lines = f"{len(new_ll)} lines outside the new functions"
        out.append(acc)
    return out


def run_spec(spec: dict, read_old, read_new) -> List[EntryResult]:
    """The entries, then the spec-level checks M3 to M5 on them, then one
    account per touched file (kind "account", after the entries)."""
    groups = spec.get("groups") or DEFAULT_GROUPS
    results = [check_entry(e, read_old, read_new, groups)
               for e in spec["entries"]]
    check_disjoint(results)
    check_map_owners(results)
    check_state_classes(spec, results, read_new)
    return results + account_files(spec, results, read_old, read_new)


def entry_results(results: List[EntryResult]) -> List[EntryResult]:
    return [r for r in results if r.kind != "account"]


def format_result(res: EntryResult) -> str:
    if res.kind == "account":
        out = [f"account {res.old_file}: everything outside the entries "
               f"({res.old_lines}; {res.new_lines})"]
    else:
        out = [f"entry {res.entry_id} [{res.phase}] {res.kind}: "
               f"{res.old_file}:{res.old_qualname} [{res.old_lines or '?'}]"
               f" -> {res.new_file or '(none)'}:"
               f"{res.new_qualname or '(none)'} [{res.new_lines or '-'}]"]
    for r in res.outside:
        out.append("  OUTSIDE " + r.replace("\n", "\n  "))
    if res.rewrites_used:
        out.append("  rewrites used: " + ", ".join(
            f"{k} x{v}" for k, v in sorted(res.rewrites_used.items())))
    for rule, msg in res.errors:
        out.append(f"  FAIL {rule}: {msg}")
    for r in res.code_residual:
        out.append("  RESIDUAL " + r.replace("\n", "\n  "))
    for r in res.comment_residual:
        out.append(f"  RESIDUAL {r}")
    for w in res.warnings:
        out.append(f"  WARN {w}")
    for i in res.info:
        out.append(f"  INFO {i}")
    verdict = {"clean": "clean", "review": "review (comments, warnings or "
               "lines outside the entries only; R reads them)", "residual": "RESIDUAL ("
               + ", ".join(res.rules_failed) + ")"}[res.status]
    out.append(f"  RESULT: {verdict}")
    return "\n".join(out)


MAP_HEADER = ["old_file", "old_qualname", "new_file", "new_qualname",
              "phase", "kind", "old_lines", "new_lines", "entry", "status"]


def write_map(path: str, results: List[EntryResult]) -> None:
    rows: List[List[str]] = []
    results = entry_results(results)
    ids = {r.entry_id for r in results}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        for line in lines[1:]:
            cols = line.split("\t")
            if len(cols) == len(MAP_HEADER) and cols[8] not in ids:
                rows.append(cols)
    for r in results:
        rows.append([r.old_file, r.old_qualname, r.new_file or "",
                     r.new_qualname or "", r.phase, r.kind, r.old_lines,
                     r.new_lines, r.entry_id, r.status])
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(MAP_HEADER) + "\n")
        for row in rows:
            fh.write("\t".join(row) + "\n")


def write_line_map(path: str, results: List[EntryResult]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("entry\told_file\told_line\tnew_file\tnew_line\n")
        for r in entry_results(results):
            for a, b in r.line_map:
                fh.write(f"{r.entry_id}\t{r.old_file}\t{a}\t{r.new_file}\t"
                         f"{b}\n")


def exit_code(results: List[EntryResult]) -> int:
    st = {r.status for r in results}
    if "residual" in st:
        return 1
    if "review" in st:
        return 3
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("--old-root")
    ap.add_argument("--old-ref")
    ap.add_argument("--repo")
    ap.add_argument("--new-root")
    ap.add_argument("--map", dest="map_path")
    ap.add_argument("--line-map")
    ap.add_argument("--json", dest="json_path")
    a = ap.parse_args(argv)
    try:
        spec = load_spec(a.spec)
        spec_dir = os.path.dirname(os.path.abspath(a.spec))
        old_root = a.old_root or spec.get("old_root")
        new_root = a.new_root or spec.get("new_root")
        if old_root and not os.path.isabs(old_root) and not a.old_root:
            old_root = os.path.join(spec_dir, old_root)
        if new_root and not os.path.isabs(new_root) and not a.new_root:
            new_root = os.path.join(spec_dir, new_root)
        read_old = file_reader(old_root, a.old_ref, a.repo)
        read_new = file_reader(new_root, None, None)
        print(f"move_check: python {sys.version.split()[0]}, spec "
              f"{a.spec}, {len(spec['entries'])} entries")
        results = run_spec(spec, read_old, read_new)
    except SpecError as exc:
        print(f"move_check: cannot run: {exc}", file=sys.stderr)
        return 2
    for r in results:
        print(format_result(r))
    if a.map_path:
        write_map(a.map_path, results)
        print(f"MIGRATION_MAP rows written: {a.map_path}")
    else:
        print("MIGRATION_MAP rows (not written, no --map):")
        for r in entry_results(results):
            print("  " + "\t".join([r.old_file, r.old_qualname,
                                    r.new_file or "", r.new_qualname or "",
                                    r.phase, r.kind]))
    if a.line_map:
        write_line_map(a.line_map, results)
    if a.json_path:
        with open(a.json_path, "w", encoding="utf-8") as fh:
            json.dump([dict(entry=r.entry_id, kind=r.kind, status=r.status,
                            rules_failed=r.rules_failed, outside=r.outside,
                            errors=r.errors, code_residual=r.code_residual,
                            comment_residual=r.comment_residual,
                            warnings=r.warnings, info=r.info,
                            old_lines=r.old_lines, new_lines=r.new_lines,
                            rewrites_used=r.rewrites_used)
                       for r in results], fh, indent=1, ensure_ascii=False)
    code = exit_code(results)
    print(f"move_check: exit {code}")
    return code


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
