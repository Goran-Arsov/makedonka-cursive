#!/usr/bin/env python3
"""Convert a CFF/OTF to TrueType (glyf) outlines. argv: in.otf out.ttf [max_err]"""
import sys, os
from array import array
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.areaPen import AreaPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
import pathops
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from outline_util import purge_slivers

CLOSE_R = 0.8   # morphological closing radius (units) applied to every outline before the TrueType conversion
def _stroke(p, w):
    s = pathops.Path(); p.draw(s.getPen())
    s.stroke(w, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4.0); s.convertConicsToQuads(); return s
def close_outline(glyphset, name, r=CLOSE_R):
    """Heal the sub-unit pinch points where the disk-brush / embolden unions touch themselves: a morphological
    CLOSING (dilate by r, erode by r — fill ∪ round stroke, then minus the stroke of that). Those pinches are what
    cu2qu's integer rounding turns into coincident segments (FontBakery `overlapping_path_segments`, TTF-only).
    Guarded: if pathops fails or the result moves the bbox > 2u or changes the area > 3% (it does on three
    traced letters — Ж н Ц), the original outline is kept. Returns a pathops.Path or None (= use the original)."""
    p = pathops.Path(); glyphset[name].draw(p.getPen())
    if not p.bounds: return None
    try:
        d = pathops.Path(); p.draw(d.getPen()); _stroke(p, 2 * r).draw(d.getPen()); d.simplify()
        e = pathops.Path(); pathops.difference([d], [_stroke(d, 2 * r)], e.getPen()); e.simplify()
        e = purge_slivers(e)
    except pathops.PathOpsError:
        return None
    b0 = BoundsPen(glyphset); p.draw(b0); b1 = BoundsPen(glyphset); e.draw(b1)
    if not b1.bounds or max(abs(x - y) for x, y in zip(b0.bounds, b1.bounds)) > 2.0: return None
    a0 = AreaPen(glyphset); p.draw(a0); a1 = AreaPen(glyphset); e.draw(a1)
    if abs(abs(a1.value) / max(1.0, abs(a0.value)) - 1.0) > 0.03: return None
    return e

def dedupe_points(glyph):
    """Drop points that integer-rounding made coincide with their neighbour (an off-curve on top of an on-curve,
    or two equal on-curves in a row) — the zero-length segments FontBakery also reports as overlapping."""
    if glyph.numberOfContours <= 0: return 0
    co, fl, en = glyph.coordinates, glyph.flags, glyph.endPtsOfContours
    contours, s = [], 0
    for e in en:
        contours.append([(co[i][0], co[i][1], fl[i] & 1) for i in range(s, e + 1)]); s = e + 1
    out, dropped = [], 0
    for c in contours:
        keep = []
        for pt in c:
            prev = keep[-1] if keep else c[-1]
            if keep and (pt[0], pt[1]) == (prev[0], prev[1]):
                if pt[2] and not prev[2]: keep[-1] = pt          # on-curve wins over a coincident off-curve
                dropped += 1; continue
            keep.append(pt)
        while len(keep) > 1 and (keep[0][0], keep[0][1]) == (keep[-1][0], keep[-1][1]):
            keep.pop(); dropped += 1
        if len(keep) >= 3: out.append(keep)
    if not dropped: return 0
    nc, nf, ne = [], [], []
    for c in out:
        for (x, y, on) in c: nc.append((x, y)); nf.append(on)
        ne.append(len(nc) - 1)
    glyph.coordinates = GlyphCoordinates(nc); glyph.flags = array("B", nf)
    glyph.endPtsOfContours = ne; glyph.numberOfContours = len(out)
    return dropped

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
_closed = 0
for name in order:
    pen = TTGlyphPen(gs)
    src = close_outline(gs, name)
    if src is not None: _closed += 1
    (src if src is not None else gs[name]).draw(Cu2QuPen(pen, MAX_ERR, reverse_direction=True))
    glyf.glyphs[name] = pen.glyph()
print(f"closed {_closed} outlines (r={CLOSE_R}u)")
f["loca"] = newTable("loca")
f["glyf"] = glyf
del f["CFF "]
if "VORG" in f: del f["VORG"]
_specks = sum(drop_speck_contours(glyf.glyphs[name]) for name in order)
if _specks: print(f"dropped {_specks} degenerate speck contours")
_dups = sum(dedupe_points(glyf.glyphs[name]) for name in order)
if _dups: print(f"dropped {_dups} coincident points")
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
