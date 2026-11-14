#!/usr/bin/env python3
"""Rule 16 of the dev tracks (Hani, 2026-11-07 about 14:08: "make sure runs dont
lead to massive memory buildup anyhwhere"): what path 6's harnesses measure and
decide about memory, in one module that tools/cluster/p6_run.py (the tabletop
cells, through each arm's own eval_runner) and tools/gen_scene_eval.py (the
find_dice episodes) share.

Standard library only.  The /proc readers take their root as an argument, so
the parsers and the decisions run (and are tested) on Windows with a fake tree;
on Windows the readers find nothing and every number is None.  Units: every
number is in kB, as /proc/meminfo, /proc/<pid>/status and /usr/bin/time -v
count; a limit given in GB is 1024 * 1024 kB, and 0 switches a limit off
(it only records).

Names alike with path 5's tampura_on_sb/memguard.py and path 7's guard, so that
one report reads them all: the row field `mem` (a dict of kB values with _kb
names), the flag `peak_over_6gb` (named after the default limit), the log line
STOPPED_LOW_MEMORY (and OUT/STOPPED_LOW_MEMORY.txt) and exit code 4.

One episode's `mem` (EpisodeWatch.as_row), measured around the episode by the
harness process that starts it:
  avail_start_kb    MemAvailable just before the episode started
  avail_end_kb      MemAvailable after it ended
  avail_min_kb      the lowest MemAvailable seen at the start, at any poll (every 2 s) and at the end
  peak_rss_kb       the biggest resident set of one process of the episode: exact when the harness's
                    children high-water mark (getrusage(RUSAGE_CHILDREN), the number /usr/bin/time -v
                    prints as "Maximum resident set size") rose during the episode (peak_exact true),
                    else the largest one seen at a poll, which is a lower bound (an earlier episode
                    already reached the high-water mark, children_hwm_kb)
  children_hwm_kb   the high-water mark after the episode (never goes down: the largest child so far)
  group_peak_kb     the highest SUM of VmRSS over the processes below the harness at a poll (python,
                    SymK's Fast Downward, workers); a shared page counts twice, so it is an upper
                    bound, and a spike between two polls can be missed
  polls             how many polls
  batch_rss_kb      the harness process's own resident set at the episode's end (flat across the
                    episodes means that nothing accumulates in the harness)
  leftover          processes that run a pipeline program (STRAY_WORDS) after the episode and did not
                    before it: reported, never ended here (a kill by name is not ours to make)
  shm_new           names that appeared in /dev/shm during the episode (reported, never deleted)
  min_avail_limit_kb, peak_limit_kb   the two limits in force
  peak_over_limit   the larger of the two peaks is over peak_limit_kb
and the row's top-level flag `peak_over_6gb`, the same value.

The stop rule: MemAvailable under the limit (4 GB) at any reading of an episode
(start, polls, end) stops the batch after that episode's row; under it before an
episode, nothing starts.  A stop writes STOPPED_LOW_MEMORY.txt, prints the
STOPPED_LOW_MEMORY line and the harness exits with code 4 (on the laptop the lock
goes with the shell).  Nothing here ends a process or drops a cache.
"""
import json
import os
import threading
import time

KB_PER_GB = 1024 * 1024
MIN_AVAIL_GB = 4.0       # MemAvailable under this: nothing starts, and the batch stops after the episode
PEAK_REPORT_GB = 6.0     # a peak RSS over this is flagged (`peak_over_6gb`) and reported
EXIT_LOW_MEMORY = 4      # the harness's exit code after STOPPED_LOW_MEMORY (paths 5 and 7 use it too)
POLL_S = 2.0
STOP_FILE = 'STOPPED_LOW_MEMORY.txt'
STRAY_WORDS = ('downward', 'translate', 'test_full_pipeline', 'run_bridge_on_finddice',
               'run_tampura_timed', 'run_planner')
DEAD_STATES = ('Z', 'X')


