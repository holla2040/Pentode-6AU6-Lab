# Pentode (6AU6) Common-Cathode Amplifier Simulation

## Context

Fourth build: mirror the triode amplifier (`~/Blender-Triode-6SN7/amplifier/`) for the **pentode**, in **`~/Blender-Pentode-6AU6/amplifier/`**. Same circuit — B+ (150–500 V) through a plate resistor R_L (20k–500k) to the plate, sine generator (amplitude + DC offset) on g1, commons to cathode, no plate slider (load line solved live) — but the pentode changes the *lesson*:

- **Gain has no μ ceiling** (the screen isolates plate from cathode) → gain ≈ gm·R_L, so it **scales with R_L** where the triode saturated at ~μ. This is why pentodes were the high-gain stage.
- **The screen is fed from B+ through a screen resistor R_g2** (user-added requirement — the true classic RC stage): `Vg2 = B+ − Ig2·R_g2` is a **second solved load line**, coupled to the first. The Vg2 slider is replaced by an **R_g2 slider (50k–1MΩ, default 470k** → Vg2 ≈ 150 V at the default operating point, 6AU6-typical). Vg2 becomes a live readout; when the tube runs hot the screen sags — the screen resistor's self-protective action, visible.
- A **"Screen bypass" checkbox (default on)** teaches why the bypass capacitor exists: ON → Vg2 solved against the *slow* screen current (a bypassed screen holds steady at DC, full gain); OFF → Vg2 follows the signal-frequency screen current, ripples in anti-phase, and gain visibly drops. A small capacitor-can appears on the bench when bypassed.
- The **knee** becomes the bottom clipping limit: output can't swing cleanly below ~40–60 V, and Ig2 (and the screen sag) spike on that half-cycle.
- The **suppressor toggle** becomes a distortion demo: in tetrode mode, when the output swings below Vg2, secondaries (orange) stream to the screen mid-cycle and the waveform kinks.

Both parents are fully verified this session: `pentode_sim.py` (tube, 3 grids, two particle banks, secondaries, Ig2 accounting, suppressor toggle) and `amplifier_sim.py` (algebraic load-line solve with live-calibrated companion model, generator, auto-ranging scope, 3D bench). Blender + MCP alive (amplifier scene loaded, saved & pushed — safe to wipe). `pentode_sim.blend` is user-modified in the working tree — keep excluding it from commits.

## Approach: merge the two proven modules

Start from a copy of **`pentode_sim.py`** (keeps tube physics + secondaries intact), transplant the amplifier layer from **`amplifier_sim.py`**, rename to module **`pentode_amp_sim.py`** with prefix `PAMP_`, props `pamp_*`, classes `PENTAMP_*`, ops `pentamp.*`, tab **"Pentode Amp"**.

