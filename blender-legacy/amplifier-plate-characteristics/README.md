# Pentode Amplifier with a Live Plate-Characteristics Display

> Lessons 8 and 12 of the repo's guided course use this display:
> **[LESSONS.md](../../LESSONS.md)**.

The [screen-resistor amplifier](../amplifier/README.md) with the instrument
a datasheet can't print: a **plate-characteristics plot whose curves move**.

## The two datasheet plots (docs/6AU6A.pdf)

- **Page 3, "Average Plate Characteristics"**: Ip(Vp) for Ec1 = 0…−5 V at a
  *fixed* screen, Ec2 = 150 V. Moving between these curves is what the
  signal on the grid does.
- **Page 4, top**: Ip(Vp) for Ec2 = 150/125/100/75/50 V at Ec1 = 0. The
  whole family **shifts downward as the screen voltage falls** — and upward
  as it rises.

These two plots are often misread as alternatives. In a real RC stage with
an **unbypassed screen resistor they happen simultaneously**: the signal
walks the operating point between the Ec1 curves (page-3 motion) while the
screen current through R_g2 moves the *entire family* up and down (page-4
motion) — and the load line, set only by B+ and R_L, never moves.

## What the display shows

- **The green family** — Ec1 = 0…−5 V (the page-3 plot), drawn every frame
  at the *instantaneous* screen voltage. The plot lines themselves move
  with Vg2: with the bypass capacitor out they breathe ~50 V worth of Vg2
  every cycle; with it in, they stand still.
- **Static white LOAD LINE** — from (B+, 0) to (0, B+/R_L), clipped to the
  plot; redrawn only when you move the B+ or R_L sliders, deliberately
  frozen during the signal.
- **Operating-point dot** — at (Vp, (B+−Vp)/R_L), always on the load line.
  The dot walks the line *between* the family lines with the grid swing —
  the classic load-line reading. Nothing travels with the dot.
- **Live Vs readout** — the screen voltage moving the family (labels use
  g / s / p for grid, screen, plate throughout the bench).

