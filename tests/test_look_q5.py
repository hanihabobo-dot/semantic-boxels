"""Q5 (Hani's decision, tracks/look/Q4_Q6_CHECK.md): a look whose image
registered a body the belief did not hold ends the plan for a replan, with
the look's own dispatch status; a look that registered nothing goes on with
the plan (Q6).  It is a loop rule in main()'s look branch, the same in every
look mode and with --eye fixed or --eye arm.  An AST test on that branch, no
episode.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_eye_switch import MAIN, _calls  # noqa: E402


def _look_branch():
    """The body of main()'s ``elif action_name == 'look'``."""
    (branch,) = [n for n in ast.walk(MAIN) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "action_name == 'look'"]
    return branch.body


def _ancestors_tests(node):
    """The tests of every ``if`` in main() that holds ``node`` in its body or
    its else."""
    out = []
    for n in ast.walk(MAIN):
        if isinstance(n, ast.If) and n is not node:
            inner = {id(m) for s in n.body + n.orelse for m in ast.walk(s)}
            if id(node) in inner:
                out.append(ast.unparse(n.test))
    return out


def test_a_look_that_registers_a_body_ends_the_plan_for_a_replan():
    body = _look_branch()
    (rule,) = [s for s in body if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'look_result.registered']
    assert [ast.literal_eval(c.args[0]) for c in _calls(rule, 'dispatch_end')] == \
        ['look_outcome']
    assert isinstance(rule.body[-1], ast.Break) and not rule.orelse
    # After the unconditional-effects rule and the strike reset, as the last
    # statement of the branch: a look that registered nothing goes on as before.
    (cont,) = [i for i, s in enumerate(body) if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'not look_result.continue_']
    (reset,) = [i for i, s in enumerate(body) if isinstance(s, ast.Expr)
                and ast.unparse(s) == 'observe_strikes.pop(obj_str, None)']
    assert cont < reset < body.index(rule) == len(body) - 1


def test_the_rule_holds_in_every_look_mode_and_with_either_eye():
    body = _look_branch()
    (rule,) = [s for s in body if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'look_result.registered']
    tests = _ancestors_tests(rule)
    assert "action_name == 'look'" in tests
    assert not [t for t in tests if 'eye' in t or 'look_mode' in t], tests
