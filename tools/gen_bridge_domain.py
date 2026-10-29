"""Write M8's generated domain (m8_domain.GENERATED_FILE) from the live
pddl/domain_pddlstream.pddl plus M8's declared delta (m8_domain.EDITS,
OBSERVE_ACTION).  The live file is never written.

  python tools/gen_bridge_domain.py          write the file
  python tools/gen_bridge_domain.py --check  exit 1 if it is missing or stale
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import m8_domain  # noqa: E402


def main():
    text = m8_domain.generate(m8_domain.read(m8_domain.LIVE_FILE))
    if '--check' in sys.argv[1:]:
        ok = (os.path.isfile(m8_domain.GENERATED_FILE)
              and m8_domain.read(m8_domain.GENERATED_FILE) == text)
        print(f"{'up to date' if ok else 'MISSING OR STALE'}: "
              f"{m8_domain.GENERATED_FILE} sha {m8_domain.sha(text)[:16]}")
        sys.exit(0 if ok else 1)
    with open(m8_domain.GENERATED_FILE, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f"wrote {m8_domain.GENERATED_FILE} sha {m8_domain.sha(text)[:16]}")


if __name__ == '__main__':
    main()
