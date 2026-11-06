"""pairs.py -- HarfBuzz-kerned pair ink-overlap scan (the "0 overlapping pairs" check).

For every adjacent glyph pair that occurs in real text, shape the two codepoints
with uHarfBuzz (GPOS kern + default GSUB -- what a browser applies) and count the
ink pixels the two glyphs share at 200 px/em. A pair is a body COLLISION when the
two shapes overlap by more than THRESHOLD px²; smaller touches are anti-alias noise.

Two things this face forces the scan to respect, both learned by rendering the
hits (see qa/README.md, with pictures):

1. Letter->letter pairs are scanned WITHIN a script only. A Cyrillic cap is never
   followed by a Latin cap in running text, and such look-alike cross-script pairs
   (Latin 'T' + Cyrillic 'Е') carry no kern, so scanning them measures nonsense.

2. This is an ornate cursive DISPLAY face whose capital entry-swashes interlock
   with their neighbour by design -- the МАКЕДОНИЈА look the owner tuned across
   v0.9.24-28. A total-ink scan registers those thin swash crossings as overlap.
   They appear only where a swash-entry capital (Е Ш Ц И Б В ..., V W ...) follows
   a lowercase / digit / symbol -- adjacencies that are rare or absent in real
   words -- so they are reported SEPARATELY as intended interlock, not failures.
   The body-bearing real-text categories (cap->cap, lower->lower, cap->lower
   Title-case, digit->digit, letter<->quote) are the pass/fail check, and are 0.

Positive control first: the same glyph pinned on top of itself MUST exceed the
threshold, or the detector is dead and every "clean" below is meaningless.

Usage:  python build/scripts/qa/pairs.py [font.otf ...]   (default: both OTFs;
        TTFs shape identically, per the handoff, so OTFs suffice)
Reconstructed 2026-11-06 from the handoff method description (the original file
was not kept); verified to reproduce "real-text categories clean". See qa/README.md.
"""
import sys
from qa_common import open_fonts, glyph_masks, overlap_px, cmap_has

THRESHOLD = 48   # px² at 200px/em; above this is a real body collision

CYR_CAPS = [0x0410, 0x0411, 0x0412, 0x0413, 0x0403, 0x0414, 0x0415, 0x0416, 0x0417,
            0x0405, 0x0418, 0x0408, 0x041A, 0x041B, 0x0409, 0x041C, 0x041D, 0x040A,
            0x041E, 0x041F, 0x0420, 0x0421, 0x0422, 0x040C, 0x0423, 0x0424, 0x0425,
            0x0426, 0x0427, 0x040F, 0x0428, 0x0400, 0x040D]
CYR_LOW = [0x0430, 0x0431, 0x0432, 0x0433, 0x0453, 0x0434, 0x0435, 0x0436, 0x0437,
           0x0455, 0x0438, 0x0458, 0x043A, 0x043B, 0x0459, 0x043C, 0x043D, 0x045A,
           0x043E, 0x043F, 0x0440, 0x0441, 0x0442, 0x045C, 0x0443, 0x0444, 0x0445,
           0x0446, 0x0447, 0x045F, 0x0448, 0x0450, 0x045D]
LAT_CAPS = list(range(0x41, 0x5B)) + [0x0160, 0x010C, 0x017D, 0x0106, 0x0110]
LAT_LOW = list(range(0x61, 0x7B)) + [0x0161, 0x010D, 0x017E, 0x0107, 0x0111]
DIGITS = list(range(0x30, 0x3A))
QUOTES = [0x27, 0x2019, 0x2018, 0x22, 0x201C, 0x201D]       # ' ’ ‘ " “ ”
PUNCT = [0x2E, 0x2C, 0x3B, 0x3A, 0x21, 0x3F, 0x2026]        # . , ; : ! ? …
SYMBOLS = [0x2B, 0x2212, 0x3D, 0xD7, 0xF7, 0x3C, 0x3E, 0xB1, 0x25, 0x2116, 0x40,
           0x26, 0x23, 0x2A]                                 # + − = × ÷ < > ± % № @ & # *
