"""#P4 B0: the bridge gates, static and ledger side (PAPER_AUDIT.txt #P4, P4.1).

Usage, from the repository root (standard library only):
  python tools/bridge_gates.py static          G1 G2 G7 G11(i) G17 over the
                                               campaign import graph
  python tools/bridge_gates.py allowlist-draft every G1/G2 hit as a draft
                                               allowlist line (B0 generates
                                               the reviewed file from it)
  python tools/bridge_gates.py domain          G10: domain and stream hashes
  python tools/bridge_gates.py ledger RUN_DIR [--m7 on|off]
                                               G3 G4 G5 G11 G15 G18 G19 G21
                                               from a run ledger (ours or the
                                               bridge's)
  python tools/bridge_gates.py tree [--save F | --compare F]
                                               G13 inside WSL: their trees,
                                               git status, pip freeze
  python tools/bridge_gates.py tdriver         G13: the T driver against
                                               run_planner.py's __main__
  python tools/bridge_gates.py all             every gate that needs no run
Exit code 0 when every gate passes, 1 otherwise.

The runtime gates (G3's motion hook, G6, G8(b), G10, G11(ii), G14, G16, G20)
are tampura_bridge/gate_hooks.py; their counts reach this tool through the
ledger's gate_record row (G21).
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST = os.path.join(REPO, 'tools', 'bridge_gates_allowlist.txt')
TW = os.environ.get('TAMPURA_WORK', '/root/tampura-work')   # cluster: $W/tampura-work
PINNED_COMMITS = {'tampura': 'cdddf14', 'tampura_environments': '4167c35'}
# The one declared change to their tree (BF#3): tampura_environments at
# 4167c35 does not import as shipped (its package __init__ star-imports the
# toy_discrete subpackage that commit removed), so the 2026-05-26 set-up
# replaced the six star imports with guarded ones.  G13 accepts exactly this
# file with exactly this content and fails on any other modification.
DECLARED_THEIR_CHANGES = {
    'tampura_environments': {
        'tampura_environments/__init__.py':
            '9a64bea00c9ef6dcea6a8ee5b26a1f071a4366f053895509ddc32e45fe7b8ec4',
    },
}
# Arm T imports tampura from its venv's site-packages, a pip install from git
# at the pinned commit, not from the checkout (RG1.3, GF2).  G13 requires
# every tracked file of the checkout's package that the install carries to be
# byte-equal.  Tracked files pip leaves out (none is read at run time:
# load_config reads the --config file, find_dice's own):
NOT_INSTALLED = frozenset((
    'config/default.yml', 'third_party/symk/.gitattributes',
    'third_party/symk/.gitignore', 'third_party/symk/.uncrustify.cfg'))
# What pip builds that git does not track: the setup.py dummy extension and
# SymK's own build tree (bin/downward is the planner arm T runs).  These
# cannot equal the checkout's build; their hash goes into --compare instead.
INSTALL_BUILT = re.compile(r'(_dummy\.cpython-[^/]*\.so|third_party/symk/builds/.*)$')

# The campaign drivers (G1).  test_full_pipeline.py is a declared root as
# well: D1 runs its main() inside execute_fn, so it is on the campaign path
# whether or not B2's driver exists yet.
CAMPAIGN_ROOTS = ('tampura_bridge/run_bridge_on_finddice.py',
                  'tools/run_tampura_timed.py', 'test_full_pipeline.py')
# Never on the campaign path; reaching one from a root fails G1.
FORBIDDEN_PREFIXES = ('tampura_bridge/tests/', 'tests/', 'archive/')

G1_NAMES = frozenset((
    'createConstraint', 'changeConstraint', 'removeConstraint', 'removeBody',
    'createMultiBody', 'loadURDF', 'loadSDF', 'loadMJCF', 'loadBullet',
    'loadSoftBody', 'saveState', 'restoreState', 'resetSimulation',
    'setRealTimeSimulation', 'resetBasePositionAndOrientation',
    'resetBaseVelocity', 'resetJointState', 'resetJointStateMultiDof',
    'resetJointStatesMultiDof', 'applyExternalForce', 'applyExternalTorque',
    'setCollisionFilterPair', 'setCollisionFilterGroupMask',
    'set_group_positions', 'set_pose', 'changeDynamics', 'setGravity',
    'setTimeStep', 'setPhysicsEngineParameter'))
G2_CALLS = frozenset(('getBasePositionAndOrientation', 'get_pose', 'get_aabb',
                      'getAABB', 'rayTest', 'rayTestBatch'))
G2_ATTRS = frozenset(('object_poses', 'visibility_grid'))
# 'gate hook': gate_hooks.py's own machinery (the names it wraps, the reads
# its checks make with the unwrapped functions); allowed in that file only.
G1_CLASSES = ('plan client', 'D9 set-up', 'G14 exemption',
              'unreachable on the bridge path', 'test control', 'gate hook')
G2_CLASSES = ('write-only', 'scoring', 'plan twin',
              'unreachable on the bridge path', 'test control', 'gate hook')
GATE_HOOK_FILE = 'tampura_bridge/gate_hooks.py'

G7_PATTERNS = (re.compile(r'cup_\d'), re.compile(r'^die$'),
               re.compile(r'1747173\d{3}'), re.compile(r'problems/'),
               re.compile(r'_cups_ud'))
G7_EXEMPT_FILES = ('tampura_bridge/task_spec.py',)
LOG_CALLS = frozenset(('print', 'debug', 'info', 'warning', 'error',
                       'exception', 'ledger_event', 'note'))

# G19: the pinned seed-to-scene map of the campaign (BF#8, option A): the
# cluster's own, read from B1(g)'s consoles (job 4940012, "Loading scene
# from" in results/b1g/consoles/seed_N.log on /work/rleap1).  TAMPURA picks
# the scene by random.choice(os.listdir(problems)), and the cluster's NFS
# lists [1747173593, 1747173591, 1747173590].
SCENE_MAP = {}
for _scene, _seeds in (('1747173593', (1, 2, 3, 4, 8, 14, 15, 18)),
                       ('1747173591', (0, 7, 9, 11, 12, 13, 16)),
                       ('1747173590', (5, 6, 10, 17, 19))):
    for _s in _seeds:
        SCENE_MAP[_s] = _scene
# The 2026-05-26 laptop run's map (P4.2; ext4 lists [1747173590,
# 1747173591, 1747173593]).  Used only to group that block by layout; it
# pins no campaign episode.
SCENE_MAP_LAPTOP_2026_05_26 = {}
for _scene, _seeds in (('1747173590', (1, 2, 3, 4, 8, 14, 15, 18)),
                       ('1747173591', (0, 7, 9, 11, 12, 13, 16)),
                       ('1747173593', (5, 6, 10, 17, 19))):
    for _s in _seeds:
        SCENE_MAP_LAPTOP_2026_05_26[_s] = _scene

# G5: the enumerated channels behind a SHADOW boxel's belief change.
G5_CHANNELS = ('planned_sense_render', 'sweep_render', 'lost_caster_render',
               'rediscovery_render', 'strike_park', 'observed_before_placement')
G5_UNRENDERED = 'superseded_unrendered'
# G3: how a dispatched step may end (run_logger.STEP_END_STATUSES less
# 'unlabelled', which always fails).
G3_STATUSES = ('ok', 'sense_outcome', 'integrity_replan',
               'motion_resolve_failed', 'pick_failure', 'place_failure',
               'stack_failure', 'empty_hand', 'stale_precondition',
               'home_not_reached')
G4_TOL_M = 1e-6
# G18: the arm O driver's clock stamps, in order.  Between their
# initialize() returning and the rollout's first env.step it may only load
# and assert the pinned scene map (G19), register the schema, build the
# policy (run_planner.py does too) and run G13's runtime check (GF1).
G18_EVENTS = ('seeded', 'initialize_call', 'initialize_return',
              'scene_map_asserted', 'schema_registered', 'policy_built',
              'g13_checked', 'rollout_start')
G19_PYTHONHASHSEED = '0'


def rel(path):
    return os.path.relpath(path, REPO).replace(os.sep, '/')


class Report:
    def __init__(self):
        self.rows = []

    def add(self, gate, status, detail=''):
        self.rows.append((gate, status, detail))

    def failed(self):
        return any(s == 'FAIL' for _, s, _ in self.rows)

    def show(self):
        for gate, status, detail in self.rows:
            print(f"{gate:<8} {status:<5} {detail}")


# ----- import graph ------------------------------------------------------

def _module_file(dotted):
    parts = dotted.split('.')
    base = os.path.join(REPO, *parts)
    for cand in (base + '.py', os.path.join(base, '__init__.py')):
        if os.path.isfile(cand):
            return cand
    return None


def _imports(path):
    """Repository files imported by `path` (absolute and relative)."""
    with open(path, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    pkg_parts = rel(os.path.dirname(path)).split('/')
    pkg_parts = [] if pkg_parts == ['.'] else pkg_parts
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(_module_file(alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[:len(pkg_parts) - node.level + 1]
                dotted = '.'.join(base + ([node.module] if node.module else []))
            else:
                dotted = node.module or ''
            found.append(_module_file(dotted) if dotted else None)
            for alias in node.names:
                found.append(_module_file(f"{dotted}.{alias.name}"
                                          if dotted else alias.name))
    return [f for f in found if f]


def import_graph():
    """(files, missing roots, forbidden files reached).  Every non-test
    module of tampura_bridge/ is a root too: the driver imports them."""
    roots = [os.path.join(REPO, r) for r in CAMPAIGN_ROOTS]
    pkg = os.path.join(REPO, 'tampura_bridge')
    if os.path.isdir(pkg):
        for name in sorted(os.listdir(pkg)):
            if name.endswith('.py'):
                roots.append(os.path.join(pkg, name))
    missing = [rel(r) for r in roots if not os.path.isfile(r)]
    todo = [r for r in roots if os.path.isfile(r)]
    seen = set()
    while todo:
        path = os.path.abspath(todo.pop())
        if path in seen:
            continue
        seen.add(path)
        todo.extend(_imports(path))
    files = sorted(seen)
    forbidden = [rel(f) for f in files
                 if rel(f).startswith(FORBIDDEN_PREFIXES)]
    return files, missing, forbidden


# ----- AST scans ---------------------------------------------------------

class _Scanner(ast.NodeVisitor):
    """G1 / G2 hits: calls by name, `from pybullet import`, getattr with a
    constant name, and (RG1.17, GF3) any other Load of such a name on the
    pybullet module or an alias of it (`get = p.getAABB`) and any string
    constant equal to one (a lookup by name)."""

    def __init__(self, path, lines, tree):
        self.path = rel(path)
        self.lines = lines
        self.scope = []
        self.calls = []
        self.hits = []
        self.modules = {'p', 'pybullet'}
        self.seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == 'pybullet':
                        self.modules.add(alias.asname or 'pybullet')
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                 ast.AsyncFunctionDef)):
                doc = node.body[0] if node.body else None
                if (isinstance(doc, ast.Expr)
                        and isinstance(doc.value, ast.Constant)):
                    self.seen.add(id(doc.value))

    @staticmethod
    def _gate_of(name):
        return 'G1' if name in G1_NAMES else 'G2' if name in G2_CALLS else None

    def _qual(self):
        return '.'.join(self.scope) or '<module>'

    def _hit(self, gate, node, what):
        src = self.lines[node.lineno - 1].strip()
        self.hits.append({'gate': gate, 'file': self.path,
                          'func': self._qual(), 'line': node.lineno,
                          'what': what, 'src': src})

    def visit_FunctionDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_ClassDef = visit_FunctionDef

    def visit_ImportFrom(self, node):
        if node.module == 'pybullet':
            for alias in node.names:
                if alias.name in G1_NAMES or alias.name in G2_CALLS:
                    self._hit('G1' if alias.name in G1_NAMES else 'G2',
                              node, f'from pybullet import {alias.name}')
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else None)
        if name in G1_NAMES:
            self._hit('G1', node, name)
        if name in G2_CALLS:
            self._hit('G2', node, name)
        if isinstance(func, ast.Attribute):
            self.seen.add(id(func))
        if (name == 'getattr' and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in (G1_NAMES | G2_CALLS)):
            self._hit('G1' if node.args[1].value in G1_NAMES else 'G2',
                      node, f'getattr {node.args[1].value}')
            self.seen.add(id(node.args[1]))
        self.generic_visit(node)

    def visit_Constant(self, node):
        gate = (self._gate_of(node.value) if isinstance(node.value, str)
                else None)
        if gate and id(node) not in self.seen:
            self._hit(gate, node, f'name {node.value!r} as a string')

    def visit_Attribute(self, node):
        if isinstance(node.ctx, ast.Load):
            base = node.value.id if isinstance(node.value, ast.Name) else None
            gate = self._gate_of(node.attr)
            if gate and base in self.modules and id(node) not in self.seen:
                self._hit(gate, node, f'{base}.{node.attr} referenced, not called')
            if node.attr in G2_ATTRS:
                self._hit('G2', node, node.attr)
            elif node.attr == 'poses' and base == 'world':
                self._hit('G2', node, 'world.poses')
            elif node.attr == 'position' and base not in ('grasp', 'self'):
                self._hit('G2', node, '.position read')
        self.generic_visit(node)


def scan(files):
    hits = []
    for path in files:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        tree = ast.parse(text, filename=path)
        sc = _Scanner(path, text.splitlines(), tree)
        sc.visit(tree)
        hits.extend(sc.hits)
    return hits


def _parse_allowlist():
    entries, problems = [], []
    if not os.path.isfile(ALLOWLIST):
        return entries, [f'{rel(ALLOWLIST)} missing']
    with open(ALLOWLIST, 'r', encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            parts = [p.strip() for p in line.split(' | ')]
            if len(parts) != 7:
                problems.append(f'allowlist line {n}: 7 fields expected')
                continue
            gate, file, func, lineno, cls, reason, src = parts
            allowed = G1_CLASSES if gate == 'G1' else G2_CLASSES
            if cls not in allowed:
                problems.append(f'allowlist line {n}: class {cls!r}')
            if cls == 'gate hook' and file != GATE_HOOK_FILE:
                problems.append(f'allowlist line {n}: gate hook outside '
                                f'{GATE_HOOK_FILE}')
            if not reason or reason == 'UNREVIEWED':
                problems.append(f'allowlist line {n}: no reviewed reason')
            entries.append({'gate': gate, 'file': file, 'func': func,
                            'src': src, 'n': n})
    return entries, problems


def check_allowlisted(hits, gate):
    """Every hit of `gate` matches one allowlist entry (file, function,
    source text; line numbers are informational) and every entry matches
    one hit."""
    entries, problems = _parse_allowlist()
    pool = [e for e in entries if e['gate'] == gate]
    unmatched = []
    for h in (h for h in hits if h['gate'] == gate):
        for e in pool:
            if (e['file'], e['func'], e['src']) == (h['file'], h['func'],
                                                    h['src']):
                pool.remove(e)
                break
        else:
            unmatched.append(h)
    stale = pool
    return unmatched, stale, problems


def _draft_line(h):
    return (f"{h['gate']} | {h['file']} | {h['func']} | {h['line']} | "
            f"UNREVIEWED | UNREVIEWED | {h['src']}")


def g7_scan(files):
    hits = []
    for path in files:
        r = rel(path)
        if r in G7_EXEMPT_FILES:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
        tree = ast.parse(text, filename=path)
        skip = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                 ast.AsyncFunctionDef)):
                doc = node.body[0] if node.body else None
                if (isinstance(doc, ast.Expr)
                        and isinstance(doc.value, ast.Constant)):
                    skip.add(id(doc.value))
            if isinstance(node, ast.Call):
                fn = node.func
                name = (fn.attr if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else None)
                if name in LOG_CALLS:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Constant):
                            skip.add(id(sub))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in skip):
                for pat in G7_PATTERNS:
                    if pat.search(node.value):
                        hits.append(f"{r}:{node.lineno} {node.value!r}")
                        break
    return hits


def g11_scan(files):
    allowed = ('pddlstream_planner.py', 'streams.py')
    hits = []
    for path in files:
        if rel(path) in allowed:
            continue
        with open(path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                mods = [node.module or '']
            for m in mods:
                if m == 'pddlstream' or m.startswith('pddlstream.'):
                    hits.append(f"{rel(path)}:{node.lineno} imports {m}")
    return hits


def g17_scan():
    needle = re.compile('faith' + 'ful', re.IGNORECASE)
    targets = []
    for top in ('tampura_bridge',):
        for root, _, names in os.walk(os.path.join(REPO, top)):
            if '__pycache__' in root:
                continue
            targets += [os.path.join(root, n) for n in names]
    for name in ('bridge_gates_allowlist.txt', 'run_tampura_timed.py',
                 '_bridge_campaign.py'):
        p = os.path.join(REPO, 'tools', name)
        if os.path.isfile(p):
            targets.append(p)
    ev = os.path.join(REPO, 'eval_results')
    if os.path.isdir(ev):
        for d in os.listdir(ev):
            if d.startswith('tampura_bridge_'):
                for root, _, names in os.walk(os.path.join(ev, d)):
                    targets += [os.path.join(root, n) for n in names
                                if n.endswith(('.json', '.txt', '.md',
                                               '.log', '.tex', '.csv'))]
    hits = []
    for p in targets:
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                for n, line in enumerate(f, 1):
                    if needle.search(line):
                        hits.append(f"{rel(p)}:{n}")
        except OSError:
            pass
    return hits


def run_static(report):
    files, missing, forbidden = import_graph()
    report.add('graph', 'INFO', f"{len(files)} modules; roots not present "
                                f"yet: {', '.join(missing) or 'none'}")
    hits = scan(files)
    for gate in ('G1', 'G2'):
        unmatched, stale, problems = check_allowlisted(hits, gate)
        n = sum(1 for h in hits if h['gate'] == gate)
        bad = list(problems)
        bad += [f"unlisted {h['file']}:{h['line']} {h['func']}: {h['src']}"
                for h in unmatched]
        bad += [f"stale entry line {e['n']} {e['file']} {e['func']}"
                for e in stale]
        if gate == 'G1' and forbidden:
            bad += [f'graph reaches {f}' for f in forbidden]
        report.add(gate, 'FAIL' if bad else 'PASS',
                   f"{n} hits, all reviewed" if not bad else
                   f"{n} hits; " + '; '.join(bad[:12])
                   + (f' (+{len(bad) - 12} more)' if len(bad) > 12 else ''))
    g7 = g7_scan(files)
    report.add('G7', 'FAIL' if g7 else 'PASS', '; '.join(g7) or 'no scene literal')
    g11 = g11_scan(files)
    report.add('G11(i)', 'FAIL' if g11 else 'PASS',
               '; '.join(g11) or 'pddlstream imported only by '
                                 'pddlstream_planner.py and streams.py')
    g17 = g17_scan()
    report.add('G17', 'FAIL' if g17 else 'PASS', '; '.join(g17) or 'clean')
    return hits


# ----- G10 ---------------------------------------------------------------

def _pddl_sha(name):
    with open(os.path.join(REPO, 'pddl', name), 'r') as f:
        return hashlib.sha256(f.read().encode('utf-8')).hexdigest()


def run_domain(report):
    d, s = _pddl_sha('domain_pddlstream.pddl'), _pddl_sha('stream.pddl')
    report.add('G10', 'INFO', f"domain_pddlstream.pddl {d[:16]}  "
                              f"stream.pddl {s[:16]}")
    gen = os.path.join(REPO, 'tools', 'gen_bridge_domain.py')
    if os.path.isfile(gen):
        report.add('G10', 'FAIL', 'gen_bridge_domain.py exists but its '
                                  'regeneration check is not written yet (B4)')
    else:
        report.add('G10', 'PASS', 'no generated domain (M1 not adopted); the '
                                  'planner must read the files above')


# ----- G13 ---------------------------------------------------------------

def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def tree_state():
    state = {}
    for repo in ('tampura', 'tampura_environments'):
        path = os.path.join(TW, repo)
        files = _run(['git', '-C', path, 'ls-files', '-z']).split('\0')
        h = hashlib.sha256()
        for f in sorted(x for x in files if x):
            h.update(f.encode())
            fp = os.path.join(path, f)
            if os.path.isfile(fp):
                with open(fp, 'rb') as fh:
                    h.update(hashlib.sha256(fh.read()).digest())
        modified = _run(['git', '-C', path, 'status', '--porcelain',
                         '--untracked-files=no']).splitlines()
        declared = DECLARED_THEIR_CHANGES.get(repo, {})
        undeclared = []
        for entry in modified:
            name = entry[3:].strip()
            fp = os.path.join(path, name)
            digest = None
            if os.path.isfile(fp):
                with open(fp, 'rb') as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
            if entry[:2] != ' M' or declared.get(name) != digest:
                undeclared.append(entry)
        head = _run(['git', '-C', path, 'rev-parse', 'HEAD']).strip()
        state[repo] = {'tracked_sha256': h.hexdigest(), 'head': head,
                       'modified_tracked': modified,
                       'undeclared_changes': undeclared}
    freeze = _run([os.path.join(TW, '.venv', 'bin', 'pip'), 'freeze'])
    state['pip_freeze_sha256'] = hashlib.sha256(freeze.encode()).hexdigest()
    state['tampura_installed'] = installed_state()
    return state


def _sha(fp):
    with open(fp, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def installed_state():
    """The site-packages tampura of arm T's venv against the checkout."""
    found = _run([os.path.join(TW, '.venv', 'bin', 'python'), '-c',
                  'import tampura, os; print(os.path.dirname(tampura.__file__))']).strip()
    checkout = os.path.join(TW, 'tampura', 'tampura')
    tracked = [f[len('tampura/'):] for f in
               _run(['git', '-C', os.path.join(TW, 'tampura'), 'ls-files', '-z',
                     'tampura']).split('\0') if f]
    differ, missing, equal = [], [], 0
    for rel in tracked:
        fp = os.path.join(found, rel)
        if not os.path.isfile(fp):
            if rel not in NOT_INSTALLED:
                missing.append(rel)
        elif _sha(fp) != _sha(os.path.join(checkout, rel)):
            differ.append(rel)
        else:
            equal += 1
    tracked_set, extra = set(tracked), []
    built = hashlib.sha256()
    for root, dirs, files in os.walk(found):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), found).replace(os.sep, '/')
            if rel in tracked_set:
                continue
            if INSTALL_BUILT.match(rel):
                built.update(rel.encode())
                built.update(bytes.fromhex(_sha(os.path.join(root, name))))
            else:
                extra.append(rel)
    return {'path': found, 'tracked': len(tracked), 'equal': equal, 'differ': differ,
            'missing': missing, 'untracked_extra': extra,
            'built_sha256': built.hexdigest()}


