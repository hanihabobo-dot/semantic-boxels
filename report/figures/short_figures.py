"""Figure files of the 8-page report (report/short.tex).

Makes the image files under report/figures/short/ from archived images. No simulation:
it only copies or crops existing PNGs. A target that already exists is left alone when
its bytes are the same and is an error when they differ (figures are added, never
replaced). Run from anywhere:

    C:\\Python312\\python.exe report\\figures\\short_figures.py
"""
import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "archive" / "tampura_bridge_plan_2026-10-25"
OUT = ROOT / "report" / "figures" / "short"

# (target name, source below ARCH, crop box in pixels or None for a plain copy[, new size])
JOBS = [
    # Hani's GUI run of 30 October, seed 10 (untracked run folder, so the frame is copied)
    ("fd_ours_s10_frame025.png",
     "bf/gui_runs/watch_s10_2026-10-30_13-23-41/ours/run_2026-10-30_13-25-12/eye_025_gui.png",
     (150, 120, 810, 700)),
    # path 4's painter frames: the board without the white margin and the legend
    ("wumpus_lw1_frame006.png", "tracks/wumpus/painter/lw1_frame_006.png", (370, 295, 1230, 1005)),
    ("wumpus_explore_frame007.png", "tracks/wumpus/painter/explore_frame_007.png", (370, 295, 1230, 1005)),
    ("wumpus_lw1_frame000.png", "tracks/wumpus/painter/lw1_frame_000.png", (370, 295, 1230, 1005)),
    ("wumpus_lw1_frame009.png", "tracks/wumpus/painter/lw1_frame_009.png", (370, 295, 1230, 1005)),
    ("wumpus_explore_frame004.png", "tracks/wumpus/painter/explore_frame_004.png", (370, 295, 1230, 1005)),
    # run 2 of BF#63, scene 118: the final overview of a failure, cut to the table
    ("fd_fail_s118_overview.png",
     "bf/BF63_gen_scenes/eval2/5084299/failures/O_s118_r0_a1/overview_final.png",
     (130, 60, 900, 720)),
]

# The 12 scenes our arm fails on in run 2 of BF#63 (repetition 0): the final overview of
# each, cut to the table like scene 118 above and halved, for the gallery figure.
FAIL_JOBS = {100: 5084295, 101: 5084295, 102: 5084295, 103: 5084295, 104: 5084296, 107: 5084296,
             111: 5084297, 118: 5084299, 124: 5084301, 127: 5084301, 128: 5084302, 135: 5084303}
for _scene, _job in FAIL_JOBS.items():
    JOBS.append((f"fail_tile_s{_scene}.png",
                 f"bf/BF63_gen_scenes/eval2/{_job}/failures/O_s{_scene}_r0_a1/overview_final.png",
                 (130, 60, 900, 720), (385, 330)))


def png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, src, box, *size in JOBS:
        source = ARCH / src
        target = OUT / name
        if not source.is_file():
            print(f"MISSING source {source}")
            bad += 1
            continue
        img = Image.open(source).convert("RGB")
        if box is not None:
            img = img.crop(box)
        if size:
            img = img.resize(size[0], Image.LANCZOS)
        data = png_bytes(img)
        if target.exists():
            if target.read_bytes() == data:
                print(f"same     {name}")
            else:
                print(f"DIFFERS  {name} (not replaced; give the new version a new name)")
                bad += 1
            continue
        target.write_bytes(data)
        print(f"written  {name} {img.size[0]}x{img.size[1]} {len(data)} bytes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
