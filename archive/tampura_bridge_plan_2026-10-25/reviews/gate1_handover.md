# Review gate 1: hand-over (2026-10-27)

Written by the Claude session that ran B3, B1 part 2, B2 and review gate 1 on
branch `tampura-bridge`, stopped at the user's request before recording the gate.
Read PAPER_AUDIT.txt section #P4 (P4.0 to P4.10, the BF# entries in P4.14) before
touching anything.

## State

- Branch `tampura-bridge`, HEAD `18be9d2`, local only. Never push without Hani's
  explicit approval for that push.
- Nothing uncommitted from this work. PAPER_AUDIT.txt's only working-tree change
  is Hani's own hunk near line 771: never stage it (method below).
- The four gate reports are complete and untracked:
  `archive/tampura_bridge_plan_2026-10-25/reviews/gate1_{cheat,pod,validity,feasibility}.json`.
  All four say "revise". Counts (blocker/major/minor): cheat 0/3/7, POD 0/2/7,
  validity 0/6/10, feasibility 1/6/5. Feasibility was read by title only.
- Gate 1 is not recorded yet. That is the next step.

## Rules that bind this work (CLAUDE.md, memory, the task)

- Shell: PowerShell only. Never Git Bash (it crashes this machine). Windows git
  only, never WSL git. WSL Python is fine: `wsl -e /root/...` style, scripts in
  files, outputs on the Windows side (WSL /tmp is wiped between calls).
- Never stash, reset, switch branches or use worktrees in this checkout. Stage
  paths explicitly. Never stage `emails and pdfs/`.
- Commits: one per BF# entry, a single one-line subject, no Co-Authored-By trailer.
- Prose: no em dashes; never the word "faithful".
- Run `python tools/bridge_gates.py all` with the WSL `wsl_env/bin/python`
  before every bridge commit.
- Cluster (i6): `ssh -o BatchMode=yes cn-04` (key i6_ed25519), partition
  rleap_cpu, `sbatch -w cn-110`, layout `/work/rleap1/hani.alassiri.alhabboub/p4`.
  PowerShell eats `$` in ssh strings: pipe scripts as
  `$s | ssh -o BatchMode=yes cn-04 "tr -d '\r' | bash -s"`. Strip other users'
  rows from Slurm logs before committing them (the GitHub remote is public).

## Committing PAPER_AUDIT.txt without Hani's hunk

