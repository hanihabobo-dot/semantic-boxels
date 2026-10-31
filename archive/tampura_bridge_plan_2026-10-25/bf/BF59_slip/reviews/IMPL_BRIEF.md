# BF#59 implementation brief (phase 5): one fix, one worktree, one branch

Written 2026-10-31 by the orchestrating session. You implement ONE fix of
the candidate list in STATE.md, in the worktree the orchestrator created
for it. Read, in this order: BRIEF.md (the problem, the code map, section
4 how to run, section 5 the rules), STATE.md (the candidate list: your
fix's mechanism, its dependencies, the arm it will run in), the proposal
that defined your fix (proposals/<angle>.md, the fix's subsection: the
exact change) and its review (reviews/<angle>.md: what the reviewer
required changed), then the code.

## 1. Where you work

- Your worktree: `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-<name>` (in
  WSL `/mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-<name>`), branch
  `slip/<name>`, created by the orchestrator from tampura-bridge at the
  base commit STATE.md names. Edit ONLY there: never the main checkout,
  never their tree under /root/tampura-work, never another fix's
  worktree. The worktree is a sibling of the main checkout, so
  `../pddlstream_lib` resolves there as it does in the main checkout.
- Git: Windows git only (`git -C <worktree> ...` from PowerShell; WSL git
  cannot follow a worktree's gitdir and must not be used). Stage by path
  (`git add -- <file>`), commit on `slip/<name>` with a one-line subject
  `BF#59 <name>: <what>`, no body, no trailer, never push. Several
  commits are fine.
- Python runs in WSL with arm O's venv (BRIEF.md section 4, with `$S`
  your worktree's WSL path). Every episode run and every pytest run that
  plans goes through `flock /root/sb_pipeline.lock`; the campaign's check
  script (section 3) does that for you. Inside `wsl -e bash -lc '...'`
  never put double quotes (they are stripped): write a script file.

## 2. What a fix is

1. The switch: `import slip_fixes` and
   `slip_fixes.register('<name>', '<one line>')` at the top level of the
   module where the behaviour lives (registered at import, before main()
   configures the run), and `if slip_fixes.on('<name>'):` at the one
   point (or the few points) where the behaviour differs. With the switch
   off the pipeline behaves exactly as before: the same code path, the
   same numbers, the same log lines. The name is fixed by STATE.md; a fix
   that needs two switches asks the orchestrator first.
2. Physics settings (solver iterations, constraints, motor budgets,
   friction) are pipeline-wide: the bridge's executing world
   (`tampura_bridge/policy.py` `d9_setup`) and our own world
   (`boxel_env.py`); the switch decides in both places the same way.
3. Gates: `setPhysicsEngineParameter`, every other pybullet write and
   every read of the executing world are gated (`tools/bridge_gates.py`
   from line 91, `tampura_bridge/gate_hooks.py` from line 99). Run
   `tools/bridge_gates.py static`; a new write needs a line in
   `tools/bridge_gates_allowlist.txt` with the reason; a read of a task
   body's truth that feeds control is forbidden (BRIEF.md section 5 rule
   3), the cameras, the joint readback and the pad contacts are the
   senses.
4. Logging: the fix logs what it decided per pick or carry (one line
   through the run's logger, prefixed with the fix's name) so the eval
   can tell affected episodes from unaffected ones and a null result is
   informative. The eval counts carries and losses from the lines
   "firm grip on dice", "grip lost after post-pick lift for dice",
   "PHYSICAL_FAILURE (goal): (holding dice)" and "Picking dice": do not
   change those lines.
5. Tests: `tests/test_slip_<name>.py` with (a) the name registered and off
   by default, the base behaviour unchanged with it off; (b) with it on,
   the behaviour at the unit level (a function on a small world or a
   stub, not a full episode); (c) every invariant the review asked for.
   The existing suites must stay green (`pytest tests -q` in the
   worktree, the bridge tests from their tampura_environments cwd).
6. Narration comments stay; new code gets the same kind (what and why,
   the BF#59 reference and the proposal's number where a constant comes
   from). Prose: no em dashes anywhere, never "faithful", plain voice.

## 3. The check, before you report

From the MAIN checkout's tools (the same script on every branch; the main
checkout's copy so every fix is checked the same way), with the fix on,
then off:

    wsl -e bash -lc 'bash /mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/tools/slip_check.sh /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-<name> 0 <name>'
    wsl -e bash -lc 'bash /mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/tools/slip_check.sh /mnt/c/Users/HaniAlassiriAlhabbou/git/sb-slip-<name> 0'

Each run: the unit tests, the bridge tests, the static gates, one seed-0
episode (the same scene everywhere, about 10 s of planning), outputs
under your worktree's `archive/.../BF59_slip/checks/<stamp>/`. Both must
be green: tests passed, gates PASS, the episode's outcome success, the
run record's "slip_fixes" naming your fix (empty for the base run). If
your fix touches the carry or the hold, also run one episode of a seed
where the base lost the die (laptop seeds 1 and 6, with
`--allow-g19-mismatch 1`, under the lock, the fix on) and report the
outcome, knowing one episode is a coin flip. If your fix changes the step
time, report the episode's wall and steps against the base run's.

## 4. The report

`reviews/impl_<name>.md` in the MAIN checkout's campaign folder
(`C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels\archive\
tampura_bridge_plan_2026-10-25\bf\BF59_slip\reviews\impl_<name>.md`,
untracked, the orchestrator commits it), written at the start and filled
as you go: the branch and its commits (hashes, subjects); the files and
functions changed with line numbers; what the switch does on and off;
where the fix logs; the tests and their result; the check outputs (the
checks/<stamp> paths, the test counts, the gates, the episodes' outcomes
and times); deviations from the proposal and why (the review's
requirements); open questions for the implementation reviewer; the data
you generated (paths, sizes) and deleted. Your return value: ten lines
(the commits, the check results, the deviations).

## 5. The rules, again (BRIEF.md section 5)

Model side, never a plan edit; pipeline-wide or TAMPURA-matched, no
bridge-only tuning; no truth reads feeding control; one switch, default
off; honest naming; narration comments kept; never commit on
tampura-bridge, never push, never touch their tree; data under the
campaign folder, listed with sizes, garbage deleted by you by path; never
kill a process that is not yours (Hani may run the GUI); the lock for
every episode.
