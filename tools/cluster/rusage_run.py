#!/usr/bin/env python3
"""Run one command and record what it cost: wall time, CPU time, peak memory, file reads.

  rusage_run.py <out.json> <timeout s> <console file> -- <command> [args ...]

The command runs with this process's environment and working directory, its output goes to the
console file, and <out.json> gets: rc, timed_out, wall_s, and from the kernel's accounting of the
child (resource.getrusage, RUSAGE_CHILDREN): user_s, sys_s, max_rss_kb, inblock (blocks read from
a file system: 0 means everything came from the page cache), oublock, majflt, minflt; beside them
the load average and MemAvailable at the start and the end and the page cache's size at the start.
The same numbers `/usr/bin/time -v` prints, without needing that program on the node.

A command past the timeout is ended with its own process group (the processes this script
started, nothing else) and recorded as timed_out.  The exit code of this script is 0 whatever the
command returned: the record says what happened.
"""
import json
import os
import signal
import subprocess
import sys
import time

try:
    import resource
except ImportError:                     # Windows: the tests run there without the accounting
    resource = None


def meminfo_kb(key, path='/proc/meminfo'):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith(key + ':'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def loadavg(path='/proc/loadavg'):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [float(x) for x in f.read().split()[:3]]
    except (OSError, ValueError):
        return None


def children_usage():
    if resource is None:
        return None
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'user_s': r.ru_utime, 'sys_s': r.ru_stime, 'max_rss_kb': r.ru_maxrss, 'inblock': r.ru_inblock,
            'oublock': r.ru_oublock, 'majflt': r.ru_majflt, 'minflt': r.ru_minflt}


def usage_delta(before, after):
    """The child's share: the counters are sums over all children so far, the peak is a maximum."""
    if before is None or after is None:
        return {k: None for k in ('user_s', 'sys_s', 'max_rss_kb', 'inblock', 'oublock', 'majflt', 'minflt')}
    out = {k: after[k] - before[k] for k in after if k != 'max_rss_kb'}
    out['user_s'], out['sys_s'] = round(out['user_s'], 3), round(out['sys_s'], 3)
    out['max_rss_kb'] = after['max_rss_kb']
    return out


def split_argv(argv):
    if '--' not in argv or argv.index('--') != 3 or len(argv) < 5:
        raise SystemExit('usage: rusage_run.py <out.json> <timeout s> <console file> -- <command> [args ...]')
    return argv[0], float(argv[1]), argv[2], argv[4:]


def run(out_json, timeout_s, console, cmd):
    rec = {'cmd': cmd, 'cwd': os.getcwd(), 'timeout_s': timeout_s, 'start': time.strftime('%Y-%m-%dT%H:%M:%S'),
           'load_start': loadavg(), 'memavailable_kb_start': meminfo_kb('MemAvailable'),
           'cached_kb_start': meminfo_kb('Cached')}
    before = children_usage()
    t0 = time.perf_counter()
    timed_out = False
    with open(console, 'w', encoding='utf-8', errors='replace') as con:
        proc = subprocess.Popen(cmd, stdout=con, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, AttributeError):
                proc.kill()
            rc = proc.wait()
    rec.update(wall_s=round(time.perf_counter() - t0, 3), rc=rc, timed_out=timed_out,
               end=time.strftime('%Y-%m-%dT%H:%M:%S'), load_end=loadavg(),
               memavailable_kb_end=meminfo_kb('MemAvailable'))
    rec.update(usage_delta(before, children_usage()))
    tmp = out_json + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rec, f, indent=1)
    os.replace(tmp, out_json)
    return rec


def main(argv=None):
    out_json, timeout_s, console, cmd = split_argv(sys.argv[1:] if argv is None else argv)
    rec = run(out_json, timeout_s, console, cmd)
    print(f"rc {rec['rc']}{' (timeout)' if rec['timed_out'] else ''}  wall {rec['wall_s']} s  user {rec['user_s']} s  "
          f"sys {rec['sys_s']} s  peak RSS {rec['max_rss_kb']} kB  blocks read {rec['inblock']}  "
          f"major faults {rec['majflt']}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
