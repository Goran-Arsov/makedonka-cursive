#!/usr/bin/env python3
"""Build MakedonkaCursive-Bold from the Regular OTF (same source suite).

The letters are traced outlines, so a redrawn heavier weight isn't available;
this is a faux-bold — every glyph is dilated by an 8-direction union (grows the
shape by D on all sides), the advance grows by 2D and the glyph shifts +D so the
left sidebearing is preserved. Rebuilt via FontBuilder so the CFF/widths are
clean, and tagged as the Bold member of the "Makedonka Cursive" family.

  argv[1]=Regular.otf   argv[2]=OUTDIR   argv[3]=D (dilation, default 13)
"""
import sys, os, math
from fontTools.ttLib import TTFont, newTable
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
import pathops
from outline_util import purge_slivers

REG, OUTDIR = sys.argv[1], sys.argv[2]
D = float(sys.argv[3]) if len(sys.argv) > 3 else 16.0    # horizontal bold amount (the thick-stem axis)
TAN = math.tan(math.radians(18))                         # the font's italic angle
DY = max(4.0, round(D * 0.44))                           # vertical growth < horizontal, so weight lands on the thick
                                                         # near-vertical stems, not the thin horizontals (т/г/п overbars,
                                                         # ш underline, connectors) — this keeps the Regular's contrast
VER = "0.937"
f = TTFont(REG); gs = f.getGlyphSet(); order = f.getGlyphOrder()
cmap = f.getBestCmap(); hmtx = f["hmtx"]; UPM = f["head"].unitsPerEm

def embolden(path, dx, dy):
    # Contrast-preserving faux-bold: un-slant so the thick strokes stand ~vertical, dilate MORE
    # horizontally (dx) than vertically (dy) so the weight lands on those stems while the thin
    # horizontal hairlines barely grow, then re-slant. (A plain isotropic dilation fattens thick
    # and thin equally and flattens the Regular's contrast.)
    # v0.9.35: a TRUE dilation — the fill unioned with a round-pen STROKE of the outline (width 2·dx) in a
    # space stretched vertically by dx/dy, i.e. a Minkowski sum with a dx×dy ellipse. The previous 8-copy
    # union only covered 9 discrete offsets: a ~5u hairline came out as 3 parallel ghost lines 16u apart
    # and every tapered flourish tip frayed into strands (audit #14). Stroked round joins arrive as
    # conics, so they are converted to quads before the union.
    k = dx / dy
    us = pathops.Path(); path.draw(TransformPen(us.getPen(), (1, 0, -TAN, k, 0, 0)))   # un-slant + stretch y
    try: us.simplify()
    except pathops.PathOpsError: pass
    st = pathops.Path(); us.draw(st.getPen())
    st.stroke(2 * dx, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4.0); st.convertConicsToQuads()
    u = pathops.Path(); us.draw(u.getPen()); st.draw(u.getPen())
    try: u.simplify()
    except pathops.PathOpsError: pass   # un-simplified fill+band still renders solid via nonzero winding
    out = pathops.Path(); u.draw(TransformPen(out.getPen(), (1, 0, TAN / k, 1.0 / k, 0, 0)))   # unstretch + re-slant
    try: out.simplify()
    except pathops.PathOpsError: pass
    return purge_slivers(out)

charstrings = {}; metrics = {}
for g in order:
    adv, lsb = hmtx[g]
    p = pathops.Path(); gs[g].draw(p.getPen())
    if not p.bounds:                                   # space / empty
        charstrings[g] = T2CharStringPen(adv, None).getCharString(); metrics[g] = (adv, lsb); continue
    pb = embolden(p, D, DY)
    sh = pathops.Path(); pb.draw(TransformPen(sh.getPen(), (1,0,0,1,D,0)))
    try: sh.simplify()
    except pathops.PathOpsError: pass
    newadv = int(round(adv + 2*D)); b = sh.bounds
    t2 = T2CharStringPen(newadv, None); sh.draw(t2)
    charstrings[g] = t2.getCharString(); metrics[g] = (newadv, int(round(b[0])) if b else lsb)

AUTHOR = "Goran Arsov"
ATTRIB = (f'Makedonka Cursive. (c) 2026 {AUTHOR}. Macedonian cursive letterforms derived from '
          '"Macedonian cursive script" by MacedonianBoy (Wikimedia Commons), CC BY-SA 3.0; changes were made. '
          'Distributed under CC BY-SA 3.0.')
LICENSE = (f'Makedonka Cursive by {AUTHOR} is a derivative of "Macedonian cursive script" by MacedonianBoy '
           '(https://commons.wikimedia.org/wiki/File:Macedonian_cursive_script.svg), CC BY-SA 3.0. The digits, '
           f'punctuation, Bold weight, Latin alphabet, spacing and kerning are by {AUTHOR}. Distributed under '
           'CC BY-SA 3.0: keep attribution and license derivatives alike.')
