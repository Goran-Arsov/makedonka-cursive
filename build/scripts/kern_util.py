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
_LAT = "abcdefghijklmnopqrstuvwxyz"

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
_CYR_CAPS = "АБВГДЃЕЖЗЅИЈКЛЉМНЊОПРСТЌУФХЦЧЏШ"
_LAT_CAPS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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


def _profiles(gs, gn):
    fp = _FP(); gs[gn].draw(fp); R = {}; L = {}
    for x, y in fp.pts:
        if 0 <= y < 270:
            b = int(y // 6); R[b] = max(R.get(b, -1e9), x); L[b] = min(L.get(b, 1e9), x)
    return R, L


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
          + _cap_pairs(pilfont, cm, hm, _CYR_CAPS) + _cap_pairs(pilfont, cm, hm, _LAT_CAPS)
    # register the feature under both scripts (+ default), so shapers that look up `cyrl`/`latn`
    # apply it — not just those that fall back to DFLT
    fea = ("languagesystem DFLT dflt;\nlanguagesystem latn dflt;\nlanguagesystem cyrl dflt;\n"
           + extra_fea +
           "feature kern {\n" + "".join(f"  pos {a} {b} {k};\n" for a, b, k in pairs) + "} kern;\n")
    addOpenTypeFeaturesFromString(f, fea); f.save(otf_path)
    return len(pairs)
