"""The LW1 problem written from our registry (PLAN.md section 5).

Objects: the cell boxels.  (adj p q): from each boxel's x and y neighbour
ids, both directions, in the order of LW1's own listing (for cell p<i>-<j>:
the pair with p<i>-<j+1>, then the pair with p<i+1>-<j>).  Init, as in
LW1's p.pddl: (need-start), (not (wumpus-at s)), (not (pit-at s)), (at s),
(alive) for the start cell s.  Goal: (got-the-treasure).  The hidden block
is the caller's: the real hidden state for L (LW1 alone), a decoy for P (the
patch takes the observations from our robot).  Nothing here reads the
world's hidden state.

``parse`` and ``compare`` check a written problem against LW1's own file
fact for fact (order and case ignored).
"""
import re

from wumpus.world import cell_ij

_TOKENS = re.compile(r';[^\n]*|[()]|[^\s()]+')


def cells_of(registry):
    """The registry's cell boxels in LW1's object order (p1-1, p1-2, ...)."""
    return sorted(registry.boxels, key=cell_ij)


def adj_facts(registry):
    out = []
    for c in cells_of(registry):
        nb = registry.get_boxel(c).neighbor_ids
        for key in ('y_pos', 'x_pos'):
            for q in nb.get(key, []):
                out += [f'(adj {c} {q})', f'(adj {q} {c})']
    return out


def init_facts(registry, start):
    return adj_facts(registry) + ['(need-start)', f'(not (wumpus-at {start}))',
                                  f'(not (pit-at {start}))', f'(at {start})', '(alive)']


def write_problem(registry, start, hidden=(), name=None, domain='wumpus'):
    """The problem file's text.  hidden: literals such as '(gold-at p3-2)'."""
    cells = cells_of(registry)
    n = max(cell_ij(c)[0] for c in cells)
    name = name or f'p{n}x{n}'
    lines = [f'(define (problem {name})', f'(:domain {domain})',
             '(:objects ' + ' '.join(cells) + ' - pos)', '(:init']
    facts = init_facts(registry, start)
    for k in range(0, len(facts), 4):
        lines.append(' '.join(facts[k:k + 4]))
    lines += [')', '(:goal (got-the-treasure))']
    if hidden:
        lines.append('(:hidden ' + ' '.join(hidden) + ')')
    lines.append(')')
    return '\n'.join(lines) + '\n'


# ------------------------------------------------------------ comparison
def _read(tokens, k):
    if tokens[k] != '(':
        return tokens[k], k + 1
    out, k = [], k + 1
    while tokens[k] != ')':
        x, k = _read(tokens, k)
        out.append(x)
    return out, k + 1


def _text(x):
    return x if isinstance(x, str) else '(' + ' '.join(_text(y) for y in x) + ')'


def parse(text):
    """{'name', 'domain', 'objects', 'init', 'goal', 'hidden'} of a problem file
    (facts as lower-case one-line strings)."""
    tokens = [t.lower() for t in _TOKENS.findall(text) if not t.startswith(';')]
    tree, _ = _read(tokens, 0)
    out = {'name': None, 'domain': None, 'objects': [], 'init': [], 'goal': None, 'hidden': []}
    for part in tree[1:]:
        head = part[0]
        if head == 'problem':
            out['name'] = part[1]
        elif head == ':domain':
            out['domain'] = part[1]
        elif head == ':objects':
            out['objects'] = [x for x in part[1:] if x != '-' and x != 'pos']
        elif head == ':init':
            out['init'] = [_text(x) for x in part[1:]]
        elif head == ':goal':
            out['goal'] = _text(part[1])
        elif head == ':hidden':
            out['hidden'] = [_text(x) for x in part[1:]]
    return out


def compare(ours, theirs, hidden=False):
    """Differences between two problem files' objects, init and goal (and the
    hidden block when hidden=True), as {'field': (only in ours, only in theirs)};
    empty when they agree fact for fact."""
    a, b = parse(ours), parse(theirs)
    diff = {}
    for field in ('objects', 'init') + (('hidden',) if hidden else ()):
        x, y = set(a[field]), set(b[field])
        if x != y or len(a[field]) != len(b[field]):
            diff[field] = (sorted(x - y), sorted(y - x))
    if a['goal'] != b['goal']:
        diff['goal'] = (a['goal'], b['goal'])
    return diff