PS = "MakedonkaCursive-Bold"
fb = FontBuilder(UPM, isTTF=False)
fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
# CFF alignment zones, widened slightly for the dilated Bold; heavier standard stems than the Regular.
PRIVATE = {"BlueValues": [-12, 0, 258, 278, 546, 568, 678, 700], "OtherBlues": [-252, -232],
           "StdHW": 30, "StdVW": 72, "BlueScale": 0.0396, "BlueShift": 7, "BlueFuzz": 1}
fb.setupCFF(PS, {"version": VER, "FullName": "Makedonka Cursive Bold", "FamilyName": "Makedonka Cursive",
                 "Weight": "Bold", "Notice": ATTRIB, "ItalicAngle": 0}, charstrings, PRIVATE)
fb.setupHorizontalMetrics(metrics)
asc = f["hhea"].ascent; desc = f["hhea"].descent
fb.setupHorizontalHeader(ascent=asc, descent=desc, lineGap=0)
fb.setupNameTable({
    "familyName": "Makedonka Cursive", "styleName": "Bold", "uniqueFontIdentifier": f"MakedonkaCursive;{VER};Bold",
    "fullName": "Makedonka Cursive Bold", "psName": PS, "version": f"Version {VER}", "copyright": ATTRIB,
    "description": "Macedonian cursive display font by Goran Arsov, Bold weight (dilated from the Regular); letterforms derived from a CC BY-SA 3.0 chart by MacedonianBoy.",
    "designer": "Goran Arsov; original Macedonian cursive letterforms by MacedonianBoy", "manufacturer": "Goran Arsov",
    "licenseDescription": LICENSE, "licenseInfoURL": "https://creativecommons.org/licenses/by-sa/3.0/",
})
o2 = f["OS/2"]
fb.setupOS2(sTypoAscender=o2.sTypoAscender, sTypoDescender=o2.sTypoDescender, sTypoLineGap=o2.sTypoLineGap,
            usWinAscent=asc, usWinDescent=abs(desc), usWeightClass=700,
            sxHeight=o2.sxHeight, sCapHeight=o2.sCapHeight)   # carry the Regular's measured x/cap heights
fb.font["OS/2"].fsSelection = (fb.font["OS/2"].fsSelection & ~0x40) | 0x20 | 0x80   # clear REGULAR; set BOLD + USE_TYPO_METRICS
fb.font["head"].macStyle |= 0x01
# ---- font-table correctness + QA, matching the Regular ----
_b = fb.font["OS/2"]
_b.version = 4                          # USE_TYPO_METRICS bit needs OS/2 v4+
_b.fsType = 0x0000; _b.achVendID = "GARS"
_b.ulCodePageRange1 = 0x00000005; _b.ulCodePageRange2 = 0x00000000
for _k, _v in dict(bFamilyType=3, bSerifStyle=0, bWeight=8, bProportion=3, bContrast=6, bStrokeVariation=6,
                   bArmStyle=0, bLetterForm=9, bMidline=0, bXHeight=4).items():
    setattr(_b.panose, _k, _v)          # PANOSE: Latin hand-written / script, bold
fb.font["head"].fontRevision = 0.937
# STAT (Bold's position on the Weight axis) + meta (design/supported scripts), matching the
# Regular. Placed BEFORE the Mac-name strip so buildStatTable's platform-1 names are removed too.
from fontTools.otlLib.builder import buildStatTable
buildStatTable(fb.font, [dict(tag="wght", name="Weight",
                              values=[dict(value=700, name="Bold", flags=0x0)])],
               elidedFallbackName="Regular")
_meta = newTable("meta"); _meta.data = {"dlng": "Latn, Cyrl", "slng": "Latn, Cyrl"}
fb.font["meta"] = _meta
fb.font["name"].removeNames(platformID=1)   # drop legacy Macintosh name records
_bh = fb.font["hhea"]
_bh.caretSlopeRise = 1; _bh.caretSlopeRun = 0   # vertical caret (upright-classified; italicAngle 0)
fb.setupPost(italicAngle=0.0)
otf = os.path.join(OUTDIR, "MakedonkaCursive-Bold.otf")
fb.save(otf); print("saved", otf, "D=", D)
from kern_util import add_kern                       # kern the Bold on its own (dilated) metrics
from features import FIGURE_FEA                       # figure features come via the emboldened variant glyphs
print(f"kerning (bold): {add_kern(otf, FIGURE_FEA)} pairs")   # kern GPOS + figures GSUB, one compile
# hinting: psautohint stem hints keyed off the Private-dict alignment zones (best-effort)
import subprocess
try:
    _ps = os.path.join(os.path.dirname(sys.executable), "psautohint")
    _r = subprocess.run([_ps, otf, "-o", otf], capture_output=True, text=True, timeout=300)
    print(f"hinted bold (psautohint rc={_r.returncode})")
except Exception as _e:
    print(f"WARN: psautohint skipped for bold ({_e})")
for fl in ("woff2", "woff"):
    g = TTFont(otf); g.flavor = fl; g.save(os.path.join(OUTDIR, f"MakedonkaCursive-Bold.{fl}"))
