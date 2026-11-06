"""triples.py -- letter + apostrophe + letter overlap scan (the tuck-collision check).

The apostrophe tuck (kern_util._tuck_pairs) pulls an x-height letter leftward,
UNDER a preceding apostrophe ("it's", "I'mma"), so the font reads tight instead of
holding a full mark-advance of air. That negative kern risks pulling the third
letter into the first, or into the mark. This scans every

    first (any cased letter) + mark (' or ’) + third (any lowercase)

HarfBuzz-shaped (so the .lc apostrophe calt rules and the tuck/floor kerns all
fire), ~16k triples, and flags a collision when the third letter's ink hits the
first letter's or the mark's by more than THRESHOLD px².

Self-validating via a NO-MARK control: the same first+third shaped without the
mark. If first<->third already overlap without the apostrophe, that is a
pre-existing cursive flourish (historically ј's left-sweeping descender), NOT a
tuck collision -- so a triple is only reported when the mark makes the overlap
WORSE than the control, or when the mark itself is hit. A synthetic positive
control (mark stacked on the letter) proves the detector is live.

Usage:  python build/scripts/qa/triples.py [font.otf ...]   (default: both OTFs)
Reconstructed 2026-11-06 from the handoff; reproduces "triple scan clean". See qa/README.md.
"""
import sys
from qa_common import open_fonts, glyph_masks, overlap_px, cmap_has

THRESHOLD = 48
MARKS = [0x27, 0x2019]                                   # ' ’
CYR_LOW = [0x0430, 0x0431, 0x0432, 0x0433, 0x0453, 0x0434, 0x0435, 0x0436, 0x0437,
           0x0455, 0x0438, 0x0458, 0x043A, 0x043B, 0x0459, 0x043C, 0x043D, 0x045A,
           0x043E, 0x043F, 0x0440, 0x0441, 0x0442, 0x045C, 0x0443, 0x0444, 0x0445,
           0x0446, 0x0447, 0x045F, 0x0448, 0x0450, 0x045D]
LAT_LOW = list(range(0x61, 0x7B)) + [0x0161, 0x010D, 0x017E, 0x0107, 0x0111]
CYR_CAP = list(range(0x0410, 0x0430)) + [0x0403, 0x0405, 0x0408, 0x0409, 0x040A,
                                         0x040C, 0x040F, 0x0400, 0x040D]
LAT_CAP = list(range(0x41, 0x5B)) + [0x0160, 0x010C, 0x017D, 0x0106, 0x0110]
LOWERS = CYR_LOW + LAT_LOW
FIRSTS = CYR_CAP + LAT_CAP + LOWERS


def scan(path):
    ft, hbf, upem = open_fonts(path)
    firsts = [c for c in FIRSTS if cmap_has(ft, c)]
    thirds = [c for c in LOWERS if cmap_has(ft, c)]
    marks = [c for c in MARKS if cmap_has(ft, c)]
    print(f"\n== {path} ==  ({len(firsts)}x{len(marks)}x{len(thirds)} = "
          f"{len(firsts) * len(marks) * len(thirds)} triples, threshold {THRESHOLD} px²)")

    # positive control: two tall letters pinned on top of each other must register.
    cm, _ = glyph_masks(ft, hbf, upem, "ll", stack=True)
    cval = overlap_px(cm[0], cm[1])
    if cval <= THRESHOLD:
        print(f"  positive control FAILED ({cval}) -- detector dead, ABORT")
        return False
    print(f"  positive control (l stacked on l): {cval} px²  OK")

    mark_hits, tuck_hits, flourish = [], [], 0
    for a in firsts:
        for m in marks:
            for c in thirds:
                tri, _ = glyph_masks(ft, hbf, upem, chr(a) + chr(m) + chr(c))
                if len(tri) != 3:
                    continue
                ov_mc = overlap_px(tri[1], tri[2])      # mark <-> third
                ov_ft = overlap_px(tri[0], tri[2])      # first <-> third
                if ov_mc > THRESHOLD:
                    mark_hits.append((ov_mc, chr(a) + chr(m) + chr(c)))
                if ov_ft > THRESHOLD:
                    ctl, _ = glyph_masks(ft, hbf, upem, chr(a) + chr(c))  # no mark
                    base = overlap_px(ctl[0], ctl[1]) if len(ctl) == 2 else 0
                    if ov_ft > base + 8:                # the tuck made it worse
                        tuck_hits.append((ov_ft, base, chr(a) + chr(m) + chr(c)))
                    else:
                        flourish += 1                   # pre-existing, mark-independent
    print(f"  mark<->letter collisions : {len(mark_hits)}"
          + ("  " + ", ".join(f"{s!r}:{v}" for v, s in sorted(mark_hits, reverse=True)[:6])
             if mark_hits else ""))
    print(f"  tuck-worsened first<->third: {len(tuck_hits)}"
          + ("  " + ", ".join(f"{s!r}:{v}(ctl {b})"
                              for v, b, s in sorted(tuck_hits, reverse=True)[:6])
             if tuck_hits else ""))
    print(f"  pre-existing flourish overlaps (mark-independent, not a tuck fault): {flourish}")
    clean = not mark_hits and not tuck_hits
    print(f"  => apostrophe triples {'CLEAN' if clean else 'HAVE TUCK COLLISIONS'}")
    return clean


if __name__ == "__main__":
    fonts = sys.argv[1:] or ["MakedonkaCursive-Regular.otf",
                             "MakedonkaCursive-Bold.otf"]
    sys.exit(0 if all(scan(f) for f in fonts) else 1)
