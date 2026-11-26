"""The page beside our own simulator window (Hani, 2026-11-22; BF#27).

With `--gui-page on` our own window (`run boxels`) opens without PyBullet's
own panels (the menu, the tabs, the Params column, the white strip, the
status bar, the grid and the three camera panes: one switch,
COV_ENABLE_GUI, set by boxel_env) and this module serves a page for a
browser beside it: the console's moving drawing of what the robot does now
with its status, the three pictures of the robot's camera (colour, depth,
mask), the world as boxels (Hani, 2026-11-25) and the console's committed
lines.

Display only.  Nothing here feeds a decision, and nothing here calls
PyBullet (this module does not import it): PyBullet's client takes one
caller thread and the page is served from a thread of its own.  What the
page shows is handed over by the run's main thread:

  the camera   boxel_env hands copies of renders it makes anyway
               (Page.offer_render): the robot's own detection render and
               the display render after a plan or a step.  No render is
               made for the page.
  the console  console_ui.page_snapshot and console_ui.page_art, read under
               the console's own lock.
  the boxels   the robot's belief as the registry holds it and nothing
               else: never a body of the simulation, never a pose the robot
               has not registered.  The page follows one registry
               (Page.follow_boxels, once it is built) and keeps plain
               copies of its boxels: one boxel again when its id is told
               (Page.boxel_changed, boxel_data's watcher), the whole of it
               when a render is handed over (Page.look_at_boxels).  A
               number goes up only when a copy really changed, and the page
               fetches the boxels only then.

The server listens on 127.0.0.1 only, answers GET only and serves no file
of the disk: the page (/), the console's looks (/art), the state (/state),
the three pictures (/cam/rgb.png, /cam/depth.png, /cam/mask.png) and the
boxels (/boxels).  It never opens a browser; the launcher (run.ps1) does,
on the Windows side.

  SB_GUI_PAGE_PORT    the port (default 8765; busy: one of the nine after
                      it; 0: any free port)
  SB_GUI_PAGE_TOKEN   a word the launcher sets and reads back from /state,
                      so that it opens the page of its own run
"""
import atexit
import json
import os
import sys
import threading
import time

DEFAULT_PORT = 8765
PORT_TRIES = 10            # the port and the nine after it
POLL_MS = 250              # the page asks for the state this often
LINGER_S = 1.0             # at the run's end, for the page to fetch the last lines
PICTURES = ('rgb', 'depth', 'mask')
# The world as boxels: how much of a free-space boxel's colour its faces get
# (0: none, 1: solid).  The one number for it; its edges are drawn from it
# too.  Free boxels are most of the boxels and lie behind each other, where
# their faces add up, so this stays small (Hani, 2026-11-25: "the free
# boxles are mostly very trasnparent").
FREE_OPACITY = 0.03
# The page is for a browser on this machine: a request that names another
# host (a page of another site resolving its own name to 127.0.0.1) is refused.
_HOSTS = ('localhost', '127.0.0.1', '[::1]')