**Handler hygiene across all four sims**: name the handler `amp_pentode_frame_change` (startswith `amp_` ⇒ the triode-amp's strip list already removes it) and strip `("tri_", "pen_", "amp_")` here — any sim registering cleans up all others regardless of order.

### Circuit layer (from amplifier_sim.py, adapted to TWO coupled load lines)

- Sliders: heater, **B+** 150–500 (300), **R_L** 20k–500k (100k), **Screen resistor R_g2** 50k–1000k (470k), **amplitude** 0–8 Vpk (0.5 — pentode gain is high), **DC offset** −15…+5 (**−3**, class-A for μ2=18 cutoff ≈ −9). Checkboxes: **Screen bypass** (new, default on), suppressor, glass. No plate or screen-voltage sliders — both are solved.
- Per frame: `Vg1(t) = dc + A·sin(2π·0.25·t)`, then solve the coupled system by **nested bisection** (both monotone, ~24×24 scalar model evals, trivial cost):
  - companion model: cathode current `Ik = K̂·max(0, Vg1 + Vg2/μ2 + Vp/μp − Vsc·cf)^1.5`, split `Ip = Ik·(1−S_FRAC)·min(1, Vp/V_KNEE_M)^0.8`, `Ig2 = Ik − Ip` (whatever the plate doesn't take, the screen collects — physically right above and below the knee)
  - inner: bisect Vp on `B+ − R_L·Ip(Vp, Vg2) − Vp = 0`
  - outer: bisect Vg2 on `B+ − R_g2·Ig2(Vg2) − Vg2 = 0`, where Ig2 is the **slow EMA** current when bypassed (steady screen) or the instantaneous model current when unbypassed (screen ripples, gain drops)
- Calibration from the particle sim (slow EMAs, no servo dynamics — the lesson from the triode amp): `K̂` from measured plate+screen hits vs model Ik (EMA 0.03); `S_FRAC` from measured Ig2/(Ip+Ig2) when Vp is above the knee (EMA 0.02, seeded 0.35). `VP_SMOOTH = 0.5`, `MA_PER_E = 0.02` (real-mA scale; nominal Ik ≈ 1.1 mA → Vp ≈ 220 V, Vg2 ≈ 150 V at the defaults — 6AU6-typical).
- Displays are KVL-true by construction: Ip = `(B+ − Vp)/R_L`, Ig2 = `(B+ − Vg2)/R_g2`.

### Scene (reuse builders)

- Tube: unchanged 6AU6 build from pentode_sim.py.
- Bench: scope (10-division, IN −20…+5 V at 5 V/div, OUT auto-ranged 0–300/0–500 per B+ with self-updating labels), B+ supply, generator, and **two live-banded resistors**: R_L from B+ to the plate, **R_g2 from B+ to a g2 rod** (rods sit at ±Y) — the band updater is generalized to color both from their sliders. A small **bypass-capacitor can** from the g2 node to the common bus appears/hides with the bypass checkbox. Generator wire routes clear of the scope (lesson learned).
- Meter (4 lines): `B+ / Vg2(solved)`, `Vp / Ip`, `Ig2 / Vg1`, `Gain`. Panel mirrors it.
- Cameras: Bench (wide), Top, Inside — from pentode positions; bench camera framed like the triode amp's.

## Acceptance scenarios

| # | Settings | Expected |
|---|---|---|
| 1 | Cold (500 K) | Vp = B+ **and Vg2 = B+** (no current → no drop across either resistor) |
| 2 | Defaults (300 / R_L 100k / R_g2 470k / dc −3 / A 0) | Settles Vp ≈ 180–240 V, **Vg2 ≈ 130–170 V**; **both KVLs** hold; stable |
| 3 | A = 0.5, bypass on | Clean inverted sine, **gain ≈ 20–50×** |
| 4 | **R_L 100k → 300k at fixed drive** | **Gain grows ~linearly** (assert gain(300k) > 1.6× gain(100k)) — the pentode's signature vs the triode |
| 5 | R_g2 470k → 150k | Vg2 rises → operating current and gain rise — the screen resistor sets the operating point |
| 6 | **Bypass off** at A = 0.5 | Vg2 ripples in anti-phase, **gain drops** (assert bypassed > 1.25× unbypassed) — why the bypass cap exists |
| 7 | A = 4 | Clipping: flat top at B+, bottom near the **knee**, Ig2 + screen sag spike on the low half-cycle |
| 8 | **Suppressor off** at an op point swinging below Vg2 | Orange secondaries mid-cycle, Ig2 jumps (>1.5×), waveform visibly kinked |
| 9 | Stability | No ringing at R_L = 500k (and R_g2 1M) |

`selfcheck()` asserts 1–4, 6, 7 (top > 0.9·B+), 8 (Ig2 ratio), 9, both KVLs, plus corr(in,out) < −0.7.

## Implementation sequence (chunked MCP, screenshot gates as always)

1. Write `amplifier/pentode_amp_sim.py` locally: copy pentode_sim.py → renames → remove plate + screen-voltage sliders, add R_g2 slider + bypass checkbox → splice the coupled-load-line block into `_step` (before emission, after cf) → transplant `_build_scope`/`_build_bench`/`_push_traces`/`_upd_bplus`/meter/selfcheck from amplifier_sim.py with `pamp_` adaptation; generalize the band recolorer for two resistors; add the bypass-cap visual + its checkbox callback. `python3 -m py_compile` gate.
2. MCP: wipe, build_all → bench/top/inside screenshots (two banded resistors, bypass cap, scope).
3. Settle test at defaults (print Vp AND Vg2 traces; tune V_KNEE_M / S_FRAC seed if the op point hunts); both KVLs; then A=0.5 gain run → scope screenshot; R_L 300k gain-scaling; R_g2 150k run; bypass-off run; clipping A=4; tetrode-distortion run; `selfcheck()`.
4. Deliverables in `amplifier/`: save .blend (embed script), `shots/` (bench amplifying, scope gain, bypass on-vs-off pair, clipping-at-knee, tetrode-kink distortion, the two banded resistors), README (pentode-vs-triode gain story, screen resistor + sag, bypass-cap lesson, knee clipping, suppressor distortion), PROMPT.md (verbatim from JSONL), PLAN.md (this file). **No commit/push unless asked**; `pentode_sim.blend` stays excluded.

## Verification

Per-chunk screenshots + counters; `selfcheck()` green; live playback + mid-run slider test once at the end (procedure proven three times on this Blender instance).
