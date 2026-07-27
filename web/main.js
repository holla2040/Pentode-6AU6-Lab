// Boot, control panel, and the fixed-step loop.
//
// The physics runs at a fixed 24 Hz regardless of display rate: every tuned
// constant in engine.js is per FRAME, not per second (IP_ALPHA, K_ALPHA,
// D15_DELAY=24, SCOPE_N="2 cycles at 0.25 Hz, 24 fps"). Stepping at rAF rate
// would silently change every time constant and the generator frequency.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { SIMS, makeState, reset, step, DT } from "./engine.js";
import { buildTube, applyHeat, pushParticles, makeCameras, resizeCameras,
         setPointMode, VIEWS } from "./tube.js";
import { buildBench, updateBench, drawInstruments } from "./bench.js";

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);   // Blender's axis convention, so every
                                          // coordinate copies over verbatim

// ------------- control declarations ------------------------------------------
const R = (k, label, min, max, step, unit, fmt = 0) =>
  ({ k, label, min, max, step, unit, fmt });
const B = (k, label) => ({ k, label, bool: true });

const HEAT = R("T", "Heater temp", 300, 1300, 1, "K");
const GLASS = B("showGlass", "Show glass envelope");
const SUPP = B("sup", "Suppressor connected");
const SUPPLY = [
  R("bplus", "B+ supply", 150, 500, 1, "V"),
  R("rl", "Plate resistor R_L", 20, 500, 1, "kΩ"),
  R("rg2", "Screen resistor R_g2", 50, 1000, 1, "kΩ"),
  R("sigAmp", "Signal amplitude", 0, 8, 0.1, "Vpk", 1),
];

const CONTROLS = {
  pentode: [
    HEAT,
    R("vg1", "Grid 1 voltage", -20, 10, 0.1, "V", 1),
    R("vg2", "Screen voltage", 0, 200, 1, "V"),
    R("vp", "Plate voltage", 0, 300, 1, "V"),
    SUPP, GLASS,
  ],
  amp: [
    HEAT, ...SUPPLY,
    R("sigDc", "Grid bias / DC offset", -15, 5, 0.1, "V", 1),
    B("g2Bypass", "Screen bypass capacitor"), SUPP, GLASS,
  ],
  cb: [
    HEAT, ...SUPPLY,
    R("sigDc", "Generator DC offset", -10, 5, 0.1, "V", 1),
    R("rk", "Cathode resistor R_k", 0.1, 5, 0.05, "kΩ", 2),
    B("kBypass", "Cathode bypass capacitor"),
    B("g2Bypass", "Screen bypass capacitor"), SUPP, GLASS,
  ],
  curves: [
    HEAT, ...SUPPLY,
    R("sigDc", "Grid bias / DC offset", -15, 5, 0.1, "V", 1),
    B("g2Bypass", "Screen bypass capacitor"), GLASS,
  ],
};

// The bare tube reads its meters straight off the particle counters; the amps
// report resistor currents, which is what makes them KVL-true.
const METERS = {
  pentode: (S) =>
    `Plate current Ip:  ${(S.ip * S.maPerE).toFixed(1)} mA\n` +
    `Screen current Ig2: ${(S.ig2 * S.maPerE).toFixed(1)} mA\n` +
    `Space-charge cloud: ${S.cloud} e-\n` +
    (S.g1Hits ? `g1 interception:   ${S.g1Hits} e-/frame` : ""),
  amp: (S, p) =>
    `B+ ${p.bplus.toFixed(0)}V     Gain ${S.gainTxt}\n` +
    `Vp ${S.vp.toFixed(0)}V   Ip ${S.ipShow.toFixed(2)}mA\n` +
    `Vg2 ${S.vg2.toFixed(0)}V   Ig2 ${S.ig2Show.toFixed(2)}mA\n` +
    `Vg1 ${S.vg1 >= 0 ? "+" : ""}${S.vg1.toFixed(1)}V`,
  cb: (S, p) =>
    `B+ ${p.bplus.toFixed(0)}V  Vg2 ${(S.vg2 + S.vk).toFixed(0)}V  ` +
    `Vp ${(S.vp + S.vk).toFixed(0)}V\n` +
    `Ip ${S.ipShow.toFixed(2)}mA   Ig2 ${S.ig2Show.toFixed(2)}mA\n` +
    `Vk ${S.vk.toFixed(2)}V   Vg1k ${S.vg1 >= 0 ? "+" : ""}` +
    `${S.vg1.toFixed(1)}V (self-bias)\n` +
    `Gain = ${S.gainTxt}`,
  curves: (S, p) =>
    `B+ ${p.bplus.toFixed(0)}V   Gain ${S.gainTxt}\n` +
    `Vp ${S.vp.toFixed(0)}V   Ip ${S.ipShow.toFixed(2)}mA   ` +
    `Pp ${(S.vp * S.ipShow / 1000).toFixed(2)}W\n` +
    `Vs ${S.vg2.toFixed(0)}V   Is ${S.ig2Show.toFixed(2)}mA   ` +
    `Ps ${(S.vg2 * S.ig2Show / 1000).toFixed(2)}W\n` +
    `Vg ${S.vg1 >= 0 ? "+" : ""}${S.vg1.toFixed(1)}V`,
};

