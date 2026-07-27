# Interactive Pentode (6AU6) Simulation in Blender

## Context

Follow-on to the completed & pushed `Blender-Triode-6SN7` project. The user wants the same interactive teaching simulation for a **pentode** — a stylized **6AU6** (miniature 7-pin) — in `/home/holla/Blender-Pentode-6AU6`, which already exists and contains two reference macro photos (`img/6AU6-170424-120244.jpg`: top-down electrode stack with coarse suppressor spiral and flattened plate halves; `img/6AU6-170424-120556.jpg`: grid winding + dimpled plate side view). New repo with remote `git@github.com:holla2040/Blender-Pentode-6AU6.git`.

Core ask: *duplicate all the triode work, add a screen grid with a screen-voltage slider.* User confirmed (via question): full pentode **plus a "Suppressor connected" toggle** that switches to tetrode mode with secondary emission, so students can see the tetrode kink the suppressor exists to fix. Blender 5.1.2 + MCP verified alive (triode scene loaded; it is saved & pushed, safe to wipe).

## What carries over verbatim (proven this session, in `~/Blender-Triode-6SN7/triode_sim.py`)

Start `pentode_sim.py` as a copy of `triode_sim.py` — every load-bearing mechanism is already verified live on this Blender build: numpy `frame_change_pre` engine + 4 substeps, dupli-vert (`instance_type='VERTS'`) emissive electron rendering with `foreach_set`+`update`+`update_tag`, idempotent register/unregister (handler strip by name prefix), `bpy.props` sliders with imperative material updates (no drivers), `_principled/_emission/_light/_cam/_cyl/_poly_curve` helpers, transparent-shadow glass/mica, shadowless cathode point light, passepartout cameras + `view_camera_zoom`, `FRAME_DROP` sync, EEVEE raytracing off, targeted `wipe_scene()` (never factory-reset — kills MCP), meter text object, selfcheck pattern, `__main__` build-or-reregister guard. Rename prefix `TRI_` → `PEN_`, props `tri_*` → `pen_*`, classes `TRIODE_*` → `PENTODE_*`, operators `triode.*` → `pentode.*`.

## What's new

### Geometry (6AU6 style, gaps exaggerated ~3× as before; z ∈ [−1.2, 1.2])

| Part | Spec | Notes |
|---|---|---|
| Cathode + heater | r_c = 0.15, unchanged | same as triode |
| **g1 control grid** | r = 0.33, fine pitch 0.085, wire r 0.010 + 2 rods | finest winding (photo 2) |
| **g2 SCREEN grid** | r = 0.55, pitch 0.14, wire r 0.012 + 2 rods | the new controlled electrode |
| **g3 suppressor** | r = 0.80, coarse pitch 0.34 (~7 turns), wire r 0.014 + 2 rods | matches the open spiral in photo 1 |
| Plate | superellipse sleeve, x-inradius 1.0, **flattened y×0.88**, cutaway window on −Y face | 6AU6 plate is a flattened box (photo 1); absorption via superellipse test, not plain radius |
| Micas | annuli at z = ±1.34 | unchanged |
| Envelope | slimmer straight T-5½ style: r 1.42, dome + **top exhaust nipple** | miniature look |
| Base | **no bakelite**: glass button bottom + 7 pins on r 0.85 circle | 7-pin miniature |

### Physics (4 radial regions instead of 2)

Per substep, radial accel by region (μ2 = 18, μp = 400 → plate nearly screened from cathode — THE pentode property):

- r < g1: `a = C1·(Vg1 + Vg2/μ2 + Vp/μp − V_sc·cloud_frac)` — cutoff via Vg1, extraction set by **screen**, plate almost irrelevant
- g1→g2: `a = C2·(Vg2 − Vg1)` — acceleration to screen
- g2→g3: `a = C3·(0.12·Vp − Vg2)` — retarding region behind the screen; at low Vp electrons stall here and fall back to the screen (soft pentode knee)
- g3→plate: `a = C4·(Vp − 0)` (g3 at cathode potential)

Grid-wire local terms as in triode (soft 1/d² per grid at its own voltage: g1 ∝ −Vg1, g2 ∝ −Vg2 → attraction, g3 ≈ 0), **contact absorption on ALL grid wires** (any wire hit = capture): g2 interception is the **screen current Ig2** — second meter. Emission/space-charge/integration identical to triode; the substep integrator is factored into one function applied to both particle banks (below).

### Secondary emission + tetrode-mode toggle (user-confirmed)

