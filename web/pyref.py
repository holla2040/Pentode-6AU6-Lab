#!/usr/bin/env python3
"""Golden reference: run the original Blender selfchecks under plain CPython.

The four sim scripts only touch Blender for scene building; `selfcheck()` walks
`_step()` and reads scene properties, nothing else. Stub `bpy`/`bmesh`/`mathutils`
and the physics runs headless in seconds instead of launching Blender.

    python3 -B web/pyref.py            # all four
    python3 -B web/pyref.py curves     # one

The printed numbers are the acceptance target for web/selfcheck.js.
"""
import sys, time, types, os
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LEGACY = "blender-legacy"
SIMS = {
    "pentode": f"{LEGACY}/pentode_sim.py",
    "amp":     f"{LEGACY}/amplifier/pentode_amp_sim.py",
    "cb":      f"{LEGACY}/amplifier-cathode-bias/pentode_cb_amp_sim.py",
    "curves":  f"{LEGACY}/amplifier-plate-characteristics/plate_curves_sim.py",
}


class _Vec(list):
    """Mutable xyz, so `ob.location.z = v` works after `ob.location = (x,y,z)`."""
    for _i, _n in enumerate("xyz"):
        locals()[_n] = property(lambda s, i=_i: s[i],
                                lambda s, v, i=_i: s.__setitem__(i, v))
    del _i, _n


class _Obj:
    """Datablock stand-in: real name + vector attrs, everything else auto-mocked."""
    _VEC = ("location", "rotation_euler", "scale", "delta_location")

    def __init__(self, name=""):
        object.__setattr__(self, "_d", {"name": name})

    def __setattr__(self, k, v):
        if k in self._VEC and isinstance(v, (tuple, list)):
            v = _Vec(v)
        self._d[k] = v

    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        d = object.__getattribute__(self, "_d")
        if k not in d:
            d[k] = _Obj() if k in ("data",) else MagicMock()
        return d[k]


class _Coll:
    """bpy.data.<collection>: name-keyed, so get() finds what new() created."""

    def __init__(self):
        self._m = {}

    def new(self, name, *a, **k):
        self._m[name] = ob = _Obj(name)
        return ob

    def get(self, name, default=None):
        return self._m.get(name, default)

    def remove(self, ob, **k):
        self._m.pop(getattr(ob, "name", None), None)

    def __iter__(self):
        return iter(list(self._m.values()))

    def __len__(self):
        return len(self._m)

    def __getitem__(self, i):
        return list(self._m.values())[i]


def _fresh_bpy():
    """A bpy stub just real enough for build_all() + selfcheck()."""
    bpy = MagicMock()
    for coll in ("objects", "meshes", "curves", "materials", "lights",
                 "cameras", "worlds"):
        setattr(bpy.data, coll, _Coll())
    # Property declarations must yield real values: the sim reads them as floats.
    bpy.props.FloatProperty = lambda **k: float(k.get("default", 0.0))
    bpy.props.IntProperty = lambda **k: int(k.get("default", 0))
    bpy.props.BoolProperty = lambda **k: bool(k.get("default", False))
    bpy.props.StringProperty = lambda **k: str(k.get("default", ""))
    # Operator/Panel are subclassed, so they must be real classes.
    bpy.types.Operator = type("Operator", (), {})
    bpy.types.Panel = type("Panel", (), {})
    # Blender's own Scene members are mocked; unknown names still raise, so a
    # mistyped sim property stays loud instead of silently becoming a mock.
    _API = {"collection", "render", "eevee", "cycles", "world", "view_settings",
            "view_layers", "node_tree", "use_nodes", "unit_settings"}

    def _scene_getattr(self, k):
        if k in _API:
            v = MagicMock()
            object.__setattr__(self, k, v)
            return v
        raise AttributeError(k)

    bpy.types.Scene = type("Scene", (), {
        "frame_current": 1, "frame_start": 1, "frame_end": 1048574,
        "sync_mode": 'FRAME_DROP', "camera": None,
        "property_unset": lambda self, n: None,
        "__getattr__": _scene_getattr,
    })
    # register_ui() assigns the property defaults onto bpy.types.Scene as class
    # attributes; this instance then reads them exactly as Blender's scene does.
    bpy.data.scenes = [bpy.types.Scene()]
    return bpy


def run(key, path):
    # SEED=n re-seeds the sims (they hardcode default_rng(0)) so the Python's
    # OWN run-to-run scatter can be measured and compared against the JS port's.
    seed = os.environ.get("SEED")
    if seed:
        import numpy as np
        orig = getattr(np.random, "_pyref_orig", np.random.default_rng)
        np.random._pyref_orig = orig
        np.random.default_rng = lambda *a, **k: orig(int(seed))

    sys.modules["bpy"] = _fresh_bpy()
    sys.modules["bmesh"] = MagicMock()
    sys.modules["mathutils"] = MagicMock()
    for m in [m for m in sys.modules if m.endswith("_sim")]:
        del sys.modules[m]

    import runpy
    t0 = time.time()
    g = runpy.run_path(os.path.join(ROOT, path), run_name="__main__")
    ok = True
    try:
        g["selfcheck"]()
    except AssertionError as e:
        ok = False
        print(f"  FAIL {key}: {e}")
    print(f"  ({key}: {time.time() - t0:.1f}s)")
    return ok


if __name__ == "__main__":
    want = sys.argv[1:] or list(SIMS)
    bad = [k for k in want if k not in SIMS]
    if bad:
        sys.exit(f"unknown sim {bad}; choose from {list(SIMS)}")
    results = [run(k, SIMS[k]) for k in want]
    sys.exit(0 if all(results) else 1)
