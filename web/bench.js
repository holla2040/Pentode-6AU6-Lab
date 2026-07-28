// The bench: supply, resistors, wiring, and the two instruments.
//
// The scope and the plate-characteristics display are drawn with Canvas2D onto
// a CanvasTexture instead of being built from Blender CURVE splines and FONT
// objects. That replaces _build_scope / _push_traces / _build_tracer /
// _push_curves / _write_pc_spline / _update_load_line / _ensure_fam_labels /
// _text with a few fillText and lineTo calls, and comes out sharper.

import * as THREE from "three";
import { principled, emission, VIEWS } from "./tube.js";
import { pcModelMa, PC_FAMILY_EC1, PC_VMAX, PC_IMAX, SCOPE_N } from "./engine.js";

// Tracer plot box: 10 x 8 divisions, sized to fill a panel the same size as
// the scope. That panel is portrait, so the divisions come out taller than
// they are wide — the alternative was a square graticule adrift in a tall
// empty panel. The extra height buys resolution on the current axis, which is
// where the load line and the operating dot live.
const PC_W = 2.6, PC_H = 3.6;
const PC_L = -PC_W / 2, PC_R = PC_W / 2;   // plot box edges, in panel units
const PC_B = -PC_H / 2, PC_T = PC_H / 2;

/**
 * rotZ that leaves an instrument panel parallel to the Bench camera's image
 * plane, which is the only orientation that projects as a true rectangle.
 *
 * Aiming a panel AT the camera is a different angle and is not what you want:
 * a panel off to one side, turned to face the lens, is still oblique to the
 * image plane and still projects keystoned. Parallel planes never keystone,
 * however far off-axis they sit. Derived from VIEWS.BENCH so moving the
 * camera cannot silently leave the instruments skewed.
 *
 * A panel's face normal is (sin rotZ, -cos rotZ, 0); setting that antiparallel
 * to the camera's forward direction gives the atan2 below.
 */
const FACE_CAM = (() => {
  const { pos, target } = VIEWS.BENCH;
  return Math.atan2(-(target[0] - pos[0]), target[1] - pos[1]);
})();

// resistor colour code, digits 0-9
const BAND_RGB = [[0.02, 0.02, 0.02], [0.28, 0.15, 0.06], [0.75, 0.05, 0.03],
                  [0.90, 0.35, 0.02], [0.85, 0.70, 0.03], [0.05, 0.45, 0.08],
                  [0.03, 0.15, 0.65], [0.45, 0.10, 0.55], [0.35, 0.35, 0.35],
                  [0.90, 0.90, 0.90]];

const box = (sx, sy, sz, pos, mat, parent, name) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat);
  m.position.set(...pos);
  m.name = name || "";
  parent.add(m);
  return m;
};

const cylAt = (r, d, pos, mat, parent, axis = "z", segs = 24) => {
  const g = new THREE.CylinderGeometry(r, r, d, segs);
  if (axis === "z") g.rotateX(Math.PI / 2);
  else if (axis === "x") g.rotateZ(Math.PI / 2);
  const m = new THREE.Mesh(g, mat);
  m.position.set(...pos);
  parent.add(m);
  return m;
};

function wire(pts, bevel, mat, parent) {
  const curve = new THREE.CatmullRomCurve3(
    pts.map((p) => new THREE.Vector3(...p)), false, "catmullrom", 0);
  const m = new THREE.Mesh(
    new THREE.TubeGeometry(curve, pts.length * 6, bevel, 8, false), mat);
  parent.add(m);
  return m;
}

/** Axial resistor with four band rings, body on the X axis at height 1.95. */
function resistor(tag, y, mats, parent) {
  const grp = new THREE.Group();
  parent.add(grp);
  for (const [dx, r, dpt, m] of [[-0.42, 0.014, 0.24, mats.wire],
                                 [0.42, 0.014, 0.24, mats.wire],
                                 [0.0, 0.085, 0.62, mats.beige]]) {
    cylAt(r, dpt, [2.0 + dx, y, 1.95], m, grp, "x");
  }
  const bands = [];
  for (const dx of [-0.20, -0.10, 0.00, 0.22]) {
    const mat = principled([0.3, 0.3, 0.3], { roughness: 0.45, glow: 0.6 });
    cylAt(0.092, 0.05, [2.0 + dx, y, 1.95], mat, grp, "x");
    bands.push(mat);
  }
  return { grp, bands };
}

