"""BF#59 grasp_wrist_home: the joint-7 formula against the recorded die
carries (loss_dynamics' five base episodes, carry_motion's two flip
episodes).  Inputs read from their logs by hand: the die's believed centre
before the pick (console '[eye] ... before action pick(dice)'), the grasp
yaw of the last sample_grasp line, and the recorded joint-7 travel home
(base: nine times the first waypoint pair's dq7 in carry.jsonl, the
planned linear path, reviews/carry_motion.md 1; flip: the proposal's 1.3
table).  Their Panda's base is at the origin, home joint 7 0.7849.

  python episodes_check.py
"""
import math

import pose_belief as pb

H = 0.7849
EPISODES = [
    ('s0_r1 held', 0.673, 0.216, 0.00, 9 * 0.3247),
    ('s1_r1 held', 0.591, -0.242, -0.67, 9 * 0.3549),
    ('s1_r2 lost', 0.591, -0.242, -0.67, 9 * 0.3548),
    ('s1_r3 lost', 0.591, -0.242, -0.76, 9 * 0.3434),
    ('s6_r1 lost', 0.486, -0.159, -0.19, 9 * 0.3852),
    ('s0 flip+trap', 0.673, 0.216, 3.14, math.radians(22)),
    ('s1 flip+trap', 0.591, -0.242, 2.47, math.radians(12)),
]
for name, x, y, g, trav in EPISODES:
    q = pb.wrist_joint7_top_down((x, y), (0.0, 0.0), g)
    chosen, info = pb.wrist_home_twin(g, (x, y), (0.0, 0.0), H)
    pred = math.degrees(abs(q - H))
    rec = math.degrees(trav)
    print(f"{name:14s} yaw {math.degrees(g):7.1f} deg: predicted q7 {q:+.3f} rad, "
          f"travel {pred:5.1f} deg, recorded {rec:5.1f} deg (diff {pred - rec:+5.1f}); "
          f"the switch would take yaw {math.degrees(chosen):7.1f} deg "
          f"(twin {info['twin']}, |dq7| {math.degrees(info['d']):.0f} against "
          f"{math.degrees(info['twin_d']):.0f} deg)")
