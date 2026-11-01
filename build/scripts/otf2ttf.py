#!/usr/bin/env python3
"""Convert a CFF/OTF to TrueType (glyf) outlines. argv: in.otf out.ttf [max_err]"""
import sys
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

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
