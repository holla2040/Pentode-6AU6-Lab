# Pentode Amplifier with Live Plate-Characteristics Display

## Context

From `docs/6AU6A.pdf` (now in the pentode repo): page 3's plate-characteristics family (Ec1 = 0…−5 V at Ec2 = 150 V) and page 4's family (Ec1 = 0, Ec2 = 150/125/100/75/50 V). The user's teaching point — often misunderstood: with the **screen bypass capacitor removed**, rising plate current sags the plate voltage through R_L *and* rising screen current sags the screen voltage through R_g2; the sagging Vg2 **compresses the plate-characteristic curves downward (page-4 behavior) in real time, while the load line (B+, R_L) never moves**. The operating point is always the intersection of the moving curve and the fixed line.

Deliverable: a new Blender animation based on the screen-resistor pentode amplifier, adding — alongside the scope — a **dynamic Plate Characteristics display**: live curve positioned by the instantaneous screen voltage, static load line, operating-point dot, and (user-confirmed) a faint static Ec1 reference family at Vg2 = 150 V so the compression below the fixed-screen reference is visible.

Blender is running again (MCP reconnect to be verified at build start; `/snap/bin/blender` also exists as a headless fallback). `docs/` is untracked — include it in the commit. `amplifier-cathode-bias/pentode_cb_amp_sim.blend` is user-modified (their play save) — include in the final commit like last time's scene-state commits.

## Location & naming

`~/Blender-Pentode-6AU6/amplifier-plate-characteristics/`, module **`plate_curves_sim.py`** (unique module name), prefix `PCV_`, props `pcv_*`, classes `PCURVES_*`, ops `pcurves.*`, tab **"Plate Curves"**, handler **`amp_pcv_frame_change`** (`amp_`-prefixed per the cross-project strip-list convention).

**Base: copy `amplifier/pentode_amp_sim.py`** (screen-resistor stage — cathode grounded, so plate-to-ground = plate-to-cathode, matching the datasheet axes; no R_k). The solver, calibration, scope, bench, and selfcheck machinery carry over untouched; this project only adds an instrument.

## The Plate Characteristics display (the new component)

A second screen on the bench, placed back-right (~(4.3, 1.5, 1.3), rotated to face the bench camera; final position nudged via screenshot like the scope was). Axes datasheet-style, static: **X = plate voltage 0–500 V (50 V/div, 10 div)**, **Y = plate current 0–4 mA (0.5 mA/div, 8 div)** (our RC-stage currents, not the datasheet's fixed-supply 20 mA scale). Local mapping: div = 0.3 units → screen ≈ 3.0×2.4.

| Element | Behavior |
|---|---|
| Graticule + labels | static; title "PLATE CHARACTERISTICS", "50 V/div", "0.5 mA/div" |
| **Static Ec1 reference family** | 6 faint green curves, Ec1 = 0…−5 V step 1 V, computed from the live companion model at **Vg2 = 150 V** (page-3 look; recomputed per frame — 6×48 model evals, trivial — so they track calibration but not the signal) |
| **Live curve** | bright amber, 64 points: `Ip_model(vp; Vg1(t), Vg2(t))` swept vp 0→500 — rises/falls with the grid (page-3 motion) and **compresses down as Vg2 sags** (page-4 motion) |
| **Load line** | white, 2-point segment from (B+, 0) to (0, B+/R_L), clipped to the plot box; redrawn only in the B+/R_L update callbacks — deliberately static during the signal |
| **Operating-point dot** | small emissive sphere at (Vp(t), (B+−Vp)/R_L) — slides along the fixed load line at the moving curve's intersection |
| **Live Vg2 readout** | amber text on the bezel ("Vg2 = 96 V") — the number driving the compression |

Curve updates reuse the scope-trace pattern (`spline.points.foreach_set` + `update_tag`); the family and live curve are POLY curves parented to a display root empty, exactly like `_build_scope()`.

## Controls (per user)

Sliders as before: heater, **B+** (300), **R_L** (100k), **R_g2** (470k), **amplitude** (default 2.0 Vpk), **DC offset** (default −2 V). **Screen bypass capacitor: selectable checkbox, default OFF** (the point of this project; check it to freeze the curves for contrast). **Suppressor: always connected — the toggle, tetrode branch, and panel warning are removed** (`sup=True` hardwired, g3 always visible; secondary-emission machinery stays inert behind it). Glass toggle inherited.

## Verification / acceptance

1. MCP alive check (reload deferred tool schemas); wipe scene (all prior sims saved & pushed), `build_all()`, screenshots: bench with both instruments, tracer close-up showing family + load line + live curve + dot.
2. Physics inherited — rerun the inherited `selfcheck()` (should stay green untouched).
3. New display checks, scripted: (a) op-point dot always on the load line (|y − (B+−x)/R_L| < ε); (b) with bypass ON, live-curve position over a cycle varies only with Vg1 (Vg2 frozen); (c) with bypass OFF at A=2, capture min/max Vg2 over a cycle and screenshot both extremes — the live curve visibly below its Ec1-family reference at max sag; (d) load line vertices unchanged across the cycle, and correct after B+/R_L slider changes.
4. Stills for `shots/`: bench, tracer at max-sag vs min-sag (the compression pair), tracer with bypass ON (curves pinned, page-3 motion only), close-up of dot riding the line.
## Deliverables (full doc set, same pattern as every prior build)

In `amplifier-plate-characteristics/`:
- `plate_curves_sim.py` — standalone idempotent builder
- `plate_curves_sim.blend` — saved scene with the script embedded as a text block
- `README.md` — the two-datasheet-plots explanation (page-3 Ec1 family vs page-4 Ec2 family), why the load line doesn't move while the curves do, controls table, student experiments
- `PROMPT.md` — this request verbatim from the session transcript
- `PLAN.md` — this plan
- `shots/` — the acceptance stills listed above

Commit also includes `docs/6AU6A.pdf` (currently untracked) and the user's modified `pentode_cb_amp_sim.blend` scene state; commit + push at the end per the established review-gate pattern.
