"""planted_changes.py: the planted changes of PLAN 24.3 (e) for pin 47's
scripted tapes (REVIEW_PHASE0 B3), written into a throwaway copy of
test_full_pipeline.py, never into the checkout.

Each plant is one exact text replacement that must match exactly once in
the checkout's test_full_pipeline.py (a plant whose text is not found, or
found twice, is an error: the line numbers moved and the plant must be
re-read, not guessed).  The copy keeps the file name test_full_pipeline.py
(the executor stubs and record_episode's import redirect find main() by
it) and goes to ``<out>/<plant>/test_full_pipeline.py``; the planted pins
run it through ``READABLE_TFP_COPY`` (record_episode.py), then
``pin_outputs.py --compare`` against an unplanted pass must name the pin
listed here as differing.

    python tools/readable/planted_changes.py --out DIR [--plant NAME ...]
    python tools/readable/planted_changes.py --list
"""
import argparse
import difflib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TFP = REPO / 'test_full_pipeline.py'

# test_full_pipeline.py 2213 to 2214 on the tag (SPEC D8: the look joined
# the actions that keep the at-home state; read again, not guessed).  Since
# main() was cut into functions the two lines stand in dispatch_step (1656
# to 1657), and the empty-hand lines below in do_place (2328 to 2333), both
# at the function's own depth and with the names of the episode state st.
_HOME_OLD = ("    if action_name not in ('sense', 'observe', 'look'):\n"
             "        st.arm.at_home_ok = False\n")
_HOME_NEW = ("    if action_name not in ('sense', 'observe', 'look'):\n"
             "        pass\n")

_EH_HEAD = ('        print(f"    empty hand at place entry for {obj_str}; "\n'
            '              f"clearing held state and replanning (#P1 F1).")\n')
_EH_COUNT = ('        st.strikes.transit_loss_counts[obj_str] = \\\n'
             '            st.strikes.transit_loss_counts.get(obj_str, 0) + 1\n')
_EH_PRINT = ('        print(f"    transit loss {st.strikes.transit_loss_counts[obj_str]}"\n'
             '              f"/3 for {obj_str} (review-fix strike counter)")\n')
_EH_PRINT_GET = ('        print(f"    transit loss {st.strikes.transit_loss_counts.get(obj_str, 0)}"\n'
                 '              f"/3 for {obj_str} (review-fix strike counter)")\n')

# name: (what, old text, new text, the pins that must turn red)
PLANTS = {
    'at_home_drop': (
        '`at_home_ok = False` dropped (the at-home state outlives an arm move)',
        _HOME_OLD, _HOME_NEW, ['p47_scripted_home_split']),
    'empty_hand_swap': (
        'two statements swapped in the place empty-hand path: the strike print '
        'before the strike count (the first loss raises KeyError)',
        _EH_HEAD + _EH_COUNT + _EH_PRINT, _EH_HEAD + _EH_PRINT + _EH_COUNT,
        ['p47_scripted_empty_hand_place']),
    'empty_hand_swap_quiet': (
        'the same two statements swapped with the print made safe by .get '
        '(no crash; only the printed strike count is one low)',
        _EH_HEAD + _EH_COUNT + _EH_PRINT, _EH_HEAD + _EH_PRINT_GET + _EH_COUNT,
        ['p47_scripted_empty_hand_place']),
}


class PlantError(RuntimeError):
    """A plant's text is not found exactly once."""


def planted_text(name, source):
    """The planted copy of `source` (the text of test_full_pipeline.py)."""
    _, old, new, _ = PLANTS[name]
    n = source.count(old)
    if n != 1:
        raise PlantError(f'plant {name}: its text is found {n} times in test_full_pipeline.py, '
                         'not once; read the file again and update the plant')
    return source.replace(old, new, 1)


def write(name, out, tfp=TFP):
    """Write ``<out>/<name>/test_full_pipeline.py``; returns (path, diff)."""
    with open(tfp, encoding='utf-8', newline='') as f:
        src = f.read()
    new = planted_text(name, src.replace('\r\n', '\n'))
    if '\r\n' in src:
        new = new.replace('\n', '\r\n')
    d = Path(out) / name
    d.mkdir(parents=True, exist_ok=True)
    path = d / 'test_full_pipeline.py'
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    diff = ''.join(difflib.unified_diff(src.splitlines(True), new.splitlines(True),
                                        'test_full_pipeline.py', f'{name}/test_full_pipeline.py', n=1))
    return path, diff


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out')
    ap.add_argument('--plant', action='append')
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args(argv)
    if a.list or not a.out:
        for k, (what, _, _, red) in PLANTS.items():
            print(f'{k}: {what}; must turn red: {", ".join(red)}')
        return 0
    for name in a.plant or list(PLANTS):
        path, diff = write(name, a.out)
        print(f'{name}: {path}')
        print(diff)
    return 0


if __name__ == '__main__':
    sys.exit(main())
