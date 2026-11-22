"""
slip_fixes.py: the switch registry of the BF#59 die-slip campaign.

Every candidate fix of the campaign lands behind a name and asks
``slip_fixes.on('name')`` at the one point where its behaviour differs.
The run says which names are on with --slip-fixes (run_logger's flag,
passed through the bridge driver like the M8 to M10 switches and recorded,
as the effective set, in the run record and in the episode's switches):

  (no flag, or an empty value)  the defaults: DEFAULT_ON, the four switches
                                of the BF#59 eval's chosen set (BF#62,
                                Hani's decision of 2026-11-02)
  none                          every switch off: the campaign's base arm,
                                the pipeline of commit 92d1e06
  a,b[,...]  (or a+b)           exactly the named switches, no others
  default,c                     the four and c

A fix registers its name where it lives (``slip_fixes.register('name',
'one line')`` at that module's import), so two fixes never edit the same
line of this file.  ``configure`` refuses a name nobody registered: a typo
in an arm's spec cannot run a base episode under a fix's label.  The four
defaults are known to this module itself (a process that imports only it
behaves as the pipeline does); their modules register them all the same.
"""
from typing import Dict, FrozenSet, List

# name -> one line, filled at import by the modules that carry a fix.
KNOWN: Dict[str, str] = {}

# BF#62 (Hani, 2026-11-02): the four switches of the chosen set, on unless
# the run says otherwise (BF#59's jobs D and E: 120 of 120 carries held,
# 120 of 120 successes; base 53 losses in 262 carries, 209 of 300).
DEFAULT_ON: FrozenSet[str] = frozenset({'solver_iters', 'force_hold',
                                        'pose_radius_keep', 'grasp_wrist_home'})
# The flag values that are not names: 'none' switches everything off,
# 'default' stands for DEFAULT_ON inside a list.
NONE = 'none'
DEFAULT = 'default'

# The names the run switched on: the defaults until configure() says.
ENABLED: FrozenSet[str] = DEFAULT_ON


def register(name: str, description: str) -> None:
    """Declare a fix's name (idempotent; a second registration must agree)."""
    if (not name or name != name.strip().lower() or ',' in name or '+' in name
            or name in (NONE, DEFAULT)):
        raise ValueError(f"slip fix name {name!r}: lowercase, no commas or plus "
                         f"signs, not {NONE!r} or {DEFAULT!r}")
    if name in KNOWN and KNOWN[name] != description:
        raise ValueError(f"slip fix {name!r} registered twice with different lines")
    KNOWN[name] = description


def parse(spec: str) -> List[str]:
    """The names a flag value means, in order: comma separated, blanks
    ignored, 'default' expanded to DEFAULT_ON, 'none' contributing nothing;
    an empty value means the defaults."""
    tokens = [s.strip() for s in str(spec or '').replace('+', ',').split(',')
              if s.strip()]
    if not tokens:
        tokens = [DEFAULT]
    names: List[str] = []
    for token in tokens:
        if token == NONE:
            continue
        for n in (sorted(DEFAULT_ON) if token == DEFAULT else [token]):
            if n not in names:
                names.append(n)
    return names


def resolve(spec: str) -> str:
    """The effective set a flag value means, as spec() would print it,
    without switching anything (for a record written before configure)."""
    names = parse(spec)
    return ','.join(sorted(names)) if names else NONE


def configure(spec: str) -> FrozenSet[str]:
    """Switch on the names ``spec`` means (and nothing else).  Unknown names
    are refused.  Returns the enabled set."""
    global ENABLED
    names = parse(spec)
    unknown = sorted(n for n in names if n not in KNOWN and n not in DEFAULT_ON)
    if unknown:
        raise ValueError(f"unknown slip fix(es) {unknown}; registered: "
                         f"{sorted(KNOWN) or 'none'}")
    ENABLED = frozenset(names)
    return ENABLED


def on(name: str) -> bool:
    """True when the run switched ``name`` on."""
    return name in ENABLED


def spec() -> str:
    """The enabled names as the flag would say them ('none' when none), so
    that configure(spec()) restores the same set."""
    return ','.join(sorted(ENABLED)) if ENABLED else NONE