"""Off-screen pictures of the painter: no window on Hani's desktop (tracks rule 13).

    python wumpus/run_wumpus.py --vis 0 --paint-frames DIR [the run's other flags]

The runner then builds a PaintedEnv: a WumpusEnv with paint=True, so its
show_knowledge colours the tiles in DIRECT mode with the same call as in the
GUI (env.py), and after every knowledge update it renders the board with the
tiny renderer from the GUI's own camera (env.py: distance 1.5 N s + 2, yaw 0,
pitch -60, aimed at the grid's centre), draws each cell's label at the GUI's
anchor (env.label_anchor; the GUI shows the labels as debug text, which no
camera image holds), adds a title and the colour legend, and writes
DIR/frame_NNN.png.  DIR/frames.json lists every frame: the actions so far, the
robot's cell, the counts, and each cell's tile state and label.

The pictures are made between the controller's calls and nothing in them is
read back, and the tiles are no percept (perceive() reads the segmentation by
body id), so the episode makes the same moves as without --paint-frames; only
its wall times grow by the rendering.
"""
import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pybullet as p
from PIL import Image, ImageDraw, ImageFont

from wumpus import knowledge as kn
from wumpus.env import WumpusEnv

W, H = 1600, 1200            # the rendered board, pixels
BAND = 110                   # the legend band below it
FOV = 50.0                   # vertical field of view, degrees
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
LEGEND = (('unknown', 'nothing known'), ('possible', 'one hazard ruled out'),
          ('safe', 'both hazards ruled out'), ('visited', 'visited'), ('danger', 'hazard known'))
LABEL_KEY = 'label: the cell, then W? P? G? for what it may hold, W! P! G! for what it holds'


def _font(size: int):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def camera(env) -> Tuple[tuple, tuple]:
    """The GUI's camera (env.py, resetDebugVisualizerCamera) as view and projection matrices."""
    n, s = env.world.n, env.s
    half = n * s / 2
    view = p.computeViewMatrixFromYawPitchRoll(cameraTargetPosition=[half, half, 0],
                                               distance=1.5 * n * s + 2, yaw=0, pitch=-60,
                                               roll=0, upAxisIndex=2)
    proj = p.computeProjectionMatrixFOV(fov=FOV, aspect=W / H, nearVal=0.1, farVal=100.0)
    return view, proj


def project(view, proj, xyz) -> Optional[Tuple[float, float]]:
    """A world point to picture pixels (x to the right, y down); None behind the camera."""
    v = np.array(view, dtype=float).reshape(4, 4).T          # pybullet's are column-major
    pr = np.array(proj, dtype=float).reshape(4, 4).T
    c = pr @ v @ np.array([xyz[0], xyz[1], xyz[2], 1.0])
    if c[3] <= 0:
        return None
    return ((c[0] / c[3] + 1) / 2 * W, (1 - c[1] / c[3]) / 2 * H)


def picture(env, view_k: Dict, title: str) -> Image.Image:
    """The board as the GUI shows it now, with the labels, a title and the legend."""
    view, proj = camera(env)
    _, _, rgba, _, _ = p.getCameraImage(W, H, viewMatrix=view, projectionMatrix=proj,
                                        renderer=p.ER_TINY_RENDERER, physicsClientId=env.cid)
    board = Image.fromarray(np.asarray(rgba, dtype=np.uint8).reshape(H, W, 4)[:, :, :3])
    img = Image.new('RGB', (W, H + BAND), (255, 255, 255))
    img.paste(board, (0, 0))
    d = ImageDraw.Draw(img)
    f = _font(15)
    for cell, e in view_k.items():
        at = project(view, proj, env.label_anchor(cell))
        if at is not None:
            d.text(at, kn.label(cell, e), fill=(0, 0, 0), font=f, anchor='lm')
    ft = _font(22)
    d.rectangle([0, 0, W, 40], fill=(255, 255, 255))
    d.text((12, 20), title, fill=(0, 0, 0), font=ft, anchor='lm')
    x = 12
    for state, words in LEGEND:
        r, g, b, _ = kn.TILE_RGBA[state]
        d.rectangle([x, H + 14, x + 34, H + 48], fill=(int(r * 255), int(g * 255), int(b * 255)),
                    outline=(0, 0, 0))
        d.text((x + 44, H + 31), words, fill=(0, 0, 0), font=ft, anchor='lm')
        x += 44 + int(d.textlength(words, font=ft)) + 36
    d.text((12, H + 82), LABEL_KEY, fill=(0, 0, 0), font=ft, anchor='lm')
    return img


class PaintedEnv(WumpusEnv):
    """A WumpusEnv that paints without the GUI and writes a picture after every
    knowledge update (see the module's text)."""

    def __init__(self, world, out_dir: str, title: str = '', **kw):
        kw['paint'] = True
        super().__init__(world, **kw)
        self.out_dir, self.title = out_dir, title
        self.n_actions = 0
        self.frames: List[Dict] = []
        os.makedirs(out_dir, exist_ok=True)

    def perceive(self):
        r = super().perceive()
        self.n_actions += 1
        return r

    def move(self, cell):
        r = super().move(cell)
        self.n_actions += 1
        return r

    def grab(self):
        r = super().grab()
        self.n_actions += 1
        return r

    def show_knowledge(self, knowledge):
        super().show_knowledge(knowledge)
        view_k = self.painted
        k = len(self.frames)
        here = self.robot_cell()
        c = kn.counts(view_k, self.cells())
        head = (f'{self.title}  |  after {self.n_actions} actions, robot at {here}  |  '
                f"visited {c['visited']}, safe {c['safe']}, maybe pit {c['maybe_pit']}, "
                f"maybe wumpus {c['maybe_wumpus']}, gold {'known' if c['gold_known'] else 'not known'}")
        png = f'frame_{k:03d}.png'
        picture(self, view_k, head).save(os.path.join(self.out_dir, png))
        self.frames.append({'frame': k, 'png': png, 'actions': self.n_actions, 'robot_cell': here,
                            'counts': c, 'states': {cl: kn.tile_state(e) for cl, e in view_k.items()},
                            'labels': {cl: kn.label(cl, e) for cl, e in view_k.items()}})
        with open(os.path.join(self.out_dir, 'frames.json'), 'w') as f:
            json.dump({'title': self.title, 'size': [W, H + BAND], 'frames': self.frames}, f, indent=1)
