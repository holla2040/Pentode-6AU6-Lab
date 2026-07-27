# Blender build — superseded

These are the original Blender simulations. **The project is now the browser
build in [`../web/`](../web/README.md)**; this directory is kept for reference,
not for use.

Nothing here is maintained. Fixes go into `../web/engine.js`.

## Why it is still here

`../web/pyref.py` runs these four scripts, unmodified, as the **physics golden
reference** for the port:

```
python3 -B web/pyref.py        # runs the code in this directory
node web/selfcheck.js          # runs the port
```

It stubs `bpy`/`bmesh`/`mathutils`, so no Blender install is needed — the four
`selfcheck()` suites run under plain CPython in about 90 seconds. That is what
makes the browser engine checkable against the original rather than only
against itself, and it is the reason these files were archived instead of
deleted. Measured agreement is in [`../web/README.md`](../web/README.md):
within 0.4 % on plate current, screen current and space-charge population.

If you ever change the physics in `web/engine.js`, run both and compare.

## What is here

| Path | |
|---|---|
| `pentode_sim.py` / `.blend` | the bare tube |
| `amplifier/` | RC stage, two solved load lines |
| `amplifier-cathode-bias/` | self-bias, three coupled loops |
| `amplifier-plate-characteristics/` | the live curve tracer |
| `PLAN.md`, `PROMPT.md` | the original plan and request, verbatim |

## Running them in Blender

Still works, if you want to compare by eye:

```
blender -P blender-legacy/pentode_sim.py
```

Or open a `.blend`, then Text Editor → **Run Script** once (the electron engine
is a Python frame handler, which Blender does not persist), then **N** →
the sim's tab → **Run / Pause**.

Known quirks, left as they were: the sim is stateful so scrubbing the timeline
does not rewind it (use **Reset**); a fresh build takes about a minute to
settle; and one tube project per Blender session.
