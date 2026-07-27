// The 6AU6 itself: procedural geometry, materials, lights, cameras.
//
// Every coordinate is copied verbatim from pentode_sim.py's build_geometry() /
// build_materials(). That only works because we set Object3D.DEFAULT_UP to
// +Z at boot (main.js) so the scene shares Blender's axis convention.
//
// Blender's node default_value colours are LINEAR, and three's working colour
// space is linear-srgb, so Color.setRGB(r, g, b) takes them unchanged.

import * as THREE from "three";
import { R_C, G1, G2, G3, PLATE_A, PLATE_B, Z_HALF, POOL, POOL2, PARK }
  from "./engine.js";

const lin = (r, g, b) => new THREE.Color().setRGB(r, g, b);

// ------------- material helpers ----------------------------------------------
export function principled(color, { metalness = 0.0, roughness = 0.5,
                                    alpha = 1.0, glow = 0.0,
                                    glowColor = null } = {}) {
  const m = new THREE.MeshStandardMaterial({
    color: lin(...color), metalness, roughness,
    transparent: alpha < 1.0, opacity: alpha,
  });
  if (alpha < 1.0) { m.depthWrite = false; m.side = THREE.DoubleSide; }
  if (glow > 0.0) {
    m.emissive = lin(...(glowColor || color));
    m.emissiveIntensity = glow;
  }
  return m;
}

/** Blender's Emission shader: emissiveIntensity is unclamped and linear, so
 *  strengths > 1 survive into the tone mapper exactly as EEVEE's did. */
export function emission(color, strength) {
  return new THREE.MeshStandardMaterial({
    color: 0x000000, emissive: lin(...color), emissiveIntensity: strength,
    roughness: 1.0, metalness: 0.0,
  });
}

// ------------- geometry helpers ----------------------------------------------
const cyl = (r, depth, segs = 48) =>
  new THREE.CylinderGeometry(r, r, depth, segs).rotateX(Math.PI / 2);

/** _poly_curve: a polyline swept by a round bevel. */
function polyTube(pts, bevel, closed = false) {
  const curve = new THREE.CatmullRomCurve3(
    pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])), closed, "catmullrom", 0);
  return new THREE.TubeGeometry(curve, Math.max(pts.length * 2, 8), bevel, 8,
                                closed);
}

function mesh(geo, mat, name, parent) {
  const o = new THREE.Mesh(geo, mat);
  o.name = name;
  if (parent) parent.add(o);
  return o;
}

/** One grid: helical wire plus its two support rods. */
function helix(g, mat, parent, name) {
  const spt = 24;
  const turns = Math.trunc(2.2 / g.pitch);
  const n = turns * spt;
  const z0 = -turns * g.pitch / 2.0;
  const pts = [];
  for (let i = 0; i <= n; i++) {
    pts.push([g.r * Math.cos(2 * Math.PI * i / spt),
              g.r * Math.sin(2 * Math.PI * i / spt),
              z0 + g.pitch * i / spt]);
  }
  const grp = new THREE.Group();
  grp.name = name;
  parent.add(grp);
  mesh(polyTube(pts, g.wire), mat, name + "Wire", grp);
  const a = g.rod_ang * Math.PI / 180;
  for (const sgn of [1, -1]) {
    const rod = mesh(cyl(g.rod, 2.66, 16), mat, name + "Rod", grp);
    rod.position.set(sgn * g.r * Math.cos(a), sgn * g.r * Math.sin(a), 0.03);
  }
  return grp;
}