def fmt_gb(kb):
    return 'n/a' if kb is None else '%.2f GB' % (kb / KB_PER_GB)


def limit_kb(gb):
    return int(gb * KB_PER_GB)


def low_memory(avail_kb, min_kb):
    """True when MemAvailable is known and under a limit that is on (an unreadable meminfo is not a stop)."""
    return bool(min_kb) and min_kb > 0 and avail_kb is not None and avail_kb < min_kb


class LowMemory(BaseException):
    """MemAvailable is under the limit.  where: 'start' (the episode did not start) or 'end' (it ended
    and its row is written).  A BaseException, so that an arm's own runner, which catches Exception,
    cannot swallow it."""

    def __init__(self, where, avail_kb, min_kb, label=''):
        super().__init__('%s %s: MemAvailable %s under the limit %s'
                         % (label, where, fmt_gb(avail_kb), fmt_gb(min_kb)))
        self.where, self.avail_kb, self.min_kb, self.label = where, avail_kb, min_kb, label


# ---- readers of /proc (functions over text, so they run on Windows) ------------------------------

def parse_meminfo(text):
    """{'MemAvailable': kB, ...} from the text of /proc/meminfo (lines 'Name:   123 kB')."""
    out = {}
    for line in text.splitlines():
        name, sep, rest = line.partition(':')
        parts = rest.split()
        if sep and parts and parts[0].isdigit():
            out[name.strip()] = int(parts[0])
    return out


def mem_available_kb(path='/proc/meminfo'):
    try:
        with open(path, errors='replace') as f:
            return parse_meminfo(f.read()).get('MemAvailable')
    except OSError:
        return None


def status_kb(text, key='VmRSS'):
    """One kB value (VmRSS, VmHWM, ...) from the text of /proc/<pid>/status, None if the line is missing."""
    for line in text.splitlines():
        if line.startswith(key + ':'):
            parts = line.split(':', 1)[1].split()
            if parts and parts[0].isdigit():
                return int(parts[0])
    return None


def self_rss_kb(path='/proc/self/status'):
    try:
        with open(path, errors='replace') as f:
            return status_kb(f.read())
    except OSError:
        return None


def stat_fields(text):
    """{comm, state, ppid} from the text of /proc/<pid>/stat.  The command name sits in parentheses and may
    hold spaces and parentheses itself, so the fields after it are counted from the LAST ')'."""
    j, i = text.find('('), text.rfind(')')
    if j < 0 or i < j:
        return None
    rest = text[i + 1:].split()
    if len(rest) < 2:
        return None
    try:
        return {'comm': text[j + 1:i], 'state': rest[0], 'ppid': int(rest[1])}
    except ValueError:
        return None


def scan_stats(proc_root='/proc'):
    """{pid: {comm, state, ppid}} of every process whose /proc/<pid>/stat reads (one that vanishes is skipped)."""
    out = {}
    try:
        names = os.listdir(proc_root)
    except OSError:
        return out
    for n in names:
        if not n.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, n, 'stat'), errors='replace') as f:
                st = stat_fields(f.read())
        except OSError:
            continue
        if st:
            out[int(n)] = st
    return out


def rss_kb(pid, proc_root='/proc'):
    """VmRSS of a process in kB, 0 when it is gone or has none (a zombie)."""
    try:
        with open(os.path.join(proc_root, str(pid), 'status'), errors='replace') as f:
            return status_kb(f.read()) or 0
    except OSError:
        return 0


def below(stats, root_pid):
    """The pids below root_pid (children, grandchildren, ...) by the parent chain of one scan."""
    kids = {}
    for pid, st in stats.items():
        kids.setdefault(st['ppid'], []).append(pid)
    out, todo = [], list(kids.get(root_pid, []))
    while todo:
        p = todo.pop()
        out.append(p)
        todo.extend(kids.get(p, []))
    return sorted(out)


