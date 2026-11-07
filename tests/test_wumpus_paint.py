"""The painter without the GUI (tracks rule 13): a headless env paints
nothing, paint=True colours the tiles with the GUI's call, and PaintedEnv
writes a picture with the labels.  Builds DIRECT envs; run under
`flock /root/sb_pipeline.lock` with the other env tests."""
import json

import numpy as np
import pybullet as p

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


def test_painted_env_writes_a_picture(tmp_path):
    from PIL import Image
    from wumpus import paint_render as pr
    env = pr.PaintedEnv(WumpusWorld.random(5, 0), str(tmp_path), title='test')
    try:
        view, proj = pr.camera(env)
        x, y = pr.project(view, proj, [2.5, 2.5, 0.0])     # the GUI camera aims at the grid's centre
        assert abs(x - pr.W / 2) < 1 and abs(y - pr.H / 2) < 1
        env.show_knowledge(KNOWN)
        rec = json.loads((tmp_path / 'frames.json').read_text())
        assert len(rec['frames']) == 1
        fr = rec['frames'][0]
        assert fr['actions'] == 0 and fr['robot_cell'] == 'p1-1'
        assert fr['states']['p1-1'] == 'visited' and fr['states']['p2-2'] == 'unknown'
        assert fr['labels']['p2-2'] == 'p2-2 W? P? G?' and fr['labels']['p1-1'] == 'p1-1'
        img = Image.open(tmp_path / fr['png'])
        assert img.size == (pr.W, pr.H + pr.BAND)
        px = np.asarray(img.convert('RGB')).astype(int)
        # below p2-2's label line the tile shows the 'unknown' blue-grey, not the floor's grey
        cx, cy = pr.project(view, proj, list(env.cell_center('p2-2')) + [0.0])
        r, g, b = px[int(cy) + 22, int(cx)]
        assert b > r + 20 and b > g, (r, g, b)
    finally:
        env.close()