def run_tree(report, save=None, compare=None):
    if not os.path.isdir(TW):
        report.add('G13', 'FAIL', f'{TW} not found (run inside WSL)')
        return
    state = tree_state()
    for repo, pin in PINNED_COMMITS.items():
        s = state[repo]
        bad = []
        if not s['head'].startswith(pin):
            bad.append(f"HEAD {s['head'][:7]} != pinned {pin}")
        if s['undeclared_changes']:
            bad.append(f"undeclared changes: {s['undeclared_changes'][:5]}")
        n_decl = len(s['modified_tracked']) - len(s['undeclared_changes'])
        report.add('G13', 'FAIL' if bad else 'PASS',
                   f"{repo}: " + ('; '.join(bad) if bad else
                                  f"HEAD {pin}, tree {s['tracked_sha256'][:16]}, "
                                  f"{n_decl} declared change(s) (BF#3), "
                                  f"nothing else modified"))
    report.add('G13', 'INFO', f"arm T pip freeze {state['pip_freeze_sha256'][:16]}")
    inst = state['tampura_installed']
    bad = [f"{k}: {inst[k][:5]}" for k in ('differ', 'missing', 'untracked_extra')
           if inst[k]]
    if inst['path'] == os.path.join(TW, 'tampura', 'tampura'):
        bad.append('arm T imports the checkout itself, not the install G13 expects')
    report.add('G13', 'FAIL' if bad else 'PASS',
               f"arm T's installed tampura: " + ('; '.join(bad) if bad else
               f"{inst['equal']} of {inst['tracked']} tracked files byte-equal "
               f"to the checkout, the rest never installed and never read, "
               f"build {inst['built_sha256'][:16]}"))
    if save:
        with open(save, 'w') as f:
            json.dump(state, f, indent=1)
    if compare:
        with open(compare) as f:
            before = json.load(f)
        diff = [k for k in ('pip_freeze_sha256',) if before.get(k) != state.get(k)]
        if 'tampura_installed' in before and (before['tampura_installed']['built_sha256']
                                              != state['tampura_installed']['built_sha256']):
            diff.append('tampura_installed build')
        diff += [r for r in PINNED_COMMITS
                 if before[r]['tracked_sha256'] != state[r]['tracked_sha256']]
        report.add('G13', 'FAIL' if diff else 'PASS',
                   f"changed since {compare}: {diff}" if diff
                   else f"unchanged since {compare}")


