# Makedonka Cursive — font build (project instructions)

This folder is the **Makedonka Cursive** deliverable + its reproducible build.
A Macedonian cursive display font, vectorized from a CC BY-SA 3.0 chart.

## Read first (these are NOT auto-loaded — read them before working on the font)
- **`followups.md`** — what's left to do, with priorities and the verified current state.
- **`macedonian-cursive-font-handoff.md`** — full build internals: the path→glyph MAP,
  every design knob (`BASEFRAC`, `SCALE_OVERRIDE`, `EMBOLDEN`, `LEFT_CAP`, `CONN_LO/HI`,
  `M_BODY`, the disk-brush digit stroker), the history, and the rebuild steps.

## What's here
- Shipped font (**v0.9**): `MakedonkaCursive-Regular.{otf,woff2,woff}`.
- Web: `makedonka-cursive.css` (`@font-face`), `demo.html`. Specimen: `specimen.png`.
- Reproducible build: `build/` — source SVG, `paths.json`, `scripts/` (canonical
  `build/scripts/build_font.py`), `requirements.txt`. Rebuild steps are in the handoff.

## Where the font also lives (keep in sync if the font changes)
- LibreOffice/desktop: `~/.local/share/fonts/MakedonkaCursive-Regular.otf` (then `fc-cache -f`).
- amici project: `/home/goran/IT/Rails/MyApps/amici/public/fonts/` + `@font-face` in its
  Tailwind CSS (cache-buster `?v=N`); used on the home page. Bump `?v=` on updates.

## License
CC BY-SA 3.0, derived from "Macedonian cursive script" by MacedonianBoy (Wikimedia Commons).
Keep the attribution when distributing; a site serving the font owes a **visible** credit.
