"""#P4 GF1: G13's runtime half (PAPER_AUDIT.txt P4.1 G13, BF#14 GF1).

Checked once per run, right before their rollout, and recorded in the run's
g13_runtime.json; any failure stops the run (a per-run gate, P4.6):
  - registrations: arm O registers exactly one schema, boxel_episode, whose
    execute_fn is ours, and no class of ours sits in their env or planner
    registry; arm T registers tampura_policy_timed -> TampuraPolicyTimed and
    nothing else of ours, and no schema of ours exists;
  - arm O: type(policy).rollout is their Policy.rollout and the policy class
    of ours defines __init__ and get_action and nothing else;
  - arm T (amended for DV-1, Hani 2026-11-07): their Policy.rollout is
    reached unchanged through TampuraPolicy (TampuraPolicy.rollout is
    Policy.rollout), the policy class of ours defines __init__, get_action
    and rollout and nothing else, and its rollout is compared as code (the
    abstract syntax tree, comments and docstring aside) with
    REVIEWED_ARM_T_ROLLOUT: their rollout through super(), then one read of
    their final world (tampura_bridge/final_world.py), then the result
    returned unchanged;
  - arm O: the env has no instance attribute 'step' (on arm T no code of ours
    ever holds the env);
  - no monkeypatch: every function in the __dict__ of their Policy,
    TampuraPolicy, their registered env classes and (arm O) the belief's class
    comes from their own modules;
  - every loaded tampura / tampura_environments module lies in their checkout
    or is byte-identical to the checkout's file (arm T imports the
    site-packages copy of tampura, BF#14 RG1.3);
  - arm O: the env adapter inherits BoxelTestEnv.sync_to_plan_client (the G8(c)
    wrapper cannot be bypassed by an override).
Their checkout root is found from the loaded tampura_environments package
(their editable or PYTHONPATH checkout on both arms), or $TAMPURA_WORK.
"""
import ast
import inspect
import json
import os
import sys
import textwrap

THEIR_ROOTS = ('tampura', 'tampura_environments')
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

# The one body of rollout G13 accepts on arm T (DV-1's amendment): any other
# code in that method, or a second method, fails the run.  Compared as code
# by rollout_wrapper_failures; a change here and in timed_policy.py is a
# change to the protocol (PAPER_AUDIT P4.6: any later change is a BF# entry).
REVIEWED_ARM_T_ROLLOUT = '''
def rollout(self, env, b, store):
    out = super().rollout(env, b, store)
    final_world.record_after_rollout(env, self.config['save_dir'])
    return out
'''


def _ours(obj):
    """True when obj was defined in a file of this repo (the drivers' __main__ included)."""
    mod = sys.modules.get(getattr(obj, '__module__', None) or '')
    f = getattr(mod, '__file__', None)
    return bool(f) and os.path.realpath(f).startswith(REPO + os.sep)


def _tw():
    if os.environ.get('TAMPURA_WORK'):
        return os.path.realpath(os.environ['TAMPURA_WORK'])
    import tampura_environments
    # <TW>/tampura_environments/tampura_environments/__init__.py
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.realpath(tampura_environments.__file__))))


def _module_files(tw):
    """Every loaded module of their two packages: in the checkout, or a
    byte-identical copy of the checkout's file.  Returns (counts, failures)."""
    counts = {'in_checkout': 0, 'identical_copy': 0}
    failures = []
    for root in THEIR_ROOTS:
        pkg = sys.modules.get(root)
        if pkg is None or not getattr(pkg, '__file__', None):
            continue
        loaded_dir = os.path.dirname(os.path.realpath(pkg.__file__))
        checkout_dir = os.path.join(tw, root, root)
        for name, mod in list(sys.modules.items()):
            if name.split('.')[0] != root:
                continue
            f = getattr(mod, '__file__', None)
            if not f:
                continue
            f = os.path.realpath(f)
            if f.startswith(os.path.join(tw, root) + os.sep):
                counts['in_checkout'] += 1
                continue
            twin = os.path.join(checkout_dir, os.path.relpath(f, loaded_dir))
            same = False
            if os.path.isfile(twin):
                with open(f, 'rb') as a, open(twin, 'rb') as b:
                    same = a.read() == b.read()
            if same:
                counts['identical_copy'] += 1
            else:
                failures.append(f'{name}: {f} is outside {tw} and differs from '
                                f'its checkout file')
    return counts, failures


def _no_patch(classes):
    """Functions in their classes' __dict__ that come from a module of ours."""
    bad = []
    for cls in classes:
        for k, v in vars(cls).items():
            fn = getattr(v, '__func__', v)
            if callable(fn) and _ours(fn):
                bad.append(f'{cls.__module__}.{cls.__qualname__}.{k} from {fn.__module__}')
    return bad


def _own_methods(cls):
    return sorted(k for k in vars(cls)
                  if not (k.startswith('__') and k.endswith('__')) or k == '__init__')


def _normal_def(source):
    """A method's code without its comments, docstring and layout: the tuple
    of the dumps of its name, arguments, decorators, return annotation and
    body statements."""
    node = ast.parse(textwrap.dedent(source)).body[0]
    body = list(node.body)
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return (node.name, ast.dump(node.args),
            [ast.dump(d) for d in node.decorator_list],
            ast.dump(node.returns) if node.returns is not None else None,
            [ast.dump(s) for s in body])


