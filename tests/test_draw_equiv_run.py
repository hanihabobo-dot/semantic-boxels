"""BF#68: tools/draw_equiv_run.py, the harness that produces the evidence, run
on a stand-in driver in a scratch checkout (--repo): it hashes every render,
counts debug calls, keeps each call on its own client, reads the renderer
from its real argument slot, and refuses to run into a folder that holds a
run.  Each case runs in its own process: the console takes over fds 1 and 2."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, 'tools', 'draw_equiv_run.py')

FAKE_DRIVER = '''
import numpy as np
import pybullet as p
from pybullet_utils import bullet_client
import console_ui

view = p.computeViewMatrix([0, -1, 1], [0, 0, 0], [0, 0, 1])
proj = p.computeProjectionMatrixFOV(60, 1.0, 0.05, 3.0)
c0 = p.connect(p.DIRECT)
b = bullet_client.BulletClient(p.DIRECT)          # its own client, not 0
assert b._client != c0 and c0 == 0
# every positional argument up to the renderer (slot 11), as TAMPURA's code passes them
p.getCameraImage(8, 8, view, proj, [0, 0, 1], [1, 1, 1], 1.0, 1, 0.6, 0.8, 0.4,
                 p.ER_TINY_RENDERER, physicsClientId=c0)
b.getCameraImage(8, 8, viewMatrix=view, projectionMatrix=proj,
                 renderer=p.ER_TINY_RENDERER)
p.getCameraImage(8, 8, viewMatrix=view, projectionMatrix=proj,
                 renderer=p.ER_BULLET_HARDWARE_OPENGL, physicsClientId=c0)
p.addUserDebugLine([0, 0, 0], [1, 1, 1], physicsClientId=c0)
b.addUserDebugText('x', [0, 0, 0])
b.removeAllUserDebugItems()
console_ui.finish(0)
'''


def _repo(tmp_path):
    repo = tmp_path / 'repo'
    (repo / 'tampura_bridge').mkdir(parents=True)
    (repo / 'tampura_bridge' / 'run_bridge_on_finddice.py').write_text(FAKE_DRIVER)
    return repo


def _run(tmp_path, out, repo, *extra):
    # HOME in tmp_path: the console writes its start-up debug file under
    # ~/.cache/semantic_boxels, which no tool sweeps; a test run leaves none there.
    env = dict(os.environ, PYTHONPATH=ROOT, PYTHONDONTWRITEBYTECODE='1', HOME=str(tmp_path))
    return subprocess.run(
        [sys.executable, HARNESS, '--out', str(out), '--repo', str(repo), *extra,
         '--', '--global-seed', '0', '--vis', '0'],
        capture_output=True, text=True, timeout=180, env=env, cwd=str(tmp_path))


def test_it_hashes_every_render_and_counts_debug_calls(tmp_path):
    out = tmp_path / 'out'
    proc = _run(tmp_path, out, _repo(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = [json.loads(ln) for ln in (out / 'render_hashes.jsonl').read_text().splitlines()]
    assert [r['tiny'] for r in rows] == [True, True, False]    # renderer read from slot 11
    # a call through BulletClient stays on the client it names (the wrapper is
    # a Python function, which BulletClient would not give a client id to)
    assert rows[0]['client'] == 0 and rows[1]['client'] != 0 and rows[2]['client'] == 0
    assert all(r['rgb'] and r['depth'] and r['seg'] and r['view'] and r['proj'] for r in rows)
    final = json.loads((out / 'probe_final.json').read_text())
    assert final['debug_calls'] == {'line': 1, 'text': 1, 'remove': 0, 'remove_all': 1}
    assert final['renders'] == 3 and final['exit_code'] == 0
    assert set(final['clients']) == {'0', str(rows[1]['client'])}
    info = json.loads((out / 'run_info.json').read_text())
    assert info['repo'] == str(tmp_path / 'repo')


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='run_procs.sh reads /proc')
def test_run_procs_lists_and_ends_the_harness_like_any_pipeline_process(tmp_path):
    import time
    # run.ps1 feeds the file to bash through tr -d '\r'
    with open(os.path.join(ROOT, 'tools', 'run_procs.sh'), encoding='utf-8') as f:
        procs = f.read().replace('\r', '')
    script = tmp_path / 'draw_equiv_run.py'
    script.write_text('import time\ntime.sleep(120)\n')
    p = subprocess.Popen([sys.executable, str(script), '--out', str(tmp_path / 'OUTX'),
                          '--', '--global-seed', '5', '--vis', '1'])
    try:
        def run_procs(*args):
            return subprocess.run(['bash', '-s', '--', *args], input=procs,
                                  capture_output=True, text=True, timeout=60).stdout
        line = ''
        for _ in range(50):
            mine = [ln for ln in run_procs('list').splitlines() if ln.startswith(f'pid {p.pid} ')]
            if mine:
                line = mine[0]
                break
            time.sleep(0.2)
        assert 'check harness (BF#68) seed 5, GUI, OUTX' in line, line
        run_procs('kill-mine', 'OUTX', '100')
        assert p.wait(timeout=20) is not None
    finally:
        if p.poll() is None:
            p.kill()


def test_it_refuses_a_folder_that_holds_a_run_and_a_repo_without_a_driver(tmp_path):
    out = tmp_path / 'out'
    repo = _repo(tmp_path)
    assert _run(tmp_path, out, repo).returncode == 0
    again = _run(tmp_path, out, repo)
    assert again.returncode != 0 and 'holds a run already' in again.stdout + again.stderr
    bare = tmp_path / 'bare'
    bare.mkdir()
    none = _run(tmp_path, tmp_path / 'out2', bare)
    assert none.returncode != 0 and 'no driver' in none.stdout + none.stderr
