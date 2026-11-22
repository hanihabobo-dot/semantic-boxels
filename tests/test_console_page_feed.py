"""The console's feed for the page beside our own window (gui_page; Hani,
2026-11-22): console_ui.page_snapshot and page_art.

The page shows the committed lines as the terminal shows them, in their
styles, and the live activity.  Each test drives the real console in a
process of its own (it takes the process's file descriptors over), once
with a captured console and once on a terminal (a pty no window shows),
and reads the snapshots it took."""
import json
import os
import pty
import struct
import subprocess
import sys
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FEED = r'''
import json, sys, time
from console import console_ui

out_path, debug_path = sys.argv[1], sys.argv[2]
seen = {'before': console_ui.page_snapshot()}       # no console yet
c = console_ui.install(debug_path)
console_ui.header(scene='random-pairs seed 3', goal='holding blue_object', switches='m8 on')
seen['header'] = console_ui.page_snapshot()
c.narration('=== PLAN #1 ===')
time.sleep(0.05)
seen['thinking'] = console_ui.page_snapshot(seen['header']['seq'])
console_ui.on_ledger_event('plan', {'plan_id': 1, 'plan_time_s': 1.25, 'actions': [
    ['move', 'view__red'], ['pick', 'red_object', 'b3'], ['place', 'red_object', 'b7']]})
console_ui.on_ledger_event('step', {'plan': 1, 'step': 2, 'action': 'pick',
                                    'args': ['red_object', 'b3'], 't': 10.0})
seen['acting'] = console_ui.page_snapshot(seen['thinking']['seq'])
console_ui.on_ledger_event('step_end', {'status': 'ok', 't': 12.5})
console_ui.say('G1   PASS  a gate row')
console_ui.warn('a warning')
seen['done'] = console_ui.page_snapshot(seen['acting']['seq'])
seen['all'] = console_ui.page_snapshot()
seen['tty'] = c._tty
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(seen, f)
console_ui.uninstall()
'''


def _run(tmp_path, terminal):
    out, debug = tmp_path / 'seen.json', tmp_path / 'console_debug.log'
    cmd = [sys.executable, '-c', _FEED, str(out), str(debug)]
    env = dict(os.environ, LANG='C.UTF-8', LC_ALL='C.UTF-8', TERM='xterm-256color')
    env.pop('NO_COLOR', None)
    if not terminal:
        done = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr[-2000:]
    else:
        import fcntl
        import termios
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 100, 0, 0))
        drained = []

        def drain():
            try:
                while True:
                    chunk = os.read(master, 65536)
                    if not chunk:
                        return
                    drained.append(chunk)
            except OSError:
                return

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            done = subprocess.run(cmd, cwd=REPO, env=env, stdout=slave, stderr=subprocess.PIPE,
                                  stdin=subprocess.DEVNULL, text=True, timeout=120)
        finally:
            os.close(slave)
        reader.join(timeout=5)
        os.close(master)
        assert done.returncode == 0, done.stderr[-2000:]
    seen = json.loads(out.read_text(encoding='utf-8'))
    mirrored = [line[len('[console] '):] for line in debug.read_text(encoding='utf-8').splitlines()
                if line.startswith('[console] ')]
    return seen, mirrored


def _text(row):
    return ''.join(text for text, _ in row[1])


@pytest.fixture(scope='module', params=['captured', 'terminal'])
def fed(request, tmp_path_factory):
    seen, mirrored = _run(tmp_path_factory.mktemp(request.param), request.param == 'terminal')
    assert seen['tty'] is (request.param == 'terminal')
    return request.param, seen, mirrored


def test_without_a_console_there_is_no_snapshot(fed):
    assert fed[1]['before'] is None


