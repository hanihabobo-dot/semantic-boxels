"""TB-9: a run prints its console header once.

test_full_pipeline.main called console_ui.header twice from db3f374 on
(BF#59's scaffolding): the second call sat inside the audit #10 comment,
split it in two and lacked the slip-fixes text, so every run printed
"Mission: ..." and the switches line twice.  The fix keeps the first call.

The check reads the source (ast), so it starts no episode: one
console_ui.header call in the whole module, inside main(), on main's
straight path (no loop and no branch around it), and it carries the
slip-fixes text.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'test_full_pipeline.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)


def _is_header_call(node) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'header'
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'console_ui')


def _header_calls(tree):
    return [n for n in ast.walk(tree) if _is_header_call(n)]


def _main():
    mains = [n for n in TREE.body
             if isinstance(n, ast.FunctionDef) and n.name == 'main']
    assert len(mains) == 1
    return mains[0]


def test_one_header_call_in_the_module():
    calls = _header_calls(TREE)
    assert len(calls) == 1, [c.lineno for c in calls]


def test_the_header_call_is_a_statement_of_main_itself():
    # A statement of main's own body: not under a loop, an if or a try,
    # so every run reaches it exactly once.
    top = [s for s in _main().body
           if isinstance(s, ast.Expr) and _is_header_call(s.value)]
    assert len(top) == 1


def test_the_header_names_the_slip_fixes():
    call = _header_calls(TREE)[0]
    switches = [k.value for k in call.keywords if k.arg == 'switches']
    assert len(switches) == 1
    assert 'slip_fixes.spec()' in ast.unparse(switches[0])


def test_the_audit_10_comment_is_whole_again():
    # The second call had split this comment after "at the requested".
    lines = SOURCE.splitlines()
    i = next(k for k, ln in enumerate(lines)
             if ln.rstrip().endswith('free-space dispatch and (re)build '
                                     'the lattice at the requested'))
    assert lines[i + 1].lstrip().startswith('# cell size before any boxel')
