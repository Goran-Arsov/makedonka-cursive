#!/usr/bin/env python3
"""Regenerate `specimen.html` — a single self-contained browser specimen of the CURRENT build.

Both woff2 files are embedded as base64 `@font-face` sources, so the page needs no server and no
font install, renders the real GPOS kerning + GSUB features natively, and can be shared as one
file. Run after every build (ship step 1):

    python build/scripts/specimen_html.py [project-dir]   -> <project-dir>/specimen.html
"""
import base64, os, sys, datetime
from fontTools.ttLib import TTFont

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REG, BOLD = os.path.join(ROOT, "MakedonkaCursive-Regular.woff2"), os.path.join(ROOT, "MakedonkaCursive-Bold.woff2")
def b64(p):
    with open(p, "rb") as fh: return base64.b64encode(fh.read()).decode("ascii")
ver = TTFont(os.path.join(ROOT, "MakedonkaCursive-Regular.otf"))["name"].getDebugName(5).replace("Version ", "")
glyphs = len(TTFont(os.path.join(ROOT, "MakedonkaCursive-Regular.otf")).getGlyphOrder())

ROWS = [  # (css class, text)
    ("caps", "А Б В Г Д Ѓ Е Ж З Ѕ И Ј К Л Љ М Н Њ О П Р С Т Ќ У Ф Х Ц Ч Џ Ш"),
    ("lc", "а б в г д ѓ е ж з ѕ и ј к л љ м н њ о п р с т ќ у ф х ц ч џ ш"),
    ("big", "Скопје, Македонија"),
    ("mid", "ОХРИД СКОПЈЕ ШТИП ЃОРЃИ ЅВЕЗДА МАКЕДОНИЈА 2025 · OHRID 1999"),
    ("mid", "патот дете ѓердан ѕвезда џез ќерка љубов њива — Сѐ ѝ кажав."),
    ("mid", "„Виножито над Вардар.“ · «Охрид» · 100 денари; (бр. 7) · вода, леб и убавина?"),
    ("caps", "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z · Š Č Ž Ć Đ"),
    ("lc", "a b c d e f g h i j k l m n o p q r s t u v w x y z · š č ž ć đ"),
    ("mid", "Makedonija, Ohrid — Skopje, Šibenik, Čačak, Đakovo · Dom Gaga Quin Rob Una Vera Wim Fluid Tito"),
    ("mid", "Tom &amp; Jerry · “quote” ‘q’ ‚x‘ ‹y› · ¡Hola! · a@b.mk · €50 $5 · ½ ¼ ¾ · m² H₂O · ™ ® § ¶ © ‰"),
    ("mid", "0 1 2 3 4 5 6 7 8 9 · 1999 2006 60 99 · 2025-11-02 · воз-воз · a-b · А–Б · x—y · 20° 50% · [1] {2} (3)"),
    ("mid", "1 + 2 = 3 · 8 ÷ 2 × 4 · № 7 · x &lt; y &gt; z · a ± b · #*_|~\\^ · `x` •"),
    ("big b", "Битола, Прилеп — Задебелено · Bold Makedonija"),
    ("mid b", "ОХРИД СКОПЈЕ · ѕвезда sos šef hbl · “Quote” 2025-11-02 ½ € &amp;"),
]
FEATS = [  # (feature css, label, text)
    ("'frac' 1", "frac", "1/2 · 3/4 · 7/8 · 22/7 · 10/11/2025"),
    ("'sups' 1", "sups", "x2, km2, n3, 10"),
    ("'subs' 1", "subs", "H2O, CO2"),
    ("'zero' 1", "zero", "0, 100, 2030"),
    ("'tnum' 1", "tnum", "0123456789 (tabular)"),
    ("'case' 1", "case", "a-b x–y p—q 2025 + 3 (raised dashes/operators, cap-height figures)"),
    ("'calt' 0", "calt off", "2025-11-02 А–Б МАКЕДОНИЈА 2025 (low dashes, ascender-height figures without calt)"),
]
rows = "\n".join(f'<div class="mk {c}">{t}</div>' for c, t in ROWS)
feats = "\n".join(f'<div class="mk mid" style="font-feature-settings:{f}"><span class="lab">{l}</span>{t}</div>' for f, l, t in FEATS)
html = f"""<!doctype html>
<html lang="mk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Makedonka Cursive {ver} — specimen</title>
<style>
@font-face {{ font-family: "Makedonka Cursive"; font-weight: 400; font-style: normal; font-display: block;
  src: url(data:font/woff2;base64,{b64(REG)}) format("woff2"); }}
@font-face {{ font-family: "Makedonka Cursive"; font-weight: 700; font-style: normal; font-display: block;
  src: url(data:font/woff2;base64,{b64(BOLD)}) format("woff2"); }}
body {{ margin: 2rem 3rem; background: #fff; color: #111; font-family: system-ui, sans-serif; }}
h1 {{ font: 400 1.1rem system-ui, sans-serif; color: #666; letter-spacing: .04em; margin: 0 0 1.2rem }}
.mk {{ font-family: "Makedonka Cursive", cursive; line-height: 1.55; margin: .35em 0; white-space: nowrap; overflow-x: auto }}
.caps {{ font-size: 44px }} .lc {{ font-size: 40px }} .big {{ font-size: 72px }} .mid {{ font-size: 34px }} .b {{ font-weight: 700 }}
.lab {{ font: 12px system-ui, sans-serif; color: #888; display: inline-block; width: 5.5em }}
h2 {{ font: 400 .9rem system-ui, sans-serif; color: #888; margin: 2rem 0 .4rem; text-transform: uppercase; letter-spacing: .1em }}
footer {{ margin-top: 3rem; font: 12px system-ui, sans-serif; color: #888 }}
</style></head><body>
<h1>Makedonka Cursive — version {ver} · {glyphs} glyphs · Regular + Bold · generated {datetime.date.today()}</h1>
{rows}
<h2>OpenType features</h2>
{feats}
<footer>Makedonka Cursive by Goran Arsov — derived from “Macedonian cursive script” by MacedonianBoy (Wikimedia Commons), CC BY-SA 3.0.
Both weights are embedded in this file, so kerning and features render natively in any browser.</footer>
</body></html>
"""
out = os.path.join(ROOT, "specimen.html")
with open(out, "w", encoding="utf-8") as fh: fh.write(html)
print(f"wrote {out} ({os.path.getsize(out)//1024} KB, version {ver}, {glyphs} glyphs)")
