"""
The world as boxels for the page beside our own window (gui_page.py, its
fourth view; Hani, 2026-11-25).  Display only.

The page gets the registry's own content and nothing else, with the label and
the colour of the overlay in the window, both from visualization's two
functions, so that the page and the window cannot drift apart.  The page is
told the id of a changed boxel by boxel_data's watcher (the registry's own
methods, and the overlay where it redraws a boxel that may have been changed
in place) and reads that boxel from the registry it follows.

Nothing here runs in a run without a page, and nothing here calls PyBullet.
A file of its own so that visualization.py carries two lines for the page and
no more.
"""

from typing import Optional

import numpy as np

from world import boxel_data
from world.boxel_data import BoxelData
from console.visualization import _color_for_boxel, _label_for_boxel


def boxel_for_page(bd: BoxelData) -> tuple:
    """One boxel as the page shows it: (id, kind, min corner, max corner,
    label, colour, occluder, region kind).  Plain values; the corners in
    tenths of a millimetre, whole numbers: the page keeps them and compares
    them with the next ones, so a boxel written again with the same numbers,
    or moved by less than that, is no change.  Runs on the run's own thread
    for every changed boxel of a run with the page, so it is kept short."""
    lo = np.asarray(bd.min_corner, dtype=float).tolist()
    hi = np.asarray(bd.max_corner, dtype=float).tolist()
    return (bd.id, bd.boxel_type.value,
            (round(lo[0] * 1e4), round(lo[1] * 1e4), round(lo[2] * 1e4)),
            (round(hi[0] * 1e4), round(hi[1] * 1e4), round(hi[2] * 1e4)),
            _label_for_boxel(bd), tuple(_color_for_boxel(bd)),
            bool(bd.is_occluder), getattr(bd, 'region_kind', 'lateral'))


def ground_for_page(env) -> Optional[dict]:
    """The table's top as the ground of the page's view and the robot's base
    on the floor: what the scene's furniture is, no object's pose.  None for
    an env that does not say."""
    try:
        base = getattr(env, '_ROBOT_BASE_XY', None)
        return {'x': [float(v) for v in env.table_x_range],
                'y': [float(v) for v in env.table_y_range],
                'z': float(env.table_surface_height),
                'robot': None if base is None else [float(base[0]), float(base[1]), 0.0]}
    except Exception:
        return None


def show_on_page(page, registry, env=None) -> None:
    """From here on the page shows this registry: as it stands now, and every
    change (boxel_data.watch tells the page the id of a changed boxel; the
    page reads that boxel from the registry it follows).  Called once the
    registry is built, by world_setup.build_registry, only when a page was
    started.  A page that fails here never reaches the run."""
    try:
        page.follow_boxels(registry, boxel_for_page, ground_for_page(env))
        boxel_data.watch(page.boxel_changed)
    except Exception:
        pass
