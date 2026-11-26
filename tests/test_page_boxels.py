"""Hani, 2026-11-25: "also include a forth "boxels" view. i.e. the world as
seen by boxles, updated whenever boxles change."  The fourth view of the page
beside our own window (gui_page.py): what the page is handed, when, and that
nothing of it reaches a run.

The page shows the registry's own content and nothing else, in the overlay's
own colours and names (visualization.py is their one source).  It is told
the id of a changed boxel by boxel_data's watcher, which is None in every
run without a page; a number goes up only when a copy really changed, and
only then does the page fetch /boxels.

No test here opens a window or a browser (tracks rule 13): the server is
asked over its own socket.  What the view looks like is the screen check's
finding (tracks/dbgcams/SPLIT_REPORT.md, pictures in checks/boxels_view)."""
import http.client
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from world import boxel_data
from console import gui_page
from console import page_boxels
from console import visualization
from world.boxel_data import BoxelData, BoxelRegistry, BoxelType

REPO = Path(__file__).resolve().parent.parent
# The pipeline's modules lie in their folders since the folder move: the top
# level and the six folders are where a module of the run can be.
_FOLDERS = ('world', 'sensing', 'planning', 'acting', 'console', 'evaluation')


def _pipeline_files():
    return list(REPO.glob('*.py')) + [f for d in _FOLDERS for f in (REPO / d).glob('*.py')]


def _name(path):
    return path.relative_to(REPO).as_posix()


@pytest.fixture
def page():
    assert gui_page.active() is None and boxel_data._watcher is None
    started = gui_page.start(console=None, port=0, token='tok')
    yield started
    gui_page.stop()
    # a page that is gone takes its watcher with it
    assert boxel_data._watcher is None
    boxel_data.watch(None)


def _get(page, path):
    conn = http.client.HTTPConnection('127.0.0.1', page.port, timeout=10)
    try:
        conn.request('GET', path)
        answer = conn.getresponse()
        return answer.status, dict(answer.getheaders()), answer.read()
    finally:
        conn.close()


def _served(page):
    status, headers, body = _get(page, '/boxels')
    assert status == 200 and headers['Content-Type'] == 'application/json'
    return json.loads(body)


def _version(page):
    return json.loads(_get(page, '/state')[2])['boxels']['version']


def _box(boxel_id, kind, lo, hi, **more):
    return BoxelData(id=boxel_id, boxel_type=kind, min_corner=np.array(lo, dtype=float),
                     max_corner=np.array(hi, dtype=float), **more)


def _registry():
    """One boxel of every kind and role the registry has."""
    reg = BoxelRegistry()
    reg.add_boxel(_box('red_object', BoxelType.OBJECT, [0.10, 0.00, 0.325], [0.16, 0.06, 0.46],
                       object_name='red_object', is_occluder=True))
    reg.add_boxel(_box('blue_object', BoxelType.OBJECT, [0.30, 0.20, 0.325], [0.34, 0.24, 0.365],
                       object_name='blue_object'))
    reg.add_boxel(_box('shadow_000', BoxelType.SHADOW, [0.10, 0.06, 0.325], [0.30, 0.40, 0.46],
                       created_by_object='red_object'))
    reg.add_boxel(_box('interior_of_cup', BoxelType.SHADOW, [0.40, 0.00, 0.325], [0.45, 0.05, 0.40],
                       created_by_object='cup', region_kind='interior'))
    reg.add_boxel(_box('', BoxelType.FREE_SPACE, [-0.10, -0.40, 0.325], [0.10, 0.00, 0.575]))
    return reg


def _by_id(data):
    return {b['id']: b for b in data['boxels']}


# ---------------------------------------------------------------------------
# what the page is handed
# ---------------------------------------------------------------------------

def test_before_a_registry_is_followed_the_page_has_no_boxels(page):
    assert json.loads(_get(page, '/state')[2])['boxels'] is None
    assert _served(page) == {'version': 0, 'clock': None, 'ground': None, 'boxels': []}