def snapshot_below(root_pid, proc_root='/proc'):
    """[{pid, comm, rss_kb}] of the living processes below root_pid."""
    stats = scan_stats(proc_root)
    return [{'pid': p, 'comm': stats[p]['comm'], 'rss_kb': rss_kb(p, proc_root)}
            for p in below(stats, root_pid) if stats[p]['state'] not in DEAD_STATES]


def ancestors(stats, pid):
    out = set()
    while pid in stats and pid not in out:
        out.add(pid)
        pid = stats[pid]['ppid']
    return out


def strays(proc_root='/proc', words=STRAY_WORDS, own_pid=None):
    """The processes of the machine that run a pipeline program (their command line holds one of the words),
    leaving out this process and its ancestors: [{pid, ppid, comm, rss_kb, cmd}].  Reporting only."""
    stats = scan_stats(proc_root)
    skip = ancestors(stats, os.getpid() if own_pid is None else own_pid)
    out = []
    for pid, st in sorted(stats.items()):
        if pid in skip or st['state'] in DEAD_STATES:
            continue
        try:
            with open(os.path.join(proc_root, str(pid), 'cmdline'), 'rb') as f:
                cmd = f.read().replace(b'\0', b' ').decode('utf-8', 'replace').strip()
        except OSError:
            continue
        if any(w in cmd for w in words):
            out.append({'pid': pid, 'ppid': st['ppid'], 'comm': st['comm'],
                        'rss_kb': rss_kb(pid, proc_root), 'cmd': cmd[:160]})
    return out


def shm_names(path='/dev/shm'):
    try:
        return set(os.listdir(path))
    except OSError:
        return set()


