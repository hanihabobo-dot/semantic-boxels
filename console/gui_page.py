"""The page beside our own simulator window (Hani, 2026-11-22; BF#27).

With `--gui-page on` our own window (`run boxels`) opens without PyBullet's
own panels (the menu, the tabs, the Params column, the white strip, the
status bar, the grid and the three camera panes: one switch,
COV_ENABLE_GUI, set by boxel_env) and this module serves a page for a
browser beside it: the console's moving drawing of what the robot does now
with its status, the three pictures of the robot's camera (colour, depth,
mask) and the console's committed lines.

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

The server listens on 127.0.0.1 only, answers GET only and serves no file
of the disk: the page (/), the console's looks (/art), the state (/state)
and the three pictures (/cam/rgb.png, /cam/depth.png, /cam/mask.png).  It
never opens a browser; the launcher (run.ps1) does, on the Windows side.

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
        from http.server import ThreadingHTTPServer
        self._console = console
        self.token = str(token or '')
        self.started = time.time()
        self._lock = threading.Lock()
        self._cam = None           # the latest render handed over
        self._renders = 0
        self._png = {}             # (render number, picture name) -> PNG bytes
        self._served = (0.0, -1)   # (monotonic time, console line number) of the last /state
        self._httpd = ThreadingHTTPServer(('127.0.0.1', int(port)), _handler_class())
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
        the run: the page keeps its last pictures."""
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

    # ----- asked by the server's threads ----------------------------------------

    def html(self):
        return (_HTML.replace('__TITLE__', self.title)
                .replace('__POLL_MS__', str(POLL_MS)))

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
        return {'run': {'token': self.token, 'pid': os.getpid(), 'started': self.started,
                        'now': time.time(), 'port': self.port},
                'console': snap, 'camera': meta}

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


_handler = None


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
:root { --bg:#161822; --line:#2a2e42; --text:#e6e8ef; --dim:#9aa0b4; --brand:#5fd7d7; --well:#0c0d14; }
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
main { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 1fr); }
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
#log { overflow: auto; padding: 10px 16px 16px; font-size: 13px; line-height: 1.45; }
.ln { white-space: pre-wrap; overflow-wrap: anywhere; min-height: 1.45em; }
#noconsole { color: var(--dim); padding: 10px 16px; display: none; }
#oops { display: none; padding: 6px 16px; background: #4a1f1f; color: #ffd0d0; font-size: 12px; white-space: pre-wrap; }
@media (min-width: 980px) {
  main { grid-template-columns: minmax(0, 1fr) 360px; grid-template-rows: auto minmax(0, 1fr); }
  #cams { grid-column: 2; grid-row: 1 / span 2; border-bottom: 0; border-left: 1px solid var(--line); overflow: auto; }
  .camrow { grid-template-columns: minmax(0, 1fr); }
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
  #log { padding: 8px 10px 12px; font-size: 12px; }
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
  for (const id of ['log', 'art', 'head', 'info', 'status', 'counts']) empty(id);
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
setInterval(draw, 50);
poll();
})();
</script>
</body>
</html>
'''
