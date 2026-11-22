"""What one render says about one body: whether its detection is complete,
what a check may judge it for, and whether a release is seen.

`execution` imports every name of this file, and callers import them from
there.
"""
import numpy as np

import arm_eye
import pose_belief
from boxel_data import BoxelType
from perception import DETECTION_MIN_PIXELS, first_surface_interceptors


def _observe_release(env, dropped_name, expected_top_z=None, rigid_ext=None,
                     enforce_tilt=False, settle_steps=20):
    """Verify a release by OBSERVATION after the post-action lift (#P1
    WP2b, 2026-09-19): the camera half of the drop verification.

    Two renders ``settle_steps`` apart (env.detect_objects).  On the
    released object's detection:
      top      — its estimated top within 2 cm of ``expected_top_z``
                 (support top + the object's rigid height; None skips
                 the check, e.g. a tray whose floor is not a modelled
                 support);
      upright  — with ``enforce_tilt``, the horizontal extents no wider
                 than the rigid size + 1.5 cm and the top no higher than
                 expected + 1.5 cm (a toppled box grows sideways and
                 shrinks in height; a hanging one is too high);
      still    — the centre moved no more than 3 mm between the renders
                 (a body riding on the retreating arm moves).
    The tops of resting bodies are the best-observed surface of this
    camera (probe: +0.1 cm), so 2 cm is generous.  An object the render
    does not show at all (hidden by the arm or another body) cannot be
    judged by sight: the release is accepted on the tactile checks and
    the run log says so; the dispatcher's post-action refresh keeps
    correcting the belief.  Returns (ok, diag, observed_centre) — the
    centre is None when the object was not observed or the check failed.
    With --eye arm (arm_eye.following) each render is the arm camera where
    the arm stands, and the released object is judged only when both of
    its detections lie wholly in their images; otherwise the release is
    accepted on the tactile checks, as for an object the render does not
    show.  Its registry box is the pick-time one, so the detections are
    the boxes an image can hold.
    """
    following = arm_eye.following(env)
    dets_a = env.detect_objects()[0]
    view_a = env._view_and_projection_matrices()[0] if following else None
    for _ in range(settle_steps):
        env.step_simulation()
    dets_b = env.detect_objects()[0]
    view_b = env._view_and_projection_matrices()[0] if following else None
    da, db = dets_a.get(dropped_name), dets_b.get(dropped_name)
    if da is None or db is None or db.pixel_count < DETECTION_MIN_PIXELS:
        return True, (f"unobserved after the lift "
                      f"({'no detection' if db is None else f'{db.pixel_count} px'}) — "
                      f"accepted on the tactile checks"), None
    if following and not (arm_eye.in_frame(view_a, (da.est_min, da.est_max))
                          and arm_eye.in_frame(view_b, (db.est_min, db.est_max))):
        return True, (f"not wholly in the arm camera's image after the lift "
                      f"({db.pixel_count} px): accepted on the tactile checks"), None
    top = float(db.est_max[2])
    ext = db.est_max - db.est_min
    shift = float(np.hypot(*((db.est_center - da.est_center)[:2])))
    problems = []
    if expected_top_z is not None and abs(top - expected_top_z) > 0.02:
        problems.append(f"top {top:.4f} is {(top - expected_top_z) * 1000:+.0f} mm "
                        f"from the expected {expected_top_z:.4f}")
    if enforce_tilt and rigid_ext is not None:
        if (ext[0] > rigid_ext[0] + 0.015) or (ext[1] > rigid_ext[1] + 0.015):
            problems.append(f"footprint {ext[0] * 100:.1f} x {ext[1] * 100:.1f} cm "
                            f"exceeds the rigid {rigid_ext[0] * 100:.1f} x "
                            f"{rigid_ext[1] * 100:.1f} cm — toppled")
        if expected_top_z is not None and top > expected_top_z + 0.015:
            problems.append("top above the expected top — tilted or hanging")
    if shift > 0.003:
        problems.append(f"moved {shift * 1000:.1f} mm between two renders")
    diag = (f"observed {db.pixel_count} px, top {top:.4f}"
            f"{'' if expected_top_z is None else f' (expected {expected_top_z:.4f})'}, "
            f"footprint {ext[0] * 100:.1f} x {ext[1] * 100:.1f} cm, "
            f"shift {shift * 1000:.1f} mm")
    if problems:
        return False, diag + " — " + "; ".join(problems), None
    return True, diag, np.asarray(db.est_center, dtype=float)


def frame_judgement(view, bd, det) -> str:
    """Path 9, --eye arm: what a check after an action may judge the
    registered body ``bd`` for, from the render whose view matrix is
    ``view`` and its detection ``det`` (None when it shows none).  The look
    manager's rule (2026-11-14): absence verdicts need the believed box
    wholly in the frame, presence verdicts need the detection wholly in the
    frame, and nothing is re-posed from a cut detection.

      'presence': the detection lies wholly in the frame (arm_eye.in_frame).
          The body is judged as with the fixed camera, wherever its
          believed box is: re-posed, disturbed, toppled, off its support,
          knocked off the table when the detection lies below it.
      'absence': no detection, or one the frame cuts, and the believed box
          wholly in the frame.  The body is judged as one with no
          detection: the lost check on its believed region decides.
      'keep': neither.  The body keeps its belief, its support relation
          included."""
    if det is not None and arm_eye.in_frame(view, (det.est_min, det.est_max)):
        return 'presence'
    if arm_eye.in_frame(view, (bd.min_corner, bd.max_corner)):
        return 'absence'
    return 'keep'


def detection_complete(env, box_min, box_max, det, render) -> bool:
    """M8 A: a COMPLETE detection has at least DETECTION_MIN_PIXELS, its
    box lattice (3 x 3 x 3) all in view, and no lattice point hidden by
    the robot or by another registered body (the seg-mask id of the
    surface in front, the identity map's ids)."""
    if render is None or det is None or det.pixel_count < DETECTION_MIN_PIXELS:
        return False
    g = [np.linspace(float(box_min[k]), float(box_max[k]), 3) for k in range(3)]
    pts = np.array([[x, y, z] for x in g[0] for y in g[1] for z in g[2]])
    icp, hids, in_view = first_surface_interceptors(pts, render[0], render[1],
                                                    render[2], render[3])
    others = {info.object_id for n, info in env.objects.items()
              if n not in ("plane", "table")} - {int(det.body_id)}
    return bool(np.all(in_view) and not np.any(icp & np.isin(hids, list(others))))


def record_initial_detections(env, registry) -> None:
    """M8 A for the initial observation's registrations (Phase 3): every
    OBJECT boxel built from the first render is a first registration,
    formula if its detection is complete, else plus half its completion.
    One eye render, identical to the one the boxels came from (no step
    in between).  No-op while every switch is OFF."""
    if not pose_belief._any_on():
        return
    dets, _, buf, seg = env.detect_objects()
    render = (env._depth_buffer_to_meters(buf), seg,
              *env._view_and_projection_matrices())
    for bd in registry.get_boxels_by_type(BoxelType.OBJECT):
        det = dets.get(bd.id)
        if det is None:
            continue
        pose_belief.record_detection(
            bd, det, 'eye',
            detection_complete(env, bd.min_corner, bd.max_corner, det, render),
            first=True)
