// 6AU6 pentode engine — a direct port of the Blender sims' physics.
//
// Imports nothing. No three.js, no DOM. That is deliberate: it lets
// `node web/selfcheck.js` run the entire physics + circuit stack headless,
// which is where all the real porting risk lives.
//
// Ported from pentode_sim.py / amplifier/*.py / amplifier-cathode-bias/*.py /
// amplifier-plate-characteristics/*.py. Constants and the order of operations
// are transcribed verbatim — several were tuned empirically against
// docs/6AU6A.pdf and against solver-stability failures documented at length in
// plate_curves_sim.py:1117-1179. Do not "clean up" the sequencing.

// ------------- geometry (Blender units; gaps ~3x a real 6AU6 for visibility) -
export const R_C = 0.15;                 // cathode outer radius
//                   radius  helix pitch  wire r  rod r  rod angle  force  capture
export const G1 = { r: 0.33, pitch: 0.085, wire: 0.010, rod: 0.022, rod_ang: 0.0,
                    kw: 0.002, cap: 0.014 };
export const G2 = { r: 0.55, pitch: 0.140, wire: 0.012, rod: 0.026, rod_ang: 90.0,
                    kw: 0.0006, cap: 0.0095 };  // capture calibrated to the 6AU6-A
                    // datasheet: Ic2/Icathode ~ 0.27-0.31 (docs/6AU6A.pdf p3-4)
export const G3 = { r: 0.80, pitch: 0.340, wire: 0.014, rod: 0.030, rod_ang: 45.0,
                    kw: 0.002, cap: 0.016 };
export const PLATE_A = 1.00;   // superellipse x semi-axis (inradius)
export const PLATE_B = 0.88;   // flattened y semi-axis (6AU6 plate is squashed)
const ABS_K = 0.98;     // absorb just inside the visual wall
export const Z_HALF = 1.2;     // cathode half height = active region
export const PARK = [0.0, 0.0, -500.0];  // dead electrons live here, off camera

// ------------- physics -------------------------------------------------------
export const POOL = 7000;      // primary electron pool
export const POOL2 = 1500;     // secondary electron pool (plate emission)
const MU2 = 18.0;              // screen mu: cathode field term Vg2/MU2
const MUP = 400.0;             // plate mu: plate is almost screened away
const C1 = 0.5;                // accel/volt, cathode->g1
const C2 = 0.040;              // accel/volt, g1->g2
const C3 = 0.030;              // accel/volt, g2->g3 (retarding: -Vg2 dominates)
const KNEE_C = 1.2;            // plate's reach into the g2-g3 valley
const V_KNEE = 60.0;           // reach saturates above this: flat top + knee below
const C4 = 0.055;              // accel/volt, g3->plate
const C34 = 0.020;             // tetrode mode: merged g2->plate region
const V_SC = 1.5;              // space-charge depression at full cloud [V]
const CLOUD_R = 0.30;
const CLOUD_CAP = 2000.0;
const EPS = 0.02;              // wire force softening
const BAND = 0.08;             // wire force active band around each grid radius
const SEC_VTH = 0.8;           // impact speed above which secondaries appear
const SEC_YIELD = 0.55;        // probability of a secondary per fast hit
const SEC_V0 = 0.30;           // secondary launch speed (inward)
const E0 = 150.0;              // electrons/frame emitted at T_REF
const E_CLAMP = 400.0;
const T_REF = 1100.0;
const T_SLOPE = 13000.0;
export const DT = 1.0 / 24.0;
const SUBSTEPS = 4;
const GAMMA = 0.7;             // mild drag only; heavy drag traps electrons in
                               // the g2-g3 valley
const V_MAX = 6.0;
const IP_ALPHA = 0.15;

// ------------- circuit -------------------------------------------------------
const FREQ = 0.25;             // generator frequency [Hz]
const K_ALPHA = 0.06;          // perveance calibration EMA (out of signal band)
const SF_ALPHA = 0.01;         // screen-fraction calibration EMA
const IK_LOOP_ALPHA = 0.05;    // smoothed measured currents feeding calibration
const D15_DELAY = 24;          // frames the estimator's drive is delayed to match
                               // the measured drive->arrival transport lag
const VP_SMOOTH = 0.5;         // light smoothing of the solved voltages
export const SCOPE_N = 192;    // scope buffer (2 cycles at 0.25 Hz, 24 fps)

// ------------- plate-characteristics display ---------------------------------
export const PC_VMAX = 500.0;  // x axis: plate volts, 50 V/div * 10 div
export const PC_IMAX = 4.0;    // y axis: plate mA, 0.5 mA/div * 8 div
export const PC_FAMILY_EC1 = [0.0, -1.0, -2.0, -3.0, -4.0, -5.0];

// ------------- helpers -------------------------------------------------------

