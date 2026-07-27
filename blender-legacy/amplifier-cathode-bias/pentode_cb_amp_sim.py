"""Interactive pentode (6AU6) SELF-BIASED RC amplifier for Blender 5.x.

Build standalone:   blender -P pentode_cb_amp_sim.py
Or from a console:  import pentode_cb_amp_sim; pentode_cb_amp_sim.build_all()

The capstone of the tube series -- the complete, textbook-authentic 6AU6
stage with THREE coupled self-regulating loops and no bias supplies at all:

    B+ --[ plate resistor R_L 20k-500k ]-------> plate
    B+ --[ screen resistor R_g2 50k-1M ]-------> screen g2 (+ bypass cap)
    generator (amplitude + DC offset, def. 0) --> control grid g1
    cathode --[ CATHODE RESISTOR R_k 0.1k-5k ]--> common  (+ bypass cap)

The cathode current (Ip + Ig2!) through R_k lifts the cathode; the screen
sags on its own resistor; the plate rides its load line -- three equations
solved together every frame by nested bisection against a live-calibrated,
emission-aware companion model. Two independent bypass checkboxes let you
un-bypass the cathode (series feedback, gain drops) or the screen (shunt-ish
feedback, gain collapses) and watch each mechanism separately.

The scope's green trace is Vg1k (grid-to-cathode): the self-found bias.
Meters are KVL-true on all three resistors. Suppressor toggle still gives
the tetrode secondary-emission demo.

Open the "Pentode CB Amp" tab (N key), Run / Pause, drag sliders live.
Stateful sim: use Reset, don't scrub the timeline.
"""
import math

import bpy
import bmesh
import numpy as np
from mathutils import Vector

# ------------- geometry (Blender units; gaps ~3x a real 6AU6 for visibility) -
PREFIX = "PCBA_"
R_C = 0.15                     # cathode outer radius
#           radius  helix pitch  wire r  rod r  rod angle  wire force  capture r
G1 = dict(r=0.33, pitch=0.085, wire=0.010, rod=0.022, rod_ang=0.0,
          kw=0.002, cap=0.014)
G2 = dict(r=0.55, pitch=0.140, wire=0.012, rod=0.026, rod_ang=90.0,
          kw=0.0006, cap=0.0095)   # capture calibrated to the 6AU6-A datasheet:
                                   # Ic2/Icathode ~ 0.27-0.31 (docs/6AU6A.pdf p3-4)
G3 = dict(r=0.80, pitch=0.340, wire=0.014, rod=0.030, rod_ang=45.0,
          kw=0.002, cap=0.016)
PLATE_A = 1.00                 # superellipse x semi-axis (inradius)
PLATE_B = 0.88                 # flattened y semi-axis (6AU6 plate is squashed)
ABS_K = 0.98                   # absorb just inside the visual wall
Z_HALF = 1.2                   # cathode half height = active region
PARK = (0.0, 0.0, -500.0)      # dead electrons live here, far off camera

# ------------- physics -------------------------------------------------------
POOL = 7000                    # primary electron pool
POOL2 = 1500                   # secondary electron pool (plate emission)
MU2 = 18.0                     # screen mu: cathode field term Vg2/MU2
MUP = 400.0                    # plate mu: plate is almost screened away
C1 = 0.5                       # accel/volt, cathode->g1
C2 = 0.040                     # accel/volt, g1->g2
C3 = 0.030                     # accel/volt, g2->g3 (retarding: -Vg2 dominates)
KNEE_C = 1.2                   # plate's reach into the g2-g3 valley
V_KNEE = 60.0                  # reach saturates above this: flat top + knee below
C4 = 0.055                     # accel/volt, g3->plate
C34 = 0.020                    # tetrode mode: merged g2->plate region
V_SC = 1.5                     # space-charge depression at full cloud [V]
CLOUD_R = 0.30
CLOUD_CAP = 2000.0
EPS = 0.02                     # wire force softening
BAND = 0.08                    # wire force active band around each grid radius
SEC_VTH = 0.8                  # impact speed above which secondaries appear
SEC_YIELD = 0.55               # probability of a secondary per fast hit
SEC_V0 = 0.30                  # secondary launch speed (inward)
E0 = 150.0                     # electrons/frame emitted at T_REF
E_CLAMP = 400.0
T_REF = 1100.0
T_SLOPE = 13000.0
DT = 1.0 / 24.0
SUBSTEPS = 4
GAMMA = 0.7                    # ponytail: mild drag only; heavy drag traps electrons in the g2-g3 valley
V_MAX = 6.0
IP_ALPHA = 0.15
MA_PER_E = 0.02                # mA per electron/frame -- real-tube range so V = I*R works

# ------------- circuit -------------------------------------------------------
FREQ = 0.25                    # generator frequency [Hz]; fixed for now
K_ALPHA = 0.06                 # perveance calibration EMA (slow, out of signal band)
SF_ALPHA = 0.02                # screen-fraction calibration EMA
IK_LOOP_ALPHA = 0.05           # smoothed measured currents feeding calibration
VP_SMOOTH = 0.5                # light smoothing of the solved voltages
SCOPE_N = 192                  # scope buffer (2 cycles at 0.25 Hz, 24 fps)
SCOPE_XS = np.linspace(-1.28, 1.28, SCOPE_N)

_S = {}                        # sim state; (re)filled by reset_electrons()


# ------------- small helpers -------------------------------------------------
def _scene():
    return bpy.data.scenes[0]


def _ob(name):
    return bpy.data.objects.get(PREFIX + name)


def _link(ob):
    _scene().collection.objects.link(ob)
    return ob


def _mesh_obj(name, bm):
    me = bpy.data.meshes.new(PREFIX + name)
    bm.to_mesh(me)
    bm.free()
    return _link(bpy.data.objects.new(PREFIX + name, me))


def _pydata_obj(name, verts, faces):
    me = bpy.data.meshes.new(PREFIX + name)
    me.from_pydata(verts, [], faces)
    me.update()
    return _link(bpy.data.objects.new(PREFIX + name, me))


def _cyl(name, r, depth, loc=(0, 0, 0), segs=48, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs,
                          radius1=r, radius2=r, depth=depth)
    ob = _mesh_obj(name, bm)
    ob.location = loc
    if smooth:
        ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
    return ob


