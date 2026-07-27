# The Pentode, From Electrons to Amplifiers — a Lesson Guide

A guided path through the four simulations in this repository. Followed in
order, it takes you from watching individual electrons leave a hot cathode
to choosing bias points and predicting distortion character in audio and
guitar amplifier stages — with every claim checkable on a meter, a scope,
or the moving plate-characteristics display.

**The four laboratories:**

| Sim | Open | What it teaches |
|---|---|---|
| The naked tube | `web/#pentode` | electrons, grids, why the screen and suppressor exist |
| The RC amplifier | `web/#amp` | load lines, gain, the screen resistor and its bypass |
| The self-biased stage | `web/#cb` | how real stages find their own bias |
| The living datasheet | `web/#curves` | seeing bias, swing, and compression on the Ip(Vp) plane |

Serve the page once (`python3 -m http.server 8000 --directory web`) and leave
it open — see [web/README.md](web/README.md). Pick a sim from the dropdown,
press **Run / Pause**, and drag sliders while it plays. Use **Reset** rather
than reloading; the sim is stateful.

Every lesson's **Set:** line can also go straight in the URL, so a lesson is a
link — the tetrode kink of Lesson 4 is
`web/?vg2=150&vp=60&sup=0#pentode`.

Unlike a real amp, each sim has already settled by the time you see it: the
perveance calibration and the bypass capacitors are run forward before the
first frame. Add `&warm=0` if you would rather watch one warm up from cold.

> The original Blender build lives in
> [`blender-legacy/`](blender-legacy/README.md) and is no longer maintained.
> It is kept because it is still the physics reference the browser engine is
> checked against.

---

## Part I — The tube itself (`web/#pentode`)

### Lesson 1 — Current is emission, and emission is temperature

**Set:** grid 0 V, screen 150 V, plate 250 V. Drag **Heater temp** from
minimum upward.

**Watch:** nothing conducts until the cathode glows. The electron cloud
(the space charge) forms first, hugging the cathode; only then does
current cross to the screen and plate. Drag the heater back down and the
current dies no matter what the electrodes ask for.

**The point:** every tube stage is a *current valve*, and the current on
offer is set thermionically. The space-charge cloud is the reservoir the
grids meter out. No emission, no amplifier — and everything downstream in
this guide modulates this one supply of electrons.

### Lesson 2 — The control grid: volts in, milliamps out, no grid power

**Set:** heater 1100 K, screen 150 V, plate 250 V. Sweep **Grid 1** from
0 V down to −5 V and back, slowly.

**Watch:** the Ip meter follows the grid smoothly (0 → roughly cutoff over
just a few volts), while the grid itself — being negative — collects no
electrons. Watch the cloud: a more negative grid doesn't destroy
electrons, it *turns them back* into the cloud.

**The point:** a few volts on a cold, currentless electrode controls
milliamps flowing to the plate. That asymmetry *is* amplification. Note
the transfer is curved (steeper near 0 V than near cutoff) — remember
this curvature; it becomes "distortion" in Part IV.

### Lesson 3 — Why the screen exists: the pentode's flat plate curves

**Set:** grid 0 V, screen 150 V. Now sweep **Plate voltage** from 400 V
down toward 20 V.

**Watch:** Ip barely moves across hundreds of plate volts — until Vp drops
below the knee (~60 V), where it finally collapses. Now hold Vp at 250 V
and sweep the **Screen** instead: Ip follows Vg2 eagerly.

**The point:** the screen grid electrostatically hides the plate from the
cathode. The *screen* sets the current; the *plate* merely collects it.
That is the pentode's defining property — a current source above the
knee — and it is why pentode voltage gain scales with the load resistor
(Lesson 6) instead of saturating at a μ like a triode.

### Lesson 4 — The tetrode kink and the suppressor's one job

**Set:** grid 0 V, screen 150 V, plate at 100 V (below the screen).
Uncheck **Suppressor connected**.

**Watch:** orange secondary electrons boil off the plate and stream
*backwards* to the screen — plate current drops, screen current jumps.
Re-check the suppressor and the orange stream collapses.

**The point:** fast primaries knock secondaries out of the plate; whenever
Vp < Vg2 the screen steals them (the tetrode kink — a negative-resistance
wrinkle that made early tetrodes howl). The suppressor is a nearly-free
grounded grid whose only job is to shove secondaries back home. Audio
consequence: with the suppressor in place you may run the plate *below*
the screen voltage cleanly — which large output-stage swings routinely do.

---

## Part II — Wiring it into an amplifier (`web/#amp`)

### Lesson 5 — The load line: the resistor does the volts

**Set:** defaults (B+ 300 V, R_L 100k, R_g2 470k, bypass on), amplitude 0.
Sweep **DC offset** slowly from −8 V to 0 V.

**Watch:** the meters. `Vp = B+ − Ip·R_L` at every setting — as the grid
admits more current, the *resistor* eats more of B+ and the plate falls.
Cold tube: no current, no drop, Vp = B+ ("the rails float").

