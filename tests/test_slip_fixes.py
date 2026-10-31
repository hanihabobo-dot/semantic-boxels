"""BF#59: the die-slip campaign's switch registry (slip_fixes.py) and its
plumbing: run_logger's --slip-fixes, main()'s configure call, the run
record, the bridge driver's pass-through."""
import inspect
import re

import pytest

import slip_fixes


@pytest.fixture
def registry():
    """A clean registry for one test; the module's state restored after."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.KNOWN.clear()
    slip_fixes.ENABLED = frozenset()
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


def test_nothing_on_by_default(registry):
    registry.register('a_fix', 'a line')
    assert registry.configure('') == frozenset()
    assert not registry.on('a_fix')
    assert registry.spec() == ''


def test_configure_switches_the_named_fixes_on(registry):
    registry.register('a_fix', 'a line')
    registry.register('b_fix', 'b line')
    assert registry.configure('b_fix, a_fix') == {'a_fix', 'b_fix'}
    assert registry.on('a_fix') and registry.on('b_fix')
    assert registry.spec() == 'a_fix,b_fix'
    assert registry.configure('a_fix') == {'a_fix'}         # the others go off again
    assert not registry.on('b_fix')
    assert registry.parse('a+b') == ['a', 'b']               # an arm's spelling


def test_an_unknown_name_is_refused(registry):
    registry.register('a_fix', 'a line')
    with pytest.raises(ValueError, match="unknown slip fix"):
        registry.configure('a_fix,typo')
    assert registry.ENABLED == frozenset()                   # nothing half applied


def test_register_is_idempotent_and_checks_the_name(registry):
    registry.register('a_fix', 'a line')
    registry.register('a_fix', 'a line')
    with pytest.raises(ValueError):
        registry.register('a_fix', 'another line')
    for bad in ('A_fix', 'a,b', 'a+b', ''):
        with pytest.raises(ValueError):
            registry.register(bad, 'x')


def test_the_flag_and_the_plumbing():
    import run_logger
    import test_full_pipeline
    src = inspect.getsource(run_logger)
    assert "'--slip-fixes'" in src
    main_src = inspect.getsource(test_full_pipeline.main)
    assert re.search(r"slip_fixes\.configure\(getattr\(args, 'slip_fixes', ''\)\)", main_src)
    assert 'slip_fixes=slip_fixes.spec()' in main_src           # the ledger's domain row
    whole = inspect.getsource(test_full_pipeline)
    assert '"slip_fixes": getattr(args, \'slip_fixes\', \'\')' in whole   # the run record
    args = test_full_pipeline.parse_pipeline_args(['--no-gui', '--goal', 'holding'])
    assert args.slip_fixes == ''
    args = test_full_pipeline.parse_pipeline_args(['--no-gui', '--goal', 'holding',
                                                   '--slip-fixes', 'a_fix'])
    assert args.slip_fixes == 'a_fix'


def test_the_driver_passes_it_through():
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'tampura_bridge', 'run_bridge_on_finddice.py'),
              encoding='utf-8') as f:
        src = f.read()
    assert "ap.add_argument('--slip-fixes', default='')" in src
    assert "'slip_fixes': a.slip_fixes" in src