def _poly_curve(name, pts, bevel):
    cu = bpy.data.curves.new(PREFIX + name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for p, (x, y, z) in zip(sp.points, pts):
        p.co = (x, y, z, 1.0)
    return _link(bpy.data.objects.new(PREFIX + name, cu))


def _look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ------------- scene build ---------------------------------------------------
def wipe_scene():
    """Targeted wipe. Never read_factory_settings(): it would kill the MCP addon."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                 bpy.data.lights, bpy.data.cameras):
        for block in [b for b in coll if b.users == 0]:
            coll.remove(block)


def _helix(name, g):
    spt = 24
    turns = int((2.2 / g["pitch"]))
    n = turns * spt
    z0 = -turns * g["pitch"] / 2.0
    pts = [(g["r"] * math.cos(2 * math.pi * i / spt),
            g["r"] * math.sin(2 * math.pi * i / spt),
            z0 + g["pitch"] * i / spt) for i in range(n + 1)]
    _poly_curve(name, pts, g["wire"])
    a = math.radians(g["rod_ang"])
    for suffix, sgn in (("A", 1), ("B", -1)):
        _cyl(name + "Rod" + suffix, g["rod"], 2.66,
             loc=(sgn * g["r"] * math.cos(a), sgn * g["r"] * math.sin(a), 0.03),
             segs=16)


def build_geometry():
    # --- cathode sleeve + heater hairpin (tips out the top)
    _cyl("Cathode", R_C, 2 * Z_HALF)
    pts = [(0.05, 0.0, 1.34), (0.05, 0.0, -1.02)]
    pts += [(0.05 * math.cos(a), 0.0, -1.02 - 0.05 * math.sin(a))
            for a in (math.pi * i / 6 for i in range(1, 6))]
    pts += [(-0.05, 0.0, -1.02), (-0.05, 0.0, 1.34)]
    _poly_curve("Heater", pts, 0.016)

    # --- three grids: control, SCREEN, suppressor
    _helix("Grid1", G1)
    _helix("Grid2", G2)
    _helix("Grid3", G3)

    # --- plate: flattened superellipse sleeve with cutaway window on -Y
    nz, na = 27, 96
    zs = np.linspace(-1.28, 1.28, nz)
    angs = [2 * math.pi * i / na for i in range(na)]

    def srad(th):
        c, s = math.cos(th), math.sin(th)
        return ((abs(c) / PLATE_A) ** 4 + (abs(s) / PLATE_B) ** 4) ** -0.25

    verts = [(srad(a) * math.cos(a), srad(a) * math.sin(a), z)
             for z in zs for a in angs]
    faces = []
    for iz in range(nz - 1):
        zmid = 0.5 * (zs[iz] + zs[iz + 1])
        for ia in range(na):
            ja = (ia + 1) % na
            amid = angs[ia] + math.pi / na
            w = ((amid + math.pi) % (2 * math.pi)) - math.pi
            if abs(w + math.pi / 2) < math.pi / 5 and abs(zmid) < 0.92:
                continue  # the cutaway window
            faces.append((iz * na + ia, iz * na + ja,
                          (iz + 1) * na + ja, (iz + 1) * na + ia))
    plate = _pydata_obj("Plate", verts, faces)
    plate.data.polygons.foreach_set("use_smooth", [True] * len(plate.data.polygons))
    sol = plate.modifiers.new("Sol", 'SOLIDIFY')
    sol.thickness = 0.025

    # --- mica spacer rings
    def ring(name, z):
        segs, r0, r1 = 48, 0.45, 1.36
        vs = [(r0 * math.cos(2 * math.pi * i / segs),
               r0 * math.sin(2 * math.pi * i / segs), z) for i in range(segs)]
        vs += [(r1 * math.cos(2 * math.pi * i / segs),
                r1 * math.sin(2 * math.pi * i / segs), z) for i in range(segs)]
        fs = [(i, (i + 1) % segs, segs + (i + 1) % segs, segs + i)
              for i in range(segs)]
        _pydata_obj(name, vs, fs)

    ring("MicaTop", 1.30)
    ring("MicaBottom", -1.30)

    # --- miniature T-5.5 envelope: straight sides, dome, exhaust nipple on top
    prof = [(0.85, -1.74), (1.34, -1.70), (1.42, -1.30), (1.42, 1.55)]
    prof += [(1.42 * math.cos(a), 1.55 + 0.62 * math.sin(a))
             for a in (math.pi / 2 * i / 6 for i in range(1, 6))]
    prof += [(0.30, 2.16), (0.10, 2.26), (0.055, 2.40), (0.0, 2.44)]
    bm = bmesh.new()
    prev = None
    for r, z in prof:
        v = bm.verts.new((r, 0.0, z))
        if prev is not None:
            bm.edges.new((prev, v))
        prev = v
    bmesh.ops.spin(bm, geom=bm.verts[:] + bm.edges[:], cent=(0, 0, 0),
                   axis=(0, 0, 1), angle=2 * math.pi, steps=48, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    glass = _mesh_obj("Glass", bm)
    glass.data.polygons.foreach_set("use_smooth", [True] * len(glass.data.polygons))

    # --- 7-pin miniature button base: glass wafer + pins with an index gap
    _cyl("Button", 1.34, 0.14, loc=(0, 0, -1.76), segs=48)
    for i in range(7):
        a = math.radians(90 + i * 45)  # 7 pins over 315 deg, gap = key
        _cyl(f"Pin{i}", 0.05, 0.62,
             loc=(0.85 * math.cos(a), 0.85 * math.sin(a), -2.10), segs=12)

    # --- particle banks: primaries (cyan) + secondaries (orange)
    for name, pool, radius in (("Electrons", POOL, 0.009),
                               ("Secondaries", POOL2, 0.011)):
        me = bpy.data.meshes.new(PREFIX + name + "Mesh")
        me.from_pydata([PARK] * pool, [], [])
        me.update()
        eob = _link(bpy.data.objects.new(PREFIX + name, me))
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=radius)
        sph = _mesh_obj(name[:-1] if name.endswith("s") else name, bm)
        sph.parent = eob
        eob.instance_type = 'VERTS'

    _build_scope()
    _build_bench()




# ------------- bench: scope, supply, resistors, generator, wires --------------
def _box(name, scale, loc, mat=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    ob = _mesh_obj(name, bm)
    ob.scale = scale
    ob.location = loc
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def _text(name, body, size, loc, rot, mat, align='LEFT', parent=None):
    ob = _ob(name)
    if ob is None:
        fc = bpy.data.curves.new(PREFIX + name, 'FONT')
        ob = _link(bpy.data.objects.new(PREFIX + name, fc))
    ob.data.body = body
    ob.data.size = size
    ob.data.align_x = align
    ob.location = loc
    ob.rotation_euler = rot
    if not ob.data.materials:
        ob.data.materials.append(mat)
    if parent is not None:
        ob.parent = parent
    return ob


def _build_scope():
    root = _ob("ScopeRoot")
    if root is None:
        root = _link(bpy.data.objects.new(PREFIX + "ScopeRoot", None))
    root.location = (-3.9, 0.9, 1.15)
    root.rotation_euler = (0.0, 0.0, math.radians(48.0))  # face the bench camera

    body = _box("ScopeBody", (3.05, 0.24, 4.40), (0, 0.14, 0),
                _principled("MatScopeBody", (0.10, 0.10, 0.11), rough=0.55))
    body.parent = root
    screen = _pydata_obj("ScopeScreen",
                         [(-1.4, 0, -2.1), (1.4, 0, -2.1),
                          (1.4, 0, 2.1), (-1.4, 0, 2.1)],
                         [(0, 1, 2, 3)])
    screen.parent = root
    screen.data.materials.append(
        _principled("MatScreen", (0.008, 0.02, 0.012), rough=0.4))

    # graticule: 10 rows. Top 5 = input -20..+5 V at 5 V/div; bottom 5 =
    # output, auto-ranged 0-300 or 0-500 V (see _push_traces/_upd_bplus).
    cu = bpy.data.curves.new(PREFIX + "Graticule", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.004
    lines = [((x, -0.01, -2.05), (x, -0.01, 2.05))
             for x in np.arange(-1.2, 1.21, 0.4)]
    lines += [((-1.35, -0.01, z), (1.35, -0.01, z))
              for z in np.arange(-2.0, 2.01, 0.4)]
    for a, b in lines:
        sp = cu.splines.new('POLY')
        sp.points.add(1)
        sp.points[0].co = (*a, 1.0)
        sp.points[1].co = (*b, 1.0)
    grat = _link(bpy.data.objects.new(PREFIX + "Graticule", cu))
    grat.parent = root
    grat.data.materials.append(_emission("MatGraticule", (0.1, 0.45, 0.18), 0.7))

    for name, matname, color, bev in (
            ("TraceIn", "MatTraceIn", (0.2, 1.0, 0.3), 0.010),
            ("TraceOut", "MatTraceOut", (1.0, 0.6, 0.12), 0.012)):
        pts = [(x, -0.02, 0.0) for x in SCOPE_XS]
        tr = _poly_curve(name, pts, bev)
        tr.data.use_fill_caps = False
        tr.parent = root
        tr.data.materials.append(_emission(matname, color, 4.0))

    rot_txt = (math.radians(90), 0, 0)
    green = _emission("MatTraceIn", (0.2, 1.0, 0.3), 4.0)
    amber = _emission("MatTraceOut", (1.0, 0.6, 0.12), 4.0)
    _text("ScopeLblIn", "IN Vg1k  5 V/div", 0.13, (-1.35, -0.03, 2.18), rot_txt,
          green, parent=root)
    _text("ScopeGain", "GAIN --", 0.15, (-0.35, -0.03, 2.18), rot_txt,
          amber, parent=root)
    _text("ScopeLblOut", "OUT Vp  100 V/div", 0.13, (0.45, -0.03, 2.18), rot_txt,
          amber, parent=root)
    _text("ScopeMkInHi", "+5V", 0.10, (-1.36, -0.02, 1.84), rot_txt,
          green, parent=root)
    _text("ScopeMkInLo", "-20V", 0.10, (-1.36, -0.02, 0.06), rot_txt,
          green, parent=root)
    _text("ScopeMkOutHi", "500V", 0.10, (-1.36, -0.02, -0.20), rot_txt,
          amber, parent=root)
    _text("ScopeMkOutLo", "0V", 0.10, (-1.36, -0.02, -1.97), rot_txt,
          amber, parent=root)


# resistor color code, digits 0-9
_BAND_RGB = [(0.02, 0.02, 0.02), (0.28, 0.15, 0.06), (0.75, 0.05, 0.03),
             (0.90, 0.35, 0.02), (0.85, 0.70, 0.03), (0.05, 0.45, 0.08),
             (0.03, 0.15, 0.65), (0.45, 0.10, 0.55), (0.35, 0.35, 0.35),
             (0.90, 0.90, 0.90)]


def _resistor(tag, y):
    """Axial resistor with 4 band rings at height 1.95, axis X, offset y."""
    beige = _principled("MatResistor", (0.80, 0.68, 0.50), rough=0.6)
    wirem = _principled("MatWire", (0.65, 0.55, 0.40), metallic=1.0, rough=0.35)
    for nm, dx, r, dpt in ((f"ResLeadA{tag}", -0.42, 0.014, 0.24),
                           (f"ResLeadB{tag}", 0.42, 0.014, 0.24),
                           (f"ResBody{tag}", 0.0, 0.085, 0.62)):
        ob = _cyl(nm, r, dpt, loc=(2.0 + dx, y, 1.95), segs=24)
        ob.rotation_euler = (0, math.radians(90), 0)
        ob.data.materials.append(wirem if "Lead" in nm else beige)
    for suffix, dx in (("A", -0.20), ("B", -0.10), ("C", 0.00), ("D", 0.22)):
        ob = _cyl(f"Band{suffix}{tag}", 0.092, 0.05, loc=(2.0 + dx, y, 1.95),
                  segs=24)
        ob.rotation_euler = (0, math.radians(90), 0)
        base = (0.75, 0.60, 0.10) if suffix == "D" else (0.3, 0.3, 0.3)
        ob.data.materials.append(
            _principled(f"MatBand{suffix}{tag}", base, rough=0.45))


def _recolor_bands(tag, kohms):
    ohms = max(float(kohms), 0.001) * 1000.0
    exp = int(math.floor(math.log10(ohms))) - 1
    d = int(round(ohms / 10 ** exp))
    if d >= 100:
        d //= 10
        exp += 1
    for suffix, digit in (("A", d // 10), ("B", d % 10), ("C", exp)):
        m = bpy.data.materials.get(PREFIX + f"MatBand{suffix}{tag}")
        if m:
            bsdf = m.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (*_BAND_RGB[digit], 1.0)


def _upd_rl(self, context):
    _recolor_bands("RL", self.pcb_rl)


def _upd_rg2(self, context):
    _recolor_bands("RG2", self.pcb_rg2)


def _upd_rk(self, context):
    _recolor_bands("RK", self.pcb_rk)


def _upd_kbypass(self, context):
    show = self.pcb_k_bypass
    for nm in ("BypCapK", "WireCapK1", "WireCapK2", "CapKLbl"):
        ob = _ob(nm)
        if ob:
            ob.hide_viewport = not show
            ob.hide_render = not show


def _upd_bplus(self, context):
    ob = _ob("PSUVal")
    if ob:
        ob.data.body = f"{self.pcb_bplus:.0f} V"
    # OUT channel auto-range: 0-300 V below 300 V B+, 0-500 V above
    vmax = 300 if self.pcb_bplus <= 300.0 else 500
    for name, want in (("ScopeLblOut", f"OUT Vp  {vmax // 5} V/div"),
                       ("ScopeMkOutHi", f"{vmax}V")):
        t = _ob(name)
        if t and t.data.body != want:
            t.data.body = want


def _upd_bypass(self, context):
    show = self.pcb_g2_bypass
    for nm in ("BypCap", "WireCapTop", "WireCapGnd", "CapLbl"):
        ob = _ob(nm)
        if ob:
            ob.hide_viewport = not show
            ob.hide_render = not show


def _build_bench():
    wirem = _principled("MatWire", (0.65, 0.55, 0.40), metallic=1.0, rough=0.35)
    dark = _principled("MatPSU", (0.10, 0.12, 0.16), rough=0.5)
    red = _principled("MatPostR", (0.65, 0.05, 0.04), rough=0.4)
    blk = _principled("MatPostB", (0.02, 0.02, 0.02), rough=0.4)
    lbl = _emission("MatLabel", (0.85, 0.9, 1.0), 1.5)
    rot_txt = (math.radians(90), 0, 0)

    # --- B+ supply, right of the tube
    _box("PSU", (1.05, 0.75, 0.95), (3.2, 0.5, -1.32), dark)
    _cyl("PSUPostP", 0.05, 0.28, loc=(2.95, 0.35, -0.72), segs=12).data \
        .materials.append(red)
    _cyl("PSUPostN", 0.05, 0.28, loc=(3.45, 0.35, -0.72), segs=12).data \
        .materials.append(blk)
    _text("PSULbl", "B+", 0.30, (3.2, 0.115, -1.20), rot_txt, lbl, align='CENTER')
    _text("PSUVal", "300 V", 0.22, (3.2, 0.115, -1.62), rot_txt, lbl,
          align='CENTER')

    # --- plate load resistor R_L (front) and screen resistor R_g2 (behind)
    _resistor("RL", 0.30)
    _resistor("RG2", 1.30)
    _text("RLLbl", "RL", 0.16, (2.0, 0.30, 2.14), rot_txt, lbl, align='CENTER')
    _text("RG2Lbl", "Rg2", 0.16, (2.0, 1.30, 2.14), rot_txt, lbl, align='CENTER')

    # --- screen bypass capacitor: g2 node down to the common bus
    cap = _cyl("BypCap", 0.10, 0.38, loc=(0.9, 1.30, 1.50), segs=24)
    cap.data.materials.append(_principled("MatCap", (0.15, 0.25, 0.55),
                                          rough=0.35))
    _text("CapLbl", "C", 0.14, (1.03, 1.30, 1.44), rot_txt, lbl)
    _poly_curve("WireCapTop", [(0.9, 1.30, 1.95), (0.9, 1.30, 1.70)],
                0.018).data.materials.append(wirem)
    _poly_curve("WireCapGnd", [(0.9, 1.30, 1.30), (0.9, 1.30, -2.62),
                               (0.9, -1.35, -2.62)],
                0.018).data.materials.append(wirem)

    # --- signal generator, front-left
    _box("Gen", (0.95, 0.60, 0.75), (-3.0, -0.8, -1.42), dark)
    _cyl("GenPostP", 0.045, 0.24, loc=(-2.78, -0.80, -0.95), segs=12).data \
        .materials.append(red)
    _cyl("GenPostN", 0.045, 0.24, loc=(-3.22, -0.80, -0.95), segs=12).data \
        .materials.append(blk)
    sine = [(-3.0 + (i / 16.0 - 0.5) * 0.55, -1.115,
             -1.40 + math.sin(2 * math.pi * i / 16.0) * 0.13)
            for i in range(17)]
    _poly_curve("GenSine", sine, 0.014).data.materials.append(
        _emission("MatSine", (0.3, 0.9, 1.0), 2.0))
    _text("GenLbl", "GEN 0.25 Hz", 0.16, (-3.0, -1.115, -1.72), rot_txt, lbl,
          align='CENTER')

    # --- wiring
    wires = {
        "WirePlate": [(0.99, 0.20, 1.26), (0.99, 0.20, 1.95),
                      (1.20, 0.30, 1.95), (1.58, 0.30, 1.95)],
        "WireRtoPSU": [(2.42, 0.30, 1.95), (2.95, 0.30, 1.95),
                       (2.95, 0.35, -0.60)],
        "WireRg2Feed": [(2.95, 0.30, 1.55), (2.95, 1.30, 1.55),
                        (2.95, 1.30, 1.95), (2.42, 1.30, 1.95)],
        "WireRg2Out": [(1.58, 1.30, 1.95), (0.0, 1.30, 1.95),
                       (0.0, 0.55, 1.40)],
        "WirePSUGnd": [(3.45, 0.35, -0.62), (3.45, 0.35, -2.62),
                       (2.30, -1.45, -2.62)],
        "WireGenGrid": [(-2.78, -0.80, -0.85), (-2.78, -0.80, -0.55),
                        (-1.55, -0.95, -0.55), (-1.55, -0.95, 1.75),
                        (-0.33, 0.0, 1.75), (-0.33, 0.0, 1.40)],
        "WireGenGnd": [(-3.22, -0.80, -0.85), (-3.22, -0.80, -2.62),
                       (-2.00, -1.45, -2.62)],
    }
    for nm, pts in wires.items():
        _poly_curve(nm, pts, 0.022).data.materials.append(wirem)

    # --- cathode-bias network: ground bar, Rk (vertical, live bands), cap
    _box("GndBar", (4.8, 0.12, 0.07), (0.15, -1.45, -2.64), dark)
    _text("GndLbl", "COMMON", 0.13, (-0.4, -1.53, -2.86), rot_txt, lbl)
    beige = _principled("MatResistor", (0.80, 0.68, 0.50), rough=0.6)
    for nm, dz, r, dpt in (("ResLeadKA", 0.42, 0.014, 0.24),
                           ("ResLeadKB", -0.42, 0.014, 0.24),
                           ("ResBodyK", 0.0, 0.085, 0.62)):
        ob = _cyl(nm, r, dpt, loc=(1.65, -1.45, -2.02 + dz), segs=24)
        ob.data.materials.append(wirem if "Lead" in nm else beige)
    for suffix, dz in (("A", 0.20), ("B", 0.10), ("C", 0.00), ("D", -0.22)):
        ob = _cyl("BandRK" + suffix, 0.092, 0.05,
                  loc=(1.65, -1.45, -2.02 + dz), segs=24)
        base = (0.75, 0.60, 0.10) if suffix == "D" else (0.3, 0.3, 0.3)
        ob.data.materials.append(
            _principled("MatBandRK" + suffix, base, rough=0.45))
    _text("RkLbl", "Rk", 0.15, (1.85, -1.48, -2.06), rot_txt, lbl)
    _poly_curve("WireCathRk", [(1.10, -0.75, -1.80), (1.65, -1.45, -1.58),
                               (1.65, -1.45, -1.66)],
                0.022).data.materials.append(wirem)
    _poly_curve("WireRkGnd", [(1.65, -1.45, -2.38), (1.65, -1.45, -2.62)],
                0.022).data.materials.append(wirem)
    capk = _cyl("BypCapK", 0.10, 0.38, loc=(2.45, -1.45, -2.02), segs=24)
    capk.data.materials.append(_principled("MatCap", (0.15, 0.25, 0.55),
                                           rough=0.35))
    _text("CapKLbl", "Ck", 0.13, (2.60, -1.48, -2.06), rot_txt, lbl)
    _poly_curve("WireCapK1", [(1.65, -1.45, -1.60), (2.45, -1.45, -1.60),
                              (2.45, -1.45, -1.82)],
                0.020).data.materials.append(wirem)
    _poly_curve("WireCapK2", [(2.45, -1.45, -2.22), (2.45, -1.45, -2.62)],
                0.020).data.materials.append(wirem)


def _push_traces():
    """Scope traces. IN top half: g1 voltage, -20..+5 V at 5 V/div.
    OUT bottom half: plate voltage, auto-ranged 0-300 / 0-500 V per B+."""
    bp = float(getattr(_scene(), "pcb_bplus", 300.0))
    out_vmax = 300.0 if bp <= 300.0 else 500.0
    for name, buf, z0, upv, lo, hi in (
            ("TraceIn", _S["vg_buf"], 1.6, 0.08, 0.0, 2.0),
            ("TraceOut", _S["vp_buf"], -2.0, 2.0 / out_vmax, -2.0, 0.0)):
        ob = _ob(name)
        if ob is None:
            continue
        arr = np.empty((SCOPE_N, 4), np.float32)
        arr[:, 0] = SCOPE_XS
        arr[:, 1] = -0.02
        arr[:, 2] = np.clip(z0 + buf * upv, lo, hi)
        arr[:, 3] = 1.0
        sp = ob.data.splines[0]
        sp.points.foreach_set("co", arr.ravel())
        ob.data.update_tag()


# ------------- materials / look ----------------------------------------------
def _principled(name, color, metallic=0.0, rough=0.5, alpha=1.0, blended=False,
                spec=None):
    m = bpy.data.materials.get(PREFIX + name)
    if m is None:
        m = bpy.data.materials.new(PREFIX + name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Alpha"].default_value = alpha
    if spec is not None:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if blended:
        m.surface_render_method = 'BLENDED'
    return m


def _emission(name, color, strength):
    m = bpy.data.materials.get(PREFIX + name)
    if m is None:
        m = bpy.data.materials.new(PREFIX + name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def _assign(obname, mat):
    ob = _ob(obname)
    if ob is None:
        return
    if ob.data.materials:
        ob.data.materials[0] = mat
    else:
        ob.data.materials.append(mat)


def _light(name, loc, energy, size, color=(1.0, 1.0, 1.0), kind='AREA',
           shadow=True):
    ob = _ob(name)
    if ob is None:
        ld = bpy.data.lights.new(PREFIX + name, kind)
        ob = _link(bpy.data.objects.new(PREFIX + name, ld))
    ob.data.energy = energy
    if kind == 'AREA':
        ob.data.size = size
    else:
        ob.data.shadow_soft_size = size
    ob.data.color = color
    if hasattr(ob.data, "use_shadow"):
        ob.data.use_shadow = shadow
    ob.location = loc
    _look_at(ob, (0, 0, 0))
    return ob


def _glow(T):
    """Thermal glow ramp for 300..1300 K (deep red -> orange)."""
    x = max(0.0, (T - 600.0) / 700.0)
    color = (1.0, 0.15 + 0.35 * x, 0.02 + 0.12 * x)
    return color, x


def _apply_heat(scene=None):
    sc = scene or _scene()
    T = getattr(sc, "pcb_heater_t", T_REF)
    color, x = _glow(T)
    hm = bpy.data.materials.get(PREFIX + "MatHeater")
    if hm:
        em = hm.node_tree.nodes.get("Emission")
        if em:
            em.inputs["Color"].default_value = (*color, 1.0)
            em.inputs["Strength"].default_value = 16.0 * x ** 3
    cm = bpy.data.materials.get(PREFIX + "MatCathode")
    if cm:
        bsdf = cm.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 2.5 * x ** 3
    cl = _ob("Cath_Light")
    if cl:
        cl.data.color = color
        cl.data.energy = 9.0 * x ** 3


def build_materials():
    _assign("Cathode", _principled("MatCathode", (0.75, 0.73, 0.68), rough=0.65))
    _assign("Heater", _emission("MatHeater", (1.0, 0.5, 0.2), 6.0))
    copper = _principled("MatCopper", (0.72, 0.43, 0.28), metallic=1.0, rough=0.32)
    silver = _principled("MatSilver", (0.75, 0.77, 0.80), metallic=1.0, rough=0.28)
    steel = _principled("MatSteel", (0.42, 0.44, 0.47), metallic=1.0, rough=0.45)
    for nm in ("Grid1", "Grid1RodA", "Grid1RodB"):
        _assign(nm, copper)          # control grid: copper (photo 2)
    for nm in ("Grid2", "Grid2RodA", "Grid2RodB"):
        _assign(nm, silver)          # SCREEN: bright silver so it stands out
    for nm in ("Grid3", "Grid3RodA", "Grid3RodB"):
        _assign(nm, steel)           # suppressor: dull steel (photo 1)
    _assign("Plate", _principled("MatPlate", (0.055, 0.055, 0.062),
                                 metallic=0.35, rough=0.68))
    mica = _principled("MatMica", (0.82, 0.77, 0.62), rough=0.55,
                       alpha=0.45, blended=True)
    _assign("MicaTop", mica)
    _assign("MicaBottom", mica)
    glass = _principled("MatGlass", (0.9, 0.95, 1.0), rough=0.12,
                        alpha=0.055, blended=True, spec=0.15)
    _assign("Glass", glass)
    for m in (glass, mica):  # don't let see-through parts black out the inside
        if hasattr(m, "use_transparent_shadow"):
            m.use_transparent_shadow = True
    _assign("Button", _principled("MatButton", (0.55, 0.58, 0.60), rough=0.35,
                                  alpha=0.5, blended=True))
    nickel = _principled("MatPin", (0.6, 0.6, 0.62), metallic=1.0, rough=0.35)
    for i in range(7):
        _assign(f"Pin{i}", nickel)
    _assign("Electron", _emission("MatElectron", (0.35, 0.85, 1.0), 5.0))
    _assign("Secondarie", _emission("MatSecondary", (1.0, 0.42, 0.10), 7.0))

    # world + lights
    w = bpy.data.worlds[0] if bpy.data.worlds else bpy.data.worlds.new("World")
    _scene().world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.004, 0.005, 0.008, 1.0)
        bg.inputs["Strength"].default_value = 1.0
    _light("Key_Light", (-3.2, -4.2, 3.2), energy=80.0, size=2.5)
    _light("Rim_Light", (2.5, 3.2, 1.2), energy=40.0, size=3.0,
           color=(1.0, 0.85, 0.7))
    # shadow off: sits inside the cathode sleeve; fakes the sleeve's own glow
    _light("Cath_Light", (0.0, 0.0, 0.3), energy=3.0, size=0.14, kind='POINT',
           shadow=False)

    sc = _scene()
    sc.render.engine = 'BLENDER_EEVEE'
    if hasattr(sc.eevee, "use_raytracing"):
        sc.eevee.use_raytracing = False
    sc.render.fps = 24
    sc.frame_start = 1
    sc.frame_end = 1048574
    sc.render.resolution_x = 1440
    sc.render.resolution_y = 1080
    sc.sync_mode = 'FRAME_DROP'
    _setup_viewports()
    _apply_heat()


def _setup_viewports():
    for w in bpy.data.window_managers[0].windows:
        for a in w.screen.areas:
            if a.type == 'VIEW_3D':
                sp = a.spaces.active
                sp.shading.type = 'RENDERED'
                sp.overlay.show_overlays = False
                sp.clip_start = 0.005
                sp.clip_end = 300.0


# ------------- physics engine ------------------------------------------------
def reset_electrons():
    for tag, pool in (("", POOL), ("2", POOL2)):
        _S["pos" + tag] = np.zeros((pool, 3))
        _S["vel" + tag] = np.zeros((pool, 3))
        _S["alive" + tag] = np.zeros(pool, bool)
        _S["draw" + tag] = np.empty((pool, 3), np.float32)
        _S["draw" + tag][:] = PARK
    _S["rng"] = np.random.default_rng(0)
    _S["ip"] = 0.0
    _S["ig2"] = 0.0
    _S["cloud"] = 0
    _S["g1_hits"] = 0
    _S["fails"] = 0
    _S["last_txt"] = ""
    _S["t"] = 0.0
    _S["vp"] = float(getattr(_scene(), "pcb_bplus", 300.0))   # tube off ->
    _S["vg2"] = _S["vp"]                                        # both at B+
    _S["vk"] = 0.0                                              # no lift
    _S["vg1"] = float(getattr(_scene(), "pcb_sig_dc", -3.0))
    _S["khat"] = _S.get("khat", 0.0)    # calibration persists across resets
    _S["khat_slow"] = _S.get("khat_slow", 0.0)
    _S["d15_loop"] = _S.get("d15_loop", 0.0)
    _S["cf_slow"] = 0.5
    _S["vk_byp"] = None
    _S["vg2gnd_byp"] = None
    _S["sfrac"] = _S.get("sfrac", 0.28)   # datasheet Ic2/Ik
    _S["ik_loop"] = 0.0
    _S["ig2_loop"] = 0.0
    _S["ip_show"] = 0.0
    _S["ig2_show"] = 0.0
    _S["vg_buf"] = np.full(SCOPE_N, _S["vg1"])
    _S["gen_buf"] = np.full(SCOPE_N, float(getattr(_scene(), "pcb_sig_dc", 0.0)))
    _S["vp_buf"] = np.full(SCOPE_N, _S["vp"])
    _S["gain_txt"] = "--"
    _push_draw()
    _push_traces()


def _push_draw():
    for tag, name in (("", "Electrons"), ("2", "Secondaries")):
        ob = _ob(name)
        if ob is None:
            continue
        me = ob.data
        me.vertices.foreach_set("co", _S["draw" + tag].ravel())
        me.update()
        me.update_tag()


def _radial_accel(r, Vg1, Vg2, Vp, cf, sup):
    """Region field: force per unit charge on an electron, + = outward."""
    a = np.empty_like(r)
    m1 = r < G1["r"]
    m2 = (r >= G1["r"]) & (r < G2["r"])
    a[m1] = C1 * (Vg1 + Vg2 / MU2 + Vp / MUP - V_SC * cf)
    a[m2] = C2 * (Vg2 - Vg1)
    if sup:
        m3 = (r >= G2["r"]) & (r < G3["r"])
        a[m3] = C3 * (KNEE_C * min(Vp, V_KNEE) - Vg2)
        a[r >= G3["r"]] = C4 * Vp
    else:
        a[r >= G2["r"]] = C34 * (Vp - Vg2)   # tetrode: g3 out of circuit
    return a


def _plate_s(x, y):
    """Superellipse coordinate: >= 1 means at/inside the plate wall."""
    return (np.abs(x) / (ABS_K * PLATE_A)) ** 4 + (np.abs(y) / (ABS_K * PLATE_B)) ** 4


def _step(scene):
    S = _S
    if "pos" not in S:
        reset_electrons()
    rng = S["rng"]
    T = scene.pcb_heater_t
    sup = scene.pcb_suppressor

    p, v, al = S["pos"], S["vel"], S["alive"]
    p2, v2, al2 = S["pos2"], S["vel2"], S["alive2"]

    r_all = np.hypot(p[:, 0], p[:, 1])
    cloud = int(np.count_nonzero(al & (r_all < CLOUD_R)))
    if cloud > CLOUD_CAP and S["ip"] + S.get("ig2", 0.0) < 1.0:
        # TRUE space-charge lockup: cloud at cap with zero throughput means
        # emission stays gated (lam *= 1-cf) and the trapped electrons can
        # never drain past the grid-wire barrier -- the tube latches dead.
        # Reclaim them into the cathode to break the latch. A full cloud
        # WITH current flowing is normal space-charge-limited operation and
        # is deliberately left alone.
        idx = np.flatnonzero(al & (r_all < CLOUD_R))
        al[idx[:int(cloud - CLOUD_CAP) + 25]] = False
        cloud = int(CLOUD_CAP)
    cf = min(cloud / CLOUD_CAP, 1.2)
    S["cf_slow"] = S.get("cf_slow", 0.5) + 0.02 * (cf - S.get("cf_slow", 0.5))

    # --- the circuit: SELF-BIAS pentode RC stage. Cathode current (Ip+Ig2)
    # through Rk lifts the cathode; screen and plate ride their own load
    # lines. Three coupled equations, solved ALGEBRAICALLY every frame by
    # nested bisection (measured-current servo loops ring against the
    # electron transit delay -- the recurring lesson of this project).
    S["t"] += DT
    Vgen = scene.pcb_sig_dc + scene.pcb_sig_amp * math.sin(
        2 * math.pi * FREQ * S["t"])
    Bp = scene.pcb_bplus
    RL = scene.pcb_rl
    RG2 = scene.pcb_rg2
    RK = scene.pcb_rk

    emis = min(1.0, math.exp(-T_SLOPE * (1.0 / T - 1.0 / T_REF)))

    def _model(vp, vg2, vg1, cfx=None):
        d = max(0.0, vg1 + vg2 / MU2 + vp / MUP
                - V_SC * (cf if cfx is None else cfx))
        ik = S["khat"] * emis * d ** 1.5
        ip = ik * (1.0 - S["sfrac"]) * min(1.0, vp / V_KNEE) ** 0.8
        return ip, ik - ip

    def _solve_vp(vg2, vg1, vk, cfx=None):
        lo, hi = 0.0, Bp
        for _ in range(18):
            mid = 0.5 * (lo + hi)
            if Bp - RL * MA_PER_E * _model(mid, vg2, vg1, cfx)[0] - vk - mid > 0.0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def _solve_vg2(vg1, vk, vg2gnd_fixed=None, cfx=None):
        if vg2gnd_fixed is not None:            # bypassed screen: frozen node
            return max(vg2gnd_fixed - vk, 0.0)
        lo2, hi2 = 0.0, Bp
        for _ in range(18):
            mid2 = 0.5 * (lo2 + hi2)
            ig2_m = _model(_solve_vp(mid2, vg1, vk, cfx), mid2, vg1, cfx)[1]
            if Bp - RG2 * MA_PER_E * ig2_m - vk - mid2 > 0.0:
                lo2 = mid2
            else:
                hi2 = mid2
        return 0.5 * (lo2 + hi2)

    def _solve_all(vgen_x, vk_fixed=None, vg2gnd_fixed=None, cfx=None):
        """(vk, vg2_tube, vp_tube, ip, ig2), honoring bypass freezes."""
        def at_vk(vk):
            vg1 = vgen_x - vk
            vg2 = _solve_vg2(vg1, vk, vg2gnd_fixed, cfx)
            vp = _solve_vp(vg2, vg1, vk, cfx)
            ip, ig2 = _model(vp, vg2, vg1, cfx)
            return vg2, vp, ip, ig2
        if vk_fixed is not None:
            vg2, vp, ip, ig2 = at_vk(vk_fixed)
            return vk_fixed, vg2, vp, ip, ig2
        lo3, hi3 = 0.0, min(60.0, Bp)
        for _ in range(16):
            mid3 = 0.5 * (lo3 + hi3)
            _, _, ip_m, ig2_m = at_vk(mid3)
            if (ip_m + ig2_m) * MA_PER_E * RK - mid3 > 0.0:
                lo3 = mid3
            else:
                hi3 = mid3
        vk = 0.5 * (lo3 + hi3)
        vg2, vp, ip, ig2 = at_vk(vk)
        return vk, vg2, vp, ip, ig2

    # DC reference point, solved with SLOW calibration + space charge: it
    # anchors the calibration and provides the voltages the bypass
    # capacitors hold (live khat/cf jitter must not shake "held" nodes)
    S["khat_slow"] += 0.02 * (S["khat"] - S["khat_slow"])
    _k_live = S["khat"]
    S["khat"] = S["khat_slow"]
    vk_dc, vg2_dc, vp_dc, ip_dc, ig2_dc = _solve_all(scene.pcb_sig_dc,
                                                     cfx=S["cf_slow"])
    S["khat"] = _k_live
    d_dc = max(0.0, (scene.pcb_sig_dc - vk_dc) + vg2_dc / MU2
               + vp_dc / MUP - V_SC * S["cf_slow"])
    # Down-corrections always allowed (see the plate-characteristics build:
    # a poisoned-high khat starves the op point, closes the healthy-drive
    # gate, and can otherwise never heal).
    # unbiased perveance: averaged current over equally-averaged drive^1.5
    d_now = max(0.0, S["vg1"] + S["vg2"] / MU2 + S["vp"] / MUP - V_SC * cf)
    S["d15_loop"] += IK_LOOP_ALPHA * (d_now ** 1.5 - S["d15_loop"])
    if emis > 0.2 and d_dc > 0.5 and S["d15_loop"] > 0.3:
        k_inst = S["ik_loop"] / (emis * S["d15_loop"])
        # down-corrections fire ONLY on the lockup signature (cloud pinned
        # at cap): during warmup ramps k_inst reads low (current lags the
        # drive through the transit delay) and would wrongly crush khat
        down_ok = k_inst < S["khat"] and cloud >= CLOUD_CAP - 25
        if down_ok or (d_dc > 1.5 and S["ik_loop"] > 5.0):
            a = 0.15 if S["khat"] < 0.7 * k_inst else K_ALPHA
            S["khat"] += a * (k_inst - S["khat"])
        if d_dc > 1.5 and S["ik_loop"] > 5.0 and vp_dc > 80.0:
            r_inst = S["ig2_loop"] / S["ik_loop"]
            S["sfrac"] += SF_ALPHA * (min(max(r_inst, 0.15), 0.42) - S["sfrac"])

    # fully-bypassed nodes HOLD (capacitor supplies the ripple current);
    # the slow filters are just the caps recharging when sliders move
    if scene.pcb_k_bypass:
        if S["vk_byp"] is None:
            S["vk_byp"] = vk_dc
        S["vk_byp"] += 0.008 * (vk_dc - S["vk_byp"])
        vk_freeze = S["vk_byp"]
    else:
        S["vk_byp"] = None
        vk_freeze = None
    if scene.pcb_g2_bypass:
        if S["vg2gnd_byp"] is None:
            S["vg2gnd_byp"] = vg2_dc + vk_dc
        S["vg2gnd_byp"] += 0.008 * ((vg2_dc + vk_dc) - S["vg2gnd_byp"])
        vg2gnd_freeze = S["vg2gnd_byp"]
    else:
        S["vg2gnd_byp"] = None
        vg2gnd_freeze = None
    vk_sol, vg2_sol, vp_sol, _, _ = _solve_all(Vgen, vk_freeze, vg2gnd_freeze)

    S["vk"] += VP_SMOOTH * (vk_sol - S["vk"])
    S["vg2"] += VP_SMOOTH * (vg2_sol - S["vg2"])
    S["vp"] += VP_SMOOTH * (vp_sol - S["vp"])
    Vk = S["vk"]
    Vg2 = S["vg2"]
    Vp = S["vp"]
    Vg1 = Vgen - Vk          # grid-to-cathode: what the tube actually feels
    S["vg1"] = Vg1

    # --- thermionic emission, throttled by space charge
    lam = min(E0 * math.exp(-T_SLOPE * (1.0 / T - 1.0 / T_REF)), E_CLAMP)
    lam *= max(0.0, 1.0 - cf)
    k = int(rng.poisson(lam)) if lam > 1e-6 else 0
    dead = np.flatnonzero(~al)
    k = min(k, dead.size)
    if k:
        idx = dead[:k]
        th = rng.uniform(0, 2 * np.pi, k)
        ct, st = np.cos(th), np.sin(th)
        rr = R_C + 0.006
        p[idx, 0] = rr * ct
        p[idx, 1] = rr * st
        p[idx, 2] = rng.uniform(-1.0, 1.0, k)
        vr = 0.2 * math.sqrt(T / T_REF) + np.abs(rng.normal(0, 0.06, k))
        vt = rng.normal(0, 0.06, k)
        v[idx, 0] = vr * ct - vt * st
        v[idx, 1] = vr * st + vt * ct
        v[idx, 2] = rng.normal(0, 0.06, k)
        al[idx] = True

    grids = [(G1, Vg1), (G2, Vg2)] + ([(G3, 0.0)] if sup else [])
    h = DT / SUBSTEPS
    hits_p = 0          # primary plate arrivals
    sec_to_screen = 0   # secondaries collected by the screen (Ip-, Ig2+)
    hits_g2 = 0         # primaries intercepted by screen wires
    hits_g1 = 0
    spawn_x = []        # queued secondary spawns (pos, unit_radial)

    def integrate(P, V, A, secondary):
        """One substep for a bank. Returns kill bookkeeping via closures."""
        nonlocal hits_p, sec_to_screen, hits_g2, hits_g1
        ii = np.flatnonzero(A)
        if ii.size == 0:
            return
        x, y, z = P[ii, 0], P[ii, 1], P[ii, 2]
        r = np.maximum(np.hypot(x, y), 1e-6)
        ux, uy = x / r, y / r
        ar = _radial_accel(r, Vg1, Vg2, Vp, cf, sup)
        az = np.zeros_like(ar)
        for g, Vw in grids:
            dr = r - g["r"]
            band = np.abs(dr) < BAND
            if band.any() and abs(Vw) > 1e-3:
                dz = ((z[band] + g["pitch"] / 2) % g["pitch"]) - g["pitch"] / 2
                d2 = dr[band] ** 2 + dz ** 2 + EPS * EPS
                d = np.sqrt(d2)
                f = g["kw"] * (-Vw) / d2
                ar[band] += f * dr[band] / d
                az[band] += f * dz / d
        vx = V[ii, 0] + ar * ux * h
        vy = V[ii, 1] + ar * uy * h
        vz = V[ii, 2] + az * h
        damp = 1.0 - GAMMA * h
        vx *= damp
        vy *= damp
        vz *= damp
        sp = np.sqrt(vx * vx + vy * vy + vz * vz)
        fcl = np.minimum(1.0, V_MAX / np.maximum(sp, 1e-9))
        vx *= fcl
        vy *= fcl
        vz *= fcl
        nx, ny, nz2 = x + vx * h, y + vy * h, z + vz * h
        V[ii, 0], V[ii, 1], V[ii, 2] = vx, vy, vz
        P[ii, 0], P[ii, 1], P[ii, 2] = nx, ny, nz2

        nr = np.hypot(nx, ny)
        on_plate = _plate_s(nx, ny) >= 1.0
        reab = (nr <= R_C + 0.002) & (nx * vx + ny * vy < 0)
        zout = np.abs(nz2) > Z_HALF
        kill = on_plate | reab | zout
        # contact capture on every physical grid wire
        wire_hit = {}
        for g, Vw in grids:
            dzw = ((nz2 + g["pitch"] / 2) % g["pitch"]) - g["pitch"] / 2
            wd2 = (nr - g["r"]) ** 2 + dzw ** 2
            wh = (wd2 < g["cap"] ** 2) & ~kill
            wire_hit[id(g)] = wh
            kill |= wh
        if secondary:
            sec_to_screen += int(np.count_nonzero(wire_hit.get(id(G2), False)))
            # plate return and other losses are silent
        else:
            n_pl = int(np.count_nonzero(on_plate))
            hits_p += n_pl
            hits_g2 += int(np.count_nonzero(wire_hit.get(id(G2), False)))
            hits_g1 += int(np.count_nonzero(wire_hit.get(id(G1), False)))
            if n_pl:
                # Monte-Carlo secondary emission off the plate
                sel = np.flatnonzero(on_plate)
                spd = sp[sel] if sel.size else np.empty(0)
                fast = spd > SEC_VTH
                lucky = rng.random(sel.size) < SEC_YIELD
                for j in sel[fast & lucky]:
                    spawn_x.append((nx[j], ny[j], nz2[j]))
        A[ii[kill]] = False

    for _ in range(SUBSTEPS):
        integrate(p, v, al, secondary=False)
        integrate(p2, v2, al2, secondary=True)

    # --- launch queued secondaries just inside the plate wall, aimed inward
    if spawn_x:
        dead2 = np.flatnonzero(~al2)
        for (sx, sy, sz), slot in zip(spawn_x, dead2):
            s = _plate_s(np.array([sx]), np.array([sy]))[0]
            kk = (0.93 / max(s, 1e-6)) ** 0.25
            rx, ry = sx * kk, sy * kk
            rr = max(math.hypot(rx, ry), 1e-6)
            p2[slot] = (rx, ry, sz)
            jit = rng.normal(0, 0.08, 2)
            v2[slot] = (-SEC_V0 * rx / rr + jit[0],
                        -SEC_V0 * ry / rr + jit[1],
                        rng.normal(0, 0.05))
            al2[slot] = True

    S["ip"] = (1.0 - IP_ALPHA) * S["ip"] + IP_ALPHA * (hits_p - sec_to_screen)
    S["ig2"] = (1.0 - IP_ALPHA) * S["ig2"] + IP_ALPHA * (hits_g2 + sec_to_screen)
    S["ik_loop"] += IK_LOOP_ALPHA * ((hits_p + hits_g2) - S["ik_loop"])
    S["ig2_loop"] += IK_LOOP_ALPHA * ((hits_g2 + sec_to_screen) - S["ig2_loop"])
    S["cloud"] = cloud
    S["g1_hits"] = hits_g1

    # --- draw + meter
    for tag, (pp, aa) in {"": (p, al), "2": (p2, al2)}.items():
        S["draw" + tag][:] = PARK
        aidx = np.flatnonzero(aa)
        if aidx.size:
            S["draw" + tag][aidx] = pp[aidx].astype(np.float32)
    _push_draw()
    # --- scope + meters (currents shown are the resistor currents: KVL-true)
    S["vg_buf"][:-1] = S["vg_buf"][1:]
    S["vg_buf"][-1] = Vg1
    S["gen_buf"][:-1] = S["gen_buf"][1:]
    S["gen_buf"][-1] = Vgen
    S["vp_buf"][:-1] = S["vp_buf"][1:]
    S["vp_buf"][-1] = Vp + Vk    # scope probe reads plate-to-GROUND
    _push_traces()
    S["ip_show"] = (Bp - (Vp + Vk)) / max(RL, 1e-6)     # resistor currents,
    S["ig2_show"] = (Bp - (Vg2 + Vk)) / max(RG2, 1e-6)  # KVL-true
    if scene.pcb_sig_amp > 0.02:
        # stage gain from the GENERATOR terminal; the green Vg1k trace shows
        # how cathode feedback shrinks the tube's actual drive
        g = float(np.std(S["vp_buf"]) / max(float(np.std(S["gen_buf"])), 1e-6))
        S["gain_txt"] = f"{g:.1f}x"
    else:
        S["gain_txt"] = "--"
    txt = (f"B+ {Bp:.0f}V  Vg2 {Vg2 + Vk:.0f}V  Vp {Vp + Vk:.0f}V\n"
           f"Ip {S['ip_show']:.2f}mA   Ig2 {S['ig2_show']:.2f}mA\n"
           f"Vk {Vk:.2f}V   Vg1k {Vg1:+.1f}V (self-bias)\n"
           f"Gain = {S['gain_txt']}")
    if txt != S["last_txt"]:
        mo = _ob("Meter")
        if mo:
            mo.data.body = txt
        go = _ob("ScopeGain")
        if go:
            go.data.body = f"GAIN {S['gain_txt']}"
        S["last_txt"] = txt
    if scene.frame_current % 4 == 0:
        for w in bpy.data.window_managers[0].windows:
            for a in w.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()


def amp_pcb_frame_change(scene, depsgraph=None):
    try:
        _step(scene)
        _S["fails"] = 0
    except Exception:
        import traceback
        traceback.print_exc()
        _S["fails"] = _S.get("fails", 0) + 1
        if _S["fails"] > 5:
            _remove_handlers()
            print("pentode_cb_amp_sim: handler removed after repeated errors")


def _remove_handlers():
    # strip every tube project's handler: one sim per Blender session
    for hnd in list(bpy.app.handlers.frame_change_pre):
        if getattr(hnd, "__name__", "").startswith(("tri_", "pen_", "amp_")):
            bpy.app.handlers.frame_change_pre.remove(hnd)


def register_sim():
    _remove_handlers()
    bpy.app.handlers.frame_change_pre.append(amp_pcb_frame_change)
    if "pos" not in _S:
        reset_electrons()


# ------------- UI ------------------------------------------------------------
def _upd_heat(self, context):
    _apply_heat(self)


def _upd_glass(self, context):
    g = _ob("Glass")
    if g:
        g.hide_viewport = not self.pcb_show_glass
        g.hide_render = g.hide_viewport


def _upd_suppressor(self, context):
    show = self.pcb_suppressor
    for nm in ("Grid3", "Grid3RodA", "Grid3RodB"):
        ob = _ob(nm)
        if ob:
            ob.hide_viewport = not show
            ob.hide_render = not show


class PCBAMP_OT_reset(bpy.types.Operator):
    bl_idname = "pcbamp.reset"
    bl_label = "Reset"
    bl_description = "Clear all electrons and restart the meters"

    def execute(self, context):
        reset_electrons()
        return {'FINISHED'}


class PCBAMP_OT_play(bpy.types.Operator):
    bl_idname = "pcbamp.play"
    bl_label = "Run / Pause"
    bl_description = "Toggle the simulation (animation playback)"

    def execute(self, context):
        bpy.ops.screen.animation_play()
        return {'FINISHED'}


class PCBAMP_OT_view(bpy.types.Operator):
    bl_idname = "pcbamp.view"
    bl_label = "View"
    bl_description = "Jump to a preset camera"
    which: bpy.props.StringProperty(default="OVER")

    def execute(self, context):
        set_view(self.which)
        return {'FINISHED'}


class PCBAMP_PT_main(bpy.types.Panel):
    bl_label = "Pentode CB Amp"
    bl_idname = "PCBAMP_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pentode CB Amp"

    def draw(self, context):
        s = context.scene
        L = self.layout
        col = L.column(align=True)
        col.prop(s, "pcb_heater_t", slider=True)
        col.prop(s, "pcb_bplus", slider=True)
        col.prop(s, "pcb_rl", slider=True)
        col.prop(s, "pcb_rg2", slider=True)
        col.prop(s, "pcb_rk", slider=True)
        col.separator()
        col.prop(s, "pcb_sig_amp", slider=True)
        col.prop(s, "pcb_sig_dc", slider=True)
        L.prop(s, "pcb_g2_bypass")
        L.prop(s, "pcb_k_bypass")
        L.prop(s, "pcb_suppressor")
        row = L.row(align=True)
        row.operator("pcbamp.play", icon='PLAY')
        row.operator("pcbamp.reset", icon='FILE_REFRESH')
        row = L.row(align=True)
        for label, key in (("Bench", "OVER"), ("Top", "TOP"), ("Inside", "INSIDE")):
            row.operator("pcbamp.view", text=label).which = key
        L.prop(s, "pcb_show_glass")
        box = L.box()
        box.label(text=f"Vp: {_S.get('vp', 0.0):.0f} V   "
                       f"Ip: {_S.get('ip_show', 0.0):.2f} mA")
        box.label(text=f"Vg2: {_S.get('vg2', 0.0):.0f} V   "
                       f"Ig2: {_S.get('ig2_show', 0.0):.2f} mA")
        box.label(text=f"Vk: {_S.get('vk', 0.0):.2f} V   "
                       f"Vg1k: {_S.get('vg1', 0.0):+.1f} V")
        box.label(text=f"Gain: {_S.get('gain_txt', '--')}")
        box.label(text=f"Space-charge cloud: {_S.get('cloud', 0)} e-")
        if not s.pcb_suppressor:
            box.label(text="TETRODE MODE (no suppressor)", icon='ERROR')


def _cam(name, loc, target=None, lens=50.0, clip=0.01, ortho=None):
    ob = _ob(name)
    if ob is None:
        cd = bpy.data.cameras.new(PREFIX + name)
        ob = _link(bpy.data.objects.new(PREFIX + name, cd))
    cd = ob.data
    if ortho is not None:
        cd.type = 'ORTHO'
        cd.ortho_scale = ortho
    else:
        cd.type = 'PERSP'
        cd.lens = lens
    cd.clip_start = clip
    cd.clip_end = 200.0
    cd.passepartout_alpha = 1.0
    ob.location = loc
    if target is not None:
        _look_at(ob, target)
    return ob


def set_view(which):
    names = {"TOP": "Cam_Top", "INSIDE": "Cam_Inside", "OVER": "Cam_Over"}
    ob = _ob(names.get(which, "Cam_Over"))
    if ob is None:
        return
    _scene().camera = ob
    for w in bpy.data.window_managers[0].windows:
        for a in w.screen.areas:
            if a.type == 'VIEW_3D':
                r3d = a.spaces.active.region_3d
                r3d.view_perspective = 'CAMERA'
                r3d.view_camera_zoom = 28.0
                r3d.view_camera_offset = (0.0, 0.0)


def register_ui():
    Sc = bpy.types.Scene
    for name in ("pcb_heater_t", "pcb_bplus", "pcb_rl", "pcb_rg2", "pcb_rk",
                 "pcb_sig_amp", "pcb_sig_dc", "pcb_g2_bypass", "pcb_k_bypass",
                 "pcb_suppressor", "pcb_show_glass"):
        if hasattr(Sc, name):
            try:
                delattr(Sc, name)
            except Exception:
                pass
    Sc.pcb_heater_t = bpy.props.FloatProperty(
        name="Heater temp (K)", min=300.0, max=1300.0, default=1100.0,
        step=100, precision=0, update=_upd_heat,
        description="Cathode temperature: sets thermionic emission (cloud density)")
    Sc.pcb_bplus = bpy.props.FloatProperty(
        name="B+ supply (V)", min=150.0, max=500.0, default=300.0,
        step=100, precision=0, update=_upd_bplus,
        description="HV supply feeding plate (through RL) and screen (through Rg2)")
    Sc.pcb_rl = bpy.props.FloatProperty(
        name="Plate resistor (kOhm)", min=20.0, max=500.0, default=100.0,
        step=100, precision=0, update=_upd_rl,
        description="Load between B+ and plate; Vp = B+ - Ip*RL. Bands update live")
    Sc.pcb_rg2 = bpy.props.FloatProperty(
        name="Screen resistor (kOhm)", min=50.0, max=1000.0, default=470.0,
        step=100, precision=0, update=_upd_rg2,
        description="Feeds the screen from B+; Vg2 = B+ - Ig2*Rg2 (solved live)")
    Sc.pcb_sig_amp = bpy.props.FloatProperty(
        name="Signal amplitude (Vpk)", min=0.0, max=8.0, default=0.5,
        step=10, precision=1,
        description="Sine on g1; pentode gain is high, start small")
    Sc.pcb_sig_dc = bpy.props.FloatProperty(
        name="Generator DC offset (V)", min=-10.0, max=5.0, default=0.0,
        step=10, precision=1,
        description="Leave at 0: the cathode resistor biases the stage itself")
    Sc.pcb_rk = bpy.props.FloatProperty(
        name="Cathode resistor (kOhm)", min=0.1, max=5.0, default=1.0,
        step=10, precision=1, update=_upd_rk,
        description="Self-bias: Vk = (Ip+Ig2)*Rk lifts the cathode. Bands live")
    Sc.pcb_k_bypass = bpy.props.BoolProperty(
        name="Cathode bypass capacitor", default=True, update=_upd_kbypass,
        description="Bypassed: full gain. Unbypassed: Rk applies series "
                    "negative feedback and gain drops")
    Sc.pcb_g2_bypass = bpy.props.BoolProperty(
        name="Screen bypass capacitor", default=True, update=_upd_bypass,
        description="Bypassed: screen held steady at its average (full gain). "
                    "Unbypassed: Vg2 ripples with the signal and gain drops")
    Sc.pcb_suppressor = bpy.props.BoolProperty(
        name="Suppressor connected", default=True, update=_upd_suppressor,
        description="Uncheck for tetrode mode: secondary electrons (orange) "
                    "escape the plate to the screen when Vp < Vg2")
    Sc.pcb_show_glass = bpy.props.BoolProperty(
        name="Show glass envelope", default=True, update=_upd_glass)

    for cls_name in ("PCBAMP_OT_reset", "PCBAMP_OT_play",
                     "PCBAMP_OT_view", "PCBAMP_PT_main"):
        old = getattr(bpy.types, cls_name, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass
    for cls in (PCBAMP_OT_reset, PCBAMP_OT_play, PCBAMP_OT_view, PCBAMP_PT_main):
        bpy.utils.register_class(cls)

    # top camera inside the envelope just below the top mica: cross-section view
    _cam("Cam_Top", (0, 0, 1.26), ortho=2.9, clip=0.003)
    # 135 deg azimuth: the only angle clear of all three rod pairs (0/90/45)
    _cam("Cam_Inside", (-0.64, 0.64, 0.05), target=(0.1, -0.1, 0.0),
         lens=13.0, clip=0.004)
    _cam("Cam_Over", (6.6, -7.6, 3.6), target=(-0.25, 0.2, 0.25), lens=34.0)
    _scene().camera = _ob("Cam_Over")

    if not _ob("Meter"):
        fc = bpy.data.curves.new(PREFIX + "Meter", 'FONT')
        fc.body = "B+ 300V   Vg2 300V\nVp 300V   Ip 0.00mA\nIg2 0.00mA   Vg1 -3.0V\nGain = --"
        fc.size = 0.20
        fc.align_x = 'CENTER'
        mo = _link(bpy.data.objects.new(PREFIX + "Meter", fc))
        mo.location = (0.0, -1.58, -2.02)
        mo.rotation_euler = (math.radians(90), 0, 0)
        mo.data.materials.append(_emission("MatMeter", (0.3, 1.0, 0.5), 3.0))

    _apply_heat()
    # sync toggles/labels with current prop values
    _upd_suppressor(_scene(), None)
    _upd_glass(_scene(), None)
    _upd_rl(_scene(), None)
    _upd_rg2(_scene(), None)
    _upd_rk(_scene(), None)
    _upd_bplus(_scene(), None)
    _upd_bypass(_scene(), None)
    _upd_kbypass(_scene(), None)


# ------------- entry points --------------------------------------------------
def build_all():
    wipe_scene()
    build_geometry()
    build_materials()
    register_ui()
    register_sim()
    reset_electrons()
    set_view("OVER")


def selfcheck():
    """The capstone stage: three coupled self-bias loops, all behaviors."""
    sc = _scene()

    def run(T, dc, A, bp, rl, rg2, rk, frames, sup=True, g2b=True, kb=True):
        sc.pcb_heater_t, sc.pcb_sig_dc, sc.pcb_sig_amp = T, dc, A
        sc.pcb_bplus, sc.pcb_rl, sc.pcb_rg2, sc.pcb_rk = bp, rl, rg2, rk
        sc.pcb_suppressor, sc.pcb_g2_bypass, sc.pcb_k_bypass = sup, g2b, kb
        reset_electrons()
        for _ in range(frames):
            _step(sc)
        return _S

    S = run(500, 0, 0, 300, 100, 470, 1.0, 100)   # cold: all rails float
    assert S["vp"] > 0.97 * 300 and S["vg2"] > 0.95 * 300 and S["vk"] < 0.2, (
        f"cold: Vp={S['vp']:.0f} Vg2={S['vg2']:.0f} Vk={S['vk']:.2f}")

    S = run(1100, 0, 0, 300, 100, 470, 1.0, 700, g2b=False, kb=False)  # triple self-bias
    vp0, vg20, vk0 = S["vp"], S["vg2"], S["vk"]
    ip0 = (S["ik_loop"] - S["ig2_loop"]) * MA_PER_E
    ig20 = S["ig2_loop"] * MA_PER_E
    assert 0.3 < vk0 < 3.5, f"cathode self-bias off: Vk={vk0:.2f}"
    assert 45 < vg20 < 230, f"screen op point off: Vg2={vg20:.0f}"
    assert 0.30 * 300 < vp0 + vk0 < 0.93 * 300, f"plate op off: {vp0 + vk0:.0f}"
    kvl_p = abs(300.0 - (vp0 + vk0) - ip0 * 100.0)
    kvl_s = abs(300.0 - (vg20 + vk0) - ig20 * 470.0)
    kvl_k = abs(vk0 - (ip0 + ig20) * 1.0)
    assert kvl_p < 30.0, f"plate KVL off {kvl_p:.1f} V"
    assert kvl_s < 40.0, f"screen KVL off {kvl_s:.1f} V"
    assert kvl_k < 0.8, f"cathode KVL off {kvl_k:.2f} V"
    assert float(np.std(S["vp_buf"][-24:])) < 6.0, "ringing"

    vp_neg = run(1100, -3, 0, 300, 100, 470, 1.0, 380, g2b=False, kb=False)["vp"]
    vp_pos = run(1100, 2, 0, 300, 100, 470, 1.0, 380, g2b=False, kb=False)["vp"]
    assert vp_neg > vp0 > vp_pos, "not inverting"

    S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900)  # all bypassed: full gain
    g_full = float(np.std(S["vp_buf"]) / max(float(np.std(S["gen_buf"])), 1e-6))
    corr = float(np.corrcoef(S["gen_buf"], S["vp_buf"])[0, 1])
    assert 10.0 < g_full < 70.0, f"gain {g_full:.1f} out of range"
    assert corr < -0.7, f"not inverted (corr={corr:.2f})"

    S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900, kb=False)  # Rk feedback
    g_kun = float(np.std(S["vp_buf"]) / max(float(np.std(S["gen_buf"])), 1e-6))
    assert g_full > 1.10 * g_kun, (
        f"cathode feedback should cut gain: {g_full:.1f} !> 1.10x{g_kun:.1f}")

    S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900, g2b=False)  # screen feedback
    g_sun = float(np.std(S["vp_buf"]) / max(float(np.std(S["gen_buf"])), 1e-6))
    assert g_full > 1.25 * g_sun, (
        f"screen feedback should cut gain: {g_full:.1f} !> 1.25x{g_sun:.1f}")

    S = run(1100, 0, 0.5, 300, 300, 470, 1.0, 900)  # pentode: gain ~ RL
    g300 = float(np.std(S["vp_buf"]) / max(float(np.std(S["gen_buf"])), 1e-6))
    assert g300 > 1.5 * g_full, f"gain not scaling with RL: {g300:.1f}"

    # overdrive: with the screen bypassed (frozen ~136 V) cutoff needs only
    # ~-8 V, so the TOP rails clean at B+; the bottom soft-limits near 160 V
    # because the knee factor caps the plate current the load line can pull.
    S = run(1100, 0, 8, 300, 100, 470, 1.0, 900)
    assert float(np.max(S["vp_buf"][-192:])) > 0.95 * 300, "top not railing"
    assert float(np.min(S["vp_buf"][-192:])) < 180.0, "no bottom compression"

    S = run(1100, 0, 0, 300, 500, 1000, 5.0, 340)   # stability at maxima
    assert float(np.std(S["vp_buf"][-24:])) < 20.0, "unstable at max R values"

    print(f"selfcheck OK  self-bias Vk={vk0:.2f}V Vg2={vg20:.0f}V "
          f"Vp={vp0 + vk0:.0f}V (dc=0) | gain full {g_full:.1f}x, "
          f"Rk-unbyp {g_kun:.1f}x, g2-unbyp {g_sun:.1f}x, RL300k {g300:.1f}x "
          f"(corr {corr:.2f})")
    return True


if __name__ == "__main__":
    # Fresh scene (blender -P pentode_cb_amp_sim.py): full build.
    # Run Script inside a saved .blend: just re-register handler/UI.
    if _ob("Cathode") is None:
        build_all()
    else:
        register_ui()
        register_sim()
        reset_electrons()
