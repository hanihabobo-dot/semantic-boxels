"""Render the page's screenshots of one TAMPURA task at seed 0.
Usage (cwd /root/task_shots, via run.sh): python shots.py <task>"""
import os
import shutil
import sys

import numpy as np

import common as C
from common import IMG, label, project, ring, shade

os.makedirs(IMG, exist_ok=True)
task = sys.argv[1]


def save(img, name):
    path = os.path.join(IMG, name)
    img.save(path, optimize=True)
    print('wrote', path)


def plain(client, cam, shadow=True):
    rgb, _ = C.render_full(client, *cam, shadow=shadow)
    return C.downsample(rgb)


def pos(client, body):
    return client.getBasePositionAndOrientation(body)[0]


if task == 'find_dice':
    env, _ = C.build_env(task)
    w = env.world
    c = w.client
    die = next(b for b, cat in zip(w.objects, w.categories) if 'dice' in str(cat))
    die_xyz = pos(c, die)
    cams = {
        'oblique': ((1.45, -0.35, 1.25), (0.40, 0.0, 0.15), (0, 0, 1)),
        'top': ((0.40, 0.01, 1.15), (0.40, 0.01, 0.0), (1, 0, 0)),
    }
    for view, cam in cams.items():
        img = plain(c, cam)
        px = project(die_xyz, *cam)
        r = 34
        ring(img, px, r=r)
        off = (-200, 120) if view == 'oblique' else (-60, 140)
        label(img, (px[0], px[1] + r), 'die (hidden under this cup)', off, dot=(220, 0, 0))
        label(img, project((0.05, 0, 0.3), *cam), 'Panda arm', (-40, -90) if view == 'oblique' else (220, 0))
        save(img, f'find_dice_{view}.png')

elif task == 'class_uncertain':
    env, _ = C.build_env(task)
    w = env.state.world
    c = w.client
    names = [cat for cat in w.categories if cat != 'bowl']
    kinds = {'apple': 'fruit', 'lemon': 'fruit', 'strawberry': 'fruit',
             'tennis_ball': 'ball', 'racquetball': 'ball', 'baseball': 'ball'}
    bowl = w.regions[1]
    print('pairs', list(zip(w.objects, names)), 'bowl', bowl)
    cams = {
        'oblique': ((1.25, -0.35, 0.95), (0.45, 0.05, 0.05), (0, 0, 1)),
        'top': ((0.52, 0.06, 0.80), (0.52, 0.06, 0.0), (1, 0, 0)),
    }
    offs = {
        'oblique': {'strawberry': (90, 130), 'racquetball': (-130, 130), 'tennis_ball': (-170, -110), 'bowl': (150, -110)},
        'top': {'strawberry': (0, 110), 'racquetball': (-40, 110), 'tennis_ball': (0, 120), 'bowl': (180, -170)},
    }
    for view, cam in cams.items():
        img = plain(c, cam)
        for body, name in zip(w.objects, names):
            txt = f"{name.replace('_', ' ')} ({kinds[name]})"
            label(img, project(pos(c, body), *cam), txt, offs[view][name])
        label(img, project(pos(c, bowl), *cam), 'bowl', offs[view]['bowl'])
        save(img, f'class_uncertain_{view}.png')

elif task == 'tool_use':
    env, _ = C.build_env(task)
    w = env.world
    c = w.client
    cubes = w.objects[:3]
    hook = w.objects[3]
    particles = [b for cube in cubes for b in w.ghosts[cube][1:]]
    print('cubes', cubes, 'hook', hook, 'particles', len(particles))
    cams = {
        'oblique': ((1.20, -0.30, 0.80), (0.40, -0.05, 0.03), (0, 0, 1)),
        'top': ((0.36, -0.05, 0.80), (0.36, -0.05, 0.0), (1, 0, 0)),
    }
    offs = {
        'oblique': [(-150, -110), (150, 100), (60, -120)],
        'top': [(0, 120), (180, 110), (260, -50)],
    }
    saved = {b: c.getBasePositionAndOrientation(b) for b in particles}
    for view, cam in cams.items():
        rgb_all, seg = C.render_full(c, *cam)
        for b in particles:
            c.resetBasePositionAndOrientation(b, (saved[b][0][0], saved[b][0][1], -5), saved[b][1])
        rgb_real, _ = C.render_full(c, *cam)
        for b, (p_, o_) in saved.items():
            c.resetBasePositionAndOrientation(b, p_, o_)
        mask = np.isin(seg, particles)[:, :, None]
        out = np.where(mask, 0.35 * rgb_all + 0.65 * rgb_real, rgb_real).astype(np.uint8)
        img = C.downsample(out)
        C.downsample(rgb_all).save(os.path.join(C.SHOTS, f'tool_use_{view}_all_solid.png'))
        for i, cube in enumerate(cubes):
            label(img, project(pos(c, cube), *cam), f'cube {i} and 9 guesses', offs[view][i])
        label(img, project(pos(c, hook), *cam), 'hook (pose known)', (-120, 90) if view == 'oblique' else (-210, 0))
        save(img, f'tool_use_{view}.png')