def rusage_children_kb():
    """The high-water mark of the children this process has waited for (kB on Linux), None without the
    resource module (Windows)."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    except (ImportError, OSError, ValueError):
        return None


# ---- one episode's record --------------------------------------------------------------------------

class EpisodeWatch:
    """Context manager around one episode: MemAvailable at the start, at every poll and at the end, the
    resident sets of the processes below this one at every poll, the children's high-water mark before
    and after.  as_row() is the row's `mem`.  The poll thread never ends an episode: its errors are dropped."""

    def __init__(self, min_avail_kb, peak_limit_kb, poll_s=POLL_S, root_pid=None, proc_root='/proc',
                 meminfo='/proc/meminfo', shm_path='/dev/shm', rusage=rusage_children_kb):
        self.min_avail_kb, self.peak_limit_kb, self.poll_s = min_avail_kb, peak_limit_kb, poll_s
        self.root_pid = os.getpid() if root_pid is None else root_pid
        self.proc_root, self.meminfo, self.shm_path, self.rusage = proc_root, meminfo, shm_path, rusage
        self.avail_start_kb = self.avail_end_kb = self.avail_min_kb = None
        self.peak_single_kb = 0
        self.group_peak_kb = 0
        self.polls = 0
        self.hwm_before = self.hwm_after = None
        self.peak_rss_kb, self.peak_exact = None, False
        self.batch_rss_kb = None
        self.leftover, self.shm_new = [], []
        self._shm_start, self._strays_start = set(), set()
        self._stop = threading.Event()
        self._thread = None

    def _seen(self, avail_kb):
        if avail_kb is not None and (self.avail_min_kb is None or avail_kb < self.avail_min_kb):
            self.avail_min_kb = avail_kb

    def sample(self):
        """One poll (public, so that a test can drive it without the thread)."""
        self._seen(mem_available_kb(self.meminfo))
        procs = snapshot_below(self.root_pid, self.proc_root)
        self.polls += 1
        if procs:
            self.group_peak_kb = max(self.group_peak_kb, sum(p['rss_kb'] for p in procs))
            self.peak_single_kb = max(self.peak_single_kb, max(p['rss_kb'] for p in procs))

    def _loop(self):
        while not self._stop.wait(self.poll_s):
            try:
                self.sample()
            except Exception:
                pass

    def __enter__(self):
        self.avail_start_kb = mem_available_kb(self.meminfo)
        self._seen(self.avail_start_kb)
        self._shm_start = shm_names(self.shm_path)
        self._strays_start = {s['pid'] for s in strays(self.proc_root, own_pid=self.root_pid)}
        self.hwm_before = self.rusage()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.avail_end_kb = mem_available_kb(self.meminfo)
        self._seen(self.avail_end_kb)
        self.hwm_after = self.rusage()
        rose = self.hwm_before is not None and self.hwm_after is not None and self.hwm_after > self.hwm_before
        self.peak_exact = bool(rose)
        self.peak_rss_kb = self.hwm_after if rose else (self.peak_single_kb or None)
        self.batch_rss_kb = self_rss_kb(os.path.join(self.proc_root, 'self', 'status'))
        self.leftover = [s for s in strays(self.proc_root, own_pid=self.root_pid)
                         if s['pid'] not in self._strays_start]
        self.shm_new = sorted(shm_names(self.shm_path) - self._shm_start)
        return False

    def over(self):
        return bool(self.peak_limit_kb) and self.peak_limit_kb > 0 and \
            max(self.peak_rss_kb or 0, self.group_peak_kb or 0) > self.peak_limit_kb

    def low(self):
        return low_memory(self.avail_min_kb, self.min_avail_kb)

    def as_row(self):
        return {'avail_start_kb': self.avail_start_kb, 'avail_end_kb': self.avail_end_kb,
                'avail_min_kb': self.avail_min_kb, 'peak_rss_kb': self.peak_rss_kb,
                'peak_exact': self.peak_exact, 'children_hwm_kb': self.hwm_after,
                'group_peak_kb': self.group_peak_kb, 'polls': self.polls,
                'batch_rss_kb': self.batch_rss_kb, 'leftover': self.leftover,
                'shm_new': self.shm_new, 'min_avail_limit_kb': self.min_avail_kb,
                'peak_limit_kb': self.peak_limit_kb, 'peak_over_limit': self.over()}

    def end_lines(self, label):
        """The log lines for the end of the episode."""
        lines = ['mem %s end: MemAvailable %s (lowest %s), peak RSS %s%s, process sum peak %s%s'
                 % (label, fmt_gb(self.avail_end_kb), fmt_gb(self.avail_min_kb), fmt_gb(self.peak_rss_kb),
                    '' if self.peak_exact else ' (at a poll)', fmt_gb(self.group_peak_kb),
                    ', OVER %.0f GB (report it)' % (self.peak_limit_kb / KB_PER_GB) if self.over() else '')]
        if self.leftover:
            lines.append('mem %s LEFTOVER (reported, not ended): %s' % (
                label, ', '.join('pid %d %s %s' % (p['pid'], p['comm'], fmt_gb(p['rss_kb'])) for p in self.leftover)))
        if self.shm_new:
            lines.append('mem %s NEW in /dev/shm during the episode: %s' % (label, self.shm_new))
        return lines


def row_fields(mem):
    """What an episode row takes from the episode's record: `mem` and the flag `peak_over_6gb`."""
    return {'mem': mem, 'peak_over_6gb': bool((mem or {}).get('peak_over_limit'))}


# ---- the stop ---------------------------------------------------------------------------------------

def stop_line(e):
    return 'STOPPED_LOW_MEMORY: %s' % e


def write_stop(out_dir, e, extra=''):
    """Print the STOPPED_LOW_MEMORY line and write out_dir/STOPPED_LOW_MEMORY.txt; returns the path."""
    line = stop_line(e)
    print('[mem] ' + line, flush=True)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, STOP_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(line + '\n')
        f.write(time.strftime('%Y-%m-%d %H:%M:%S') + '  where %s  label %s  MemAvailable %s kB  limit %s kB\n'
                % (e.where, e.label, e.avail_kb, e.min_kb))
        if extra:
            f.write(extra + '\n')
    return path


# ---- the batch's lines (for a report) ----------------------------------------------------------------