def test_the_page_gets_every_boxel_by_kind_extent_and_name(page):
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    data = _served(page)
    got = _by_id(data)
    assert set(got) == set(reg.boxels) == {'red_object', 'blue_object', 'shadow_000',
                                           'interior_of_cup', 'free_000'}
    assert [got[i]['kind'] for i in ('red_object', 'blue_object', 'shadow_000', 'interior_of_cup',
                                     'free_000')] == ['object', 'object', 'shadow', 'shadow', 'free_space']
    assert {b['kind'] for b in data['boxels']} == {t.value for t in BoxelType}
    for boxel_id, bd in reg.boxels.items():
        assert got[boxel_id]['min'] == pytest.approx(bd.min_corner.tolist(), abs=1e-9)
        assert got[boxel_id]['max'] == pytest.approx(bd.max_corner.tolist(), abs=1e-9)
        # the name is the overlay's own label
        assert got[boxel_id]['name'] == visualization._label_for_boxel(bd)
    assert got['shadow_000']['name'] == 'shadow_of_red_object'
    assert got['interior_of_cup']['name'] == 'interior_of_cup'
    assert (got['red_object']['occluder'], got['blue_object']['occluder']) == (True, False)
    assert (got['shadow_000']['region'], got['interior_of_cup']['region']) == ('lateral', 'interior')
    state = json.loads(_get(page, '/state')[2])['boxels']
    assert state['count'] == 5 and state['version'] == data['version']
    assert re.fullmatch(r'\d\d:\d\d:\d\d', state['clock']) and state['clock'] == data['clock']
    assert 0 <= state['age_s'] < 30


def test_the_colours_are_the_overlays(page):
    """One table: visualization._color_for_boxel.  The page has none of its
    own for the boxels; every boxel carries the colour that function gives,
    and the key over the view is made from the boxels."""
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    got = _by_id(_served(page))
    for boxel_id, bd in reg.boxels.items():
        assert got[boxel_id]['colour'] == visualization._color_for_boxel(bd)
    # and that table is what the overlay in the window has drawn since audit #35
    assert got['red_object']['colour'] == [1.0, 0.0, 0.0]         # an occluder
    assert got['blue_object']['colour'] == [0.0, 0.0, 1.0]        # an object in view
    assert got['shadow_000']['colour'] == [0.5, 0.5, 0.5]
    assert got['interior_of_cup']['colour'] == [0.5, 0.5, 0.5]
    assert got['free_000']['colour'] == [0.0, 1.0, 1.0]
    text = _get(page, '/')[2].decode('utf-8')
    assert 'colour: row.colour' in text and 'css(shade, fill)' in text


def test_the_corners_are_rounded_to_a_tenth_of_a_millimetre():
    bd = _box('b', BoxelType.OBJECT, [0.12344, -0.20006, 0.3], [0.2, 0.3, 0.40001], object_name='b')
    row = page_boxels.boxel_for_page(bd)
    assert row == ('b', 'object', (1234, -2001, 3000), (2000, 3000, 4000), 'b', (0.0, 0.0, 1.0),
                   False, 'lateral')
    assert all(type(v) is int for v in row[2] + row[3])
    # plain values only: nothing of the boxel itself is kept
    assert not any(isinstance(v, np.ndarray) for v in row)
    json.dumps(row)


def test_the_ground_is_the_tables_top_and_the_robots_base(page):
    env = types.SimpleNamespace(table_x_range=(-0.4, 0.6), table_y_range=(-0.5, 0.5),
                                table_surface_height=0.325, _ROBOT_BASE_XY=(-0.4, 0.0))
    assert page_boxels.ground_for_page(env) == {
        'x': [-0.4, 0.6], 'y': [-0.5, 0.5], 'z': 0.325, 'robot': [-0.4, 0.0, 0.0]}
    assert page_boxels.ground_for_page(object()) is None
    assert page_boxels.ground_for_page(None) is None
    page_boxels.show_on_page(page, _registry(), env)
    assert _served(page)['ground'] == page_boxels.ground_for_page(env)
    # the env's own numbers are these
    from world.boxel_env import BoxelTestEnv
    assert BoxelTestEnv._ROBOT_BASE_XY == (-0.4, 0.0)


