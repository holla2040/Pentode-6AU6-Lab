// Physics regression for the ported engine.  Run:  node web/selfcheck.js
//
// These are the four selfcheck() suites from the Blender scripts, ported
// assertion-for-assertion. They import only engine.js — no three.js, no DOM —
// so they prove the physics headlessly, which is where the porting risk is.
//
// Golden reference (python3 -B web/pyref.py, which runs the ORIGINAL Blender
// scripts under a bpy stub; sim 1 verified identical against real Blender):
//
//   pentode  Ip(250)=8.3 Ip(80)=7.7 Ip(15)=2.2 | Ig2 nom=1.7 knee=5.9
//            | kink 2.8 vs 8.3 mA
//   amp      Vp=240V Vg2=99V | gain 31.5x@100k -> 97.5x@300k (corr -0.97)
//            | unbypassed 2.3x | kink secondaries 58->656
//   cb       Vk=1.10V Vg2=147V Vp=222V | gain full 16.4x, Rk-unbyp 11.0x,
//            g2-unbyp 6.2x, RL300k 38.7x (corr -0.96)
//   curves   Vp=242V Vg2=105V | gain 16.4x@100k -> 52.8x@300k (corr -0.99)
//            | unbypassed 4.2x | family 1.09>0.28mA, sag@100V 0.60mA
//            | Vg2 swing 50.0V
//
// The asserts are the pass/fail gate; the printed numbers are the real
// comparison. A different RNG stream cannot reproduce numpy bit-for-bit, so
// agreement is judged on the values, not on identity.

import { SIMS, makeState, reset, step, std, corr, aliveCount, pcModelMa }
  from "./engine.js";

let failures = 0;
const ok = (cond, msg) => {
  if (!cond) { failures++; console.error(`  FAIL: ${msg}`); }
};
const f1 = (x) => x.toFixed(1);
const f0 = (x) => x.toFixed(0);
const tail = (buf, n) => buf.slice(Math.max(0, buf.length - n));
const maxOf = (a) => a.reduce((m, v) => (v > m ? v : m), -Infinity);
const minOf = (a) => a.reduce((m, v) => (v < m ? v : m), Infinity);

/** Build a fresh sim whose calibration persists across run() calls, as the
 *  Python `_S` dict does (reset_electrons keeps khat/sfrac/d15). */
const SEED = Number(process.env.SEED || 0);

function harness(key) {
  const cfg = SIMS[key];
  const S = makeState(cfg, SEED);
  return (params, frames) => {
    const p = { ...cfg.defaults, ...params };
    reset(S, p);
    for (let i = 0; i < frames; i++) step(S, p);
    return S;
  };
}

// ---------------------------------------------------------------- bare tube
function checkPentode() {
  const run0 = harness("pentode");
  const M = SIMS.pentode.maPerE;
  const run = (T, vg1, vg2, vp, sup = true, frames = 54) => {
    const S = run0({ T, vg1, vg2, vp, sup }, frames);
    return [S.ip * M, S.ig2 * M, aliveCount(S.alive)];
  };

  let [ip, , alive] = run(500, 0, 150, 250);
  ok(alive < 20 && ip < 0.5, `cold cathode leaks: Ip=${ip.toFixed(2)}`);
  [ip] = run(1100, 0, 0, 300);
  ok(ip < 1.0, `screen off but Ip=${ip.toFixed(2)} — plate should not reach cathode`);
  [ip, , alive] = run(1100, -8, 150, 250);
  ok(ip < 1.0, `cutoff leaks: Ip=${ip.toFixed(2)}`);
  ok(alive > 300, `no cloud at cutoff: ${alive}`);
  const [ipHi, ig2Hi] = run(1100, 0, 150, 250);
  ok(ipHi > 4.0, `no conduction: Ip=${ipHi.toFixed(2)}`);
  ok(ig2Hi > 0.5, `no screen current: Ig2=${ig2Hi.toFixed(2)}`);
  const [ipLo] = run(1100, 0, 150, 80);
  const flat = Math.abs(ipHi - ipLo) / ipHi;
  ok(flat < 0.30, `not pentode-flat: Ip(250)=${f1(ipHi)} Ip(80)=${f1(ipLo)}`);
  const [ipKnee, ig2Knee] = run(1100, 0, 150, 15);
  ok(ipKnee < 0.6 * ipLo, `no knee: Ip(15)=${f1(ipKnee)} vs Ip(80)=${f1(ipLo)}`);
  ok(ig2Knee > ig2Hi, "Ig2 should spike below the knee");
  const [ipTet] = run(1100, 0, 150, 60, false);
  const [ipPen] = run(1100, 0, 150, 60, true);
  ok(ipTet < 0.7 * ipPen,
     `tetrode kink missing: Ip(tet)=${f1(ipTet)} vs Ip(pen)=${f1(ipPen)}`);

  console.log(`pentode  Ip(250)=${f1(ipHi)} Ip(80)=${f1(ipLo)} ` +
    `Ip(15)=${f1(ipKnee)} | Ig2 nom=${f1(ig2Hi)} knee=${f1(ig2Knee)} | ` +
    `kink: ${f1(ipTet)} vs ${f1(ipPen)} mA`);
}