**The point:** the tube converts grid volts to current; the load resistor
converts current back to (many more) volts. An amplifier is that round
trip. There is no plate-voltage knob on this bench *because the circuit
solves it* — the operating point is wherever the tube's appetite and the
resistor's supply agree. You will *see* that agreement as a dot on a line
in Lesson 8.

### Lesson 6 — Pentode gain scales with the load (triode gain doesn't)

**Set:** amplitude 0.5 V, DC −3 V, bypass on. Read the scope's GAIN
readout at R_L = 100k, then slide to 300k.

**Watch:** ~32× becomes ~97×. Try the same trick on the companion triode
amplifier (the 6SN7 triode project) and the gain barely moves off ~13×.

**The point:** a triode's gain is pinned near its μ; the pentode is a
current source, so gain ≈ gm·R_L — buy as much gain as you can afford in
supply volts. This is why the small pentode owned the high-gain voltage
stage (and the guitar-amp input) for decades.

### Lesson 7 — The screen resistor: a self-protecting, self-adjusting rail

**Set:** amplitude 0, DC −3 V. Sweep **R_g2** 100k → 1M, watching the Vg2
meter. Then set DC to −9 V and watch what refuses to happen.

**Watch:** bigger R_g2 starves the screen far below B+ (≈ 95 V at 470k).
And at −9 V the tube will not die: as current falls, the drop across R_g2
vanishes, Vg2 rises toward B+ and *pulls the tube back on*.

**The point:** feeding the screen through a resistor is standard practice
because it is self-regulating — run the stage hot and the screen sags to
protect itself; starve the tube and the screen rises to revive it. That
same two-way self-regulation becomes the star of Lessons 11–12.

---

## Part III — Bias: choosing where the stage lives

### Lesson 8 — See the bias point: a dot on a line
(`web/#curves`)

**Set:** amplitude 0, bypass on, defaults otherwise. Now sweep **DC
offset** from 0 to −5 V slowly and watch the plate-characteristics
display.

**Watch:** the white load line never moves (only B+ and R_L may move it).
The dot — the operating point — walks *along* the line as you re-bias:
near the top-left at 0 V (heavy current, low Vp), near the bottom-right
at −5 V (starved, Vp near B+). The green family stands still; the dot
moves *between* its lines.

**The point:** "choosing a bias point" means literally *choosing where on
the load line the stage idles*. Everything about the stage's character —
clean headroom, clipping behavior, distortion flavor — follows from that
one choice:

- **Center bias** (dot mid-line, Vp ≈ B+/2… here DC ≈ −2 V): maximum
  symmetric swing before *either* end misbehaves. The hi-fi choice.
- **Cold bias** (dot low-right): lots of downward-current headroom, but
  the cold half-cycle reaches cutoff early — expect flat-topped output.
- **Hot bias** (dot high-left): the hot half-cycle drives Vp into the
  knee early — expect the bottom of the output to compress first.

### Lesson 9 — Self-bias: the stage that finds its own operating point
(`web/#cb`)

**Set:** defaults (R_k 1k, both bypass caps on, DC offset 0). Watch Vk on
the meter. Then sweep **R_k** 0.5k → 5k.

**Watch:** with zero applied bias the stage sits at Vk ≈ 1.1 V — the
cathode has lifted *itself* above the grounded grid, biasing the tube
Vgk ≈ −1.1 V. Bigger R_k → more lift → colder bias, automatically.

**The point:** real stages don't ship with a −2 V battery. The cathode
resistor turns the tube's own current into its bias, and the loop is
self-stabilizing: a hotter tube pulls more current → more cathode lift →
more negative Vgk → current pulled back down. Manufacturing spread and
aging get absorbed. Note the interplay: adding R_k also *raises* the
screen voltage (less current → less R_g2 sag) — three regulators, one
operating point, all visible on the meters.

---

## Part IV — Amplitude and distortion: audio amps vs guitar amps

The scope is your distortion meter here: a clean stage shows an output
sine that is a scaled, inverted copy of the input. Distortion is anything
you can *see* diverging — flattening, asymmetry, one half-cycle fatter
than the other.

### Lesson 10 — Small-signal: the linear fiction that hi-fi lives in

**Sim:** the RC amplifier. **Set:** center bias (DC −2 V), bypass on,
amplitude 0.25 V.

**Watch:** output is a clean inverted sine; gain steady. Raise amplitude
in steps — 0.5, 1, 1.5 V — and watch the output's *bottom* half (the
inverted hot half) start to fatten before anything actually clips: the
tube's transfer curve (Lesson 2's curvature) is steeper at the top of the
swing than the bottom.

**The point:** "linear" is a small-signal approximation. The curvature
produces mostly **second harmonic** at moderate levels — the gentle,
"warm" coloration audio folklore attributes to tubes. A hi-fi voltage
stage is designed to *stay* in this region: center bias, small fraction
of available swing, bypassed screen and cathode.

### Lesson 11 — Overdrive: the two clip edges are different animals

**Sim:** the RC amplifier. **Set:** DC −3 V, bypass on, amplitude 4 V.

