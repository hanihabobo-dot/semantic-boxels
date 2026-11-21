"""What a controller knows about each cell, in one controller-neutral form,
and how the GUI paints it (env.show_knowledge).

    knowledge = {cell: {'wumpus': V, 'pit': V, 'gold': V, 'visited': bool}}

V is 'yes' (known present), 'no' (known absent) or 'maybe' (not known).  A
cell left out means nothing is known about it; a key left out means 'maybe'
(and 'visited' False), so a controller sends only what it knows.  LW1
(lw1_driver, from its K-literals), the explore controller (its own sets) and
path 10's SB controller (from SB's belief) all feed the painter with it.  The
older form {cell: 'safe' | 'unknown' | 'danger'} is still accepted.

The painter shows, per cell, a tile colour for how dangerous the cell may be
(the two hazards only) and a label for what it may hold:

    danger    a hazard known present (wumpus or pit 'yes')         red
    visited   both hazards known absent, the robot stood there     green
    safe      both hazards known absent, not yet visited           light green
    possible  one hazard ruled out, the other not                  amber
    unknown   neither hazard known                                 blue-grey

The label is the cell's name with W?, P?, G? for each content that is 'maybe'
and W!, P!, G! for each that is 'yes' (nothing for 'no'), so the gold shows in
the label only.

Pure functions only: nothing here reads the world, and nothing a controller
decides depends on it.
"""
from typing import Dict, Iterable, Optional

CONTENTS = ('wumpus', 'pit', 'gold')
VALUES = ('yes', 'no', 'maybe')
MARK = {'wumpus': 'W', 'pit': 'P', 'gold': 'G'}

# The floor's own checkerboard greys are (0.62, 0.62, 0.62) and (0.45, 0.45, 0.47)
# (env.py); every state below differs from both, 'unknown' included.
TILE_RGBA = {
    'danger': (0.85, 0.20, 0.20, 1),
    'visited': (0.30, 0.75, 0.30, 1),
    'safe': (0.62, 0.88, 0.55, 1),
    'possible': (0.96, 0.68, 0.20, 1),
    'unknown': (0.55, 0.65, 0.92, 1),
}

_LEGACY = {'safe': {'wumpus': 'no', 'pit': 'no'}, 'unknown': {}, 'danger': {'danger': True}}


def entry(value=None) -> Dict:
    """One cell's knowledge made complete: {'wumpus', 'pit', 'gold': 'yes' |
    'no' | 'maybe', 'visited': bool, 'danger': bool}.  `value` is the cell's
    dict, an old-form string, or None (nothing known).  'danger' is set only
    by the old form's 'danger', which does not say which hazard."""
    if isinstance(value, str):
        if value not in _LEGACY:
            raise ValueError(f"unknown cell state {value!r}: 'safe', 'unknown' or 'danger'")
        value = _LEGACY[value]
    value = value or {}
    out = {'visited': bool(value.get('visited', False)), 'danger': bool(value.get('danger', False))}
    for c in CONTENTS:
        v = value.get(c, 'maybe')
        if v not in VALUES:
            raise ValueError(f"{c} is {v!r}: 'yes', 'no' or 'maybe'")
        out[c] = v
    return out


def normalize(knowledge: Optional[Dict], cells: Iterable[str]) -> Dict[str, Dict]:
    """{cell: entry} for every cell of `cells` (left-out cells: nothing known).
    A cell in `knowledge` that is not in `cells` is an error."""
    cells = list(cells)
    knowledge = knowledge or {}
    extra = set(knowledge) - set(cells)
    if extra:
        raise ValueError(f'cells not in the world: {sorted(extra)}')
    return {c: entry(knowledge.get(c)) for c in cells}


def tile_state(e: Dict) -> str:
    """'danger' | 'visited' | 'safe' | 'possible' | 'unknown' for a complete entry."""
    if e['danger'] or e['wumpus'] == 'yes' or e['pit'] == 'yes':
        return 'danger'
    if e['wumpus'] == 'no' and e['pit'] == 'no':
        return 'visited' if e['visited'] else 'safe'
    if e['wumpus'] == 'no' or e['pit'] == 'no':
        return 'possible'
    return 'unknown'


def marks(e: Dict) -> str:
    """'W? P? G?' for nothing known, 'G!' for the gold known here, '' for a
    cell known empty; '!' alone for the old form's 'danger'."""
    m = [MARK[c] + ('!' if e[c] == 'yes' else '?') for c in CONTENTS if e[c] != 'no']
    if e['danger'] and not any(e[c] == 'yes' for c in ('wumpus', 'pit')):
        m.insert(0, '!')
    return ' '.join(m)


def label(cell: str, e: Dict) -> str:
    """The text over a cell: its name and its marks."""
    mk = marks(e)
    return f'{cell} {mk}' if mk else cell


def counts(knowledge: Optional[Dict], cells: Iterable[str]) -> Dict:
    """What the console's thinking block shows: {'visited', 'safe',
    'maybe_pit', 'maybe_wumpus', 'gold_known'} (safe counts visited cells too)."""
    view = normalize(knowledge, cells)
    return {'visited': sum(e['visited'] for e in view.values()),
            'safe': sum(tile_state(e) in ('safe', 'visited') for e in view.values()),
            'maybe_pit': sum(e['pit'] == 'maybe' for e in view.values()),
            'maybe_wumpus': sum(e['wumpus'] == 'maybe' for e in view.values()),
            'gold_known': any(e['gold'] == 'yes' for e in view.values())}