elif task == 'puck_slide':
    env, _ = C.build_env(task)
    w = env.state.world
    c = w.client
    puck = w.objects[0]
    hidden = []
    for i in range(c.getNumBodies()):
        b = c.getBodyUniqueId(i)
        vs = c.getVisualShapeData(b)
        if vs and all(v[7][3] == 0 for v in vs):
            hidden.append(b)
    print('alpha-0 bodies moved away for rendering:', hidden)
    cams = {
        'oblique': ((0.55, -1.55, 1.0), (0.60, 0.0, 0.15), (0, 0, 1)),
        'top': ((0.52, 0.0, 1.35), (0.52, 0.0, 0.0), (0, 1, 0)),
    }
    first = {v: plain(c, cam) for v, cam in cams.items()}
    for v, img in first.items():
        img.save(os.path.join(C.SHOTS, f'puck_slide_{v}_with_surface.png'))
    for b in hidden:
        o = c.getBasePositionAndOrientation(b)[1]
        c.resetBasePositionAndOrientation(b, (0, 0, -20), o)
    z = 0.052
    reach = [(0.3, -0.35, z), (0.9, -0.35, z), (0.9, 0.35, z), (0.3, 0.35, z)]
    goal = [(1.2, -0.35, z), (1.4, -0.35, z), (1.4, 0.35, z), (1.2, 0.35, z)]
    for view, cam in cams.items():
        rgb, seg = C.render_full(c, *cam)
        base = C.downsample(rgb)
        img = shade(base, reach, cam, (40, 110, 235, 95))
        img = shade(img, goal, cam, (30, 170, 80, 110))
        # keep the pucks unshaded so their own colour shows
        from PIL import Image
        puck_mask = Image.fromarray((np.isin(seg, w.objects) * 255).astype(np.uint8)).resize(C.OUT, Image.NEAREST)
        img.paste(base, (0, 0), puck_mask)
        if view == 'oblique':
            label(img, project(pos(c, puck), *cam), 'puck (friction unknown)', (-40, -130))
            label(img, project((0.75, -0.3, z), *cam), 'reach region', (0, 110))
            label(img, project((1.3, 0.2, z), *cam), 'goal', (40, -110))
        else:
            label(img, project(pos(c, puck), *cam), 'puck (friction unknown)', (0, -150))
            label(img, project((0.75, -0.28, z), *cam), 'reach region', (0, 80))
            label(img, project((1.3, -0.28, z), *cam), 'goal', (-20, 80))
        save(img, f'puck_slide_{view}.png')