def _main_block(lines):
    for i, line in enumerate(lines):
        if re.match(r'''if\s+__name__\s*==\s*['"]__main__['"]\s*:''', line):
            return [l.rstrip() for l in lines[i:] if l.strip()]
    return None


T_DRIVER_IMPORT = re.compile(r'^\s+import tampura_bridge\.timed_policy\b')


def tdriver_diff(ours_text, theirs_text):
    """The ordered whole-file check (GF1): our T driver minus its leading
    docstring and the one permitted import, line for line equal to their
    run_planner.py.  Returns (ok, message)."""
    ours = ours_text.splitlines()
    if ours and ours[0].startswith('"""'):
        end = next((i for i, l in enumerate(ours)
                    if l.rstrip().endswith('"""') and (i > 0 or l.count('"""') > 1)), None)
        if end is None:
            return False, 'unterminated docstring in our T driver'
        ours = ours[end + 1:]
    imports = [i for i, l in enumerate(ours) if T_DRIVER_IMPORT.match(l)]
    if len(imports) != 1:
        return False, f'{len(imports)} permitted imports, need exactly 1'
    main = _main_block(ours) or []
    if not any(T_DRIVER_IMPORT.match(l) for l in main):
        return False, 'the permitted import is not inside __main__'
    del ours[imports[0]]
    a = [l.rstrip() for l in ours]
    b = [l.rstrip() for l in theirs_text.splitlines()]
    if a == b:
        return True, 'T driver = run_planner.py line for line, plus the one import'
    i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return False, (f'T driver differs from run_planner.py at line {i + 1}: '
                   f'ours {a[i] if i < len(a) else "<end>"!r}, '
                   f'theirs {b[i] if i < len(b) else "<end>"!r}')