/** The flattened superellipse plate, with the cutaway window on -Y. */
function plateGeometry() {
  const nz = 27, na = 96;
  const zs = [];
  for (let i = 0; i < nz; i++) zs.push(-1.28 + (2.56 * i) / (nz - 1));
  const angs = [];
  for (let i = 0; i < na; i++) angs.push(2 * Math.PI * i / na);
  const srad = (th) => {
    const c = Math.abs(Math.cos(th)) / PLATE_A;
    const s = Math.abs(Math.sin(th)) / PLATE_B;
    return Math.pow(c * c * c * c + s * s * s * s, -0.25);
  };
  const verts = [];
  for (const z of zs) {
    for (const a of angs) {
      const r = srad(a);
      verts.push(r * Math.cos(a), r * Math.sin(a), z);
    }
  }
  const idx = [];
  for (let iz = 0; iz < nz - 1; iz++) {
    const zmid = 0.5 * (zs[iz] + zs[iz + 1]);
    for (let ia = 0; ia < na; ia++) {
      const ja = (ia + 1) % na;
      const amid = angs[ia] + Math.PI / na;
      const w = ((amid + Math.PI) % (2 * Math.PI)) - Math.PI;
      if (Math.abs(w + Math.PI / 2) < Math.PI / 5 && Math.abs(zmid) < 0.92) {
        continue;                       // the cutaway window
      }
      const a0 = iz * na + ia, b0 = iz * na + ja;
      const a1 = (iz + 1) * na + ia, b1 = (iz + 1) * na + ja;
      idx.push(a0, b0, b1, a0, b1, a1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;                           // SOLIDIFY -> material side: DoubleSide
}

/** Miniature T-5.5 envelope: straight sides, dome, exhaust nipple on top. */
function glassGeometry() {
  const prof = [[0.85, -1.74], [1.34, -1.70], [1.42, -1.30], [1.42, 1.55]];
  for (let i = 1; i <= 5; i++) {
    const a = (Math.PI / 2) * i / 6;
    prof.push([1.42 * Math.cos(a), 1.55 + 0.62 * Math.sin(a)]);
  }
  prof.push([0.30, 2.16], [0.10, 2.26], [0.055, 2.40], [0.0, 2.44]);
  return new THREE.LatheGeometry(prof.map(([r, z]) => new THREE.Vector2(r, z)),
                                 48).rotateX(Math.PI / 2);
}

/** A soft round dot for the electron point sprites. */
function discTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0.0, "rgba(255,255,255,1)");
  grd.addColorStop(0.55, "rgba(255,255,255,1)");
  grd.addColorStop(1.0, "rgba(255,255,255,0)");
  g.fillStyle = grd;
  g.beginPath();
  g.arc(32, 32, 32, 0, Math.PI * 2);
  g.fill();
  const tex = new THREE.CanvasTexture(c);
  // No mipmaps. A minified sprite has its alpha averaged down by the mip
  // chain, which drops it under alphaTest and discards the fragment — the
  // electrons vanished entirely at the bench camera's distance.
  tex.generateMipmaps = false;
  tex.minFilter = THREE.LinearFilter;
  return tex;
}

/** A Points bank fed straight from the engine's draw buffer. */
function bank(n, color, size, sprite, strength = 1.0) {
  const geo = new THREE.BufferGeometry();
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) arr.set(PARK, i * 3);
  geo.setAttribute("position", new THREE.BufferAttribute(arr, 3));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e4);
  // Opaque, not additive: in shots/2_inside_nominal.png the electrons OCCLUDE
  // the grid wires behind them rather than glowing through.
  const mat = new THREE.PointsMaterial({
    color: lin(...color.map((c) => c * strength)), size,
    sizeAttenuation: true, map: sprite,
    alphaTest: 0.5, transparent: false, depthWrite: true,
  });
  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  pts.userData.worldSize = size;
  return pts;
}

// An electron drawn smaller than this reads as nothing at all. The banks are
// the whole point of the simulation, so hold them at a legible size rather
// than at true scale when the camera is far away.
const MIN_POINT_PX = 4.0;

/**
 * Size the electron sprites for the active camera.
 *
 * Two things go wrong if you just set a world size and forget it:
 *  - PointsMaterial attenuates from the perspective divide, which collapses to
 *    nothing under an OrthographicCamera (the Top view showed no electrons).
 *  - At true scale (0.018 = the Blender icospheres' diameter) the dots are
 *    ~2.5 px from the bench camera 13 units away — invisible. That is the
 *    whole electron flow gone from three of the four sims.
 *
 * So: true world size when it is big enough to see, inflated to MIN_POINT_PX
 * when it is not, and a straight pixel size under ortho.
 */
export function setPointMode(T, camera, pixelHeight) {
  const ortho = camera.isOrthographicCamera;
  // px on screen per world unit at the tube, which sits at the origin
  const pxPerUnit = ortho
    ? pixelHeight / (camera.top - camera.bottom)
    : pixelHeight / (2 * Math.tan(camera.fov * Math.PI / 360) *
                     Math.max(camera.position.length(), 1e-3));
  for (const p of [T.electrons, T.secondaries]) {
    const m = p.material;
    if (m.sizeAttenuation !== !ortho) {
      m.sizeAttenuation = !ortho;
      m.needsUpdate = true;                // sizeAttenuation is a shader define
    }
    const world = p.userData.worldSize;
    const floor = MIN_POINT_PX / pxPerUnit;      // world units for MIN px
    m.size = ortho ? Math.max(world, floor) * pxPerUnit
                   : Math.max(world, floor);
  }
}