Make a diff of PAPER_AUDIT.txt, drop the hunk whose old-side start is line 768
(Hani's own hunk), correct the new-side starts of the later hunks for the lines
that hunk added, `git apply --cached` the result, then check `git diff --cached`
before committing. The script used so far:
`C:\Users\HANIAL~1\AppData\Local\Temp\claude\C--Users-HaniAlassiriAlhabbou-git-Semantic-Boxels\e5e85307-4209-4b32-8c64-922545c8e7dc\scratchpad\filter_patch.ps1`
(read it first; if it is gone, redo the method by hand).

## Next step 1: record gate 1 as BF#14

- Format: P4.7 (PAPER_AUDIT.txt:4542). Style: the critique logs of P4.11
  (PAPER_AUDIT.txt:4704), one line per merged finding:
  `<id> [severity, lenses] finding. ACCEPTED / ACCEPTED IN PART / REJECTED: why; fix in BF#n, before B4 or before B7.`
- Place: after BF#13, which ends at PAPER_AUDIT.txt:6022, before the `#P5.` banner.
- Also: BF#12 (header at :5894, "[DONE, review gate 1 pending]") gets a
  correction line; B2's header in P4.4 (:4031) goes back to OPEN until the
  before-B4 fixes land, because B2's deliverable (:4063) lists G2, G13, G18 and
  G19 green and parts of all four do not exist.
- Commit BF#14 with the four JSON files and this note.

## Claims checked against the code (this session)

1. Arm T imports the site-packages copy of tampura
   (`bf/BF7_b1j/p4-setup-armT_4940009.txt:146`); `tree_state()` hashes only the
   two checkouts and the pip freeze (`tools/bridge_gates.py:461-492`); G13's text
   promises every loaded tampura module lies inside the hashed trees
   (PAPER_AUDIT.txt:3441), which arm T would fail today.
2. G13's runtime half (two registrations, `Policy.rollout` identity, the timed
   class's `__dict__`, no `step` attribute on the env, `__file__`) has no code;
   `run_bridge_on_finddice.py:80-95` asserts only G19's scene map; the T-driver
   check compares lines as a set (`bridge_gates.py:549-552`).
3. The G6 controls are stubs (`tampura_bridge/tests/test_g6_controls.py:19-23`);
   no arm readback is logged at main() return.
4. `execute_fn` swallows every exception and returns a conf-only observation
   (`tampura_bridge/policy.py:190-207`); the exit code is `rewards[-1]` alone
   (`run_bridge_on_finddice.py:104`).
5. Stale text: D9 "12 of 20" (PAPER_AUDIT.txt:3915), P4.6 "12 of 20" (:4520),
   "every cup partly out of frame" (:4524-4525), the in-frame column
   (:4464-4465). The campaign map gives 15 of 20 (`bridge_gates.py:90-92`).
6. BF#11 (:5856-5880): the payload stayed in the pads in 5 of 96 trials, the cap
   52 comes from the empty-hand trials, the die loss is deferred to B7 with no
   pre-registered rule.
7. G2's leak test is specified (:3326-3329) and exists nowhere; allowlist lines
   44-45 cite it.
8. D7 (vi): `_loop_done` (`test_full_pipeline.py:1338-1348`) ends on the held
   flag plus `at_home_ok`; nothing checks the grip after the move to q_home
   (:1777-1835). Scoring reads contacts, so a dropped die scores 0.0, never a
   false 1.0: the defect is a loop ending on a stale literal.
9. M3 is one sentence with no H3 lines (:4322-4324).
10. `report_run_outcome` has no `home_not_reached` branch and prints the
    wall-clock message (`run_logger.py:546`).
11. M1's CLAIM EFFECT cites BF#2 (:4286-4287); the measurement is BF#11 (h).
12. `set_phase('main')` comes only after the env adapter is built
    (`policy.py:164-174`), so the setup exemption covers the adapter build.
13. BF#10 re-runs (`bf/BF10_b3/acceptance_report.json`, `rerun.per_seed`): seed
    116 ab `[[true,6],[true,3]]`, rerun `[[false,8],[true,6]]`; seed 10 ab
    `[[true,3],[true,1]]`, rerun `[[true,2],[false,4]]`. The validity reviewer
    reads 116 as a second new difference (c31cbdd fails, B3 succeeds); confirm
    the pair order in `tools/b3_acceptance_report.py` before writing it.
14. BF#4 (c)'s die numbers (tilt 21 deg and 0.069 m/s residual motion in
    1747173591; 49.8 deg in 1747173593) are at PAPER_AUDIT.txt:5373-5389.

## Draft dispositions (the executor's draft, not yet recorded)

Before B4 (gate 1 closes when these land, each its own BF# and commit):

- D1. G13 runtime assertions in both drivers right before rollout, recorded,
  stopping the run on failure; the T-driver check becomes an ordered diff of the
  whole file minus the docstring and the one import; also assert
  `type(env).sync_to_plan_client is BoxelTestEnv.sync_to_plan_client`.
- D2. G13 hashes the tampura package in arm T's venv (and armO-venvA's, if it
  has one) and requires its files to equal the checkout's byte for byte; run it
  once on the cluster now, which covers B1(g) if the freeze hash is unchanged.
- D3. G2: the leak test's pre-planning half now (seeds 0 and 1,
  stop_before_planning, write-only values replaced by noise and tactile
  non-robot ids permuted; registry, boxels and casts identical); its planning
  half pre-registered to run with B7's headless episodes, so B7 stays the first
  planned episodes; `ObjectInfo.position` a raising property in
  TampuraWorldEnv (G16); the AST scan flags any Load of a G1/G2 name on p or
  pybullet and string constants of those names; allowlist gate_hooks' own reads.
- D4. G6 controls: die hold gives 1.0, cup hold gives 0.0, die hold 2e-3 rad
  off DEFAULT_ARM_POS gives 0.0; the readback at main() return logged and
  compared bit for bit; the pickle round trip of an arm O history in arm T's
  venv. Faults (3) to (5) stay with B7.
- D5. G18 and G19's seed hygiene in the ledger reader (the driver stamps
  initialize-return and rollout-start); reword G18 to allow the pinned-map load
  and the G19 assertion.
- D6. `set_phase('main')` (or an 'adapter' phase with no allowance) right after
  `d9_setup`.