def run_tdriver(report):
    drv = os.path.join(REPO, 'tools', 'run_tampura_timed.py')
    theirs = os.path.join(TW, 'tampura_environments', 'run_planner.py')
    if not os.path.isfile(drv):
        report.add('G13', 'N/A', 'T driver tools/run_tampura_timed.py not '
                                 'written yet (B2)')
        return
    if not os.path.isfile(theirs):
        report.add('G13', 'FAIL', f'{theirs} not found (run inside WSL)')
        return
    with open(drv) as f:
        ours = f.read()
    with open(theirs) as f:
        ref = f.read()
    ok, msg = tdriver_diff(ours, ref)
    report.add('G13', 'PASS' if ok else 'FAIL', msg)


# ----- ledger reader -----------------------------------------------------

def read_ledger(run_dir):
    path = os.path.join(run_dir, 'ledger.jsonl')
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_ledger(report, run_dir, m7='on'):
    rows = read_ledger(run_dir)
    closes = [r for r in rows if r['kind'] == 'ledger_close']
    if not closes:
        report.add('ledger', 'FAIL', 'no ledger_close row: incomplete ledger')
    elif closes[-1].get('write_errors'):
        report.add('ledger', 'FAIL', f"{closes[-1]['write_errors']} write errors")
    else:
        report.add('ledger', 'PASS', f'{len(rows)} rows, complete')

    # G3: executed = planned, in order, early ends labelled.
    plans = {}
    for r in rows:
        if r['kind'] == 'plan' and r.get('actions') is not None:
            plans[r['plan_id']] = r
    steps = [r for r in rows if r['kind'] == 'step']
    ends = {(r.get('plan'), r.get('step')): r['status']
            for r in rows if r['kind'] == 'step_end'}
    bad3 = []
    by_plan = {}
    for s in steps:
        by_plan.setdefault(s['plan'], []).append(s)
    for pid, ss in sorted(by_plan.items()):
        p = plans.get(pid)
        if p is None:
            bad3.append(f'plan {pid}: steps without a plan row')
            continue
        for k, s in enumerate(ss, 1):
            if s['step'] != k:
                bad3.append(f'plan {pid}: step {s["step"]} dispatched as #{k}')
            planned = p['actions'][k - 1] if k <= len(p['actions']) else None
            if planned != [s['action']] + s['args']:
                bad3.append(f'plan {pid} step {k}: {[s["action"]] + s["args"]}'
                            f' != planned {planned}')
            if s.get('plan_obj') != p.get('plan_obj'):
                bad3.append(f'plan {pid} step {k}: not the planned list object')
            st = ends.get((pid, s['step']))
            if st is None:
                bad3.append(f'plan {pid} step {k}: no step_end')
            elif st not in G3_STATUSES:
                bad3.append(f'plan {pid} step {k}: ended {st}')
            elif st != 'ok' and k != len(ss):
                bad3.append(f'plan {pid} step {k}: {st} but dispatch went on')
        last = ends.get((pid, ss[-1]['step']))
        if len(ss) < len(p['actions']) and last == 'ok':
            bad3.append(f'plan {pid}: {len(ss)}/{len(p["actions"])} steps '
                        f'dispatched with no logged early end')
    for r in rows:
        if r['kind'] == 'move_resolve' and not r.get('goal_equal'):
            bad3.append(f"plan {r.get('plan')} step {r.get('step')}: re-solved "
                        f"move changed its goal configuration")
    n_early = sum(1 for v in ends.values() if v != 'ok')
    report.add('G3', 'FAIL' if bad3 else 'PASS',
               '; '.join(bad3[:8]) if bad3 else
               f'{len(steps)} steps over {len(by_plan)} plans, all as planned; '
               f'{n_early} labelled early ends')

    # G4: commanded place destination = the planned boxel's centre.
    bad4 = []
    places = [r for r in rows if r['kind'] == 'place_target']
    for r in places:
        c = r.get('boxel_center_xy')
        t = r.get('target_xy')
        if c is None:
            bad4.append(f"{r['boxel']}: planned boxel not in the registry")
        elif max(abs(a - b) for a, b in zip(c, t)) > G4_TOL_M:
            bad4.append(f"{r['boxel']}: target {t} vs centre {c}")
    report.add('G4', 'FAIL' if bad4 else 'PASS',
               '; '.join(bad4[:6]) or f'{len(places)} places at the planned centre')

    # G5: every SHADOW change names an enumerated channel.
    bad5, unrendered, counts = [], 0, {}
    sense_regions = {}
    for s in steps:
        if s['action'] == 'sense' and len(s['args']) >= 2:
            sense_regions[(s['plan'], s['step'])] = s['args'][1]
    for r in rows:
        if r['kind'] != 'belief' or r['op'] == 'add':
            continue
        ch = r.get('channel')
        counts[ch] = counts.get(ch, 0) + 1
        if ch == G5_UNRENDERED:
            unrendered += 1
        elif ch not in G5_CHANNELS:
            bad5.append(f"{r['region']} {r['op']} {r.get('status')}: no channel")
        elif ch == 'planned_sense_render':
            planned = sense_regions.get((r.get('plan'), r.get('step')))
            if planned != r['region']:
                bad5.append(f"{r['region']} {r['op']}: sense render of "
                            f"{planned}, not this region")
    if unrendered and m7 == 'on':
        bad5.append(f'{unrendered} unrendered rediscovery removals with M7 on')
    detail = ', '.join(f'{k}={v}' for k, v in sorted(counts.items(),
                                                       key=lambda kv: str(kv[0])))
    if unrendered and m7 == 'off':
        detail += (f'; DISCLOSE: {unrendered} rows superseded_unrendered '
                   f'(P4.5 correction (6))')
    report.add('G5', 'FAIL' if bad5 else 'PASS',
               '; '.join(bad5[:6]) if bad5 else (detail or 'no fragment change'))

    # G15: every sense step has its classified outcome.
    sense_steps = [s for s in steps if s['action'] == 'sense']
    results = {(r.get('plan'), r.get('step')) for r in rows
               if r['kind'] == 'sense_result'}
    missing = [f"plan {s['plan']} step {s['step']}" for s in sense_steps
               if (s['plan'], s['step']) not in results]
    report.add('G15', 'FAIL' if missing else 'PASS',
               f'no outcome for {missing[:5]}' if missing else
               f'{len(sense_steps)} senses, each classified on its planned region')

    # G19: the loaded scene file per seed equals the pinned map.  The
    # 'episode' row is written by the bridge driver (B2).
    eps = [r for r in rows if r['kind'] == 'episode']
    if not eps:
        report.add('G19', 'N/A', 'no episode row (not a bridge run)')
    else:
        bad19 = [f"seed {e.get('seed')}: {e.get('scene_file')} "
                 f"(pinned {SCENE_MAP.get(e.get('seed'))})"
                 for e in eps
                 if SCENE_MAP.get(e.get('seed')) is None
                 or SCENE_MAP[e['seed']] not in str(e.get('scene_file'))]
        report.add('G19', 'FAIL' if bad19 else 'PASS',
                   '; '.join(bad19) or 'scene file matches the pinned map')
        check_driver_clock(report, rows, eps[-1])

    # G11 and G21 from the runtime hooks, when the run had them.
    rec = [r for r in rows if r['kind'] == 'gate_record']
    if not rec:
        report.add('G21', 'FAIL' if eps else 'N/A',
                   'no gate_record in a bridge run' if eps else
                   'no gate_record (run without the bridge hooks)')
        return
    rec = rec[-1]
    calls = sum(1 for r in rows if r['kind'] == 'plan')
    report.add('G11', 'PASS' if rec.get('solve_calls') == calls else 'FAIL',
               f"{rec.get('solve_calls')} solve calls, {calls} plan rows")
    bad21 = {k: v for k, v in rec.get('counts', {}).items() if v}
    report.add('G21', 'FAIL' if bad21 else 'PASS',
               f'violations {bad21}' if bad21 else
               f"every runtime count 0; steps {rec.get('steps')}")


