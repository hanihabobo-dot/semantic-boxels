"""The Wumpus world as data: size, start, wumpuses, pits, gold, percept rule.

Cells are named as LW1 names them, ``p<i>-<j>`` with i, j in 1..N; the
4-neighbours of p<i>-<j> are p<i+-1>-<j> and p<i>-<j+-1> inside the grid.
Two sources: LW1's hidden-state literals (``from_hidden``) and a seeded
random generator with LW1's counts by board size (``random``).
"""
import random
import re
from typing import FrozenSet, List, Optional

_CELL = re.compile(r'^p(\d+)-(\d+)$')
_LIT = re.compile(r'\(\s*(wumpus-at|pit-at|gold-at)\s+(p\d+-\d+)\s*\)')
_BLOCK = re.compile(r'\(:hidden\b(.*?)\)\s*\)', re.S)


def cell_name(i: int, j: int) -> str:
    return f'p{i}-{j}'


def cell_ij(cell: str):
    m = _CELL.match(cell)
    if not m:
        raise ValueError(f'not a cell name: {cell!r}')
    return int(m.group(1)), int(m.group(2))


def default_counts(n: int):
    """LW1's counts by board size (AAAI 2014, Table 2): up to 5x5 one
    wumpus and one pit, 6 to 10 two and two, above 10 four and four.
    Provisional until their generator is read."""
    if n <= 5:
        return 1, 1
    if n <= 10:
        return 2, 2
    return 4, 4


class WumpusWorld:
    def __init__(self, n: int, wumpuses, pits, gold: str, start: str = 'p1-1'):
        self.n = int(n)
        self.start = start
        self.wumpuses: FrozenSet[str] = frozenset(wumpuses)
        self.pits: FrozenSet[str] = frozenset(pits)
        self.gold = gold
        for c in list(self.wumpuses) + list(self.pits) + [gold, start]:
            i, j = cell_ij(c)
            if not (1 <= i <= self.n and 1 <= j <= self.n):
                raise ValueError(f'cell {c} outside the {self.n}x{self.n} grid')
        if gold == start:
            raise ValueError('the gold may not lie in the start cell')
        if start in self.wumpuses or start in self.pits:
            raise ValueError('the start cell holds a wumpus or a pit')
        occupied = list(self.wumpuses) + list(self.pits) + [gold]
        if len(set(occupied)) != len(occupied):
            raise ValueError('two things share a cell')

    # ---- construction -------------------------------------------------
    @classmethod
    def from_hidden(cls, n: int, text: str) -> 'WumpusWorld':
        """One LW1 hidden block, for example
        ``(:hidden (wumpus-at p2-3) (pit-at p7-3) (gold-at p9-3))``."""
        wumpuses, pits, golds = [], [], []
        for kind, cell in _LIT.findall(text):
            {'wumpus-at': wumpuses, 'pit-at': pits, 'gold-at': golds}[kind].append(cell)
        if len(golds) != 1:
            raise ValueError(f'a hidden block needs exactly one gold-at, got {len(golds)}')
        return cls(n, wumpuses, pits, golds[0])

    @classmethod
    def random(cls, n: int, seed: int, n_wumpus: Optional[int] = None,
               n_pits: Optional[int] = None) -> 'WumpusWorld':
        dw, dp = default_counts(n)
        n_wumpus = dw if n_wumpus is None else n_wumpus
        n_pits = dp if n_pits is None else n_pits
        rng = random.Random(seed)
        cells = [cell_name(i, j) for i in range(1, n + 1) for j in range(1, n + 1)]
        safe = {'p1-1', 'p1-2', 'p2-1', 'p2-2'}
        free = [c for c in cells if c not in safe]
        if n_wumpus + n_pits + 1 > len(free) + len(safe) - 1:
            raise ValueError('too many things for this board')
        wumpuses = rng.sample(free, n_wumpus)
        free = [c for c in free if c not in wumpuses]
        pits = rng.sample(free, n_pits)
        rest = [c for c in cells if c != 'p1-1' and c not in wumpuses and c not in pits]
        gold = rng.choice(rest)
        return cls(n, wumpuses, pits, gold)

    # ---- geometry and percepts ---------------------------------------
    def cells(self) -> List[str]:
        return [cell_name(i, j) for i in range(1, self.n + 1) for j in range(1, self.n + 1)]

    def neighbors(self, cell: str) -> List[str]:
        i, j = cell_ij(cell)
        out = []
        for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            a, b = i + di, j + dj
            if 1 <= a <= self.n and 1 <= b <= self.n:
                out.append(cell_name(a, b))
        return out

    def stench(self, cell: str) -> bool:
        return any(c in self.wumpuses for c in self.neighbors(cell))

    def breeze(self, cell: str) -> bool:
        return any(c in self.pits for c in self.neighbors(cell))

    def glitter(self, cell: str) -> bool:
        return cell == self.gold

    def to_dict(self):
        return {'n': self.n, 'start': self.start, 'wumpuses': sorted(self.wumpuses),
                'pits': sorted(self.pits), 'gold': self.gold}


def parse_hidden_file(path: str) -> List[str]:
    """The hidden-state blocks of a file of LW1 instances, in order (seed k
    = block k).  A block is a ``(:hidden ...)`` form."""
    with open(path, 'r') as f:
        text = f.read()
    blocks = []
    pos = 0
    while True:
        k = text.find('(:hidden', pos)
        if k < 0:
            break
        depth, e = 0, k
        while e < len(text):
            if text[e] == '(':
                depth += 1
            elif text[e] == ')':
                depth -= 1
                if depth == 0:
                    break
            e += 1
        blocks.append(text[k:e + 1])
        pos = e + 1
    return blocks