elif task in ('slam_collect', 'slam_collect_simple'):
    import matplotlib
    matplotlib.rcParams['savefig.dpi'] = 200
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Rectangle
    from PIL import Image, ImageChops
    env, save_dir = C.build_env(task)
    # their frame, with the empty white margin trimmed (the raw file stays in save_dir/frames)
    frame = Image.open(os.path.join(save_dir, 'frames', 'frame_000.png')).convert('RGB')
    bbox = ImageChops.difference(frame, Image.new('RGB', frame.size, 'white')).getbbox()
    pad = 24
    frame = frame.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                        min(frame.width, bbox[2] + pad), min(frame.height, bbox[3] + pad)))
    frame.save(os.path.join(IMG, f'{task}_theirs.png'), optimize=True)
    print('saved their frame_000.png, trimmed to', frame.size)
    if task == 'slam_collect':
        s = env.state

        def corners(pose, w_, h_):
            ct, st = np.cos(pose.theta), np.sin(pose.theta)
            pts = []
            for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                x, y = sx * w_ / 2, sy * h_ / 2
                pts.append((pose.x + ct * x - st * y, pose.y + st * x + ct * y))
            return pts

        plt.rcParams['font.family'] = 'DejaVu Sans'
        fig, ax = plt.subplots(figsize=(8, 8), dpi=128)
        ax.add_patch(Rectangle((0, 0), 10, 10, fc='#f7f7f4', ec='#333', lw=1.2))
        for b in s.beacons:
            ax.add_patch(Polygon(corners(b.pose, b.shape.width, b.shape.height), closed=True,
                                 fc='#3b6fd6', alpha=0.12, ec='#3b6fd6', lw=1, ls='--'))
            ax.add_patch(Polygon(corners(b.pose, 0.4, 0.4), closed=True, fc='#2851a3', ec='black', lw=0.8))
        for o in s.obstacles:
            ax.add_patch(Polygon(corners(o.pose, o.shape.width, o.shape.height), closed=True,
                                 fc='#8a8a8a', ec='black', lw=0.8))
        for t in s.targets:
            ax.add_patch(Polygon(corners(t.pose, t.shape.width, t.shape.height), closed=True,
                                 fc='#f2c230', ec='black', lw=0.8))
        g = s.goal
        ax.add_patch(Polygon(corners(g.pose, g.shape.width, g.shape.height), closed=True,
                             fc='#3aa655', alpha=0.6, ec='#1d6b31', lw=1.2))
        r = s.robot
        rc = corners(r.pose, r.shape.width, r.shape.height)
        tri = [((rc[0][0] + rc[3][0]) / 2, (rc[0][1] + rc[3][1]) / 2), rc[1], rc[2]]
        ax.add_patch(Polygon(tri, closed=True, fc='#8e44ad', ec='black', lw=0.8))
        for cn in s.corners:
            ax.plot(cn.pose.x, cn.pose.y, marker='s', ms=9, color='#c0392b', clip_on=False, zorder=5)
        box = dict(boxstyle='round,pad=0.4', fc='white', ec='#555', lw=0.8)
        arrow = dict(arrowstyle='-', color='#333', lw=1)
        kw = dict(fontsize=10.5, fontweight='bold', bbox=box, arrowprops=arrow, color='#222')
        ax.annotate('goal: bring all three\ntargets here', (g.pose.x, g.pose.y), (6.3, 9.0), **kw)
        b0 = s.beacons[2]
        ax.annotate('beacon: drive into its square\nto learn your exact position', (b0.pose.x, b0.pose.y), (0.6, 2.4), **kw)
        t0 = s.targets[1]
        ax.annotate('target block (0.5 m)', (t0.pose.x, t0.pose.y), (5.6, 3.3), **kw)
        ax.annotate('robot at start\n(position becomes uncertain\nas it drives)', (r.pose.x, r.pose.y), (2.2, 0.5), **kw)
        o0 = s.obstacles[4]
        ax.annotate('obstacle: touching one fails', (o0.pose.x, o0.pose.y), (6.0, 0.35), **kw)
        ax.annotate('map corner: also gives\nthe exact position', (10, 10), (7.1, 10.55), annotation_clip=False, **kw)
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        handles = [
            Patch(fc='#8e44ad', ec='black', label='robot (0.3 x 0.6 m)'),
            Patch(fc='#8a8a8a', ec='black', label='obstacle'),
            Patch(fc='#f2c230', ec='black', label='target block'),
            Patch(fc='#3aa655', alpha=0.6, ec='#1d6b31', label='goal (0.8 m)'),
            Patch(fc='#2851a3', ec='black', label='beacon (0.4 m)'),
            Patch(fc='#3b6fd6', alpha=0.12, ec='#3b6fd6', ls='--', label='beacon square (2 m)'),
            Line2D([], [], marker='s', ls='', ms=9, color='#c0392b', label='map corner'),
        ]
        ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.08), ncol=4,
                  frameon=False, fontsize=10)
        ax.set_xlim(-0.3, 10.3)
        ax.set_ylim(-0.3, 11.3)
        ax.set_aspect('equal')
        ax.set_xlabel('x (m)')
        ax.set_ylabel('y (m)')
        ax.spines[['top', 'right']].set_visible(False)
        fig.set_size_inches(8, 8.8)
        fig.tight_layout()
        fig.savefig(os.path.join(IMG, 'slam_collect_map.png'), dpi=128)
        print('wrote slam_collect_map.png')