def rollout_wrapper_failures(cls, their_policy, their_tampura_policy,
                             reviewed=REVIEWED_ARM_T_ROLLOUT):
    """Arm T's rollout (DV-1's amendment): their Policy.rollout reached
    unchanged, and the one reviewed wrapper in the class of ours."""
    fails = []
    if their_tampura_policy.rollout is not their_policy.rollout:
        fails.append('TampuraPolicy.rollout is not Policy.rollout')
    own = vars(cls).get('rollout')
    if own is None:
        fails.append(f'{cls.__qualname__} has no rollout wrapper')
        return fails
    try:
        source = inspect.getsource(own)
    except (OSError, TypeError) as e:
        return fails + [f'{cls.__qualname__}.rollout source unreadable: {e}']
    if _normal_def(source) != _normal_def(reviewed):
        fails.append(f'{cls.__qualname__}.rollout is not the reviewed wrapper')
    return fails


def _and(names):
    names = list(names)
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]


def _common(policy, extra_classes, record, own_methods=('__init__', 'get_action'),
            reviewed_rollout=None):
    from tampura.config import config as tconfig
    from tampura.policies.policy import Policy
    from tampura.policies.tampura_policy import TampuraPolicy
    tw = _tw()
    record['their_root'] = tw
    fails = record['failures']
    if reviewed_rollout is None:
        if type(policy).rollout is not Policy.rollout:
            fails.append(f'{type(policy).__qualname__}.rollout is not Policy.rollout')
    else:
        record['rollout'] = 'their Policy.rollout, reached through the reviewed wrapper'
        fails += rollout_wrapper_failures(type(policy), Policy, TampuraPolicy,
                                          reviewed_rollout)
    methods = _own_methods(type(policy))
    record['policy_methods'] = methods
    if methods != sorted(own_methods):
        fails.append(f'{type(policy).__qualname__} defines {methods}, '
                     f'not only {_and(sorted(own_methods))}')
    envs = list(tconfig.env_registry.items.values())
    planners = dict(tconfig.planner_registry.items)
    patched = _no_patch([Policy, TampuraPolicy, *envs, *extra_classes])
    fails += [f'monkeypatch: {p}' for p in patched]
    counts, mod_fails = _module_files(tw)
    record['their_modules'] = counts
    fails += mod_fails
    return envs, planners


def check_arm_o(env, policy, b0, schema_name, execute_fn):
    """Arm O, in run_bridge_on_finddice.py right before policy.rollout."""
    record = {'arm': 'O', 'failures': []}
    fails = record['failures']
    envs, planners = _common(policy, [type(env), type(b0)], record)
    ours = [s.name for s in env.problem_spec.action_schemas
            if s.execute_fn is not None and _ours(s.execute_fn)]
    named = [s for s in env.problem_spec.action_schemas if s.name == schema_name]
    record['schemas_of_ours'] = ours
    if ours != [schema_name] or len(named) != 1 or named[0].execute_fn is not execute_fn:
        fails.append(f'registrations: schemas of ours {ours}, '
                     f'{len(named)} named {schema_name}')
    foreign = [k for k, c in planners.items() if _ours(c)]
    foreign += [c.__qualname__ for c in envs if _ours(c)]
    if foreign:
        fails.append(f'registrations: classes of ours in their registries {foreign}')
    if 'step' in vars(env):
        fails.append("the env has an instance attribute 'step'")
    from world.boxel_env import BoxelTestEnv
    from tampura_bridge.env_adapter import TampuraWorldEnv
    if TampuraWorldEnv.sync_to_plan_client is not BoxelTestEnv.sync_to_plan_client:
        fails.append('TampuraWorldEnv overrides sync_to_plan_client')
    record['ok'] = not fails
    return record


def check_arm_t(policy, problem_spec, planner_name, planner_class,
                reviewed_rollout=REVIEWED_ARM_T_ROLLOUT):
    """Arm T, in TampuraPolicyTimed.__init__ (their driver copy stays as is)."""
    record = {'arm': 'T', 'failures': []}
    fails = record['failures']
    envs, planners = _common(policy, [], record,
                             own_methods=('__init__', 'get_action', 'rollout'),
                             reviewed_rollout=reviewed_rollout)
    foreign = [k for k, c in planners.items()
               if _ours(c) and not (k == planner_name and c is planner_class)]
    if planners.get(planner_name) is not planner_class:
        foreign.append(f'{planner_name} is not {planner_class.__qualname__}')
    foreign += [c.__qualname__ for c in envs if _ours(c)]
    foreign += [s.name for s in problem_spec.action_schemas
                if s.execute_fn is not None and _ours(s.execute_fn)]
    if foreign:
        fails.append(f'registrations: {foreign}')
    record['ok'] = not fails
    return record


def write_and_enforce(record, save_dir):
    """Writes g13_runtime.json into the run's folder; stops the run on failure."""
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, 'g13_runtime.json'), 'w') as f:
        json.dump(record, f, indent=1)
    if not record['ok']:
        raise SystemExit('G13 runtime check failed: ' + '; '.join(record['failures']))