- **Always-on physics**: a primary hitting the plate above an impact-speed threshold spawns (p≈0.55) one **secondary** just inside the plate with a slow inward velocity. Secondaries live in a **second particle bank (~1500, rendered ORANGE)** so the backward stream is visually unmistakable; integrated by the same field code.
- **`Suppressor connected` checkbox (default on)**: ON → fields as above; region g3→plate always pushes secondaries back to the plate — kink suppressed *emergently*, exactly the real mechanism. OFF (**tetrode mode**) → g3 object hidden and regions 3–4 merge into `C34·(Vp − Vg2)`: when Vp < Vg2 that field sweeps secondaries INTO the screen — Ig2 spikes and net Ip sags (the kink). Accounting: primary plate hit → Ip+1; its secondary collected by the screen → Ip−1, Ig2+1; secondary returns to plate → no-op.

Starting constants (tune at checkpoints): `C1=0.5, C2=0.030, C3=0.012, C4=0.055, V_SC=1.5, cap 2000, pool 7000 + 1500 secondaries, wire absorb 0.016, v_max 6, γ=1.5, dt 1/24 ×4 substeps, secondary: v_impact>1.2, yield 0.55, v_emit 0.3`. Defaults = 6AU6 datasheet-ish nominal: **T 1100 K, Vg1 0 V, Vg2 150 V, Vp 250 V**; target Ig2/Ip ≈ 0.3–0.45.

### UI

- **4 sliders**: Heater temp (300–1300 K), Control grid Vg1 (−20…+10 V), **Screen Vg2 (0–200 V)** ← the new control, Plate Vp (0–300 V)
- **`Suppressor connected` checkbox** (tetrode-mode toggle; also hides/shows the g3 object)
- Panel + in-scene meter show **both Ip and Ig2** (one two-line text object); panel also shows cloud count and g1 interception
- Buttons unchanged: Run/Pause, Reset, Top / Inside / Overview, glass toggle
- Inside camera moves to the g3–plate gap (r ≈ 0.9): view through suppressor → screen → g1 → glowing cathode, four concentric layers

## Acceptance scenarios (each: set → step 36–60 frames → screenshot + counters)

| # | Settings | Expected |
|---|---|---|
| 1 | T=500, Vg2=150, Vp=250 | Nothing (cold cathode) |
| 2 | T=1100, **Vg2=0**, Vp=300 | ≈ no current — **the screen does the pulling, not the plate** |
| 3 | Nominal 150/250 | Strong Ip, Ig2 ≈ 0.3–0.45·Ip, sparkle on screen wires |
| 4 | **Vp 250 → 80 at Vg2=150** | Ip nearly unchanged — **pentode flatness** (headline demo; triode would sag) |
| 5 | Vp=15 | Knee: Ip drops, **Ig2 jumps** (stalled electrons return to screen) |
| 6 | Vg1=−8, rest nominal | Cutoff, cloud retained |
| 7 | **Suppressor OFF, Vg2=150, Vp=60** | **Tetrode kink**: orange secondaries stream plate→screen, Ip sags vs same point with suppressor ON, Ig2 spikes; re-check the box → stream collapses back to the plate |
| 8 | All three cameras | Framed correctly, layered grids visible inside |

`selfcheck()` asserts: cold-dead, screen-off-dead, cutoff, flatness (|Ip(250)−Ip(80)| small), knee (Ip(15) < ½·Ip(80)), Ig2 > 0 at nominal, and **kink: Ip(tetrode, Vp=60) < 0.7·Ip(pentode, Vp=60)**.

## Implementation sequence (same chunked MCP pattern as triode)

1. Copy `triode_sim.py` → `~/Blender-Pentode-6AU6/pentode_sim.py`; apply renames + geometry/physics/UI deltas locally. MCP: import, `wipe_scene()`, `build_geometry()` → scene-info + overview screenshot (4 concentric electrodes, flattened cutaway plate, 7-pin button base, nipple).
2. `build_materials()` + `register_ui()` → glow check, 4 sliders present, camera framings ×3.
3. `register_sim()` → 48-frame step: counters plausible, screenshots differ, Ig2 accumulating.
4. Scenario sweep 1–7 with per-point tuning (C2/C3/C4, μ2, absorb radius, secondary yield to hit Ig2/Ip ratio, flatness, and a convincing kink), live mid-run slider change, `selfcheck()`.
5. Deliverables: save `pentode_sim.blend` (embed script text), render `shots/` stills of scenarios (incl. the Ip-flatness pair and the tetrode-kink pair), README.md (embed BOTH img photos, controls incl. screen slider + suppressor toggle, the demos), PROMPT.md (this request verbatim from session JSONL), PLAN.md (this plan), `.gitignore` (same 3 lines).
6. Repo: `git init` + `git remote add origin git@github.com:holla2040/Blender-Pentode-6AU6.git`. **No commit/push until explicitly requested.**

## Verification

Every chunk gates on viewport screenshots + printed counters as in the triode build; final `selfcheck()` must pass; playback + live-slider test once at the end (procedure already proven on this Blender instance).