// ------------------------------------------------------------ RC amplifier
function checkAmp() {
  const run0 = harness("amp");
  const M = SIMS.amp.maPerE;
  const run = (T, dc, A, bp, rl, rg2, frames, sup = true, byp = true) =>
    run0({ T, sigDc: dc, sigAmp: A, bplus: bp, rl, rg2, sup, g2Bypass: byp },
         frames);

  let S = run(500, -3, 0, 300, 100, 470, 100);      // cold: rails float to B+
  ok(S.vp > 0.97 * 300 && S.vg2 > 0.97 * 300,
     `cold but Vp=${f0(S.vp)} Vg2=${f0(S.vg2)}`);

  S = run(1100, -3, 0, 300, 100, 470, 700, true, false);   // settle
  const vp0 = S.vp, vg20 = S.vg2;
  const ip0 = S.ikLoop - S.ig2Loop, ig20 = S.ig2Loop;
  ok(0.30 * 300 < vp0 && vp0 < 0.92 * 300, `bad plate op point Vp=${f0(vp0)}`);
  ok(55 < vg20 && vg20 < 230, `bad screen op point Vg2=${f0(vg20)}`);
  const kvlP = Math.abs(300.0 - vp0 - ip0 * M * 100.0);
  const kvlS = Math.abs(300.0 - vg20 - ig20 * M * 470.0);
  ok(kvlP < 30.0, `plate load line off by ${f1(kvlP)} V`);
  ok(kvlS < 40.0, `screen load line off by ${f1(kvlS)} V`);
  ok(std(tail(S.vpBuf, 24)) < 6.0, "plate loop ringing");

  const vpNeg = run(1100, -7, 0, 300, 100, 470, 340, true, false).vp;
  const vpPos = run(1100, -1, 0, 300, 100, 470, 340, true, false).vp;
  ok(vpNeg > vp0 && vp0 > vpPos,
     `not inverting: ${f0(vpNeg)} > ${f0(vp0)} > ${f0(vpPos)} expected`);

  S = run(1100, -3, 0.5, 300, 100, 470, 760);      // small-signal, bypassed
  const g100 = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  const cc = corr(S.vgBuf, S.vpBuf);
  ok(12.0 < g100 && g100 < 70.0, `gain ${f1(g100)} out of range`);
  ok(cc < -0.7, `output not inverted (corr=${cc.toFixed(2)})`);

  S = run(1100, -3, 0.5, 300, 300, 470, 760);      // pentode: gain ~ RL
  const g300 = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  ok(g300 > 1.6 * g100,
     `gain should scale with RL: ${f1(g300)} !> 1.6x${f1(g100)}`);

  S = run(1100, -3, 0.5, 300, 100, 470, 460, true, false);
  const gUn = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  ok(g100 > 1.25 * gUn,
     `unbypassed screen should cut gain: ${f1(g100)} !> 1.25x${f1(gUn)}`);

  S = run(1100, -3, 4, 300, 100, 470, 760);        // overdrive: cutoff clipping
  ok(maxOf(tail(S.vpBuf, 192)) > 0.9 * 300, "no cutoff clipping");

  // kink needs Vp below Vg2: high Vg2 (small Rg2) + low Vp (big RL). The
  // visible signature is the orange secondaries in flight, not the meter.
  const secPen = aliveCount(run(1100, -3, 1.0, 300, 300, 150, 380).alive2);
  const secTet = aliveCount(
    run(1100, -3, 1.0, 300, 300, 150, 380, false).alive2);
  ok(secTet > 1.4 * Math.max(secPen, 10),
     `tetrode mode should free secondaries: ${secTet} !> 1.4x${secPen}`);

  S = run(1100, -3, 0, 300, 500, 1000, 340);       // stability at max resistors
  ok(std(tail(S.vpBuf, 24)) < 20.0, "unstable at RL=500k/Rg2=1M");

  console.log(`amp      op Vp=${f0(vp0)}V Vg2=${f0(vg20)}V | gain ` +
    `${f1(g100)}x@100k -> ${f1(g300)}x@300k (corr ${cc.toFixed(2)}) | ` +
    `unbypassed ${f1(gUn)}x | kink secondaries ${secPen}->${secTet}`);
}

