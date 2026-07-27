# Plan: Pentode Cathode-Bias Amplifier (the capstone)

Answering "does a pentode version have value?" — yes: with R_k added to the
[screen-resistor stage](../amplifier/PLAN.md), this is the **complete,
schematic-authentic 6AU6 RC stage**: THREE coupled self-regulating loops
(cathode bias, screen sag, plate load) and no bias supplies anywhere. The
new lesson is the coupling itself — the loops interact (adding R_k *raises*
the screen voltage, because the cathode lift throttles screen current) and
the stage still finds one stable operating point. Two independent bypass
checkboxes separate series (cathode) from shunt-ish (screen) feedback.

Module `pentode_cb_amp_sim.py`, prefix `PCBA_`, handler
`amp_pcb_frame_change` (amp_-prefixed for the cross-project strip-list
convention). Base: copy of `../amplifier/pentode_amp_sim.py`.

## Circuit & solve

- `Vk = (Ip + Ig2)·R_k` — the **cathode current is plate + screen**, a
  pentode subtlety the meter verifies (`Vk = (Ip+Ig2)·R_k` to <0.1 V).
- Tube-referenced: `Vg1 = Vgen − Vk`, `Vg2 = (B+ − Ig2·R_g2) − Vk`,
  `Vp = (B+ − Ip·R_L) − Vk`.
- Triple nested bisection per frame (outer Vk 16 × screen 18 × plate 18 —
  ~5.7 ms/frame measured, fine). All algebraic; the DC operating point is
  always solved first, anchoring the K̂/S_FRAC calibration (Jensen lesson)
  and freezing whichever nodes are bypassed.

## Verified (selfcheck green)

Cold → all rails at B+ · triple self-bias at dc=0: Vk=1.13 V, Vg2=130 V,
Vp=223 V, all three KVLs (plate <30 V, screen <40 V, cathode <0.8 V) ·
inverting · gain ladder 15.7× all-bypassed / 13.7× Rk-unbypassed / 9.5×
screen-unbypassed / 41.7× at R_L=300k (still scales — pentode signature) ·
corr −0.97 · overdrive asymmetry: top RAILS at B+ (frozen screen puts
cutoff at only ≈−8 V) while the bottom soft-limits near 160 V (the knee
factor caps plate current) · stable at R_L=500k / R_g2=1M / R_k=5k.
