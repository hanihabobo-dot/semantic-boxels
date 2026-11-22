"""Our window's debug camera panes in TAMPURA's window (Hani, 2026-11-21;
BF#27's request).

Our own window (boxel_env.py, p.connect(p.GUI)) keeps PyBullet's side panel,
and in it the camera panes: RGB and depth, "the two debug cameras", and the
segmentation mask of the same render (on again in both windows on Hani's
word of 2026-11-21).  BoxelTestEnv fills them from the robot's camera with a
hardware render, under the GUI alone: get_camera_observation and
refresh_debug_camera_views, the latter after every plan and every executed
step (test_full_pipeline.main).  On TAMPURA's env the same code runs in a
--vis 1 run, since the episode builds TampuraWorldEnv(world, gui=cfg.vis)
(policy.py), so the panes are filled there too.  They are not shown: their
window is set up without the side panel
(tampura_environments/panda_utils/panda_env_utils.py, setup_robot_pybullet:
client.configureDebugVisualizer(p.COV_ENABLE_GUI, 0)), and PyBullet draws
the panes as part of that panel.

show() switches the panel back on, with the panes as our window has them.
The driver calls it under --vis 1 alone, after their initialize (their own
first image is taken before it) and before the episode installs the gates.
A GUI run is for watching and is never scored (BF#39).

Display only.  It sets debug visualizer flags of their window: no body, no
step, no render, no read of the simulator and no random number.  What the
panes then show is what the renders of the run already drew; this module
renders nothing.  PyBullet has one flag for the whole panel, so their window
also gets what our window has beside the panes: the side menus and the
ground grid.

What the panes show.  PyBullet copies EVERY camera render on the window's
client into them, the TinyRenderer's as well as the hardware renderer's
(bullet3, PhysicsServerCommandProcessor::processRequestCameraImageCommand:
debugDisplayCameraImageData is called in both branches; seen on a screen
with the installed build on 2026-11-21).  At show() they hold TAMPURA's own
first image, a hardware render of their hand camera that their initialize
took.  Between show() and hide() the renders on that client are: the robot's
camera, which is the declared eye or the wrist at its forward kinematics
(outside world_eye's captures gate G20 refuses any other view during the
episode; inside a capture it compares nothing), and, inside such a capture,
world_eye's window screenshot under --save-screenshots on, after which
world_eye renders the robot's camera again (TB-40).  Their rollout renders
nothing after our episode (its remaining steps are no-ops, which it does not
execute).  The driver's final overview is not the robot's view, so the
driver calls hide() before it.
"""
import pybullet as p

# (flag, value), in the order set: the panel, then the panes as
# boxel_env.py leaves them in our window (all three on: RGB, depth and the
# segmentation mask).  The panel's flag does the work today: the three pane
# flags are on when PyBullet opens a window and their setup never touches
# them; they are set so that their window shows what ours shows whatever a
# later setup of theirs does.
PANES = (
    (p.COV_ENABLE_GUI, 1),
    (p.COV_ENABLE_RGB_BUFFER_PREVIEW, 1),
    (p.COV_ENABLE_DEPTH_BUFFER_PREVIEW, 1),
    (p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW, 1),
)
PANEL_OFF = ((p.COV_ENABLE_GUI, 0),)


def _set(client, flags, what):
    """Display only: a window that does not take a flag (closed by hand,
    say) is reported in one line and is never the run's problem."""
    try:
        for flag, value in flags:
            client.configureDebugVisualizer(flag, value)
    except Exception as e:
        print(f"gui_panes: the camera panes were not {what} "
              f"({type(e).__name__}: {e})")


def show(client):
    """Show the camera panes in the window of `client` (their BulletClient
    of the executing world)."""
    _set(client, PANES, 'shown')


def hide(client):
    """Put the panel away again, as their window setup leaves it.  The
    driver calls it once the rollout is over, before it renders the final
    overview: PyBullet copies a render into the panes whichever view it
    has, and the overview's two views are not the robot's."""
    _set(client, PANEL_OFF, 'put away')