// ---------------------------------------------------------- cathode bias
function checkCB() {
  const run0 = harness("cb");
  const M = SIMS.cb.maPerE;
  const run = (T, dc, A, bp, rl, rg2, rk, frames,
               sup = true, g2b = true, kb = true) =>
    run0({ T, sigDc: dc, sigAmp: A, bplus: bp, rl, rg2, rk, sup,
           g2Bypass: g2b, kBypass: kb }, frames);

  let S = run(500, 0, 0, 300, 100, 470, 1.0, 100);       // cold: rails float
  ok(S.vp > 0.97 * 300 && S.vg2 > 0.95 * 300 && S.vk < 0.2,
     `cold: Vp=${f0(S.vp)} Vg2=${f0(S.vg2)} Vk=${S.vk.toFixed(2)}`);

  S = run(1100, 0, 0, 300, 100, 470, 1.0, 700, true, false, false);
  const vp0 = S.vp, vg20 = S.vg2, vk0 = S.vk;
  const ip0 = (S.ikLoop - S.ig2Loop) * M, ig20 = S.ig2Loop * M;
  ok(0.3 < vk0 && vk0 < 3.5, `cathode self-bias off: Vk=${vk0.toFixed(2)}`);
  ok(45 < vg20 && vg20 < 230, `screen op point off: Vg2=${f0(vg20)}`);
  ok(0.30 * 300 < vp0 + vk0 && vp0 + vk0 < 0.93 * 300,
     `plate op off: ${f0(vp0 + vk0)}`);
  const kvlP = Math.abs(300.0 - (vp0 + vk0) - ip0 * 100.0);
  const kvlS = Math.abs(300.0 - (vg20 + vk0) - ig20 * 470.0);
  const kvlK = Math.abs(vk0 - (ip0 + ig20) * 1.0);
  ok(kvlP < 30.0, `plate KVL off ${f1(kvlP)} V`);
  ok(kvlS < 40.0, `screen KVL off ${f1(kvlS)} V`);
  ok(kvlK < 0.8, `cathode KVL off ${kvlK.toFixed(2)} V`);
  ok(std(tail(S.vpBuf, 24)) < 6.0, "ringing");

  const vpNeg = run(1100, -3, 0, 300, 100, 470, 1.0, 380, true, false, false).vp;
  const vpPos = run(1100, 2, 0, 300, 100, 470, 1.0, 380, true, false, false).vp;
  ok(vpNeg > vp0 && vp0 > vpPos, "not inverting");

  S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900);        // all bypassed
  const gFull = std(S.vpBuf) / Math.max(std(S.genBuf), 1e-6);
  const cc = corr(S.genBuf, S.vpBuf);
  ok(10.0 < gFull && gFull < 70.0, `gain ${f1(gFull)} out of range`);
  ok(cc < -0.7, `not inverted (corr=${cc.toFixed(2)})`);

  S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900, true, true, false);
  const gKun = std(S.vpBuf) / Math.max(std(S.genBuf), 1e-6);
  ok(gFull > 1.10 * gKun,
     `cathode feedback should cut gain: ${f1(gFull)} !> 1.10x${f1(gKun)}`);

  S = run(1100, 0, 0.5, 300, 100, 470, 1.0, 900, true, false, true);
  const gSun = std(S.vpBuf) / Math.max(std(S.genBuf), 1e-6);
  ok(gFull > 1.25 * gSun,
     `screen feedback should cut gain: ${f1(gFull)} !> 1.25x${f1(gSun)}`);

  S = run(1100, 0, 0.5, 300, 300, 470, 1.0, 900);        // gain ~ RL
  const g300 = std(S.vpBuf) / Math.max(std(S.genBuf), 1e-6);
  ok(g300 > 1.5 * gFull, `gain not scaling with RL: ${f1(g300)}`);

  S = run(1100, 0, 8, 300, 100, 470, 1.0, 900);          // overdrive
  ok(maxOf(tail(S.vpBuf, 192)) > 0.95 * 300, "top not railing");
  ok(minOf(tail(S.vpBuf, 192)) < 180.0, "no bottom compression");

  S = run(1100, 0, 0, 300, 500, 1000, 5.0, 340);         // stability at maxima
  ok(std(tail(S.vpBuf, 24)) < 20.0, "unstable at max R values");

  console.log(`cb       self-bias Vk=${vk0.toFixed(2)}V Vg2=${f0(vg20)}V ` +
    `Vp=${f0(vp0 + vk0)}V (dc=0) | gain full ${f1(gFull)}x, ` +
    `Rk-unbyp ${f1(gKun)}x, g2-unbyp ${f1(gSun)}x, RL300k ${f1(g300)}x ` +
    `(corr ${cc.toFixed(2)})`);
}