// Python's % is non-negative for a positive modulus; JS keeps the dividend's
// sign. The grid pitch modulo runs on z in [-1.2, 1.2] — negative half the
// time — so a bare % silently breaks wire capture over the tube's lower half.
const wrap = (a, m) => ((a % m) + m) % m;

/** mulberry32: seeded, fast, and good enough for a Monte-Carlo tube. */
export function makeRng(seed = 0) {
  let a = (seed + 0x6d2b79f5) >>> 0;
  let spare = null;
  const random = () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const normal = (mu = 0, sigma = 1) => {
    if (spare !== null) { const s = spare; spare = null; return mu + sigma * s; }
    let u = 0, v = 0, s = 0;
    do {
      u = random() * 2 - 1; v = random() * 2 - 1; s = u * u + v * v;
    } while (s >= 1 || s === 0);
    const f = Math.sqrt(-2 * Math.log(s) / s);
    spare = v * f;
    return mu + sigma * u * f;
  };
  const uniform = (lo, hi) => lo + (hi - lo) * random();
  // lam reaches E_CLAMP=400, where Knuth's e^-lam underflows to 0 and the
  // product loop never terminates correctly. Normal approximation above 20.
  const poisson = (lam) => {
    if (lam <= 0) return 0;
    if (lam < 20) {
      const L = Math.exp(-lam);
      let k = 0, p = 1;
      do { k++; p *= random(); } while (p > L);
      return k - 1;
    }
    return Math.max(0, Math.round(lam + Math.sqrt(lam) * normal()));
  };
  return { random, normal, uniform, poisson };
}

export const std = (a) => {
  const n = a.length;
  let m = 0;
  for (let i = 0; i < n; i++) m += a[i];
  m /= n;
  let s = 0;
  for (let i = 0; i < n; i++) { const d = a[i] - m; s += d * d; }
  return Math.sqrt(s / n);
};

export const corr = (a, b) => {
  const n = a.length;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
  ma /= n; mb /= n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - ma, db = b[i] - mb;
    sab += da * db; saa += da * da; sbb += db * db;
  }
  return sab / Math.max(Math.sqrt(saa * sbb), 1e-12);
};

/** Region field: force per unit charge on an electron, + = outward. */
function radialAccel(r, Vg1, Vg2, Vp, cf, sup) {
  if (r < G1.r) return C1 * (Vg1 + Vg2 / MU2 + Vp / MUP - V_SC * cf);
  if (r < G2.r) return C2 * (Vg2 - Vg1);
  if (!sup) return C34 * (Vp - Vg2);          // tetrode: g3 out of circuit
  if (r < G3.r) return C3 * (KNEE_C * Math.min(Vp, V_KNEE) - Vg2);
  return C4 * Vp;
}

/** Superellipse coordinate: >= 1 means at/inside the plate wall. */
function plateS(x, y) {
  const a = Math.abs(x) / (ABS_K * PLATE_A), b = Math.abs(y) / (ABS_K * PLATE_B);
  return a * a * a * a + b * b * b * b;
}

// ------------- state ---------------------------------------------------------

/**
 * cfg: { maPerE, circuit, lockupBand, reclaimMin }
 *   maPerE      0.2 on the bare tube (display scale); 0.02 on the amps, so
 *               V = I*R lands in real-tube range.
 *   lockupBand  bare tube + amps trip at cloud > CAP; the curves build uses a
 *               band (cloud >= CAP-25) because emission gates to ~zero NEAR
 *               the cap, so the cloud can hover just below it forever.
 */
export function makeState(cfg, seed = 0) {
  const S = {
    cfg,
    seed,
    maPerE: cfg.maPerE,
    pos: new Float64Array(POOL * 3), vel: new Float64Array(POOL * 3),
    alive: new Uint8Array(POOL), draw: new Float32Array(POOL * 3),
    pos2: new Float64Array(POOL2 * 3), vel2: new Float64Array(POOL2 * 3),
    alive2: new Uint8Array(POOL2), draw2: new Float32Array(POOL2 * 3),
    vgBuf: new Float64Array(SCOPE_N), vpBuf: new Float64Array(SCOPE_N),
    genBuf: new Float64Array(SCOPE_N),
    // Calibration persists across resets, exactly as in the Python (_S.get):
    // the selfchecks depend on it carrying between run() calls.
    khat: 0.0, khatSlow: 0.0, sfrac: 0.28, d15Loop: 0.0, d15q: [],
  };
  reset(S, cfg.defaults || {});
  return S;
}

