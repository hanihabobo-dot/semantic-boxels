"""Review check (REVIEW.md): recompute the tracked-tree sha256 of TAMPURA's two
repos the way tools/bridge_gates.py tree_state() does (bridge_gates.py:598-609:
sorted `git ls-files`, each name then the sha256 digest of its bytes), to compare
with the prefixes ARGUMENT.md 4.5 quotes.  Reads only; writes nothing but stdout.

Run: python3 rp_tree_hash.py
"""
import hashlib
import os
import subprocess

TW = "/root/tampura-work"
for repo in ("tampura", "tampura_environments"):
    path = os.path.join(TW, repo)
    files = subprocess.run(["git", "-C", path, "ls-files", "-z"], check=True,
                           capture_output=True, text=True).stdout.split("\0")
    h = hashlib.sha256()
    for f in sorted(x for x in files if x):
        h.update(f.encode())
        fp = os.path.join(path, f)
        if os.path.isfile(fp):
            with open(fp, "rb") as fh:
                h.update(hashlib.sha256(fh.read()).digest())
    status = subprocess.run(["git", "-C", path, "status", "--porcelain",
                             "--untracked-files=no"], check=True,
                            capture_output=True, text=True).stdout.strip()
    print(f"{repo}: tracked_sha256 {h.hexdigest()}  modified: {status or 'none'}")
