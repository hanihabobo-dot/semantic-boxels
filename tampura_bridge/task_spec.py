"""#P4 the declared task knowledge for find_dice (PAPER_AUDIT.txt P4.4 B2, D8).

Everything the bridge tells our pipeline about TAMPURA's task, and nothing
else: the target category, the hollow categories with their cavities, class
sizes, masses and frictions, the D4 eye, the workspace window W, the home
configuration and D9's set-up values.  Every number comes from one of G9's
sources (the URDF, the YCB meshes, a constant in their source, a cited
dataset table, or a scene-independent probe on the empty table) and cites
the BF# entry that measured it.  Values marked PROVISIONAL are B1 part 2's
measurements; B6 freezes them before B7.  Its hash goes into campaign.json.
"""

# Category names as their scenes label them (world.categories).
TARGET_CATEGORY = 'dice'
CUP_CATEGORIES = ('a_cups_ud', 'b_cups_ud', 'c_cups_ud', 'd_cups_ud',
                  'e_cups_ud')

# Class sizes: the collision mesh's AABB extents (x, y, z) in metres, BF#4 (b).
CLASS_EXTENTS = {
    'dice': (0.0176, 0.0173, 0.0178),
    'a_cups_ud': (0.0576, 0.0586, 0.0625),
    'b_cups_ud': (0.0619, 0.0619, 0.0650),
    'c_cups_ud': (0.0666, 0.0666, 0.0676),
    'd_cups_ud': (0.0718, 0.0718, 0.0696),
    'e_cups_ud': (0.0767, 0.0767, 0.0719),
}

# Hollow categories (D6, model tweak M2; used from B5 on): the footprint a
# die-class body fits in, with 16.2 mm clearance, and the cavity height, from
# the collision meshes, BF#4 (b).
HOLLOW_CAVITY = {
    'a_cups_ud': (0.040, 0.040, 0.0537),
    'b_cups_ud': (0.045, 0.044, 0.0558),
    'c_cups_ud': (0.050, 0.048, 0.0591),
    'd_cups_ud': (0.054, 0.054, 0.0606),
    'e_cups_ud': (0.056, 0.057, 0.0624),
}

# D9 (3): class masses, Calli et al., "The YCB Object and Model Set", ICAR
# 2015, Table I; every task body gets lateral friction 1.0, the ObjectSpec
# default of our scenes (boxel_env.py ObjectSpec.lateral_friction).
CLASS_MASS_KG = {'dice': 0.0052, 'a_cups_ud': 0.013, 'b_cups_ud': 0.014,
                 'c_cups_ud': 0.017, 'd_cups_ud': 0.019, 'e_cups_ud': 0.021}
# D9 (3): the inertia diagonal of each class's collision geometry, derived
# once from the meshes: the VHACD pieces' convex hulls at one uniform
# density giving the class mass, about the body origin (create_ycb's visual
# centre of mass); pieces with fewer than four distinct points, zero hull
# volume or a non-finite centre are skipped (BF#12 corrects BF#4's rule,
# which let a zero-volume piece through and gave NaN for b and e).
CLASS_INERTIA_DIAG = {
    'dice': (2.33769e-07, 2.354e-07, 2.23686e-07),
    'a_cups_ud': (7.69821e-06, 7.54269e-06, 5.95507e-06),
    'b_cups_ud': (9.37399e-06, 9.23996e-06, 7.64247e-06),
    'c_cups_ud': (1.28835e-05, 1.25884e-05, 1.12588e-05),
    'd_cups_ud': (1.56253e-05, 1.55573e-05, 1.45189e-05),
    'e_cups_ud': (1.91863e-05, 1.894e-05, 1.83881e-05),
}
OBJECT_LATERAL_FRICTION = 1.0
# D9 (1), (2), (4): our gravity and timestep, our pad friction and opening
# (boxel_env.py _setup_scene; robot_utils.SIM_TIMESTEP).
GRAVITY_Z = -9.81
TIMESTEP = 1.0 / 240.0
PAD_LATERAL_FRICTION = 1.2
FINGER_OPEN = 0.04

# D4: the fixed eye, the view their pb_utils.get_image_at_pose computes for
# camera_frame at DEFAULT_ARM_POS (pb_utils.py get_image_at_pose, get_image,
# get_projection_matrix; robot.py WIDTH, HEIGHT, FX, FY), measured in BF#11
# (e) from their own functions.  Rendered with our TinyRenderer path.
EYE_POSITION = (0.17861445248126984, 0.048803217709064484, 0.5883188247680664)
EYE_TARGET = (3.285824775695801, -0.16977983713150024, -3.322878360748291)
EYE_UP = (0.0, 0.0, 1.0)
EYE_FOV_DEG = 49.13434264120263     # 2 atan(240 / 525)
EYE_WIDTH, EYE_HEIGHT = 640, 480
EYE_NEAR, EYE_FAR = 0.02, 5.0

# D8: the workspace window W (PROVISIONAL, BF#11 (e)): the largest
# axis-aligned rectangle of 1 cm cells inside their shortened table that
# the eye images in full (column up to the tallest class) and the arm
# reaches at the post-place lift height of the tallest class.
WINDOW_X = (0.35, 0.74)
WINDOW_Y = (-0.28, 0.34)

# Their table top (panda_env_utils.TABLE_POSE: the 3 cm box centred at
# z = -0.015) and their robot's base at the origin.
TABLE_TOP_Z = 0.0

# D7 (ii): the home configuration q_home = their DEFAULT_ARM_POS
# (tampura_environments/panda_utils/robot.py:36), read from their module at
# run time, never copied.
HOME_IS_THEIR_DEFAULT_ARM_POS = True

# D7 (vii): twice the largest step count the final hold needed to pass
# TAMPURA's at-home test over B1(i)'s probe grid (26), BF#11 (i)
# (PROVISIONAL until B6 freezes it).
HOME_HOLD_STEP_CAP = 52

# D8: the pick contact floor, a probe on the empty table (2026-10-28, BF#26):
# their Panda's fingertip collision AABB reaches 11.2 mm below
# panda_grasptarget with the gripper pointing down (ours the same), plus
# 2 mm clearance.  Our pipeline's 35 mm default put the die's pinch above
# the 17.8 mm die.  PROVISIONAL until B6 freezes it.  The reach envelope
# stays B6's (None keeps our pipeline's value).
PICK_CONTACT_FLOOR = 0.0132
REACH_ENVELOPE = None
