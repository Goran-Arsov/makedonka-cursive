# QA scans — Makedonka Cursive

Reproducible checks behind the numbers quoted in `followups.md` and
`macedonian-cursive-font-handoff.md` ("0 overlapping pairs", the measured slants,
the apostrophe tuck being collision-free).

**Provenance.** The original QA scripts lived in a Claude session scratchpad and
were not kept (followups Open #9). These are **faithful reconstructions**, written
2026-11-06 from the method descriptions in the handoff, and each is **validated to
reproduce the handoff's published numbers** via a built-in positive control or
calibration anchor (detailed below). They are not byte-for-byte the originals.

Run with the project venv, from the repo root:

```
.venv/bin/python build/scripts/qa/slant3.py        # slant per glyph group
.venv/bin/python build/scripts/qa/pairs.py         # pair ink-overlap scan
.venv/bin/python build/scripts/qa/triples.py       # letter+apostrophe+letter
.venv/bin/python build/scripts/qa/show.py "word1" "word2"   # proof sheet
```

Each scan defaults to both OTFs (TTFs shape identically, per the handoff) and
exits non-zero if the real-text check fails. These scans add two QA-only deps on
top of the main build — install `build/scripts/qa/requirements.txt` (`uharfbuzz`,
`freetype-py`; `pillow` built with RAQM and `numpy` already come from
`build/requirements.txt`).

## Method (shared: `qa_common.py`)

Shape each test string with **uHarfBuzz** (GPOS `kern` + default GSUB — exactly
what a browser applies, including this font's `.lc` apostrophe `calt` rules), then
rasterise **each glyph id in isolation** with **FreeType** at 200 px/em and place
it at its shaped position on a common canvas. Overlap is the count of ink pixels
two glyphs share (an "N px²" in the docs == N overlapping pixels at this size).
Per-glyph isolation is why PIL's whole-string render won't do — it can't separate
two glyphs' ink to measure their overlap. Glyph bitmaps are cached (294 glyphs),
so a full pair scan runs in under a second.

Every scan runs a **positive control** first (a pair pinned on top of itself must
exceed the threshold); a scan that can only ever report "clean" is worthless.

## Scripts

### `slant3.py` — projection-profile italic angle
For each un-shear angle, de-shear the ink and score the column histogram's
sharpness (`sum(colsum²)`); the glyph's slant is the angle that maximises it.
**Calibration anchor:** the straight glyphs `| [ ] #`, drawn at a known 10°
(`T_DEG`), read **10.0°** — printed first as the sanity check. Reproduces the
handoff's stem-bearing medians to ±1° (cyr lower **14.2°** exact, Latin ~10°).
Round/flourished groups (ornate caps, round digits) read +2–3° steeper here and
are soft — judge slant from the stem-bearing groups + the anchor, as the handoff
does. Stemless curves (`s ѕ S С о е`) are unmeasurable and excluded.

### `pairs.py` — HarfBuzz-kerned pair ink-overlap scan
The "0 overlapping pairs" check. Two things this ornate **display** face forces:

1. **Letter↔letter pairs are within-script only.** A Cyrillic cap never precedes
   a Latin cap in text, and such look-alike cross-script pairs (Latin `T` +
   Cyrillic `Е`) carry no kern — scanning them measures nonsense. Digits, quotes,
   punctuation and symbols are script-neutral and stay mixed.
2. **Cap entry-swashes interlock by design** (the МАКЕДОНИЈА look tuned across
   v0.9.24–28). A total-ink scan registers those thin swash crossings as overlap.
   They appear only where a swash-entry capital (`Е Ш Ц И Б В … V W …`) *follows* a
   lowercase/digit/symbol — rare or absent in real words — so they are reported
   **separately as intended interlock, not failures** (rendered and confirmed to
   be thin flourish crossings, not body collisions).

**Result (both weights):** every body-bearing real-text category — cap→cap,
lower→lower, cap→lower (Title-case), digit→digit, letter→quote, quote→lower — is
**0 above the 48 px² threshold**. This is the reproducible form of the claim.

### `triples.py` — letter + apostrophe + letter
Checks the apostrophe **tuck** never collides: ~16 384 triples, shaped so the
`.lc` apostrophe and the tuck/floor kerns fire. **Self-validating** via a *no-mark
control* — if first↔third already overlap without the apostrophe, that's a
pre-existing cursive flourish (historically `ј`'s descender), not a tuck fault, so
a triple is flagged only when the mark makes it worse or the mark itself is hit.
**Result:** 0 mark↔letter collisions, 0 tuck-worsened, both weights — reproduces
"16 384-triple apostrophe scan completely clean in both weights".

### `show.py` — comparison / proof sheets
Renders words with real shaping (PIL **RAQM** engine = GPOS + GSUB; the *basic*
engine applies neither) and crops to a sheet with a **10% white margin on every
edge, sized from the real ink** — the owner's standing rule (nothing clipped; a
sheet once cut the underbar under discussion). One font proofs it; `--cmp` stacks
an old-vs-new comparison. Defaults include the standing specimen phrases.

## Not reconstructed (and why)
- **`slant.py` / `slant2.py`** — the *rejected* downstroke-segment and
  row-centroid slant measures (they under-read cursive by 2–8°). Only the
  projection profile (`slant3.py`) is trustworthy; the rejects aren't worth
  carrying as code.
- **`obox.py`** — a pair's crossing extent; subsumed by `pairs.py`'s per-pair
  reporting.
- **`tuck.py`** — slant-wise air under an apostrophe; the tuck fires only in the
  `letter-'-letter` context, which `triples.py` already exercises and proves
  collision-free, so a standalone air measure adds little.
