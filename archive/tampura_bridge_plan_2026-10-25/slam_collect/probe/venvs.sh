#!/bin/bash
# Read-only: package versions in arm T's and arm O's venvs (prints only).
for py in /root/tampura-work/.venv/bin/python /root/armO-venvA/bin/python; do
  echo "== $py"
  [ -x "$py" ] || { echo "missing"; continue; }
  "$py" -B -c "
import importlib
for m in ['numpy', 'matplotlib', 'imageio', 'scipy']:
    try:
        mod = importlib.import_module(m)
        print(m, getattr(mod, '__version__', '?'))
    except Exception as e:
        print(m, 'MISSING', type(e).__name__)
"
done