- D7. G8(c) also asserts the identity quaternion of non-static twins and the
  held twin at the EE; measure the YCB twin offset (create_ycb puts the base at
  the mesh's centre of mass; POD suspicion) and compensate or compare AABB
  centres.
- D8. `boxel_data.json`: run main() from arm O's run directory and change back;
  G13 flags untracked files outside runs/, temp/, logs/, __pycache__. The B2
  smoke left one in `/root/tampura-work/tampura_environments`: check it is ours,
  then remove it.

Record fixes (fine inside BF#14's commit):

- R1. BF#12 correction line (green covered G2's grep, G13's tree, status,
  freeze and T-driver checks and G19's scene map only; G18 held by inspection).
- R2. D9 and P4.6: 15 of 20 on the campaign map (12 on the laptop map); the
  die's fall, tilt and residual motion; the belief-posed shadow cast (R6 at
  :4596-4597 already says it is disclosed); "partly out of frame" becomes fully
  in frame, provisional until the inertia re-measure (BF#12 (4)).
- R3. M3 gets BEFORE / AFTER / CLAIM EFFECT (POD's draft in gate1_pod.json;
  check its methods.tex line references 84, 188, 198, 199, 211 first); D7 on is
  model tweak M3; the claim ledger's find_dice-only sentence adds M3; P4.6
  lists the naming rule beside at-home strictness.
- R4. BF#10: the second re-run difference (item 13); the per-arm tallies
  (validity's numbers, check against `bf/BF10_b3/diag/*.json`); the
  "timed-out plan() calls" clause implemented before B5 or struck.
- R5. Record the sha256 of `tools/_eval_ab.py` and of its cluster copies; have
  `acceptance_dist.sbatch` print it. Do not commit `_eval_ab.py` (Hani's
  untracked file) without asking.
- R6. M1 cites BF#11 (h).
- R7. D10: say the 900 s process cap is the only bound (symmetric with arm T),
  or implement the clip (feasibility also raises D10).
- R8. P4.6: an arm O episode with `error` in bridge_episode.json is a crash,
  censored at the cap and flagged; one outcome field combines `rewards[-1]`,
  the error and the G21 counts.
- R9. P4.6 TIME: O's set-up is on its clock, T's initialize() is not; report
  O's set-up share as its own column.
- R10. P4.6 COMMANDS: the campaign passes --save-dir and never --vis to the T
  driver.
- R11. A new PAPER_AUDIT finding against the thesis pipeline: plans certify
  moves while holding with the cargo at the approach offset (POD minor).
- R12. Record that B2 and B1 part 2 landed while Q13 was open (answered in
  18be9d2).

Before B7 (with B4 to B6, reviewed by gate 2):

- The die loss: diagnose on the empty table; pre-register now (a main-pipeline
  remedy through the B3 acceptance with BF#13's test; if none holds, Hani
  decides before B7, as in D11 (iii)). Feasibility calls this a blocker because
  no package or calendar slot owns it: give it one.
- HOME_HOLD_STEP_CAP re-measured with a payload that stays in the pads, plus
  the pass's persistence (cheat minor), before B6 freezes it.
- D7 (vi) tactile check after every move while holding, a mid-plan at-home
  miss ends the plan (`stale_precondition`), and the `home_not_reached` report
  branch: one main-pipeline change, default off, B3 acceptance with BF#13's test.
- auto_cell from the declared class (B6); G10's install accepts only the live
  or regenerated domain hash (with B4); world_eye image saves off or timed.

Feasibility's hand-back (all four reviewers have now finished) moves the die
loss BEFORE B4: an empty-table probe, a decision rule and a question to Hani,
pre-registered before any remedy, because a fix chosen after B7 has run on
their layouts would be fitted to outcomes. It adds that only 4 of the 96 holds
would score (one of the 5 kept dice read 0.11 N, below scoring's 0.5 N), that
the grasp was only ever tested on 0.1 to 0.5 kg bodies and never carrying a
cup, that PDDLStream rewrites `statistics/py3/boxel-streams.pkl` in the working
directory on every solve (episodes depend on earlier runs; the laptop copy
holds a June file from the discarded v1 bridge; a pickle truncated by the 900 s
kill would break later solves), that the old per-seed rule fails even a no-op
change about 96% of the time, and about 11 to 13 days of slack before
2026-11-24 if these start now, in parallel with B4 to B6.

Feasibility findings still to verify and merge: the die-loss blocker (above); no
planned episode has run with the hooks installed; G6 placeholders (merged in
D4); PDDLStream's persisted stream statistics couple arm O episodes; D10's
budget; B4's acceptance rule undefined after Q13; D11 on 9 cells with a 0.8 mm
margin (8 of 20 seeds); PICK_CONTACT_FLOOR still None; RunLogger removes
TAMPURA's logging handlers; "12 of 20" (merged in R2); GateConfig.held_body
never wired; the VHACD twin's planning cost unmeasured.

## Open for Hani

- Local smokes and probes ran in the laptop's arm T venv, which D12 and the Q11
  answer forbid (validity minor). Confirm the deviation, or have a local arm O
  venv built.
- The B3 cherry-pick onto `main-paper-icaps-2027` needs a branch switch, which
  is not done in this shared checkout.
