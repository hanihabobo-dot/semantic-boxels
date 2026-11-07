"""Write M8's generated domain (m8_domain.GENERATED_FILE) from the live
pddl/domain_pddlstream.pddl plus M8's declared delta (m8_domain.EDITS,
OBSERVE_ACTION).  The live file is never written.  With --look, write the
look-mode domain (look_domain.GENERATED_FILE) instead: M8's domain with the
look delta (path 9).

  python tools/gen_bridge_domain.py                 write M8's file
  python tools/gen_bridge_domain.py --check         exit 1 if it is missing or stale
  python tools/gen_bridge_domain.py --look          write the look-mode file
  python tools/gen_bridge_domain.py --look --check  exit 1 if it is missing or stale
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import look_domain  # noqa: E402
import m8_domain  # noqa: E402


def main():
    look = '--look' in sys.argv[1:]
    mod = look_domain if look else m8_domain
    text = mod.generate(mod.read(mod.LIVE_FILE))
    if '--check' in sys.argv[1:]:
        ok = (os.path.isfile(mod.GENERATED_FILE)
              and mod.read(mod.GENERATED_FILE) == text)
        print(f"{'up to date' if ok else 'MISSING OR STALE'}: "
              f"{mod.GENERATED_FILE} sha {mod.sha(text)[:16]}")
        sys.exit(0 if ok else 1)
    with open(mod.GENERATED_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f"wrote {mod.GENERATED_FILE} sha {mod.sha(text)[:16]}")


if __name__ == '__main__':
    main()