// --------------------------------------------------- plate characteristics
function checkCurves() {
  const cfg = SIMS.curves;
  const S = makeState(cfg, SEED);
  const M = cfg.maPerE;
  let last = null;
  const run = (T, dc, A, bp, rl, rg2, frames, byp = true) => {
    last = { ...cfg.defaults, T, sigDc: dc, sigAmp: A, bplus: bp, rl, rg2,
             g2Bypass: byp };
    reset(S, last);
    for (let i = 0; i < frames; i++) step(S, last);
    return S;
  };

  run(500, -3, 0, 300, 100, 470, 100);       // cold: both rails float to B+
  ok(S.vp > 0.97 * 300 && S.vg2 > 0.97 * 300,
     `cold but Vp=${f0(S.vp)} Vg2=${f0(S.vg2)}`);

  // long settle: calibration persists across resets, so the starting K can be
  // far from this op point's value after other runs
  run(1100, -3, 0, 300, 100, 470, 4500, false);
  const vp0 = S.vp, vg20 = S.vg2;
  const ip0 = S.ikLoop - S.ig2Loop, ig20 = S.ig2Loop;
  ok(0.30 * 300 < vp0 && vp0 < 0.92 * 300, `bad plate op point Vp=${f0(vp0)}`);
  ok(55 < vg20 && vg20 < 230, `bad screen op point Vg2=${f0(vg20)}`);
  const kvlP = Math.abs(300.0 - vp0 - ip0 * M * 100.0);
  const kvlS = Math.abs(300.0 - vg20 - ig20 * M * 470.0);
  ok(kvlP < 30.0, `plate load line off by ${f1(kvlP)} V`);
  // bound is 70 V, not 40: this op point's real load-line intersection sits
  // inside the engine's cloud-choke fold, and the fast-cf pairing parks the
  // solve ABOVE the fold with a deliberate steady ~50 V brake offset.
  ok(kvlS < 70.0, `screen load line off by ${f1(kvlS)} V`);
  ok(std(tail(S.vpBuf, 24)) < 6.0, "plate loop ringing");

  const vpNeg = run(1100, -7, 0, 300, 100, 470, 340, false).vp;
  const vpPos = run(1100, -1, 0, 300, 100, 470, 340, false).vp;
  ok(vpNeg > vp0 && vp0 > vpPos,
     `not inverting: ${f0(vpNeg)} > ${f0(vp0)} > ${f0(vpPos)} expected`);

  run(1100, -3, 0.5, 300, 100, 470, 760);              // small-signal gain
  const g100 = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  const cc = corr(S.vgBuf, S.vpBuf);
  ok(12.0 < g100 && g100 < 70.0, `gain ${f1(g100)} out of range`);
  ok(cc < -0.7, `output not inverted (corr=${cc.toFixed(2)})`);

  run(1100, -3, 0.5, 300, 300, 470, 760);              // gain ~ RL
  const g300 = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  ok(g300 > 1.6 * g100,
     `gain should scale with RL: ${f1(g300)} !> 1.6x${f1(g100)}`);

  run(1100, -3, 0.5, 300, 100, 470, 460, false);       // why bypass caps exist
  const gUn = std(S.vpBuf) / Math.max(std(S.vgBuf), 1e-6);
  ok(g100 > 1.25 * gUn,
     `unbypassed screen should cut gain: ${f1(g100)} !> 1.25x${f1(gUn)}`);

  run(1100, -3, 4, 300, 100, 470, 760);                // overdrive
  ok(maxOf(tail(S.vpBuf, 192)) > 0.9 * 300, "no cutoff clipping");

  // the display's model: page-3 family ordering (Ec1=0 on top) and page-4
  // compression (lower Vg2 -> lower curve) at a mid-plate voltage
  const at300 = [300.0];
  const yTop = pcModelMa(S, at300, 0.0, 150.0)[0];
  const yBot = pcModelMa(S, at300, -5.0, 150.0)[0];
  const ySag = pcModelMa(S, at300, 0.0, 100.0)[0];
  ok(yTop > yBot + 0.2, `family inverted: ${yTop.toFixed(2)} vs ${yBot.toFixed(2)}`);
  ok(ySag < 0.8 * yTop, `no Vg2 compression: ${ySag.toFixed(2)} vs ${yTop.toFixed(2)}`);

  // unbypassed drive must actually swing the screen (the whole point)
  run(1100, -2, 2.0, 300, 100, 470, 460, false);
  let lo = S.vg2, hi = S.vg2;
  for (let i = 0; i < 96; i++) {
    step(S, last);
    lo = Math.min(lo, S.vg2); hi = Math.max(hi, S.vg2);
  }
  const swing = hi - lo;
  ok(swing > 8.0, `screen barely swings: ${f1(swing)} V over a cycle`);

  run(1100, -3, 0, 300, 500, 1000, 340);               // stability at maxima
  ok(std(tail(S.vpBuf, 24)) < 20.0, "unstable at RL=500k/Rg2=1M");

  console.log(`curves   op Vp=${f0(vp0)}V Vg2=${f0(vg20)}V | gain ` +
    `${f1(g100)}x@100k -> ${f1(g300)}x@300k (corr ${cc.toFixed(2)}) | ` +
    `unbypassed ${f1(gUn)}x | family ${yTop.toFixed(2)}>${yBot.toFixed(2)}mA, ` +
    `sag@100V ${ySag.toFixed(2)}mA | Vg2 swing ${f1(swing)}V`);
}