def summary_lines(records):
    """Memory lines from records, each a dict with `mem` (and optionally `label`): the lowest MemAvailable, the
    biggest peaks, the process's own growth, and every flagged, leftover or /dev/shm episode."""
    ms = [(r, r['mem']) for r in records if r.get('mem')]
    if not ms:
        return ['memory: no episode recorded']

    def vals(key):
        return [m[key] for _, m in ms if m.get(key) is not None]

    def lo(key):
        v = vals(key)
        return min(v) if v else None

    def hi(key):
        v = vals(key)
        return max(v) if v else None
    lines = ['memory: %d episodes recorded; lowest MemAvailable %s (any reading), lowest at an episode end %s; '
             'highest peak RSS of one process %s, highest process sum %s; the harness process %s to %s'
             % (len(ms), fmt_gb(lo('avail_min_kb')), fmt_gb(lo('avail_end_kb')), fmt_gb(hi('peak_rss_kb')),
                fmt_gb(hi('group_peak_kb')), fmt_gb(lo('batch_rss_kb')), fmt_gb(hi('batch_rss_kb')))]
    for r, m in ms:
        who = r.get('label') or r.get('tag') or '?'
        if r.get('peak_over_6gb') or m.get('peak_over_limit'):
            lines.append('memory: OVER the peak limit: %s, peak RSS %s, process sum %s'
                         % (who, fmt_gb(m.get('peak_rss_kb')), fmt_gb(m.get('group_peak_kb'))))
        if m.get('leftover'):
            lines.append('memory: %s left %d pipeline process(es) behind (reported, not ended): %s'
                         % (who, len(m['leftover']), [(p.get('pid'), p.get('comm')) for p in m['leftover']]))
        if m.get('shm_new'):
            lines.append('memory: %s: new in /dev/shm: %s' % (who, m['shm_new']))
    return lines


def append_jsonl(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec) + '\n')


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    except OSError:
        pass
    return out


# ---- the tabletop runner's guard ----------------------------------------------------------------------

def install_run_cell_guard(er, out_dir, min_avail_kb, peak_limit_kb, log=print, poll_s=POLL_S, **watch_kw):
    """Wrap `run_cell` of an arm's own eval_runner module (its main loop calls it through the module's
    global name, so the thesis commit's file stays unedited): before a cell MemAvailable is read and, under
    the limit, nothing starts (LowMemory); around a cell an EpisodeWatch records `mem`; each cell's record goes
    to out_dir/mem_cells.jsonl and its lines to the log; after a cell whose lowest reading was under the limit
    LowMemory is raised, once the cell's own summary is on disk.  A cell the runner skips (--skip-existing,
    its summary is banked) is not an episode and is not recorded.  Returns the wrapper."""
    orig = er.run_cell
    jsonl = os.path.join(out_dir, 'mem_cells.jsonl')

    def guarded(cell, sweep_dir, timeout_s, extra_args, skip_existing):
        tag = er.cell_tag(cell)
        if skip_existing and os.path.exists(os.path.join(str(sweep_dir), 'cells', tag, 'timing_summary.json')):
            return orig(cell, sweep_dir, timeout_s, extra_args, skip_existing)
        avail = mem_available_kb(watch_kw.get('meminfo', '/proc/meminfo'))
        if low_memory(avail, min_avail_kb):
            raise LowMemory('start', avail, min_avail_kb, tag)
        log('mem %s start: MemAvailable %s' % (tag, fmt_gb(avail)))
        w = EpisodeWatch(min_avail_kb, peak_limit_kb, poll_s=poll_s, **watch_kw)
        t0 = time.time()
        with w:
            row = orig(cell, sweep_dir, timeout_s, extra_args, skip_existing)
        append_jsonl(jsonl, dict({'tag': tag, 'started_epoch': round(t0, 3), 'ended_epoch': round(time.time(), 3)},
                                 **row_fields(w.as_row())))
        for line in w.end_lines(tag):
            log(line)
        if w.low():
            raise LowMemory('end', w.avail_min_kb, min_avail_kb, tag)
        return row
    er.run_cell = guarded
    return guarded
