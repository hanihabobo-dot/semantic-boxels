# REPORT: TAMPURA task page (API agent, 2026-11-04)

Status: done. The page and its images are ready for review; nothing was published, committed or deleted.

## Files made (all inside HERE)

- index.html: the page (47 KB). Title and h1 "TAMPURA's other tasks". Fonts: Bricolage Grotesque (display) and Atkinson Hyperlegible (body) from Google Fonts; no JavaScript; images by relative path img/*.png.
- img/ (11 PNGs, 783,480 bytes in total) and img/MANIFEST.md (camera, labels and command per image).
- Scripts: common.py (build the env as run_planner.py does, render, project, label), shots.py (one branch per task), info.py (prints bodies and poses per scene), run.sh (runs a HERE script with cwd /root/task_shots, their PYTHONPATH, PYTHONDONTWRITEBYTECODE=1), setup.sh (the 3.1 setup), check_page.py and check_numbers.py (self-checks).
- shots/: run folders (SAVE_DIR per task) plus check renders and rejected renders (see leftovers).

## Images on the page (all seed 0, rendered from their code)

- img/find_dice_oblique.png: overview; seed 0 layout has one cup (d_cups_ud), die ringed under it.
- img/find_dice_top.png: top view, same ring and labels.
- img/class_uncertain_oblique.png: strawberry, racquetball, tennis ball (just behind the bowl in this view), bowl; true classes labelled.
- img/class_uncertain_top.png: top view, same labels; the tennis ball touches the bowl's rim.
- img/tool_use_oblique.png: three cubes, real cube solid, nine particles blended in at 35 %, hook labelled.
- img/tool_use_top.png: top view, same blending.
- img/puck_slide_oblique.png: side overview, reach region (blue) and goal (green) shaded, puck pixels kept unshaded.
- img/puck_slide_top.png: top view, x to the right.
- img/slam_collect_map.png: my own labelled map from env.state, with legend.
- img/slam_collect_theirs.png: their own frame_000.png (dpi 200), white margin trimmed.
- img/slam_collect_simple_theirs.png: their own frame of slam_collect_simple, trimmed the same way.

## Self-check results

- html.parser plus a tag-balance check: no errors, nothing unclosed; all 11 img srcs exist; all in-page links resolve; the only external link is the arXiv paper (plus the Google Fonts stylesheet).
- U+2014: 0, U+2013: 0 (page and MANIFEST). "faithful": 0. No emoji.
- 41 "unverified" tags, 4 "measured" tags (the tool_use probe results).
- Every number in the page's visible text occurs verbatim in sources/ (check_numbers.py).
- Not done: I could not view the page in a browser (no browser tool here), so the layout at phone width and in dark mode is checked only by reading the CSS (tables in overflow-x wrappers with min-widths, 16 px gutters, images max-width 100 %, grid stacks below 760 px). Please glance at it before publishing.

## Unsure or not confirmed

- puck_slide: the brief suspected TinyRenderer would draw the alpha-0 "surface" box black. A check render with it in place (shots/puck_slide_*_with_surface.png) shows it is not drawn at all. I still moved it away in the final renders; this changes nothing visible, and the caption says so.
- slam_collect map: I drew the beacon sensing areas as rotated 2 m squares (their Region shape and pose, centred, as their get_corners does). I did not read the exact membership test for beacons, only that regions use these shapes; their own plot draws the range as a circle, which the caption mentions.
- class_uncertain oblique: the tennis ball's label dot falls on the bowl's rim because the ball is behind the bowl from that camera; the caption says so and the top view shows it clearly.
- Jargon kept from the reports with a short gloss where it first appears: B9, M8, H1, audit #53. Hani knows them; a wider audience would not.
- Facts left as unverified on the page (as in the sources): implied success rates, how Table I was computed, all effort estimates, which variant is E-MF, DROPABILITY 0.85 or 0.35, whether the repo's class_uncertain is the paper's version, whether the class_uncertain scenes are the paper's, whether the find_dice layouts are the paper's, find_dice_simple visibility, the Panda's 855 mm reach, his cameras measuring the tool_use cloud, TAMPURA's world-state score on tool_use, and where a puck_slide or slam_collect port would land.
- The two reports give different effort figures for puck_slide (survey 2 to 3 weeks, no-fit case 1 to 2 weeks); the page shows both, each attributed.

## Leftovers to delete (I deleted nothing)

- WSL: /root/task_shots (two folders and three symlinks into /root/tampura-work; nothing else written there). Nothing under /root/tampura-work was changed.
- HERE/shots/rejected_v1/: first-round renders of all 11 images (cage-bar shadow bands, overlapping labels, a cage post in the tool_use view, robot cut off in puck_slide).
- HERE/shots/rejected_v2/: second-round puck_slide renders (blue shading tinted the puck).
- HERE/shots/tool_use_oblique_all_solid.png, tool_use_top_all_solid.png: the unblended first pass (TinyRenderer drew all alpha 0.2 copies solid, as expected).
- HERE/shots/puck_slide_oblique_with_surface.png, puck_slide_top_with_surface.png: the surface check renders.
- HERE/shots/run_<task>/: SAVE_DIRs; run_slam_collect and run_slam_collect_simple hold their frames (frames/frame_000.png used, frame_001.png and later are repeats from re-runs).
- Scripts and checks in HERE (common.py, shots.py, info.py, run.sh, setup.sh, check_page.py, check_numbers.py): keep them if the images should stay regenerable, otherwise delete.

## Cost

The runner showed about $3.2 of the $20 cap when this report was written.