function recolorBands(res, kohms) {
  const ohms = Math.max(kohms, 0.001) * 1000.0;
  let exp = Math.floor(Math.log10(ohms)) - 1;
  let d = Math.round(ohms / Math.pow(10, exp));
  if (d >= 100) { d = Math.floor(d / 10); exp += 1; }
  const digits = [Math.floor(d / 10), d % 10, exp];
  for (let i = 0; i < 3; i++) {
    const c = BAND_RGB[Math.max(0, Math.min(9, digits[i]))];
    res.bands[i].color.setRGB(...c);
    // self-glow so the colour code reads on the dark bench
    res.bands[i].emissive.setRGB(...c);
  }
}

// ------------- Canvas2D instruments ------------------------------------------

/** A screen panel: a lit canvas mapped onto a plane, plus a dark backing box. */
function panel(scene, { w, h, pos, rotZ, px, bare = false }) {
  const canvas = document.createElement("canvas");
  canvas.width = px;
  canvas.height = Math.round(px * h / w);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const root = new THREE.Group();
  root.position.set(...pos);
  root.rotation.z = rotZ;
  scene.add(root);
  if (!bare) {
    box(w * 1.06, 0.24, h * 1.06, [0, 0.14, 0],
        principled([0.10, 0.10, 0.11], { roughness: 0.55 }), root);
  }
  const face = new THREE.Mesh(
    new THREE.PlaneGeometry(w, h).rotateX(Math.PI / 2),
    new THREE.MeshBasicMaterial({ map: tex, toneMapped: false,
                                  transparent: bare, depthWrite: !bare,
                                  side: THREE.DoubleSide }));
  face.position.y = -0.005;
  root.add(face);
  const g = canvas.getContext("2d");
  return { canvas, ctx: g, tex, root, w, h,
           // world (x, z) on the panel face -> canvas pixels
           X: (x) => (x / w + 0.5) * canvas.width,
           Y: (z) => (0.5 - z / h) * canvas.height };
}

function gridLines(P, x0, x1, z0, z1, dx, dz, color) {
  const g = P.ctx;
  g.strokeStyle = color;
  g.lineWidth = 1;
  g.beginPath();
  for (let x = x0; x <= x1 + 1e-6; x += dx) {
    g.moveTo(P.X(x), P.Y(z0)); g.lineTo(P.X(x), P.Y(z1));
  }
  for (let z = z0; z <= z1 + 1e-6; z += dz) {
    g.moveTo(P.X(x0), P.Y(z)); g.lineTo(P.X(x1), P.Y(z));
  }
  g.stroke();
}

function trace(P, buf, z0, upv, lo, hi, color, width) {
  const g = P.ctx;
  g.strokeStyle = color;
  g.lineWidth = width;
  g.lineJoin = "round";
  g.beginPath();
  for (let i = 0; i < SCOPE_N; i++) {
    const x = -1.28 + (2.56 * i) / (SCOPE_N - 1);
    const z = Math.max(lo, Math.min(hi, z0 + buf[i] * upv));
    if (i === 0) g.moveTo(P.X(x), P.Y(z)); else g.lineTo(P.X(x), P.Y(z));
  }
  g.stroke();
}

const label = (P, text, x, z, size, color, align = "left") => {
  const g = P.ctx;
  g.fillStyle = color;
  g.textAlign = align;
  g.textBaseline = "middle";
  g.font = `${Math.round(size * P.canvas.height / P.h)}px ` +
           `ui-monospace, Menlo, Consolas, monospace`;
  g.fillText(text, P.X(x), P.Y(z));
};

const GREEN = "#2fd04b", AMBER = "#ffa030", WHITE = "#eaeaff",
      GRAT = "#1c7a2e", DIM = "#5ad07a";

