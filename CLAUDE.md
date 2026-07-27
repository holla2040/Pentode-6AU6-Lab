# Pentode-6AU6-Lab

Four interactive 6AU6 pentode simulations. `web/` is the project. It began as a
Blender build, which now lives frozen in `blender-legacy/`.

Live: https://holla2040.github.io/Pentode-6AU6-Lab/

## Layout

| | |
|---|---|
| `web/engine.js` | particle physics, seeded RNG, the three circuit solvers |
| `web/selfcheck.js` | five physics regression suites |
| `web/tube.js` `bench.js` `main.js` | three.js scene, Canvas2D instruments, loop |
| `web/pyref.py` | runs the **original Blender scripts** as the golden reference |
| `blender-legacy/` | frozen. Do not edit — it is the reference, not a fork |

## Rules that are load-bearing

**`engine.js` and `selfcheck.js` must never import three.js, the DOM, or
anything else.** That is the whole architecture: it lets the entire physics and
circuit stack run under Node with no browser. If you add an import there, the
regression suites stop being runnable and the port stops being verifiable.

**Physics is per *frame* at a fixed 24 Hz, not per second.** `IP_ALPHA`,
`K_ALPHA`, `SF_ALPHA`, `IK_LOOP_ALPHA`, `D15_DELAY = 24`, the `0.008` capacitor
recharge, `SCOPE_N` ("2 cycles at 0.25 Hz, 24 fps") are all frame counts.
`main.js` steps a fixed accumulator for exactly this reason. Converting to
delta-time would silently change every time constant and the generator
frequency.

**Do not unify the per-sim solver constants.** They were tuned separately and
differ on purpose: bisection iterations are 22/22 in `circuitAmp` and
`circuitCurves` but 18/18/16 in `circuitCB`; the `khatSlow` EMA is a flat 0.02
in `circuitCB` but banded 0.05/0.005 in `circuitCurves`. The comments in
`plate_curves_sim.py:1117-1179` document the limit cycles that produced those
numbers.

**Python `%` is non-negative for a positive modulus; JS keeps the dividend's
sign.** The grid-pitch modulo runs on `z ∈ [-1.2, 1.2]`, negative half the time.
Use the `wrap()` helper. A bare `%` silently breaks wire capture over the lower
half of the tube and still looks plausible.

**`G2.cap = 0.0095` is a datasheet calibration**, tuned so Ic2/Ik lands in
0.27–0.31 per `docs/6AU6A.pdf` pages 3–4. Do not round it off.

## Verifying a physics change

Run both, and compare the printed values — not just pass/fail:

```
node web/selfcheck.js          # the port           ~39 s, five suites
python3 -B web/pyref.py        # the Blender code   ~87 s, four suites
```

The suites are threshold-based and deliberately loose, so passing is necessary
but not sufficient. The two engines cannot match bit-for-bit (numpy PCG64 vs
mulberry32), so judge agreement on values, and use `SEED=n` on **both** to
compare distributions rather than single samples — several metrics scatter
±20 % run to run, and the reference's own seed 0 is sometimes the outlier.

The strongest check is a long average at a fixed operating point; the two
engines agree there to within 0.4 % on Ip, Ig2 and cloud population.

## Working on the browser build

- Browsers cache ES modules hard and `python3 -m http.server` sends no cache
  headers, so **edits may not reach the page**. Serve with `Cache-Control:
  no-store` (recipe in `web/README.md`) or hard-reload. Changing only the hash
  (`#amp` → `#cb`) does not reload the document at all.
- `window.__sim` exposes `S`, `params`, `tube`, `bench`, `camera` for console
  poking. Not `window.sim` — `<select id="sim">` already owns that global.
- There is **no bloom**, deliberately: the reference renders have no halo.
  Emission rides `emissiveIntensity` through `AgXToneMapping`, which is what
  EEVEE's default view transform did.
- Point sprites need care: size attenuation collapses under an
  OrthographicCamera, and a mipmapped sprite's alpha falls below `alphaTest`
  when minified. Both made the electrons vanish entirely. See `setPointMode`.

## Conventions

- Coordinates are Blender's, verbatim. `main.js` sets
  `THREE.Object3D.DEFAULT_UP` to +Z so they copy across unchanged.
- Blender node colours are linear; `Color.setRGB(r, g, b)` takes them as-is.
- `shots/` are the visual acceptance criteria, not decoration.