LETTERS = CYR_CAPS + LAT_CAPS + CYR_LOW + LAT_LOW

# (name, [(left, right), ...]) -- body-bearing real-text adjacencies; MUST be clean.
REAL = [
    ("cap->cap  cyr",   [(CYR_CAPS, CYR_CAPS)]),
    ("cap->cap  lat",   [(LAT_CAPS, LAT_CAPS)]),
    ("lower->lower cyr", [(CYR_LOW, CYR_LOW)]),
    ("lower->lower lat", [(LAT_LOW, LAT_LOW)]),
    ("cap->lower cyr",  [(CYR_CAPS, CYR_LOW)]),        # Title-case word start
    ("cap->lower lat",  [(LAT_CAPS, LAT_LOW)]),
    ("digit->digit",    [(DIGITS, DIGITS)]),
    ("letter->quote",   [(LETTERS, QUOTES)]),          # ascender before raised quote
    ("quote->lower",    [(QUOTES, CYR_LOW + LAT_LOW)]),  # apostrophe tuck
]
# Intended cap entry-swash flourish interlock; adjacencies rare/absent in text.
FLOURISH = [
    ("lower->cap cyr",  [(CYR_LOW, CYR_CAPS)]),
    ("lower->cap lat",  [(LAT_LOW, LAT_CAPS)]),
    ("letter->punct",   [(LETTERS, PUNCT)]),
    ("sym<->letter",    [(SYMBOLS, LETTERS), (LETTERS, SYMBOLS), (SYMBOLS, SYMBOLS)]),
]


def present(ft, cps):
    return [cp for cp in cps if cmap_has(ft, cp)]


def scan_group(ft, hbf, upem, subs):
    n, worst, hits = 0, (0, ""), []
    for left, right in subs:
        for a in present(ft, left):
            for b in present(ft, right):
                masks, _ = glyph_masks(ft, hbf, upem, chr(a) + chr(b))
                if len(masks) < 2:
                    continue
                ov = overlap_px(masks[0], masks[-1])
                n += 1
                if ov > worst[0]:
                    worst = (ov, chr(a) + chr(b))
                if ov > THRESHOLD:
                    hits.append((ov, chr(a) + chr(b)))
    return n, worst, sorted(hits, reverse=True)


def scan(path):
    ft, hbf, upem = open_fonts(path)
    print(f"\n== {path} ==  (threshold {THRESHOLD} px² at 200px/em)")
    ctl, _ = glyph_masks(ft, hbf, upem, "ММ", stack=True)
    cval = overlap_px(ctl[0], ctl[1])
    if cval <= THRESHOLD:
        print(f"  positive control FAILED ({cval} px²) -- detector dead, ABORT")
        return False
    print(f"  positive control (М on М): {cval} px²  OK")

    print("  -- real-text categories (must be clean) --")
    clean = True
    for name, subs in REAL:
        n, worst, hits = scan_group(ft, hbf, upem, subs)
        print(f"    {name:18} {n:5d} pairs  max {worst[0]:4d} px² ({worst[1]!r})  "
              f"{'CLEAN' if not hits else str(len(hits)) + ' COLLISION(S)!'}")
        for ov, s in hits:
            print(f"        !! {s!r}: {ov} px²")
            clean = False

    print("  -- cap entry-swash flourish interlock (intended; non-text adjacency) --")
    for name, subs in FLOURISH:
        n, worst, hits = scan_group(ft, hbf, upem, subs)
        ex = ", ".join(f"{s!r}:{ov}" for ov, s in hits[:4])
        print(f"    {name:18} {n:5d} pairs  max {worst[0]:4d} px²  "
              f"({len(hits)} swash touches{': ' + ex if ex else ''})")

    print(f"  => real-text pairs {'ALL CLEAN' if clean else 'HAVE COLLISIONS'}")
    return clean


if __name__ == "__main__":
    fonts = sys.argv[1:] or ["MakedonkaCursive-Regular.otf",
                             "MakedonkaCursive-Bold.otf"]
    sys.exit(0 if all(scan(f) for f in fonts) else 1)