# ---------------------------------------------------------------------------
# when it changes, and only then
# ---------------------------------------------------------------------------

def test_a_removed_boxel_is_gone_and_a_new_one_is_there(page):
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    v0 = _version(page)
    reg.remove_boxel('shadow_000')
    assert _version(page) == v0 + 1
    assert 'shadow_000' not in _by_id(_served(page))
    new = reg.add_boxel(_box('', BoxelType.FREE_SPACE, [0.5, 0.0, 0.325], [0.6, 0.1, 0.4]))
    assert _version(page) == v0 + 2
    assert _by_id(_served(page))[new]['max'] == [0.6, 0.1, 0.4]
    # a place: the free boxel goes and the object's boxel takes its place
    reg.update_after_place(new, 'blue_object', [0.52, 0.02, 0.325], [0.56, 0.06, 0.365], 0.325)
    got = _by_id(_served(page))
    assert new not in got and got['blue_object']['min'] == [0.52, 0.02, 0.325]
    assert _version(page) == v0 + 4
    assert len(got) == len(reg.boxels) == 4


def test_the_number_goes_up_only_when_a_boxel_really_changed(page):
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    v0 = _version(page)
    before = _get(page, '/boxels')[2]
    # told again and looked at again, with nothing changed
    for boxel_id in list(reg.boxels) + ['no_such_boxel']:
        boxel_data.note_change(boxel_id)
        page.boxel_changed(boxel_id)
    page.look_at_boxels()
    page.offer_render(2, 2, np.zeros((2, 2, 4)), np.ones((2, 2)), np.zeros((2, 2)), 0.01, 5.0, 'display')
    reg.remove_boxel('no_such_boxel')
    assert _version(page) == v0 and _get(page, '/boxels')[2] == before
    # the same numbers written again, and a move of less than a tenth of a millimetre
    red = reg.get_boxel('red_object')
    red.min_corner = red.min_corner.copy()
    red.max_corner = red.max_corner + 2e-5
    boxel_data.note_change('red_object')
    page.look_at_boxels()
    assert _version(page) == v0
    # a real move, told once: one step up, and no more for telling it again
    red.max_corner = red.max_corner + np.array([0.0, 0.0, 0.01])
    boxel_data.note_change('red_object')
    boxel_data.note_change('red_object')
    page.look_at_boxels()
    assert _version(page) == v0 + 1
    assert _by_id(_served(page))['red_object']['max'][2] == pytest.approx(0.47, abs=1e-4)
    # another role is another colour: a change too
    reg.get_boxel('blue_object').is_occluder = True
    boxel_data.note_change('blue_object')
    assert _version(page) == v0 + 2
    assert _by_id(_served(page))['blue_object']['colour'] == [1.0, 0.0, 0.0]


def test_what_nobody_tells_is_seen_when_a_render_is_handed_over(page):
    """Corners written in place in a run without the overlay, and an entry
    taken out of the dict directly (interior_regions does), go through
    neither the registry's methods nor the overlay.  The page looks at the
    whole registry where the env hands a render over: after a plan, after a
    step and at every observation."""
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    v0 = _version(page)
    reg.get_boxel('shadow_000').max_corner = np.array([0.30, 0.20, 0.46])
    reg.boxels.pop('interior_of_cup')
    assert _version(page) == v0                       # not told
    page.offer_render(2, 2, np.zeros((2, 2, 4)), np.ones((2, 2)), np.zeros((2, 2)), 0.01, 5.0, 'observation')
    assert _version(page) == v0 + 1                   # both in one look
    got = _by_id(_served(page))
    assert 'interior_of_cup' not in got and got['shadow_000']['max'] == [0.3, 0.2, 0.46]
    # and a render that cannot be read still lets the page look
    reg.boxels.pop('free_000')
    page.offer_render(2, 2, None, None, None, 0.01, 5.0, 'observation')
    assert _version(page) == v0 + 2 and 'free_000' not in _by_id(_served(page))


