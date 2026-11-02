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
SC = 0.68     # scale of the super/subscript & numerator/denominator figures (of the 450u hybrid figure → ~306u)

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
    fh = base_paths["zero"].bounds[3]   # the default (hybrid) figure height — the raises scale with it
    for d in DIG:
        for suf, dy in (("sups", round(0.45 * fh)), ("subs", -70), ("numr", round(0.44 * fh)), ("dnom", 10)):
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
    # v0.9.37: a THIN tapered pen diagonal (half-width 11 at the top, 5 at the bottom; was a 40u-thick bar that
    # read as a bold slash next to the light figures), from just below the baseline to just above the figure top
    fr = pathops.Path(); fp = fr.getPen(); tt, tb = 11, 5; x0, y0, y1 = 40, -40, fh + 12; x1 = x0 + round(260 * (y1 - y0) / 740.0)
    L2 = math.hypot(x1-x0, y1-y0); ux, uy = (x1-x0)/L2, (y1-y0)/L2; nx2, ny2 = -uy, ux
    fpts = [(x0-nx2*tb, y0-ny2*tb), (x1-nx2*tt, y1-ny2*tt),
            (x1+nx2*tt, y1+ny2*tt), (x0+nx2*tb, y0+ny2*tb)]
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
@dashf = [hyphen.fig endash.fig emdash.fig plus.fig minus.fig equal.fig multiply.fig divide.fig less.fig greater.fig plusminus.fig];
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
lookup DASH_FIG  { sub @dash by @dashf; } DASH_FIG;
# cap-height figures (v0.9.36): the default figures are hybrid (450u); next to a capital (space allowed) a figure
# run takes the 660u `.case` set — after a capital it propagates left-to-right (also across a `.case` dash), before
# a capital runs of 1–4 figures are matched whole. Dashes/operators: `.case` next to capitals or `.case` figures,
# `.fig` next to hybrid (or tabular) figures, the lowercase default otherwise.
lookup FIG_CASE { sub @figs by @figsc; } FIG_CASE;
# apostrophes after an x-height letter take a lower form (v0.9.37): the raised one floated far above "it's"
@XH = [a.lat c.lat e.lat g.lat i j.lat m.lat n o.lat p q r s.lat u.lat v w x.lat y.lat z scaron zcaron cacute t
       """ + " ".join("uni%04X" % ord(c) for c in "агдежзѕијклљмнњопрстќуфхцчџшѐѝ") + """];
@LC_ASC = [b d f h k l dcroat uni0431 uni0432 uni0453];
@LETTERS = [@XH @LC_ASC @CAPS];
@PUNCT = [comma period semicolon colon exclam question ellipsis parenright bracketright braceright hyphen endash emdash quotedblright guillemotright];
lookup QUO_LC { sub quoteright by quoteright.lc; sub quotesingle by quotesingle.lc; } QUO_LC;
feature case { lookup DASH_CASE; lookup FIG_CASE; } case;
feature calt {
    # apostrophes: lowered after a short letter when a letter follows (it's, don't, element's) and when leading
    # before a short letter ('n', 'tis, 'cause); a straight ' after a short letter is always lowered (commin',
    # commin'. — and the closing of a straight-quoted 'word' pairs with its lowered opening); a typographic ’
    # after a short letter is lowered before a letter or a punctuation mark (commin’, goin’.) but stays high
    # before a space or at the end (boys’ room, ‘quote’ — so it matches its ‘); the 'n' idiom (rock'n'roll) is
    # lowered whatever precedes it, so both apostrophes match
    sub @XH [quoteright quotesingle]' lookup QUO_LC @LETTERS;
    sub @XH [quoteright quotesingle]' lookup QUO_LC @PUNCT;
    sub @XH quotesingle' lookup QUO_LC;
    sub space [quoteright quotesingle]' lookup QUO_LC @XH;
    sub [quoteright quotesingle]' lookup QUO_LC @XH [quoteright quotesingle];
    # cap-height figures: after a capital (propagating along the run, also across a `.case` dash), or before an
    # ALL-CAPS word (two capitals); a single following capital is ordinary prose ("all 31 Macedonian letters")
    sub @CAPS @figs' lookup FIG_CASE;
    sub @CAPS space @figs' lookup FIG_CASE;
    sub [@figsc @dashc] @figs' lookup FIG_CASE;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE space @CAPS @CAPS;
    sub @figs' lookup FIG_CASE space @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @figs' lookup FIG_CASE @CAPS @CAPS;
    sub @figs' lookup FIG_CASE @CAPS @CAPS;
    # dashes/operators: (1) after a cap-height figure → `.case`; (2) a hybrid (or tabular) figure on either side
    # → `.fig`; (3) after a capital, or before an ALL-CAPS word → `.case`; a lone following capital does not raise
    # ("њива — Сѐ"); otherwise the lowercase default
    sub @figsc @dash' lookup DASH_CASE;
    sub @figsc space @dash' lookup DASH_CASE;
    sub [@figs @tf] @dash' lookup DASH_FIG;
    sub [@figs @tf] space @dash' lookup DASH_FIG;
    sub @dash' lookup DASH_FIG [@figs @tf];
    sub @dash' lookup DASH_FIG space [@figs @tf];
    sub @CAPS @dash' lookup DASH_CASE;
    sub @CAPS space @dash' lookup DASH_CASE;
    sub @dash' lookup DASH_CASE @CAPS @CAPS;
    sub @dash' lookup DASH_CASE space @CAPS @CAPS;
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