def check_driver_clock(report, rows, episode):
    """G18 and G19's seed hygiene from the arm O driver's driver_clock row
    (GF5).  G18: the stamps are G18_EVENTS in order, and every ledger row
    (all of the bridge's own work: D9, the settle, the adapter, main())
    comes after rollout_start, so inside their time_deltas.  G19h: both
    global RNGs were seeded with the episode's seed and untouched when
    their code took over, and PYTHONHASHSEED is the pinned value."""
    clocks = [r for r in rows if r['kind'] == 'driver_clock']
    if not clocks:
        report.add('G18', 'FAIL', 'no driver_clock row in a bridge run')
        report.add('G19h', 'FAIL', 'no driver_clock row in a bridge run')
        return
    ck = clocks[-1]
    events = [tuple(e) for e in ck.get('events', [])]
    names = tuple(n for n, _ in events)
    bad18 = []
    if names != G18_EVENTS:
        bad18.append(f'stamps {list(names)} != {list(G18_EVENTS)}')
    elif any(b[1] < a[1] for a, b in zip(events, events[1:])):
        bad18.append('stamps out of time order')
    if 'rollout_start' in names:
        start = dict(events)['rollout_start']
        early = [r['kind'] for r in rows if r['t'] < start]
        if early:
            bad18.append(f'{len(early)} ledger rows before rollout_start '
                         f'({early[:4]})')
    if bad18:
        report.add('G18', 'FAIL', '; '.join(bad18))
    else:
        t = dict(events)
        gaps = ', '.join(f'{b[0]} +{b[1] - a[1]:.3f} s'
                         for a, b in zip(events, events[1:]))
        report.add('G18', 'PASS',
                   f"initialize return to rollout start "
                   f"{t['rollout_start'] - t['initialize_return']:.3f} s ({gaps})")

    bad19h = []
    if ck.get('seed') != episode.get('seed'):
        bad19h.append(f"seeded {ck.get('seed')}, episode {episode.get('seed')}")
    for rng in ('random', 'numpy'):
        if ck.get('rng_untouched', {}).get(rng) is not True:
            bad19h.append(f'{rng} RNG consumed before their code')
    if ck.get('pythonhashseed') != G19_PYTHONHASHSEED:
        bad19h.append(f"PYTHONHASHSEED {ck.get('pythonhashseed')!r}, "
                      f"pinned {G19_PYTHONHASHSEED!r}")
    report.add('G19h', 'FAIL' if bad19h else 'PASS', '; '.join(bad19h) or
               f"seed {ck.get('seed')}, both RNGs untouched, PYTHONHASHSEED "
               f"{G19_PYTHONHASHSEED}")


