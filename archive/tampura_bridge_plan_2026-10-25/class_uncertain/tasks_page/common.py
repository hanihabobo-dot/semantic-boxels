"""Shared helpers for the task screenshots: build a TAMPURA env exactly as
run_planner.py does (seed 0), render with TinyRenderer, project points and
draw PIL labels. Run from cwd /root/task_shots (see shots.sh)."""
import os
import random

import numpy as np
import pybullet as p
from PIL import Image, ImageDraw, ImageFont

HERE = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/class_uncertain/tasks_page'
IMG = os.path.join(HERE, 'img')
SHOTS = os.path.join(HERE, 'shots')
FULL = (2048, 1536)
OUT = (1024, 768)
FOV = 55
FONT = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)


def build_env(task, seed=0):
    from tampura.config import config as tconfig
    import tampura_environments  # noqa: F401  registers the tasks
    save_dir = os.path.join(SHOTS, f'run_{task}')
    os.makedirs(save_dir, exist_ok=True)
    cfg = f'./env_configs/{task}.yml'
    config = tconfig.load_config(config_file=cfg, arg_dict={
        'config': cfg, 'global_seed': seed, 'vis': False, 'save_dir': save_dir})
    random.seed(seed)
    np.random.seed(seed)
    env = tconfig.get_env(config['task'])(config=config)
    env.initialize()
    return env, save_dir


def matrices(eye, target, up):
    view = p.computeViewMatrix(eye, target, up)
    proj = p.computeProjectionMatrixFOV(fov=FOV, aspect=4 / 3, nearVal=0.05, farVal=10)
    return view, proj


def render_full(client, eye, target, up, shadow=True):
    """Full-resolution RGB (H, W, 3) uint8 and the segmentation buffer."""
    view, proj = matrices(eye, target, up)
    W, H = FULL
    kw = dict(shadow=1, lightDirection=[0.08, -0.05, 1.0]) if shadow else {}
    w, h, rgba, _, seg = client.getCameraImage(W, H, viewMatrix=view, projectionMatrix=proj,
                                               renderer=p.ER_TINY_RENDERER, **kw)
    rgb = np.asarray(rgba, dtype=np.uint8).reshape(h, w, 4)[:, :, :3].copy()
    seg = np.asarray(seg).reshape(h, w)
    return rgb, seg


def downsample(rgb):
    return Image.fromarray(rgb).resize(OUT, Image.LANCZOS)


def project(pt, eye, target, up, size=OUT):
    view, proj = matrices(eye, target, up)
    V = np.asarray(view, dtype=float).reshape(4, 4).T
    P = np.asarray(proj, dtype=float).reshape(4, 4).T
    clip = P @ V @ np.append(np.asarray(pt, dtype=float), 1.0)
    return ((clip[0] / clip[3] + 1) / 2 * size[0], (1 - clip[1] / clip[3]) / 2 * size[1])


def shade(img, corners3d, cam, fill):
    """Translucent polygon from projected world corners; fill is RGBA."""
    pts = [project(c, *cam) for c in corners3d]
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=fill, outline=fill[:3] + (230,))
    out = Image.alpha_composite(img.convert('RGBA'), layer)
    return out.convert('RGB')


def label(img, anchor, text, offset, dot=(30, 30, 30)):
    """Dot at anchor (px), leader line, rounded white box centred at anchor+offset."""
    d = ImageDraw.Draw(img)
    ax, ay = anchor
    bx, by = ax + offset[0], ay + offset[1]
    l, t, r, b = d.textbbox((0, 0), text, font=FONT)
    tw, th = r - l, b - t
    pad = 8
    box = [bx - tw / 2 - pad, by - th / 2 - pad, bx + tw / 2 + pad, by + th / 2 + pad]
    # keep the box inside the image
    dx = max(0, 4 - box[0]) - max(0, box[2] - (img.width - 4))
    dy = max(0, 4 - box[1]) - max(0, box[3] - (img.height - 4))
    box = [box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy]
    cx = min(max(ax, box[0]), box[2])
    cy = min(max(ay, box[1]), box[3])
    if offset != (0, 0):
        d.line([(ax, ay), (cx, cy)], fill=(40, 40, 40), width=2)
    d.ellipse([ax - 5, ay - 5, ax + 5, ay + 5], fill=dot, outline=(255, 255, 255), width=2)
    d.rounded_rectangle(box, radius=8, fill=(255, 255, 255), outline=(70, 70, 70), width=1)
    d.text((box[0] + pad - l, box[1] + pad - t), text, font=FONT, fill=(25, 25, 25))
    return img


def ring(img, center, r=22, color=(220, 0, 0)):
    d = ImageDraw.Draw(img)
    x, y = center
    d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=4)
    return img