/** Oscilloscope: 10 divisions. Top 5 = g1 input, bottom 5 = plate output. */
function drawScope(P, S, p) {
  const g = P.ctx;
  g.fillStyle = "#02060a";
  g.fillRect(0, 0, P.canvas.width, P.canvas.height);
  g.fillStyle = "#03130a";
  g.fillRect(P.X(-1.4), P.Y(2.1), P.X(1.4) - P.X(-1.4), P.Y(-2.1) - P.Y(2.1));
  gridLines(P, -1.2, 1.2, -2.0, 2.0, 0.4, 0.4, GRAT);
  const outVmax = p.bplus <= 300.0 ? 300.0 : 500.0;
  trace(P, S.vgBuf, 1.6, 0.08, 0.0, 2.0, GREEN, 3);
  trace(P, S.vpBuf, -2.0, 2.0 / outVmax, -2.0, 0.0, AMBER, 3.5);
  label(P, "IN Vg  5 V/div", -1.35, 2.28, 0.13, GREEN);
  label(P, `GAIN ${S.gainTxt}`, -0.30, 2.28, 0.15, AMBER);
  label(P, "OUT Vp  100 V/div", 0.50, 2.28, 0.13, AMBER);
  label(P, "+5V", -1.36, 1.90, 0.10, DIM);
  label(P, "-20V", -1.36, 0.08, 0.10, DIM);
  label(P, `${outVmax.toFixed(0)}V`, -1.36, -0.18, 0.10, AMBER);
  label(P, "0V", -1.36, -1.97, 0.10, AMBER);
  P.tex.needsUpdate = true;
}

const pcx = (vp) => -PC_W / 2 + Math.max(0, Math.min(vp, PC_VMAX)) * (PC_W / PC_VMAX);
const pcy = (ma) => -PC_H / 2 + Math.max(0, Math.min(ma, PC_IMAX)) * (PC_H / PC_IMAX);

/** Plate characteristics: the family breathes with the live screen voltage,
 *  the load line does not move, and the dot rides the load line. */
function drawTracer(P, S, p) {
  const g = P.ctx;
  g.fillStyle = "#02060a";
  g.fillRect(0, 0, P.canvas.width, P.canvas.height);
  g.fillStyle = "#03130a";
  g.fillRect(P.X(PC_L), P.Y(PC_T), P.X(PC_R) - P.X(PC_L), P.Y(PC_B) - P.Y(PC_T));
  gridLines(P, PC_L, PC_R, PC_B, PC_T, PC_W / 10, PC_H / 8, GRAT);

  // the family, at the INSTANTANEOUS screen voltage
  const vps = [];
  for (let i = 0; i < 48; i++) vps.push(PC_VMAX * i / 47);
  g.strokeStyle = "#2fbf4a";
  g.lineWidth = 2;
  for (const ec1 of PC_FAMILY_EC1) {
    const ys = pcModelMa(S, vps, ec1, S.vg2, S.cfSlow);
    g.beginPath();
    for (let i = 0; i < vps.length; i++) {
      const X = P.X(pcx(vps[i])), Y = P.Y(pcy(ys[i]));
      if (i === 0) g.moveTo(X, Y); else g.lineTo(X, Y);
    }
    g.stroke();
    // inside the right edge, not outside it — the panel clears the plot box by
    // only 0.22 a side, and an outboard label runs off the canvas
    label(P, `${ec1.toFixed(0)}`, PC_R - 0.05, pcy(ys[ys.length - 1]),
          0.10, "#2fbf4a", "right");
  }

  // static load line from (B+, 0) to (0, B+/RL), clipped to the plot box.
  // Redrawn from the sliders only — it must NOT move with the signal.
  const i0 = p.bplus / Math.max(p.rl, 1e-6);
  const p0 = i0 <= PC_IMAX ? [0.0, i0] : [p.bplus - PC_IMAX * p.rl, PC_IMAX];
  g.strokeStyle = WHITE;
  g.lineWidth = 2.5;
  g.beginPath();
  g.moveTo(P.X(pcx(p0[0])), P.Y(pcy(p0[1])));
  g.lineTo(P.X(pcx(Math.min(p.bplus, PC_VMAX))), P.Y(pcy(0.0)));
  g.stroke();

  // bias dot (DC point) then the live operating point on top
  const dot = (vp, color, r) => {
    const ip = (p.bplus - vp) / Math.max(p.rl, 1e-6);
    g.fillStyle = color;
    g.beginPath();
    g.arc(P.X(pcx(vp)), P.Y(pcy(ip)), r, 0, Math.PI * 2);
    g.fill();
  };
  dot(S.vpRef !== undefined ? S.vpRef : S.vp, "#b00808", 7);
  dot(S.vp, "#ff4033", 9);

  // anchored to the plot box, not to the canvas, so resizing the panel does
  // not leave the captions stranded
  label(P, "PLATE CHARACTERISTICS", PC_L, PC_T + 0.30, 0.125, WHITE);
  label(P, "Vg 0..-5V (moves w/ Vs)", PC_L, PC_B - 0.32, 0.10, GREEN);
  label(P, `Vs = ${S.vg2.toFixed(0)} V`, PC_R, PC_B - 0.32, 0.115, GREEN, "right");
  label(P, "0", PC_L, PC_B - 0.11, 0.09, WHITE);
  label(P, "500V (50/div)", PC_R, PC_B - 0.11, 0.09, WHITE, "right");
  label(P, "4mA (0.5/div)", PC_L + 0.05, PC_T - 0.11, 0.09, WHITE);
  P.tex.needsUpdate = true;
}

