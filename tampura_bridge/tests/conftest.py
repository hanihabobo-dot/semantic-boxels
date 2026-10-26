"""pytest set-up for tampura_bridge/tests: the repository root on sys.path.
Nothing on the campaign path imports this folder (G1 asserts it)."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
