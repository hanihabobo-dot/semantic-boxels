"""Hani, 2026-11-22: "this one looks best" on the sketch of our own window
without PyBullet's panels and a page of our own beside it.  The page's
server (gui_page.py): what it serves, to whom, and that it only ever reads.

No test here opens a window or a browser (tracks rule 13): the server is
asked over its own socket.  What the page looks like in a browser is the
screen check's finding (tracks/dbgcams/STATE.md)."""
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import time

import numpy as np
import pytest
from PIL import Image

from console import console_ui
from console import gui_page

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeConsole:
    """What gui_page asks of console_ui, with the calls written down."""

    def __init__(self):
        self.seq = 5
        self.asked = []

    def page_snapshot(self, after=0):
        self.asked.append(after)
        lines = [[n, [['line %d' % n, None]]] for n in range(1, self.seq + 1) if n > after]
        return {'seq': self.seq, 'lines': lines, 'live': None, 'run_id': 'a_run',
                'elapsed': 1.5, 'counts': {}}

    def page_art(self):
        return console_ui.page_art()


@pytest.fixture
def page():
    assert gui_page.active() is None
    console = FakeConsole()
    started = gui_page.start(console=console, port=0, token='tok')
    assert started is not None and gui_page.active() is started
    started.console = console
    yield started
    gui_page.stop()
    assert gui_page.active() is None


