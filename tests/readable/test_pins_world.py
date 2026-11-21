"""Phase 0 pins, group "world" (the world and its sensing; index
phase0/index/pins_world.md, R's pins 1, 1b, 2, 3, 6, 7, 9, 10, 13 to 16, 21
and 35): a fresh generation by tools/readable/pin_outputs.py compared, pin
by pin and file by file, with a stored folder named by READABLE_GOLDEN.

No golden output is stored before tag refactor-checkpoint-2 (R's condition
on the Phase 0 plan), so without READABLE_GOLDEN the pin tests skip.  On the
checkpoint, first the render fixture of pins 13 to 16, then the golden
folder:

    python tests/readable/make_render_fixture.py --out <fixture>
    READABLE_RENDER_FIXTURE=<fixture> \
        python tools/readable/pin_outputs.py --group world --out <folder>

and run, in WSL under the pipeline lock (R's rule 5), headless:

    READABLE_GOLDEN=<folder> READABLE_RENDER_FIXTURE=<fixture> PYTHONHASHSEED=0 \
        flock /root/sb_pipeline.lock /root/armO-venvA/bin/python \
        -m pytest -q tests/readable/test_pins_world.py

READABLE_WORLD_ONLY=p03_shadow_geometry,p13_detections limits the fresh
generation (and the compared pins) to those ids.  Pins p01b and p35b need
the bridge venv (TAMPURA's tree at /root/tampura-work); without it they
fail with "needs the bridge venv" and their test says so.  Files named
INFO_* are not compared.  The small tests at the end need no golden folder
and start no physics client.
"""
import difflib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools' / 'readable'))
import pin_outputs as po  # noqa: E402

GOLDEN = po.readable_path(po.GOLDEN_VAR)   # absolute, or None when unset (SPEC D11)
ONLY = [s for s in os.environ.get('READABLE_WORLD_ONLY', '').split(',') if s]
PINS = [p for p in po.GROUPS['world'] if not ONLY or p in ONLY]
BRIDGE_PINS = ('p01b_find_dice_scenes', 'p35b_bridge_table')
needs_golden = pytest.mark.skipif(
    not GOLDEN,
    reason='READABLE_GOLDEN is not set: no stored golden output exists before tag '
           'refactor-checkpoint-2 (R\'s condition); set it to a folder written by '
           '"pin_outputs.py --group world --out <folder>" on that tag')

# R's pin numbers of the index pins_world.md and the pin ids that cover them.
COVERAGE = {
    '1': ('p01_scene_presets', 'p01_scene_random_pairs', 'p01_scene_failures'),
    '1b': ('p01b_find_dice_scenes',),
    '2': ('p02_first_observation',),
    '3': ('p03_shadow_geometry',),
    '6': ('p06_twin_sync',),
    '7': ('p07_init_facts',),
    '9': ('p09_streams', 'p09_ik_tables'),
    '10': ('p10_move_steps',),
    '13': ('p13_detections',),
    '14': ('p14_sense_render',),
    '15': ('p15_shadow_blockers',),
    '16': ('p16_fragment_render',),
    '21': ('p21_pick_record',),
    '35': ('p35_bridge_pure', 'p35b_bridge_table'),
}


@pytest.fixture(scope='module')
def fresh(tmp_path_factory):
    """One generation of the group (each pin in its own child process)."""
    out = tmp_path_factory.mktemp('pins_world')
    for pid in PINS:
        po.run_group('world', out, only=[pid], log=lambda s: None)
    return out


def _first_difference(a, b):
    la = a.read_text(encoding='utf-8', errors='replace').splitlines()
    lb = b.read_text(encoding='utf-8', errors='replace').splitlines()
    diff = list(difflib.unified_diff(la, lb, 'golden', 'fresh', lineterm='', n=2))
    return '\n'.join(diff[:40])


@needs_golden
@pytest.mark.parametrize('pin_id', PINS)
def test_pin_equals_golden(fresh, pin_id):
    golden = Path(GOLDEN) / pin_id
    assert golden.is_dir(), f'the golden folder {GOLDEN} has no {pin_id}'
    manifest = json.loads((fresh / 'MANIFEST.json').read_text(encoding='utf-8'))
    status = manifest['pins'][pin_id]['status']
    err = fresh / pin_id / 'ERROR.txt'
    text = err.read_text(encoding='utf-8') if err.exists() else ''
    if pin_id in BRIDGE_PINS and 'needs the bridge venv' in text:
        pytest.skip(f'{pin_id} needs the bridge venv (TAMPURA\'s tree at {po.TW_ENVS})')
    assert status == 'ok', f'{pin_id} did not run: {status}\n' + text
    want, have = po.pin_files(golden), po.pin_files(fresh / pin_id)
    assert sorted(want) == sorted(have), f'file sets differ: golden {sorted(want)}, fresh {sorted(have)}'
    for name in sorted(want):
        if want[name].read_bytes() != have[name].read_bytes():
            pytest.fail(f'{pin_id}/{name} differs from the golden copy:\n'
                        + _first_difference(want[name], have[name]))


def test_group_covers_the_index():
    """Every item of the index has its pin ids registered, and nothing else is
    in the group."""
    ids = list(po.GROUPS['world'])
    want = [p for ps in COVERAGE.values() for p in ps]
    assert sorted(ids) == sorted(want)
    for pid in BRIDGE_PINS:
        assert 'needs the bridge venv' in po.GROUPS['world'][pid].about


def test_missing_render_fixture_says_how_to_make_it(tmp_path, monkeypatch):
    """Pins 13 to 16 read the stored renders; without them they stop with the
    command that makes them (no physics client, no render here)."""
    monkeypatch.setenv(po.RENDER_FIXTURE_VAR, str(tmp_path / 'none'))
    with pytest.raises(RuntimeError, match='make_render_fixture.py'):
        po._load_fixture()


def test_bridge_pins_say_when_the_tree_is_absent(monkeypatch):
    """Pins 1b and 35b name their need instead of failing on an import."""
    monkeypatch.setattr(po, 'TW_ENVS', '/nonexistent/tampura_environments')
    with pytest.raises(RuntimeError, match='needs the bridge venv'):
        po._need_tampura()