Axes: 0–500 V at 50 V/div, 0–4 mA at 0.5 mA/div (our RC-stage current
scale; the datasheet's 20 mA axis belongs to a fixed 150 V screen supply).

## The phenomenon: the unbypassed family expands AND compresses

This is the observation this simulation exists to make visible, and it is
one you will not find plotted in the classic texts: with the screen bypass
capacitor removed, the plate-characteristic family does not merely sag on
signal peaks — **it breathes in both directions around its resting
position**, rising *above* the quiescent curves on one half-cycle and
sinking *below* them on the other.

### What the end user should look for

1. **Establish the resting position.** Set signal amplitude (Vpk) to 0.
   Bypassed or unbypassed, the family settles at the same height and the
   Vg2 readout shows the same value (≈ 137 V at the defaults; the two
   modes agree to about a volt). This is the quiescent operating
   point — your visual reference line.
2. **Turn Vpk up to 2 V with the bypass OFF.** Watch the family relative
   to where it rested:
   - On the **positive half-cycle** of the grid, the family dives *below*
     the resting height (Vg2 down to ≈ 113 V at the defaults) — the
     compression everyone expects from the page-4 plot.
   - On the **negative half-cycle**, the family climbs *above* the resting
     height (Vg2 up to ≈ 164 V) — the expansion almost nobody has seen
     drawn.
   The Vg2 readout sweeps roughly ±26 V around its resting value, once per
   cycle. Meanwhile the dot slides along the unmoving load line, and the
   family it is trying to climb keeps moving under it — family low when
   the dot is high, family high when the dot is low, in antiphase.
3. **Flip the bypass ON mid-signal.** The family glides to a stop (watch
   it "charge" over a few seconds — that is the capacitor time constant)
   and parks near the *middle* of the excursion it was making. The dot
   keeps walking the load line between now-stationary lines, and the gain
   readout on the scope jumps from ~4× to ~16×.

### Why the curves actually expand and compress

The screen node obeys Ohm's law and KVL *instant by instant*:

```
Vg2(t) = B+ − Ig2(t) · R_g2
```

At rest, the screen current sits at its quiescent value (≈ 0.35 mA at the
defaults), dropping ≈ 163 V across the 470k screen resistor: Vg2 ≈ 137 V.
A signal on the grid swings the cathode current — and therefore the screen
current — **symmetrically around that bias point**, so the screen voltage
must swing both ways too:

- **Grid swings positive** → more cathode current → Ig2 rises above its
  quiescent value → a larger drop across R_g2 → **Vg2 sags below 137 V**
  → the family compresses. This is the half of the story the page-4
  datasheet plot tells.
- **Grid swings negative** → the tube heads toward cutoff → Ig2 falls
  below its quiescent value → a smaller drop across R_g2 → **Vg2 rises
  above 137 V, toward B+** → the family expands. This is the half the
  datasheet never draws, because a datasheet's screen is a stiff supply
  that never moves at all.

Compression-only would require the screen current to *never fall below*
its quiescent value — impossible when a sine wave swings the grid both
ways around the bias point. The expansion is not an artifact; it is the
same self-regulation documented in the parent amplifier ("try to cut it
off": as the grid kills the current, the screen rises toward B+ and pulls
the tube back on).

**The two-way motion is also exactly why the unbypassed gain collapses.**
The moving family is negative feedback acting on *both* half-cycles: on
the hot half the sagging screen throttles the current the grid asked for;
on the cold half the rising screen props up the current the grid tried to
kill. Both halves of the output wave get flattened — gain falls from ~16×
(bypassed) to ~4× (unbypassed) at the defaults. A family that only
compressed would mean feedback on only half the wave.

**What the bypass capacitor really does**, seen in this language: the
capacitor supplies the ripple current, so the resistor only ever carries
the *average* screen current, and the family is nailed at the
average-current height. The average current is nearly identical in both
modes (≈ 0.35 mA either way at the defaults — the cap carries the ripple,
the resistor carries the mean), which is why the bypassed family parks
near the middle of the unbypassed excursion rather than at its top or
bottom. You can check the sim's honesty by hand at any moment:
`Vg2 = B+ − Ig2·R_g2` holds on the meter panel in every frame, both modes.

### Replicating the phenomenon, step by step

All of this uses only the sliders in the **Plate Curves** sidebar tab
(N-panel), at the default component values (B+ 300 V, R_L 100k,
R_g2 470k, DC offset −2 V):

1. **Baseline** — Vpk = 0, bypass ON. Note the family height and the Vg2
   readout (≈ 137 V). Toggle the bypass OFF and wait a few seconds: same
   height, same readout. The two modes agree at rest.
2. **Two-way breathing** — bypass OFF, raise Vpk to 2. Watch one full
   cycle (4 s): family up to Vg2 ≈ 164, down to ≈ 113, once per cycle.
   Compare against the scope: the family is highest when the green input
   trace is at its bottom, lowest when the input is at its top.
3. **The antiphase dot** — same settings: dot at the top of its load-line
   travel ⇔ family at its lowest; dot at the bottom ⇔ family at its
   tallest. One current, two resistors, two displays.
4. **Freeze it** — check the bypass box mid-signal. The family glides to
   the middle of its former excursion and stops; gain jumps ~4× → ~16×.
   Uncheck it and the breathing resumes.
5. **Compression-dominant variant** — drag the DC offset to −4 V (bypass
   OFF). The quiescent screen current is now tiny, so the family rests
   high near B+ with almost no headroom above: positive swings dig deep
   sags, negative swings barely lift it. This is the closest a real
   circuit gets to the "only compresses" intuition — and it falls out of
   the same KVL with no special casing.
6. **Exaggerate / tame it** — R_g2 toward 1M deepens both directions of
   the breathing (more volts per mA); toward 50k stiffens the screen and
   the family barely moves even unbypassed. Bigger Vpk widens the
   excursion until cutoff clips the cold half.

## Controls

Sliders as in the parent project: heater, B+ (300 V), R_L (100k, live
bands), R_g2 (470k, live bands), signal amplitude (default 2 Vpk), DC
offset (default −2 V). **Screen bypass capacitor: checkbox, default OFF**.
**The suppressor is permanently connected in this build** (no tetrode
toggle). Scope, meters, and glass toggle inherited.

## Experiments

1. **Watch the breathing**: defaults (bypass off, A = 2 V) — the family
   expands and compresses ~50 V of Vg2 per cycle; the dot slides along
   the unmoving white line (see the step-by-step above).
2. **Freeze it**: check the bypass box — Vg2 parks and the family locks;
   only the dot keeps walking the load line. Gain jumps (~4× → ~16×).
   This is what the capacitor is *for*.
3. **Move the load line** (the only way it moves): drag B+ or R_L — the
   white line pivots, the dot finds the new intersection, the curves are
   unaffected. Tube physics vs circuit constraints, cleanly separated.
4. **Deeper breathing**: raise R_g2 toward 1M or raise the drive.

## Files & running

- `plate_curves_sim.blend` — open, Text Editor → Run Script once
- `plate_curves_sim.py` — or `blender -P plate_curves_sim.py`
- Sidebar (N) → **Plate Curves** tab → Run / Pause
- `shots/` — bench, the max-sag/min-sag breathing pair, and the
  bypassed (parked) comparison

Engine notes: same verified 6AU6 electron simulation and algebraic
coupled-load-line solver as the parent. All circuit solves (both bypass
modes) run on a steady slow-averaged copy of the live particle-current
calibration, so the two modes agree exactly at zero drive and calibration
noise cannot wander the operating point; the bypassed screen node is the
DC solution held through the capacitor's time constant. The display family
is drawn from the same model, so the curves, the dot, and the meters can
never disagree. Expect a fresh build (or Reset) to glide to its resting
point over the first minute — that is the calibration and the capacitor
charging, not drift. Stateful sim: Reset, don't scrub; one tube project
per Blender session.
