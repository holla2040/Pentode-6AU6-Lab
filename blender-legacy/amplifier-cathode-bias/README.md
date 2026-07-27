# Pentode Cathode-Bias Amplifier (Blender) — the complete 6AU6 stage

> Lessons 9, 13, and 14 of the repo's guided course use this bench:
> **[LESSONS.md](../../LESSONS.md)**.

The capstone of the tube series: the [screen-resistor amplifier](../amplifier/README.md)
with **cathode self-bias** added — every resistor a real 6AU6 preamp
schematic has, and **no bias supplies anywhere**.

```
  B+ ──[ R_L  20k–500k ]──► plate
  B+ ──[ R_g2 50k–1M   ]──► screen g2        (+ bypass cap, checkbox)
  generator (amplitude + DC offset, default 0) ──► grid g1
  cathode ──[ R_k 0.1k–5k ]──► COMMON        (+ bypass cap Ck, checkbox)
```

**Three coupled self-regulating loops**, solved together every frame:
cathode bias (`Vk = (Ip + Ig2)·R_k` — note the cathode carries *both*
currents), screen sag (`Vg2 = B+ − Ig2·R_g2`), and the plate load line.
At the defaults the stage biases itself to Vk ≈ 1.1 V, Vg2 ≈ 145 V,
Vp ≈ 222 V with the DC offset at zero — textbook 6AU6 numbers.

## The lessons (beyond the parent projects)

1. **The loops interact**: adding R_k *raises* the screen voltage vs the
   fixed-cathode stage (~130 V vs ~95 V) — the cathode lift throttles the
   tube, so less screen current, so less sag. Three regulators, one stable
   operating point.
2. **Two feedbacks, separated**: uncheck the **cathode** bypass → series
   feedback, gain 16.4× → 11.0×. Uncheck the **screen** bypass instead →
   gain collapses to ~6×. Both at once compound. The green Vg1k trace
   shows the cathode feedback eating the drive in real time.
3. **Still a pentode**: gain scales with R_L (~16× at 100k → ~39× at 300k) even with all the self-bias machinery in circuit.
4. **Asymmetric overdrive, pentode edition**: at A = 8 the top **rails
   clean at B+** (with the screen bypassed at ~130 V, cutoff needs only
   ≈ −8 V — compare the self-biased triode, which can't cut off at all),
   while the bottom only compresses to ~160 V because the pentode knee
   caps the plate current the load line can pull.
5. Suppressor toggle still does the tetrode secondary-emission demo.

## Files & running

- `pentode_cb_amp_sim.blend` — open, Text Editor → Run Script once
- `pentode_cb_amp_sim.py` — or `blender -P pentode_cb_amp_sim.py`
- Sidebar (N) → **Pentode CB Amp** tab → Run / Pause, drag sliders live
- `shots/` — stills: triple self-bias bench, the three-gain scope set,
  overdrive railing, and the cathode network close-up

Bench: everything from the parent (scope with Vg1k input trace, B+ supply,
banded R_L and R_g2, screen cap, generator) plus the **COMMON ground bar**,
banded **R_k**, and blue **Ck** — both caps hide when unchecked. Meters are
KVL-true on all three resistors; GAIN is stage gain from the generator
terminal.

Engine notes: verified 6AU6 electron simulation (two particle banks,
secondary emission); triple nested bisection ≈ 5.7 ms/frame; calibration
anchored to the always-computed DC solve and persistent across resets.
Stateful sim: Reset, don't scrub; one tube project per Blender session.