export function reset(S, p) {
  S.pos.fill(0); S.vel.fill(0); S.alive.fill(0);
  S.pos2.fill(0); S.vel2.fill(0); S.alive2.fill(0);
  for (let i = 0; i < POOL; i++) S.draw.set(PARK, i * 3);
  for (let i = 0; i < POOL2; i++) S.draw2.set(PARK, i * 3);
  S.rng = makeRng(S.seed || 0);
  S.ip = 0.0; S.ig2 = 0.0; S.cloud = 0; S.g1Hits = 0;
  S.t = 0.0;
  S.vp = p.bplus !== undefined ? p.bplus : 300.0;   // tube off -> both at B+
  S.vg2 = S.vp;
  S.vk = 0.0;
  S.vg1 = p.sigDc !== undefined ? p.sigDc : -3.0;
  S.ikLoop = 0.0; S.ig2Loop = 0.0;
  S.ipShow = 0.0; S.ig2Show = 0.0;
  S.cf = 0.0; S.cfSlow = 0.5;
  S.vg2Byp = null; S.vkByp = null; S.vg2gndByp = null;
  S.emis = 1.0; S.gainTxt = "--";
  S.vgBuf.fill(S.vg1); S.vpBuf.fill(S.vp);
  S.genBuf.fill(p.sigDc !== undefined ? p.sigDc : 0.0);
  // khat / khatSlow / sfrac / d15Loop / d15q deliberately survive.
}

// ------------- circuits ------------------------------------------------------
// Each returns the voltages the tube actually feels this frame and runs its own
// calibration. The three amplifier variants differ in gate conditions and EMA
// rates that were tuned separately — they are NOT unified on purpose.

/** Bare tube: the sliders are the electrode voltages. */
function circuitDirect(S, p) {
  return { vg1: p.vg1, vg2: p.vg2, vp: p.vp, vk: 0.0, sup: p.sup };
}

function mkModel(S, emis, cf) {
  return (vp, vg2, vg1, cfx) => {
    const c = cfx === undefined ? cf : cfx;
    const d = Math.max(0.0, vg1 + vg2 / MU2 + vp / MUP - V_SC * c);
    const ik = S.khat * emis * Math.pow(d, 1.5);
    const ip = ik * (1.0 - S.sfrac) * Math.pow(Math.min(1.0, vp / V_KNEE), 0.8);
    return [ip, ik - ip];
  };
}

