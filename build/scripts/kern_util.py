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
from PIL import Image, ImageDraw
from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

W_LOW, W_HIGH, N_FLOOR, S_MAX, MIN_KERN = 115, 180, 14, 60, 5
_CYR = "абвгдѓежзѕијклљмнњопрстќуфхцчџшѐѝ"
_LAT = "abcdefghijklmnopqrstuvwxyz"

# Uppercase spacing kern (v0.9.17; reworked v0.9.25): the ornate caps have wildly varying flourish
# extents, so spacing by DENSE-BODY gap left the VISUAL gaps uneven and some flourishes still collided
# (and were cramped next to over-spaced pairs). Instead equalise the VISUAL INK gap: place each cap so
# its leftmost ink clears the previous cap's rightmost ink (flourishes included) by exactly CAP_VIS_GAP
# font units. This both WIDENS and TIGHTENS pairs toward one gap, but the target is positive so every
# cap->cap pair ends with real clearance — evenly distanced AND provably non-overlapping. Fires ONLY
# capital-before-capital, so the approved capital->lowercase tuck-under is untouched.
CAP_VIS_GAP, MIN_CAP_KERN = 160, 10
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


def _cap_ink(gs, gn):
    # full ink left/right extremes of a cap (flourishes included), from the flattened outline
    fp=_CFP(); gs[gn].draw(fp); cts=[c for c in fp.ct if len(c)>=2]
    if not cts: return 0.0, 0.0
    xs=[x for c in cts for x,_ in c]
    return min(xs), max(xs)


def _cap_pairs(gs, cm, hm, caps):
    present=[c for c in caps if ord(c) in cm]
    IL={}; IR={}; A={}
    for c in present:
        gn=cm[ord(c)]; IL[c],IR[c]=_cap_ink(gs,gn); A[c]=hm[gn][0]
    out=[]
    for a in present:
        for b in present:
            gap0 = A[a] + IL[b] - IR[a]           # natural VISUAL ink gap if b sits at a's advance
            k = int(round(CAP_VIS_GAP - gap0))     # equalise to CAP_VIS_GAP (widen OR tighten; target>0 => always clears)
            if abs(k) >= MIN_CAP_KERN:
                out.append((cm[ord(a)], cm[ord(b)], k))
    return out


def add_kern(otf_path, extra_fea=""):
    # `extra_fea` (e.g. the figures GSUB from features.py) is compiled in the SAME call:
    # addOpenTypeFeaturesFromString rebuilds GSUB+GPOS from the FEA it is given, so kern and
    # any other features must share one FEA or the later call wipes the earlier tables.
    f = TTFont(otf_path); gs = f.getGlyphSet(); cm = f.getBestCmap(); hm = f["hmtx"]
    pairs = _pairs(gs, cm, hm, _CYR) + _pairs(gs, cm, hm, _LAT) \
          + _cap_pairs(gs, cm, hm, _CYR_CAPS) + _cap_pairs(gs, cm, hm, _LAT_CAPS)
    # register the feature under both scripts (+ default), so shapers that look up `cyrl`/`latn`
    # apply it — not just those that fall back to DFLT
    fea = ("languagesystem DFLT dflt;\nlanguagesystem latn dflt;\nlanguagesystem cyrl dflt;\n"
           + extra_fea +
           "feature kern {\n" + "".join(f"  pos {a} {b} {k};\n" for a, b, k in pairs) + "} kern;\n")
    addOpenTypeFeaturesFromString(f, fea); f.save(otf_path)
    return len(pairs)
