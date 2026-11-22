"""C-01: what test_full_pipeline.py's entry block makes of the end of main().

An exception out of main() used to end the process with exit code 1, the
code of a failed episode, so eval_runner filed the crash as no_summary or
banked it with the episode's verdict.  The entry block now ends it with
exit code 70, after its clean-up, and shows it through sys.excepthook as
before.  Ctrl-C, SystemExit and the codes 0 and 1 are as they were.

The entry block is module code under `if __name__ == "__main__":`, and it
builds a scene in the simulator before it reaches main().  So these tests
run the block's own statements from `logger = RunLogger(...)` to its end:
taken from the source by ast, compiled as they are, and run with stand-ins
for the names they use.  One test runs them in a process of its own, with
the real console_ui and Python's own excepthook (what a cell of
eval_runner uses at --log-level quiet).
"""
import ast
import subprocess
import sys
import types
from pathlib import Path

import pytest

SOURCE_PATH = Path(__file__).resolve().parents[1] / 'test_full_pipeline.py'
CRASH_EXIT = 70
CLEAN_UP = ['telemetry.disable', 'world_eye.disable', 'logger.close']
MESSAGE = 'the planner state is broken'


def _entry_tail():
    """The entry block from `logger = RunLogger(...)` to its end, compiled
    with the file's own name and line numbers."""
    tree = ast.parse(SOURCE_PATH.read_text(encoding='utf-8'))
    (entry,) = [n for n in tree.body if isinstance(n, ast.If)
                and ast.unparse(n.test) == "__name__ == '__main__'"]
    (start,) = [i for i, s in enumerate(entry.body)
                if isinstance(s, ast.Assign)
                and ast.unparse(s.targets[0]) == 'logger']
    return compile(ast.Module(body=entry.body[start:], type_ignores=[]),
                   str(SOURCE_PATH), 'exec')


class _AnyArgs:
    """The parsed command line: every flag reads as None."""
    def __getattr__(self, name):
        return None


def _stand_ins(main, console_ui, calls):
    """The names the entry block's tail uses; every call is noted."""
    def note(name):
        return lambda *args, **kwargs: calls.append(name)

    def run_main(**kwargs):
        calls.append('main')
        return main()

    return {
        'args': _AnyArgs(), 'scene_cfg': None, 'run_config': {},
        'RunLogger': lambda verbosity: types.SimpleNamespace(
            close=note('logger.close')),
        'main': run_main,
        'telemetry': types.SimpleNamespace(disable=note('telemetry.disable')),
        'world_eye': types.SimpleNamespace(disable=note('world_eye.disable')),
        'console_ui': console_ui,
        'sys': sys,
    }


def _crash():
    raise RuntimeError(MESSAGE)


@pytest.fixture
def entry(monkeypatch):
    """entry(main) runs the tail with main standing in for main() and
    returns (what ended it, the calls in order, what the hook was shown).
    console_ui.finish is the one without a console: sys.exit(code)."""
    def run(main):
        calls, shown = [], []

        def finish(code=0):
            calls.append(f'finish {code}')
            raise SystemExit(code)

        def hook(exc_type, exc, tb):
            calls.append('excepthook')
            shown.append((exc_type, exc, tb))

        monkeypatch.setattr(sys, 'excepthook', hook)
        try:
            exec(_entry_tail(), _stand_ins(
                main, types.SimpleNamespace(finish=finish), calls))
        except BaseException as end:     # SystemExit and Ctrl-C end it too
            return end, calls, shown
        return None, calls, shown
    return run


def test_an_exception_in_main_ends_with_the_crash_code_after_the_clean_up(entry):
    end, calls, shown = entry(_crash)
    assert isinstance(end, SystemExit) and end.code == CRASH_EXIT
    # the clean-up first, then the crash shown by the hook, then the exit
    assert calls == ['main'] + CLEAN_UP + ['excepthook', f'finish {CRASH_EXIT}']
    ((exc_type, exc, tb),) = shown
    assert exc_type is RuntimeError and str(exc) == MESSAGE
    # the traceback starts in the entry block, as the interpreter's own does
    assert tb.tb_frame.f_code.co_filename == str(SOURCE_PATH)


def test_ctrl_c_in_main_is_not_caught(entry):
    def interrupted():
        raise KeyboardInterrupt
    end, calls, shown = entry(interrupted)
    assert isinstance(end, KeyboardInterrupt)
    assert calls == ['main'] + CLEAN_UP and shown == []


def test_a_system_exit_in_main_is_not_caught(entry):
    def leaves():
        raise SystemExit(2)
    end, calls, shown = entry(leaves)
    assert isinstance(end, SystemExit) and end.code == 2
    assert calls == ['main'] + CLEAN_UP and shown == []


@pytest.mark.parametrize('success, code', [(True, 0), (False, 1)])
def test_a_run_that_ends_exits_0_or_1_as_before(entry, success, code):
    end, calls, shown = entry(lambda: success)
    assert isinstance(end, SystemExit) and end.code == code
    assert calls == ['main'] + CLEAN_UP + [f'finish {code}'] and shown == []


def test_as_a_process_a_crash_exits_70_with_the_traceback_on_stderr():
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve())],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == CRASH_EXIT, proc.stdout + proc.stderr
    lines = proc.stderr.splitlines()
    assert lines[0] == 'Traceback (most recent call last):'
    assert lines[-1] == f'RuntimeError: {MESSAGE}'
    assert proc.stdout.split() == ['main'] + CLEAN_UP


if __name__ == '__main__':
    # The process of the test above: the tail with the real console_ui (no
    # console is installed, so finish is sys.exit) and Python's own
    # excepthook.  main() raises; the calls made are printed at the end.
    sys.path.insert(0, str(SOURCE_PATH.parent))
    from console import console_ui
    made = []
    try:
        exec(_entry_tail(), _stand_ins(_crash, console_ui, made))
    finally:
        print(' '.join(made), flush=True)
