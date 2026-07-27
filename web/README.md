# The 6AU6 pentode sims

Four interactive simulations in the browser: three.js for the tube and bench,
Canvas2D for the instruments, no install and no build step.

```
python3 -m http.server 8000 --directory web
# then open http://localhost:8000/
```

Or just open `web/index.html`. It is static: an import map pulls three.js
0.185.1 from a CDN, and nothing else is fetched. Deploys to GitHub Pages as-is.

Pick a simulation from the dropdown, or deep-link with `#pentode`, `#amp`,
`#cb`, `#curves`.

## Why this exists

This started as a Blender project (still in
[`../blender-legacy/`](../blender-legacy/README.md), no longer maintained).
Getting a student to a simulation used to cost: install Blender, open a
`.blend`, find the Text Editor, press Run Script, press **N**, find the tab,
then wait about a minute for the amplifier builds to settle. Now it costs a
click.

## If you are editing these files

Browsers cache ES modules hard and `http.server` sends no cache headers, so
your changes may not reach the page. Either hard-reload (Ctrl+Shift+R), or
serve with caching off:

```python
import functools, http.server, socketserver
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(("", 8000),
    functools.partial(H, directory="web")).serve_forever()
```

Note too that switching sims by hash alone (`#amp` → `#cb`) does **not** reload
the document — the app handles that with a `hashchange` listener, but your
edits will not be picked up that way.

## Files

| File | What | three.js? |
|---|---|---|
| `engine.js` | particle physics, RNG, the three circuit solvers | **no** |
| `selfcheck.js` | five physics regression suites | **no** |
| `tube.js` | tube geometry, materials, lights, cameras | yes |
| `bench.js` | bench props + the Canvas2D scope and curve tracer | yes |
| `main.js` | boot, control panel, fixed-step loop | yes |
| `index.html` | page, import map, panel markup | — |
| `pyref.py` | dev tool: runs the **original** Blender scripts headless | — |

`engine.js` and `selfcheck.js` import nothing at all. That is the whole point:
the physics runs under Node with no browser and no graphics stack, which is
where the porting risk lived.

## Verifying the physics

```
node web/selfcheck.js            # the port          (~39 s, five suites)
python3 -B web/pyref.py          # the Blender code  (~87 s, four suites)
```

`pyref.py` stubs `bpy`/`bmesh`/`mathutils` and runs the four **unmodified**
`*_sim.py` files, so the reference is the real thing rather than a
transcription of it. Its `pentode` numbers were checked against actual Blender
5.2 (`blender -b`) and match exactly.

Neither engine can match the other bit-for-bit — numpy's PCG64 and the port's
mulberry32 are different streams — so agreement is judged on values, with
`SEED=n` available on both to compare distributions rather than single samples.

Measured agreement, 1500-frame average at a fixed operating point:

| | Ip | Ig2 | cloud | Ig2/Ip |
|---|---|---|---|---|
| Python | 8.633 mA | 2.443 mA | 522 | 0.2830 |
| JS | 8.651 mA | 2.439 mA | 522 | 0.2819 |
| difference | +0.21 % | −0.16 % | 0 % | −0.39 % |

The screen-capture ratio stays inside the 0.27–0.31 band that `G2.cap = 0.0095`
was tuned to hit against `docs/6AU6A.pdf` pages 3–4, so the datasheet
calibration survives the port. Per-suite selfcheck numbers vary by more than
this because they are short runs from a cold cathode; over five seeds each, the
two implementations' distributions overlap on every metric.

`selfcheck.js` adds a fifth suite the Blender build never had — `breathe`,
which pins down the phenomenon
[`../blender-legacy/amplifier-plate-characteristics/README.md`](../blender-legacy/amplifier-plate-characteristics/README.md)
calls this project's original contribution: with the screen bypass out, the
plate-characteristic family **expands as well as compresses**.

| | rest (unbyp / byp) | driven low | driven high | bypassed span |
|---|---|---|---|---|
| Python | 138.2 / 136.7 V | 104.0 V | 156.2 V | 0.3 V |
| JS | 138.2 / 134.9 V | 108.4 V | 159.2 V | 0.3 V |

Both breathe ~50 V two-way around a ~138 V rest, and both park dead still near
the middle of that excursion once the capacitor is in.

## URL parameters

Any control can be set from the query string, so a lesson links at its exact
settings. Booleans take `0`/`1`.

```
?vg2=150&vp=60&sup=0#pentode      the tetrode kink
?view=TOP#pentode                 cross-section down the axis
?rg2=1000&sigAmp=2&g2Bypass=0#curves   deep screen breathing
?warm=0#curves                    watch it settle from cold instead
```

`view` takes `TOP`, `INSIDE`, `OVER`, `BENCH`. `warm` overrides how many frames
run before the first paint — the amplifier builds default to several hundred so
the calibration and the bypass capacitors have settled by the time you look.

## What differs from the Blender renders

- **Instruments are Canvas2D**, not curve and text objects. Sharper, and it
  replaces `_build_scope`, `_push_traces`, `_build_tracer`, `_push_curves`,
  `_write_pc_spline`, `_update_load_line`, `_ensure_fam_labels` and `_text`.
- **Lights are spots, not area lamps.** three.js `RectAreaLight` cannot cast
  shadows, and a directional light has no distance falloff — which lit the
  plate bore far too hot. Spots keep the 1/d² decay an area lamp six units away
  has. Intensities were retuned by eye against `../shots/`; there is no
  conversion between Blender Watts and three.js candela.
- **The Top cross-section is lighter inside** than
  `../shots/3_top_nominal_Vp250.png`. Both key and rim lights cast shadow maps,
  but EEVEE still puts less light down the plate bore than this does.
- **No bloom.** Neither has any: the reference renders have no halo — the
  electrons occlude the grid wires behind them. Emission strength rides
  `emissiveIntensity` through `AgXToneMapping`, which is what EEVEE's default
  view transform did.

The physics is not on this list.

## Notes

- The sim is stateful. Use **Reset**, not reload, and expect it to keep
  running while you drag sliders — that is the point.
- Physics is locked to 24 Hz by a fixed-step accumulator no matter the display
  rate. Every tuned constant in `engine.js` is per *frame*: `IP_ALPHA`,
  `K_ALPHA`, `D15_DELAY = 24`, `SCOPE_N` ("2 cycles at 0.25 Hz, 24 fps").
  Stepping at requestAnimationFrame rate would silently change all of them.
