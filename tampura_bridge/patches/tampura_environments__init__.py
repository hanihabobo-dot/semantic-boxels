# Guarded imports (equivalent of the student's declared BF#3 fix): 4167c35
# removed toy_discrete but still star-imports it.
import importlib as _il
import warnings as _w
for _m in ("class_uncertain", "find_dice", "puck_slide", "slam_collect", "tool_use", "toy_discrete"):
    try:
        _mod = _il.import_module(f".{_m}.env", __name__)
    except ModuleNotFoundError as _e:
        _w.warn(f"tampura_environments: {_m} not importable: {_e}")
        continue
    globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("_")})
