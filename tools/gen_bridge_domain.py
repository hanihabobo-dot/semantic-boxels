"""Write M8's generated domain (m8_domain.GENERATED_FILE) from the live
pddl/domain_pddlstream.pddl plus M8's declared delta (m8_domain.EDITS,
OBSERVE_ACTION), and (BF#52) M8's generated stream file
(m8_domain.STREAM_GENERATED_FILE) from the live pddl/stream.pddl plus the
test-sense-view stream (m8_domain.SENSE_VIEW_STREAM).  The live files are
never written.

  python tools/gen_bridge_domain.py          write both files
  python tools/gen_bridge_domain.py --check  exit 1 if either is missing or stale
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import m8_domain  # noqa: E402


def main():
    pairs = ((m8_domain.GENERATED_FILE,
              m8_domain.generate(m8_domain.read(m8_domain.LIVE_FILE))),
             (m8_domain.STREAM_GENERATED_FILE,
              m8_domain.generate_stream(m8_domain.read(m8_domain.STREAM_LIVE_FILE))))
    if '--check' in sys.argv[1:]:
        ok = True
        for path, text in pairs:
            good = os.path.isfile(path) and m8_domain.read(path) == text
            ok = ok and good
            print(f"{'up to date' if good else 'MISSING OR STALE'}: "
                  f"{path} sha {m8_domain.sha(text)[:16]}")
        sys.exit(0 if ok else 1)
    for path, text in pairs:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        print(f"wrote {path} sha {m8_domain.sha(text)[:16]}")


if __name__ == '__main__':
    main()
