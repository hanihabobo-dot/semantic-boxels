"""BF#68, run tampura -Draw cameras: what each of OUR cameras saw at its latest
render, for the camera window (tools/camera_view.ps1: its own window, not the
GUI's).

An observer on pybullet.getCameraImage.  For a TinyRenderer render on the
executing client it reads the result the caller gets (the caller gets the very
same object back) and writes, per camera, DIR/<camera>.png (the rgb image, and
below it the depth image and the segmentation image at half size) and then
DIR/<camera>.json (the caption: render count, plan and step, clock), each by an
atomic replace.  It also draws the camera's view volume as GUI debug lines and
a label.  It asks the simulator nothing, renders nothing, moves and steps
nothing, adds no body and draws no random number.  Debug lines are no bodies
and are in no TinyRenderer image (tests/test_boxel_overlay_lines.py), so the
runs with and without it see and do the same; tools/draw_equiv_run.py and
draw_equiv_compare.py check that, run against run.

Cameras: 'eye' is the render whose matrices are the declared eye's, 'wrist'
every other TinyRenderer render on the executing client.  Gate G20 passes
the declared eye's matrices and a wrist robot's own, except for a render made
inside gate_hooks.capture(...) (world_eye's); those use the eye's matrices
today, and one with another view would be shown as the wrist (display only).
Not shown: the plan twin's test renders (hundreds per replan, not
observations) and the display-only OpenGL renders that keep the GUI's panes
fresh (the same eye, drawn by another renderer).

Order with the gates: install AFTER gate_hooks.install, so the observer wraps
the G20 hook and sees the call after the gate let it through (a render the
gate refuses raises through the observer), and BulletClient reaches it with
its client id (the gates' patch; nothing here checks that it is in place).
Call uninstall() BEFORE gate_hooks.uninstall(), which restores the function it
saved and so drops the observer too when that is the order forgotten.

A viewer must never touch the run, so nothing the observer does may raise into
it:
  * install() that cannot make its folder warns once and installs nothing;
  * a picture that cannot be written after five tries is skipped (the window
    keeps the previous one); ten skipped in a row, or any other error in the
    observer's own work, turns it off with one warning, and the render goes
    through as it was;
  * the warning itself never raises.
The files are written inside the render call, as the run writes its own logs
on the same disk (a stalled disk stalls both).
"""
import functools
import io
import json
import os
import time

import numpy as np
import pybullet

import run_logger

