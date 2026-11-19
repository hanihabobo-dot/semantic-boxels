"""Path 9: arm_eye.TAMPURA_HOME_JOINTS, the start configuration and q_home of
--eye arm on our tabletop when no joints are given, is TAMPURA's
DEFAULT_ARM_POS.  The tabletop run cannot import tampura_environments, so the
constant is a literal; this bridge test (their trees importable, as
test_g6_controls.py) checks it against theirs."""
import arm_eye


def test_the_arm_cameras_tabletop_start_is_their_default_arm_pos():
    from tampura_environments.panda_utils.robot import DEFAULT_ARM_POS
    assert [float(v) for v in arm_eye.TAMPURA_HOME_JOINTS] == \
        [float(v) for v in DEFAULT_ARM_POS]
