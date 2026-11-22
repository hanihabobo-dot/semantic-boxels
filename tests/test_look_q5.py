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

from test_eye_switch import MAIN, _calls, _holder  # noqa: E402

# MAIN is main() with the functions cut out of it (test_eye_switch).  Since
# main() was cut the look branch stands in dispatch_step and its body is one
# statement, the call of do_look; the statements the branch held are the
# body of do_look, with the names of the episode state st, and a ``break``
# out of the plan's loop is ``return True`` there, passed on by the branch
# and turned into the break at the one call of dispatch_step.


def _look_branch():
    """The body of main()'s ``elif action_name == 'look'``: the body of
    do_look, which that branch, and nothing else, calls."""
    (branch,) = [n for n in ast.walk(MAIN) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "action_name == 'look'"]
    (passing,) = branch.body
    assert ast.unparse(passing) == 'if do_look(st, env, params):\n    return True'
    assert len(_calls(MAIN, 'do_look')) == 1
    (do_look,) = [f for f in MAIN.body if f.name == 'do_look']
    return do_look.body


def _a_true_of_the_branch_breaks_the_plan():
    """The function that holds the look branch is called once, by the plan's
    loop, and its True is that loop's break."""
    (branch,) = [n for n in ast.walk(MAIN) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "action_name == 'look'"]
    (call,) = _calls(MAIN, _holder(branch).name)
    (loop,) = [n for n in ast.walk(_holder(call)) if isinstance(n, ast.For)
               and any(s is call for b in n.body for s in ast.walk(b))]
    return (ast.unparse(loop.iter) == 'enumerate(st.round.plan)' and len(loop.body) == 1
            and isinstance(loop.body[0], ast.If) and loop.body[0].test is call
            and len(loop.body[0].body) == 1 and isinstance(loop.body[0].body[0], ast.Break)
            and not loop.body[0].orelse)


def _ancestors_tests(node):
    """The tests of every ``if`` that holds ``node`` in its body or its else,
    in the function that holds the node and, through the one call of that
    function, on up to main()."""
    out = []
    while True:
        fn = _holder(node)
        for n in ast.walk(fn):
            if isinstance(n, ast.If) and n is not node:
                inner = {id(m) for s in n.body + n.orelse for m in ast.walk(s)}
                if id(node) in inner:
                    out.append(ast.unparse(n.test))
        if fn.name == 'main':
            return out
        (node,) = _calls(MAIN, fn.name)


def test_a_look_that_registers_a_body_ends_the_plan_for_a_replan():
    body = _look_branch()
    (rule,) = [s for s in body if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'look_result.registered']
    assert [ast.literal_eval(c.args[0]) for c in _calls(rule, 'dispatch_end')] == \
        ['look_outcome']
    assert ast.unparse(rule.body[-1]) == 'return True' and not rule.orelse
    assert _a_true_of_the_branch_breaks_the_plan()
    # After the unconditional-effects rule and the strike reset, as the last
    # statement of the branch: a look that registered nothing goes on as before.
    (cont,) = [i for i, s in enumerate(body) if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'not look_result.continue_']
    (reset,) = [i for i, s in enumerate(body) if isinstance(s, ast.Expr)
                and ast.unparse(s) == 'st.counts.observe_strikes.pop(obj_str, None)']
    assert cont < reset < body.index(rule) == len(body) - 1


def test_the_rule_holds_in_every_look_mode_and_with_either_eye():
    body = _look_branch()
    (rule,) = [s for s in body if isinstance(s, ast.If)
               and ast.unparse(s.test) == 'look_result.registered']
    tests = _ancestors_tests(rule)
    assert "action_name == 'look'" in tests
    assert not [t for t in tests if 'eye' in t or 'look_mode' in t], tests
