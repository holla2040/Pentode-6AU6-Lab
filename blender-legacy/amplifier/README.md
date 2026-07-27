# Pentode (6AU6) Common-Cathode Amplifier (Blender)

> Lessons 5–7 and 10–11 of the repo's guided course use this bench:
> **[LESSONS.md](../../LESSONS.md)**.

The [pentode simulation](../pentode_sim.py) wired into the classic RC-coupled
stage — the same bench as the
[triode amplifier](https://github.com/holla2040/Blender-Triode-6SN7/tree/main/amplifier),
but with the pentode's two extra electrodes doing what they were invented for:

```
  B+ (150–500 V) ──[ R_L  20k–500k ]──► plate
  B+ (same rail) ──[ R_g2 50k–1M   ]──► screen grid g2   (+ bypass cap C)
  sine generator (amplitude + DC offset) ──► control grid g1
  supply − and generator − ──► cathode (common)
```

There are **no plate or screen voltage sliders** — both electrodes ride
**solved load lines**, coupled through the tube: `Vp = B+ − Ip·R_L` and
`Vg2 = B+ − Ig2·R_g2`, recomputed every frame against the live electron
current. The measured numbers all satisfy Ohm's law and KVL.

## What the pentode changes (vs the triode stage)

| Lesson | Triode amp | This stage |
|---|---|---|
| Gain | pinned near μ ≈ 13× no matter the load | **~32× at 100k → ~97× at 300k** — gain ≈ gm·R_L, scales with the resistor |
| Screen supply | — | R_g2 starves the screen to ~90–100 V at the default 470k — authentic RC-stage practice, and self-protective: run the tube hot and Vg2 sags |
| Bypass capacitor | — | uncheck **Screen bypass** and gain collapses ~32× → ~2–4×: the unbypassed screen ripples in anti-phase and steals the signal |
| Cutoff | −9 V kills it | at −9 V the screen **rises to B+ and pulls the tube back on** — screen-resistor self-bias fights cutoff |
| Distortion demo | grid-current clipping | uncheck **Suppressor connected** at Vp < Vg2: hundreds of orange secondaries stream plate→screen mid-cycle and the waveform kinks |

## Files

- `pentode_amp_sim.blend` — ready to open (script embedded as a text block)
- `pentode_amp_sim.py`    — standalone builder: `blender -P pentode_amp_sim.py`
- `shots/`                — rendered stills of the key operating points

## Run it

1. Open `pentode_amp_sim.blend` (or `blender -P pentode_amp_sim.py`).
2. If opening the .blend: Text Editor → `pentode_amp_sim.py` → **Run Script**
   once (re-registers the physics handler).
3. 3D view → **N** → **Pentode Amp** tab → **Run / Pause**, drag sliders live.

## Controls

Heater temp · B+ (150–500 V) · Plate resistor R_L (20k–500k, live color
bands) · **Screen resistor R_g2 (50k–1M, live color bands)** · Signal
amplitude (0–8 Vpk) · Grid bias / DC offset (−15…+5 V) ·
**Screen bypass capacitor** (the cap "C" appears on the bench when on) ·
Suppressor connected · Show glass.

Scope: 10 divisions — green g1 input (5 V/div, −20…+5 V), amber plate
output (auto-ranged 0–300 / 0–500 V with B+), GAIN readout on the bezel.
Meter and panel show B+, Vg2, Vp, Ip, Ig2, Vg1, gain — all KVL-consistent.

## Experiments for students

1. **Both rails float**: cold cathode → Vp = Vg2 = B+ (no current, no drops).
2. **Watch it bias itself**: heat the cathode; the plate settles mid-supply
   while the screen sags deep (~95 V at 470k) — the screen resistor finds
   its own operating point.
3. **Gain vs load**: A = 0.5 V; read gain ~32× at R_L = 100k, then slide to
   300k → ~97×. Try that on the triode amp: it barely moves. This is why
   pentodes were the high-gain voltage stage.
4. **The bypass capacitor**: uncheck Screen bypass → gain collapses to ~2–4×.
   Watch Vg2 on the meter ripple against the input. Re-check it and Vg2
   HOLDS at its DC value (the capacitor supplies the ripple current): full
   gain returns.
5. **Overdrive**: A = 4 → flat top at B+ (cutoff side), bottom limited near
   the pentode knee, screen sagging on the hot half-cycle.
6. **Why the suppressor exists**: R_L 300k, R_g2 150k (Vp ≈ 145 < Vg2 ≈ 185),
   uncheck Suppressor connected → ~850 orange secondaries flood plate→screen
   and the output kinks. Re-check and the stream collapses.
7. **Try to cut it off**: drag bias to −9 V — the tube won't die: as current
   falls, Vg2 rises toward B+ and turns it back on. Screen-resistor
   self-regulation, visible.

## How the circuit is solved (honest summary)

The electron engine is the verified pentode simulation (numpy frame handler,
two dupli-vert particle banks — cyan primaries, orange secondaries — 4-region
radial fields, Monte-Carlo secondary emission, mean-field space charge,
exaggerated geometry). The circuit layer per frame:

- `Vg1(t) = DC + A·sin(2πft)`, f = 0.25 Hz (code constant).
- Both load lines are solved **algebraically by nested bisection** against a
  companion model: cathode current `Ik = K̂·emis(T)·drive^1.5`, split between
  plate and screen by a calibrated fraction with a knee factor. **K̂ and the
  screen fraction are calibrated live** from the measured particle currents
  (slow, gated EMAs that persist across resets). No measured-current
  feedback loops — those ring against the ~15-frame electron transit delay
  (the lesson from the triode amplifier, twice).
- The **bypass checkbox picks which grid voltage the screen line sees**: the
  DC bias (bypassed — the capacitor holds the average, so no signal ripple)
  or the instantaneous signal (unbypassed — Vg2 ripples, gain drops).
- Displayed currents are the resistor currents `(B+−V)/R`, KVL-true always.
- `selfcheck()` asserts: cold rails at B+, both load lines converged,
  inverting monotonicity, gain 12–70× with corr < −0.7, gain scaling with
  R_L (>1.6× for 3× R_L), bypass gain ratio (>1.25×), cutoff clipping,
  tetrode secondary flood (>1.4×), stability at R_L 500k / R_g2 1M.

Same caveats as the other sims: stateful (Reset, don't scrub), one tube
project per Blender session.
