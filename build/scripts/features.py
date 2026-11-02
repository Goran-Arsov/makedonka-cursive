#!/usr/bin/env python3
"""OpenType figures feature suite for Makedonka Cursive, derived from the built
digit outlines (no new drawing tools). Features:
  tnum  tabular (uniform-advance) figures
  zero  slashed zero
  sups  superscript figures      subs  subscript figures
  numr  numerators               dnom  denominators
  frac  fractions (1/2 -> numerator + fraction bar + denominator)

build_font.py calls generate_figures() with the positioned digit paths (it adds
the ~52 variant glyphs) then compiles FIGURE_FEA; make_bold.py emboldens those
glyphs with the rest and only re-compiles FIGURE_FEA. Glyph names are shared.
"""
import math
import pathops
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen

DIG = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
TAB = 360     # common tabular advance (figures centred within it)
SC = 0.60     # scale of the super/subscript & numerator/denominator figures

def _cs(path, adv):
    t2 = T2CharStringPen(adv, None); path.draw(t2); return t2.getCharString()
def _xf(path, t):
    q = pathops.Path(); path.draw(TransformPen(q.getPen(), t))
    try: q.simplify()
    except pathops.PathOpsError: pass
    return q

def generate_figures(base_paths, charstrings, metrics, glyph_order, cmap):
    """base_paths: {digit_name: pathops.Path positioned on the baseline}. Appends
    the variant glyphs to the four build dicts; returns the FEA string to compile."""
    def add(name, path, adv, uni=None):
        glyph_order.append(name); charstrings[name] = _cs(path, adv)
        b = path.bounds; metrics[name] = (adv, int(round(b[0])) if b else 0)
        if uni is not None: cmap[uni] = name

    # tabular figures — each digit's ink centred in a common advance
    for d in DIG:
        p = base_paths[d]; b = p.bounds; cx = (b[0]+b[2])/2.0
        add(d+".tf", _xf(p, (1, 0, 0, 1, TAB/2.0-cx, 0)), TAB)

    # scaled figure variants (scale about the baseline origin keeps the slant).
    # numr/dnom sit snug around the fraction bar, so they get less side spacing than sups/subs.
    var = {}   # name -> positioned path (reused to compose ½ ¼ ¾ below)
    for d in DIG:
        for suf, dy in (("sups", 300), ("subs", -70), ("numr", 290), ("dnom", 10)):
            s = _xf(base_paths[d], (SC, 0, 0, SC, 0, 0)); b = s.bounds
            pad = 6 if suf in ("numr", "dnom") else 20
            var[d+"."+suf] = _xf(s, (1, 0, 0, 1, -b[0], dy))
            add(d+"."+suf, var[d+"."+suf], int(round((b[2]-b[0])+pad)))
    # v0.9.35 (audit #27): the super/subscript figures also get their Unicode codepoints
    # (¹ ² ³ ⁰ ⁴–⁹, ₀–₉), so "m²" / "H₂O" typed as characters no longer render tofu.
    for i, d in enumerate(DIG):
        cmap[{1: 0x00B9, 2: 0x00B2, 3: 0x00B3}.get(i, 0x2070 + i)] = d + ".sups"
        cmap[0x2080 + i] = d + ".subs"

    # slashed zero — a diagonal bar through the counter (default and, if present, the cap-height `.case` zero)
    for zname in ("zero", "zero.case"):
        if zname not in base_paths: continue
        pz = base_paths[zname]; b = pz.bounds
        cx, cy = (b[0]+b[2])/2.0, (b[1]+b[3])/2.0; L, th = 150 * (b[3]-b[1]) / 660.0, 26
        dx, dy = math.cos(math.radians(62)), math.sin(math.radians(62)); nx, ny = -dy, dx
        bar = pathops.Path(); bp = bar.getPen()
        pts = [(cx-dx*L-nx*th, cy-dy*L-ny*th), (cx+dx*L-nx*th, cy+dy*L-ny*th),
               (cx+dx*L+nx*th, cy+dy*L+ny*th), (cx-dx*L+nx*th, cy-dy*L+ny*th)]
        bp.moveTo(pts[0]); [bp.lineTo(q) for q in pts[1:]]; bp.closePath()
        zs = pathops.Path(); pz.draw(zs.getPen()); bar.draw(zs.getPen())
        try: zs.simplify()
        except pathops.PathOpsError: pass
        add(zname.replace("zero", "zero.slash"), zs, metrics[zname][0])

    # fraction bar (U+2044) — a steep thin diagonal spanning the figure height (follows the default figure height)
    fh = base_paths["zero"].bounds[3]
    fr = pathops.Path(); fp = fr.getPen(); th2 = 20; x0, y0, y1 = 40, -60, fh + 20; x1 = x0 + round(260 * (y1 - y0) / 740.0)
    L2 = math.hypot(x1-x0, y1-y0); ux, uy = (x1-x0)/L2, (y1-y0)/L2; nx2, ny2 = -uy, ux
    fpts = [(x0-nx2*th2, y0-ny2*th2), (x1-nx2*th2, y1-ny2*th2),
            (x1+nx2*th2, y1+ny2*th2), (x0+nx2*th2, y0+ny2*th2)]
    fp.moveTo(fpts[0]); [fp.lineTo(q) for q in fpts[1:]]; fp.closePath()
    add("fraction", fr, 180, 0x2044)
    # precomposed vulgar fractions ½ ¼ ¾ (U+00BD/BC/BE) = numerator + fraction bar + denominator, laid out
    # exactly as `frac` would shape them (v0.9.35, audit #27)
    for name, uni, n, dn in (("onehalf", 0x00BD, "one", "two"), ("onequarter", 0x00BC, "one", "four"), ("threequarters", 0x00BE, "three", "four")):
        comp = pathops.Path(); x = 0.0
        for part, pname in ((var[n + ".numr"], n + ".numr"), (fr, "fraction"), (var[dn + ".dnom"], dn + ".dnom")):
            part.draw(TransformPen(comp.getPen(), (1, 0, 0, 1, x, 0)))
            x += metrics[pname][0]
        try: comp.simplify()
        except pathops.PathOpsError: pass
        add(name, comp, int(round(x)), uni)
    return FIGURE_FEA

