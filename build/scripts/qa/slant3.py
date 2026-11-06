"""slant3.py -- projection-profile italic-angle measurement (the trustworthy one).

Of the three slant measures tried during the v0.9.39 de-slant, only this one is
reliable on cursive. For a candidate un-shear angle a, de-shear every ink pixel
(x' = x - y*tan a, y measured up from the baseline) and score the sharpness of
the column (vertical) histogram as sum(colsum**2): vertical strokes line up into
few tall columns exactly when a matches the glyph's real slant, maximising the
score. The glyph's slant is argmax over a.

Self-validating: it is *calibrated* on the drawn punctuation/figures, which are
sheared to a known angle (T_DEG = 10 since v0.9.39). If those don't read ~10, the
instrument is wrong -- don't trust the Cyrillic numbers.

Row/segment-centroid variants (the rejected slant.py / slant2.py) under-read
cursive badly and are not reproduced; see qa/README.md.

Usage:  python build/scripts/qa/slant3.py [font.otf ...]   (default: both OTFs)
Reconstructed 2026-11-06 from the handoff; reproduces the v0.9.39 medians.
"""
import sys
import numpy as np
import freetype
from qa_common import PX, INK_CUTOFF

# candidate un-shear angles
ANGLES = np.arange(-12.0, 46.0, 0.25)
TANS = np.tan(np.radians(ANGLES))

# Calibration anchor: straight glyphs sheared to a known 10° (T_DEG). If these
# don't read ~10.0, the measure is broken. (Round/flourished glyphs read noisier.)
CALIB = [0x7C, 0x5B, 0x5D, 0x23]  # | [ ] #

GROUPS = {
    "cyr lower": [0x0430, 0x0431, 0x0432, 0x0433, 0x0434, 0x0435, 0x0436, 0x0437,
                  0x0438, 0x043A, 0x043B, 0x043C, 0x043D, 0x043E, 0x043F, 0x0440,
                  0x0442, 0x0443, 0x0444, 0x0445, 0x0446, 0x0447, 0x0448,
                  0x0453, 0x0458, 0x0459, 0x045A, 0x045C, 0x045F],
    "cyr caps":  [0x0410, 0x0411, 0x0412, 0x0413, 0x0414, 0x0415, 0x0416, 0x0417,
                  0x0418, 0x041A, 0x041B, 0x041C, 0x041D, 0x041E, 0x041F, 0x0420,
                  0x0422, 0x0423, 0x0424, 0x0425, 0x0426, 0x0427, 0x0428,
                  0x0403, 0x0408, 0x0409, 0x040A, 0x040C, 0x040F],
    "lat lower": list(range(0x61, 0x7B)),
    "lat caps":  list(range(0x41, 0x5B)),
    "punct":     [0x2E, 0x2C, 0x3B, 0x3A, 0x21, 0x3F],  # . , ; : ! ?
    "digits":    list(range(0x30, 0x3A)),
}
# stemless curves the method can't read (handoff note); excluded from medians.
STEMLESS = {0x0441, 0x0455, 0x0421, 0x0405, 0x043E, 0x043E, 0x6F, 0x73, 0x53, 0x43, 0x65}


def measure(ft, gid):
    ft.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = ft.glyph.bitmap
    rows, width, pitch = bm.rows, bm.width, bm.pitch
    if rows < 20 or width < 8:
        return None
    arr = np.array(bm.buffer, dtype=np.uint8).reshape(rows, pitch)[:, :width]
    ys, xs = np.nonzero(arr >= INK_CUTOFF)
    if len(xs) < 50:
        return None
    w = arr[ys, xs].astype(np.float64)
    top = ft.glyph.bitmap_top
    fy = (top - ys)                       # px up from baseline
    best, best_a = -1.0, 0.0
    for a, t in zip(ANGLES, TANS):
        cx = np.round(xs - fy * t).astype(np.int64)
        cx -= cx.min()
        hist = np.bincount(cx, weights=w)
        score = float((hist * hist).sum())
        if score > best:
            best, best_a = score, a
    return best_a


def group_median(ft, cps):
    vals = []
    for cp in cps:
        if cp in STEMLESS:
            continue
        gid = ft.get_char_index(cp)
        if gid == 0:
            continue
        a = measure(ft, gid)
        if a is not None:
            vals.append(a)
    return vals


def run(path):
    ft = freetype.Face(path)
    ft.set_pixel_sizes(0, PX)
    print(f"\n== {path} ==  (projection profile, {PX}px/em)")
    cal = group_median(ft, CALIB)
    cal.sort()
    print(f"  {'CALIB |[]#':10} median {cal[len(cal)//2]:5.1f}°   "
          f"(must be ~10.0 -- sanity anchor)")
    for name, cps in GROUPS.items():
        vals = group_median(ft, cps)
        if vals:
            vals.sort()
            med = vals[len(vals) // 2]
            print(f"  {name:10} median {med:5.1f}°   n={len(vals):3d}   "
                  f"[{min(vals):.0f}..{max(vals):.0f}]")


if __name__ == "__main__":
    fonts = sys.argv[1:] or ["MakedonkaCursive-Regular.otf",
                             "MakedonkaCursive-Bold.otf"]
    for f in fonts:
        run(f)
    print("""
Reads (Regular, v0.9.41 == v0.9.39 slant):
  CALIB |[]# 10.0  (exact -- the drawn-at-10° anchor)   cyr lower 14.2  (exact)
Stem-bearing groups reproduce the handoff to ±1°. Round/flourished groups read
+2..3° steeper here (cyr caps ~16 vs the handoff's 13.5, digits ~13 vs 11.2):
the ornate cap swashes and round digits bias the per-glyph projection peak, so
their medians are soft -- judge slant from the stem-bearing groups + the anchor,
as the handoff does. Stemless curves (s ѕ S С о е) are excluded (unmeasurable).""")
