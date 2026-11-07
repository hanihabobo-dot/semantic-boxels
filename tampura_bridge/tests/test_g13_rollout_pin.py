"""#P4 path 6, DV-1: G13's amendment, arm T's rollout wrapper.

The check compares the wrapper with g13_runtime.REVIEWED_ARM_T_ROLLOUT as
code and requires their Policy.rollout to be reached unchanged.  These tests
use plain classes standing in for their Policy and TampuraPolicy, so they
need neither their packages nor pybullet; the real classes are exercised in
test_g13_runtime.py (arm-O venv with their trees on PYTHONPATH).
"""
import ast
import os

import pytest

from tampura_bridge import g13_runtime as g13


class Policy:
    def rollout(self, env, b, store):
        return ('their history', store)


class TampuraPolicy(Policy):
    pass


class Good(TampuraPolicy):
    def rollout(self, env, b, store):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return out


class GoodWithDocAndComments(TampuraPolicy):
    def rollout(self, env, b, store):
        """Their rollout, then the one read."""
        # the call is theirs, unchanged
        out = super().rollout(env, b, store)

        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return out


class ExtraStatement(TampuraPolicy):
    def rollout(self, env, b, store):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        store = None
        return out


class ReadBeforeTheirRollout(TampuraPolicy):
    def rollout(self, env, b, store):
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        out = super().rollout(env, b, store)
        return out


class OtherFolder(TampuraPolicy):
    def rollout(self, env, b, store):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, '/tmp/elsewhere')  # noqa: F821
        return out


class ChangesTheResult(TampuraPolicy):
    def rollout(self, env, b, store):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return None


class CallsBaseDirectly(TampuraPolicy):
    def rollout(self, env, b, store):
        out = Policy.rollout(self, env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return out


class OtherSignature(TampuraPolicy):
    def rollout(self, env, b, store, extra=None):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return out


def _decorated(fn):
    return fn


class Decorated(TampuraPolicy):
    @_decorated
    def rollout(self, env, b, store):
        out = super().rollout(env, b, store)
        final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
        return out


class NoWrapper(TampuraPolicy):
    pass


class TheirPolicyOverridden(Policy):
    def rollout(self, env, b, store):            # their TampuraPolicy changed
        return ('patched', store)


def failures(cls, base=Policy, mid=TampuraPolicy):
    return g13.rollout_wrapper_failures(cls, base, mid)


def test_the_reviewed_wrapper_passes():
    assert failures(Good) == []


def test_comments_docstring_and_layout_do_not_reopen_the_review():
    assert failures(GoodWithDocAndComments) == []


@pytest.mark.parametrize('cls', [ExtraStatement, ReadBeforeTheirRollout, OtherFolder,
                                 ChangesTheResult, CallsBaseDirectly, OtherSignature,
                                 Decorated])
def test_any_other_code_fails(cls):
    assert failures(cls) == [f'{cls.__qualname__}.rollout is not the reviewed wrapper']


def test_a_class_without_the_wrapper_fails():
    assert failures(NoWrapper) == ['NoWrapper has no rollout wrapper']


def test_their_rollout_must_be_reached_unchanged():
    class Mid(TheirPolicyOverridden):
        rollout = TheirPolicyOverridden.rollout

    class Wrapped(Mid):
        def rollout(self, env, b, store):
            out = super().rollout(env, b, store)
            final_world.record_after_rollout(env, self.config['save_dir'])  # noqa: F821
            return out
    assert 'TampuraPolicy.rollout is not Policy.rollout' in g13.rollout_wrapper_failures(
        Wrapped, Policy, Mid)


def test_normal_form_ignores_layout_and_docstring_only():
    one = g13._normal_def('def f(self):\n    return 1\n')
    two = g13._normal_def('    def f(self):\n        """doc"""\n        # c\n\n        return 1\n')
    assert one == two
    assert one != g13._normal_def('def f(self):\n    return 2\n')
    assert one != g13._normal_def('def g(self):\n    return 1\n')
    assert one != g13._normal_def('def f(self, x):\n    return 1\n')


def test_the_and_helper_keeps_the_arm_o_message():
    assert g13._and(['__init__', 'get_action']) == '__init__ and get_action'
    assert g13._and(['__init__', 'get_action', 'rollout']) == '__init__, get_action and rollout'
    assert g13._and(['x']) == 'x'


def test_the_class_in_timed_policy_carries_exactly_the_reviewed_body():
    """timed_policy.py needs their packages to import, so read its source."""
    path = os.path.join(g13.REPO, 'tampura_bridge', 'timed_policy.py')
    with open(path, encoding='utf-8') as f:
        text = f.read()
    cls = next(n for n in ast.parse(text).body
               if isinstance(n, ast.ClassDef) and n.name == 'TampuraPolicyTimed')
    methods = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
    assert sorted(methods) == ['__init__', 'get_action', 'rollout']
    rollout = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'rollout')
    assert g13._normal_def(ast.get_source_segment(text, rollout)) == \
        g13._normal_def(g13.REVIEWED_ARM_T_ROLLOUT)
    # and the module imports the reader the wrapper names
    assert 'final_world' in text.split('PLANNER_NAME', 1)[0]
