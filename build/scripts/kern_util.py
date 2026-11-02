"""Connection kerning — a GPOS `kern` feature that evens cursive joins without touching the glyphs.

The lavish cursive exits (о's right hair, etc.) set wide advances, so some joins read disconnected
(о–н), while some straight-before-straight pairs (n–k) read crowded. Rather than trim the exits
(kills the lavish look) or move sidebearings (hurts other pairs), kern each pair:

  per within-script lowercase pair, measure the white area and nearest approach in the x-height band,
  then LOOSEN crowded pairs up toward W_LOW, and TIGHTEN loose pairs down toward W_HIGH — never past
  the nearest floor N_FLOOR, so a tighten can never collide. Pairs already in the W_LOW..W_HIGH band
  are left alone.

Called by both the Regular build and make_bold, so each weight is kerned on its own metrics
(the Bold's dilated glyphs are wider, so it needs different kerns)."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

W_LOW, W_HIGH, N_FLOOR, S_MAX, MIN_KERN = 115, 180, 14, 60, 5
_CYR = "абвгдѓежзѕијклљмнњопрстќуфхцчџшѐѝ"
_LAT = "abcdefghijklmnopqrstuvwxyzšžčćđ"   # + the South-Slavic diacritics (v0.9.35)
# v0.9.35 (audit #18): proportional figures have negative sidebearings (lsb −29..−102) and NO kerning, so
# 60 09 68 66 89 99 04 54 … interlocked. Push every figure pair apart to a minimum full-height ink gap.
DIG_GAP, DIG_MAX = 24, 120
_DIG = "0123456789"
_DIG_CASE = [n + ".case" for n in ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")]   # cap-height set (v0.9.36)
# v0.9.35 (audit #19): the ornate S/Š top curl lands on a following ascender loop (Sk Sl Sf Sb Sh); push
# those pairs apart until the ascender band (above the x-height) clears by ASC_GAP, capped at ASC_MAX.
ASC_GAP, ASC_MAX, ASC_LO, ASC_HI = 10, 160, 270, 640
_ASC_CAPS, _ASC_LOW = "SŠFT", "bfhklđ"      # + F/T (their bars over a following ascender loop; the glyphs were also reshaped)
# the ornate Ф/Ѕ right flourishes cross a following ascender/overbar letter in the Bold (Фб 448px²…) — same
# floor model in the band where the Ф tail hangs (y 343..497 measured)
_CYR_FL_CAPS, _CYR_FL_LOW, CFL_LO, CFL_HI, CFL_GAP, CFL_MAX = "ФЅ", "бвѓќрјтпгд", 300, 600, 10, 160
# the raised closing quotes now share the opening quotes' height, so in the Bold a tall ascender (f d đ в)
# can touch a following ’ ” — same floor model in the quote band (v0.9.35)
_QUO_L_LOW, _QUO_L_CAPS = "bdfhklđtвѓќб", "ABCDEFGHIJKLMNOPQRSTUVWXYZŠČŽĆĐ" + "АБВГДЃЕЖЗЅИЈКЛЉМНЊОПРСТЌУФХЦЧЏШ"
_QUO_L, _QUO_R, QUO_LO, QUO_HI, QUO_GAP, QUO_MAX = _QUO_L_LOW + _QUO_L_CAPS, "’”‘“'\"", 250, 700, 36, 170   # + capitals ("I'd", "O'Neil"); б's flag needs ~120 in the Bold;
# QUO_LO 250 (was 300): since v0.9.38 the marks span ~260–465, tail at the x-height, so the band must reach the
# exit strokes there — an exit overshooting its advance would otherwise meet the tail unseen.
# gap 36 (not the usual 8): the b/h/k/l ascender loops lean right, and an apostrophe parked 8u from the loop
# read as part of it ("capital's") — it needs visible white before it. The reverse pass (quote → ascender)
# keeps the small gap. A CAPITAL before an apostrophe gets more still (CAP_QUO_GAP): the mark parked 36u
# from an I's stem read as glued to it ("I'd", owner's v0.9.37 screenshot).
QUO_GAP_REV = 8
CAP_QUO_GAP = 80
# the lowered `.lc` apostrophes (after x-height letters) are kerned in their own, lower band (v0.9.37)
_QUO_LC = ["quoteright.lc", "quotesingle.lc"]
_QUO_LC_L = "acegijmnopqrsuvwxyzšžćtагдежзѕијклљмнњопрстќуфхцчџшѐѝ"
QUO_LC_LO, QUO_LC_HI = 250, 540   # LO 250 since v0.9.38 (tail at the x-height — see QUO_LO)
# v0.9.37 "tuck": an x-height letter after an apostrophe (s in "Let's", m in "I'mma") never enters the quote
# band, so no pass above touches the pair and the letter sits a full apostrophe-advance away — the s/m/м
# start with a long low entry stroke, so their x-height ink is far right of the mark's tail and the pair reads
# with a hole under the mark. Pull such a letter under the mark until its top-left ink is TUCK_G from the
# tail tip MEASURED ALONG THE SLANT (the tail line extended down to the letter's top); negative-only, capped
# at TUCK_MAX so the tucked letter's ink stays ≥ ~60u right of the mark's origin (the mark's own left air —
# an I's foot swash or a cursive exit before the mark is never reached). Pairs the floor passes own (letters
# with ink inside the quote band: ascenders, t, i-dot, overbars) are left to them. TUCK_G 215 ≈ the air the
# untouched good pairs already have (n'r 249, a'a 199, you're 249).
_QUO_APOS = ["quotesingle", "quoteright", "quotesingle.lc", "quoteright.lc"]
TUCK_G, TUCK_MAX, TUCK_BAND, TUCK_SLANT_DEG = 215, 110, 70, 15.0   # TUCK_SLANT_DEG == build_font.T_DEG
TUCK_XH_MAX = 300   # a letter whose ink tops out below this is an x-height letter and tucks (tallest: Bold s 282);
                    # anything taller (ascenders 569+, i/j dots ~397, overbars ~356, ѓ/ќ accents) is floor-owned.
                    # Since the quote tail now sits AT the x-height (QUO_DY −175), "reaches the mark's lowest ink"
                    # would have disowned every x-height letter — the tuck keeps 215u of slant-wise separation anyway.

# Uppercase spacing kern (v0.9.17; reworked v0.9.25, v0.9.27, v0.9.28): equalise the gap the EYE reads
# between cap bodies. v0.9.27 used a full-height 15/85 ink-MASS percentile for the body edges, but that
# percentile is skewed by the ornate flourishes that loop ABOVE cap-height and BELOW the baseline — so
# the measured edge did not match the visible body, and the perceived (body-band) whitespace still varied
# wildly (−7..+89px across pairs; letters like Ѕ Ј С Е read with extra space in front). Instead measure
# each cap's body edge as the LEFT/RIGHT-MOST INK within the CAP-BODY BAND (CAP_BAND_LO..CAP_BAND_HI units
# above the baseline) — i.e. where the stroke is actually visible in the x-height/cap zone, ignoring the
# vertical flourishes. Placing those band edges CAP_BAND_GAP apart (both widening AND tightening) evens the
# perceived whitespace to ~10px spread. Fires ONLY capital-before-capital, so the capital->lowercase tuck is
# untouched. (The band excludes descenders/top flourishes, so those still cross thinly between ornate pairs.)
CAP_BAND_GAP, CAP_BAND_LO, CAP_BAND_HI, MIN_CAP_KERN = 290, 100, 590, 10
_CYR_CAPS = "АБВГДЃЕЖЗЅИЈКЛЉМНЊОПРСТЌУФХЦЧЏШЀЍ"      # + Ѐ Ѝ (v0.9.35, audit #17 — they had no cap kern)
_LAT_CAPS = "ABCDEFGHIJKLMNOPQRSTUVWXYZŠČŽĆĐ"


class _FP:   # flatten pen: collect on-curve + sampled-curve points
    def __init__(s): s.pts = []; s.c = None
    def moveTo(s, p): s.c = p
    def lineTo(s, p): s.c = p; s.pts.append(p)
    def curveTo(s, *P):
        p0 = s.c; c1, c2, p3 = P
        for i in range(1, 13):
            t = i / 12.0; u = 1 - t
            s.pts.append((u*u*u*p0[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t*t*t*p3[0],
                          u*u*u*p0[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t*t*t*p3[1]))
        s.c = p3
    def qCurveTo(s, *P): s.c = P[-1]; s.pts.append(P[-1])
    def closePath(s): pass
    def endPath(s): pass


def _profiles(gs, gn, lo=0, hi=270):
    fp = _FP(); gs[gn].draw(fp); R = {}; L = {}
    for x, y in fp.pts:
        if lo <= y < hi:
            b = int(y // 6); R[b] = max(R.get(b, -1e9), x); L[b] = min(L.get(b, 1e9), x)
    return R, L


def _gn(cm, gs, item):
    # a kern-list item is either a character (mapped through the cmap) or a glyph name (e.g. "zero.case")
    if len(item) == 1 and ord(item) in cm: return cm[ord(item)]
    return item if item in gs else None


def _floor_pairs(gs, cm, hm, lefts, rights, lo, hi, gap, cap):
    # positive-only kern: push each (a, b) pair apart until the nearest ink approach within the
    # y-band [lo, hi) is at least `gap` units (never tightens; capped at `cap`)
    present_l = [g for g in (_gn(cm, gs, c) for c in lefts) if g]; present_r = [g for g in (_gn(cm, gs, c) for c in rights) if g]
    R = {g: _profiles(gs, g, lo, hi)[0] for g in present_l}
    L = {g: _profiles(gs, g, lo, hi)[1] for g in present_r}
    out = []
    for a in present_l:
        for b in present_r:
            bins = set(R[a]) & set(L[b])
            if not bins:
                continue
            near = min(L[b][k] + hm[a][0] - R[a][k] for k in bins)
            if near < gap:
                k = min(int(round(gap - near)), cap)
                if k >= MIN_KERN:
                    out.append((a, b, k))
    return out


def _tuck_pairs(gs, cm, hm, marks, letters):
    # negative-only kern (see TUCK_G): for (mark, letter) where the letter stays entirely BELOW the mark's
    # ink (so no floor pass can see the pair), pull the letter under the mark until its top-left ink is
    # TUCK_G from the mark's tail tip along the slant; capped at TUCK_MAX
    import math
    slant = math.tan(math.radians(TUCK_SLANT_DEG))
    def points(g):
        fp = _FP(); gs[g].draw(fp); return fp.pts
    tails = {}
    for m in marks:
        if m not in gs: continue
        P = points(m); ylo = min(y for x, y in P)
        tails[m] = min((x, y) for x, y in P if y < ylo + 30)          # leftmost ink in the lowest 30u = the tail tip
    out = []
    for b in (_gn(cm, gs, c) for c in letters):
        if not b: continue
        P = points(b)
        yhi = max(y for x, y in P)
        if yhi >= TUCK_XH_MAX: continue                                # ascender / dot / overbar: a floor pass owns it
        lx, ly = min((x, y) for x, y in P if y > yhi - TUCK_BAND)      # top-left ink of the letter
        for m, (tx, ty) in tails.items():
            g = lx + hm[m][0] - (tx + slant * (ly - ty))
            k = int(round(TUCK_G - g))
            if k <= -MIN_KERN:
                out.append((m, b, max(k, -TUCK_MAX)))
    return out


def _pairs(gs, cm, hm, letters):
    present = [c for c in letters if ord(c) in cm]
    R = {}; L = {}; A = {}
    for c in present:
        gn = cm[ord(c)]; R[c], L[c] = _profiles(gs, gn); A[c] = hm[gn][0]
    out = []
    for a in present:
        for b in present:
            bins = set(R[a]) & set(L[b])
            if not bins:
                continue
            gaps = [L[b][k] + A[a] - R[a][k] for k in bins]
            near = min(gaps); white = sum(gaps) / len(gaps)
            if white < W_LOW:
                k = min(int(round(W_LOW - white)), S_MAX)                       # loosen the crowded pair
            elif white > W_HIGH:
                k = -min(int(round(white - W_HIGH)), max(0, int(round(near - N_FLOOR))))  # tighten, nearest-floored
            else:
                k = 0
            if abs(k) >= MIN_KERN:
                out.append((cm[ord(a)], cm[ord(b)], k))
    return out


class _CFP:   # flatten pen -> closed contours, for rasterising a cap's dense body
    def __init__(s): s.ct=[]; s._c=None; s._p=(0,0)
    def moveTo(s,p): s._c=[p]; s._p=p
    def lineTo(s,p): s._c.append(p); s._p=p
    def curveTo(s,*P):
        c1,c2,e=P[-3],P[-2],P[-1]; p0=s._p
        for i in range(1,11):
            t=i/10.0; u=1-t
            s._c.append((u*u*u*p0[0]+3*u*u*t*c1[0]+3*u*t*t*c2[0]+t*t*t*e[0],
                         u*u*u*p0[1]+3*u*u*t*c1[1]+3*u*t*t*c2[1]+t*t*t*e[1]))
        s._p=e
    def qCurveTo(s,*P):
        pts=list(P); on=pts[-1]; offs=pts[:-1]; pv=s._p
        for j,c in enumerate(offs):
            nx=on if j==len(offs)-1 else ((c[0]+offs[j+1][0])/2,(c[1]+offs[j+1][1])/2)
            for i in range(1,11):
                t=i/10.0; u=1-t
                s._c.append((u*u*pv[0]+2*u*t*c[0]+t*t*nx[0], u*u*pv[1]+2*u*t*c[1]+t*t*nx[1]))
            pv=nx
        s._p=on
    def closePath(s):
        if s._c: s.ct.append(s._c); s._c=None
    def endPath(s): s.closePath()
    def addComponent(s,*a,**k): pass


def _cap_body(pilfont, ch):
    # body left/right edge = LEFT/RIGHT-most ink within the cap-body BAND (CAP_BAND_LO..CAP_BAND_HI units
    # above the baseline), from the RENDERED glyph (pilfont at size == UPM, so 1px == 1 unit; counters empty).
    # Drawn with anchor "ls" so the baseline is known; the band ignores top flourishes and descenders, so
    # the edge matches the visible body the eye spaces by.
    bb = pilfont.getbbox(ch, anchor="ls")           # (l,t,r,b) rel to left-baseline; t<0 above, b>0 below
    if not bb: return 0.0, 0.0
    l, t, r, b = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
    ox = 20 - min(0, l); base = 20 - t
    im = Image.new("L", (r + ox + 20, base + max(0, b) + 20), 0)
    ImageDraw.Draw(im).text((ox, base), ch, fill=255, font=pilfont, anchor="ls")
    a = np.asarray(im) >= 128
    band = a[max(0, base - CAP_BAND_HI): max(0, base - CAP_BAND_LO), :]
    cols = np.where(band.max(axis=0))[0]
    if len(cols) == 0:                              # no ink in band -> fall back to full ink extent
        cols = np.where(a.max(axis=0))[0]
        if len(cols) == 0: return 0.0, 0.0
    return float(cols.min() - ox), float(cols.max() - ox)


def _cap_pairs(pilfont, cm, hm, caps):
    present=[c for c in caps if ord(c) in cm]
    BL={}; BR={}; A={}
    for c in present:
        BL[c],BR[c]=_cap_body(pilfont, c); A[c]=hm[cm[ord(c)]][0]
    out=[]
    for a in present:
        for b in present:
            gap0 = A[a] + BL[b] - BR[a]            # natural band-ink gap if b sits at a's advance
            k = int(round(CAP_BAND_GAP - gap0))     # equalise every pair's body-band gap (widen OR tighten)
            if abs(k) >= MIN_CAP_KERN:
                out.append((cm[ord(a)], cm[ord(b)], k))
    return out


def add_kern(otf_path, extra_fea=""):
    # `extra_fea` (e.g. the figures GSUB from features.py) is compiled in the SAME call:
    # addOpenTypeFeaturesFromString rebuilds GSUB+GPOS from the FEA it is given, so kern and
    # any other features must share one FEA or the later call wipes the earlier tables.
    f = TTFont(otf_path); gs = f.getGlyphSet(); cm = f.getBestCmap(); hm = f["hmtx"]
    pilfont = ImageFont.truetype(otf_path, f["head"].unitsPerEm)   # 1px == 1 unit, for the cap body measure
    pairs = _pairs(gs, cm, hm, _CYR) + _pairs(gs, cm, hm, _LAT) \
          + _cap_pairs(pilfont, cm, hm, _CYR_CAPS) + _cap_pairs(pilfont, cm, hm, _LAT_CAPS) \
          + _floor_pairs(gs, cm, hm, _DIG, _DIG, -10, 670, DIG_GAP, DIG_MAX) \
          + _floor_pairs(gs, cm, hm, _DIG_CASE, _DIG_CASE, -10, 670, DIG_GAP, DIG_MAX) \
          + _floor_pairs(gs, cm, hm, _ASC_CAPS, _ASC_LOW, ASC_LO, ASC_HI, ASC_GAP, ASC_MAX) \
          + _floor_pairs(gs, cm, hm, _QUO_L_LOW, _QUO_R, QUO_LO, QUO_HI, QUO_GAP, QUO_MAX) \
          + _floor_pairs(gs, cm, hm, _QUO_L_CAPS, _QUO_R, QUO_LO, QUO_HI, CAP_QUO_GAP, QUO_MAX) \
          + _floor_pairs(gs, cm, hm, _QUO_R, _QUO_L, QUO_LO, QUO_HI, QUO_GAP_REV, QUO_MAX) \
          + _floor_pairs(gs, cm, hm, _QUO_LC_L, _QUO_LC, QUO_LC_LO, QUO_LC_HI, 24, QUO_MAX) \
          + _floor_pairs(gs, cm, hm, _QUO_LC, _QUO_L + _QUO_LC_L, QUO_LC_LO, QUO_LC_HI, QUO_GAP_REV, QUO_MAX) \
          + _tuck_pairs(gs, cm, hm, _QUO_APOS[:2], _CYR + _LAT) \
          + _tuck_pairs(gs, cm, hm, _QUO_APOS[2:], _CYR + _LAT) \
          + _floor_pairs(gs, cm, hm, _CYR_FL_CAPS, _CYR_FL_LOW, CFL_LO, CFL_HI, CFL_GAP, CFL_MAX)
    # one value per pair: the passes are listed collision-avoiders first, so if a tuck (negative) and a floor
    # (positive) ever both speak for the same pair, the floor wins (feaLib would otherwise reject the duplicate)
    seen = set(); uniq = []
    for a, b, k in pairs:
        if (a, b) not in seen: seen.add((a, b)); uniq.append((a, b, k))
    pairs = uniq
    # register the feature under both scripts (+ default), so shapers that look up `cyrl`/`latn`
    # apply it — not just those that fall back to DFLT
    fea = ("languagesystem DFLT dflt;\nlanguagesystem latn dflt;\nlanguagesystem cyrl dflt;\n"
           + extra_fea +
           "feature kern {\n" + "".join(f"  pos {a} {b} {k};\n" for a, b, k in pairs) + "} kern;\n")
    addOpenTypeFeaturesFromString(f, fea); f.save(otf_path)
    return len(pairs)
