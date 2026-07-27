"""Interactive pentode (6AU6) simulation for Blender 5.x.

Build standalone:   blender -P pentode_sim.py
Or from a console:  import pentode_sim; pentode_sim.build_all()

Open the "Pentode" tab in the 3D-view sidebar (N key):
  Heater temp    -> thermionic emission rate, launch speed, heater/cathode glow
  Grid 1 voltage -> control grid: retarding field, cutoff
  SCREEN voltage -> g2: does the actual pulling; sets plate current almost
                    independently of plate voltage (pentode flatness)
  Plate voltage  -> extraction beyond the suppressor; near-flat Ip above the knee
  Suppressor connected -> uncheck for TETRODE MODE: secondary electrons knocked
                    off the plate (orange) stream back to the screen when
                    Vp < Vg2 — the tetrode kink the suppressor exists to fix.

Derived from the verified triode_sim.py (Blender-Triode-6SN7). Physics is
pedagogical: 1-D radial region fields + local grid-wire terms, mean-field
space charge, Monte-Carlo secondary emission. Not TCAD.

The integrator is a frame_change_pre handler: press play (or the Run button)
and drag sliders live. It is stateful — scrubbing the timeline does not rewind
the electrons; use Reset instead.
"""
import math

import bpy
import bmesh
import numpy as np
from mathutils import Vector

# ------------- geometry (Blender units; gaps ~3x a real 6AU6 for visibility) -
PREFIX = "PEN_"
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
MA_PER_E = 0.2                 # meter scale: mA per electron/frame

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
    T = getattr(sc, "pen_heater_t", T_REF)
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
    _push_draw()


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
    Vg1 = scene.pen_g1_v
    Vg2 = scene.pen_g2_v
    Vp = scene.pen_plate_v
    T = scene.pen_heater_t
    sup = scene.pen_suppressor

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
    S["cloud"] = cloud
    S["g1_hits"] = hits_g1

    # --- draw + meter
    for tag, (pp, aa) in {"": (p, al), "2": (p2, al2)}.items():
        S["draw" + tag][:] = PARK
        aidx = np.flatnonzero(aa)
        if aidx.size:
            S["draw" + tag][aidx] = pp[aidx].astype(np.float32)
    _push_draw()
    txt = (f"Ip  = {S['ip'] * MA_PER_E:.1f} mA\n"
           f"Ig2 = {S['ig2'] * MA_PER_E:.1f} mA")
    if txt != S["last_txt"]:
        mo = _ob("Meter")
        if mo:
            mo.data.body = txt
        S["last_txt"] = txt
    if scene.frame_current % 4 == 0:
        for w in bpy.data.window_managers[0].windows:
            for a in w.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()


def pen_frame_change(scene, depsgraph=None):
    try:
        _step(scene)
        _S["fails"] = 0
    except Exception:
        import traceback
        traceback.print_exc()
        _S["fails"] = _S.get("fails", 0) + 1
        if _S["fails"] > 5:
            _remove_handlers()
            print("pentode_sim: handler removed after repeated errors")


def _remove_handlers():
    for hnd in list(bpy.app.handlers.frame_change_pre):
        if getattr(hnd, "__name__", "").startswith(("pen_", "tri_")):
            bpy.app.handlers.frame_change_pre.remove(hnd)


def register_sim():
    _remove_handlers()
    bpy.app.handlers.frame_change_pre.append(pen_frame_change)
    if "pos" not in _S:
        reset_electrons()


# ------------- UI ------------------------------------------------------------
def _upd_heat(self, context):
    _apply_heat(self)


def _upd_glass(self, context):
    g = _ob("Glass")
    if g:
        g.hide_viewport = not self.pen_show_glass
        g.hide_render = g.hide_viewport


def _upd_suppressor(self, context):
    show = self.pen_suppressor
    for nm in ("Grid3", "Grid3RodA", "Grid3RodB"):
        ob = _ob(nm)
        if ob:
            ob.hide_viewport = not show
            ob.hide_render = not show


class PENTODE_OT_reset(bpy.types.Operator):
    bl_idname = "pentode.reset"
    bl_label = "Reset"
    bl_description = "Clear all electrons and restart the meters"

    def execute(self, context):
        reset_electrons()
        return {'FINISHED'}


