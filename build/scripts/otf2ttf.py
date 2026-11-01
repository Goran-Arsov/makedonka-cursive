#!/usr/bin/env python3
"""Convert a CFF/OTF to TrueType (glyf) outlines. argv: in.otf out.ttf [max_err]"""
import sys
from array import array
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

def drop_speck_contours(glyph, min_area=8.0, max_span=3.0):
    """Drop the near-zero-area sliver contours the disk-brush / faux-bold union
    leaves behind: sub-unit 'there-and-back' specks that the cu2qu conversion
    then integer-rounds into segments with coincident endpoints. They add no fill
    at any rendering size, so removing whole specks is shape-preserving — it just
    clears FontBakery's `overlapping_path_segments` (a TTF-only check) on the
    affected glyphs. Only contours that are BOTH tiny in area AND tiny in extent
    are dropped, so real counters/dots (orders of magnitude larger) are never
    touched. (The CFF/OTF is simplify()-ed at build time and the check skips it.)"""
    if glyph.numberOfContours <= 0:          # empty or composite
        return 0
    co, fl, en = glyph.coordinates, glyph.flags, glyph.endPtsOfContours
    contours, s = [], 0
    for e in en:
        contours.append([(co[i][0], co[i][1], fl[i]) for i in range(s, e + 1)]); s = e + 1
    def area(c):
        a = 0.0; n = len(c)
        for i in range(n):
            a += c[i][0] * c[(i + 1) % n][1] - c[(i + 1) % n][0] * c[i][1]
        return abs(a) / 2.0
    def span(c):
        xs = [p[0] for p in c]; ys = [p[1] for p in c]
        return max(max(xs) - min(xs), max(ys) - min(ys))
    keep = [c for c in contours if not (area(c) < min_area and span(c) < max_span)]
    if len(keep) == len(contours):
        return 0
    nc, nf, ne = [], [], []
    for c in keep:
        for (x, y, f0) in c:
            nc.append((x, y)); nf.append(f0)
        ne.append(len(nc) - 1)
    glyph.coordinates = GlyphCoordinates(nc); glyph.flags = array("B", nf)
    glyph.endPtsOfContours = ne; glyph.numberOfContours = len(keep)
    return len(contours) - len(keep)

SRC, DST = sys.argv[1], sys.argv[2]
MAX_ERR = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
f = TTFont(SRC)
assert f.sfntVersion == "OTTO", "input is not CFF/OTF"
order = f.getGlyphOrder(); gs = f.getGlyphSet()
glyf = newTable("glyf"); glyf.glyphOrder = order; glyf.glyphs = {}
for name in order:
    pen = TTGlyphPen(gs)
    gs[name].draw(Cu2QuPen(pen, MAX_ERR, reverse_direction=True))
    glyf.glyphs[name] = pen.glyph()
f["loca"] = newTable("loca")
f["glyf"] = glyf
del f["CFF "]
if "VORG" in f: del f["VORG"]
_specks = sum(drop_speck_contours(glyf.glyphs[name]) for name in order)
if _specks: print(f"dropped {_specks} degenerate speck contours")
glyf.compile(f)                                   # populates per-glyph bounds
for name in order: glyf.glyphs[name].recalcBounds(glyf)
maxp = newTable("maxp"); maxp.tableVersion = 0x00010000
for a in ("maxZones","maxTwilightPoints","maxStorage","maxFunctionDefs","maxInstructionDefs",
          "maxStackElements","maxSizeOfInstructions","maxComponentElements","maxComponentDepth"):
    setattr(maxp, a, 0)
maxp.maxZones = 1
f["maxp"] = maxp
f["post"].formatType = 3.0
f["head"].indexToLocFormat = 0
if "glyf" in f: f["head"].glyphDataFormat = 0
f.sfntVersion = "\x00\x01\x00\x00"
f.save(DST); print("saved", DST)

# ---- TrueType grid-fitting hints via ttfautohint (best-effort) ----
try:
    from ttfautohint import ttfautohint
    _hinted = ttfautohint(in_file=DST)
    with open(DST, "wb") as _fh:
        _fh.write(_hinted)
    _t = TTFont(DST); _t["head"].flags |= (1 << 3); _t.save(DST)   # hinted: force ppem to integer values
    print("ttfautohinted", DST)
except Exception as _e:
    print(f"WARN: ttfautohint skipped ({_e}) — shipping unhinted TTF")
