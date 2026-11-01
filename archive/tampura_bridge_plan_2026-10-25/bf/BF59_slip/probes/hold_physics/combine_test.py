"""How this pybullet build combines rolling and spinning friction of two bodies.

A sphere (r 1 cm, 50 g) on a box plate, given a spin about the vertical
(spinning) or a roll about x (rolling), friction values per case; the angular
speed left after 0.5 s tells which combination rule holds:
product a*b, or the cross rule a_roll*b_lat + a_lat*b_roll."""
import pybullet as p

p.connect(p.DIRECT)
p.setGravity(0, 0, -9.81)
p.setTimeStep(1 / 240)


def run(mode, s_lat, s_x, pl_lat, pl_x):
    p.resetSimulation()
    p.setGravity(0, 0, -9.81)
    p.setTimeStep(1 / 240)
    plate = p.createMultiBody(0, p.createCollisionShape(p.GEOM_BOX, halfExtents=[1, 1, 0.01]),
                              basePosition=[0, 0, -0.01])
    sph = p.createMultiBody(0.05, p.createCollisionShape(p.GEOM_SPHERE, radius=0.01),
                            basePosition=[0, 0, 0.0099])
    key = 'rollingFriction' if mode == 'roll' else 'spinningFriction'
    p.changeDynamics(plate, -1, lateralFriction=pl_lat, **{key: pl_x})
    p.changeDynamics(sph, -1, lateralFriction=s_lat, **{key: s_x}, linearDamping=0, angularDamping=0)
    for _ in range(20):
        p.stepSimulation()
    w0 = [10, 0, 0] if mode == 'roll' else [0, 0, 10]
    v0 = [0, -0.1, 0] if mode == 'roll' else [0, 0, 0]   # roll about x moves along -y
    p.resetBaseVelocity(sph, v0, w0)
    for _ in range(120):
        p.stepSimulation()
    _, w = p.getBaseVelocity(sph)
    return w[0] if mode == 'roll' else w[2]


cases = [
    ('none', 1.0, 0.0, 1.0, 0.0),
    ('sphere x 2e-5 only', 1.0, 2e-5, 1.0, 0.0),
    ('plate x 2e-5 only', 1.0, 0.0, 1.0, 2e-5),
    ('both 2e-5', 1.0, 2e-5, 1.0, 2e-5),
    ('sphere x 2e-5, plate lat 0.5', 1.0, 2e-5, 0.5, 0.0),
    ('sphere x 2e-5, sphere lat 0.5', 0.5, 2e-5, 1.0, 0.0),
]
for mode in ('roll', 'spin'):
    for name, *vals in cases:
        print(f'{mode:4s} {name:32s} angular speed after 0.5 s: {run(mode, *vals):7.3f} rad/s (from 10)')
