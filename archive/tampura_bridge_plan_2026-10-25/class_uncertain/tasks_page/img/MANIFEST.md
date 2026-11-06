# Image manifest (2026-11-04)

All images: seed 0 (random.seed(0), np.random.seed(0), global_seed 0), scene built exactly as run_planner.py does (see common.py build_env), TAMPURA code at /root/tampura-work used read-only.

Regenerate one task (from PowerShell):

    wsl -e bash -c "bash /mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels/archive/tampura_bridge_plan_2026-10-25/class_uncertain/tasks_page/run.sh shots.py <task>"

run.sh sets cwd /root/task_shots (symlinks to their env_configs and problems folders), PYTHONPATH to their two packages, PYTHONDONTWRITEBYTECODE=1, and uses /root/tampura-work/.venv/bin/python. Scripts: shots.py (per task), common.py (build, render, project, label helpers).

3D renders: getCameraImage 2048x1536, ER_TINY_RENDERER, shadow=1, lightDirection (0.08, -0.05, 1.0), projection computeProjectionMatrixFOV(fov=55, aspect=4/3, near 0.05, far 10), downsampled to 1024x768 with LANCZOS. Labels: PIL, DejaVuSans-Bold 20 px, white rounded box, dot and leader line at the object (anchor = projected body base position).

| file | task | camera eye / target / up (fov 55) | labels and overlays | notes |
|---|---|---|---|---|
| find_dice_oblique.png | find_dice (env.world) | (1.45, -0.35, 1.25) / (0.40, 0, 0.15) / (0, 0, 1) | red ring (r 34 px) at the die; "die (hidden under this cup)", "Panda arm" | seed 0 layout: one cup (d_cups_ud) with the die under it |
| find_dice_top.png | find_dice | (0.40, 0.01, 1.15) / (0.40, 0.01, 0) / (1, 0, 0) | same | |
| class_uncertain_oblique.png | class_uncertain (env.state.world) | (1.25, -0.35, 0.95) / (0.45, 0.05, 0.05) / (0, 0, 1) | "strawberry (fruit)", "racquetball (ball)", "tennis ball (ball)", "bowl" | objects 10, 11, 12 paired in order with categories strawberry, racquetball, tennis_ball; bowl = world.regions[1] = body 13. The tennis ball sits just behind the bowl in this view |
| class_uncertain_top.png | class_uncertain | (0.52, 0.06, 0.80) / (0.52, 0.06, 0) / (1, 0, 0) | same | |
| tool_use_oblique.png | tool_use (env.world) | (1.20, -0.30, 0.80) / (0.40, -0.05, 0.03) / (0, 0, 1) | "cube 0/1/2 and 9 guesses", "hook (pose known)" | rendered twice: all bodies (keeping the segmentation buffer), then the 27 particle bodies moved to z -5; particle pixels of the first blended over the second at 35 % opacity, so the real cube is solid. Particles restored afterwards (in-process only) |
| tool_use_top.png | tool_use | (0.36, -0.05, 0.80) / (0.36, -0.05, 0) / (1, 0, 0) | same | same blending |
| puck_slide_oblique.png | puck_slide (env.state.world) | (0.55, -1.55, 1.0) / (0.60, 0, 0.15) / (0, 0, 1) | blue polygon reach region x 0.3 to 0.9, green polygon goal x 1.2 to 1.4 (z 0.052); "puck (friction unknown)", "reach region", "goal" | the alpha-0 "surface" body (id 12) was moved to z -20 before rendering; a check render with it in place (shots/puck_slide_*_with_surface.png) shows TinyRenderer did not draw it, so this changes nothing visible. Puck pixels (segmentation) kept unshaded |
| puck_slide_top.png | puck_slide | (0.52, 0, 1.35) / (0.52, 0, 0) / (0, 1, 0) | same | x points right |
| slam_collect_theirs.png | slam_collect | none (2D) | none | their own plot_trajectories frame (SAVE_DIR/frames/frame_000.png written by env.initialize() with savefig.dpi 200), white margin trimmed (24 px kept) |
| slam_collect_map.png | slam_collect (env.state) | none (2D, matplotlib, 8 x 8.8 in at 128 dpi) | legend; labels for goal, beacon, target, robot, obstacle, map corner | own drawing: Regions as rotated rectangles centred on pose with shape (as their get_corners); beacon vision squares 2 m dashed; robot as their triangle |
| slam_collect_simple_theirs.png | slam_collect_simple | none (2D) | none | their own frame_000.png, trimmed as above |
