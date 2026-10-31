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
from fontTools.ttLib import TTFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
import pathops

REG, OUTDIR = sys.argv[1], sys.argv[2]
D = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
VER = "0.9.11"
f = TTFont(REG); gs = f.getGlyphSet(); order = f.getGlyphOrder()
cmap = f.getBestCmap(); hmtx = f["hmtx"]; UPM = f["head"].unitsPerEm

def embolden(path, d):
    dirs = [(d,0),(-d,0),(0,d),(0,-d),(0.7*d,0.7*d),(-0.7*d,-0.7*d),(0.7*d,-0.7*d),(-0.7*d,0.7*d)]
    def union():
        u = pathops.Path(); pen = u.getPen(); path.draw(pen)
        for dx, dy in dirs: path.draw(TransformPen(pen, (1,0,0,1,dx,dy)))
        return u
    u = union()
    try:
        u.simplify(); return u
    except pathops.PathOpsError:
        return union()   # un-simplified: renders solid via nonzero winding

charstrings = {}; metrics = {}
for g in order:
    adv, lsb = hmtx[g]
    p = pathops.Path(); gs[g].draw(p.getPen())
    if not p.bounds:                                   # space / empty
        charstrings[g] = T2CharStringPen(adv, None).getCharString(); metrics[g] = (adv, lsb); continue
    pb = embolden(p, D)
    sh = pathops.Path(); pb.draw(TransformPen(sh.getPen(), (1,0,0,1,D,0)))
    try: sh.simplify()
    except pathops.PathOpsError: pass
    newadv = int(round(adv + 2*D)); b = sh.bounds
    t2 = T2CharStringPen(newadv, None); sh.draw(t2)
    charstrings[g] = t2.getCharString(); metrics[g] = (newadv, int(round(b[0])) if b else lsb)

ATTRIB = ('Derived from "Macedonian cursive script" by MacedonianBoy (Wikimedia Commons), licensed CC BY-SA 3.0.')
LICENSE = ('Derivative of "Macedonian cursive script" by MacedonianBoy '
           '(https://commons.wikimedia.org/wiki/File:Macedonian_cursive_script.svg), CC BY-SA 3.0. '
           'This font is distributed under CC BY-SA 3.0: keep attribution and license derivatives alike.')
PS = "MakedonkaCursive-Bold"
fb = FontBuilder(UPM, isTTF=False)
fb.setupGlyphOrder(order); fb.setupCharacterMap(cmap)
fb.setupCFF(PS, {"version": VER, "FullName": "Makedonka Cursive Bold", "FamilyName": "Makedonka Cursive",
                 "Weight": "Bold", "Notice": ATTRIB, "ItalicAngle": -18}, charstrings, {})
fb.setupHorizontalMetrics(metrics)
asc = f["hhea"].ascent; desc = f["hhea"].descent
fb.setupHorizontalHeader(ascent=asc, descent=desc, lineGap=0)
fb.setupNameTable({
    "familyName": "Makedonka Cursive", "styleName": "Bold", "uniqueFontIdentifier": f"MakedonkaCursive;{VER};Bold",
    "fullName": "Makedonka Cursive Bold", "psName": PS, "version": f"Version {VER}", "copyright": ATTRIB,
    "description": "Macedonian cursive display font, Bold weight (dilated from the Regular).",
    "designer": "MacedonianBoy (original cursive letterforms)",
    "licenseDescription": LICENSE, "licenseInfoURL": "https://creativecommons.org/licenses/by-sa/3.0/",
})
o2 = f["OS/2"]
fb.setupOS2(sTypoAscender=o2.sTypoAscender, sTypoDescender=o2.sTypoDescender, sTypoLineGap=o2.sTypoLineGap,
            usWinAscent=asc, usWinDescent=abs(desc), usWeightClass=700)
fb.font["OS/2"].fsSelection = (fb.font["OS/2"].fsSelection & ~0x40) | 0x20   # clear REGULAR, set BOLD
fb.font["head"].macStyle |= 0x01
fb.setupPost(italicAngle=-18.0)
otf = os.path.join(OUTDIR, "MakedonkaCursive-Bold.otf")
fb.save(otf); print("saved", otf, "D=", D)
for fl in ("woff2", "woff"):
    g = TTFont(otf); g.flavor = fl; g.save(os.path.join(OUTDIR, f"MakedonkaCursive-Bold.{fl}"))