FIGURE_FEA = """
@figs = [zero one two three four five six seven eight nine];
@tf   = [zero.tf one.tf two.tf three.tf four.tf five.tf six.tf seven.tf eight.tf nine.tf];
@sups = [zero.sups one.sups two.sups three.sups four.sups five.sups six.sups seven.sups eight.sups nine.sups];
@subs = [zero.subs one.subs two.subs three.subs four.subs five.subs six.subs seven.subs eight.subs nine.subs];
@numr = [zero.numr one.numr two.numr three.numr four.numr five.numr six.numr seven.numr eight.numr nine.numr];
@dnom = [zero.dnom one.dnom two.dnom three.dnom four.dnom five.dnom six.dnom seven.dnom eight.dnom nine.dnom];

@figsc = [zero.case one.case two.case three.case four.case five.case six.case seven.case eight.case nine.case];
@figsall = [@figs @figsc];
@dash  = [hyphen endash emdash plus minus equal multiply divide less greater plusminus];
@dashc = [hyphen.case endash.case emdash.case plus.case minus.case equal.case multiply.case divide.case less.case greater.case plusminus.case];
# capitals of both scripts (for the raised-dash context)
@CAPS = [""" + " ".join("uni%04X" % ord(c) for c in "АБВГДЃЕЖЗЅИЈКЛЉМНЊОПРСТЌУФХЦЧЏШЀЍ") + """
         A.lat B.lat C.lat D E.lat F G H.lat I J.lat K.lat L M.lat N O.lat P.lat Q R S.lat T U V W X.lat Y.lat Z
         Scaron Ccaron Zcaron Cacute Dcroat];

feature tnum { sub @figs by @tf; } tnum;
# dashes and math operators sit on a lowercase axis by default (lowercase text); next to a figure or a capital
# (before or after, a space allowed in between), or in all-caps settings (`case`), the raised `.case` forms on
# the figure axis are used (v0.9.35 dashes, v0.9.36 operators)
lookup DASH_CASE { sub @dash by @dashc; } DASH_CASE;
# cap-height figures (v0.9.36): the default figures are ascender-height; next to a capital (space allowed) a
# figure run takes the 660u `.case` set — after a capital it propagates left-to-right, before a capital runs of
# 1–4 figures are matched whole
lookup FIG_CASE { sub @figs by @figsc; } FIG_CASE;
feature case { lookup DASH_CASE; lookup FIG_CASE; } case;
feature calt {
    sub @CAPS @figs' lookup FIG_CASE;
    sub @CAPS space @figs' lookup FIG_CASE;
    sub @figsc @figs' lookup FIG_CASE;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS;
    sub @figs' lookup FIG_CASE space @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS;
    sub @figs' lookup FIG_CASE @CAPS;
    sub [@figsall @tf @CAPS] @dash' lookup DASH_CASE;
    sub [@figsall @tf @CAPS] space @dash' lookup DASH_CASE;
    sub @dash' lookup DASH_CASE [@figsall @tf @CAPS];
    sub @dash' lookup DASH_CASE space [@figsall @tf @CAPS];
} calt;
feature zero { sub zero by zero.slash; sub zero.case by zero.slash.case; } zero;
feature sups { sub @figs by @sups; sub @figsc by @sups; } sups;
feature subs { sub @figs by @subs; sub @figsc by @subs; } subs;
feature numr { sub @figs by @numr; sub @figsc by @numr; } numr;
feature dnom { sub @figs by @dnom; sub @figsc by @dnom; } dnom;

lookup FRAC_NUMR { sub @figs by @numr; sub @figsc by @numr; } FRAC_NUMR;
lookup FRAC_DNOM { sub @figs by @dnom; sub @figsc by @dnom; } FRAC_DNOM;
feature frac {
    sub slash by fraction;
    # denominators FIRST (up to four figures after a bar), so a figure run between two bars — "10/11/2025" —
    # is a denominator and never re-matched as the next numerator (v0.9.35, audit #27)
    sub fraction @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM;
    sub fraction @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM;
    sub fraction @figsall' lookup FRAC_DNOM @figsall' lookup FRAC_DNOM;
    sub fraction @figsall' lookup FRAC_DNOM;
    # numerators: up to four figures before the fraction bar (longest match first)
    sub @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR fraction;
    sub @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR fraction;
    sub @figsall' lookup FRAC_NUMR @figsall' lookup FRAC_NUMR fraction;
    sub @figsall' lookup FRAC_NUMR fraction;
} frac;
"""