def test_the_overlays_redraw_tells_the_page(page, monkeypatch):
    """A boxel whose corners were written in place is redrawn by the overlay
    (remove_boxel_viz, draw_boxel_data: execution.py, look_action.py), and
    the page changes at that moment, as the window does."""
    drawn = []
    monkeypatch.setattr(visualization, 'p', types.SimpleNamespace(
        addUserDebugLine=lambda **k: drawn.append('line') or -1,
        addUserDebugText=lambda **k: drawn.append('text') or -1,
        removeUserDebugItem=lambda item: None))
    reg = _registry()
    viz = visualization.BoxelVisualizer(phantoms=False)
    page_boxels.show_on_page(page, reg)
    v0 = _version(page)
    bd = reg.get_boxel('blue_object')
    bd.min_corner, bd.max_corner = bd.min_corner + 0.1, bd.max_corner + 0.1
    assert _version(page) == v0
    viz.remove_boxel_viz(bd.id)
    viz.draw_boxel_data(bd)
    assert drawn.count('line') == 12 and _version(page) == v0 + 1
    assert _by_id(_served(page))['blue_object']['min'] == pytest.approx([0.4, 0.3, 0.425])


def test_the_page_follows_one_registry_and_keeps_copies(page):
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    v0 = _version(page)
    before = _served(page)
    # another registry with the same ids changes: nothing on the page
    other = _registry()
    other.remove_boxel('red_object')
    other.get_boxel('blue_object').max_corner = np.array([9.0, 9.0, 9.0])
    boxel_data.note_change('blue_object')
    other.add_boxel(_box('stranger', BoxelType.OBJECT, [0, 0, 0], [1, 1, 1], object_name='stranger'))
    assert _version(page) == v0 and _served(page) == before
    # the boxel's own arrays written into, untold: the page has copies
    reg.get_boxel('red_object').min_corner[:] = 7.0
    assert _served(page) == before
    # following another registry replaces the whole set
    page_boxels.show_on_page(page, other)
    assert set(_by_id(_served(page))) == set(other.boxels) and _version(page) > v0


# ---------------------------------------------------------------------------
# no ground truth
# ---------------------------------------------------------------------------

def test_an_object_the_robot_has_not_seen_is_not_in_what_the_page_gets(page, monkeypatch, tmp_path):
    """The source is the registry and nothing else.  The scene of `run
    boxels -Seed 3` (targets behind occluders), the registry built from the
    robot's own first observation by the pipeline's own stage
    (world_setup.build_registry, which hands it to the page): a hidden
    target's name and its true place are nowhere in /boxels or /state."""
    import pybullet as p
    from world import world_setup
    from world.boxel_env import BoxelTestEnv, random_pairs_scene
    from world.cell_merger import merge_free_space_cells

    env = BoxelTestEnv(gui=False, scene_config=random_pairs_scene(
        n_occluders=2, extra_distractors=0, seed=3))
    try:
        for _ in range(50):
            env.step_simulation()
        env.update_object_positions()
        obs = env.get_camera_observation()
        bodies = [n for n in env.objects if n not in ('plane', 'table', 'robot')]
        hidden = [n for n in bodies if n not in obs.visible_objects]
        assert hidden, 'the scene must hide a body from the first observation'
        free = merge_free_space_cells(env.generate_free_space(obs.boxels, visualize=False))
        env.annotate_free_space_surface(free)
        st = types.SimpleNamespace(
            setup=types.SimpleNamespace(all_boxels=obs.boxels + free, target_name=hidden[0]),
            opts=types.SimpleNamespace(run_logger=None, gui=False, draw_boxel_overlays=False,
                                       show_free=False))
        monkeypatch.chdir(tmp_path)                 # build_registry writes boxel_data.json
        world_setup.build_registry(st, env, False)
        assert boxel_data._watcher == page.boxel_changed

        data = _served(page)
        assert data['ground'] == page_boxels.ground_for_page(env)
        # what is served is the registry, boxel for boxel
        assert set(_by_id(data)) == set(st.setup.registry.boxels)
        objects = [b for b in data['boxels'] if b['kind'] == 'object']
        assert sorted(b['id'] for b in objects) == sorted(obs.visible_objects)
        raw = (_get(page, '/boxels')[2] + _get(page, '/state')[2]).decode('utf-8')
        for name in hidden:
            assert name not in raw
            # no object boxel stands where the hidden body truly is
            true_xyz = np.array(p.getBasePositionAndOrientation(
                env.objects[name].object_id, physicsClientId=env.client_id)[0])
            for b in objects:
                inside = np.all(true_xyz >= np.array(b['min']) - 1e-6) and np.all(
                    true_xyz <= np.array(b['max']) + 1e-6)
                assert not inside, (name, b['id'])
        # and once the robot registers it, the page has it
        seen_now = _box(hidden[0], BoxelType.OBJECT, [0.6, 0.3, 0.325], [0.63, 0.33, 0.355],
                        object_name=hidden[0])
        st.setup.registry.add_boxel(seen_now)
        assert hidden[0] in _by_id(_served(page))
    finally:
        env.close()