// ------------- the tube ------------------------------------------------------

export function buildTube(scene) {
  const root = new THREE.Group();
  root.name = "Tube";
  scene.add(root);

  const T = {};   // handles the sim mutates per frame

  // --- materials
  const copper = principled([0.72, 0.43, 0.28], { metalness: 1.0, roughness: 0.32 });
  const silver = principled([0.75, 0.77, 0.80], { metalness: 1.0, roughness: 0.28 });
  const steel  = principled([0.42, 0.44, 0.47], { metalness: 1.0, roughness: 0.45 });
  const nickel = principled([0.60, 0.60, 0.62], { metalness: 1.0, roughness: 0.35 });
  const mica   = principled([0.82, 0.77, 0.62], { roughness: 0.55, alpha: 0.45 });
  T.matCathode = principled([0.75, 0.73, 0.68], { roughness: 0.65 });
  T.matHeater  = emission([1.0, 0.5, 0.2], 6.0);
  const matGlass = principled([0.9, 0.95, 1.0], { roughness: 0.12, alpha: 0.055 });

  // --- cathode sleeve + heater hairpin (tips out the top)
  mesh(cyl(R_C, 2 * Z_HALF), T.matCathode, "Cathode", root);
  const hp = [[0.05, 0.0, 1.34], [0.05, 0.0, -1.02]];
  for (let i = 1; i <= 5; i++) {
    const a = Math.PI * i / 6;
    hp.push([0.05 * Math.cos(a), 0.0, -1.02 - 0.05 * Math.sin(a)]);
  }
  hp.push([-0.05, 0.0, -1.02], [-0.05, 0.0, 1.34]);
  mesh(polyTube(hp, 0.016), T.matHeater, "Heater", root);

  // --- three grids: control (copper), SCREEN (silver), suppressor (steel)
  helix(G1, copper, root, "Grid1");
  helix(G2, silver, root, "Grid2");
  T.grid3 = helix(G3, steel, root, "Grid3");

  // --- plate, micas, envelope, base
  const plate = mesh(plateGeometry(),
                     principled([0.055, 0.055, 0.062],
                                { metalness: 0.35, roughness: 0.68 }),
                     "Plate", root);
  plate.material.side = THREE.DoubleSide;
  for (const z of [1.30, -1.30]) {
    const ring = mesh(new THREE.RingGeometry(0.45, 1.36, 48), mica, "Mica", root);
    ring.position.z = z;
  }
  T.glass = mesh(glassGeometry(), matGlass, "Glass", root);
  T.glass.renderOrder = 2;
  const button = mesh(cyl(1.34, 0.14), principled([0.55, 0.58, 0.60],
                      { roughness: 0.35, alpha: 0.5 }), "Button", root);
  button.position.z = -1.76;
  for (let i = 0; i < 7; i++) {        // 7 pins over 315 deg, gap = key
    const a = (90 + i * 45) * Math.PI / 180;
    const pin = mesh(cyl(0.05, 0.62, 12), nickel, "Pin", root);
    pin.position.set(0.85 * Math.cos(a), 0.85 * Math.sin(a), -2.10);
  }

  // --- particle banks: primaries (cyan) + secondaries (orange)
  const sprite = discTexture();
  T.electrons = bank(POOL, [0.35, 0.85, 1.0], 0.018, sprite, 5.0);
  T.secondaries = bank(POOL2, [1.0, 0.42, 0.10], 0.022, sprite, 7.0);
  root.add(T.electrons, T.secondaries);

  // --- lights. Blender's AREA lamps become spots, not directionals: an area
  // lamp ~6 units away falls off as 1/d², so the tube's interior gets
  // materially less light than its outside. A directional has no falloff at
  // all, which lit the plate bore far too hot in the Top and Inside views.
  // Spots keep the decay and still shadow from a single map (RectAreaLight
  // cannot shadow at all). Intensities are by eye against shots/ — Blender
  // Watts and three's candela have no conversion.
  const spot = (color, intensity, pos, mapSize) => {
    const L = new THREE.SpotLight(color, intensity, 0, 1.05, 1.0, 2.0);
    L.position.set(...pos);
    L.castShadow = true;
    L.shadow.mapSize.set(mapSize, mapSize);
    L.shadow.camera.near = 0.5;
    L.shadow.camera.far = 24;
    L.shadow.bias = -0.0016;
    scene.add(L.target);                  // target defaults to the origin
    return L;
  };
  const key = spot(0xffffff, 26.0, [-3.2, -4.2, 3.2], 2048);
  const rim = spot(lin(1.0, 0.85, 0.7), 11.0, [2.5, 3.2, 1.2], 1024);
  // sits inside the cathode sleeve; fakes the sleeve's own glow
  T.cathLight = new THREE.PointLight(0xffffff, 0.35, 0, 2);
  T.cathLight.position.set(0.0, 0.0, 0.3);
  scene.add(key, rim, T.cathLight, new THREE.AmbientLight(0xffffff, 0.004));

  root.traverse((o) => {
    if (!o.isMesh) return;
    o.receiveShadow = true;
    o.castShadow = !o.material.transparent;
  });

  T.root = root;
  return T;
}