/** The floating in-scene meter, matching the Blender FONT object. */
function drawMeter(P, text, size = 0.24) {
  const g = P.ctx;
  g.clearRect(0, 0, P.canvas.width, P.canvas.height);
  const lines = text.split("\n").filter(Boolean);
  lines.forEach((ln, i) => {
    label(P, ln, 0, P.h / 2 - size * (i + 0.75), size, "#4dff8a", "center");
  });
  P.tex.needsUpdate = true;
}

// ------------- build ---------------------------------------------------------

export function buildBench(scene) {
  const B = { props: new THREE.Group() };
  scene.add(B.props);
  const g = B.props;

  const mats = {
    wire: principled([0.65, 0.55, 0.40], { metalness: 1.0, roughness: 0.35,
                     glow: 0.5, glowColor: [0.85, 0.72, 0.5] }),
    beige: principled([0.80, 0.68, 0.50], { roughness: 0.6, glow: 0.35 }),
    dark: principled([0.10, 0.12, 0.16], { roughness: 0.5, glow: 0.35,
                     glowColor: [0.22, 0.22, 0.26] }),
    red: principled([0.65, 0.05, 0.04], { roughness: 0.4, glow: 0.7,
                    glowColor: [0.85, 0.08, 0.05] }),
    blk: principled([0.02, 0.02, 0.02], { roughness: 0.4, glow: 0.4,
                    glowColor: [0.25, 0.25, 0.28] }),
  };

  // --- B+ supply, right of the tube
  box(1.05, 0.75, 0.95, [3.2, 0.5, -1.32], mats.dark, g);
  cylAt(0.05, 0.28, [2.95, 0.35, -0.72], mats.red, g, "z", 12);
  cylAt(0.05, 0.28, [3.45, 0.35, -0.72], mats.blk, g, "z", 12);

  // --- signal generator, front-left
  box(0.95, 0.60, 0.75, [-3.0, -0.8, -1.42], mats.dark, g);
  cylAt(0.045, 0.24, [-2.78, -0.80, -0.95], mats.red, g, "z", 12);
  cylAt(0.045, 0.24, [-3.22, -0.80, -0.95], mats.blk, g, "z", 12);
  const sine = [];
  for (let i = 0; i <= 16; i++) {
    sine.push([-3.0 + (i / 16.0 - 0.5) * 0.55, -1.115,
               -1.40 + Math.sin(2 * Math.PI * i / 16.0) * 0.13]);
  }
  wire(sine, 0.014, emission([0.3, 0.9, 1.0], 2.0), g);

  // --- plate load resistor R_L (front) and screen resistor R_g2 (behind)
  B.rl = resistor("RL", 0.30, mats, g);
  B.rg2 = resistor("RG2", 1.30, mats, g);

  // --- screen bypass capacitor: g2 node down to the common bus
  B.cap = new THREE.Group();
  g.add(B.cap);
  cylAt(0.10, 0.38, [0.9, 1.30, 1.50],
        principled([0.15, 0.25, 0.55], { roughness: 0.35, glow: 0.5,
                   glowColor: [0.2, 0.35, 0.75] }), B.cap);
  wire([[0.9, 1.30, 1.95], [0.9, 1.30, 1.70]], 0.018, mats.wire, B.cap);
  wire([[0.9, 1.30, 1.30], [0.9, 1.30, -2.35], [1.30, 0.60, -2.35],
        [1.26, 0.24, -1.85]], 0.018, mats.wire, B.cap);

  // --- wiring
  for (const pts of [
    [[0.99, 0.20, 1.26], [0.99, 0.20, 1.95], [1.20, 0.30, 1.95], [1.58, 0.30, 1.95]],
    [[2.42, 0.30, 1.95], [2.95, 0.30, 1.95], [2.95, 0.35, -0.60]],
    [[2.95, 0.30, 1.55], [2.95, 1.30, 1.55], [2.95, 1.30, 1.95], [2.42, 1.30, 1.95]],
    [[1.58, 1.30, 1.95], [0.0, 1.30, 1.95], [0.0, 0.55, 1.40]],
    [[3.45, 0.35, -0.62], [3.45, 0.35, -2.35], [1.35, 0.20, -2.35], [1.26, 0.18, -1.82]],
    [[-2.78, -0.80, -0.85], [-2.78, -0.80, -0.55], [-1.55, -0.95, -0.55],
     [-1.55, -0.95, 1.75], [-0.33, 0.0, 1.75], [-0.33, 0.0, 1.40]],
    [[-3.22, -0.80, -0.85], [-3.22, -0.80, -2.35], [-1.35, -0.20, -2.35],
     [-1.26, -0.18, -1.82]],
  ]) wire(pts, 0.022, mats.wire, g);

  // --- cathode-bias network (cb only): Rk to ground, plus its bypass cap
  B.kNet = new THREE.Group();
  g.add(B.kNet);
  B.rk = { grp: B.kNet, bands: [] };
  for (const [dz, r, d, m] of [[0.30, 0.014, 0.24, mats.wire],
                               [-0.30, 0.014, 0.24, mats.wire],
                               [0.0, 0.085, 0.50, mats.beige]]) {
    cylAt(r, d, [1.65, -1.45, -2.10 + dz], m, B.kNet, "z");
  }
  for (const dz of [0.15, 0.06, -0.03, -0.19]) {
    const mat = principled([0.3, 0.3, 0.3], { roughness: 0.45, glow: 0.6 });
    cylAt(0.092, 0.05, [1.65, -1.45, -2.10 + dz], mat, B.kNet, "z");
    B.rk.bands.push(mat);
  }
  wire([[1.10, -0.75, -1.80], [1.65, -1.45, -1.58], [1.65, -1.45, -1.80]],
       0.022, mats.wire, B.kNet);
  wire([[1.65, -1.45, -2.38], [1.65, -1.45, -2.62]], 0.022, mats.wire, B.kNet);
  B.kCap = new THREE.Group();
  B.kNet.add(B.kCap);
  cylAt(0.09, 0.34, [2.15, -1.45, -2.10],
        principled([0.15, 0.25, 0.55], { roughness: 0.35, glow: 0.5,
                   glowColor: [0.2, 0.35, 0.75] }), B.kCap);
  wire([[2.15, -1.45, -1.90], [2.15, -1.45, -1.58], [1.65, -1.45, -1.58]],
       0.018, mats.wire, B.kCap);
  wire([[2.15, -1.45, -2.30], [2.15, -1.45, -2.62], [1.65, -1.45, -2.62]],
       0.018, mats.wire, B.kCap);

  // --- instruments
  // Both instruments read as flat rectangles from the Bench view — see
  // FACE_CAM. Blender's 48 deg on the scope aimed at ITS three-quarter bench
  // camera, and from this head-on one it skewed by 31 deg.
  B.scope = panel(scene, { w: 3.05, h: 4.40, pos: [-3.9, 0.9, 1.15],
                           rotZ: FACE_CAM, px: 640 });
  // Same size and same plane as the scope — a matched pair of instruments.
  // It sits further out than a mirror of the scope would, because the drop
  // from R_L to the supply stands at x=2.95 and the supply's own ground wire
  // at x=3.45: both are nearer the camera than the instrument plane, so they
  // read OUTBOARD of their own x and would clip the tracer's lower left.
  B.tracer = panel(scene, { w: 3.05, h: 4.40, pos: [5.25, 0.9, 1.15],
                            rotZ: FACE_CAM, px: 640 });
  // the floating in-scene meters, at the Blender FONT objects' spots
  B.meter = panel(scene, { w: 2.6, h: 0.78, pos: [0.0, -1.58, -1.98],
                           rotZ: 0, px: 560, bare: true });
  B.benchMeter = panel(scene, { w: 4.2, h: 1.15, pos: [0.2, 2.6, 3.1],
                                rotZ: 0, px: 780, bare: true });

  // --- bench labels (Blender FONT objects -> small transparent planes)
  const lbl = (text, w, h, pos, size, color) => {
    const P = panel(scene, { w, h, pos, rotZ: 0, px: Math.round(w * 190),
                             bare: true });
    P.ctx.clearRect(0, 0, P.canvas.width, P.canvas.height);
    label(P, text, 0, 0, size, color, "center");
    P.tex.needsUpdate = true;
    B.props.add(P.root);
    return P;
  };
  const INK = "#dbe6ff";
  B.psuVal = lbl("300 V", 1.5, 0.42, [3.2, 0.115, -1.62], 0.22, INK);
  lbl("B+", 1.0, 0.45, [3.2, 0.115, -1.20], 0.30, INK);
  lbl("GEN 0.25 Hz", 1.6, 0.30, [-3.0, -1.115, -1.72], 0.16, INK);
  lbl("RL", 0.7, 0.28, [2.0, 0.30, 2.14], 0.16, INK);
  lbl("Rg2", 0.8, 0.28, [2.0, 1.30, 2.14], 0.16, INK);
  B.capLbl = lbl("C", 0.4, 0.26, [1.06, 1.30, 1.44], 0.14, INK);
  B.cap.add(B.capLbl.root);
  B.rkLbl = lbl("Rk", 0.7, 0.28, [1.98, -1.45, -2.06], 0.15, INK);
  B.kNet.add(B.rkLbl.root);
  return B;
}

