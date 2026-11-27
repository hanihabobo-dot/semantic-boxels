# tampura_environments/__init__.py for tampura_environments@4167c35, copied over
# theirs by scripts/setup.sh --tampura.  That commit removed the toy_discrete
# subpackage but still star-imports it, so the package does not import as
# shipped (BF#3 in docs/PAPER_AUDIT.txt).  Only that one import is guarded; the
# others fail loudly, so a missing dependency is never hidden.
from .class_uncertain.env import *
from .find_dice.env import *
from .puck_slide.env import *
from .slam_collect.env import *
from .tool_use.env import *

try:
    from .toy_discrete.env import *
except ModuleNotFoundError as e:
    if e.name != __name__ + '.toy_discrete':
        raise