def test_the_page_is_handed_the_registry_and_never_the_env():
    """follow_boxels takes a registry, a function for one boxel and the
    ground's numbers; gui_page reads `registry.boxels` and nothing else of
    the run, and imports neither the simulator nor the pipeline."""
    import ast
    import inspect
    assert list(inspect.signature(gui_page.Page.follow_boxels).parameters) == [
        'self', 'registry', 'describe', 'ground']
    source = (REPO / 'console' / 'gui_page.py').read_text(encoding='utf-8')
    tree = ast.parse(source.split("_HTML = r'''")[0])
    imported = {a.name.split('.')[0] for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom))
                for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or '')])}
    assert imported <= {'atexit', 'json', 'os', 'sys', 'threading', 'time', 'numpy', 'io', 'PIL', 'http'}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    read = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == 'registry'}
    assert read == {'boxels'}
    assert not names & {'env', 'objects', 'pybullet', 'p'}


# ---------------------------------------------------------------------------
# nothing without a page, and nothing of a page reaches the run
# ---------------------------------------------------------------------------

def test_without_a_page_a_change_costs_one_comparison(monkeypatch):
    """No watcher is set unless a page follows a registry; then the
    registry's methods do not even call the function that would tell it."""
    assert boxel_data._watcher is None

    def never(boxel_id):
        raise AssertionError('told without a watcher: %r' % (boxel_id,))

    monkeypatch.setattr(boxel_data, 'note_change', never)
    reg = _registry()
    new = reg.add_boxel(_box('', BoxelType.FREE_SPACE, [0.5, 0.0, 0.325], [0.6, 0.1, 0.4]))
    reg.update_after_place(new, 'blue_object', [0.52, 0.02, 0.325], [0.56, 0.06, 0.365], 0.325)
    assert reg.remove_boxel('shadow_000').id == 'shadow_000'
    assert len(reg.boxels) == 4
    monkeypatch.undo()
    # the overlay's word goes nowhere
    assert boxel_data.note_change('red_object') is None