/** Show only what this sim uses, and keep the resistor colour bands live. */
export function updateBench(B, key, p) {
  const isAmp = key !== "pentode";
  B.props.visible = isAmp;
  B.scope.root.visible = isAmp;
  B.tracer.root.visible = key === "curves";
  B.kNet.visible = key === "cb";
  B.cap.visible = isAmp && !!p.g2Bypass;
  if (B.kCap) B.kCap.visible = !!p.kBypass;
  B.meter.root.visible = !isAmp;        // bare tube's Ip/Ig2 readout
  B.benchMeter.root.visible = isAmp;    // the benches' KVL block
  if (isAmp) {
    recolorBands(B.rl, p.rl);
    recolorBands(B.rg2, p.rg2);
    if (key === "cb" && p.rk) recolorBands(B.rk, p.rk);
    B.psuVal.ctx.clearRect(0, 0, B.psuVal.canvas.width, B.psuVal.canvas.height);
    label(B.psuVal, `${p.bplus.toFixed(0)} V`, 0, 0, 0.22, "#dbe6ff", "center");
    B.psuVal.tex.needsUpdate = true;
  }
}

export function drawInstruments(B, key, S, p, meterText) {
  if (key === "pentode") {
    drawMeter(B.meter, `Ip  = ${(S.ip * S.maPerE).toFixed(1)} mA\n` +
                       `Ig2 = ${(S.ig2 * S.maPerE).toFixed(1)} mA`);
    return;
  }
  drawScope(B.scope, S, p);
  drawMeter(B.benchMeter, meterText, 0.20);
  if (key === "curves") drawTracer(B.tracer, S, p);
}
