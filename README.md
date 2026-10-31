# Makedonka Cursive

A Macedonian cursive **display** font — all 31 Macedonian letters (upper + lowercase),
a full **Latin** alphabet, digits 0–9, and punctuation — in two weights, **Regular** and
**Bold**. The Macedonian letters are
vectorized from the Wikimedia chart *"Macedonian cursive script"* and spaced to **join at
the x-height**, so words read as a connected whole and lowercase tucks under a leading
capital's flourish. (True contextual joining — a v2 — is future work.)

**Version 0.9.13.**

![specimen](specimen.png)

## Files

Each weight (**Regular**, **Bold**) ships in four formats:

| Format  | Use |
|---------|-----|
| `.otf`  | Desktop install (Word, LibreOffice, Photoshop…) and editing in FontForge/Glyphs |
| `.ttf`  | Desktop install — maximum compatibility (older apps, some embedded/Android) |
| `.woff2`| **Web** (primary — smallest, all modern browsers) |
| `.woff` | Web fallback (older browsers) |

Plus `makedonka-cursive.css` (ready `@font-face` rules for both weights), `demo.html`
(open in a browser), and `specimen.png`.

## Install on your computer (Word, LibreOffice, any app)

- **Windows:** select `MakedonkaCursive-Regular.otf` and `MakedonkaCursive-Bold.otf`,
  right-click → **Install** (or open each and click *Install*). Then pick
  **"Makedonka Cursive"** in Word / LibreOffice; the **Bold** button (Ctrl/⌘+B) gives the
  Bold weight.
- **macOS:** double-click each `.otf` → **Install Font** (Font Book).
- **Linux:** copy the `.otf` (or `.ttf`) files to `~/.local/share/fonts/`, then `fc-cache -f`.

Use the `.otf` by default; use the `.ttf` only if an app won't accept the `.otf`.

It's an ornate **copperplate display** face — use it **large** (headings, logos, titles,
hero text), not for body copy or small sizes. It covers **Macedonian Cyrillic only** —
Latin letters fall back to another font.

## Use it on the web

Copy the `.woff2` + `.woff` (both weights) next to your CSS and import
`makedonka-cursive.css`, or inline:

```css
@font-face {
  font-family: "Makedonka Cursive";
  src: url("MakedonkaCursive-Regular.woff2") format("woff2"),
       url("MakedonkaCursive-Regular.woff") format("woff");
  font-weight: 400; font-style: normal; font-display: swap;
}
@font-face {
  font-family: "Makedonka Cursive";
  src: url("MakedonkaCursive-Bold.woff2") format("woff2"),
       url("MakedonkaCursive-Bold.woff") format("woff");
  font-weight: 700; font-style: normal; font-display: swap;
}

h1        { font-family: "Makedonka Cursive", cursive; }
h1.strong { font-weight: 700; }
```

(Rails: drop the web files in `public/fonts/` and reference `/fonts/…`, or put them in
`app/assets/fonts/` for the asset pipeline.)

## Coverage
- **Letters:** all 31 Macedonian letters, upper + lowercase (62 glyphs), with the correct
  Macedonian/Serbian-style cursive forms (overbarred г/п/т, g-shaped д, dotted ј, …).
- **Weights:** Regular + Bold (the Bold is a dilation of the Regular — a faux-bold).
- **Digits:** 0–9, designed to match (calligraphic pen numerals; not in the source chart).
- **Punctuation:** space `. , : ; ! ? - – — ( ) ' " „ "` — calligraphic pen marks, including
  the Macedonian `„ "` quotes (designed to match; not in the source chart).
- **Latin:** full A–Z / a–z, a calmer companion to the ornate Macedonian hand — one
  consistent, moderately upright slant across all letters, figures and punctuation, in a
  **restrained** pen style. Every Latin glyph is either drawn or a re-angled copy of a
  Cyrillic letter (the Macedonian glyphs themselves are unchanged). Good for names,
  wordmarks and short Latin text — not a full-flourish Latin script.
- **Not included:** other-Cyrillic (Russian/Serbian-specific letters).

## Known limitations
- **Consecutive capitals overlap** — built for normal words (one leading capital +
  lowercase); avoid setting all-caps cursive.
- **Not pair-kerned;** true contextual joining (v2) is future work.
- **Bold is a faux-bold** (uniform dilation), so its stroke contrast is lower than the
  Regular's.
- Display face only; not hinted for small sizes.

## License & attribution — **required**

This font is a **derivative work** of
[*"Macedonian cursive script"* by **MacedonianBoy**](https://commons.wikimedia.org/wiki/File:Macedonian_cursive_script.svg)
(Wikimedia Commons), licensed **Creative Commons Attribution-ShareAlike 3.0 Unported
(CC BY-SA 3.0)**. Therefore:

- You **must keep attribution** to MacedonianBoy and the CC BY-SA 3.0 license wherever you
  distribute or ship the font (a credits/colophon page, a CSS comment, or an "about" note is
  fine). The attribution is also embedded in the font's metadata.
- You **must license the font (and modified versions) under CC BY-SA 3.0** — it cannot be
  made proprietary or sold under closed terms. Others may reuse and modify it under the same
  license (including commercially).

See `LICENSE`. Full license text: https://creativecommons.org/licenses/by-sa/3.0/

*(This is a practical summary of the license terms, not legal advice.)*
