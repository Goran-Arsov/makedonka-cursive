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

# Uppercase spacing kern (v0.9.17): the ornate caps have x-height-band sidebearings, so a
# following capital tucks fully under the previous cap's flourish and all-caps is unreadable.
# Push each cap->cap DENSE-BODY gap up to CAP_GAP (the specimen's even-body-spacing target);
# flourishes still cross. It fires ONLY capital-before-capital, so the approved capital->lowercase
# tuck-under is untouched. Positive-only — it never tightens, so it can only fix overlap.
CAP_GAP, MIN_CAP_KERN = 300, 10
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


def _cap_body(gs, gn, lo=0.14, hi=0.86, sc=0.3):
    # dense-body left/right edge via ink-mass percentile (same method the specimen uses to space caps)
    fp=_CFP(); gs[gn].draw(fp); cts=[c for c in fp.ct if len(c)>=3]
    if not cts: return 0.0, 0.0
    xs=[x for c in cts for x,_ in c]; ys=[y for c in cts for _,y in c]
    minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
    W=max(2,int((maxx-minx)*sc)+4); H=max(2,int((maxy-miny)*sc)+4)
    im=Image.new("L",(W,H),0); d=ImageDraw.Draw(im)
    for c in cts: d.polygon([((x-minx)*sc+2,(maxy-y)*sc+2) for x,y in c], fill=255)
    col=(np.asarray(im)>0).sum(axis=0).astype(float); tot=col.sum()
    if tot<=0: return minx, maxx
    cum=np.cumsum(col)
    li=int(np.searchsorted(cum, lo*tot)); ri=int(np.searchsorted(cum, hi*tot))
    return minx+(li-2)/sc, minx+(ri-2)/sc


def _cap_pairs(gs, cm, hm, caps):
    present=[c for c in caps if ord(c) in cm]
    BL={}; BR={}; A={}
    for c in present:
        gn=cm[ord(c)]; BL[c],BR[c]=_cap_body(gs,gn); A[c]=hm[gn][0]
    out=[]
    for a in present:
        for b in present:
            gap0 = A[a] + BL[b] - BR[a]          # natural body gap if b sits at a's advance
            k = int(round(CAP_GAP - gap0))        # positive-only: only loosen overlapping caps
            if k >= MIN_CAP_KERN:
                out.append((cm[ord(a)], cm[ord(b)], k))
    return out


def add_kern(otf_path):
    f = TTFont(otf_path); gs = f.getGlyphSet(); cm = f.getBestCmap(); hm = f["hmtx"]
    pairs = _pairs(gs, cm, hm, _CYR) + _pairs(gs, cm, hm, _LAT) \
          + _cap_pairs(gs, cm, hm, _CYR_CAPS) + _cap_pairs(gs, cm, hm, _LAT_CAPS)
    # register the feature under both scripts (+ default), so shapers that look up `cyrl`/`latn`
    # apply it — not just those that fall back to DFLT
    fea = ("languagesystem DFLT dflt;\nlanguagesystem latn dflt;\nlanguagesystem cyrl dflt;\n"
           "feature kern {\n" + "".join(f"  pos {a} {b} {k};\n" for a, b, k in pairs) + "} kern;\n")
    addOpenTypeFeaturesFromString(f, fea); f.save(otf_path)
    return len(pairs)
