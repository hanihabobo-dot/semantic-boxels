"""
slip_fixes.py: the switch registry of the BF#59 die-slip campaign.

Every candidate fix of the campaign lands behind a name and is OFF unless
the run says --slip-fixes <name>[,<name>...] (run_logger's flag, passed
through the bridge driver like the M8 to M10 switches and recorded in the
run record and in the episode's switches).  A fix asks
``slip_fixes.on('name')`` at the one point where its behaviour differs;
with every name off the pipeline behaves as commit 92d1e06, which is the
campaign's base arm.

A fix registers its name where it lives (``slip_fixes.register('name',
'one line')`` at that module's import), so two fixes never edit the same
line of this file.  ``configure`` refuses a name nobody registered: a typo
in an arm's spec cannot run a base episode under a fix's label.
"""
from typing import Dict, FrozenSet, List

# name -> one line, filled at import by the modules that carry a fix.
KNOWN: Dict[str, str] = {}

# The names the run switched on (configure), empty by default.
ENABLED: FrozenSet[str] = frozenset()


def register(name: str, description: str) -> None:
    """Declare a fix's name (idempotent; a second registration must agree)."""
    if not name or name != name.strip().lower() or ',' in name or '+' in name:
        raise ValueError(f"slip fix name {name!r}: lowercase, no commas or plus signs")
    if name in KNOWN and KNOWN[name] != description:
        raise ValueError(f"slip fix {name!r} registered twice with different lines")
    KNOWN[name] = description


def parse(spec: str) -> List[str]:
    """The names of a flag value: comma separated, blanks ignored, in order."""
    return [s.strip() for s in str(spec or '').replace('+', ',').split(',')
            if s.strip()]


def configure(spec: str) -> FrozenSet[str]:
    """Switch on the names of ``spec`` (and nothing else).  Unknown names
    are refused.  Returns the enabled set."""
    global ENABLED
    names = parse(spec)
    unknown = sorted(n for n in names if n not in KNOWN)
    if unknown:
        raise ValueError(f"unknown slip fix(es) {unknown}; registered: "
                         f"{sorted(KNOWN) or 'none'}")
    ENABLED = frozenset(names)
    return ENABLED


def on(name: str) -> bool:
    """True when the run switched ``name`` on."""
    return name in ENABLED


def spec() -> str:
    """The enabled names as the flag would say them ('' when none)."""
    return ','.join(sorted(ENABLED))