**Watch:** the top of the output rails *flat at B+* — on the cold
half-cycle the tube cuts off entirely and the resistor has nothing to
drop. The bottom does something different: it *compresses* near the knee
rather than slicing flat — the plate has run out of voltage headroom and
the load line has run out of current the pentode can deliver below the
knee.

**The point:** cutoff clipping is **hard** (an abrupt corner → strong
odd harmonics, buzzy, bright); knee-side limiting is **soft**
(progressive rounding → compressive, smoother). Your *bias choice picks
which edge the signal hits first* (Lesson 8):

- **Audio/hi-fi:** center-bias and keep amplitude out of both edges;
  distortion is a defect to be minimized.
- **Guitar:** the clip edges *are the product*. Cold-bias the stage
  (DC −4…−5 V) and the pick attack slams the cutoff edge — aggressive,
  trebly break-up. Hot-bias it and the knee compresses the lows first —
  fat, smooth crunch. Same tube, same circuit, opposite character; the
  bias knob is a *voicing* knob.

Also try amplitude 8 V at DC −3: both edges at once — full square-ish
drive, the classic saturated pentode rasp.

### Lesson 12 — Screen compression: the sag that guitar players call "feel"
(`web/#curves`)

**Set:** defaults, **bypass OFF**, amplitude 2 V. Watch the green family
and the Vg2 readout for a few cycles. Then check the bypass box
mid-signal.

**Watch:** unbypassed, the *entire plate-characteristics family breathes*
— down to Vg2 ≈ 113 V on the hot half-cycle, up to ≈ 164 V on the cold
one — while the load line and dot do their usual dance. Gain reads ~4×.
Check the box: the family parks, gain leaps to ~16×.

**The point:** the unbypassed screen is negative feedback applied *by the
tube's own current, at signal speed, on both half-cycles* — it throttles
the peaks and props up the troughs (the full physics write-up lives in
`amplifier-plate-characteristics/README.md`). Musically this is
**compression**: the harder the input hits, the more the screen sags and
takes gain away — then it *blooms* back as the note decays. In real
guitar amps the same mechanism appears at two scales:

- **Per-cycle** (this display): screen resistor + small/no bypass cap →
  waveform-level squash, part of the "tube warmth" even before clipping.
- **Per-note** (envelope sag): an undersized screen bypass or a soft
  power supply sags over tens of milliseconds — the touch-responsive
  give that players describe as the amp *breathing with them*.

Hi-fi kills this on purpose (big bypass cap: Lesson 12's checkbox);
guitar designers *size* it. R_g2 is your sag-depth knob: sweep it toward
1M with the bypass off and watch the family's breathing deepen.

### Lesson 13 — Cathode feedback: the other bypass cap
(`web/#cb`)

**Set:** amplitude 0.5, all caps on. Note the gain (~16×). Uncheck the
**cathode** bypass only. Then instead uncheck the **screen** bypass only.

**Watch:** cathode cap out: gain drops to ~11× — the green Vg1k scope
trace shows the cathode literally *eating* part of the input. Screen cap
out: gain collapses to ~6× (the Lesson-12 mechanism, here with self-bias
in the loop too).

**The point:** every electrode the signal current touches is a potential
feedback path, and each cap is a switch on one of them. Series cathode
feedback is *clean* — it reduces gain and distortion together (hi-fi
tolerates or exploits it; the classic "cathode-bypass cap value" argument
in guitar circles is really a brightness/feel control, since a small cap
bypasses treble only). Screen feedback is *characterful* — compressive
and level-dependent. A designer chooses gain, headroom, and feel largely
by deciding **which caps to fit and how large**.

### Lesson 14 — The recipe card

Everything above, condensed into two designs you can dial in and compare
on the self-biased capstone sim:

**A hi-fi voltage stage** — clean gain, minimal coloration:
R_k for center bias (dot mid-line, Lesson 8) · both bypass caps **in**
and large · amplitude comfortably inside both clip edges · R_g2 modest
(stiff screen) · result: maximum clean swing, mostly-second-harmonic
residue at worst.

**A guitar preamp stage** — controlled misbehavior:
bias off-center on purpose (cold for edge, hot for fat) · screen bypass
**small or absent** → per-cycle compression and touch sag (Lesson 12) ·
cathode bypass chosen for feel (out = tighter and quieter; in = fuller
and hotter) · amplitude *into* the chosen clip edge · result: the
distortion spectrum and the dynamics are design parameters, not defects.

The pentode's gift in both cases is the same flat-curve, current-source
physics from Lesson 3 — hi-fi buys clean gain with it; guitar buys a
high-gain stage whose overload character is unusually *shapeable*. Once
you can read the dot, the line, and the breathing family, you can predict
what any pentode gain stage will do before you build it.

---

*Simulations are pedagogical: exaggerated geometry, companion-model
circuit solving calibrated live from the particle currents, KVL-true
meters. They demonstrate mechanisms and trends, not SPICE-accurate
numbers — every mechanism above, though, is the real one.*