// ------------- scene ---------------------------------------------------------
const canvas = document.getElementById("gl");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
// EEVEE with raytracing off, default AgX view transform, no bloom pass — the
// reference renders have no halo (electrons occlude the wires behind them).
renderer.toneMapping = THREE.AgXToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color().setRGB(0.004, 0.005, 0.008);

const tube = buildTube(scene);
const bench = buildBench(scene);

let aspect = 1;
const cams = makeCameras(aspect);
let view = "OVER";
let camera = cams[view];
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;

function setView(which) {
  view = which;
  camera = cams[which];
  const v = VIEWS[which];
  camera.position.set(...v.pos);
  controls.object = camera;
  // OrbitControls orbits about the camera's own up; the top-down view uses +Y
  controls.object.up.set(...(v.up || [0, 0, 1]));
  setPointMode(tube, camera, canvas.clientHeight || 1080);
  controls.target.set(...v.target);
  controls.update();
  for (const b of viewBtns) b.classList.toggle("on", b.dataset.v === which);
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  aspect = w / h;
  renderer.setSize(w, h, false);
  resizeCameras(cams, aspect);
  setPointMode(tube, camera, h);
}
addEventListener("resize", resize);

// ------------- sim state -----------------------------------------------------
let simKey = (location.hash || "#pentode").slice(1);
if (!(simKey in SIMS)) simKey = "pentode";
let S, params;

function loadSim(key) {
  simKey = key;
  location.hash = key;
  const cfg = SIMS[key];
  params = { ...cfg.defaults, ...urlParams(key) };
  S = makeState(cfg);
  reset(S, params);
  buildControls();
  applyVisibility();
  steps = 0;
  dirty = true;
  warmUp();
  const wantView = new URLSearchParams(location.search).get("view");
  setView(wantView && wantView in VIEWS ? wantView
                                       : (cfg.scope ? "BENCH" : "OVER"));
  simSel.value = key;
}

/**
 * Any control key may be set from the query string, so a lesson can be linked
 * at its exact settings — e.g. ?vg2=150&vp=60&sup=0#pentode is the tetrode
 * kink of LESSONS.md Part I. Booleans take 0/1.
 */
function urlParams(key) {
  const q = new URLSearchParams(location.search);
  const out = {};
  for (const c of CONTROLS[key]) {
    const v = q.get(c.k);
    if (v === null) continue;
    out[c.k] = c.bool ? (v !== "0" && v !== "false") : parseFloat(v);
  }
  return out;
}

/**
 * Run the sim forward before the first paint. The amplifier builds need
 * hundreds of frames for the perveance calibration and the bypass capacitors
 * to settle — the Blender original just makes you sit and watch it drift for
 * the first minute. ?warm=N overrides (0 to watch it settle from cold).
 */
function warmUp() {
  const q = new URLSearchParams(location.search).get("warm");
  const n = q !== null ? parseInt(q, 10) || 0 : (SIMS[simKey].warm || 0);
  for (let i = 0; i < n; i++) { step(S, params); steps++; }
}

function applyVisibility() {
  tube.glass.visible = !!params.showGlass;
  tube.grid3.visible = params.sup !== false;
  updateBench(bench, simKey, params);
}

// ------------- panel ---------------------------------------------------------
const simSel = document.getElementById("sim");
for (const [k, cfg] of Object.entries(SIMS)) {
  simSel.add(new Option(cfg.label, k));
}
simSel.onchange = () => loadSim(simSel.value);

// A hash-only change does not reload the page, so LESSONS.md links like
// web/#curves would otherwise land on whatever sim was already showing.
addEventListener("hashchange", () => {
  const key = location.hash.slice(1);
  if (key in SIMS && key !== simKey) loadSim(key);
});

