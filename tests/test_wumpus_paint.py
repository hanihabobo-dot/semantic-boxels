"""The painter without the GUI (tracks rule 13): a headless env paints
nothing, paint=True colours the tiles with the GUI's call, and PaintedEnv
writes a picture with the labels, counts a grab as one action and refuses a
folder that holds another run's frames.  Builds DIRECT envs; run under
`flock /root/sb_pipeline.lock` with the other env tests."""
import json

import numpy as np
import pybullet as p
import pytest

from wumpus import knowledge as kn
from wumpus.env import WumpusEnv
from wumpus.world import WumpusWorld

# p1-1, p1-2, p2-1 and p2-2 hold no hazard in any random world (world.py)
KNOWN = {'p1-1': {'wumpus': 'no', 'pit': 'no', 'gold': 'no', 'visited': True},
         'p1-2': {'wumpus': 'no', 'pit': 'no'},
         'p2-1': {'wumpus': 'no'}}


def rgba(env, cell):
    shape = p.getVisualShapeData(env.floor_tile[cell], physicsClientId=env.cid)[0]
    return tuple(round(v, 3) for v in shape[7])


def test_headless_env_paints_nothing():
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        before = {c: rgba(env, c) for c in env.floor_tile}
        env.show_knowledge(KNOWN)
        assert {c: rgba(env, c) for c in env.floor_tile} == before
        assert env.painted is None and env._label_ids == []
    finally:
        env.close()


def test_paint_colours_the_tiles_as_the_gui_does():
    env = WumpusEnv(WumpusWorld.random(5, 0), paint=True)
    try:
        env.show_knowledge(KNOWN)
        want = {'p1-1': 'visited', 'p1-2': 'safe', 'p2-1': 'possible', 'p2-2': 'unknown'}
        for cell, state in want.items():
            assert rgba(env, cell) == tuple(round(v, 3) for v in kn.TILE_RGBA[state]), cell
        assert env.painted == kn.normalize(KNOWN, env.cells())
        assert env._label_ids == []          # the labels are GUI debug text only
    finally:
        env.close()


def test_gui_labels_are_what_the_painter_writes(monkeypatch):
    """The GUI's labels without a window (rule 13): with env.gui set (the flag
    only, no GUI is connected) show_knowledge writes one debug text per cell,
    kn.label at env.label_anchor, black, size 1, and the next call replaces
    them all."""
    import wumpus.env as we
    calls, removed = [], []

    def add(text, pos, **kw):
        calls.append((text, [round(float(v), 6) for v in pos], kw))
        return len(calls)

    monkeypatch.setattr(we.p, 'addUserDebugText', add)
    monkeypatch.setattr(we.p, 'removeUserDebugItem', lambda i, **kw: removed.append(i))
    env = WumpusEnv(WumpusWorld.random(5, 0))
    try:
        env.gui = True
        env.show_knowledge(KNOWN)
        view = kn.normalize(KNOWN, env.cells())
        want = [(kn.label(c, view[c]), [round(float(v), 6) for v in env.label_anchor(c)])
                for c in env.cells()]
        assert [(t, pos) for t, pos, _ in calls] == want
        assert all(kw['textColorRGB'] == [0, 0, 0] and kw['textSize'] == 1.0 for _, _, kw in calls)
        text = {c: t for c, (t, _, _) in zip(env.cells(), calls)}
        assert text['p1-1'] == 'p1-1' and text['p1-2'] == 'p1-2 G?'
        assert text['p2-1'] == 'p2-1 P? G?' and text['p2-2'] == 'p2-2 W? P? G?'
        assert env.painted == view
        first = list(env._label_ids)
        env.show_knowledge({})
        assert removed == first and len(calls) == 2 * len(env.cells())
    finally:
        env.gui = False                      # so close() disconnects the DIRECT client
        env.close()


