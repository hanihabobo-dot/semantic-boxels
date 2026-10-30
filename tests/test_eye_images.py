"""BF#50 (user rule, 2026-10-30): the eye images (eye_<k>_camera.png and
eye_<k>_gui.png) are for debugging only.  They are off unless the run says
--save-screenshots on, and BOXEL_EYE_IMAGES=0 (the cluster job scripts,
BF#17) vetoes them even then."""
import run_logger
import world_eye


def test_images_off_by_default(monkeypatch):
    monkeypatch.delenv('BOXEL_EYE_IMAGES', raising=False)
    monkeypatch.setattr(world_eye, 'SAVE_IMAGES', False)
    assert world_eye.images_wanted() is False


def test_images_on_when_the_run_asks(monkeypatch):
    monkeypatch.delenv('BOXEL_EYE_IMAGES', raising=False)
    monkeypatch.setattr(world_eye, 'SAVE_IMAGES', True)
    assert world_eye.images_wanted() is True


def test_the_cluster_veto_wins_over_the_flag(monkeypatch):
    monkeypatch.setenv('BOXEL_EYE_IMAGES', '0')
    monkeypatch.setattr(world_eye, 'SAVE_IMAGES', True)
    assert world_eye.images_wanted() is False


def test_the_flag_is_off_by_default_and_on_when_given():
    assert run_logger.parse_pipeline_args(['--no-gui']).save_screenshots == 'off'
    args = run_logger.parse_pipeline_args(['--no-gui', '--save-screenshots', 'on'])
    assert args.save_screenshots == 'on'