const viewBtns = [];
const viewsEl = document.getElementById("views");
for (const [label, key] of [["Top", "TOP"], ["Inside", "INSIDE"],
                            ["Overview", "OVER"], ["Bench", "BENCH"]]) {
  const b = document.createElement("button");
  b.textContent = label;
  b.dataset.v = key;
  b.onclick = () => setView(key);
  viewsEl.append(b);
  viewBtns.push(b);
}

const ctlEl = document.getElementById("controls");
const meterEl = document.getElementById("meter");
const noteEl = document.getElementById("note");
const hudEl = document.getElementById("hud");

function buildControls() {
  ctlEl.replaceChildren();
  for (const c of CONTROLS[simKey]) {
    if (c.bool) {
      const lab = document.createElement("label");
      lab.className = "chk";
      const inp = document.createElement("input");
      inp.type = "checkbox";
      inp.checked = !!params[c.k];
      inp.onchange = () => {
        params[c.k] = inp.checked; applyVisibility(); dirty = true;
      };
      lab.append(inp, document.createTextNode(c.label));
      ctlEl.append(lab);
      continue;
    }
    const wrap = document.createElement("div");
    wrap.className = "ctl";
    const lab = document.createElement("label");
    const val = document.createElement("span");
    const show = () =>
      (val.textContent = `${params[c.k].toFixed(c.fmt)} ${c.unit}`);
    lab.append(document.createTextNode(c.label), val);
    const inp = document.createElement("input");
    inp.type = "range";
    inp.min = c.min; inp.max = c.max; inp.step = c.step;
    inp.value = params[c.k];
    inp.oninput = () => {
      params[c.k] = parseFloat(inp.value);
      show();
      if (c.k === "T") applyHeat(tube, params.T);
      updateBench(bench, simKey, params);
      dirty = true;
    };
    show();
    wrap.append(lab, inp);
    ctlEl.append(wrap);
  }
  applyHeat(tube, params.T);
}

let running = true;
const playBtn = document.getElementById("play");
const setPlay = () => {
  playBtn.textContent = running ? "Pause" : "Run";
  playBtn.classList.toggle("on", running);
};
playBtn.onclick = () => { running = !running; setPlay(); };
document.getElementById("reset").onclick =
  () => { reset(S, params); steps = 0; warmUp(); };
addEventListener("keydown", (e) => {
  if (e.key === " ") { e.preventDefault(); running = !running; setPlay(); }
});

// ------------- loop ----------------------------------------------------------
let acc = 0, prev = performance.now(), fps = 0, frames = 0, fpsT = prev,
    steps = 0, dirty = true;

function tick(now) {
  requestAnimationFrame(tick);
  const dt = Math.min((now - prev) / 1000, 0.25);
  prev = now;

  let stepped = 0;
  if (running) {
    acc += dt;
    // cap the catch-up so a backgrounded tab does not stall on resume
    for (let n = 0; acc >= DT && n < 3; n++) {
      step(S, params); steps++; stepped++; acc -= DT;
    }
    if (acc > DT) acc = 0;
  }

  pushParticles(tube, S);
  const meterText = METERS[simKey](S, params);
  // the instrument canvases only change when the physics did; re-uploading
  // them every rAF is a few MB/frame of texture traffic for nothing
  if (stepped || dirty) { drawInstruments(bench, simKey, S, params, meterText); }
  dirty = false;
  meterEl.textContent = meterText;
  noteEl.textContent = params.sup === false ? "TETRODE MODE (no suppressor)" : "";

  frames++;
  if (now - fpsT > 500) {
    fps = Math.round(frames * 1000 / (now - fpsT));
    frames = 0; fpsT = now;
  }
  hudEl.innerHTML = `<b>${SIMS[simKey].label}</b> &nbsp; ${fps} fps &nbsp; ` +
    `frame ${steps} &nbsp; cloud ${S.cloud} e- &nbsp; ` +
    `${running ? "running" : "paused"}`;

  controls.update();
  renderer.render(scene, camera);
}

// one handle for poking at a running sim from the console.
// NOT `window.sim` — the <select id="sim"> already owns that global.
window.__sim = { get S() { return S; }, get params() { return params; },
               tube, bench, cams, scene, renderer,
               get camera() { return camera; } };

loadSim(simKey);
setPlay();
resize();
requestAnimationFrame(tick);
