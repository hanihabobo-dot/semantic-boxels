"""Write M8's generated domain (m8_domain.GENERATED_FILE) from the live
pddl/domain_pddlstream.pddl plus M8's declared delta (m8_domain.EDITS,
OBSERVE_ACTION).  The live file is never written.  With --look, write the
boxel look's domain (look_domain.GENERATED_FILE) instead: M8's domain with the
look delta (path 9); with --look-centred, the object-centred look's
(look_domain.CENTRED_FILE).

  python tools/gen_bridge_domain.py                 write M8's file
  python tools/gen_bridge_domain.py --check         exit 1 if it is missing or stale
  python tools/gen_bridge_domain.py --look          write the boxel look's file
  python tools/gen_bridge_domain.py --look --check  exit 1 if it is missing or stale
  python tools/gen_bridge_domain.py --look-centred [--check]   the same for the centred look
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import look_domain  # noqa: E402
import m8_domain  # noqa: E402


def main():
    argv = sys.argv[1:]
    mode = 'centred' if '--look-centred' in argv else 'boxel' if '--look' in argv else None
    if mode is None:
        text = m8_domain.generate(m8_domain.read(m8_domain.LIVE_FILE))
        path, sha = m8_domain.GENERATED_FILE, m8_domain.sha
        rd = m8_domain.read
    else:
        text = look_domain.generate(look_domain.read(look_domain.LIVE_FILE), mode)
        path, sha = look_domain.GENERATED_FILES[mode], look_domain.sha
        rd = look_domain.read
    if '--check' in argv:
        ok = os.path.isfile(path) and rd(path) == text
        print(f"{'up to date' if ok else 'MISSING OR STALE'}: {path} sha {sha(text)[:16]}")
        sys.exit(0 if ok else 1)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f"wrote {path} sha {sha(text)[:16]}")


if __name__ == '__main__':
    main()