def test_a_run_that_starts_no_page_sets_no_watcher(tmp_path):
    """In a process of its own: the pipeline's modules imported, a registry
    built and changed, the stage that would hand it to a page run without a
    page.  No watcher, no page, no server module."""
    code = r'''
import sys, types
sys.path.insert(0, sys.argv[1])
import numpy as np
from world import boxel_data, world_setup
from console import gui_page, visualization
from world.boxel_data import BoxelData, BoxelRegistry, BoxelType
reg = BoxelRegistry()
reg.add_boxel(BoxelData(id='a', boxel_type=BoxelType.OBJECT, object_name='a',
                        min_corner=np.zeros(3), max_corner=np.ones(3)))
reg.remove_boxel('a')
st = types.SimpleNamespace(setup=types.SimpleNamespace(all_boxels=[], target_name='a'),
                           opts=types.SimpleNamespace(run_logger=None, gui=False,
                                                      draw_boxel_overlays=False, show_free=False))
world_setup.record_initial_detections = lambda env, registry: None      # needs a scene
world_setup.build_registry(st, types.SimpleNamespace(), False)          # writes boxel_data.json here
print([boxel_data._watcher, gui_page.active(), 'http.server' in sys.modules])
'''
    done = subprocess.run([sys.executable, '-c', code, str(REPO)], cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == '[None, None, False]'


def test_the_stage_hands_the_registry_over_only_when_a_page_was_started():
    text = (REPO / 'world' / 'world_setup.py').read_text(encoding='utf-8')
    assert ('    page = gui_page.active()\n'
            '    if page is not None:\n'
            '        show_on_page(page, st.setup.registry, env)\n') in text
    assert len(re.findall(r'\bgui_page\.(?!py\b)', text)) == 1 and text.count('show_on_page(') == 1
    # and it is the last thing the stage does: the registry is complete by then
    assert text.rstrip().endswith('show_on_page(page, st.setup.registry, env)')
    # the only two modules that tell the watcher
    tellers = sorted(_name(f) for f in _pipeline_files()
                     if re.search(r'\bnote_change\(', f.read_text(encoding='utf-8')))
    assert tellers == ['console/visualization.py', 'world/boxel_data.py']
    # what the page is handed is made in a file of its own (page_boxels.py),
    # the one place that sets the watcher; visualization.py carries the two
    # lines that tell it and nothing else of the page
    assert 'from console.page_boxels import show_on_page\n' in text
    overlay = (REPO / 'console' / 'visualization.py').read_text(encoding='utf-8')
    assert overlay.count('boxel_data.note_change(') == 2
    assert '_for_page' not in overlay and 'show_on_page' not in overlay and 'gui_page' not in overlay
    setters = sorted(_name(f) for f in _pipeline_files()
                     if re.search(r'\bboxel_data\.watch\(', f.read_text(encoding='utf-8')))
    assert setters == ['console/page_boxels.py']


def test_a_watcher_that_fails_never_reaches_the_run():
    """What the watcher raises ends in boxel_data: the registry's methods
    and the overlay's word go on as without it."""
    told = []

    def watcher(boxel_id):
        told.append(boxel_id)
        raise RuntimeError('the page is broken')

    boxel_data.watch(watcher)
    try:
        reg = _registry()
        new = reg.add_boxel(_box('', BoxelType.FREE_SPACE, [0.5, 0.0, 0.325], [0.6, 0.1, 0.4]))
        assert new == 'free_001' and reg.get_boxel(new) is not None
        reg.update_after_place(new, 'blue_object', [0.52, 0.02, 0.325], [0.56, 0.06, 0.365], 0.325)
        assert reg.get_boxel('blue_object').on_surface == 'table' and reg.dirty
        assert reg.remove_boxel('shadow_000').id == 'shadow_000'
        assert boxel_data.note_change('red_object') is None
        assert told[-4:] == [new, 'blue_object', 'shadow_000', 'red_object']
    finally:
        boxel_data.watch(None)


def test_a_page_that_fails_never_reaches_the_run(page):
    """As for the renders (tests/test_window_page.py): every hand-over
    swallows its own errors, and the page keeps what it had."""
    reg = _registry()
    page_boxels.show_on_page(page, reg)
    v0, lock = _version(page), page._lock
    page._lock = None                               # every hand-over fails inside
    try:
        reg.add_boxel(_box('', BoxelType.FREE_SPACE, [0.5, 0.0, 0.325], [0.6, 0.1, 0.4]))
        reg.remove_boxel('shadow_000')
        boxel_data.note_change('red_object')
        page.look_at_boxels()
        page.offer_render(2, 2, np.zeros((2, 2, 4)), np.ones((2, 2)), np.zeros((2, 2)), 0.01, 5.0, 'display')
        page.follow_boxels(reg, page_boxels.boxel_for_page, {'x': [0, 1]})
    finally:
        page._lock = lock
    assert _version(page) == v0 and 'shadow_000' in _by_id(_served(page))
    # the next look brings the page up to date
    page.look_at_boxels()
    assert 'shadow_000' not in _by_id(_served(page))

    # a function for one boxel that fails: that boxel is not shown, the run goes on
    def describe(bd):
        if bd.id == 'red_object':
            raise ValueError('cannot be read')
        return page_boxels.boxel_for_page(bd)

    page.follow_boxels(reg, describe)
    reg.get_boxel('red_object').is_occluder = False
    boxel_data.note_change('red_object')
    assert 'red_object' not in _by_id(_served(page)) and 'blue_object' in _by_id(_served(page))
    # something that is no page at all, and a registry that is none
    page_boxels.show_on_page(object(), reg)
    page_boxels.show_on_page(page, object())
    page.boxel_changed('red_object')
    page.look_at_boxels()
    assert _get(page, '/boxels')[0] == 200


def test_a_page_that_is_stopped_follows_nothing():
    started = gui_page.start(console=None, port=0)
    try:
        reg = _registry()
        page_boxels.show_on_page(started, reg)
        assert boxel_data._watcher == started.boxel_changed
    finally:
        gui_page.stop()
    assert boxel_data._watcher is None and started._registry is None
    reg.remove_boxel('red_object')                  # nobody is told


# ---------------------------------------------------------------------------
# the page's own text
# ---------------------------------------------------------------------------

def test_the_page_asks_for_the_boxels_only_when_their_number_changed(page):
    text = _get(page, '/')[2].decode('utf-8')
    assert "getJSON('/boxels')" in text and text.count("'/boxels'") == 1
    assert 'if (b.version !== bx.version && !bx.asking) askBoxels();' in text
    assert '<canvas id="boxview">' in text and 'The world as boxels:' in text
    # drawn by the page itself: nothing is loaded for it, from the network or the disk
    assert 'http://' not in text and 'https://' not in text
    assert '<script src' not in text and 'import(' not in text and '<link rel="stylesheet"' not in text
    assert "getContext('2d')" in text
    # turning by drag, zoom by the wheel, a turn by itself until the first touch
    for word in ("'pointerdown'", "'pointermove'", "'wheel'", 'bx.turning = false;', 'boxOrder(items, eye)'):
        assert word in text, word
    assert _get(page, '/boxels?v=3')[0] == 200      # a number after the path is fine


def test_the_free_spaces_opacity_is_one_number_in_one_place(page):
    """Hani, 2026-11-25: "the free boxles are mostly very trasnparent".
    gui_page.FREE_OPACITY, handed to the page's script; the free boxels are
    shown unless the reader switches them off."""
    assert 0 < gui_page.FREE_OPACITY <= 0.05
    text = _get(page, '/')[2].decode('utf-8')
    assert '__FREE_OPACITY__' not in text
    assert re.findall(r'const FREE_OPACITY = ([0-9.e-]+);', text) == [repr(float(gui_page.FREE_OPACITY))]
    source = (REPO / 'console' / 'gui_page.py').read_text(encoding='utf-8')
    assert len(re.findall(r'^FREE_OPACITY = ', source, flags=re.M)) == 1
    assert source.count('__FREE_OPACITY__') == 2    # the script's line and the hand-over
    # every use in the drawing is the name, for the fill and for the edge
    assert 'free ? FREE_OPACITY :' in text and 'Math.min(1, FREE_OPACITY * 4)' in text
    assert 'free: true' in text and "id = 'freekey'" in text