def test_the_lines_are_numbered_and_asked_for_from_a_number(fed):
    _, seen, _ = fed
    every = seen['all']['lines']
    assert [row[0] for row in every] == list(range(1, seen['all']['seq'] + 1))
    after = seen['header']['seq']
    assert seen['thinking']['lines'] == [row for row in every
                                         if after < row[0] <= seen['thinking']['seq']]
    assert seen['done']['lines'] == [row for row in every if row[0] > seen['acting']['seq']]


def test_the_page_gets_the_lines_the_terminal_shows(fed):
    """Every line of the page is a committed line of the console, word for
    word as the debug file mirrors it; the debug file's lines that the
    terminal does not show (a gate row held for the verdict) are not on the
    page."""
    mode, seen, mirrored = fed
    texts = [_text(row) for row in seen['all']['lines']]
    assert 'G1   PASS  a gate row' in ' '.join(mirrored)
    if mode == 'captured':
        assert texts == mirrored[:len(texts)]       # the rest came after the last snapshot
    else:
        shown = [line for line in mirrored if 'G1   PASS' not in line]
        assert texts == shown[:len(texts)]
        assert not [t for t in texts if 'G1   PASS' in t]
    assert any(t.endswith('Mission: get hold of `blue_object`.'.replace('`', '')) for t in texts)


def test_the_lines_keep_their_styles(fed):
    _, seen, _ = fed
    rows = {_text(row): row[1] for row in seen['all']['lines']}
    mission = next(parts for text, parts in rows.items() if 'Mission:' in text)
    assert mission[0][1] == 'cyan'                              # the bullet
    assert ['blue_object', 'obj'] in mission                    # an object's name
    warning = next(parts for text, parts in rows.items() if 'a warning' in text)
    assert {style for _, style in warning} == {'yellow'}
    sub = next(parts for text, parts in rows.items() if 'I will' in text)
    assert sub[0] == ['  ', None] and sub[1][1] == 'dim'        # the indent, then the sub glyph
    assert not [parts for parts in rows.values() if any(text == '' for text, _ in parts)]


def test_the_live_activity_is_what_the_robot_does_now(fed):
    _, seen, _ = fed
    assert seen['header']['live'] is None
    think = seen['thinking']['live']
    assert think['kind'] == 'think' and think['sprite'] == 'think'
    assert ''.join(text for text, _ in think['head']).endswith('how to get hold of blue_object')
    assert think['elapsed'] >= 0.05
    act = seen['acting']['live']
    assert act['kind'] == 'act' and act['sprite'] == 'pick' and act['id'] != think['id']
    assert 'Picking up red_object' in ''.join(text for text, _ in act['head'])
    assert act['info'] == ['step 2 of 3 in plan 1']
    assert seen['done']['live'] is None


def test_the_counts_follow_the_run(fed):
    _, seen, _ = fed
    assert seen['header']['counts'] == {'plans': 0, 'plans_found': 0, 'dispatched': 0,
                                        'completed': 0, 'failed': 0, 'holding': None,
                                        'unknown': None}
    assert seen['done']['counts'] == {'plans': 1, 'plans_found': 1, 'dispatched': 1,
                                      'completed': 1, 'failed': 0, 'holding': 'red_object',
                                      'unknown': None}


def test_only_the_last_lines_are_kept():
    from console import console_ui
    assert console_ui.PAGE_LINES == 500


def test_the_looks_are_the_consoles_own():
    from console import console_art
    from console import console_ui
    art = console_ui.page_art()
    json.dumps(art)                                             # plain data
    assert art['codes'] == console_ui._CODES_256
    assert art['palette'] == {key: codes[0] for key, codes in console_art.PALETTE.items()}
    assert art['kinds'] == {kind: list(hues) for kind, hues in console_ui._PALETTE.items()}
    assert tuple(art['cube']) == console_ui._CUBE and tuple(art['stars']) == console_ui._STARS
    assert art['sprites'] == console_art.SPRITES
    assert art['frame_ms'] == 100 and art['light_len'] == console_ui._LIGHT_LEN
