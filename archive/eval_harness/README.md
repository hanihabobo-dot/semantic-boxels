# Archived copies of the eval harness

`tools/_eval_ab.py` stays untracked on purpose: a tracked harness would be
deleted by `git checkout <old-sha>` in the middle of an eval. These are
byte copies, kept for reproducibility. The `.txt` suffix means nothing
imports or runs them. To use one, copy it to `tools/_eval_ab.py`. A
Windows checkout may write CRLF line endings; for the exact bytes behind
each hash, take the blob with `git show HEAD:archive/eval_harness/<file>`.

| file | sha256 (first 8) | used by |
|---|---|---|
| `_eval_ab.036a2634.py.txt` | 036a2634 | the cluster runs of BF#14 (blob `6fb4b80:tools/_eval_ab.py`) |
| `_eval_ab.56d211c4.py.txt` | 56d211c4 | the live file of 30 Oct 2026; it adds `--log-level normal` to the pipeline command, with the same parse rules |

The listing in `.claude/skills/eval/SKILL.md` is the 56d211c4 version.
Bug board: TB-43.