class PENTODE_OT_play(bpy.types.Operator):
    bl_idname = "pentode.play"
    bl_label = "Run / Pause"
    bl_description = "Toggle the simulation (animation playback)"

    def execute(self, context):
        bpy.ops.screen.animation_play()
        return {'FINISHED'}


class PENTODE_OT_view(bpy.types.Operator):
    bl_idname = "pentode.view"
    bl_label = "View"
    bl_description = "Jump to a preset camera"
    which: bpy.props.StringProperty(default="OVER")

    def execute(self, context):
        set_view(self.which)
        return {'FINISHED'}


class PENTODE_PT_main(bpy.types.Panel):
    bl_label = "Pentode"
    bl_idname = "PENTODE_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pentode"

    def draw(self, context):
        s = context.scene
        L = self.layout
        col = L.column(align=True)
        col.prop(s, "pen_heater_t", slider=True)
        col.prop(s, "pen_g1_v", slider=True)
        col.prop(s, "pen_g2_v", slider=True)
        col.prop(s, "pen_plate_v", slider=True)
        L.prop(s, "pen_suppressor")
        row = L.row(align=True)
        row.operator("pentode.play", icon='PLAY')
        row.operator("pentode.reset", icon='FILE_REFRESH')
        row = L.row(align=True)
        for label, key in (("Top", "TOP"), ("Inside", "INSIDE"), ("Overview", "OVER")):
            row.operator("pentode.view", text=label).which = key
        L.prop(s, "pen_show_glass")
        box = L.box()
        box.label(text=f"Plate current Ip: {_S.get('ip', 0.0) * MA_PER_E:.1f} mA")
        box.label(text=f"Screen current Ig2: {_S.get('ig2', 0.0) * MA_PER_E:.1f} mA")
        box.label(text=f"Space-charge cloud: {_S.get('cloud', 0)} e-")
        if _S.get("g1_hits", 0):
            box.label(text=f"g1 interception: {_S['g1_hits']} e-/frame")
        if not s.pen_suppressor:
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
    for name in ("pen_heater_t", "pen_g1_v", "pen_g2_v", "pen_plate_v",
                 "pen_suppressor", "pen_show_glass"):
        if hasattr(Sc, name):
            try:
                delattr(Sc, name)
            except Exception:
                pass
    Sc.pen_heater_t = bpy.props.FloatProperty(
        name="Heater temp (K)", min=300.0, max=1300.0, default=1100.0,
        step=100, precision=0, update=_upd_heat,
        description="Cathode temperature: sets thermionic emission (cloud density)")
    Sc.pen_g1_v = bpy.props.FloatProperty(
        name="Grid 1 voltage (V)", min=-20.0, max=10.0, default=0.0,
        step=10, precision=1,
        description="Control grid: negative repels electrons back (cutoff)")
    Sc.pen_g2_v = bpy.props.FloatProperty(
        name="Screen voltage (V)", min=0.0, max=200.0, default=150.0,
        step=100, precision=0,
        description="Screen grid g2: accelerates electrons and screens the "
                    "cathode from the plate — it sets the current")
    Sc.pen_plate_v = bpy.props.FloatProperty(
        name="Plate voltage (V)", min=0.0, max=300.0, default=250.0,
        step=100, precision=0,
        description="Above the knee, Ip barely depends on this — pentode flatness")
    Sc.pen_suppressor = bpy.props.BoolProperty(
        name="Suppressor connected", default=True, update=_upd_suppressor,
        description="Uncheck for tetrode mode: secondary electrons (orange) "
                    "escape the plate to the screen when Vp < Vg2")
    Sc.pen_show_glass = bpy.props.BoolProperty(
        name="Show glass envelope", default=True, update=_upd_glass)

    for cls_name in ("PENTODE_OT_reset", "PENTODE_OT_play",
                     "PENTODE_OT_view", "PENTODE_PT_main"):
        old = getattr(bpy.types, cls_name, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass
    for cls in (PENTODE_OT_reset, PENTODE_OT_play, PENTODE_OT_view, PENTODE_PT_main):
        bpy.utils.register_class(cls)

    # top camera inside the envelope just below the top mica: cross-section view
    _cam("Cam_Top", (0, 0, 1.26), ortho=2.9, clip=0.003)
    # 135 deg azimuth: the only angle clear of all three rod pairs (0/90/45)
    _cam("Cam_Inside", (-0.64, 0.64, 0.05), target=(0.1, -0.1, 0.0),
         lens=13.0, clip=0.004)
    _cam("Cam_Over", (4.0, -4.2, 2.5), target=(0, 0, -0.12), lens=30.0)
    _scene().camera = _ob("Cam_Over")

    if not _ob("Meter"):
        fc = bpy.data.curves.new(PREFIX + "Meter", 'FONT')
        fc.body = "Ip  = 0.0 mA\nIg2 = 0.0 mA"
        fc.size = 0.24
        fc.align_x = 'CENTER'
        mo = _link(bpy.data.objects.new(PREFIX + "Meter", fc))
        mo.location = (0.0, -1.58, -1.98)
        mo.rotation_euler = (math.radians(90), 0, 0)
        mo.data.materials.append(_emission("MatMeter", (0.3, 1.0, 0.5), 3.0))

    _apply_heat()
    # sync toggles with current prop values
    _upd_suppressor(_scene(), None)
    _upd_glass(_scene(), None)


# ------------- entry points --------------------------------------------------
def build_all():
    wipe_scene()
    build_geometry()
    build_materials()
    register_ui()
    register_sim()
    reset_electrons()
    set_view("OVER")


def selfcheck(frames=54):
    """Smallest runnable check: the tube must behave like a 6AU6 pentode."""
    sc = _scene()

    def run(T, Vg1, Vg2, Vp, sup=True):
        sc.pen_heater_t, sc.pen_g1_v, sc.pen_g2_v, sc.pen_plate_v = T, Vg1, Vg2, Vp
        sc.pen_suppressor = sup
        reset_electrons()
        for _ in range(frames):
            _step(sc)
        return (_S["ip"] * MA_PER_E, _S["ig2"] * MA_PER_E,
                int(np.count_nonzero(_S["alive"])))

    ip, _, alive = run(500, 0, 150, 250)
    assert alive < 20 and ip < 0.5, f"cold cathode leaks: Ip={ip:.2f}"
    ip, _, _ = run(1100, 0, 0, 300)
    assert ip < 1.0, f"screen off but Ip={ip:.2f} — plate should not reach cathode"
    ip, _, alive = run(1100, -8, 150, 250)
    assert ip < 1.0, f"cutoff leaks: Ip={ip:.2f}"
    assert alive > 300, f"no cloud at cutoff: {alive}"
    ip_hi, ig2_hi, _ = run(1100, 0, 150, 250)
    assert ip_hi > 4.0, f"no conduction: Ip={ip_hi:.2f}"
    assert ig2_hi > 0.5, f"no screen current: Ig2={ig2_hi:.2f}"
    ip_lo, _, _ = run(1100, 0, 150, 80)
    flat = abs(ip_hi - ip_lo) / ip_hi
    assert flat < 0.30, f"not pentode-flat: Ip(250)={ip_hi:.1f} Ip(80)={ip_lo:.1f}"
    ip_knee, ig2_knee, _ = run(1100, 0, 150, 15)
    assert ip_knee < 0.6 * ip_lo, f"no knee: Ip(15)={ip_knee:.1f} vs Ip(80)={ip_lo:.1f}"
    assert ig2_knee > ig2_hi, f"Ig2 should spike below the knee"
    ip_tet, ig2_tet, _ = run(1100, 0, 150, 60, sup=False)
    ip_pen, _, _ = run(1100, 0, 150, 60, sup=True)
    assert ip_tet < 0.7 * ip_pen, (
        f"tetrode kink missing: Ip(tet)={ip_tet:.1f} vs Ip(pen)={ip_pen:.1f}")
    print(f"selfcheck OK  Ip(250)={ip_hi:.1f} Ip(80)={ip_lo:.1f} "
          f"Ip(15)={ip_knee:.1f} | Ig2 nom={ig2_hi:.1f} knee={ig2_knee:.1f} | "
          f"kink: {ip_tet:.1f} vs {ip_pen:.1f} mA")
    return True


if __name__ == "__main__":
    # Fresh scene (blender -P pentode_sim.py): full build.
    # Run Script inside a saved .blend: just re-register handler/UI.
    if _ob("Cathode") is None:
        build_all()
    else:
        register_ui()
        register_sim()
        reset_electrons()