/** Thermal glow ramp for 300..1300 K (deep red -> orange). */
export function glow(T) {
  const x = Math.max(0.0, (T - 600.0) / 700.0);
  return [[1.0, 0.15 + 0.35 * x, 0.02 + 0.12 * x], x];
}

export function applyHeat(T, kelvin) {
  const [color, x] = glow(kelvin);
  const c = lin(...color);
  T.matHeater.emissive.copy(c);
  T.matHeater.emissiveIntensity = 16.0 * x ** 3;
  T.matCathode.emissive.copy(c);
  T.matCathode.emissiveIntensity = 2.5 * x ** 3;
  T.cathLight.color.copy(c);
  T.cathLight.intensity = 0.6 * x ** 3;
}

/** Push the engine's draw buffers into the Points geometry. */
export function pushParticles(T, S) {
  const a = T.electrons.geometry.attributes.position;
  a.array.set(S.draw);
  a.needsUpdate = true;
  const b = T.secondaries.geometry.attributes.position;
  b.array.set(S.draw2);
  b.needsUpdate = true;
}

// ------------- cameras -------------------------------------------------------
// Blender lens mm -> three vertical FOV, sensor 36 mm with AUTO fit (the long
// edge takes the sensor), which for a landscape viewport is the horizontal one.
const fovFor = (lens, aspect) =>
  2 * Math.atan(18 / (lens * Math.max(aspect, 1))) * 180 / Math.PI;

export const VIEWS = {
  // top camera inside the envelope just below the top mica: cross-section view.
  // Looking straight down needs its own up vector — with the scene's +Z up,
  // lookAt along -Z is degenerate and the orientation comes out garbage.
  TOP: { pos: [0, 0, 1.26], target: [0, 0, -0.5], ortho: 2.9, near: 0.003,
         up: [0, 1, 0] },
  // 135 deg azimuth: the only angle clear of all three rod pairs (0/90/45)
  INSIDE: { pos: [-0.64, 0.64, 0.05], target: [0.1, -0.1, 0.0], lens: 13,
            near: 0.004 },
  OVER: { pos: [4.0, -4.2, 2.5], target: [0, 0, -0.12], lens: 30, near: 0.01 },
  BENCH: { pos: [0.6, -12.5, 3.4], target: [0.2, 0.4, 0.5], lens: 34,
           near: 0.05 },
};

export function makeCameras(aspect) {
  const cams = {};
  for (const [k, v] of Object.entries(VIEWS)) {
    let cam;
    if (v.ortho) {
      const s = v.ortho;
      cam = new THREE.OrthographicCamera(-s / 2, s / 2, s / (2 * aspect),
                                         -s / (2 * aspect), v.near, 200);
    } else {
      cam = new THREE.PerspectiveCamera(fovFor(v.lens, aspect), aspect,
                                        v.near, 200);
    }
    if (v.up) cam.up.set(...v.up);
    cam.position.set(...v.pos);
    cam.lookAt(...v.target);
    cams[k] = cam;
  }
  return cams;
}

export function resizeCameras(cams, aspect) {
  for (const [k, cam] of Object.entries(cams)) {
    const v = VIEWS[k];
    if (v.ortho) {
      const s = v.ortho;
      cam.left = -s / 2; cam.right = s / 2;
      cam.top = s / (2 * aspect); cam.bottom = -s / (2 * aspect);
    } else {
      cam.fov = fovFor(v.lens, aspect);
      cam.aspect = aspect;
    }
    cam.updateProjectionMatrix();
  }
}