def _get(page, path, host=None, method='GET'):
    conn = http.client.HTTPConnection('127.0.0.1', page.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader('Host', host or 'localhost:%d' % page.port)
        conn.endheaders()
        answer = conn.getresponse()
        return answer.status, dict(answer.getheaders()), answer.read()
    finally:
        conn.close()


def _render(w=8, h=6):
    """A render as getCameraImage hands it: rgb with its alpha, the raw depth
    buffer, the body ids (-1 is the background)."""
    rgb = np.zeros((h, w, 4), dtype=np.uint8)
    rgb[:, :, 0] = np.arange(w, dtype=np.uint8) * 30
    rgb[:, :, 1] = 77
    rgb[:, :, 3] = 255
    depth = np.full((h, w), 1.0, dtype=np.float32)      # nothing seen
    depth[0, 0] = 0.90                                  # near
    depth[0, 1] = 0.99                                  # far
    seg = np.full((h, w), -1, dtype=np.int32)
    seg[1, 1], seg[2, 2], seg[3, 3] = 0, 3, 23
    return rgb, depth, seg


def _picture(page, name):
    status, headers, body = _get(page, '/cam/%s.png' % name)
    assert status == 200 and headers['Content-Type'] == 'image/png'
    return np.asarray(Image.open(io.BytesIO(body)).convert('RGB'))


def test_importing_the_module_brings_no_pybullet_and_no_server():
    """boxel_env imports gui_page in every run: the import alone loads
    neither PyBullet (the page never calls it) nor the web server."""
    code = ("import sys; from console import gui_page; "
            "print(sorted(m for m in ('pybullet', 'http.server', 'PIL', 'numpy') if m in sys.modules))")
    done = subprocess.run([sys.executable, '-c', code], cwd=REPO, capture_output=True,
                          text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == '[]'


def test_no_page_unless_one_is_started():
    assert gui_page.active() is None


def test_the_server_listens_on_this_machine_only(page):
    assert page._httpd.server_address[0] == '127.0.0.1'
    assert page.url == 'http://localhost:%d/' % page.port


def test_the_page_is_served_with_its_title(page):
    status, headers, body = _get(page, '/')
    text = body.decode('utf-8')
    assert status == 200 and headers['Content-Type'].startswith('text/html')
    assert headers['Cache-Control'] == 'no-store'
    assert '<title>Semantic Boxels (page %d)</title>' % page.port in text
    assert '__TITLE__' not in text and '__POLL_MS__' not in text
    assert 'const POLL_MS = %d;' % gui_page.POLL_MS in text
    # one file: nothing is fetched from another place
    assert 'http://' not in text and 'https://' not in text


def test_the_log_keeps_to_its_newest_line_through_a_resize(page):
    """Held against the simulator's window the page is resized right after it
    opens (tools/page_dock.ps1), and the camera pictures change the log's
    height when they load.  Whether the log follows its newest line is
    therefore a state the reader's own scrolling sets, used when lines come
    and when the log's box changes its size; it is not measured when lines
    come (a log that was at its end before the resize then stayed at the
    top: the trial of 2026-11-22).  Only the page's text can be read here;
    that the log does follow was seen in the trial's picture of the page."""
    text = _get(page, '/')[2].decode('utf-8')
    assert 'let following = true;' in text
    assert "$('log').addEventListener('scroll'" in text
    assert 'following = log.scrollHeight - log.scrollTop - log.clientHeight < 40;' in text
    assert "new ResizeObserver(() => { if (following) $('log').scrollTop = $('log').scrollHeight; }).observe($('log'));" in text
    assert 'if (following && c.lines.length) log.scrollTop = log.scrollHeight;' in text
    assert 'const stick' not in text
    # and the narrow layout the held page gets
    assert '@media (max-width: 520px)' in text


def test_a_request_under_another_host_name_is_refused(page):
    assert _get(page, '/', host='localhost:%d' % page.port)[0] == 200
    assert _get(page, '/', host='127.0.0.1:%d' % page.port)[0] == 200
    assert _get(page, '/state', host='evil.example:%d' % page.port)[0] == 403
    assert _get(page, '/', host='evil.example')[0] == 403


def test_only_what_the_page_needs_is_answered(page):
    assert _get(page, '/nothing')[0] == 404
    assert _get(page, '/cam/other.png')[0] == 404
    assert _get(page, '/cam/../gui_page.py')[0] == 404
    assert _get(page, '/cam/rgb.png')[0] == 404            # no render yet
    assert _get(page, '/state', method='POST')[0] == 501   # GET only
    # no header that lets a page of another site read the answers
    headers = _get(page, '/state')[1]
    assert not [h for h in headers if h.lower().startswith('access-control')]


def test_the_state_carries_the_run_the_console_and_no_camera_yet(page):
    status, headers, body = _get(page, '/state?after=3')
    state = json.loads(body)
    assert status == 200 and headers['Content-Type'] == 'application/json'
    assert state['run']['token'] == 'tok' and state['run']['pid'] == os.getpid()
    assert state['run']['port'] == page.port
    assert state['camera'] is None
    assert state['console']['seq'] == 5
    assert [row[0] for row in state['console']['lines']] == [4, 5]
    assert page.console.asked == [3]
    # without the number, or with something else there, from the start
    json.loads(_get(page, '/state')[2])
    json.loads(_get(page, '/state?after=x')[2])
    assert page.console.asked == [3, 0, 0]


def test_a_page_without_a_console_still_answers():
    bare = gui_page.start(console=None, port=0)
    try:
        state = json.loads(_get(bare, '/state')[2])
        assert state['console'] is None and state['run']['token'] == ''
        assert json.loads(_get(bare, '/art')[2]) == {'css': ''}
        bare.linger()                                   # nothing to wait for
    finally:
        gui_page.stop()


def test_the_three_pictures_of_a_render(page):
    rgb, depth, seg = _render()
    page.offer_render(8, 6, rgb, depth, seg, 0.01, 5.0, 'observation')
    meta = json.loads(_get(page, '/state')[2])['camera']
    assert meta['version'] == 1 and meta['kind'] == 'observation' and meta['size'] == [8, 6]
    assert meta['plan'] is None and meta['step'] is None
    near_m = 5.0 * 0.01 / (5.0 - 4.99 * 0.90)
    far_m = 5.0 * 0.01 / (5.0 - 4.99 * 0.99)
    assert meta['depth_m'] == [pytest.approx(near_m, abs=2e-3), pytest.approx(far_m, abs=2e-3)]

    colour = _picture(page, 'rgb')
    assert colour.shape == (6, 8, 3) and np.array_equal(colour, rgb[:, :, :3])

    grey = _picture(page, 'depth')
    assert tuple(grey[0, 0]) == (255, 255, 255)         # the nearest surface is white
    assert tuple(grey[0, 1]) == (0, 0, 0)               # the farthest black
    assert tuple(grey[5, 7]) == (0, 0, 0)               # and so is where nothing is seen

    mask = _picture(page, 'mask')
    assert tuple(mask[0, 0]) == (0, 0, 0)               # the background
    assert tuple(mask[1, 1]) == gui_page.MASK_COLOURS[0]
    assert tuple(mask[2, 2]) == gui_page.MASK_COLOURS[3]
    assert tuple(mask[3, 3]) == gui_page.MASK_COLOURS[23 % 20]

    # the next render replaces all three
    page.offer_render(8, 6, np.zeros_like(rgb), depth, seg, 0.01, 5.0, 'display')
    meta = json.loads(_get(page, '/state')[2])['camera']
    assert meta['version'] == 2 and meta['kind'] == 'display'
    assert not _picture(page, 'rgb').any()


def test_the_render_is_copied_and_the_callers_arrays_are_left_alone(page):
    rgb, depth, seg = _render()
    before = rgb.copy(), depth.copy(), seg.copy()
    page.offer_render(8, 6, rgb, depth, seg, 0.01, 5.0, 'observation')
    for mine, was in zip((rgb, depth, seg), before):
        assert np.array_equal(mine, was)
    rgb[:] = 9
    seg[:] = 7
    depth[:] = 0.5
    assert np.array_equal(_picture(page, 'rgb'), before[0][:, :, :3])
    assert tuple(_picture(page, 'mask')[0, 0]) == (0, 0, 0)


def test_a_flat_render_is_taken_too(page):
    """A PyBullet built without numpy hands the pixels as flat tuples."""
    rgb, depth, seg = _render()
    page.offer_render(8, 6, tuple(rgb.ravel().tolist()), tuple(depth.ravel().tolist()),
                      tuple(seg.ravel().tolist()), 0.01, 5.0, 'observation')
    assert np.array_equal(_picture(page, 'rgb'), rgb[:, :, :3])


def test_a_render_that_cannot_be_read_never_reaches_the_run(page):
    rgb, depth, seg = _render()
    page.offer_render(8, 6, rgb, depth, seg, 0.01, 5.0, 'observation')
    page.offer_render(8, 6, None, None, None, 0.01, 5.0, 'observation')     # no error
    page.offer_render(8, 6, rgb[:2], depth, seg, 0.01, 5.0, 'observation')  # the wrong size
    meta = json.loads(_get(page, '/state')[2])['camera']
    assert meta['version'] == 1                         # the page keeps its last pictures


def test_the_step_a_render_belongs_to_is_named(page, monkeypatch):
    from console import run_logger
    monkeypatch.setattr(run_logger, 'current_dispatch',
                        lambda: {'plan': 2, 'step': 3, 'action': 'pick'})
    page.offer_render(8, 6, *_render(), 0.01, 5.0, 'display')
    meta = json.loads(_get(page, '/state')[2])['camera']
    assert (meta['plan'], meta['step'], meta['action']) == (2, 3, 'pick')


def test_the_mask_colours_are_the_bridge_camera_windows():
    from tampura_bridge import camera_overlay
    assert [tuple(c) for c in camera_overlay._PALETTE.tolist()] == list(gui_page.MASK_COLOURS)


def test_the_consoles_colours_become_css():
    assert gui_page._css_of('1;38;5;80') == 'font-weight:700;color:#5fd7d7'
    assert gui_page._css_of('2') == 'opacity:.62'
    assert gui_page._css_of('38;5;231') == 'color:#ffffff'
    assert gui_page._css_of('38;5;245') == 'color:#8a8a8a'      # the grey ramp
    assert gui_page._css_of('91').startswith('color:#')
    assert gui_page._css_of(None) == '' and gui_page._css_of('') == ''


def test_the_art_is_the_consoles_and_goes_through_json(page):
    art = json.loads(_get(page, '/art')[2])
    assert 'codes' not in art and 'palette' not in art
    assert '.s-cyan{color:#5fafaf}' in art['css']
    assert '.s-hi_cyan{font-weight:700;color:#5fd7d7}' in art['css']
    assert '.a-%d{' % ord('k') in art['css'] and '.a-%d{' % ord('K') in art['css']
    from console import console_art
    assert set(art['sprites']) == set(console_art.SPRITES)
    for name, sprite in art['sprites'].items():
        for glyphs, mask in sprite['frames']:
            assert len(glyphs) == len(mask) == console_art.HEIGHT, name
            assert [len(row) for row in glyphs] == [len(row) for row in mask], name
    assert set(art['kinds']) == {'startup', 'think', 'act'}
    assert len(art['cube']) == 5 and art['frame_ms'] == 100 and art['stars']
    for r, c in art['cube_loop'] + art['cube_inner']:
        assert art['cube'][r][c] != ' '


def test_a_busy_port_gives_one_of_the_next():
    held = socket.socket()
    held.bind(('127.0.0.1', 0))
    held.listen(1)
    port = held.getsockname()[1]
    try:
        page = gui_page.start(console=None, port=port)
        try:
            assert page is not None and port < page.port < port + gui_page.PORT_TRIES
            assert gui_page.start(console=None, port=port) is page      # started once
        finally:
            gui_page.stop()
    finally:
        held.close()


def test_the_port_and_the_token_come_from_the_environment(monkeypatch):
    monkeypatch.setenv('SB_GUI_PAGE_PORT', '0')
    monkeypatch.setenv('SB_GUI_PAGE_TOKEN', 'from-the-launcher')
    page = gui_page.start(console=None)
    try:
        assert page.port not in (0, gui_page.DEFAULT_PORT)
        assert json.loads(_get(page, '/state')[2])['run']['token'] == 'from-the-launcher'
    finally:
        gui_page.stop()


def test_at_the_end_the_page_gets_its_last_lines(page, monkeypatch):
    """The run's exit waits for the page only while a page is asking, and
    only until a /state has carried the console's last line."""
    monkeypatch.setattr(gui_page, 'LINGER_S', 0.6)
    t0 = time.monotonic()
    page.linger()                                   # no page has asked: no wait
    assert time.monotonic() - t0 < 0.1

    _get(page, '/state')                            # a page has all 5 lines
    t0 = time.monotonic()
    page.linger()
    assert time.monotonic() - t0 < 0.4

    page.console.seq = 6                            # a line the page has not got
    page._served = (time.monotonic(), 5)
    t0 = time.monotonic()
    page.linger()
    assert 0.5 < time.monotonic() - t0 < 1.5
