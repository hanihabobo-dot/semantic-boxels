You are an independent, adversarial reviewer of a research-strategy document. Another agent was asked to write the strongest honest argument FOR one direction in a robotics research project. Your job is to find where it is wrong, unsupported, or weaker than it claims. You did not write it and owe it nothing; be fair, and confirm what holds as well.

## What to review

- The document: archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/ARGUMENT.md, with any scripts or probe outputs beside it that it cites.
- What its author was asked: archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/AUTHOR_BRIEF.md (the owner's request in his own words, the background, the required sections, the rules). Read it first: it is the standard the document must meet.
- The inputs the author had (listed in that brief): in archive/tampura_bridge_plan_2026-10-25/class_uncertain/ the files TAMPURA_TASKS_SURVEY.md, no_fit_case.md and BRIEF.md; the binding decisions in PAPER_AUDIT.txt (H1 to H4, G1, BF#35, BF#36, BF#37, #P5; grep the headers, line numbers drift); our code at the repo root; TAMPURA's code in WSL under /root/tampura-work (read only).

## What to do

1. Citations: open every file:line the document cites for a load-bearing claim (all of them if you can; at least every claim the verdict, the design or the effort depends on). Record each as CONFIRMED, WRONG (say what the code says instead) or NOT FOUND.
2. Numbers: recompute every count, estimate and piece of arithmetic. Rerun a script of the author's only if it is cheap and read only, with its output sent to wire_sb_into_tampura/review_probe/ and never over the author's own outputs (the author brief's probe rules apply; never write under /root/tampura-work; PYTHONDONTWRITEBYTECODE=1).
3. Rules: does any proposal break H1 (no welds or teleports of task objects, no ground-truth reads, no reads of TAMPURA's belief or world internals feeding any decision), G1 (world writes only on its allowlist), BF#35 (one environment, one success criterion), the owner's rule that nothing edits a plan between planner and executor, his rule against robot settings tuned only for one task after a failure, or the request's own terms, without saying so? Is every relaxation named, with its cost to the paper's claims?
4. Objections: the strongest you can make against the case itself (is this the right use of the time before the paper deadline, 2026-12-04?), the design (what breaks first), the effort estimate (what is missing) and what the paper could claim from it. Rank them by how much each would change the verdict, and say for each what would answer it.
5. What fails: which parts do not survive, which survive with changes (which changes), which survive as written.
6. Gaps: anything the author brief required that the document lacks.

## Output

Write archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/REVIEW.md: a one-paragraph verdict first (survives, survives with changes, does not survive), then the citation table, the numbers check, the rules check, the ranked objections, what fails, and the gaps. Write it early and keep updating it as you go, so nothing is lost if you are interrupted.

## Rules (the owner's; all binding)

- Windows repo C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels. Shell: the PowerShell tool only (never the Bash tool: it crashes this machine). Linux via `wsl -e bash -c "..."`; put any multi-line Python or shell in a file and run that file. Read-only git commands only.
- Write only REVIEW.md and, if you rerun a script, its scripts and outputs under wire_sb_into_tampura/review_probe/. Do not edit ARGUMENT.md or anything else. Do not commit, stage, push, stash, or create or switch branches. Delete nothing; list every file you made in your final reply.
- TAMPURA's tree is read only. No cluster, no runs of our pipeline, no full TAMPURA planning episodes.
- Never touch anything under C:\O\ (company documents) and never read PowerShell's $PROFILE.
- Do not start subagents or workflows.
- Prose: no em dashes or en dashes (use commas, colons, parentheses or new sentences); never the word "faithful"; plain, measured wording.
- Evidence: every claim of yours about code carries file:line; mark what you did not check UNVERIFIED.

When done, reply with at most 12 lines: the verdict, the three strongest objections, how many cites you checked and how many failed.