EYE, WRIST = 'eye', 'wrist'
# getCameraImage's positional slots (width, height, viewMatrix,
# projectionMatrix, light..., renderer, ...); the repository passes them by
# keyword, the gate hook reads the first two the same way.
_VIEW, _PROJ, _RENDERER = 2, 3, 11
# A picture is written with this many tries (a pause between them); this many
# skipped pictures in a row turn the observer off.
_TRIES, _PAUSE_S, _MAX_SKIPPED = 5, 0.05, 10
# A view volume's drawn length (m) and colour per camera.
_REACH = {EYE: 0.7, WRIST: 0.25}
_COLOUR = {EYE: (0.1, 0.85, 1.0), WRIST: (1.0, 0.35, 0.9)}
_CORNERS = ((-1, -1), (1, -1), (1, 1), (-1, 1))
# Segmentation colours by body id (a fixed table: the same body, the same
# colour at every render); the background (-1) is black.
_PALETTE = np.array([
    (230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200),
    (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
    (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
    (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195),
    (128, 128, 0), (255, 215, 180), (0, 0, 128), (169, 169, 169)],
    dtype=np.uint8)


def _arg(args, kwargs, pos, name):
    if name in kwargs:
        return kwargs[name]
    return args[pos] if len(args) > pos else None


def _close(a, b, tol):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    return a.shape == b.shape and bool(np.all(np.abs(a - b) <= tol))


def _warn(message):
    """One line on the console and in the run's log.  Never raises: it runs in
    the observer's error paths, inside the render call."""
    try:
        print(f"  camera view: {message}", flush=True)
    except Exception:
        pass
    try:
        import console_ui
        console_ui.warn(f"camera view: {message}")
    except Exception:
        pass


def camera_pose(view):
    """(eye position, right, up, forward) of a camera from its view matrix
    (pybullet's column-major 16 numbers, OpenGL's convention: the camera looks
    along its -z)."""
    v = np.asarray(view, dtype=float).reshape(4, 4, order='F')
    c2w = np.linalg.inv(v)
    return c2w[:3, 3], c2w[:3, 0], c2w[:3, 1], -c2w[:3, 2]


def near_far(proj):
    """(near, far) of a projection matrix from computeProjectionMatrixFOV."""
    p = np.asarray(proj, dtype=float)
    return float(p[14] / (p[10] - 1.0)), float(p[14] / (p[10] + 1.0))


def view_volume(view, proj, reach):
    """The lines of the camera's view volume out to `reach` metres: four edges
    from the eye to the rectangle's corners, then the rectangle.  Returns a
    list of (start, end) points."""
    eye, right, up, fwd = camera_pose(view)
    p = np.asarray(proj, dtype=float)
    tx, ty = 1.0 / p[0], 1.0 / p[5]
    corner = [eye + reach * (fwd + sx * tx * right + sy * ty * up)
              for sx, sy in _CORNERS]
    return ([(eye, c) for c in corner]
            + [(corner[i], corner[(i + 1) % 4]) for i in range(4)])


class CameraObserver:
    """See the module docstring.  `out_dir`: where the files go;
    `executing_client`: the client whose renders are shown; `eye_view`,
    `eye_proj`: the declared eye's matrices (the gate's); `frustums`: draw the
    view volumes in the GUI."""

    def __init__(self, out_dir, executing_client, eye_view, eye_proj,
                 frustums=True, tol=1e-6):
        self.out_dir = str(out_dir)
        self.client = int(executing_client)
        self.eye_view = np.asarray(eye_view, dtype=float)
        self.eye_proj = np.asarray(eye_proj, dtype=float)
        self.frustums = frustums
        self.tol = tol
        self.counts = {}          # camera -> renders shown so far
        self.disabled = False
        self.error = None
        self.skipped = 0          # pictures not written, in a row
        self._items = {}          # camera -> debug item ids it drew
        self._inner = None
        self._hook = None

    def _turn_off(self, error, what):
        self.disabled = True
        self.error = f"{type(error).__name__}: {error}"
        _warn(f"{what} ({self.error})")

    # ----- install -------------------------------------------------------

    def install(self):
        """Put the observer on getCameraImage.  A folder that cannot be made
        (a file in its place, a full or read-only disk) leaves the observer
        off and the run without it: only a second install is an error."""
        if self._hook is not None:
            raise RuntimeError('the camera observer is already installed')
        try:
            os.makedirs(self.out_dir, exist_ok=True)
        except Exception as e:
            self._turn_off(e, 'could not start, the run goes on without it')
            return
        inner = pybullet.getCameraImage
        observer = self

        @functools.wraps(inner)
        def hook(*args, **kwargs):
            result = inner(*args, **kwargs)
            if not observer.disabled:
                observer._see(args, kwargs, result)
            return result

        # gate_hooks patches BulletClient to put the client id into the
        # functions marked so (a Python function is no builtin).
        hook._gate_wrapped = True
        self._inner, self._hook = inner, hook
        pybullet.getCameraImage = hook

    def uninstall(self):
        """Put back what install found; a no-op when something else (the
        gates' uninstall) already did."""
        if self._hook is not None and pybullet.getCameraImage is self._hook:
            pybullet.getCameraImage = self._inner
        self._hook = None

    # ----- the observer --------------------------------------------------

    def _see(self, args, kwargs, result):
        try:
            if int(kwargs.get('physicsClientId', 0)) != self.client:
                return
            if _arg(args, kwargs, _RENDERER, 'renderer') != pybullet.ER_TINY_RENDERER:
                return
            view = _arg(args, kwargs, _VIEW, 'viewMatrix')
            proj = _arg(args, kwargs, _PROJ, 'projectionMatrix')
            if view is None or proj is None:
                return
            eye = (_close(view, self.eye_view, self.tol)
                   and _close(proj, self.eye_proj, self.tol))
            self._show(EYE if eye else WRIST, view, proj, result)
        except Exception as e:
            self._turn_off(e, 'turned off, the run goes on without it')

    def _show(self, cam, view, proj, result):
        w, h = int(result[0]), int(result[1])
        n = self.counts[cam] = self.counts.get(cam, 0) + 1
        rgb = np.asarray(result[2], dtype=np.uint8).reshape(h, w, 4)[:, :, :3]
        buf = np.asarray(result[3], dtype=float).reshape(h, w)
        seg = np.asarray(result[4]).reshape(h, w)
        near, far = near_far(proj)
        depth_img, span = self._depth_image(buf, near, far)
        seg_img = _PALETTE[np.mod(seg, len(_PALETTE))]
        seg_img[seg < 0] = 0
        canvas = np.zeros((h + h // 2, w, 3), dtype=np.uint8)
        canvas[:h] = rgb
        half_h, half_w = h // 2, w // 2
        canvas[h:, :half_w] = depth_img[::2, ::2][:half_h, :half_w]
        canvas[h:, half_w:2 * half_w] = seg_img[::2, ::2][:half_h, :half_w]
        from PIL import Image
        png = io.BytesIO()
        Image.fromarray(canvas).save(png, format='PNG', compress_level=1)
        d = run_logger.current_dispatch()
        meta = {'camera': cam, 'n': n, 'size': f"{w}x{h}",
                'plan': d['plan'] if d else None,
                'step': d['step'] if d else None,
                'action': str(d['action']) if d else None,
                'depth_m': span, 'clock': time.strftime('%H:%M:%S'),
                'wall': time.time()}
        try:
            # the picture first, then its caption: the window reads the caption
            # file as the sign that a new picture is there
            self._write(os.path.join(self.out_dir, f"{cam}.png"), png.getvalue())
            self._write(os.path.join(self.out_dir, f"{cam}.json"),
                        json.dumps(meta).encode('utf-8'))
            self.skipped = 0
        except OSError as e:
            # this picture is skipped, the window keeps the previous one
            self.skipped += 1
            if self.skipped == 1:
                _warn(f"a picture could not be written and is skipped "
                      f"({type(e).__name__}: {e}); {_MAX_SKIPPED} in a row turn the view off")
            if self.skipped >= _MAX_SKIPPED:
                raise
        if self.frustums:
            self._draw_volume(cam, view, proj, n)

    @staticmethod
    def _depth_image(buf, near, far):
        """Grey image of the depth (near bright), scaled to this render's own
        nearest and farthest surface; the span in metres goes in the caption."""
        z = far * near / (far - (far - near) * buf)
        seen = buf < 0.9999
        if not seen.any():
            return np.zeros(buf.shape + (3,), dtype=np.uint8), None
        lo, hi = float(z[seen].min()), float(z[seen].max())
        t = np.clip((z - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
        grey = np.where(seen, 255.0 * (1.0 - t), 0.0).astype(np.uint8)
        return np.repeat(grey[:, :, None], 3, axis=2), [round(lo, 3), round(hi, 3)]

    @staticmethod
    def _write(path, data):
        """Write beside, then replace: the viewer never reads half a file.
        Windows refuses the replace (or the write beside) for a moment while
        the viewer, or a virus scanner, holds a file open: the whole sequence
        is tried again a little later, and the last error raised."""
        tmp = path + '.tmp'
        for attempt in range(_TRIES):
            try:
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, path)
                return
            except OSError:
                if attempt == _TRIES - 1:
                    raise
                time.sleep(_PAUSE_S)

    def _draw_volume(self, cam, view, proj, n):
        """The camera's view volume and its name, as GUI debug items; the
        camera's earlier ones go first.  Drawn again at every render for the
        eye too: the wrist moves, and the run's GUI cleanup between steps
        removes every debug item."""
        c = self.client
        for item in self._items.pop(cam, []):
            pybullet.removeUserDebugItem(item, physicsClientId=c)
        colour = _COLOUR[cam]
        ids = [pybullet.addUserDebugLine(
                   [float(x) for x in a], [float(x) for x in b],
                   lineColorRGB=colour, lineWidth=1.5, lifeTime=0,
                   physicsClientId=c)
               for a, b in view_volume(view, proj, _REACH[cam])]
        eye = camera_pose(view)[0]
        ids.append(pybullet.addUserDebugText(
            f"{cam} #{n}", [float(x) for x in eye], textColorRGB=colour,
            textSize=1.2, lifeTime=0, physicsClientId=c))
        self._items[cam] = ids