/** RC stage: plate and screen each ride a solved load line. */
function circuitAmp(S, p, cf) {
  S.cfSlow += 0.02 * (cf - S.cfSlow);
  S.t += DT;
  const Vg1 = p.sigDc + p.sigAmp * Math.sin(2 * Math.PI * FREQ * S.t);
  const Bp = p.bplus, RL = p.rl, RG2 = p.rg2, M = S.maPerE;
  const emis = Math.min(1.0, Math.exp(-T_SLOPE * (1.0 / p.T - 1.0 / T_REF)));
  S.emis = emis;
  const model = mkModel(S, emis, cf);

  const solveVp = (vg2, vg1, cfx) => {
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 22; i++) {
      const mid = 0.5 * (lo + hi);
      if (Bp - RL * M * model(mid, vg2, vg1, cfx)[0] - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };
  const solveVg2 = (vg1, cfx) => {
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 22; i++) {
      const mid = 0.5 * (lo + hi);
      const ig2m = model(solveVp(mid, vg1, cfx), mid, vg1, cfx)[1];
      if (Bp - RG2 * M * ig2m - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };

  // DC reference on the SLOW calibration copy: anchors the calibration and is
  // the node the bypass capacitor holds (live khat jitter must not shake it).
  S.khatSlow += 0.02 * (S.khat - S.khatSlow);
  const kLive = S.khat;
  S.khat = S.khatSlow;
  const vg2Ref = solveVg2(p.sigDc, S.cfSlow);
  const vpRef = solveVp(vg2Ref, p.sigDc, S.cfSlow);
  S.khat = kLive;
  const dDc = Math.max(0.0, p.sigDc + vg2Ref / MU2 + vpRef / MUP
                            - V_SC * S.cfSlow);
  // unbiased perveance: averaged current over equally-averaged drive^1.5
  const dNow = Math.max(0.0, Vg1 + S.vg2 / MU2 + S.vp / MUP - V_SC * cf);
  S.d15Loop += IK_LOOP_ALPHA * (Math.pow(dNow, 1.5) - S.d15Loop);
  if (emis > 0.2 && dDc > 0.5 && S.d15Loop > 0.3) {
    const kInst = S.ikLoop / (emis * S.d15Loop);
    // down-corrections only on the lockup signature
    const downOk = kInst < S.khat && S.cloud >= CLOUD_CAP - 25;
    if (downOk || (dDc > 1.5 && S.ikLoop > 5.0)) {
      const a = S.khat < 0.7 * kInst ? 0.15 : K_ALPHA;
      S.khat += a * (kInst - S.khat);
    }
    if (dDc > 1.5 && S.ikLoop > 5.0 && S.vp > 80.0) {
      const rInst = S.ig2Loop / S.ikLoop;
      S.sfrac += SF_ALPHA * (Math.min(Math.max(rInst, 0.15), 0.42) - S.sfrac);
    }
  }

  let vg2Sol;
  if (p.g2Bypass) {
    if (S.vg2Byp === null) S.vg2Byp = vg2Ref;
    S.vg2Byp += 0.008 * (vg2Ref - S.vg2Byp);
    vg2Sol = S.vg2Byp;
  } else {
    vg2Sol = solveVg2(Vg1, undefined);
  }
  const vpSol = solveVp(vg2Sol, Vg1, undefined);

  S.vg2 += VP_SMOOTH * (vg2Sol - S.vg2);
  S.vp += VP_SMOOTH * (vpSol - S.vp);
  S.vg1 = Vg1;
  return { vg1: Vg1, vg2: S.vg2, vp: S.vp, vk: 0.0, sup: p.sup, Bp, RL, RG2 };
}

/** Self-bias stage: cathode current through Rk lifts the cathode. Three loops. */
function circuitCB(S, p, cf) {
  S.cfSlow += 0.02 * (cf - S.cfSlow);
  S.t += DT;
  const Vgen = p.sigDc + p.sigAmp * Math.sin(2 * Math.PI * FREQ * S.t);
  const Bp = p.bplus, RL = p.rl, RG2 = p.rg2, RK = p.rk, M = S.maPerE;
  const emis = Math.min(1.0, Math.exp(-T_SLOPE * (1.0 / p.T - 1.0 / T_REF)));
  S.emis = emis;
  const model = mkModel(S, emis, cf);

  const solveVp = (vg2, vg1, vk, cfx) => {
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 18; i++) {
      const mid = 0.5 * (lo + hi);
      if (Bp - RL * M * model(mid, vg2, vg1, cfx)[0] - vk - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };
  const solveVg2 = (vg1, vk, vg2gndFixed, cfx) => {
    if (vg2gndFixed !== null && vg2gndFixed !== undefined) {
      return Math.max(vg2gndFixed - vk, 0.0);   // bypassed screen: frozen node
    }
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 18; i++) {
      const mid = 0.5 * (lo + hi);
      const ig2m = model(solveVp(mid, vg1, vk, cfx), mid, vg1, cfx)[1];
      if (Bp - RG2 * M * ig2m - vk - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };
  const solveAll = (vgenX, vkFixed, vg2gndFixed, cfx) => {
    const atVk = (vk) => {
      const vg1 = vgenX - vk;
      const vg2 = solveVg2(vg1, vk, vg2gndFixed, cfx);
      const vp = solveVp(vg2, vg1, vk, cfx);
      const [ip, ig2] = model(vp, vg2, vg1, cfx);
      return [vg2, vp, ip, ig2];
    };
    if (vkFixed !== null && vkFixed !== undefined) {
      const [vg2, vp, ip, ig2] = atVk(vkFixed);
      return [vkFixed, vg2, vp, ip, ig2];
    }
    let lo = 0.0, hi = Math.min(60.0, Bp);
    for (let i = 0; i < 16; i++) {
      const mid = 0.5 * (lo + hi);
      const [, , ipm, ig2m] = atVk(mid);
      if ((ipm + ig2m) * M * RK - mid > 0.0) lo = mid;
      else hi = mid;
    }
    const vk = 0.5 * (lo + hi);
    const [vg2, vp, ip, ig2] = atVk(vk);
    return [vk, vg2, vp, ip, ig2];
  };

  S.khatSlow += 0.02 * (S.khat - S.khatSlow);
  const kLive = S.khat;
  S.khat = S.khatSlow;
  const [vkDc, vg2Dc, vpDc] = solveAll(p.sigDc, null, null, S.cfSlow);
  S.khat = kLive;
  const dDc = Math.max(0.0, (p.sigDc - vkDc) + vg2Dc / MU2 + vpDc / MUP
                            - V_SC * S.cfSlow);
  const dNow = Math.max(0.0, S.vg1 + S.vg2 / MU2 + S.vp / MUP - V_SC * cf);
  S.d15Loop += IK_LOOP_ALPHA * (Math.pow(dNow, 1.5) - S.d15Loop);
  if (emis > 0.2 && dDc > 0.5 && S.d15Loop > 0.3) {
    const kInst = S.ikLoop / (emis * S.d15Loop);
    // down-corrections fire ONLY on the lockup signature: during warmup ramps
    // k_inst reads low (current lags the drive) and would wrongly crush khat
    const downOk = kInst < S.khat && S.cloud >= CLOUD_CAP - 25;
    if (downOk || (dDc > 1.5 && S.ikLoop > 5.0)) {
      const a = S.khat < 0.7 * kInst ? 0.15 : K_ALPHA;
      S.khat += a * (kInst - S.khat);
    }
    if (dDc > 1.5 && S.ikLoop > 5.0 && vpDc > 80.0) {
      const rInst = S.ig2Loop / S.ikLoop;
      S.sfrac += SF_ALPHA * (Math.min(Math.max(rInst, 0.15), 0.42) - S.sfrac);
    }
  }

  let vkFreeze = null, vg2gndFreeze = null;
  if (p.kBypass) {
    if (S.vkByp === null) S.vkByp = vkDc;
    S.vkByp += 0.008 * (vkDc - S.vkByp);
    vkFreeze = S.vkByp;
  } else S.vkByp = null;
  if (p.g2Bypass) {
    if (S.vg2gndByp === null) S.vg2gndByp = vg2Dc + vkDc;
    S.vg2gndByp += 0.008 * ((vg2Dc + vkDc) - S.vg2gndByp);
    vg2gndFreeze = S.vg2gndByp;
  } else S.vg2gndByp = null;
  const [vkSol, vg2Sol, vpSol] = solveAll(Vgen, vkFreeze, vg2gndFreeze,
                                          undefined);

  S.vk += VP_SMOOTH * (vkSol - S.vk);
  S.vg2 += VP_SMOOTH * (vg2Sol - S.vg2);
  S.vp += VP_SMOOTH * (vpSol - S.vp);
  const Vg1 = Vgen - S.vk;   // grid-to-cathode: what the tube actually feels
  S.vg1 = Vg1;
  return { vg1: Vg1, vg2: S.vg2, vp: S.vp, vk: S.vk, sup: true, Vgen,
           Bp, RL, RG2 };
}

/**
 * Plate-characteristics build. Same topology as circuitAmp but with the
 * hard-won stable calibration: ALL circuit solves run on a slow-averaged copy
 * of khat and cf, and the perveance pairing is time-aligned through a
 * D15_DELAY ring buffer and uses only the FAST cloud component. See
 * plate_curves_sim.py:1117-1179 — every one of these was a fix for a measured
 * limit cycle, not a preference.
 */
function circuitCurves(S, p, cf) {
  S.t += DT;
  const Vg1 = p.sigDc + p.sigAmp * Math.sin(2 * Math.PI * FREQ * S.t);
  const Bp = p.bplus, RL = p.rl, RG2 = p.rg2, M = S.maPerE;
  const emis = Math.min(1.0, Math.exp(-T_SLOPE * (1.0 / p.T - 1.0 / T_REF)));
  S.cf = cf;
  // tau ~8 s: far below the signal band, so cloud ripple cannot leak into the
  // family or the DC reference
  S.cfSlow += 0.005 * (cf - S.cfSlow);
  S.emis = emis;
  const model = mkModel(S, emis, cf);

  const solveVp = (vg2, vg1, cfx) => {
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 22; i++) {
      const mid = 0.5 * (lo + hi);
      if (Bp - RL * M * model(mid, vg2, vg1, cfx)[0] - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };
  const solveVg2 = (vg1, cfx) => {
    let lo = 0.0, hi = Bp;
    for (let i = 0; i < 22; i++) {
      const mid = 0.5 * (lo + hi);
      const ig2m = model(solveVp(mid, vg1, cfx), mid, vg1, cfx)[1];
      if (Bp - RG2 * M * ig2m - mid > 0.0) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  };

  // bootstrap fast to 70%, then crawl (tau ~8 s). The 1.5x down band lets the
  // slow copy chase a collapsing calibration without chasing signal ripple.
  const ks = S.khatSlow;
  const aS = (ks < 0.7 * S.khat || ks > 1.5 * S.khat) ? 0.05 : 0.005;
  S.khatSlow += aS * (S.khat - S.khatSlow);
  const kLive = S.khat;
  S.khat = S.khatSlow;
  const vg2Ref = solveVg2(p.sigDc, S.cfSlow);
  const vpRef = solveVp(vg2Ref, p.sigDc, S.cfSlow);
  let vg2Sol;
  if (p.g2Bypass) {
    if (S.vg2Byp === null) S.vg2Byp = vg2Ref;
    S.vg2Byp += 0.008 * (vg2Ref - S.vg2Byp);
    vg2Sol = S.vg2Byp;
  } else {
    vg2Sol = solveVg2(Vg1, S.cfSlow);
  }
  const vpSol = solveVp(vg2Sol, Vg1, S.cfSlow);
  S.khat = kLive;
  S.vpRef = vpRef;

  // Time-aligned, unbiased perveance estimate. The cloud term in the PAIRING
  // drive is the FAST component only (cf - cfSlow): the static -V_SC*cf slope
  // is positive feedback and produced a ~29 s Vg2 limit cycle.
  const dNow = Math.max(0.0, Vg1 + S.vg2 / MU2 + S.vp / MUP
                             - V_SC * (cf - S.cfSlow));
  S.d15q.push(Math.pow(dNow, 1.5));
  if (S.d15q.length > D15_DELAY + 1) S.d15q.shift();
  S.d15Loop += IK_LOOP_ALPHA * (S.d15q[0] - S.d15Loop);
  // Gates judge MEASURED reality, never the model's own reference solve: a
  // poisoned calibration starves the model references, and a gate based on
  // them would lock the poison in circularly.
  if (emis > 0.2 && S.d15Loop > 0.3) {
    const kInst = S.ikLoop / (emis * S.d15Loop);
    // ikLoop > 30: below ~30 arrivals/frame the current is mid-choke or
    // Poisson-thin and carries no perveance information.
    if (S.d15Loop > 1.0 && S.ikLoop > 30.0) {
      const a = S.khat < 0.7 * kInst ? 0.15 : K_ALPHA;
      S.khat += a * (kInst - S.khat);
    }
    if (S.d15Loop > 1.0 && S.ikLoop > 30.0 && S.vp > 80.0) {
      const rInst = S.ig2Loop / S.ikLoop;
      S.sfrac += SF_ALPHA * (Math.min(Math.max(rInst, 0.15), 0.42) - S.sfrac);
    }
  }

  S.vg2 += VP_SMOOTH * (vg2Sol - S.vg2);
  S.vp += VP_SMOOTH * (vpSol - S.vp);
  S.vg1 = Vg1;
  return { vg1: Vg1, vg2: S.vg2, vp: S.vp, vk: 0.0, sup: true, Bp, RL, RG2 };
}

/** The solver's companion model, swept over plate voltage, in mA. */
export function pcModelMa(S, vps, vg1, vg2, cf) {
  const c = cf === undefined ? S.cfSlow : cf;
  const k = S.khatSlow || S.khat;
  const out = new Float64Array(vps.length);
  for (let i = 0; i < vps.length; i++) {
    const vp = vps[i];
    const d = Math.max(0.0, vg1 + vg2 / MU2 + vp / MUP - V_SC * c);
    const ik = k * S.emis * Math.pow(d, 1.5);
    out[i] = ik * (1.0 - S.sfrac) *
             Math.pow(Math.min(1.0, vp / V_KNEE), 0.8) * S.maPerE;
  }
  return out;
}

// ------------- the step ------------------------------------------------------

export function step(S, p) {
  const rng = S.rng;
  const pos = S.pos, vel = S.vel, al = S.alive;
  const pos2 = S.pos2, vel2 = S.vel2, al2 = S.alive2;

  // --- space charge: mean-field cloud count, with the lockup breaker
  let cloud = 0;
  for (let i = 0; i < POOL; i++) {
    if (!al[i]) continue;
    const i3 = i * 3;
    if (Math.hypot(pos[i3], pos[i3 + 1]) < CLOUD_R) cloud++;
  }
  const band = S.cfg.lockupBand ? cloud >= CLOUD_CAP - 25 : cloud > CLOUD_CAP;
  if (band && S.ip + S.ig2 < 1.0) {
    // TRUE space-charge lockup: cloud at cap with zero throughput means
    // emission stays gated (lam *= 1-cf) and the trapped electrons can never
    // drain past the grid-wire barrier -- the tube latches dead. Reclaim them
    // into the cathode to break the latch. A full cloud WITH current flowing
    // is normal space-charge-limited operation and is deliberately left alone.
    let want = Math.trunc(cloud - CLOUD_CAP) + 25;
    if (S.cfg.reclaimMin) want = Math.max(want, S.cfg.reclaimMin);
    for (let i = 0; i < POOL && want > 0; i++) {
      if (!al[i]) continue;
      const i3 = i * 3;
      if (Math.hypot(pos[i3], pos[i3 + 1]) < CLOUD_R) { al[i] = 0; want--; }
    }
    cloud = CLOUD_CAP;
  }
  S.cloud = cloud;
  const cf = Math.min(cloud / CLOUD_CAP, 1.2);

  // --- the circuit decides what the electrodes actually sit at
  const V = S.cfg.circuit(S, p, cf);
  const Vg1 = V.vg1, Vg2 = V.vg2, Vp = V.vp, sup = V.sup;

  // --- thermionic emission, throttled by space charge
  let lam = Math.min(E0 * Math.exp(-T_SLOPE * (1.0 / p.T - 1.0 / T_REF)),
                     E_CLAMP);
  lam *= Math.max(0.0, 1.0 - cf);
  let k = lam > 1e-6 ? rng.poisson(lam) : 0;
  if (k > 0) {
    // numpy takes dead[:k] — the LOWEST k free slots. A forward scan matches.
    for (let i = 0; i < POOL && k > 0; i++) {
      if (al[i]) continue;
      const i3 = i * 3;
      const th = rng.uniform(0, 2 * Math.PI);
      const ct = Math.cos(th), st = Math.sin(th);
      const rr = R_C + 0.006;
      pos[i3] = rr * ct; pos[i3 + 1] = rr * st;
      pos[i3 + 2] = rng.uniform(-1.0, 1.0);
      const vr = 0.2 * Math.sqrt(p.T / T_REF) + Math.abs(rng.normal(0, 0.06));
      const vt = rng.normal(0, 0.06);
      vel[i3] = vr * ct - vt * st;
      vel[i3 + 1] = vr * st + vt * ct;
      vel[i3 + 2] = rng.normal(0, 0.06);
      al[i] = 1;
      k--;
    }
  }

  const grids = [[G1, Vg1], [G2, Vg2]];
  if (sup) grids.push([G3, 0.0]);
  const h = DT / SUBSTEPS;
  let hitsP = 0, secToScreen = 0, hitsG2 = 0, hitsG1 = 0;
  const spawn = [];

  function integrate(P_, V_, A_, n, secondary) {
    for (let i = 0; i < n; i++) {
      if (!A_[i]) continue;
      const i3 = i * 3;
      const x = P_[i3], y = P_[i3 + 1], z = P_[i3 + 2];
      const r = Math.max(Math.hypot(x, y), 1e-6);
      const ux = x / r, uy = y / r;
      let ar = radialAccel(r, Vg1, Vg2, Vp, cf, sup);
      let az = 0.0;
      for (let gi = 0; gi < grids.length; gi++) {
        const g = grids[gi][0], Vw = grids[gi][1];
        const dr = r - g.r;
        if (Math.abs(dr) < BAND && Math.abs(Vw) > 1e-3) {
          const dz = wrap(z + g.pitch / 2, g.pitch) - g.pitch / 2;
          const d2 = dr * dr + dz * dz + EPS * EPS;
          const d = Math.sqrt(d2);
          const f = g.kw * (-Vw) / d2;
          ar += f * dr / d;
          az += f * dz / d;
        }
      }
      let vx = V_[i3] + ar * ux * h;
      let vy = V_[i3 + 1] + ar * uy * h;
      let vz = V_[i3 + 2] + az * h;
      const damp = 1.0 - GAMMA * h;
      vx *= damp; vy *= damp; vz *= damp;
      const sp = Math.sqrt(vx * vx + vy * vy + vz * vz);   // pre-clamp speed
      const fcl = Math.min(1.0, V_MAX / Math.max(sp, 1e-9));
      vx *= fcl; vy *= fcl; vz *= fcl;
      const nx = x + vx * h, ny = y + vy * h, nz = z + vz * h;
      V_[i3] = vx; V_[i3 + 1] = vy; V_[i3 + 2] = vz;
      P_[i3] = nx; P_[i3 + 1] = ny; P_[i3 + 2] = nz;

      const nr = Math.hypot(nx, ny);
      const onPlate = plateS(nx, ny) >= 1.0;
      const reab = nr <= R_C + 0.002 && nx * vx + ny * vy < 0;
      const zout = Math.abs(nz) > Z_HALF;
      let kill = onPlate || reab || zout;
      // contact capture on every physical grid wire; first grid in order wins,
      // matching numpy's progressive `& ~kill`
      let wireG1 = false, wireG2 = false;
      if (!kill) {
        for (let gi = 0; gi < grids.length; gi++) {
          const g = grids[gi][0];
          const dzw = wrap(nz + g.pitch / 2, g.pitch) - g.pitch / 2;
          const wd2 = (nr - g.r) * (nr - g.r) + dzw * dzw;
          if (wd2 < g.cap * g.cap) {
            kill = true;
            if (g === G1) wireG1 = true; else if (g === G2) wireG2 = true;
            break;
          }
        }
      }
      if (secondary) {
        if (wireG2) secToScreen++;      // plate return and other losses silent
      } else {
        if (onPlate) {
          hitsP++;
          // Monte-Carlo secondary emission off the plate
          const lucky = rng.random() < SEC_YIELD;
          if (sp > SEC_VTH && lucky) spawn.push(nx, ny, nz);
        }
        if (wireG2) hitsG2++;
        if (wireG1) hitsG1++;
      }
      if (kill) A_[i] = 0;
    }
  }

  for (let s = 0; s < SUBSTEPS; s++) {
    integrate(pos, vel, al, POOL, false);
    integrate(pos2, vel2, al2, POOL2, true);
  }

  // --- launch queued secondaries just inside the plate wall, aimed inward.
  // numpy zips against the free slots, so excess spawns are silently DROPPED.
  if (spawn.length) {
    let slot = 0;
    for (let q = 0; q < spawn.length; q += 3) {
      while (slot < POOL2 && al2[slot]) slot++;
      if (slot >= POOL2) break;
      const sx = spawn[q], sy = spawn[q + 1], sz = spawn[q + 2];
      const s = plateS(sx, sy);
      const kk = Math.pow(0.93 / Math.max(s, 1e-6), 0.25);
      const rx = sx * kk, ry = sy * kk;
      const rr = Math.max(Math.hypot(rx, ry), 1e-6);
      const s3 = slot * 3;
      pos2[s3] = rx; pos2[s3 + 1] = ry; pos2[s3 + 2] = sz;
      vel2[s3] = -SEC_V0 * rx / rr + rng.normal(0, 0.08);
      vel2[s3 + 1] = -SEC_V0 * ry / rr + rng.normal(0, 0.08);
      vel2[s3 + 2] = rng.normal(0, 0.05);
      al2[slot] = 1;
      slot++;
    }
  }

  S.ip = (1.0 - IP_ALPHA) * S.ip + IP_ALPHA * (hitsP - secToScreen);
  S.ig2 = (1.0 - IP_ALPHA) * S.ig2 + IP_ALPHA * (hitsG2 + secToScreen);
  S.ikLoop += IK_LOOP_ALPHA * ((hitsP + hitsG2) - S.ikLoop);
  S.ig2Loop += IK_LOOP_ALPHA * ((hitsG2 + secToScreen) - S.ig2Loop);
  S.g1Hits = hitsG1;
  S.secAlive = countAlive(al2);

  // --- draw buffers (the renderer's only read surface)
  writeDraw(S.draw, pos, al, POOL);
  writeDraw(S.draw2, pos2, al2, POOL2);

  // --- scope ring buffers + meters
  if (S.cfg.scope) {
    const Vk = V.vk;
    S.vgBuf.copyWithin(0, 1); S.vgBuf[SCOPE_N - 1] = Vg1;
    S.genBuf.copyWithin(0, 1);
    S.genBuf[SCOPE_N - 1] = V.Vgen !== undefined ? V.Vgen : Vg1;
    S.vpBuf.copyWithin(0, 1);
    S.vpBuf[SCOPE_N - 1] = Vp + Vk;   // scope probe reads plate-to-GROUND
    S.ipShow = (V.Bp - (Vp + Vk)) / Math.max(V.RL, 1e-6);
    S.ig2Show = (V.Bp - (Vg2 + Vk)) / Math.max(V.RG2, 1e-6);
    if (p.sigAmp > 0.02) {
      const ref = S.cfg.gainFromGen ? S.genBuf : S.vgBuf;
      S.gainTxt = (std(S.vpBuf) / Math.max(std(ref), 1e-6)).toFixed(1) + "x";
    } else S.gainTxt = "--";
  }
  return S;
}

function countAlive(a) {
  let n = 0;
  for (let i = 0; i < a.length; i++) if (a[i]) n++;
  return n;
}

function writeDraw(draw, pos, al, n) {
  for (let i = 0; i < n; i++) {
    const i3 = i * 3;
    if (al[i]) {
      draw[i3] = pos[i3]; draw[i3 + 1] = pos[i3 + 1]; draw[i3 + 2] = pos[i3 + 2];
    } else {
      draw[i3] = PARK[0]; draw[i3 + 1] = PARK[1]; draw[i3 + 2] = PARK[2];
    }
  }
}

export const aliveCount = countAlive;

// ------------- sim table -----------------------------------------------------
// The four sims differ only in these fields. Everything else is shared.
export const SIMS = {
  pentode: {
    label: "Pentode tube",
    maPerE: 0.2, circuit: circuitDirect, scope: false, warm: 60,
    defaults: { T: 1100, vg1: 0, vg2: 150, vp: 250, sup: true, showGlass: true },
  },
  amp: {
    label: "RC amplifier",
    maPerE: 0.02, circuit: circuitAmp, scope: true, warm: 700,
    defaults: { T: 1100, sigDc: -3, sigAmp: 0.5, bplus: 300, rl: 100, rg2: 470,
                g2Bypass: true, sup: true, showGlass: true },
  },
  cb: {
    label: "Cathode bias",
    maPerE: 0.02, circuit: circuitCB, scope: true, gainFromGen: true,
    warm: 700,
    defaults: { T: 1100, sigDc: 0, sigAmp: 0.5, bplus: 300, rl: 100, rg2: 470,
                rk: 1.0, g2Bypass: true, kBypass: true, sup: true,
                showGlass: true },
  },
  curves: {
    label: "Plate characteristics",
    maPerE: 0.02, circuit: circuitCurves, scope: true,
    lockupBand: true, reclaimMin: 10, warm: 1500,
    defaults: { T: 1100, sigDc: -2, sigAmp: 2, bplus: 300, rl: 100, rg2: 470,
                g2Bypass: false, sup: true, showGlass: true },
  },
};