def episode_outcome(rewards, error, report):
    """Arm O's one outcome field (P4.6 CRASHED and GATE-FAILED EPISODES,
    RG1.7): rewards[-1], the error and every gate the ledger reader failed.
    A crash outranks a gate failure, which outranks the reward."""
    failed = {g: d for g, s, d in report.rows if s == 'FAIL'}
    reward = float(rewards[-1]) if rewards else None
    if error:
        status = 'crashed'
    elif failed:
        status = 'gate_failed'
    elif reward == 1.0:
        status = 'success'
    else:
        status = 'failure'
    return {'status': status, 'success': status == 'success',
            'reward': reward, 'error': error, 'gate_failures': failed}


# ----- entry point -------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=('static', 'allowlist-draft', 'domain',
                                    'ledger', 'tree', 'tdriver', 'all'))
    ap.add_argument('run_dir', nargs='?')
    ap.add_argument('--m7', choices=('on', 'off'), default='on')
    ap.add_argument('--save')
    ap.add_argument('--compare')
    args = ap.parse_args(argv)
    report = Report()
    if args.cmd == 'allowlist-draft':
        files, _, _ = import_graph()
        for h in scan(files):
            print(_draft_line(h))
        return 0
    if args.cmd in ('static', 'all'):
        run_static(report)
    if args.cmd in ('domain', 'all'):
        run_domain(report)
    if args.cmd in ('tree', 'all'):
        run_tree(report, args.save, args.compare)
    if args.cmd in ('tdriver', 'all'):
        run_tdriver(report)
    if args.cmd == 'ledger':
        if not args.run_dir:
            ap.error('ledger needs RUN_DIR')
        run_ledger(report, args.run_dir, args.m7)
    report.show()
    return 1 if report.failed() else 0


if __name__ == '__main__':
    sys.exit(main())