// ------------------------------------------------- the screen "breathing"
// The phenomenon amplifier-plate-characteristics/README.md:42-123 calls this
// project's original contribution, and which the Blender build has no test
// for: with the screen bypass out, the plate-characteristic family does not
// merely sag on signal peaks — it breathes BOTH ways around its resting
// position. Compression-only would need Ig2 never to fall below quiescent,
// which is impossible when a sine swings the grid both ways.
//
// Reference (python3 -B web/pyref.py equivalent, seed 0):
//   rest unbyp=138.2 byp=136.7 | drive lo=104.0 hi=156.2 mean=130.2
//   | byp-drive lo=128.4 hi=128.7 mean=128.5
function checkBreathing() {
  const cfg = SIMS.curves;
  const S = makeState(cfg, SEED);
  let p;
  const run = (A, byp, frames) => {
    p = { ...cfg.defaults, T: 1100, sigDc: -2.0, sigAmp: A, bplus: 300,
          rl: 100, rg2: 470, g2Bypass: byp };
    reset(S, p);
    for (let i = 0; i < frames; i++) step(S, p);
  };
  const sweep = (n = 96) => {          // one full 0.25 Hz cycle at 24 fps
    let lo = S.vg2, hi = S.vg2;
    for (let i = 0; i < n; i++) {
      step(S, p); lo = Math.min(lo, S.vg2); hi = Math.max(hi, S.vg2);
    }
    return [lo, hi];
  };

  run(0, false, 2500); const rUn = S.vg2;
  run(0, true, 2500);  const rBy = S.vg2;
  ok(Math.abs(rUn - rBy) < 8.0,
     `modes disagree at rest: unbyp ${f1(rUn)} vs byp ${f1(rBy)}`);

  run(2, false, 2500);
  const [lo, hi] = sweep();
  ok(hi > rUn + 8.0, `family never expands above rest: hi=${f1(hi)} rest=${f1(rUn)}`);
  ok(lo < rUn - 8.0, `family never compresses below rest: lo=${f1(lo)} rest=${f1(rUn)}`);

  run(2, true, 2500);
  const [blo, bhi] = sweep();
  ok(bhi - blo < 4.0, `bypassed screen should stand still, swings ${f1(bhi - blo)} V`);
  const mid = 0.5 * (lo + hi), park = 0.5 * (blo + bhi);
  ok(Math.abs(park - mid) < 15.0,
     `bypassed should park mid-excursion: ${f1(park)} vs mid ${f1(mid)}`);

  console.log(`breathe  rest unbyp=${f1(rUn)} byp=${f1(rBy)} | ` +
    `drive lo=${f1(lo)} hi=${f1(hi)} (span ${f1(hi - lo)}V, two-way) | ` +
    `bypassed span ${f1(bhi - blo)}V parked ${f1(park)} vs mid ${f1(mid)}`);
}

const ALL = { pentode: checkPentode, amp: checkAmp, cb: checkCB,
              curves: checkCurves, breathe: checkBreathing };
const want = process.argv.slice(2).filter((a) => a in ALL);
for (const key of (want.length ? want : Object.keys(ALL))) {
  const t0 = Date.now();
  const before = failures;
  ALL[key]();
  console.log(`  (${key}: ${((Date.now() - t0) / 1000).toFixed(1)}s` +
              `${failures > before ? `, ${failures - before} FAILED` : ""})`);
}
process.exitCode = failures ? 1 : 0;
