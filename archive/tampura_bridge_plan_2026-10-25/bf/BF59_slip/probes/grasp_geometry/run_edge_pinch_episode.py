"""One find_dice bridge episode with the edge pinch patched into M9's grasp
candidates (a probe of fix `edge_pinch`, no tracked file changed).

For a near-square fitted footprint, pose_belief.fitted_grasp_candidates
returns the diagonal grasp (grasp yaw = fitted yaw + 45 deg, the pads on two
opposite vertical edges) instead of the face grasp; its span is the yawed
rectangle's width along the pads (pinch_half_extent), widened to the
registry AABB's side as Q-H (a) does.  Everything downstream (sample_grasp,
believed_margin, pose_known, execute_pick's sizing through sized_pinch_half)
reads the module attribute, so the patch reaches every user.  The patch
prints every candidate it returns.

  cd /root/tampura-work/tampura_environments
  flock /root/sb_pipeline.lock -c "<env> python <this> --global-seed 0 --vis 0 \\
      --allow-g19-mismatch 1 --save-dir <dir>"
"""
import math
import os
import runpy
import sys

REPO = '/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels'
sys.path.insert(0, REPO)

import pose_belief  # noqa: E402

_orig = pose_belief.fitted_grasp_candidates


def edge_candidates(yaw, body_extents, square_tol, aabb_ext=None):
    e0, e1 = float(body_extents[0]), float(body_extents[1])
    if abs(e0 - e1) > square_tol:
        return _orig(yaw, body_extents, square_tol, aabb_ext)
    gy = pose_belief._wrap(yaw + math.pi / 4.0, math.pi / 2.0)
    span = 2.0 * pose_belief.pinch_half_extent(pose_belief.pad_direction(gy), yaw,
                                               body_extents)
    if aabb_ext is not None:
        span = max(span, 2.0 * pose_belief.aabb_half_along(pose_belief.pad_direction(gy),
                                                           aabb_ext))
    if span > 0.076:                      # streams.BoxelStreams.GRASP_MAX_SPAN
        return _orig(yaw, body_extents, square_tol, aabb_ext)
    # Scope (seed-0 run 13-07-56): the edge family only where its commit
    # margin is at least the face family's, so the belief never commits
    # later than today (a 51 mm cup's diagonal left a 2 mm margin).
    face = _orig(yaw, body_extents, square_tol, aabb_ext)

    def margin(gy_, span_):
        d = pose_belief.pad_direction(gy_)
        perp = pose_belief.pinch_half_extent([d[1], -d[0]], yaw, body_extents)
        return min(0.04 - span_ / 2.0 - pose_belief.PINCH_CLEARANCE,
                   pose_belief.PERP_COMMIT_FRACTION * perp)
    if margin(gy, span) < min(margin(g, s) for g, s in face):
        return face
    print(f"    [edge_pinch probe] yaw {math.degrees(yaw):.1f} deg extents "
          f"{e0 * 1e3:.1f} x {e1 * 1e3:.1f} mm -> grasp yaw {math.degrees(gy):.1f} deg, "
          f"span {span * 1e3:.1f} mm", flush=True)
    return [(gy, span)]


pose_belief.fitted_grasp_candidates = edge_candidates
sys.argv = [os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