def test_painted_env_writes_a_picture(tmp_path):
    from PIL import Image
    from wumpus import paint_render as pr
    env = pr.PaintedEnv(WumpusWorld.random(5, 0), str(tmp_path), title='test')
    try:
        view, proj = pr.camera(env)
        x, y = pr.project(view, proj, [2.5, 2.5, 0.0])     # the GUI camera aims at the grid's centre
        assert abs(x - pr.W / 2) < 1 and abs(y - pr.H / 2) < 1

        def at(cell):
            return pr.project(view, proj, list(env.cell_center(cell)) + [0.0])
        # the board the right way round, not mirrored or turned: i grows to the right, j upwards
        (x11, y11), (x51, y51), (x15, y15) = at('p1-1'), at('p5-1'), at('p1-5')
        assert x51 > x11 + 200 and y15 < y11 - 200, (x11, y11, x51, y51, x15, y15)
        env.show_knowledge(KNOWN)
        rec = json.loads((tmp_path / 'frames.json').read_text())
        assert len(rec['frames']) == 1
        fr = rec['frames'][0]
        assert fr['actions'] == 0 and fr['robot_cell'] == 'p1-1'
        assert fr['states']['p1-1'] == 'visited' and fr['states']['p2-2'] == 'unknown'
        assert fr['labels']['p2-2'] == 'p2-2 W? P? G?' and fr['labels']['p1-1'] == 'p1-1'
        assert fr['render_s'] > 0 and rec['render_s'] == fr['render_s'] == env.render_s
        img = Image.open(tmp_path / fr['png'])
        assert img.size == (pr.W, pr.H + pr.BAND)
        px = np.asarray(img.convert('RGB')).astype(int)
        # below p2-2's label line the tile shows the 'unknown' blue-grey, not the floor's grey
        cx, cy = at('p2-2')
        r, g, b = px[int(cy) + 22, int(cx)]
        assert b > r + 20 and b > g, (r, g, b)
        # and below p2-1's the amber of 'possible', the only amber tile in KNOWN: the
        # picture puts each cell's colour where project() puts the cell
        cx, cy = at('p2-1')
        r, g, b = px[int(cy) + 22, int(cx)]
        assert r > b + 80 and g > b + 40, (r, g, b)
        # the labels are drawn: dark text right of p3-3's anchor (random(5, 0) leaves p3-3
        # empty and without markers: the wumpus is at p4-2, the pit at p4-4, the gold at p1-3)
        ax, ay = (int(v) for v in pr.project(view, proj, env.label_anchor('p3-3')))
        dark = int((px[ay - 9:ay + 9, ax:ax + 90].max(axis=2) < 90).sum())
        assert dark > 40, dark
    finally:
        env.close()


def test_painted_env_counts_a_grab_once(tmp_path):
    """grab() perceives before it reaches for the gold (env.py); that perceive
    is part of the grab, so PaintedEnv counts one action for it."""
    from wumpus import paint_render as pr
    env = pr.PaintedEnv(WumpusWorld.random(5, 0), str(tmp_path))
    try:
        r = env.grab()                      # at p1-1; the gold of random(5, 0) is at p1-3
        assert r['why'] == 'no gold seen in this cell' and not r['held'], r
        assert env.n_actions == 1
        assert env.perceive()['ok'] and env.n_actions == 2
    finally:
        env.close()


@pytest.mark.parametrize('old', ['frame_007.png', 'frames.json'])
def test_painted_env_refuses_a_folder_with_frames_of_another_run(tmp_path, old):
    """One folder never mixes two episodes; the refusal comes before the env exists."""
    from wumpus import paint_render as pr
    (tmp_path / old).write_bytes(b'')
    with pytest.raises(ValueError, match='frames of another run'):
        pr.PaintedEnv(WumpusWorld.random(5, 0), str(tmp_path))


def test_painted_env_starts_with_an_empty_record(tmp_path):
    """frames.json is there from the start, so an episode that ends before
    its first knowledge update still leaves a record of no frames."""
    from wumpus import paint_render as pr
    out = tmp_path / 'frames'               # a new folder: PaintedEnv makes it
    env = pr.PaintedEnv(WumpusWorld.random(5, 0), str(out), title='t')
    try:
        assert [f.name for f in out.iterdir()] == ['frames.json']
        rec = json.loads((out / 'frames.json').read_text())
        assert rec['frames'] == [] and rec['render_s'] == 0 and rec['title'] == 't'
    finally:
        env.close()