# Mask colours by body id, the table of tampura_bridge/camera_overlay.py (the
# same body has the same colour in both windows; pinned by tests/test_gui_page.py);
# the background (-1) is black.
MASK_COLOURS = (
    (230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200),
    (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
    (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
    (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195),
    (128, 128, 0), (255, 215, 180), (0, 0, 128), (169, 169, 169))

_page = None               # the started Page; None means no page (the default)
last_error = None          # why start() gave None


def active():
    """The started page, or None (boxel_env asks when a window opens)."""
    return _page


def start(console=None, port=None, token=None):
    """Start the page's server (once; a second call returns the first page).
    `console` is console_ui or anything with its page_snapshot and page_art;
    None gives a page without the console's part.  None when no port of the
    range is free: the caller says so and the run keeps PyBullet's window as
    it is."""
    global _page, last_error
    if _page is not None:
        return _page
    if port is None:
        try:
            port = int(os.environ.get('SB_GUI_PAGE_PORT', DEFAULT_PORT))
        except ValueError:
            port = DEFAULT_PORT
    if token is None:
        token = os.environ.get('SB_GUI_PAGE_TOKEN', '')
    for candidate in ([0] if port == 0 else range(port, port + PORT_TRIES)):
        try:
            page = Page(console, candidate, token)
        except OSError as e:
            last_error = e
            continue
        page.serve()
        atexit.register(page.linger)
        _page = page
        return page
    return None


def stop():
    """End the server (tests; a run's page ends with its process)."""
    global _page
    page, _page = _page, None
    if page is not None:
        atexit.unregister(page.linger)
        page.close()


# ---------------------------------------------------------------------------
# the console's colours as CSS
# ---------------------------------------------------------------------------

_ANSI_16 = ((0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16),
            (36, 114, 200), (188, 63, 188), (17, 168, 205), (229, 229, 229),
            (102, 102, 102), (241, 76, 76), (35, 209, 139), (245, 245, 67),
            (59, 142, 234), (214, 112, 214), (41, 184, 219), (255, 255, 255))


def _xterm_rgb(n):
    """An xterm 256-colour index as (r, g, b)."""
    n = int(n)
    if n < 16:
        return _ANSI_16[n]
    if n >= 232:
        v = 8 + 10 * (n - 232)
        return (v, v, v)
    n -= 16
    levels = (0, 95, 135, 175, 215, 255)
    return (levels[n // 36], levels[(n // 6) % 6], levels[n % 6])


def _css_of(code):
    """An SGR code ('1;38;5;80', '2', '36') as CSS declarations."""
    out = []
    bits = str(code or '').split(';')
    i = 0
    while i < len(bits):
        b = bits[i]
        if b == '1':
            out.append('font-weight:700')
        elif b == '2':
            out.append('opacity:.62')
        elif b == '38' and bits[i + 1:i + 2] == ['5'] and i + 2 < len(bits):
            out.append('color:#%02x%02x%02x' % _xterm_rgb(bits[i + 2]))
            i += 2
        elif b.isdigit() and (30 <= int(b) <= 37 or 90 <= int(b) <= 97):
            n = int(b)
            out.append('color:#%02x%02x%02x' % _xterm_rgb(n - 30 if n < 90 else n - 82))
        i += 1
    return ';'.join(out)


def _art_for_the_page(looks):
    """console_ui.page_art()'s data with the SGR codes turned into one
    style sheet: `.s-<style>` for the console's styles and `.a-<code point>`
    for a sprite's colour key (keys differ by case only, k and K)."""
    looks = dict(looks or {})
    css = []
    for name, code in sorted((looks.pop('codes', None) or {}).items()):
        rule = _css_of(code)
        if rule:
            css.append('.s-%s{%s}' % (name, rule))
    for key, code in sorted((looks.pop('palette', None) or {}).items()):
        rule = _css_of(code)
        if rule and len(key) == 1:
            css.append('.a-%d{%s}' % (ord(key), rule))
    looks['css'] = '\n'.join(css)
    return looks


# ---------------------------------------------------------------------------
# the pictures
# ---------------------------------------------------------------------------

def _metres(buf, near, far):
    return far * near / (far - (far - near) * buf)


def _depth_span(buf, near, far):
    """[nearest, farthest] seen surface in metres, or None for an empty view."""
    seen = buf < 0.9999
    if not seen.any():
        return None
    z = _metres(buf[seen], near, far)
    return [round(float(z.min()), 3), round(float(z.max()), 3)]


def _depth_picture(buf, near, far):
    """Grey picture of the depth, near bright, scaled to this render's own
    nearest and farthest surface (as camera_overlay.py draws it)."""
    import numpy as np
    seen = buf < 0.9999
    if not seen.any():
        return np.zeros(buf.shape + (3,), dtype=np.uint8)
    z = _metres(buf, near, far)
    lo, hi = float(z[seen].min()), float(z[seen].max())
    t = np.clip((z - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    grey = np.where(seen, 255.0 * (1.0 - t), 0.0).astype(np.uint8)
    return np.repeat(grey[:, :, None], 3, axis=2)


def _mask_picture(seg):
    import numpy as np
    table = np.array(MASK_COLOURS, dtype=np.uint8)
    out = table[np.mod(seg, len(table))]
    out[seg < 0] = 0
    return out


def _png(picture):
    import io
    from PIL import Image
    data = io.BytesIO()
    Image.fromarray(picture).save(data, format='PNG', compress_level=1)
    return data.getvalue()


# ---------------------------------------------------------------------------
# the page's server
# ---------------------------------------------------------------------------

class Page:
    def __init__(self, console, port, token=''):
        self._console = console
        self.token = str(token or '')
        self.started = time.time()
        self._lock = threading.Lock()
        self._cam = None           # the latest render handed over
        self._renders = 0
        self._png = {}             # (render number, picture name) -> PNG bytes
        self._registry = None      # the registry whose boxels the page shows
        self._describe = None      # one boxel as plain values (page_boxels.boxel_for_page)
        self._boxels = {}          # boxel id -> those values, as last handed over
        self._boxel_version = 0    # goes up only when _boxels really changed
        self._boxel_wall = 0.0     # when it last did
        self._ground = None        # the table's top and the robot's base
        self._boxel_json = (-1, b'')   # (version, the answer to /boxels made for it)
        self._served = (0.0, -1)   # (monotonic time, console line number) of the last /state
        self._httpd = _server_class()(('127.0.0.1', int(port)), _handler_class())
        self._httpd.daemon_threads = True
        self._httpd.page = self
        self.port = self._httpd.server_address[1]
        self.url = 'http://localhost:%d/' % self.port
        self.title = 'Semantic Boxels (page %d)' % self.port
        self._thread = None

    def serve(self):
        self._thread = threading.Thread(target=self._httpd.serve_forever, name='gui-page',
                                        kwargs={'poll_interval': 0.2}, daemon=True)
        self._thread.start()

    def close(self):
        # A page that is gone follows no registry, and takes its watcher
        # with it (boxel_data is asked for by name only, as run_logger below).
        self._registry = None
        try:
            bd = sys.modules.get('world.boxel_data')
            if bd is not None and getattr(bd, '_watcher', None) == self.boxel_changed:
                bd.watch(None)
        except Exception:
            pass
        try:
            if self._thread is not None:
                self._httpd.shutdown()
                self._thread.join(timeout=2.0)
            self._httpd.server_close()
        except Exception:
            pass

    # ----- handed over by the run's main thread ------------------------------

    def offer_render(self, width, height, rgb, depth, seg, near, far, kind):
        """The latest render of the robot's camera, for the page's three
        pictures: getCameraImage's pixel arrays as they came (rgb with its
        alpha, the raw depth buffer, the body ids) and the camera's near and
        far planes.  `kind` says what the render was: 'observation' (the
        robot's own detection render) or 'display' (the render a window run
        makes for show after a plan or a step).  Copies are kept, the
        caller's arrays are not touched, and a failure here never reaches
        the run: the page keeps its last pictures.

        The same moments (after a plan, after a step, every observation) are
        when the page looks at the registry it follows once more
        (look_at_boxels): nothing when it follows none."""
        self.look_at_boxels()
        try:
            import numpy as np
            w, h = int(width), int(height)
            cam = {
                'rgb': np.array(rgb, dtype=np.uint8).reshape(h, w, -1)[:, :, :3],
                'depth': np.array(depth, dtype=np.float32).reshape(h, w),
                'seg': np.array(seg, dtype=np.int32).reshape(h, w),
                'near': float(near), 'far': float(far),
                'kind': str(kind), 'size': [w, h],
                'clock': time.strftime('%H:%M:%S'), 'wall': time.time(),
                'plan': None, 'step': None, 'action': None,
            }
            # the step this render belongs to, when a step is open (read only)
            rl = sys.modules.get('console.run_logger')
            d = rl.current_dispatch() if rl is not None else None
            if d:
                cam['plan'], cam['step'] = d.get('plan'), d.get('step')
                cam['action'] = None if d.get('action') is None else str(d.get('action'))
            with self._lock:
                self._renders += 1
                cam['version'] = self._renders
                self._cam = cam
                self._png = {}
        except Exception:
            pass

    def follow_boxels(self, registry, describe, ground=None):
        """The world as boxels: from now on the page shows the boxels of
        this registry (anything with a dict `boxels`, id -> boxel), as it
        stands now and as it changes.  `describe(boxel)` gives one boxel as
        plain values, (id, kind, min corner, max corner, label, colour,
        occluder, region kind), the corners in tenths of a millimetre:
        page_boxels.boxel_for_page, with the overlay's own label and
        colour.  `ground` is the table's top and the robot's base as
        numbers (page_boxels.ground_for_page), or None.
        The registry is read on the caller's thread only, here and in the
        two methods below; the page keeps copies, never a boxel.  A failure
        here never reaches the run.  The registry's boxels are read first and
        handed over with it in one step, so that the page never gets an empty
        set between the two (review r5, G)."""
        try:
            rows = self._rows_of(registry, describe)
            with self._lock:
                self._registry, self._describe = registry, describe
                self._ground = None if ground is None else json.loads(json.dumps(ground))
                self._boxels = rows
                self._boxel_version += 1
                self._boxel_wall = time.time()
        except Exception:
            pass

    @staticmethod
    def _rows_of(registry, describe):
        """Every boxel of the registry as a row; a boxel that cannot be read
        is not shown."""
        rows = {}
        for boxel_id, boxel in list(registry.boxels.items()):
            try:
                rows[boxel_id] = describe(boxel)
            except Exception:
                pass
        return rows

    def boxel_changed(self, boxel_id):
        """The boxel of this id may have changed: added, taken out, moved,
        another colour or label (boxel_data's watcher; told by the
        registry's own methods and by the overlay's redraws).  It is read
        again from the followed registry, whichever registry the word came
        from, and only a real difference counts.  One small copy; never
        raises."""
        try:
            registry = self._registry
            if registry is None:
                return
            boxel = registry.boxels.get(boxel_id)
            try:
                row = None if boxel is None else self._describe(boxel)
            except Exception:
                row = None              # not shown, as in look_at_boxels (review r5, H)
            with self._lock:
                if row == self._boxels.get(boxel_id):
                    return
                if row is None:
                    del self._boxels[boxel_id]
                else:
                    self._boxels[boxel_id] = row
                self._boxel_version += 1
                self._boxel_wall = time.time()
        except Exception:
            pass

    def look_at_boxels(self):
        """The followed registry read whole and compared with the copies:
        for the changes nobody tells (a boxel written in place in a run
        without the overlay, an entry taken out of the dict directly).
        offer_render calls it, so it runs where the env hands a render
        over: after a plan, after a step and at every observation.  One
        copy for each boxel, beside a render.  Never raises."""
        try:
            registry = self._registry
            if registry is None:
                return
            rows = self._rows_of(registry, self._describe)
            with self._lock:
                if rows == self._boxels:
                    return
                self._boxels = rows
                self._boxel_version += 1
                self._boxel_wall = time.time()
        except Exception:
            pass

    # ----- asked by the server's threads ----------------------------------------

    def html(self):
        return (_HTML.replace('__TITLE__', self.title)
                .replace('__POLL_MS__', str(POLL_MS))
                .replace('__FREE_OPACITY__', repr(float(FREE_OPACITY))))

    def art(self):
        looks = None
        if self._console is not None:
            try:
                looks = self._console.page_art()
            except Exception:
                looks = None
        return _art_for_the_page(looks)

    def state(self, after=0):
        snap = None
        if self._console is not None:
            try:
                snap = self._console.page_snapshot(after)
            except Exception:
                snap = None
        with self._lock:
            cam = self._cam
        meta = None
        if cam is not None:
            if 'depth_m' not in cam:
                cam['depth_m'] = _depth_span(cam['depth'], cam['near'], cam['far'])
            meta = {k: cam[k] for k in ('version', 'kind', 'size', 'clock', 'plan',
                                        'step', 'action', 'depth_m')}
            meta['age_s'] = round(time.time() - cam['wall'], 1)
        if snap is not None:
            self._served = (time.monotonic(), int(snap.get('seq', 0)))
        with self._lock:
            followed = self._registry is not None
            version, count, wall = self._boxel_version, len(self._boxels), self._boxel_wall
        # the boxels themselves are at /boxels; the page fetches them when this number differs
        boxels = None if not followed else {
            'version': version, 'count': count,
            'clock': time.strftime('%H:%M:%S', time.localtime(wall)),
            'age_s': round(time.time() - wall, 1)}
        return {'run': {'token': self.token, 'pid': os.getpid(), 'started': self.started,
                        'now': time.time(), 'port': self.port},
                'console': snap, 'camera': meta, 'boxels': boxels}

    def boxels(self):
        """The answer to /boxels as bytes: the copies as they stand, with
        their version, the clock of the last change and the ground.  Made
        once for a version."""
        with self._lock:
            version, wall, ground = self._boxel_version, self._boxel_wall, self._ground
            rows = list(self._boxels.values())
            made, data = self._boxel_json
        if made == version:
            return data
        data = json.dumps({
            'version': version,
            'clock': time.strftime('%H:%M:%S', time.localtime(wall)) if wall else None,
            'ground': ground,
            # the corners were handed over in tenths of a millimetre: the page gets metres
            'boxels': [{'id': r[0], 'kind': r[1], 'min': [v / 1e4 for v in r[2]],
                        'max': [v / 1e4 for v in r[3]], 'name': r[4], 'colour': r[5],
                        'occluder': r[6], 'region': r[7]} for r in rows],
        }).encode('utf-8')
        with self._lock:
            if self._boxel_version == version:
                self._boxel_json = (version, data)
        return data

    def picture(self, name):
        """One of the three pictures of the latest render as PNG bytes, made
        when first asked for; None before the first render."""
        with self._lock:
            cam = self._cam
            data = None if cam is None else self._png.get((cam['version'], name))
        if cam is None or data is not None:
            return data
        if name == 'rgb':
            picture = cam['rgb']
        elif name == 'depth':
            picture = _depth_picture(cam['depth'], cam['near'], cam['far'])
        else:
            picture = _mask_picture(cam['seg'])
        data = _png(picture)
        with self._lock:
            if self._cam is cam:
                self._png[(cam['version'], name)] = data
        return data

    def linger(self):
        """At the process's end (an exit handler; console_ui.finish runs them
        before os._exit): the page asks four times a second, so the run's last
        lines, the verdict among them, would often miss it.  Waits until a
        /state has carried them, LINGER_S at most, and not at all when no
        page has asked in the last two seconds."""
        try:
            snap = self._console.page_snapshot(1 << 62) if self._console is not None else None
            if not snap:
                return
            last = int(snap.get('seq', 0))
            end = time.monotonic() + LINGER_S
            while time.monotonic() < end:
                at, served = self._served
                if time.monotonic() - at > 2.0:
                    return
                if served >= last:
                    time.sleep(0.15)      # the answer is on its way to the page
                    return
                time.sleep(0.05)
        except Exception:
            pass


_server = None
_handler = None


def _server_class():
    """The server, built when the first page starts (as the handler below).
    A browser drops its connection wherever it stands (a closed window, a
    page loaded again); the standard server prints a traceback on stderr for
    each such request.  This one says nothing: the run's stderr is the
    console's, and nothing of the page reaches the run's output."""
    global _server
    if _server is not None:
        return _server
    from http.server import ThreadingHTTPServer

    class Server(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass

    _server = Server
    return Server


def _handler_class():
    """The request handler, built when the first page starts: http.server is
    not imported with this module (boxel_env imports this module in every
    run, headless ones too)."""
    global _handler
    if _handler is not None:
        return _handler
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'SemanticBoxelsPage'
        sys_version = ''

        def log_message(self, *args):       # nothing on stderr (the console tees it)
            pass

        def _send(self, status, body=b'', ctype='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                host = (self.headers.get('Host') or '').rsplit(':', 1)[0].lower()
                if host not in _HOSTS:
                    return self._send(403, b'this page is for a browser on this machine\n')
                page = self.server.page
                path, _, query = self.path.partition('?')
                if path == '/':
                    return self._send(200, page.html().encode('utf-8'), 'text/html; charset=utf-8')
                if path == '/art':
                    return self._send(200, json.dumps(page.art()).encode('utf-8'),
                                      'application/json')
                if path == '/state':
                    after = 0
                    for pair in query.split('&'):
                        if pair.startswith('after=') and pair[6:].isdigit():
                            after = int(pair[6:])
                    return self._send(200, json.dumps(page.state(after)).encode('utf-8'),
                                      'application/json')
                if path == '/boxels':
                    return self._send(200, page.boxels(), 'application/json')
                if path.startswith('/cam/') and path.endswith('.png') and path[5:-4] in PICTURES:
                    data = page.picture(path[5:-4])
                    if data is None:
                        return self._send(404, b'no picture yet\n')
                    return self._send(200, data, 'image/png')
                return self._send(404, b'not here\n')
            except (BrokenPipeError, ConnectionError):
                pass
            except Exception as e:
                try:
                    self._send(500, ('%s: %s\n' % (type(e).__name__, e)).encode('utf-8'))
                except Exception:
                    pass

    _handler = Handler
    return Handler


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------

_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="icon" href="data:,">
<style>
:root { --bg:#161822; --line:#2a2e42; --text:#e6e8ef; --dim:#9aa0b4; --brand:#5fd7d7; --well:#0c0d14;
        color-scheme: dark; }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body { background: var(--bg); color: var(--text); font: 14px/1.4 "Segoe UI", system-ui, sans-serif;
       display: flex; flex-direction: column; overflow: hidden; }
.mono { font-family: "Cascadia Mono", "Cascadia Code", Consolas, "DejaVu Sans Mono", "Segoe UI Symbol", monospace; }
header { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--line); }
header .brand { color: var(--brand); font-weight: 700; letter-spacing: .16em; white-space: nowrap; }
header .run { color: var(--dim); font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pill { font-size: 12px; padding: 2px 10px; border-radius: 999px; background: #1f3346; color: #8fd3ff; white-space: nowrap; }
body.ended .pill { background: #3a2a2a; color: #e6a9a9; }
main { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 2fr) minmax(0, 1fr); }
#now { display: flex; gap: 20px; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--line); min-height: 158px; }
#art { flex: none; width: 12ch; font-size: 22px; line-height: 1.12; }
.arow { height: 1.12em; white-space: nowrap; }
.cell { display: inline-block; width: 1ch; text-align: center; }
#words { min-width: 0; flex: 1; }
#head { font-size: 16px; line-height: 1.35; white-space: pre-wrap; overflow-wrap: anywhere; }
#info, #status, #counts { color: var(--dim); font-size: 13px; margin-top: 4px; white-space: pre-wrap; overflow-wrap: anywhere; }
#status { min-height: 1.4em; }
#counts { margin-top: 8px; }
body.ended #art, body.idle #art { opacity: .55; }
#cams { padding: 10px 16px 12px; border-bottom: 1px solid var(--line); }
#camline { color: var(--dim); font-size: 12px; margin-bottom: 6px; }
#camline b { color: var(--text); font-weight: 600; }
.camrow { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.camrow.one { grid-template-columns: minmax(0, 1fr); }
.camrow.one figure:not(.big) { display: none; }
figure { margin: 0; }
figure .shot { width: 100%; aspect-ratio: 4 / 3; background: var(--well); border: 1px solid var(--line); border-radius: 4px;
               display: block; cursor: zoom-in; object-fit: contain; }
.camrow.one figure .shot { cursor: zoom-out; }
figcaption { color: var(--dim); font-size: 12px; margin-top: 3px; }
/* the world as boxels: a line that is its key too, the view, a line about the last change */
#boxels { display: flex; flex-direction: column; min-height: 0; padding: 8px 16px 8px; border-bottom: 1px solid var(--line); }
#boxline { color: var(--dim); font-size: 12px; margin-bottom: 5px; display: flex; flex-wrap: wrap; gap: 1px 12px; align-items: center; }
.key { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; color: var(--text); }
.key i { width: 10px; height: 10px; border-radius: 2px; border: 1px solid; display: inline-block; }
button.key { font: inherit; background: none; border: 0; padding: 0; cursor: pointer; }
button.key.off { opacity: .45; text-decoration: line-through; }
#boxwrap { position: relative; flex: 1; min-height: 0; border: 1px solid var(--line); border-radius: 4px; overflow: hidden;
           background: radial-gradient(ellipse at 50% 40%, #1b1f30 0%, var(--well) 78%); user-select: none; }
#boxview { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; }
#boxview.drag { cursor: grabbing; }
#boxtip { position: absolute; left: 8px; right: 8px; bottom: 5px; font-size: 11px; pointer-events: none; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis; text-shadow: 0 0 3px #0c0d14, 0 0 3px #0c0d14, 0 0 3px #0c0d14; }
#boxbtns { position: absolute; right: 6px; top: 5px; display: flex; gap: 4px; }
#boxbtns button { font: inherit; font-size: 11px; line-height: 1.4; color: var(--dim); background: rgba(22, 24, 34, .8);
                  border: 1px solid var(--line); border-radius: 999px; padding: 0 8px; cursor: pointer; }
#boxbtns button.on { color: var(--brand); border-color: #2f5560; }
#boxnews { color: var(--dim); font-size: 12px; margin-top: 5px; height: 2.8em; overflow: hidden;
           display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
#boxnews b { color: var(--text); font-weight: 600; }
/* the view made large: it takes the room of the pictures and of the lines */
body.bigbox #cams, body.bigbox #log { display: none; }
body.bigbox main { grid-template-rows: auto minmax(0, 1fr); }
#log { overflow: auto; padding: 10px 16px 16px; font-size: 13px; line-height: 1.45; }
.ln { white-space: pre-wrap; overflow-wrap: anywhere; min-height: 1.45em; }
#noconsole { color: var(--dim); padding: 10px 16px; display: none; }
#oops { display: none; padding: 6px 16px; background: #4a1f1f; color: #ffd0d0; font-size: 12px; white-space: pre-wrap; }
/* a wide window: the console on the left, the boxels over the camera's pictures on the right */
@media (min-width: 980px) {
  main, body.bigbox main { grid-template-columns: minmax(0, 1fr) minmax(380px, 38%); grid-template-rows: auto minmax(0, 1fr) auto; }
  #now { grid-column: 1; grid-row: 1; }
  #log, body.bigbox #log { display: block; grid-column: 1; grid-row: 2 / span 2; }
  #boxels { grid-column: 2; grid-row: 1 / span 2; border-left: 1px solid var(--line); }
  body.bigbox #boxels { grid-row: 1 / span 3; border-bottom: 0; }
  #cams { grid-column: 2; grid-row: 3; border-bottom: 0; border-left: 1px solid var(--line); }
}
/* held against the simulator's window the page is narrow and no taller than that window */
@media (max-width: 520px) {
  header { padding: 7px 10px; gap: 8px; }
  header .brand { letter-spacing: .08em; }
  #now { gap: 12px; padding: 9px 10px; min-height: 0; }
  #art { font-size: 17px; }
  #head { font-size: 14px; }
  #info, #status, #counts { font-size: 12px; }
  #cams { padding: 8px 10px 9px; }
  .camrow { gap: 6px; }
  figcaption { font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #boxels { padding: 7px 10px 7px; }
  #boxline { gap: 1px 9px; margin-bottom: 4px; }
  #boxnews { margin-top: 4px; }
  #log { padding: 8px 10px 12px; font-size: 12px; }
}
/* at its least width the head keeps the name and the whole pill */
@media (max-width: 300px) {
  header .brand { font-size: 12px; letter-spacing: 0; }
  header .run { display: none; }
  .pill { padding: 2px 7px; }
  /* and the boxels keep a view worth looking at: more of the height, one line about the last change */
  main { grid-template-rows: auto auto minmax(0, 3fr) minmax(0, 1fr); }
  #boxnews { height: 1.4em; -webkit-line-clamp: 1; }
}
</style>
<style id="art-css"></style>
</head>
<body class="idle">
<header>
  <span class="brand mono">&#9635; SEMANTIC BOXELS</span>
  <span class="run" id="run"></span>
  <span class="pill" id="pill">connecting</span>
</header>
<main>
  <section id="now">
    <div id="art" class="mono" aria-hidden="true"></div>
    <div id="words">
      <div id="head" class="mono"></div>
      <div id="info" class="mono"></div>
      <div id="status" class="mono"></div>
      <div id="counts"></div>
    </div>
  </section>
  <section id="cams">
    <div id="camline">The robot's camera: no picture yet</div>
    <div class="camrow" id="camrow">
      <figure><img class="shot" id="cam-rgb" alt=""><figcaption>colour</figcaption></figure>
      <figure><img class="shot" id="cam-depth" alt=""><figcaption id="cap-depth">depth, near is bright</figcaption></figure>
      <figure><img class="shot" id="cam-mask" alt=""><figcaption>mask, one colour for each body</figcaption></figure>
    </div>
  </section>
  <section id="boxels" aria-label="the world as boxels">
    <div id="boxline"></div>
    <div id="boxwrap">
      <canvas id="boxview"></canvas>
      <div id="boxtip" class="mono"></div>
      <div id="boxbtns">
        <button type="button" id="boxturn" class="on" title="turn slowly by itself (drag turns, the wheel zooms, a double click starts over)">turn</button>
        <button type="button" id="boxbig" title="the view large, the pictures and the lines put away">larger</button>
      </div>
    </div>
    <div id="boxnews"></div>
  </section>
  <section id="log" class="mono" aria-label="the console's lines"></section>
</main>
<div id="noconsole">The console is off in this run (it runs at --log-level smart, the default); the camera's pictures only.</div>
<div id="oops" class="mono"></div>
<script>
(() => {
'use strict';
// an error of this page's own script is shown on the page, not lost in a console nobody opens
function oops(text) {
  const box = document.getElementById('oops');
  box.style.display = 'block';
  box.textContent = 'this page stumbled: ' + text;
}
window.addEventListener('error', ev => oops(ev.message + ' (line ' + ev.lineno + ')'));
window.addEventListener('unhandledrejection', ev => oops(String(ev.reason)));
const POLL_MS = __POLL_MS__;
const BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
const $ = id => document.getElementById(id);
let art = null, after = 0, runKey = null, ended = false, endedAt = 0, sawRun = false;
let live = null, liveT0 = 0, lastHead = null, drawn = '';
let camVersion = -1, cam = null, camAt = 0;
let runElapsed = null, runElapsedAt = 0, runId = '';
// The log shows its newest line until the reader scrolls up, and again once they are back at
// its end.  Kept as a state, not measured when lines arrive: the log's box changes its height
// without a scroll (the window is resized when it is held against the simulator's, the camera
// pictures load, one is made large), and a log that was at its end must still be there after.
let following = true;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function partsInto(node, parts) {
  // (text, style) parts as spans; a node keeps what it shows until that changes
  const key = JSON.stringify(parts || []);
  if (node.dataset.parts === key) return;
  node.dataset.parts = key;
  node.textContent = '';
  for (const part of parts || []) {
    if (part && part[0]) node.appendChild(el('span', part[1] ? 's-' + part[1] : null, part[0]));
  }
}
function esc(ch) { return ch === '&' ? '&amp;' : ch === '<' ? '&lt;' : ch === '>' ? '&gt;' : ch === ' ' ? '&nbsp;' : ch; }
function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
function clock(s) {
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60);
  return (m < 10 ? '0' : '') + m + ':' + (s % 60 < 10 ? '0' : '') + (s % 60);
}

async function getJSON(url) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), 3000);
  try {
    const r = await fetch(url, {cache: 'no-store', signal: stop.signal});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } finally { clearTimeout(timer); }
}

function empty(id, text) {
  // a node emptied for good: what it remembers of its last content goes too,
  // or the same line of the next run (the same mission) would not be drawn
  const node = $(id);
  node.textContent = text || '';
  delete node.dataset.parts;
  delete node.dataset.shown;
}
function startOver() {
  after = 0; live = null; lastHead = null; drawn = ''; camVersion = -1; cam = null; art = null;
  runId = ''; runElapsed = null; following = true;
  for (const name of ['rgb', 'depth', 'mask']) $('cam-' + name).src = BLANK;
  empty('camline', "The robot's camera: no picture yet");
  empty('cap-depth', 'depth, near is bright');
  for (const id of ['log', 'art', 'head', 'info', 'status', 'counts', 'boxnews', 'boxtip']) empty(id);
  bx.version = -1; bx.meta = null; bx.boxes = new Map(); bx.ghosts = []; bx.ground = null; bx.news = null;
  bx.hover = null; bx.view = null; bx.dirty = true;
  boxKey();
}

async function poll() {
  try {
    let s = await getJSON('/state?after=' + after);
    const key = s.run.token + ':' + s.run.started;
    if (key !== runKey) {          // another run answers on this port: start over
      runKey = key;
      startOver();
      s = await getJSON('/state?after=0');
    }
    if (!art) { art = await getJSON('/art'); $('art-css').textContent = art.css || ''; }
    show(s);
    sawRun = true;
    setEnded(false);
  } catch (e) {
    setEnded(true);
  }
  setTimeout(poll, ended ? 1000 : POLL_MS);
}

function setEnded(now) {
  if (now && !ended) endedAt = performance.now();
  ended = now;
  document.body.classList.toggle('ended', now);
  if (now) $('pill').textContent = sawRun ? 'the run has ended' : 'no run answers here';
}

function show(s) {
  const c = s.console;
  $('noconsole').style.display = c ? 'none' : 'block';
  if (c) {
    runId = c.run_id || '';
    runElapsed = c.elapsed; runElapsedAt = performance.now();
    const log = $('log');
    for (const row of c.lines) {
      const line = el('div', 'ln');
      partsInto(line, row[1]);
      log.appendChild(line);
      const first = (row[1][0] && row[1][0][0]) || '';
      if (first && first[0] !== ' ' && row[1].length > 1) lastHead = row[1];
    }
    while (log.childNodes.length > 600) log.removeChild(log.firstChild);
    if (following && c.lines.length) log.scrollTop = log.scrollHeight;
    after = c.seq;
    if (c.live) {
      if (!live || live.id !== c.live.id) liveT0 = performance.now() - c.live.elapsed * 1000;
      live = c.live;
    } else {
      live = null;
    }
    const k = c.counts || {}, bits = [];
    if (k.plans) bits.push(plural(k.plans, 'plan') + (k.plans_found !== k.plans ? ', ' + k.plans_found + ' found' : ''));
    if (k.dispatched) bits.push(plural(k.dispatched, 'step') + ', ' + k.completed + ' done' + (k.failed ? ', ' + k.failed + ' failed' : ''));
    if (k.holding) bits.push('holding ' + k.holding);
    if (k.unknown != null) bits.push(k.unknown ? plural(k.unknown, 'space') + ' unchecked' : 'every space checked');
    $('counts').textContent = bits.join('  ·  ');
  }
  const m = s.camera;
  if (m && m.version !== camVersion) {
    camVersion = m.version;
    for (const name of ['rgb', 'depth', 'mask']) {
      const img = $('cam-' + name);
      img.style.aspectRatio = m.size[0] + ' / ' + m.size[1];
      img.src = '/cam/' + name + '.png?v=' + m.version;
    }
    $('cap-depth').textContent = m.depth_m
      ? 'depth, near is bright (' + m.depth_m[0].toFixed(2) + ' to ' + m.depth_m[1].toFixed(2) + ' m)'
      : 'depth, near is bright';
  }
  if (m) { cam = m; camAt = performance.now() - m.age_s * 1000; }
  // the boxels are fetched only when the run says they changed
  const b = s.boxels;
  if (b) {
    if (!bx.meta) { bx.meta = b; boxKey(); }
    bx.meta = b; bx.at = performance.now() - b.age_s * 1000;
    if (b.version !== bx.version && !bx.asking) askBoxels();
  }
}

function artHTML(rows, cls) {
  let h = '';
  for (let r = 0; r < rows.length; r++) {
    h += '<div class="arow">';
    const row = Array.from(rows[r]);
    for (let c = 0; c < row.length; c++) {
      const k = cls(r, c, row[c]);
      h += '<span class="cell' + (k ? ' ' + k : '') + '">' + esc(row[c]) + '</span>';
    }
    h += '</div>';
  }
  return h;
}

function draw() {
  // a page whose run has ended stands still at the moment it lost the run
  const now = ended ? endedAt : performance.now();
  // the top line: the run and how long it has been going
  $('run').textContent = runId;
  if (!ended && runElapsed != null) $('pill').textContent = 'running ' + clock(runElapsed + (now - runElapsedAt) / 1000);
  document.body.classList.toggle('idle', !live);
  if (!art) return;
  const tick = Math.floor(now / (art.frame_ms || 100));
  const kinds = art.kinds || {};
  const hues = (live && kinds[live.kind]) || kinds.act || ['cyan', 'dim_cyan', 'hi_cyan'];
  const sprite = live && art.sprites ? art.sprites[live.sprite] : null;
  let key, html = null;
  if (sprite && !ended) {
    const n = sprite.frames.length;
    let i = Math.floor((now - liveT0) / Math.max(1, sprite.period_ms || 200));
    if (sprite.pingpong && n > 1) { const cycle = 2 * n - 2; i %= cycle; if (i >= n) i = cycle - i; } else { i %= n; }
    key = 'sprite ' + live.id + ' ' + i;
    if (key !== drawn) {
      const glyphs = sprite.frames[i][0], mask = sprite.frames[i][1];
      html = artHTML(glyphs, (r, c, ch) => (ch === ' ' || mask[r][c] === ' ') ? '' : 'a-' + mask[r].charCodeAt(c));
    }
  } else if (art.cube) {
    const loop = art.cube_loop || [], lit = new Set();
    const moving = live && !ended;
    if (moving) for (let j = 0; j < (art.light_len || 4); j++) { const p = loop[(tick + j) % loop.length]; lit.add(p[0] + ',' + p[1]); }
    key = 'cube ' + (moving ? live.kind + ' ' + (tick % loop.length) : 'still');
    if (key !== drawn) {
      const inner = new Set((art.cube_inner || []).map(p => p[0] + ',' + p[1]));
      html = artHTML(art.cube, (r, c, ch) => ch === ' ' ? '' : 's-' + (lit.has(r + ',' + c) ? hues[2] : inner.has(r + ',' + c) ? hues[1] : hues[0]));
    }
  }
  if (html != null) { $('art').innerHTML = html; drawn = key; }
  if (live) {
    partsInto($('head'), live.head);
    partsInto($('info'), [[live.info[0] || '', null]]);
    const stars = art.stars || ['*'];
    const star = ended ? '' : stars[Math.floor(tick / 2) % stars.length] + ' ';
    const status = $('status');
    status.textContent = '';
    if (star) status.appendChild(el('span', 's-' + hues[2], star));
    status.appendChild(document.createTextNode(((now - liveT0) / 1000).toFixed(1) + ' s' + (live.info[1] ? '   ' + live.info[1] : '')));
  } else {
    partsInto($('head'), lastHead || []);
    $('info').textContent = ''; $('status').textContent = '';
  }
  if (cam) {
    const line = $('camline');
    const age = Math.max(0, Math.round((now - camAt) / 1000));
    const what = cam.kind === 'observation' ? 'what the robot saw' : 'the scene';
    const at = cam.plan != null ? ', plan ' + cam.plan + ' step ' + cam.step + (cam.action ? ' (' + cam.action + ')' : '') : '';
    const text = ' at ' + cam.clock + (ended ? ', the last picture' : ' (' + age + ' s ago)') + at;
    if (line.dataset.shown !== what + text) {
      line.dataset.shown = what + text;
      line.textContent = '';
      line.appendChild(document.createTextNode("The robot's camera: "));
      line.appendChild(el('b', null, what));
      line.appendChild(document.createTextNode(text));
    }
  }
  if (bx.news) {
    const line = $('boxnews');
    const age = Math.max(0, Math.round((now - bx.at) / 1000));
    const lead = (bx.news.first ? 'first seen at ' : 'changed at ') + bx.news.clock
      + (ended ? ', the last change' : ' (' + age + ' s ago)') + ': ';
    if (line.dataset.shown !== lead + bx.news.text) {
      line.dataset.shown = lead + bx.news.text;
      line.title = lead + bx.news.text;
      line.textContent = '';
      line.appendChild(document.createTextNode(lead));
      line.appendChild(el('b', null, bx.news.text));
    }
  }
}

// ----- the world as boxels ---------------------------------------------------------------------
// The registry's boxels as the run hands them over (/boxels), drawn on a canvas with a projection
// of this page's own: nothing is loaded for it.  Boxes that let the light through must be drawn
// from the far ones to the near ones, so their order is worked out for every view (boxOrder).
const FREE_OPACITY = __FREE_OPACITY__;   // gui_page.FREE_OPACITY: how much of a free boxel's colour its faces get
// ?slow=N in the address makes a change N times slower (for a picture of one; no run uses it)
const SLOW = Math.max(1, Number(new URLSearchParams(location.search).get('slow')) || 1);
const MOVE_MS = 700 * SLOW, FIRST_MS = 450, TURN = 2 * Math.PI / 120000;   // one turn in two minutes
const FAR = 4.5, VIEW = {yaw: -1.0, pitch: 0.5, zoom: 1}, MANY = 400;
const bx = {version: -1, asking: false, meta: null, at: 0, boxes: new Map(), ghosts: [], ground: null, news: null,
            yaw: VIEW.yaw, pitch: VIEW.pitch, zoom: VIEW.zoom, turning: true, chosen: false, free: true, drag: null, mouse: null,
            hover: null, view: null, dirty: true, last: 0, cost: 0, drawn: [], order: null, orderKey: ''};
// ?big in the address opens the page with the view large, ?nofree with the free space switched
// off (for a picture of either; the button and the key do the same)
if (new URLSearchParams(location.search).has('big')) document.body.classList.add('bigbox');
if (new URLSearchParams(location.search).has('nofree')) bx.free = false;

function css(c, a) { return 'rgba(' + Math.round(c[0] * 255) + ',' + Math.round(c[1] * 255) + ',' + Math.round(c[2] * 255) + ',' + a + ')'; }
function towards(c, v, t) { return [c[0] + (v - c[0]) * t, c[1] + (v - c[1]) * t, c[2] + (v - c[2]) * t]; }
function mix3(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
function sameBox(a, b) { for (let k = 0; k < 3; k++) if (a[k] !== b[k]) return false; return true; }
function whatIs(b) {
  if (b.kind === 'object') return b.occluder ? 'occluder' : 'object';
  if (b.kind === 'shadow') return b.region === 'interior' ? 'under a cover' : 'shadow';
  return b.kind === 'free_space' ? 'free space' : b.kind;
}

async function askBoxels() {
  const run = runKey;
  bx.asking = true;
  try {
    const d = await getJSON('/boxels');
    if (run === runKey) takeBoxels(d);
  } catch (e) { /* the next state asks again */ }
  bx.asking = false;
}

// where a box stands right now: a new one grows in, a gone one shrinks out, a moved one slides
function shownBox(b, t) {
  let lo = b.min, hi = b.max, a = 1, glow = 0;
  if (b.how) {
    const u = Math.min(1, Math.max(0, (t - b.t0) / (b.how === 'first' ? FIRST_MS : MOVE_MS)));
    const e = u * u * (3 - 2 * u);
    const about = (f) => { const c = mix3(b.min, b.max, 0.5); lo = mix3(c, b.min, f); hi = mix3(c, b.max, f); };
    if (b.how === 'first') a = e;
    else if (b.how === 'came') { a = e; about(0.45 + 0.55 * e); glow = 1 - u; }
    else if (b.how === 'moved') { lo = mix3(b.from[0], b.min, e); hi = mix3(b.from[1], b.max, e); glow = 1 - u; }
    else if (b.how === 'gone') { a = 1 - e; about(1 - 0.4 * e); glow = 0.7 * (1 - u); }
    else if (b.how === 'changed') glow = 1 - u;
    if (u >= 1) b.over = true;
  }
  return {b, lo, hi, a, glow};
}

function takeBoxels(d) {
  const t = performance.now(), first = bx.version < 0;
  const next = new Map(), came = [], went = [], moved = [], changed = [];
  for (const row of d.boxels) {
    const was = bx.boxes.get(row.id);
    const b = {id: row.id, kind: row.kind, name: row.name || row.id, min: row.min, max: row.max, colour: row.colour,
               occluder: row.occluder, region: row.region, how: '', t0: t, from: null, over: false};
    if (!was) { b.how = 'came'; came.push(b); }
    else if (!sameBox(was.min, b.min) || !sameBox(was.max, b.max)) {
      const now = shownBox(was, t);
      b.how = 'moved'; b.from = [now.lo, now.hi]; moved.push(b);
    } else if (was.kind !== b.kind || was.name !== b.name || was.occluder !== b.occluder || was.region !== b.region
               || !sameBox(was.colour, b.colour)) {
      b.how = 'changed'; changed.push(b);
    } else if (was.how && !was.over) { b.how = was.how; b.t0 = was.t0; b.from = was.from; }
    next.set(b.id, b);
  }
  for (const [id, was] of bx.boxes) {
    if (!next.has(id)) { went.push(was); bx.ghosts.push(Object.assign({}, was, {how: 'gone', t0: t, over: false})); }
  }
  // the boxels with a name of their own are told by it, the free ones are counted at the end
  const told = (list, word) => {
    const named = [...new Set(list.filter(b => b.kind !== 'free_space').map(b => b.name))];
    const bits = named.slice(0, 2);
    if (named.length > 2) bits.push((named.length - 2) + ' more');
    return bits.length ? word + ' ' + bits.join(', ') : '';
  };
  const freeOf = (list) => list.filter(b => b.kind === 'free_space').length;
  if (first) {
    for (const b of next.values()) b.how = 'first';
    bx.ghosts = [];
    bx.news = {first: true, clock: d.clock || '', text: plural(next.size, 'boxel')};
  } else {
    const free = [[freeOf(came), 'new'], [freeOf(went), 'gone'], [freeOf(moved) + freeOf(changed), 'changed']]
      .filter(p => p[0]).map(p => p[0] + ' ' + p[1]).join(', ');
    const text = [told(went, 'gone:'), told(came, 'new:'), told(moved, 'moved:'), told(changed, 'changed:'),
                  free ? 'free space: ' + free : ''].filter(Boolean).join('  ·  ');
    if (text) bx.news = {first: false, clock: d.clock || '', text: text};
  }
  bx.boxes = next; bx.ground = d.ground || null; bx.version = d.version; bx.dirty = true;
  // with very many boxes the view stands still until the reader turns it (a turn by itself would cost too much)
  if (!bx.chosen) { bx.turning = next.size <= MANY; $('boxturn').classList.toggle('on', bx.turning); }
  boxKey();
}

// the line over the view: what the boxels are, how many of each, in their colours (the overlay's)
function boxKey() {
  const line = $('boxline');
  line.textContent = '';
  line.appendChild(el('span', null, 'The world as boxels:'));
  const groups = new Map();
  for (const b of bx.boxes.values()) {
    const what = whatIs(b);
    const g = groups.get(what) || {what: what, n: 0, colour: b.colour, free: b.kind === 'free_space'};
    g.n += 1;
    groups.set(what, g);
  }
  if (!groups.size) { line.appendChild(el('span', null, bx.meta ? 'none' : 'none yet')); return; }
  const rank = g => ({occluder: 0, object: 1, shadow: 2, 'under a cover': 3})[g.what] ?? (g.free ? 9 : 5);
  for (const g of [...groups.values()].sort((p, q) => rank(p) - rank(q))) {
    const key = el(g.free ? 'button' : 'span', 'key' + (g.free && !bx.free ? ' off' : ''));
    const dot = el('i');
    dot.style.background = css(g.colour, g.free ? 0.3 : 0.9);
    dot.style.borderColor = css(towards(g.colour, 1, 0.3), 1);
    key.appendChild(dot);
    const word = g.free ? 'free' : g.what === 'occluder' || g.what === 'object' || g.what === 'shadow' ? g.what + (g.n === 1 ? '' : 's') : g.what;
    key.appendChild(document.createTextNode(g.n + ' ' + word));
    if (g.free) { key.type = 'button'; key.id = 'freekey'; key.title = 'show or hide the free space'; }
    line.appendChild(key);
  }
}

// The order of two boxes, by their numbers in L and H (the low and the high corners, three numbers a
// box).  -1: i is drawn before j (j may cover it), 1: j before i, 0: neither can cover the other.
function drawnBefore(L, H, i, j, e) {
  // Two boxes apart along an axis have a plane between them, and the one on the eye's side of it
  // cannot be covered by the other.  Apart along two axes that say the opposite, neither covers
  // the other, and no order is asked for (asking for one could close a ring that is not there).
  const GAP = 1e-6, a = 3 * i, b = 3 * j;
  let apart = false, said = 0;
  for (let k = 0; k < 3; k++) {
    const al = L[a + k], ah = H[a + k], bl = L[b + k], bh = H[b + k], ek = e[k];
    let r = 0;
    if (ah <= bl + GAP) { apart = true; r = ek >= bl ? -1 : ek <= ah ? 1 : 0; }
    else if (bh <= al + GAP) { apart = true; r = ek >= al ? 1 : ek <= bh ? -1 : 0; }
    if (r) { if (said && said !== r) return 0; said = r; }
  }
  if (apart) return said;
  // they share space: one inside the other goes first (the outer one's faces lie over it) ...
  let aIn = true, bIn = true;
  for (let k = 0; k < 3; k++) {
    if (L[a + k] < L[b + k] - GAP || H[a + k] > H[b + k] + GAP) aIn = false;
    if (L[b + k] < L[a + k] - GAP || H[b + k] > H[a + k] + GAP) bIn = false;
  }
  if (aIn !== bIn) return aIn ? -1 : 1;
  if (aIn) return 0;
  // ... else they are parted where they share the least
  let k = 0, least = Infinity;
  for (let n = 0; n < 3; n++) {
    const shared = Math.min(H[a + n], H[b + n]) - Math.max(L[a + n], L[b + n]);
    if (shared < least) { least = shared; k = n; }
  }
  const mid = (Math.max(L[a + k], L[b + k]) + Math.min(H[a + k], H[b + k])) / 2;
  const ca = L[a + k] + H[a + k], cb = L[b + k] + H[b + k];
  if (ca === cb) return 0;
  return (e[k] < mid) === (ca < cb) ? 1 : -1;
}

// The boxes from the far ones to the near ones, as the eye sees them.  Each has its corners lo and
// hi and the rectangle its picture lies in (rect: left, top, right, bottom).  Only two boxes whose
// pictures can meet are held against each other: for the others the order makes no difference.
function boxOrder(items, eye) {
  const n = items.length, far = new Float64Array(n), L = new Float64Array(3 * n), H = new Float64Array(3 * n);
  const R = new Float64Array(4 * n);
  for (let i = 0; i < n; i++) {
    let d = 0;
    for (let k = 0; k < 3; k++) {
      const lo = items[i].lo[k], hi = items[i].hi[k], v = (lo + hi) / 2 - eye[k];
      L[3 * i + k] = lo; H[3 * i + k] = hi; d += v * v;
    }
    far[i] = d;
    for (let k = 0; k < 4; k++) R[4 * i + k] = items[i].rect[k];
  }
  if (n > MANY) {      // too many to hold pair against pair: the farthest first
    return Array.from(items.keys()).sort((p, q) => far[q] - far[p]).map(i => items[i]);
  }
  const after = [], waits = new Int32Array(n), done = new Uint8Array(n), out = [];
  for (let i = 0; i < n; i++) after.push([]);
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (R[4 * i] > R[4 * j + 2] || R[4 * j] > R[4 * i + 2] || R[4 * i + 1] > R[4 * j + 3] || R[4 * j + 1] > R[4 * i + 3]) continue;
      const r = drawnBefore(L, H, i, j, eye);
      if (r < 0) { after[i].push(j); waits[j] += 1; } else if (r > 0) { after[j].push(i); waits[i] += 1; }
    }
  }
  const ready = [];
  for (let i = 0; i < n; i++) if (!waits[i]) ready.push(i);
  while (out.length < n) {
    if (!ready.length) {       // a ring of boxes, each before the next: opened at the farthest
      let best = -1;
      for (let i = 0; i < n; i++) if (!done[i] && (best < 0 || far[i] > far[best])) best = i;
      ready.push(best);
    }
    let at = 0;                // of those that may be drawn now, the farthest
    for (let q = 1; q < ready.length; q++) if (far[ready[q]] > far[ready[at]]) at = q;
    const i = ready[at];
    ready[at] = ready[ready.length - 1]; ready.pop();
    if (done[i]) continue;
    done[i] = 1;
    out.push(items[i]);
    for (const j of after[i]) { waits[j] -= 1; if (!waits[j] && !done[j]) ready.push(j); }
  }
  return out;
}
function boxBounds() {
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  const take = (a, b) => { for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], a[k]); hi[k] = Math.max(hi[k], b[k]); } };
  const gr = bx.ground;
  if (gr) take([gr.x[0], gr.y[0], gr.z], [gr.x[1], gr.y[1], gr.z]);
  for (const b of bx.boxes.values()) take(b.min, b.max);
  if (lo[0] === Infinity) return [[-0.5, -0.5, 0], [0.5, 0.5, 0.4]];
  return [lo, hi];
}

const FACES = [[[0, 2, 6, 4], 0, 0], [[1, 3, 7, 5], 0, 1], [[0, 1, 5, 4], 1, 0], [[2, 3, 7, 6], 1, 1], [[0, 1, 3, 2], 2, 0], [[4, 5, 7, 6], 2, 1]];
const EDGES = [[0, 1, 0], [2, 3, 0], [4, 5, 0], [6, 7, 0], [0, 2, 1], [1, 3, 1], [4, 6, 1], [5, 7, 1], [0, 4, 2], [1, 5, 2], [2, 6, 2], [3, 7, 2]];

function drawBoxels(t) {
  const wrap = $('boxwrap'), cv = $('boxview');
  const w = wrap.clientWidth, h = wrap.clientHeight, dpr = window.devicePixelRatio || 1;
  if (w < 24 || h < 24) return;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
  const g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  g.lineJoin = 'round';
  let moving = false;

  // what is in view: it follows the boxels' bounds softly, so a new set does not make the picture jump
  const [tlo, thi] = boxBounds();
  if (!bx.view) bx.view = {lo: tlo, hi: thi};
  else {
    const f = 1 - Math.exp(-(t - bx.last) / 180);
    let off = 0;
    for (let k = 0; k < 3; k++) off += Math.abs(bx.view.lo[k] - tlo[k]) + Math.abs(bx.view.hi[k] - thi[k]);
    if (off > 1e-4) { bx.view = {lo: mix3(bx.view.lo, tlo, f), hi: mix3(bx.view.hi, thi, f)}; moving = true; }
    else bx.view = {lo: tlo, hi: thi};
  }
  const lo = bx.view.lo, hi = bx.view.hi, c = mix3(lo, hi, 0.5);
  const r = Math.max(0.2, Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2), dist = r * FAR;
  const cp = Math.cos(bx.pitch), sp = Math.sin(bx.pitch);
  // The scale at which the bounds fit from every side at this height of the eye, and where their
  // picture's middle lies: one scale for the whole turn, so the picture does not pump while it turns.
  let mx = 1e-6, ylo = Infinity, yhi = -Infinity;
  for (let i = 0; i < 24; i++) {
    const a = i * Math.PI / 12, ca = Math.cos(a), sa = Math.sin(a);
    for (let j = 0; j < 8; j++) {
      const dx = (j & 1 ? hi[0] : lo[0]) - c[0] - dist * cp * ca, dy = (j & 2 ? hi[1] : lo[1]) - c[1] - dist * cp * sa,
            dz = (j & 4 ? hi[2] : lo[2]) - c[2] - dist * sp;
      const zc = -(dx * cp * ca + dy * cp * sa + dz * sp), up = (-dx * sp * ca - dy * sp * sa + dz * cp) / zc;
      mx = Math.max(mx, Math.abs((-dx * sa + dy * ca) / zc));
      ylo = Math.min(ylo, up); yhi = Math.max(yhi, up);
    }
  }
  // room is left over the boxes for their names
  const scale = Math.min((w / 2 - 8) / mx, (h - 30) / Math.max(1e-6, yhi - ylo)) * bx.zoom;
  const midX = w / 2, midY = h / 2 + 5 + scale * (ylo + yhi) / 2;
  const cy = Math.cos(bx.yaw), sy = Math.sin(bx.yaw);
  const eye = [c[0] + dist * cp * cy, c[1] + dist * cp * sy, c[2] + dist * sp];
  const P = (p) => {
    const dx = p[0] - eye[0], dy = p[1] - eye[1], dz = p[2] - eye[2];
    const zc = -(dx * cp * cy + dy * cp * sy + dz * sp), s = scale / zc;
    return [midX + (-dx * sy + dy * cy) * s, midY - (-dx * sp * cy - dy * sp * sy + dz * cp) * s];
  };
  const path = (pts) => { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.closePath(); };

  // the ground: the table's top with a line every 10 cm, and where the robot stands
  const gr = bx.ground;
  if (gr) {
    const z = gr.z;
    path([P([gr.x[0], gr.y[0], z]), P([gr.x[1], gr.y[0], z]), P([gr.x[1], gr.y[1], z]), P([gr.x[0], gr.y[1], z])]);
    g.fillStyle = 'rgba(52, 58, 86, .55)'; g.fill();
    g.beginPath();
    for (let x = Math.ceil(gr.x[0] * 10 - 1e-6) / 10; x <= gr.x[1] + 1e-6; x += 0.1) { const a = P([x, gr.y[0], z]), b = P([x, gr.y[1], z]); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
    for (let y = Math.ceil(gr.y[0] * 10 - 1e-6) / 10; y <= gr.y[1] + 1e-6; y += 0.1) { const a = P([gr.x[0], y, z]), b = P([gr.x[1], y, z]); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); }
    g.strokeStyle = 'rgba(154, 160, 180, .13)'; g.lineWidth = 1; g.stroke();
    path([P([gr.x[0], gr.y[0], z]), P([gr.x[1], gr.y[0], z]), P([gr.x[1], gr.y[1], z]), P([gr.x[0], gr.y[1], z])]);
    g.strokeStyle = 'rgba(154, 160, 180, .45)'; g.stroke();
    if (gr.robot) {         // a ring at the table's height over the base, which stands on the floor
      const ring = [];
      for (let i = 0; i < 28; i++) ring.push(P([gr.robot[0] + 0.055 * Math.cos(i * Math.PI / 14), gr.robot[1] + 0.055 * Math.sin(i * Math.PI / 14), z]));
      path(ring);
      g.fillStyle = 'rgba(95, 215, 215, .16)'; g.fill();
      g.strokeStyle = 'rgba(95, 215, 215, .9)'; g.lineWidth = 1.5; g.stroke();
    }
  }

  // the boxes, the far ones first
  const items = [];
  for (const b of bx.boxes.values()) if (bx.free || b.kind !== 'free_space') items.push(shownBox(b, t));
  bx.ghosts = bx.ghosts.filter(b => !b.over);
  for (const b of bx.ghosts) if (bx.free || b.kind !== 'free_space') items.push(shownBox(b, t));
  for (const it of items) {
    if (it.b.how && !it.b.over) moving = true;
    const pts = [], rect = [Infinity, Infinity, -Infinity, -Infinity];
    for (let j = 0; j < 8; j++) {
      const p = P([j & 1 ? it.hi[0] : it.lo[0], j & 2 ? it.hi[1] : it.lo[1], j & 4 ? it.hi[2] : it.lo[2]]);
      pts.push(p);
      rect[0] = Math.min(rect[0], p[0]); rect[1] = Math.min(rect[1], p[1]);
      rect[2] = Math.max(rect[2], p[0]); rect[3] = Math.max(rect[3], p[1]);
    }
    it.pts = pts; it.rect = rect;
  }
  for (const b of bx.boxes.values()) if (b.over) { b.how = ''; b.over = false; }
  const drawn = [], labels = [];
  let solid = items;
  if (items.length > MANY) {
    // So many boxes (a uniform grid, free space before it is merged) are not drawn one by one, which
    // would keep a processor busy: the free ones go down first as one faint layer, all their edges
    // in one stroke and no faces, and only the others are put in order over them.
    solid = items.filter(it => it.b.kind !== 'free_space');
    const lines = new Path2D();
    let colour = null;
    for (const it of items) {
      if (it.b.kind !== 'free_space') continue;
      colour = colour || it.b.colour;
      const pts = it.pts, quads = [];
      for (const [corners, k, up] of FACES) if (up ? eye[k] > it.hi[k] : eye[k] < it.lo[k]) quads.push(corners.map(i => pts[i]));
      for (const [p, q] of EDGES) { lines.moveTo(pts[p][0], pts[p][1]); lines.lineTo(pts[q][0], pts[q][1]); }
      if (it.b.how !== 'gone') drawn.push({b: it.b, quads: quads});
    }
    if (colour) { g.strokeStyle = css(towards(colour, 1, 0.3), Math.min(1, FREE_OPACITY * 4) * 0.6); g.lineWidth = 1; g.stroke(lines); }
    const hot = items.find(it => it.b.id === bx.hover && it.b.kind === 'free_space');
    if (hot) {         // the free one under the pointer, alone over the layer
      g.beginPath();
      for (const [p, q] of EDGES) { g.moveTo(hot.pts[p][0], hot.pts[p][1]); g.lineTo(hot.pts[q][0], hot.pts[q][1]); }
      g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 1.4; g.stroke();
    }
  }
  const key = bx.version + ' ' + bx.free + ' ' + solid.length + ' ' + Math.round(bx.yaw * 120) + ' ' + Math.round(bx.pitch * 120);
  let ordered;
  if (!moving && key === bx.orderKey && bx.order && bx.order.length === solid.length) {
    const by = new Map(solid.map(it => [it.b.id, it]));
    ordered = bx.order.map(id => by.get(id)).filter(Boolean);
    if (ordered.length !== solid.length) ordered = boxOrder(solid, eye);
  } else ordered = boxOrder(solid, eye);
  bx.order = ordered.map(it => it.b.id); bx.orderKey = moving ? '' : key;

  for (const it of ordered) {
    const b = it.b, free = b.kind === 'free_space', shadow = b.kind === 'shadow';
    const fill = (free ? FREE_OPACITY : shadow ? 0.3 : 0.55) * it.a;
    const edge = (free ? Math.min(1, FREE_OPACITY * 4) : shadow ? 0.95 : 1) * it.a;
    const pts = it.pts;
    const seen = (k, up) => up ? eye[k] > it.hi[k] : eye[k] < it.lo[k];
    const line = towards(b.colour, 1, 0.3);
    const hot = bx.hover === b.id && b.how !== 'gone';
    g.setLineDash(shadow && b.region === 'interior' ? [4, 3] : []);
    // the edges on the far side, faint
    g.beginPath();
    for (const [p, q, along] of EDGES) {
      const k1 = (along + 1) % 3, k2 = (along + 2) % 3;
      if (seen(k1, p >> k1 & 1) || seen(k2, p >> k2 & 1)) continue;
      g.moveTo(pts[p][0], pts[p][1]); g.lineTo(pts[q][0], pts[q][1]);
    }
    g.strokeStyle = css(line, edge * (free ? 0.45 : 0.32)); g.lineWidth = 1; g.stroke();
    // the faces towards the eye: the top lighter, the sides along y darker
    const quads = [];
    for (const [corners, k, up] of FACES) {
      if (!seen(k, up)) continue;
      const quad = corners.map(i => pts[i]);
      quads.push(quad);
      path(quad);
      const shade = free ? b.colour : k === 2 ? towards(b.colour, 1, 0.22) : k === 1 ? towards(b.colour, 0, 0.28) : b.colour;
      g.fillStyle = css(shade, fill); g.fill();
    }
    // the edges on the near side
    g.beginPath();
    for (const [p, q, along] of EDGES) {
      const k1 = (along + 1) % 3, k2 = (along + 2) % 3;
      if (!(seen(k1, p >> k1 & 1) || seen(k2, p >> k2 & 1))) continue;
      g.moveTo(pts[p][0], pts[p][1]); g.lineTo(pts[q][0], pts[q][1]);
    }
    g.strokeStyle = css(line, edge); g.lineWidth = free ? 1 : shadow ? 1.4 : 1.8; g.stroke();
    if (it.glow > 0 || hot) {         // a box that just changed, or the one under the pointer
      g.strokeStyle = 'rgba(255,255,255,' + (hot ? 0.9 : 0.85 * it.glow * it.glow) + ')';
      g.lineWidth = hot ? 1.6 : 1 + 2 * it.glow; g.stroke();
    }
    g.setLineDash([]);
    if (b.how !== 'gone') drawn.push({b: b, quads: quads});
    if (!free || hot) {
      const top = P([(it.lo[0] + it.hi[0]) / 2, (it.lo[1] + it.hi[1]) / 2, it.hi[2]]);
      labels.push({text: b.name, x: top[0], y: top[1] - 5, colour: css(towards(b.colour, 1, hot ? 0.75 : 0.45), it.a), a: it.a, rank: hot ? 0 : shadow ? 2 : 1});
    }
  }
  bx.drawn = drawn;

  // The names: the box under the pointer, the objects, the shadows.  A name that would lie on
  // another is put higher, with a thin line down to its box; one that finds no room is left out
  // (the pointer shows it).
  if (gr && gr.robot) { const at = P([gr.robot[0], gr.robot[1], gr.z]); labels.push({text: 'robot', x: at[0], y: at[1] + 16, colour: 'rgba(95, 215, 215, .9)', rank: 3, fixed: true}); }
  g.font = '11px "Segoe UI", system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
  const placed = [], written = new Set();
  const frame = wrap.getBoundingClientRect(), btns = $('boxbtns').getBoundingClientRect();
  placed.push([btns.left - frame.left - 4, 0, w, btns.bottom - frame.top + 2]);      // the two buttons
  for (const lab of labels.sort((p, q) => p.rank - q.rank)) {
    if (written.has(lab.text)) continue;         // the parts of one shadow carry one name
    const half = g.measureText(lab.text).width / 2 + 3;
    const x = Math.min(w - half, Math.max(half, lab.x));
    for (let lift = 0; lift < (lab.fixed ? 1 : lab.rank < 2 ? 8 : 5); lift++) {
      const y = Math.min(h - 4, Math.max(12, lab.y - 13 * lift));
      const box = [x - half, y - 11, x + half, y + 3];
      if (placed.some(o => box[0] < o[2] && o[0] < box[2] && box[1] < o[3] && o[1] < box[3])) continue;
      placed.push(box);
      written.add(lab.text);
      if (lift) { g.beginPath(); g.moveTo(lab.x, lab.y + 4); g.lineTo(x, y + 3); g.strokeStyle = lab.colour; g.lineWidth = 0.7; g.stroke(); }
      g.lineWidth = 3; g.strokeStyle = 'rgba(12, 13, 20, ' + 0.8 * (lab.a == null ? 1 : lab.a) + ')';
      g.strokeText(lab.text, x, y);
      g.fillStyle = lab.colour; g.fillText(lab.text, x, y);
      break;
    }
  }
  bx.dirty = moving;
}

function boxUnder() {
  // the box under the pointer: the nearest object or shadow there, else the nearest free one
  if (!bx.mouse) return null;
  const [x, y] = bx.mouse;
  const within = (quad) => {
    let sign = 0;
    for (let i = 0; i < 4; i++) {
      const a = quad[i], b = quad[(i + 1) % 4];
      const side = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]);
      if (side !== 0) { if (sign && (side > 0) !== (sign > 0)) return false; sign = side; }
    }
    return true;
  };
  let free = null;
  for (let i = bx.drawn.length - 1; i >= 0; i--) {
    const d = bx.drawn[i];
    if (!d.quads.some(within)) continue;
    if (d.b.kind !== 'free_space') return d.b;
    free = free || d.b;
  }
  return free;
}

function boxHover() {
  const b = bx.drag ? null : boxUnder(), id = b ? b.id : null;
  if (id === bx.hover) return;
  bx.hover = id; bx.dirty = true;
  const m = (k) => (b.max[k] - b.min[k]).toFixed(2);
  $('boxtip').textContent = b ? b.name + (b.name !== b.id ? ' (' + b.id + ')' : '') + '  ·  ' + whatIs(b)
    + '  ·  ' + m(0) + ' × ' + m(1) + ' × ' + m(2) + ' m' : '';
}

function boxFrame(t) {
  requestAnimationFrame(boxFrame);
  if (document.hidden) return;
  const turns = bx.turning && !bx.drag && !ended;
  if (!bx.dirty && !turns) { bx.last = t; return; }
  // The slow turn needs no more than 25 pictures a second, and no picture may cost more than a
  // fifth of the time until the next (a half while something moves): the page runs beside the run.
  if (t - bx.last < (bx.dirty ? 2 * bx.cost : Math.max(40, 5 * bx.cost))) return;
  if (turns && bx.last) bx.yaw += Math.min(1000, t - bx.last) * TURN;
  const before = performance.now();
  drawBoxels(t);
  bx.cost = 0.7 * bx.cost + 0.3 * (performance.now() - before);
  bx.last = t;
  boxHover();
}

function boxTouched() {          // the first touch ends the turn by itself
  bx.turning = false; bx.chosen = true;
  $('boxturn').classList.remove('on');
}
{
  const cv = $('boxview');
  const at = (ev) => { const r = cv.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
  cv.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    bx.drag = {x: ev.clientX, y: ev.clientY};
    cv.setPointerCapture(ev.pointerId); cv.classList.add('drag');
    boxTouched();
  });
  cv.addEventListener('pointermove', ev => {
    bx.mouse = at(ev);
    if (bx.drag) {
      bx.yaw -= (ev.clientX - bx.drag.x) * 0.008;
      bx.pitch = Math.min(1.45, Math.max(0.06, bx.pitch + (ev.clientY - bx.drag.y) * 0.006));
      bx.drag = {x: ev.clientX, y: ev.clientY};
      bx.dirty = true;
    } else boxHover();
  });
  const up = () => { bx.drag = null; cv.classList.remove('drag'); bx.dirty = true; };
  cv.addEventListener('pointerup', up);
  cv.addEventListener('pointercancel', up);
  cv.addEventListener('pointerleave', () => { if (!bx.drag) { bx.mouse = null; boxHover(); } });
  cv.addEventListener('wheel', ev => {
    ev.preventDefault();
    bx.zoom = Math.min(6, Math.max(0.5, bx.zoom * Math.exp(-ev.deltaY * 0.0012)));
    bx.dirty = true;
    boxTouched();
  }, {passive: false});
  cv.addEventListener('dblclick', () => {       // start over: the first view, turning
    bx.yaw = VIEW.yaw; bx.pitch = VIEW.pitch; bx.zoom = VIEW.zoom; bx.turning = true; bx.chosen = true; bx.dirty = true;
    $('boxturn').classList.add('on');
  });
  $('boxturn').addEventListener('click', () => { bx.turning = !bx.turning; bx.chosen = true; $('boxturn').classList.toggle('on', bx.turning); });
  const large = (big) => { $('boxbig').textContent = big ? 'smaller' : 'larger'; $('boxbig').classList.toggle('on', big); };
  large(document.body.classList.contains('bigbox'));
  $('boxbig').addEventListener('click', () => large(document.body.classList.toggle('bigbox')));
  $('boxline').addEventListener('click', ev => {
    if (!ev.target.closest('#freekey')) return;
    bx.free = !bx.free; bx.dirty = true;
    boxKey();
  });
  new ResizeObserver(() => { bx.dirty = true; }).observe($('boxwrap'));
}

$('camrow').addEventListener('click', ev => {
  const fig = ev.target.closest('figure');
  if (!fig) return;
  const row = $('camrow'), big = fig.classList.contains('big');
  for (const f of row.querySelectorAll('figure')) f.classList.remove('big');
  row.classList.toggle('one', !big);
  if (!big) fig.classList.add('big');
});

$('log').addEventListener('scroll', () => {
  const log = $('log');
  following = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
});
new ResizeObserver(() => { if (following) $('log').scrollTop = $('log').scrollHeight; }).observe($('log'));

for (const name of ['rgb', 'depth', 'mask']) $('cam-' + name).src = BLANK;
boxKey();
requestAnimationFrame(boxFrame);
setInterval(draw, 50);
poll();
})();
</script>
</body>
</html>
'''
