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
    for d in DIG:
        for suf, dy in (("sups", 300), ("subs", -70), ("numr", 290), ("dnom", 10)):
            s = _xf(base_paths[d], (SC, 0, 0, SC, 0, 0)); b = s.bounds
            pad = 6 if suf in ("numr", "dnom") else 20
            add(d+"."+suf, _xf(s, (1, 0, 0, 1, -b[0], dy)), int(round((b[2]-b[0])+pad)))

    # slashed zero — a diagonal bar through the counter
    pz = base_paths["zero"]; b = pz.bounds
    cx, cy = (b[0]+b[2])/2.0, (b[1]+b[3])/2.0; L, th = 150, 26
    dx, dy = math.cos(math.radians(62)), math.sin(math.radians(62)); nx, ny = -dy, dx
    bar = pathops.Path(); bp = bar.getPen()
    pts = [(cx-dx*L-nx*th, cy-dy*L-ny*th), (cx+dx*L-nx*th, cy+dy*L-ny*th),
           (cx+dx*L+nx*th, cy+dy*L+ny*th), (cx-dx*L+nx*th, cy-dy*L+ny*th)]
    bp.moveTo(pts[0]); [bp.lineTo(q) for q in pts[1:]]; bp.closePath()
    zs = pathops.Path(); pz.draw(zs.getPen()); bar.draw(zs.getPen())
    try: zs.simplify()
    except pathops.PathOpsError: pass
    add("zero.slash", zs, metrics["zero"][0])

    # fraction bar (U+2044) — a steep thin diagonal spanning the figure height
    fr = pathops.Path(); fp = fr.getPen(); th2 = 20; x0, y0, x1, y1 = 40, -60, 300, 680
    L2 = math.hypot(x1-x0, y1-y0); ux, uy = (x1-x0)/L2, (y1-y0)/L2; nx2, ny2 = -uy, ux
    fpts = [(x0-nx2*th2, y0-ny2*th2), (x1-nx2*th2, y1-ny2*th2),
            (x1+nx2*th2, y1+ny2*th2), (x0+nx2*th2, y0+ny2*th2)]
    fp.moveTo(fpts[0]); [fp.lineTo(q) for q in fpts[1:]]; fp.closePath()
    add("fraction", fr, 180, 0x2044)
    return FIGURE_FEA

FIGURE_FEA = """
@figs = [zero one two three four five six seven eight nine];
@tf   = [zero.tf one.tf two.tf three.tf four.tf five.tf six.tf seven.tf eight.tf nine.tf];
@sups = [zero.sups one.sups two.sups three.sups four.sups five.sups six.sups seven.sups eight.sups nine.sups];
@subs = [zero.subs one.subs two.subs three.subs four.subs five.subs six.subs seven.subs eight.subs nine.subs];
@numr = [zero.numr one.numr two.numr three.numr four.numr five.numr six.numr seven.numr eight.numr nine.numr];
@dnom = [zero.dnom one.dnom two.dnom three.dnom four.dnom five.dnom six.dnom seven.dnom eight.dnom nine.dnom];

feature tnum { sub @figs by @tf; } tnum;
feature zero { sub zero by zero.slash; } zero;
feature sups { sub @figs by @sups; } sups;
feature subs { sub @figs by @subs; } subs;
feature numr { sub @figs by @numr; } numr;
feature dnom { sub @figs by @dnom; } dnom;

lookup FRAC_NUMR { sub @figs by @numr; } FRAC_NUMR;
lookup FRAC_DNOM { sub @figs by @dnom; } FRAC_DNOM;
feature frac {
    sub slash by fraction;
    # numerators: up to three figures before the fraction bar (longest match first)
    sub @figs' lookup FRAC_NUMR @figs' lookup FRAC_NUMR @figs' lookup FRAC_NUMR fraction;
    sub @figs' lookup FRAC_NUMR @figs' lookup FRAC_NUMR fraction;
    sub @figs' lookup FRAC_NUMR fraction;
    # denominators: up to three figures after the fraction bar
    sub fraction @figs' lookup FRAC_DNOM @figs' lookup FRAC_DNOM @figs' lookup FRAC_DNOM;
    sub fraction @figs' lookup FRAC_DNOM @figs' lookup FRAC_DNOM;
    sub fraction @figs' lookup FRAC_DNOM;
} frac;
"""
