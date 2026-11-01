#!/usr/bin/env python3
"""Build Makedonka Cursive: 62 traced Macedonian letters + designed digits +
punctuation. Per-glyph baseline alignment (each glyph sits on y=0 by its own
body bottom) + body-based horizontal spacing (flourishes overhang).

argv[1]=paths.json  argv[2]=OUTDIR  argv[3]=M_body (default 36)
"""
import sys, os, json, math, statistics
import numpy as np
from fontTools.misc.transform import Transform
from fontTools.svgLib.path import parse_path
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont, newTable
from PIL import Image, ImageDraw
import pathops

DATA, OUTDIR = sys.argv[1], sys.argv[2]
M_BODY = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0
BODY_TRIM = 0.07   # fraction of ink mass trimmed from each side -> that (thin) flourish overhangs
CONN_LO, CONN_HI = -25.0, 300.0   # x-height join band (relative to baseline) for side bearings
LEFT_CAP = 220.0   # max leftward ink overhang past the join band (stops caps crashing the previous word)
BODY_LSB = {0x0440, 0x0458}   # р ј: descender swings far left — anchor the LEFT sidebearing on the x-height body, not the descender
d = json.load(open(DATA))
recs = {p["i"]: p for p in d["paths"]}
UPM = 700          # smaller em => the glyphs (cap height fixed at ~700 units) fill more of it, so the
                   # font renders larger at a given point size — matching normal fonts (was 1000)

MAP = [
    ("А", 0x0410, [0]), ("а", 0x0430, [1]), ("Б", 0x0411, [2, 3]), ("б", 0x0431, [4]),
    ("В", 0x0412, [5]), ("в", 0x0432, [6]), ("Г", 0x0413, [7, 8]), ("г", 0x0433, [9, 10]),
    ("Д", 0x0414, [11]), ("д", 0x0434, [12]), ("Ѓ", 0x0403, [13, 14, 15]), ("ѓ", 0x0453, [16, 17, 18]),
    ("Е", 0x0415, [19]), ("е", 0x0435, [20]), ("Ж", 0x0416, [21]), ("ж", 0x0436, [22]),
    ("З", 0x0417, [23]), ("з", 0x0437, [24]), ("Ѕ", 0x0405, [83, 84]), ("ѕ", 0x0455, [85, 86]),
    ("И", 0x0418, [25]), ("и", 0x0438, [26]), ("Ј", 0x0408, [27]), ("ј", 0x0458, [28, 29]),
    ("К", 0x041A, [30, 31]), ("к", 0x043A, [32, 33]), ("Л", 0x041B, [34]), ("л", 0x043B, [35]),
    ("Љ", 0x0409, [36]), ("љ", 0x0459, [37]), ("М", 0x041C, [38]), ("м", 0x043C, [39]),
    ("Н", 0x041D, [40]), ("н", 0x043D, [41]), ("Њ", 0x040A, [42]), ("њ", 0x045A, [43]),
    ("О", 0x041E, [44]), ("о", 0x043E, [45]), ("П", 0x041F, [46, 47, 48]), ("п", 0x043F, [49, 50]),
    ("Р", 0x0420, [51]), ("р", 0x0440, [52]), ("С", 0x0421, [53]), ("с", 0x0441, [54]),
    ("Т", 0x0422, [55, 56, 57, 58]), ("т", 0x0442, [59, 60]), ("Ќ", 0x040C, [61, 62, 63]), ("ќ", 0x045C, [64, 65, 66]),
    ("У", 0x0423, [67]), ("у", 0x0443, [68]), ("Ф", 0x0424, [69]), ("ф", 0x0444, [70]),
    ("Х", 0x0425, [71]), ("х", 0x0445, [72]), ("Ц", 0x0426, [73]), ("ц", 0x0446, [74]),
    ("Ч", 0x0427, [75]), ("ч", 0x0447, [76]), ("Џ", 0x040F, [77, 78]), ("џ", 0x045F, [79, 80]),
    ("Ш", 0x0428, [81]), ("ш", 0x0448, [82]),
]

# Letters whose body-bottom auto-detection fails (widest ink is not at the
# baseline): align by ink-bottom + fraction of ink height instead.
#   Ј ј = top-heavy single strokes;  д = g-form with a wide descender loop.
BASEFRAC = {0x0408: 0.30, 0x0458: 0.42, 0x0434: 0.50, 0x0420: 0.0, 0x0427: 0.0,
            0x0437: 0.31,  # Ј lifted; Р,Ч rest on baseline; з given back its descender (was floating)
            0x043E: 0.015, 0x0435: 0.015, 0x0441: 0.015, 0x0447: 0.015, 0x0450: 0.015,  # о е с ч ѐ — round-body baseline mis-detect
            0x041E: 0.01}  # О (cap) dipped ~46u low (round-body issue); lifts Cyrillic О + Latin O.lat. С/Е have bottom
                           # swashes that defeat a fraction-based lift, so they're left as-is.
SCALE_OVERRIDE = {0x0424: 0.82, 0x0437: 0.76, 0x0455: 0.78}   # Ф, з, ѕ are drawn oversize in the source
EMBOLDEN = {0x0455: 9}   # ѕ reads too thin after the scale-down — restore a little weight

# ---- Н (En): flatten the crossbar + trim the top flourishes ------------------
# As traced, Н collides with К: both share the big left loop and tall left curl,
# and Н's middle crossbar rises steeply (~22°) from the left stem to the right,
# so the "crossbar-up + right-stem-down" pair reads as the arm+leg of К. Two
# edits, both applied as a weighted remap of Н's raw traced points (path idx 40)
# *before* the scale/flip transform, i.e. in paths.json coordinate space. There
# Н spans x≈1499..1697, y≈307..409 (y grows downward).
#
# 1) Crossbar flatten — push the bar's right part DOWN toward horizontal so Н
#    reads as two stems + a level bar (an H). The only ink in the gap
#    x≈1572..1612, y≈344..380 is the crossbar (left stem x≲1565, right stem
#    x≳1618), so the band isolates it. N_FLATTEN scales the downward push past
#    the left hinge; N_XOVER drives the bar's right end rightward into the stem
#    so pathops' nonzero union heals the junction into a solid merge (past
#    ~0.45 flatten a junction nub appears — keep it modest).
# 2) Flourish trim — shrink the two ornate stem-top curls toward their base
#    points (radial scale, weighted) so the top is less busy: N_TRIM_R the long
#    right swoosh (+ its counter), N_TRIM_L the left entry curl (1.0 = untouched,
#    smaller = more trimmed).
N_FLATTEN, N_XOVER = 0.40, 4.0
N_TRIM_R, N_TRIM_L = 0.50, 0.55
_BR = (1646.0, 344.0)   # base of the right-stem top flourish
_BL = (1596.0, 334.0)   # base of the left-stem top curl
def _n_body_shift(x, y):
    def ss(e0, e1, v):
        t = (v - e0) / (e1 - e0); t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        return t * t * (3 - 2 * t)
    x0, y0 = x, y                                # all weights/offsets use the ORIGINAL point
    # (1) crossbar flatten
    wy = ss(330, 344, y0) * ss(392, 380, y0)     # band of the crossbar + its stem junction
    wx = ss(1562, 1572, x0) * ss(1642, 1612, x0) # hinge at left stem; taper into right stem base
    x = x0 + N_XOVER * ss(1588, 1614, x0) * wy
    y = y0 + N_FLATTEN * max(0.0, x0 - 1572) * wx * wy
    # (2) flourish trim — radial shrink toward each base, keyed off the original point
    wR = ss(1645, 1663, x0) * ss(362, 352, y0)   # right swoosh + counter (x≳1648, y≲352)
    if wR > 0 and N_TRIM_R < 1.0:
        s = 1.0 - (1.0 - N_TRIM_R) * wR; x = _BR[0] + s * (x - _BR[0]); y = _BR[1] + s * (y - _BR[1])
    wL = ss(1593, 1575, x0) * ss(345, 333, y0)   # left entry curl (x≲1592, y≲343)
    if wL > 0 and N_TRIM_L < 1.0:
        s = 1.0 - (1.0 - N_TRIM_L) * wL; x = _BL[0] + s * (x - _BL[0]); y = _BL[1] + s * (y - _BL[1])
    return (x, y)
POINT_SHIFT = {0x041D: _n_body_shift}            # cp -> raw-space point transform

class ShiftPen:
    """Pen that remaps each point through fn (raw paths.json space) before forwarding."""
    def __init__(self, target, fn): self.t, self.fn = target, fn
    def moveTo(self, p): self.t.moveTo(self.fn(*p))
    def lineTo(self, p): self.t.lineTo(self.fn(*p))
    def curveTo(self, *pts): self.t.curveTo(*[self.fn(*q) for q in pts])
    def qCurveTo(self, *pts): self.t.qCurveTo(*[self.fn(*q) for q in pts])
    def closePath(self): self.t.closePath()
    def endPath(self):
        try: self.t.endPath()
        except AttributeError: pass
    def addComponent(self, *a, **k): pass

S = 700.0 / statistics.median([max(recs[i]["h"] for i in idxs) for nm, cp, idxs in MAP if nm.isupper()])
print(f"scale S={S:.4f}  M_body={M_BODY}")

# ========================= stroke geometry (digits) =========================
def _area(pts):
    return sum(pts[i][0]*pts[(i+1) % len(pts)][1] - pts[(i+1) % len(pts)][0]*pts[i][1] for i in range(len(pts))) / 2.0
def _emit(pen, pts, ccw=True):
    if len(pts) < 3:
        return
    if (_area(pts) < 0) == ccw:
        pts = pts[::-1]
    pen.moveTo(pts[0]); [pen.lineTo(q) for q in pts[1:]]; pen.closePath()
def _sample(segs, step=None):
    # uniform ~step-spaced points along every segment (lines too) so the disk
    # brush always overlaps, even on thin hairlines. step scales with _WT so a
    # weight-thinned ribbon's smaller disks still overlap (no dotted gaps).
    if step is None:
        step = max(2.0, 6.0 * _WT)
    pts = []; cur = None
    for s in segs:
        if s[0] == 'M':
            cur = s[1]; pts.append(cur)
        elif s[0] == 'L':
            p0, p1 = cur, s[1]; d = math.hypot(p1[0]-p0[0], p1[1]-p0[1]); k = max(1, int(d/step))
            for j in range(1, k + 1):
                t = j/k; pts.append((p0[0]+(p1[0]-p0[0])*t, p0[1]+(p1[1]-p0[1])*t))
            cur = p1
        elif s[0] == 'C':
            p0, c1, c2, p1 = cur, s[1], s[2], s[3]
            d = math.hypot(c1[0]-p0[0], c1[1]-p0[1]) + math.hypot(c2[0]-c1[0], c2[1]-c1[1]) + math.hypot(p1[0]-c2[0], p1[1]-c2[1])
            k = max(8, int(d/step))
            for j in range(1, k + 1):
                t = j/k; mt = 1-t
                pts.append((mt**3*p0[0]+3*mt**2*t*c1[0]+3*mt*t*t*c2[0]+t**3*p1[0],
                            mt**3*p0[1]+3*mt**2*t*c1[1]+3*mt*t*t*c2[1]+t**3*p1[1]))
            cur = p1
    return pts
WMAX_SCALE, WMIN_SCALE = 0.78, 0.55
# --- per-category typographic-colour weight (v0.9.26) ---
# The disk-brush digits/symbols/drawn-Latin rendered heavier (darker typographic colour) than the
# traced Cyrillic body — measured mean stroke width ~2.4x (digits), ~1.8x (math symbols), ~1.3x
# (drawn Latin) the Cyrillic. `_WT` scales every disk-brush RADIUS so each category matches the
# Cyrillic colour; it is set per category around that category's build (1.0 = unchanged). Traced
# Cyrillic never touches the disk brush, so it is the fixed reference and is unaffected.
_WT = 1.0
DIGIT_WT, LAT_WT = 0.45, 0.70
# Symbols/punct come in two weight tiers: heavy geometric marks (math operators, bars, dots, dashes —
# originally ~1.7-2.0x the Cyrillic) thin hard; the mild ribbon punctuation (quotes, commas, !, ?, …
# ~1.1-1.5x) thins gently so it isn't over-lightened.
SYM_HEAVY_WT, SYM_MILD_WT = 0.55, 0.80
SYM_HEAVY = {0x002B, 0x2212, 0x003D, 0x00D7, 0x00F7, 0x003C, 0x003E, 0x00B1, 0x2116, 0x0023, 0x007C,
             0x002E, 0x003A, 0x2026, 0x00B7, 0x002D, 0x2013, 0x2014}
def _disk(pen, cx, cy, r, n=16):
    # a filled polygon disk; circles never fold/flip winding, so unioning a trail
    # of them along a centerline always fills solid (no slivers / no counters mid-stroke).
    r *= _WT
    _emit(pen, [(cx + r*math.cos(2*math.pi*j/n), cy + r*math.sin(2*math.pi*j/n)) for j in range(n)], ccw=True)
def ribbon_open(pen, segs, maxw=96, minw=24):
    maxw *= WMAX_SCALE; minw *= WMIN_SCALE
    pts = _sample(segs); m = len(pts)
    for i, p in enumerate(pts):
        a = pts[max(0, i-1)]; b = pts[min(m-1, i+1)]
        dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy) or 1.0
        ty = dy/L; down = max(0.0, -ty); wgt = 0.30*abs(ty)+0.70*down
        _disk(pen, p[0], p[1], (minw+(maxw-minw)*wgt)/2)
def ribbon_oval(pen, cx, cy, rx, ry, maxw=92, minw=30, n=140):
    maxw *= WMAX_SCALE; minw *= WMIN_SCALE
    n = int(round(n * max(1.0, 1.0 / _WT)))   # more disks when thinned, so the oval stays solid
    pts = [(cx+rx*math.cos(2*math.pi*i/n), cy+ry*math.sin(2*math.pi*i/n)) for i in range(n)]
    for i in range(n):
        a = pts[(i-1) % n]; b = pts[(i+1) % n]; dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy) or 1.0
        _disk(pen, pts[i][0], pts[i][1], (minw+(maxw-minw)*abs(dy/L))/2)
# ---- calligraphic strokes for punctuation (reuse the digit disk-brush) ----
# drawn-Latin weight bump — active ONLY while building the drawn Latin glyphs
# (digits/punctuation share these strokers, so they stay byte-identical):
LW_DMAX, LW_DMIN, LW_P0, LW_P1 = 1.25, 0.82, 0.95, 0.70
_LATIN_MODE = False
_LSX = 1.0          # per-glyph horizontal stretch of the drawn-Latin centreline (widens without re-fattening stems)
_LWT = 1.0          # per-glyph weight scale for drawn-Latin strokes (lightens dense letters)
def ribbon_dir(pen, segs, maxw, minw):
    # broad-nib ribbon weighted by stroke direction (downstrokes thickest) — like
    # ribbon_open but without the digit weight-scaling. Used for the ? hook.
    if _LATIN_MODE: maxw *= LW_DMAX * _LWT; minw *= LW_DMIN * _LWT
    pts = _sample(segs); m = len(pts)
    if _LATIN_MODE and _LSX != 1.0: pts = [(x*_LSX, y) for (x, y) in pts]
    for i, p in enumerate(pts):
        a = pts[max(0, i-1)]; b = pts[min(m-1, i+1)]
        dx, dy = b[0]-a[0], b[1]-a[1]; L = math.hypot(dx, dy) or 1.0
        ty = dy/L; down = max(0.0, -ty)
        wgt = down**1.45 if _LATIN_MODE else 0.30*abs(ty)+0.70*down   # Latin: pointed-pen contrast (thin upstrokes/horizontals)
        _disk(pen, p[0], p[1], (minw+(maxw-minw)*wgt)/2)
def ribbon_prof(pen, segs, w0, w1, gamma=1.4):
    # broad-nib ribbon with an explicit pressure taper: width w0 at the start of
    # the centreline easing to w1 at the end (a nib swelling, then lifting).
    if _LATIN_MODE: w0 *= LW_P0 * _LWT; w1 *= LW_P1 * _LWT
    pts = _sample(segs); m = len(pts)
    if _LATIN_MODE and _LSX != 1.0: pts = [(x*_LSX, y) for (x, y) in pts]
    for i, p in enumerate(pts):
        t = i/(m-1) if m > 1 else 0.0
        _disk(pen, p[0], p[1], (w1 + (w0-w1)*((1-t)**gamma))/2)
def _oval(pen, cx, cy, rx, ry, n=24):
    rx *= _WT; ry *= _WT                       # filled dots/bowls honour the per-category weight too
    _emit(pen, [(cx+rx*math.cos(2*math.pi*j/n), cy+ry*math.sin(2*math.pi*j/n)) for j in range(n)], ccw=True)
def _pencomma(pen, cx, cy, s=1.0, up=False):
    # a pointed-pen comma: swelling head tapering to a fine curved tail.
    # up=True = the raised "6" form (closing “ quote / apostrophe tops).
    sy = -1 if up else 1
    segs = [('M', (cx+8*s, cy+5*s*sy)),
            ('C', (cx+20*s, cy-42*s*sy), (cx+2*s, cy-92*s*sy), (cx-30*s, cy-130*s*sy))]
    ribbon_prof(pen, segs, 64*s, 6.0, 1.6)
T_DEG = 15.0                          # single tilt for drawn Latin, digits and punctuation (the "Make" slant)
SLANT = math.tan(math.radians(T_DEG))
DIGIT_H = 660.0          # all figures normalised to one height (lining), then slanted uniformly
def digit_path(draw_fn):
    up = pathops.Path(); draw_fn(up.getPen()); up.simplify()          # upright digit
    b = up.bounds
    if b and (b[3] - b[1]) > 1:
        s = DIGIT_H / (b[3] - b[1])
        sc = pathops.Path(); up.draw(TransformPen(sc.getPen(), (1, 0, 0, s, 0, b[1] * (1 - s)))); sc.simplify()
    else:
        sc = up
    p = pathops.Path(); sc.draw(TransformPen(p.getPen(), (1, 0, SLANT, 1, 0, 0))); p.simplify()
    b2 = p.bounds
    if b2 and abs(b2[0]) > 0.01:
        q = pathops.Path(); p.draw(TransformPen(q.getPen(), (1, 0, 0, 1, -b2[0], 0))); return q
    return p
def D0(p): ribbon_oval(p, 185, 325, 120, 300)
def D8(p): ribbon_oval(p, 188, 468, 98, 168, maxw=78, minw=26); ribbon_oval(p, 182, 165, 122, 168, maxw=92, minw=28); _disk(p, 185, 316, 40)
def D1(p):
    ribbon_open(p, [('M', (95, 455)), ('C', (150, 540), (205, 585), (220, 625)), ('C', (212, 420), (208, 210), (205, 15))], maxw=104, minw=30)
    ribbon_open(p, [('M', (120, 22)), ('L', (300, 22))], maxw=40, minw=36)
def D2(p): ribbon_open(p, [('M', (70, 500)), ('C', (120, 650), (300, 640), (278, 470)), ('C', (262, 345), (120, 225), (72, 52)), ('L', (300, 44))], maxw=100, minw=24)
def D3(p): ribbon_open(p, [('M', (78, 560)), ('C', (165, 660), (300, 605), (255, 465)), ('C', (232, 385), (150, 362), (150, 358)), ('C', (270, 360), (300, 205), (240, 95)), ('C', (195, 18), (100, 32), (72, 120))], maxw=98, minw=24)
def D4(p):
    ribbon_open(p, [('M', (238, 640)), ('L', (62, 232)), ('L', (305, 232))], maxw=86, minw=26)
    ribbon_open(p, [('M', (238, 640)), ('L', (212, 10))], maxw=100, minw=40)
def D5(p):
    ribbon_open(p, [('M', (110, 620)), ('L', (92, 408)), ('C', (160, 448), (295, 438), (272, 258)), ('C', (256, 90), (110, 52), (72, 150))], maxw=98, minw=26)
    ribbon_open(p, [('M', (112, 625)), ('L', (278, 630))], maxw=44, minw=36)
def D7(p): ribbon_open(p, [('M', (70, 622)), ('L', (305, 632)), ('C', (235, 420), (175, 210), (140, 18))], maxw=92, minw=26)
def D6(p):
    ribbon_oval(p, 178, 185, 118, 168, maxw=96, minw=28)
    ribbon_open(p, [('M', (262, 600)), ('C', (150, 645), (66, 480), (78, 250))], maxw=86, minw=24)
def D9(p):
    ribbon_oval(p, 196, 455, 112, 150, maxw=92, minw=28)
    ribbon_open(p, [('M', (300, 455)), ('C', (296, 250), (235, 110), (105, 20))], maxw=86, minw=24)
DIGITS = [("0", 0x30, D0), ("1", 0x31, D1), ("2", 0x32, D2), ("3", 0x33, D3), ("4", 0x34, D4),
          ("5", 0x35, D5), ("6", 0x36, D6), ("7", 0x37, D7), ("8", 0x38, D8), ("9", 0x39, D9)]

# ========================= raw glyph paths =========================
def embolden(path, d):
    # faux-bold: union the outline with copies nudged in 8 directions (~d weight).
    out = pathops.Path(); pen = out.getPen(); path.draw(pen)
    for dx, dy in [(d, 0), (-d, 0), (0, d), (0, -d), (0.7*d, 0.7*d), (-0.7*d, -0.7*d), (0.7*d, -0.7*d), (-0.7*d, 0.7*d)]:
        path.draw(TransformPen(pen, (1, 0, 0, 1, dx, dy)))
    out.simplify()
    return out

def letter_path(idxs, cp):
    k = SCALE_OVERRIDE.get(cp, 1.0)
    shift = POINT_SHIFT.get(cp)
    p = pathops.Path(); pen = p.getPen()
    for i in idxs:
        total = Transform(S * k, 0, 0, -S * k, 0, 0).transform(tuple(recs[i]["matrix"]))  # scale + flip y
        tpen = TransformPen(pen, tuple(total))
        parse_path(recs[i]["d"], ShiftPen(tpen, shift) if shift else tpen)
    p.simplify()
    if cp in EMBOLDEN:
        p = embolden(p, EMBOLDEN[cp])
    return p

def gname(cp):
    return "uni%04X" % cp if cp > 0x40 else {0x30: "zero", 0x31: "one", 0x32: "two", 0x33: "three",
        0x34: "four", 0x35: "five", 0x36: "six", 0x37: "seven", 0x38: "eight", 0x39: "nine"}[cp]

NEUT = [(gname(cp), cp, letter_path(idxs, cp)) for nm, cp, idxs in MAP]
_WT = DIGIT_WT                      # digits are disk-brush drawn — thin them to the Cyrillic colour
NEUT += [(gname(cp), cp, digit_path(fn)) for ch, cp, fn in DIGITS]
_WT = 1.0

# ========================= measurement (flatten + raster) =========================
class FlattenPen:
    def __init__(self, steps=10):
        self.steps = steps; self.contours = []; self._c = None; self._p = (0, 0)
    def moveTo(self, p): self._c = [p]; self._p = p
    def lineTo(self, p): self._c.append(p); self._p = p
    def curveTo(self, *pts):
        c1, c2, e = pts[-3], pts[-2], pts[-1]; p0 = self._p
        for i in range(1, self.steps+1):
            t = i/self.steps; mt = 1-t
            self._c.append((mt**3*p0[0]+3*mt**2*t*c1[0]+3*mt*t*t*c2[0]+t**3*e[0],
                            mt**3*p0[1]+3*mt**2*t*c1[1]+3*mt*t*t*c2[1]+t**3*e[1]))
        self._p = e
    def qCurveTo(self, *pts):
        pts = list(pts); on = pts[-1]; offs = pts[:-1]; prev = self._p
        for j, c in enumerate(offs):
            nxt = on if j == len(offs)-1 else ((c[0]+offs[j+1][0])/2, (c[1]+offs[j+1][1])/2)
            for i in range(1, self.steps+1):
                t = i/self.steps; mt = 1-t
                self._c.append((mt*mt*prev[0]+2*mt*t*c[0]+t*t*nxt[0], mt*mt*prev[1]+2*mt*t*c[1]+t*t*nxt[1]))
            prev = nxt
        self._p = on
    def closePath(self):
        if self._c: self.contours.append(self._c); self._c = None
    def endPath(self): self.closePath()
    def addComponent(self, *a, **k): pass

def measure(path, cp, body_thresh=130, base_frac=0.40, sc=0.3):
    fp = FlattenPen(); path.draw(fp)
    cts = [c for c in fp.contours if len(c) >= 3]
    if not cts:
        return 0, 0, 0, 0, 0
    xs = [x for c in cts for x, y in c]; yso = [y for c in cts for x, y in c]
    minx, maxx, miny, maxy = min(xs), max(xs), min(yso), max(yso)
    W = max(2, int((maxx-minx)*sc)+4); H = max(2, int((maxy-miny)*sc)+4)
    img = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(img)
    for c in cts:
        dr.polygon([((x-minx)*sc+2, (maxy-y)*sc+2) for x, y in c], fill=255)
    arr = np.asarray(img) > 0
    # horizontal body via ink-MASS percentile: trim the low-mass (thin flourish)
    # tails on each side so they overhang into neighbours. Height-based detection
    # wrongly counts a capital's tall thin flourishes as body and inflates spacing.
    colmass = arr.sum(axis=0).astype(float)
    total = colmass.sum()
    if total > 0:
        cum = np.cumsum(colmass)
        li = int(np.searchsorted(cum, BODY_TRIM * total))
        ri = int(np.searchsorted(cum, (1.0 - BODY_TRIM) * total))
        bl = minx + (li - 2) / sc
        br = minx + (max(ri, li) - 2) / sc
    else:
        bl, br = minx, maxx
    # baseline: lowest font-y row (largest raster row) whose horizontal ink extent is wide
    cidx = np.arange(arr.shape[1])[None, :]
    rowany = arr.any(axis=1)
    hext = np.where(rowany, np.where(arr, cidx, -1).max(axis=1) - np.where(arr, cidx, arr.shape[1]).min(axis=1), 0)
    thr = base_frac * (hext.max() or 1)
    wide = np.where(hext >= thr)[0]
    base_row = int(wide.max()) if len(wide) else arr.shape[0]-1
    baseline_y = maxy - (base_row-2)/sc
    if cp in BASEFRAC:                       # manual fraction for detector-failing letters
        baseline_y = miny + BASEFRAC[cp]*(maxy-miny)
    elif 0x30 <= cp <= 0x39:                 # digits: designed; align by ink bottom
        baseline_y = miny
    # connection-band side bearings: space letters by their ink in the x-height
    # join zone, so neighbours meet where cursive actually connects (not under a
    # capital's tall flourishes or the ј descender/dot). Letters only, not digits.
    if not (0x30 <= cp <= 0x39):
        r_top = int(round((maxy - (baseline_y + CONN_HI)) * sc + 2))
        r_bot = int(round((maxy - (baseline_y + CONN_LO)) * sc + 2))
        r_top = max(0, r_top); r_bot = min(arr.shape[0], r_bot)
        if r_bot - r_top >= 2:
            bcols = arr[r_top:r_bot, :].any(axis=0)
            if bcols.any():
                xi = np.where(bcols)[0]
                bl = minx + (xi.min() - 2) / sc
                br = minx + (xi.max() - 2) / sc
    return minx, maxx, bl, br, baseline_y

# ========================= assemble glyphs =========================
glyph_order = [".notdef", "space"]; charstrings = {}; metrics = {}; cmap = {0x20: "space"}
base_paths = {}          # positioned digit outlines, kept for the figure features (features.py)
gy_min, gy_max = 1e9, -1e9
nd = T2CharStringPen(600, None)
nd.moveTo((60, 0)); nd.lineTo((540, 0)); nd.lineTo((540, 700)); nd.lineTo((60, 700)); nd.closePath()
charstrings[".notdef"] = nd.getCharString(); metrics[".notdef"] = (600, 60)
charstrings["space"] = T2CharStringPen(300, None).getCharString(); metrics["space"] = (300, 0)

# Macedonian accented letters: ѐ (е + grave) and ѝ (и + grave) — base trace + a calligraphic grave accent.
def _grave(pen, cx, cy, s=1.0):   # short pen grave `, thick→thin, descending left→right, centred ~(cx, cy); s scales it
    ribbon_dir(pen, [('M',(cx-28*s,cy+26*s)),('C',(cx-10*s,cy+9*s),(cx+8*s,cy-9*s),(cx+26*s,cy-28*s))], 43.7*s, 13.3*s)
def _caron(pen, cx, cy, s=1.0):   # ˇ — a calligraphic check (š č ž Š Č Ž)
    ribbon_prof(pen, [('M', (cx-30*s, cy+20*s)), ('L', (cx-2*s, cy-16*s)), ('L', (cx+30*s, cy+20*s))], 36*s, 18*s, 1.2)
def _acute(pen, cx, cy, s=1.0):   # ´ — a short rising pen stroke (ć Ć)
    ribbon_prof(pen, [('M', (cx-16*s, cy-18*s)), ('L', (cx+20*s, cy+22*s))], 44*s, 14*s, 1.4)
_accsrc = {cpx: pth for (gnx, cpx, pth) in NEUT}
for _anm, _acp, _ascp, _agx, _agy in [("uni0450",0x0450,0x0435,8,330),("uni045D",0x045D,0x0438,16,330)]:
    _ab = _accsrc[_ascp]; _am = measure(_ab, _ascp); _acx = (_am[0]+_am[1])/2 + _agx
    _ap = pathops.Path(); _ab.draw(_ap.getPen()); _grave(_ap.getPen(), _acx, _am[4]+_agy); _ap.simplify()
    NEUT.append((_anm, _acp, _ap))
# Uppercase Ѐ/Ѝ (U+0400/U+040D): cap Е/И + a larger grave above the cap body (~680), for all-caps case pairs
for _anm, _acp, _ascp, _agx, _agy in [("uni0400",0x0400,0x0415,6,748),("uni040D",0x040D,0x0418,14,748)]:
    _ab = _accsrc[_ascp]; _am = measure(_ab, _ascp); _acx = (_am[0]+_am[1])/2 + _agx
    _ap = pathops.Path(); _ab.draw(_ap.getPen()); _grave(_ap.getPen(), _acx, _am[4]+_agy, 1.3); _ap.simplify()
    NEUT.append((_anm, _acp, _ap))

for g, cp, path in NEUT:
    glyph_order.append(g); cmap[cp] = g
    minx, maxx, bl, br, basey = measure(path, cp)
    if cp in (0x0448, 0x0428):               # Macedonian cursive ш/Ш: underline beneath the letter — its ends
        _fL, _fR = {0x0448: (0.00, 0.60), 0x0428: (0.205, 0.659)}[cp]   # track the first/last stroke, not the flourishes
        _w = maxx - minx; _xL = minx + _fL*_w; _xR = minx + _fR*_w
        _dy = basey - 60; _th = 28
        _dp = path.getPen()
        _dp.moveTo((_xL, _dy - _th/2)); _dp.lineTo((_xR, _dy - _th/2))
        _dp.lineTo((_xR, _dy + _th/2)); _dp.lineTo((_xL, _dy + _th/2)); _dp.closePath()
        path.simplify()
    if cp in BODY_LSB:                       # р ј: far-left descender — base the LEFT sidebearing on the x-height
        _fp = FlattenPen(); path.draw(_fp)   # body (above the baseline) so the body sits centred, descender trails left
        _bx = [x for c in _fp.contours for (x, y) in c if basey + 25 <= y <= basey + CONN_HI]
        if _bx: bl = min(_bx)
    else:
        bl = min(bl, minx + LEFT_CAP)        # cap leftward overhang (fixes offset-bottom caps like Ч)
    hshift = M_BODY - bl
    vshift = -basey
    adv = int(round((br - bl) + 2 * M_BODY))
    t2 = T2CharStringPen(adv, None)
    path.draw(TransformPen(t2, (1, 0, 0, 1, hshift, vshift)))
    charstrings[g] = t2.getCharString()
    if 0x30 <= cp <= 0x39:                   # keep the positioned digit outline for the figure features
        _bp = pathops.Path(); path.draw(TransformPen(_bp.getPen(), (1, 0, 0, 1, hshift, vshift))); base_paths[g] = _bp
    metrics[g] = (adv, int(round(minx + hshift)))
    b = path.bounds
    if b:
        gy_min = min(gy_min, b[1] + vshift); gy_max = max(gy_max, b[3] + vshift)

ascent = int(math.ceil(gy_max)) + 20
descent = int(math.floor(gy_min)) - 20
print(f"letters+digits={len(NEUT)}  y {gy_min:.0f}..{gy_max:.0f}  ascent={ascent} descent={descent}")

# ---- punctuation (fixed widths, baseline 0) ----
def _circle(pen, cx, cy, r):
    k = 0.5523*r
    pen.moveTo((cx+r, cy)); pen.curveTo((cx+r, cy+k), (cx+k, cy+r), (cx, cy+r)); pen.curveTo((cx-k, cy+r), (cx-r, cy+k), (cx-r, cy))
    pen.curveTo((cx-r, cy-k), (cx-k, cy-r), (cx, cy-r)); pen.curveTo((cx+k, cy-r), (cx+r, cy-k), (cx+r, cy)); pen.closePath()
def _rect(pen, x0, y0, x1, y1):
    if _WT != 1.0:                             # thin the bar's NARROW dimension toward its centre
        w, h = x1 - x0, y1 - y0
        if abs(w) < abs(h):
            c = (x0 + x1) / 2.0; x0, x1 = c - w*_WT/2.0, c + w*_WT/2.0
        else:
            c = (y0 + y1) / 2.0; y0, y1 = c - h*_WT/2.0, c + h*_WT/2.0
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
def _poly(pen, pts): pen.moveTo(pts[0]); [pen.lineTo(q) for q in pts[1:]]; pen.closePath()
def _ring(pen, cx, cy, R, r, n=48):
    # a hollow ring (° and %): outer CCW + inner CW so nonzero winding leaves the hole
    if _WT != 1.0:                             # thin the ring band toward its mean radius
        m = (R + r) / 2.0; half = (R - r) * _WT / 2.0; R, r = m + half, m - half
    _emit(pen, [(cx+R*math.cos(2*math.pi*j/n), cy+R*math.sin(2*math.pi*j/n)) for j in range(n)], ccw=True)
    _emit(pen, [(cx+r*math.cos(2*math.pi*j/n), cy+r*math.sin(2*math.pi*j/n)) for j in range(n)], ccw=False)
def _paren(pen, width, left=True):
    x0 = width*0.60 if left else width*0.40; s = 1 if left else -1; top, bot = 720, -150
    pen.moveTo((x0, top)); pen.curveTo((x0-s*185, top-300), (x0-s*185, bot+300), (x0, bot))
    pen.curveTo((x0-s*140, bot+300), (x0-s*140, top-300), (x0, top)); pen.closePath()
def _make(fn, width):
    # draw upright, slant to the 18° italic, then centre the ink in the advance.
    p = pathops.Path(); fn(p.getPen()); p.simplify()
    sl = pathops.Path(); p.draw(TransformPen(sl.getPen(), (1, 0, SLANT, 1, 0, 0))); sl.simplify()
    b = sl.bounds
    if not b:
        return T2CharStringPen(width, None).getCharString(), 0
    dx = width/2.0 - (b[0]+b[2])/2.0
    out = pathops.Path(); sl.draw(TransformPen(out.getPen(), (1, 0, 0, 1, dx, 0))); out.simplify()
    t2 = T2CharStringPen(width, None); out.draw(t2); ob = out.bounds
    return t2.getCharString(), int(round(ob[0])) if ob else 0
# ---- v0.9.22 symbol helpers (drawn upright; _make slants + centres) ----
def _asterisk(pen, cx, cy, r, n=6):
    for k in range(n):
        a = math.pi/2 + k*2*math.pi/n
        ribbon_prof(pen, [('M', (cx, cy)), ('L', (cx+r*math.cos(a), cy+r*math.sin(a)))], 28, 13)
def _brace(pen, left=True):
    s = 1 if left else -1; x = 150        # sharper inward cusp at mid-height so it reads as a brace, not a paren
    ribbon_prof(pen, [('M', (x+s*74, 702)), ('C', (x+s*30, 650), (x+s*18, 452), (x-s*40, 322))], 27, 27)
    ribbon_prof(pen, [('M', (x-s*40, 322)), ('C', (x+s*18, 192), (x+s*30, -6), (x+s*74, -58))], 27, 27)
def _numero(pen):   # № : an upright N, a raised small ring (o), and its underline
    ribbon_prof(pen, [('M', (44, 24)), ('L', (44, 500))], 48, 48)
    ribbon_prof(pen, [('M', (44, 500)), ('L', (232, 24))], 42, 42)
    ribbon_prof(pen, [('M', (232, 24)), ('L', (232, 500))], 48, 48)
    _ring(pen, 338, 432, 72, 36); _rect(pen, 270, 352, 406, 392)
def _dollar(pen):   # $ : an S stroke with a vertical bar through it
    ribbon_dir(pen, [('M', (268, 486)), ('C', (210, 548), (74, 540), (86, 446)), ('C', (98, 384), (232, 372), (252, 300)),
                     ('C', (274, 214), (150, 150), (78, 214))], 44, 15)
    _rect(pen, 156, 86, 194, 600)
def _copyright(pen):   # © : a small c inside a ring
    _ring(pen, 185, 320, 182, 150)
    ribbon_dir(pen, [('M', (252, 392)), ('C', (150, 432), (110, 360), (118, 320)), ('C', (126, 272), (168, 212), (252, 250))], 24, 12)
def _at(pen):   # @ : a small 'a' inside a ring open at lower-right
    ribbon_dir(pen, [('M', (300, 206)), ('C', (258, 116), (110, 112), (90, 252)), ('C', (72, 392), (152, 498), (272, 470)),
                     ('C', (322, 458), (344, 414), (336, 352))], 32, 20)
    _ring(pen, 196, 300, 76, 40); _rect(pen, 256, 236, 288, 360)
# (& ampersand deferred: the et-ligature doesn't read cleanly from hand-tuned Béziers — a wrong
#  glyph at U+0026 is worse than none; it wants a careful drawn pass in a font editor.)
# Calligraphic set: dots are slanted ovals, comma/quotes are pen-commas, ! and ?
# are tapered/direction-weighted ribbons; every mark is slanted 18° in _make. In
# colon/semicolon the upper dot is pre-shifted by −SLANT·Δy so it stacks truly
# vertical once slanted (an italic colon shouldn't lean apart).
PUNCT = [
    (0x002E, "period", 150, lambda p: _oval(p, 75, 48, 35, 41)),
    (0x002C, "comma", 150, lambda p: _pencomma(p, 85, 92)),
    (0x003A, "colon", 160, lambda p: (_oval(p, 80, 48, 33, 38), _oval(p, 80 - SLANT*252, 300, 33, 38))),
    (0x003B, "semicolon", 160, lambda p: (_oval(p, 93 - SLANT*203, 300, 33, 38), _pencomma(p, 85, 92))),
    # ! and ? : ~30% shorter and lighter in colour (thinner ribbons + smaller dots).
    (0x0021, "exclam", 180, lambda p: (ribbon_prof(p, [('M', (80, 483)), ('C', (78, 350), (76, 224), (74, 118))], 64, 17, 1.2), _oval(p, 70, 46, 28, 30))),
    (0x003F, "question", 320, lambda p: (ribbon_dir(p, [('M', (92, 364)), ('C', (92, 490), (248, 490), (240, 382)), ('C', (234, 319), (168, 316), (165, 252)), ('C', (162, 224), (160, 210), (158, 175))], 44, 11), _oval(p, 150, 46, 27, 29))),
    (0x002D, "hyphen", 260, lambda p: _rect(p, 40, 250, 230, 305)), (0x2013, "endash", 460, lambda p: _rect(p, 40, 258, 420, 300)),
    (0x2014, "emdash", 720, lambda p: _rect(p, 40, 258, 680, 300)), (0x0028, "parenleft", 300, lambda p: _paren(p, 300, True)),
    (0x0029, "parenright", 300, lambda p: _paren(p, 300, False)), (0x0027, "quotesingle", 190, lambda p: _pencomma(p, 90, 648, 0.95)),
    (0x0022, "quotedbl", 320, lambda p: (_pencomma(p, 95, 648, 0.95), _pencomma(p, 205, 648, 0.95))),
    (0x201E, "quotedblbase", 330, lambda p: (_pencomma(p, 100, 120), _pencomma(p, 212, 120))),   # „ low opening (9-form)
    (0x201C, "quotedblleft", 330, lambda p: (_pencomma(p, 100, 560, 1.0, True), _pencomma(p, 212, 560, 1.0, True))),  # “ raised 6-form (opening)
    (0x201D, "quotedblright", 330, lambda p: (_pencomma(p, 100, 560, 1.0), _pencomma(p, 212, 560, 1.0))),             # ” raised 9-form (Latin closing — both marks UP)
    (0x2018, "quoteleft", 180, lambda p: _pencomma(p, 100, 560, 1.0, True)),                                           # ‘ single raised 6-form
    (0x2019, "quoteright", 180, lambda p: _pencomma(p, 100, 560, 1.0)),                                                # ’ single raised 9-form (= apostrophe, up)
    # ---- v0.9.16: fill real coverage gaps, reusing the calligraphic pen primitives above ----
    (0x002F, "slash", 300, lambda p: ribbon_prof(p, [('M', (74, -46)), ('L', (150, 586))], 40, 40)),                   # / solidus (dates, fractions, URLs)
    (0x2026, "ellipsis", 470, lambda p: (_oval(p, 75, 48, 35, 41), _oval(p, 225, 48, 35, 41), _oval(p, 375, 48, 35, 41))),  # … three baseline dots = period×3
    (0x00B7, "periodcentered", 150, lambda p: _oval(p, 75, 132, 35, 41)),                                              # · middle dot = period raised to mid x-height
    (0x00AB, "guillemotleft", 310, lambda p: (ribbon_prof(p, [('M', (124, 232)), ('L', (48, 130)), ('L', (124, 28))], 26, 26), ribbon_prof(p, [('M', (236, 232)), ('L', (160, 130)), ('L', (236, 28))], 26, 26))),  # « Macedonian 2ndary quote
    (0x00BB, "guillemotright", 310, lambda p: (ribbon_prof(p, [('M', (48, 232)), ('L', (124, 130)), ('L', (48, 28))], 26, 26), ribbon_prof(p, [('M', (160, 232)), ('L', (236, 130)), ('L', (160, 28))], 26, 26))),  # »
    (0x00B0, "degree", 210, lambda p: _ring(p, 98, 470, 62, 34)),                                                      # ° small ring near figure top
    (0x0025, "percent", 480, lambda p: (_ring(p, 104, 500, 58, 31), _ring(p, 338, 120, 58, 31), ribbon_prof(p, [('M', (74, 18)), ('L', (368, 600))], 34, 34))),  # % two rings + stroke
    # ---- v0.9.22: math operators + ASCII tech symbols + № numero ----
    (0x002B, "plus", 360, lambda p: (_rect(p, 52, 272, 308, 328), _rect(p, 152, 180, 208, 420))),
    (0x2212, "minus", 360, lambda p: _rect(p, 52, 272, 308, 328)),
    (0x003D, "equal", 360, lambda p: (_rect(p, 52, 236, 308, 288), _rect(p, 52, 318, 308, 370))),
    (0x00D7, "multiply", 340, lambda p: (ribbon_prof(p, [('M', (84, 196)), ('L', (256, 404))], 42, 42), ribbon_prof(p, [('M', (256, 196)), ('L', (84, 404))], 42, 42))),
    (0x00F7, "divide", 360, lambda p: (_rect(p, 52, 272, 308, 328), _oval(p, 180, 398, 31, 34), _oval(p, 180, 202, 31, 34))),
    (0x003C, "less", 330, lambda p: ribbon_prof(p, [('M', (266, 172)), ('L', (72, 300)), ('L', (266, 428))], 40, 40)),
    (0x003E, "greater", 330, lambda p: ribbon_prof(p, [('M', (64, 172)), ('L', (258, 300)), ('L', (64, 428))], 40, 40)),
    (0x00B1, "plusminus", 360, lambda p: (_rect(p, 152, 250, 208, 470), _rect(p, 52, 332, 308, 388), _rect(p, 52, 150, 308, 206))),
    (0x002A, "asterisk", 300, lambda p: _asterisk(p, 150, 486, 92)),
    (0x0023, "numbersign", 420, lambda p: (_rect(p, 128, 120, 172, 540), _rect(p, 258, 120, 302, 540), _rect(p, 58, 238, 372, 286), _rect(p, 58, 372, 372, 420))),
    (0x005F, "underscore", 360, lambda p: _rect(p, 20, -66, 340, -12)),
    (0x007C, "bar", 240, lambda p: _rect(p, 96, -140, 150, 620)),
    (0x007E, "asciitilde", 360, lambda p: ribbon_prof(p, [('M', (46, 286)), ('C', (96, 346), (150, 346), (194, 302)), ('C', (236, 262), (286, 262), (318, 314))], 30, 30)),
    (0x005C, "backslash", 300, lambda p: ribbon_prof(p, [('M', (74, 586)), ('L', (226, -46))], 40, 40)),
    (0x005E, "asciicircum", 340, lambda p: ribbon_prof(p, [('M', (72, 468)), ('L', (170, 624)), ('L', (268, 468))], 36, 36)),
    (0x005B, "bracketleft", 230, lambda p: _poly(p, [(66, -78), (196, -78), (196, -26), (120, -26), (120, 646), (196, 646), (196, 698), (66, 698)])),
    (0x005D, "bracketright", 230, lambda p: _poly(p, [(164, -78), (34, -78), (34, -26), (110, -26), (110, 646), (34, 646), (34, 698), (164, 698)])),
    (0x007B, "braceleft", 280, lambda p: _brace(p, True)),
    (0x007D, "braceright", 280, lambda p: _brace(p, False)),
    (0x2116, "numero", 470, _numero),
    # ---- v0.9.23: ornamental symbols + per-mille + primes ----
    (0x0040, "at", 440, _at),
    (0x0024, "dollar", 340, _dollar),
    (0x00A9, "copyright", 440, _copyright),
    (0x2030, "permille", 640, lambda p: (_ring(p, 104, 500, 58, 31), _ring(p, 300, 120, 58, 31), _ring(p, 480, 120, 58, 31), ribbon_prof(p, [('M', (74, 18)), ('L', (420, 600))], 34, 34))),
    (0x2032, "prime", 160, lambda p: ribbon_prof(p, [('M', (66, 640)), ('L', (112, 456))], 44, 20)),
    (0x2033, "doubleprime", 270, lambda p: (ribbon_prof(p, [('M', (66, 640)), ('L', (112, 456))], 44, 20), ribbon_prof(p, [('M', (176, 640)), ('L', (222, 456))], 44, 20))),
]
for cp, name, width, fn in PUNCT:   # unify symbol/punct colour to the Cyrillic (two weight tiers)
    _WT = SYM_HEAVY_WT if cp in SYM_HEAVY else SYM_MILD_WT
    cs, xmin = _make(fn, width); glyph_order.append(name); cmap[cp] = name; charstrings[name] = cs; metrics[name] = (width, xmin)
_WT = 1.0

# ========================= Latin =========================
# ~27 Latin letters reuse a visually identical Cyrillic glyph (homoglyphs: incl. g=д,
# u=и, m=м). The remaining 25 are drawn in the restrained pen style (a coherent
# companion to the ornate traced caps, like the digits), slanted 18° and spaced by the
# same x-height join band. Coordinates are in font units: x-height 247, ascender 553,
# cap 653, descender ~-240 (measured from the built Cyrillic — stable with the trace).
LXH, LASC, LCAP, LDESC = 247.0, 553.0, 653.0, -240.0
# per-glyph horizontal stretch for drawn letters that read too condensed (widen only, weight unchanged):
LAT_STRETCH = {"i":1.36,"t":1.25,"l":1.52,"k":1.63,"n":1.72,"h":1.73,"b":1.68,"d":1.65,"r":1.73,
               "q":1.67,"f":1.06,"v":1.80,"w":1.52,"z":1.22,
               "D":1.55,"F":1.48,"G":1.50,"I":1.35,"L":1.75,"N":1.62,"Q":1.65,"R":1.72,"U":1.78,"V":1.78,"W":1.75,"Z":1.52}
# extra side-spacing (units each side) for drawn letters that read too tight — adds whitespace, not glyph width:
LAT_SPACE = {"b":40,"h":40,"i":15,"l":40,"r":40,"t":40}   # d: none — its round bowl sits like o/e (8 each side); z: none since v0.9.34 (the symmetric z is a normal-width letter, not a narrow stem)
LAT_RSP = {"r":-38, "v":45, "d":-7}    # extra RIGHT-side space only (negative = less): r tucks closer right, v gets room after;
                                       # d's right stem slants right, so its ink edge is measured high (above x-height) — pull it back in
LAT_LSP = {"k": -6}                    # less LEFT-side space (space in front of the letter); k's ascender loop leaves optical room
CAP_H = 0.90                  # drawn caps: scale height (before slant, so the 15° tilt is kept)
CAP_SCALE = 0.89              # reused ornate caps: uniform scale (round caps lifted via BASEFRAC to match)
LAT_XCOMP = {"o.lat": 0.88}   # horizontal squeeze for specific reused copies (the Latin o read too wide/open)
# One Latin tilt: every reused Cyrillic letter becomes a copy de-skewed to the single slant SLANT.
# LAT_NAT = measured natural slant (deg) of each Cyrillic SOURCE; de-skew = tan(nat) - SLANT lands it on SLANT.
LAT_NAT = {   # v0.9.29: re-measured (projection-profile slant of each copy backed out its source's true slant)
    0x0430:29,0x0438:28,0x0440:26,0x0458:27, 0x0435:26,0x043E:21,0x0441:20,0x0434:29,  # а и р ј · е о с д  (v0.9.30: и/р less de-skew -> u/p stems match)
    0x043C:30,0x0455:25,0x0445:27,0x0443:29,                                            # м ѕ х у
    0x0410:30,0x0412:34,0x0421:26,0x0415:33,0x041D:26,0x0408:29,0x041A:33,0x041C:31,     # А В С Е Н Ј К М
    0x041E:22,0x0420:33,0x0405:30,0x0422:32,0x0425:38,0x0423:30}                         # О Р Ѕ Т Х У
def _dsk(scp): return math.tan(math.radians(LAT_NAT[scp])) - SLANT
LAT_LIGHTEN = {"h":0.84, "w":0.82, "b":0.90,            # per-glyph weight scale for the dense ones
               # drawn letters still heavier than the Cyrillic body after LAT_WT — thin to match:
               "I":0.62, "N":0.56, "L":0.70, "R":0.72, "F":0.74, "D":0.82, "Z":0.80, "U":0.84, "V":0.90,
               "i":0.82, "p":0.80, "t":0.84, "n":0.86}
def _loopasc(pen, x, top, mx=46, mn=9):
    ribbon_dir(pen, [('M',(x+4,16)),('C',(x-8,top*0.5),(x-26,top*0.88),(x+22,top)),('C',(x+56,top*1.08),(x+58,top*0.8),(x+32,top*0.70)),('C',(x+12,top*0.6),(x+18,top*0.42),(x+16,16))], mx, mn)
def _lbowl(pen, cx, cy, rx, ry):
    ribbon_prof(pen, [('M',(cx+rx*0.35,cy+ry)),('C',(cx-rx*0.9,cy+ry*0.85),(cx-rx*0.9,cy-ry*0.85),(cx+rx*0.2,cy-ry)),('C',(cx+rx*0.95,cy-ry*0.55),(cx+rx*0.95,cy+ry*0.55),(cx+rx*0.35,cy+ry))], 32, 20)
def _archright(pen, lx, rx, mx=40, mn=8):
    ribbon_dir(pen, [('M',(lx+2,LXH-2)),('C',(lx,LXH*0.5),(lx,18),(lx,14)),('C',(lx+1,LXH*0.5),(lx+2,LXH*0.86),(lx+6,LXH*0.99)),('C',(lx+22,LXH*1.07),(rx-10,LXH*1.02),(rx,LXH*0.6)),('C',(rx+1,LXH*0.33),(rx,18),(rx,14))], mx, mn)
def _L_i(p): ribbon_dir(p,[('M',(60,LXH-6)),('C',(55,LXH*0.55),(50,20),(52,14))],44,11); _oval(p,74,LXH+56,15,17)
def _L_t(p): ribbon_dir(p,[('M',(66,LASC*0.78)),('C',(56,LXH*0.55),(52,LXH*0.22),(56,18)),('C',(62,6),(84,10),(100,30))],44,12); ribbon_prof(p,[('M',(24,LXH+10)),('L',(100,LXH+2))],18,18)
def _L_l(p): _loopasc(p,62,LASC); ribbon_dir(p,[('M',(74,17)),('C',(84,0),(112,8),(140,40))],36,12)
def _L_n(p): _archright(p,42,108)
def _L_h(p): _loopasc(p,48,LASC); ribbon_dir(p,[('M',(64,14)),('C',(63,LXH*0.5),(64,LXH*0.86),(68,LXH*0.99)),('C',(84,LXH*1.07),(118,LXH*1.02),(126,LXH*0.6)),('C',(127,LXH*0.33),(126,18),(126,14))],40,8)
def _L_b(p): _loopasc(p,54,LASC); _lbowl(p,98,LXH*0.5,38,LXH*0.5)
def _L_d(p): _lbowl(p,55,LXH*0.5,50,LXH*0.5); ribbon_dir(p,[('M',(108,LASC)),('C',(104,LXH*0.6),(103,20),(104,14))],44,12)
def _L_r(p): ribbon_dir(p,[('M',(46,LXH-4)),('C',(41,LXH*0.55),(41,20),(43,14))],44,12); ribbon_dir(p,[('M',(42,LXH*0.6)),('C',(56,LXH*0.95),(84,LXH*1.0),(104,LXH*0.8))],28,9)
def _L_q(p): _lbowl(p,66,LXH*0.5,38,LXH*0.5); ribbon_dir(p,[('M',(108,LXH-2)),('C',(104,LXH*0.5),(100,-60),(98,LDESC*0.9))],44,12)
def _L_f(p): ribbon_dir(p,[('M',(66,LASC*0.55)),('C',(60,LASC*0.92),(84,LASC*1.12),(104,LASC*0.96)),('C',(120,LASC*0.82),(100,LASC*0.6),(72,LASC*0.58)),('C',(58,LASC*0.5),(54,LXH),(50,LXH*0.1)),('C',(46,-70),(34,LDESC),(14,LDESC*0.82))],44,11); ribbon_prof(p,[('M',(18,LXH+6)),('L',(96,LXH-2))],17,17)
def _L_v(p): ribbon_dir(p,[('M',(34,LXH-2)),('C',(40,LXH*0.4),(58,12),(74,16)),('C',(92,20),(102,LXH*0.55),(100,LXH-2)),('C',(104,LXH*0.78),(116,LXH*0.7),(126,LXH*0.6))],44,11)
def _L_w(p): ribbon_dir(p,[('M',(30,LXH-2)),('C',(36,LXH*0.4),(52,12),(66,16)),('C',(82,20),(88,LXH*0.5),(88,LXH-6))],44,11); ribbon_dir(p,[('M',(88,LXH-6)),('C',(90,LXH*0.4),(104,12),(118,16)),('C',(134,20),(144,LXH*0.55),(142,LXH-2)),('C',(146,LXH*0.78),(158,LXH*0.7),(168,LXH*0.6))],44,11)
def _L_z(p):   # per request: top curved hair replaced by the BOTTOM horizontal line inverted 180° on top (a small symmetric z, like the cap Z)
    ribbon_dir(p,[('M',(110,LXH*0.94)),('C',(96,LXH*0.56),(58,LXH*0.28),(44,18)),('C',(70,14),(96,20),(116,14))],44,11)   # diagonal (raised to x-height) + bottom line
    def _zbot(pen): ribbon_dir(pen,[('M',(44,18)),('C',(70,14),(96,20),(116,14))],44,11)                                   # the bottom line
    _cx, _cy = 77.0 * _LSX, (18 + LXH*0.94) / 2.0     # centre (x scaled by _LSX): rotating the bottom-line start (44,18) by 180° lands on the diagonal top (110, LXH*0.94)
    _bar = pathops.Path(); _zbot(_bar.getPen()); _bar.simplify()
    _rot = pathops.Path(); _bar.draw(TransformPen(_rot.getPen(), (-1, 0, 0, -1, 2 * _cx, 2 * _cy))); _rot.simplify()
    _rot.draw(p)                                                                                                            # top bar = bottom line rotated 180°
def _L_k(p): _loopasc(p,52,LASC); ribbon_dir(p,[('M',(132,LXH*0.98)),('C',(102,LXH*0.78),(76,LXH*0.6),(62,LXH*0.5))],30,9); ribbon_dir(p,[('M',(62,LXH*0.5)),('C',(86,LXH*0.33),(110,LXH*0.17),(138,14))],46,12)
def _U_I(p):
    ribbon_dir(p,[('M',(84,LCAP*0.96)),('C',(78,LCAP*0.5),(74,LCAP*0.2),(76,28))],56,15)                                                                              # stem
    ribbon_prof(p,[('M',(86,LCAP*0.90)),('C',(70,LCAP*1.08),(20,LCAP*1.10),(6,LCAP*0.90)),('C',(0,LCAP*0.80),(18,LCAP*0.76),(40,LCAP*0.82))],30,19)                   # top swash loop (bottom hair removed)
def _U_L(p):
    ribbon_dir(p,[('M',(70,LCAP*0.96)),('C',(58,LCAP*0.5),(50,LCAP*0.16),(56,22))],58,15)                                                                             # stem
    ribbon_prof(p,[('M',(70,LCAP*0.90)),('C',(50,LCAP*1.12),(-8,LCAP*1.15),(-32,LCAP*0.98)),('C',(-54,LCAP*0.84),(-40,LCAP*0.69),(-14,LCAP*0.70)),('C',(4,LCAP*0.71),(8,LCAP*0.82),(-6,LCAP*0.88))],30,17)   # long upper swash + small twist (like N)
    ribbon_prof(p,[('M',(56,22)),('C',(74,-8),(136,-4),(192,34)),('C',(220,52),(226,92),(204,110)),('C',(190,120),(172,113),(176,96)),('C',(179,85),(192,86),(195,95))],42,24)   # thick bottom bar + twist
def _U_D(p): ribbon_dir(p,[('M',(58,LCAP)),('C',(52,LCAP*0.5),(52,20),(56,14))],58,16); ribbon_prof(p,[('M',(60,LCAP-6)),('C',(170,LCAP*0.98),(196,LCAP*0.55),(188,LCAP*0.3)),('C',(176,LCAP*0.08),(120,14),(58,16))],30,30)
def _U_F(p):
    ribbon_dir(p,[('M',(62,LCAP*0.90)),('C',(54,LCAP*0.5),(52,LXH*0.3),(48,-30)),('C',(44,-82),(22,-112),(2,-92))],54,12)                                             # stem + descender
    ribbon_prof(p,[('M',(62,LCAP*0.84)),('C',(48,LCAP*1.04),(2,LCAP*1.08),(-10,LCAP*0.88)),('C',(-15,LCAP*0.78),(2,LCAP*0.74),(24,LCAP*0.80))],30,19)                 # top swash loop
    ribbon_prof(p,[('M',(52,LCAP-18)),('C',(112,LCAP*0.96),(160,LCAP),(202,LCAP*0.88))],26,18)                                                                       # top bar
    ribbon_prof(p,[('M',(48,LCAP*0.54)),('C',(92,LCAP*0.56),(118,LCAP*0.58),(150,LCAP*0.54))],22,16)                                                                 # mid bar
def _U_N(p):
    ribbon_dir(p,[('M',(50,LCAP*0.96)),('C',(44,LCAP*0.5),(42,18),(44,14))],54,14)                                                                                   # left stem
    ribbon_dir(p,[('M',(46,LCAP*0.94)),('C',(88,LCAP*0.60),(128,LCAP*0.34),(160,16))],56,16)                                                                         # diagonal
    ribbon_dir(p,[('M',(160,LCAP*0.94)),('C',(156,LCAP*0.5),(154,20),(156,16))],54,14)                                                                               # right stem
    ribbon_prof(p,[('M',(50,LCAP*0.90)),('C',(30,LCAP*1.12),(-28,LCAP*1.15),(-52,LCAP*0.98)),('C',(-74,LCAP*0.84),(-60,LCAP*0.69),(-34,LCAP*0.70)),('C',(-16,LCAP*0.71),(-12,LCAP*0.82),(-26,LCAP*0.88))],30,17)   # long entry swash + small twist (right hair removed)
def _U_U(p): ribbon_dir(p,[('M',(52,LCAP)),('C',(44,LCAP*0.28),(50,14),(92,11)),('C',(134,8),(168,LCAP*0.3),(160,LCAP*0.72))],58,15); ribbon_dir(p,[('M',(158,LCAP)),('C',(156,LCAP*0.6),(158,LCAP*0.75),(160,LCAP*0.72))],44,16)
def _U_V(p): ribbon_dir(p,[('M',(44,LCAP)),('C',(66,LCAP*0.5),(90,24),(100,18)),('C',(114,24),(136,LCAP*0.5),(162,LCAP))],58,13)
def _U_W(p): ribbon_dir(p,[('M',(32,LCAP)),('C',(50,LCAP*0.5),(70,22),(80,18)),('C',(92,24),(106,LCAP*0.5),(112,LCAP*0.9))],56,13); ribbon_dir(p,[('M',(112,LCAP*0.9)),('C',(118,LCAP*0.5),(132,22),(144,18)),('C',(156,24),(178,LCAP*0.5),(198,LCAP))],56,13)
def _U_Z(p):   # per request: original upper bar removed; the top bar is the LOWER bar inverted 180° onto the stem top
    ribbon_dir(p,[('M',(172,LCAP-14)),('C',(130,LCAP*0.6),(86,LCAP*0.3),(46,24))],56,14)                                                          # diagonal
    def _zbar(pen): ribbon_prof(pen,[('M',(46,24)),('C',(82,-2),(134,2),(182,24)),('C',(216,35),(226,64),(212,90))],32,19)                        # bottom sweep + swash curl
    _zbar(p)                                                                                                                                      # lower bar (stays)
    _cx, _cy = 109.0 * _LSX, (24 + (LCAP - 14)) / 2.0   # symmetry centre (x scaled by the Latin stretch _LSX that ribbon_prof already applied): rotating the bar start (46,24) by 180° lands on the stem top (172, LCAP-14)
    _bar = pathops.Path(); _zbar(_bar.getPen()); _bar.simplify()
    _rot = pathops.Path(); _bar.draw(TransformPen(_rot.getPen(), (-1, 0, 0, -1, 2 * _cx, 2 * _cy))); _rot.simplify()
    _rot.draw(p)                                                                                                                                  # top bar = lower bar rotated 180°
def _U_R(p): ribbon_dir(p,[('M',(60,LCAP)),('C',(54,LCAP*0.5),(52,20),(56,14))],58,16); ribbon_prof(p,[('M',(58,LCAP-6)),('C',(150,LCAP),(168,LCAP*0.72),(140,LCAP*0.58)),('C',(112,LCAP*0.46),(70,LCAP*0.52),(58,LCAP*0.52))],26,18); ribbon_dir(p,[('M',(96,LCAP*0.52)),('C',(120,LCAP*0.4),(150,LCAP*0.2),(170,16))],52,14)
def _U_G(p): ribbon_prof(p,[('M',(176,LCAP*0.82)),('C',(150,LCAP*1.06),(40,LCAP*1.06),(40,LCAP*0.5)),('C',(40,LCAP*-0.06),(150,LCAP*-0.06),(176,LCAP*0.2)),('C',(182,LCAP*0.3),(182,LCAP*0.42),(176,LCAP*0.46))],30,16); ribbon_prof(p,[('M',(176,LCAP*0.46)),('C',(140,LCAP*0.44),(122,LCAP*0.46),(118,LCAP*0.46))],24,24)
def _U_Q(p): ribbon_prof(p,[('M',(112,LCAP)),('C',(42,LCAP*0.98),(42,LCAP*0.02),(112,0)),('C',(182,LCAP*0.02),(182,LCAP*0.98),(112,LCAP))],30,20); ribbon_dir(p,[('M',(120,LCAP*0.36)),('C',(140,LCAP*0.25),(162,LCAP*0.12),(188,-40))],50,13)
# Latin T is no longer a drawn pen glyph: it is built by clipping the Cyrillic Т (uni0422) down to its
# top CAP + central stem (left curl and outer pipes removed) — see the "Latin T" block after REUSE_DESKEW.
LATIN_HOMO = {}   # none: every Latin letter is now drawn or a de-skewed copy (built below),
# so the Macedonian Cyrillic glyphs are never reused directly and keep their steeper slant.
LATIN_DRAWN = [("i",0x69,_L_i),("t",0x74,_L_t),("l",0x6C,_L_l),("k",0x6B,_L_k),("n",0x6E,_L_n),("h",0x68,_L_h),("b",0x62,_L_b),
    ("d",0x64,_L_d),("r",0x72,_L_r),("q",0x71,_L_q),("f",0x66,_L_f),("v",0x76,_L_v),("w",0x77,_L_w),("z",0x7A,_L_z),
    ("D",0x44,_U_D),("F",0x46,_U_F),("G",0x47,_U_G),("I",0x49,_U_I),("L",0x4C,_U_L),("N",0x4E,_U_N),
    ("Q",0x51,_U_Q),("R",0x52,_U_R),("U",0x55,_U_U),("V",0x56,_U_V),("W",0x57,_U_W),("Z",0x5A,_U_Z)]   # T built separately (clip of Cyrillic Т)
def _latin_sb(path):          # side bearings from ink in the x-height join band (baseline 0)
    fpn = FlattenPen(); path.draw(fpn)
    pts = [q for c in fpn.contours for q in c]
    if not pts: return 0.0, 0.0
    band = [x for (x, y) in pts if CONN_LO <= y <= CONN_HI]
    seq = band if band else [x for (x, y) in pts]
    return min(seq), max(seq)
latin_paths = {}          # positioned Latin outlines, kept to compose the diacritic letters below
for nm, cp, fn in LATIN_DRAWN:
    _LATIN_MODE = True; _LSX = LAT_STRETCH.get(nm, 1.0); _LWT = LAT_LIGHTEN.get(nm, 1.0); _WT = LAT_WT
    pth = pathops.Path(); fn(pth.getPen()); pth.simplify()
    _LATIN_MODE = False; _LSX = 1.0; _LWT = 1.0; _WT = 1.0
    if nm.isupper():          # shrink drawn-cap height before the slant, so the slant stays 15°
        ph2 = pathops.Path(); pth.draw(TransformPen(ph2.getPen(), (1, 0, 0, CAP_H, 0, 0))); ph2.simplify(); pth = ph2
    sl = pathops.Path(); pth.draw(TransformPen(sl.getPen(), (1, 0, SLANT, 1, 0, 0))); sl.simplify()
    bl, br = _latin_sb(sl); b = sl.bounds; minx = b[0] if b else bl
    sp = LAT_SPACE.get(nm, 0); rsp = LAT_RSP.get(nm, 0); lsp = LAT_LSP.get(nm, 0); hshift = M_BODY + sp + lsp - bl; adv = int(round((br - bl) + 2 * (M_BODY + sp) + rsp + lsp))
    t2 = T2CharStringPen(adv, None); sl.draw(TransformPen(t2, (1, 0, 0, 1, hshift, 0)))
    glyph_order.append(nm); charstrings[nm] = t2.getCharString(); metrics[nm] = (adv, int(round(minx + hshift))); cmap[cp] = nm
    _lp = pathops.Path(); sl.draw(TransformPen(_lp.getPen(), (1, 0, 0, 1, hshift, 0))); latin_paths[nm] = _lp
# De-skewed Latin copies of Cyrillic sources, so these Latin letters stand more upright than the
# Macedonian originals (which keep their steeper traced slant — only these copies are re-angled):
#   p/j brought fully to the drawn slant; all caps + a/u have their tilt reduced by CAP/LC_DETILT.
_neut = {g: pth for g, cpt, pth in NEUT}
REUSE_DESKEW = [  # (newname, latin_cp, src_glyph, src_cp, is_cap) — de-skew = _dsk(src_cp) to the single slant
    ("p.lat",0x70,"uni0440",0x0440,False), ("j.lat",0x6A,"uni0458",0x0458,False),
    ("a.lat",0x61,"uni0430",0x0430,False), ("u.lat",0x75,"uni0438",0x0438,False),
    ("c.lat",0x63,"uni0441",0x0441,False), ("e.lat",0x65,"uni0435",0x0435,False),
    ("g.lat",0x67,"uni0434",0x0434,False), ("m.lat",0x6D,"uni043C",0x043C,False),
    ("o.lat",0x6F,"uni043E",0x043E,False), ("s.lat",0x73,"uni0455",0x0455,False),
    ("x.lat",0x78,"uni0445",0x0445,False), ("y.lat",0x79,"uni0443",0x0443,False),
    ("A.lat",0x41,"uni0410",0x0410,True), ("B.lat",0x42,"uni0412",0x0412,True),
    ("C.lat",0x43,"uni0421",0x0421,True), ("E.lat",0x45,"uni0415",0x0415,True),
    ("H.lat",0x48,"uni041D",0x041D,True), ("J.lat",0x4A,"uni0408",0x0408,True),
    ("K.lat",0x4B,"uni041A",0x041A,True), ("M.lat",0x4D,"uni041C",0x041C,True),
    ("O.lat",0x4F,"uni041E",0x041E,True), ("P.lat",0x50,"uni0420",0x0420,True),
    ("S.lat",0x53,"uni0405",0x0405,True),   # T is now a drawn plain T (_U_T), not a Cyrillic-Т copy
    ("X.lat",0x58,"uni0425",0x0425,True), ("Y.lat",0x59,"uni0423",0x0423,True)]
for nm, cp, src, scp, iscap in REUSE_DESKEW:
    dsk = _dsk(scp)
    basey0 = measure(_neut[src], scp)[4]
    base0 = pathops.Path(); _neut[src].draw(TransformPen(base0.getPen(), (1, 0, 0, 1, 0, -basey0))); base0.simplify()
    de = pathops.Path(); base0.draw(TransformPen(de.getPen(), (1, 0, -dsk, 1, 0, 0))); de.simplify()
    if iscap:                 # reused ornate caps: uniform shrink (slant preserved)
        de2 = pathops.Path(); de.draw(TransformPen(de2.getPen(), (CAP_SCALE, 0, 0, CAP_SCALE, 0, 0))); de2.simplify(); de = de2
    if nm in LAT_XCOMP:       # horizontal squeeze (e.g. the too-wide Latin o)
        de3 = pathops.Path(); de.draw(TransformPen(de3.getPen(), (LAT_XCOMP[nm], 0, 0, 1, 0, 0))); de3.simplify(); de = de3
    b = de.bounds
    if iscap:
        minx, maxx, bl, br, basey = measure(de, scp); bl = min(bl, minx + LEFT_CAP)
    else:
        bl, br = _latin_sb(de); minx = b[0] if b else bl; basey = 0.0
    hshift = M_BODY - bl; adv = int(round((br - bl) + 2 * M_BODY))
    t2 = T2CharStringPen(adv, None); de.draw(TransformPen(t2, (1, 0, 0, 1, hshift, -basey)))
    glyph_order.append(nm); charstrings[nm] = t2.getCharString(); metrics[nm] = (adv, int(round(minx + hshift))); cmap[cp] = nm
    _lp = pathops.Path(); de.draw(TransformPen(_lp.getPen(), (1, 0, 0, 1, hshift, -basey))); latin_paths[nm] = _lp

# ---- Latin T: the Cyrillic Т's top CAP (left curl cut) + its MIDDLE pipe (taken whole, unedited) ----
# The cursive Cyrillic Т is drawn as four separate strokes (contours): the top CAP, a big left
# loop+first-pipe stroke, the MIDDLE pipe, and the right pipe. The Latin T is the CAP and the MIDDLE pipe:
# each is lifted verbatim and de-skewed onto the single Latin slant (_dsk(0x0422)) + scaled CAP_SCALE like
# every reused ornate cap. Then, per the design: (1) the cap's own left CURL/swash is cut off so the cap
# reads as a plain bar; (2) the MIDDLE pipe (never reshaped) is moved right T_STEM_PCT of the glyph width;
# (3) the bar is seated a few units onto the pipe's top so the join is solid.
T_CURL_CUT = 360.0  # cut the cap this many (post-scale) units in from its left edge — removes the left curl/swash cleanly
T_CAP_SEAT = 10.0   # overlap the bar onto the pipe's top by this many units (seat is otherwise auto-computed)
T_STEM_PCT = 0.10   # move the middle pipe right this fraction of the (bar+pipe) width, per request
T_RSP      = 60.0   # extra right-side room past the stem, so the next letter isn't jammed under the bar
def _build_T_latin():
    src0 = _neut["uni0422"]
    basey0 = measure(src0, 0x0422)[4]
    base0 = pathops.Path(); src0.draw(TransformPen(base0.getPen(), (1, 0, 0, 1, 0, -basey0))); base0.simplify()
    rp = RecordingPen(); base0.draw(rp)                          # split into its strokes (contours)
    conts = []; cur = []
    for cmd, pts in rp.value:
        cur.append((cmd, pts))
        if cmd in ("closePath", "endPath"): conts.append(cur); cur = []
    def _rebuild(c):
        p = pathops.Path(); pen = p.getPen()
        for cmd, pts in c:
            if pts: getattr(pen, cmd)(*pts)
            else:   getattr(pen, cmd)()
        return p
    def _deskew(p):                                              # onto the single Latin slant + cap scale
        s = pathops.Path(); p.draw(TransformPen(s.getPen(), (1, 0, -_dsk(0x0422), 1, 0, 0))); s.simplify()
        d = pathops.Path(); s.draw(TransformPen(d.getPen(), (CAP_SCALE, 0, 0, CAP_SCALE, 0, 0))); d.simplify(); return d
    def _bb(p):
        fp = FlattenPen(); p.draw(fp); q = [pt for cc in fp.contours for pt in cc]
        return min(x for x, y in q), max(x for x, y in q), min(y for x, y in q), max(y for x, y in q)
    def _box(x0, y0, x1, y1):
        p = pathops.Path(); pen = p.getPen()
        pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath(); return p
    def _tr(p, dx=0.0, dy=0.0):
        o = pathops.Path(); p.draw(TransformPen(o.getPen(), (1, 0, 0, 1, dx, dy))); return o
    raw = [_deskew(_rebuild(c)) for c in conts]
    bbs = [_bb(p) for p in raw]
    cap_i = max(range(len(raw)), key=lambda i: bbs[i][3])        # CAP = the stroke whose ink reaches highest
    rest = sorted([i for i in range(len(raw)) if i != cap_i], key=lambda i: bbs[i][0])
    mid_i = rest[len(rest) // 2]                                 # MIDDLE pipe = the median-left-edge of the rest
    capP, midP, cb = raw[cap_i], raw[mid_i], bbs[cap_i]
    capbar = pathops.Path()                                      # cut the left curl off -> plain bar
    pathops.intersection([capP], [_box(cb[0] + T_CURL_CUT, cb[2] - 60, cb[1] + 60, cb[3] + 60)], capbar.getPen())
    base = pathops.Path(); pathops.union([capbar, midP], base.getPen())   # (unmoved) width, for the 10% stem shift
    wb = _bb(base); dx = T_STEM_PCT * (wb[1] - wb[0])
    movedmid = _tr(midP, dx=dx)
    # seat the bar onto the (moved) pipe's top: lower the bar so its underside near the pipe meets the pipe top
    fpm = FlattenPen(); movedmid.draw(fpm); mp = [pt for c in fpm.contours for pt in c]
    sy = max(y for x, y in mp); sx = sum(x for x, y in mp if y > sy - 12) / max(1, sum(1 for x, y in mp if y > sy - 12))
    fpc = FlattenPen(); capbar.draw(fpc); cp = [pt for c in fpc.contours for pt in c]
    near = [y for x, y in cp if abs(x - sx) < 18]                  # bar underside right at the pipe tip
    seat = (min(near) - sy + T_CAP_SEAT) if near else T_CAP_SEAT   # lower the bar so it overlaps the pipe top by T_CAP_SEAT
    de = pathops.Path()
    pathops.union([_tr(capbar, dy=-seat), movedmid], de.getPen()); de.simplify()
    return de
_T = _build_T_latin()
# Baseline is 0 by construction (base0 was shifted to it; shears/scale about y=0 preserve it), so DON'T
# ask measure to re-detect it — the clipped T (dense top bar, thin stem) fools the baseline detector.
_bT = _T.bounds; minx, maxx = _bT[0], _bT[2]; basey = 0.0
# Space the RIGHT by the STEM (x-height join band), not the far-right bar tip: the bar's right arm then
# overhangs and the next letter tucks under it, so the T flows in the word instead of standing off from it.
_sbl, _sbr = _latin_sb(_T)
bl = minx                                     # left: the bar's left tip (unchanged)
br = _sbr + T_RSP                             # right: stem edge + a little room, so the arm overhangs but the next letter isn't jammed
hshift = M_BODY - bl; adv = int(round((br - bl) + 2 * M_BODY))
t2 = T2CharStringPen(adv, None); _T.draw(TransformPen(t2, (1, 0, 0, 1, hshift, -basey)))
glyph_order.append("T"); charstrings["T"] = t2.getCharString(); metrics["T"] = (adv, int(round(minx + hshift))); cmap[0x54] = "T"
_lp = pathops.Path(); _T.draw(TransformPen(_lp.getPen(), (1, 0, 0, 1, hshift, -basey))); latin_paths["T"] = _lp

# ---- South-Slavic Latin diacritics: base letter + a pen caron / acute / stroke ----
def _acc_glyph(base, kind):
    bp = latin_paths[base]; b = bp.bounds
    out = pathops.Path(); bp.draw(out.getPen())
    cx = (b[0]+b[2])/2.0; top = b[3]; cap = top > 400
    axc = cx + SLANT*(top - (b[1]+b[3])/2.0)          # shift the accent right to follow the italic lean
    if kind == "caron":
        _caron(out.getPen(), axc, top + (54 if cap else 42), 1.3 if cap else 1.0)
    elif kind == "acute":
        _acute(out.getPen(), axc, top + (54 if cap else 42), 1.3 if cap else 1.0)
    elif kind == "stroke" and cap:                     # Đ : bar through the left stem
        my = (b[1]+b[3])/2.0; _rect(out.getPen(), b[0]-14, my-16, b[0]+108, my+16)
    elif kind == "stroke":                             # đ : bar across the ascender
        sy = top - 74; _rect(out.getPen(), b[2]-98, sy, b[2]+18, sy+32)
    out.simplify(); return out
ACCENTED = [("scaron", 0x0161, "s.lat", "caron"), ("ccaron", 0x010D, "c.lat", "caron"),
            ("zcaron", 0x017E, "z", "caron"), ("cacute", 0x0107, "c.lat", "acute"), ("dcroat", 0x0111, "d", "stroke"),
            ("Scaron", 0x0160, "S.lat", "caron"), ("Ccaron", 0x010C, "C.lat", "caron"),
            ("Zcaron", 0x017D, "Z", "caron"), ("Cacute", 0x0106, "C.lat", "acute"), ("Dcroat", 0x0110, "D", "stroke")]
for anm, acp, base, kind in ACCENTED:
    g = _acc_glyph(base, kind); adv, lsb = metrics[base]
    t2 = T2CharStringPen(adv, None); g.draw(t2)
    glyph_order.append(anm); charstrings[anm] = t2.getCharString(); metrics[anm] = (adv, lsb); cmap[acp] = anm
for cp, gn in LATIN_HOMO.items():
    cmap[cp] = gn
cmap[0x00A0] = "space"   # no-break space: same advance as space, so it never shows tofu or breaks layout

# ---- OpenType figures features: tabular, slashed zero, sups/subs, fractions (features.py) ----
from features import generate_figures
_FIGURE_FEA = generate_figures(base_paths, charstrings, metrics, glyph_order, cmap)

# ========================= compile =========================
AUTHOR = "Goran Arsov"
ATTRIB = (f'Makedonka Cursive. (c) 2026 {AUTHOR}. Macedonian cursive letterforms derived from '
          '"Macedonian cursive script" by MacedonianBoy (Wikimedia Commons), CC BY-SA 3.0; changes were made. '
          'Distributed under CC BY-SA 3.0.')
LICENSE = (f'Makedonka Cursive by {AUTHOR} is a derivative of "Macedonian cursive script" by MacedonianBoy '
           '(https://commons.wikimedia.org/wiki/File:Macedonian_cursive_script.svg), CC BY-SA 3.0. The digits, '
           f'punctuation, Bold weight, Latin alphabet, spacing and kerning are by {AUTHOR}. Distributed under '
           'CC BY-SA 3.0: keep attribution and license derivatives alike.')
PS = "MakedonkaCursive-Regular"
fb = FontBuilder(UPM, isTTF=False)
fb.setupGlyphOrder(glyph_order); fb.setupCharacterMap(cmap)
# CFF alignment zones (UPM 700): baseline, x-height ~264, Latin ascender ~553, cap ~685; descender ~-240.
# These let the rasteriser snap those lines to the pixel grid, and give psautohint the zones it needs to hint.
PRIVATE = {"BlueValues": [-7, 0, 260, 270, 548, 560, 680, 694], "OtherBlues": [-248, -236],
           "StdHW": 20, "StdVW": 52, "BlueScale": 0.0396, "BlueShift": 7, "BlueFuzz": 1}
fb.setupCFF(PS, {"version": "0.934", "FullName": "Makedonka Cursive", "FamilyName": "Makedonka Cursive",
                 "Weight": "Regular", "Notice": ATTRIB, "ItalicAngle": 0}, charstrings, PRIVATE)
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=0)
fb.setupNameTable({
    "familyName": "Makedonka Cursive", "styleName": "Regular", "uniqueFontIdentifier": "MakedonkaCursive;0.934",
    "fullName": "Makedonka Cursive", "psName": PS, "version": "Version 0.934", "copyright": ATTRIB,
    "description": "Macedonian cursive display font by Goran Arsov; letterforms derived from a CC BY-SA 3.0 chart by MacedonianBoy, digits/punctuation/Latin/Bold/kerning by Goran Arsov.",
    "designer": "Goran Arsov; original Macedonian cursive letterforms by MacedonianBoy", "manufacturer": "Goran Arsov",
    "licenseDescription": LICENSE, "licenseInfoURL": "https://creativecommons.org/licenses/by-sa/3.0/",
})
# Vertical metrics harmonised: typo = hhea = win (ascent/-descent, lineGap 0) so every app computes the SAME
# line height, and USE_TYPO_METRICS is set below. Kept at the glyph-bbox extent so the tall flourishes never clip.
fb.setupOS2(sTypoAscender=ascent, sTypoDescender=descent, sTypoLineGap=0, usWinAscent=ascent, usWinDescent=abs(descent),
            sxHeight=264, sCapHeight=685)   # measured: round x-height ~264, cap body ~685
fb.setupPost(italicAngle=0.0)          # upright-classified standalone script (the 18° slant is intrinsic to the design)
fb.font["OS/2"].fsSelection = 0x40 | 0x80     # REGULAR + USE_TYPO_METRICS (consistent line height across apps)
fb.font["head"].macStyle = 0x0000
# ---- font-table correctness + QA ----
_os2 = fb.font["OS/2"]
_os2.version = 4                        # fsSelection bit 7 (USE_TYPO_METRICS) is only valid in OS/2 v4+
_os2.fsType = 0x0000                    # installable embedding — the CC BY-SA license permits redistribution
_os2.achVendID = "GARS"                 # 4-char vendor tag
_os2.ulCodePageRange1 = 0x00000005      # advertise Latin-1 (1252) + Cyrillic (1251)
_os2.ulCodePageRange2 = 0x00000000
for _k, _v in dict(bFamilyType=3, bSerifStyle=0, bWeight=6, bProportion=3, bContrast=6, bStrokeVariation=6,
                   bArmStyle=0, bLetterForm=9, bMidline=0, bXHeight=4).items():
    setattr(_os2.panose, _k, _v)        # PANOSE: Latin hand-written / script (was all-zeros "any")
fb.font["head"].fontRevision = 0.934    # match the name-table version (was the default 1.0)
# STAT (this face's position on the Weight axis — the modern standard for a multi-style
# family; Adobe/InDesign use it for family grouping) + meta (design/supported scripts).
# Regular is the default, so its axis-value name is elidable (flag 0x2). Placed BEFORE the
# Mac-name strip below so buildStatTable's re-added platform-1 names are removed with the
# rest (the Windows records remain, so STAT still resolves).
from fontTools.otlLib.builder import buildStatTable
buildStatTable(fb.font, [dict(tag="wght", name="Weight",
                              values=[dict(value=400, name="Regular", flags=0x2)])],
               elidedFallbackName="Regular")
_meta = newTable("meta"); _meta.data = {"dlng": "Latn, Cyrl", "slng": "Latn, Cyrl"}
fb.font["meta"] = _meta
fb.font["name"].removeNames(platformID=1)   # drop legacy Macintosh name records (keep Windows platform 3)
_hhea = fb.font["hhea"]
_hhea.caretSlopeRise = 1; _hhea.caretSlopeRun = 0   # vertical caret (upright-classified; italicAngle 0)
otf = os.path.join(OUTDIR, "MakedonkaCursive-Regular.otf")
fb.save(otf); print("saved", otf)

# ---- connection kerning (both scripts): even the cursive joins — loosen crowded pairs, tighten loose ones
from kern_util import add_kern
print(f"kerning: {add_kern(otf, _FIGURE_FEA)} pairs")   # kern GPOS + figures GSUB, one compile

# ---- hinting: psautohint adds PostScript stem hints keyed off the Private-dict alignment zones above
# (best-effort: a couple of disk-brush glyphs self-overlap and warn, which is non-fatal)
import subprocess
def hint_otf(path):
    try:
        ps = os.path.join(os.path.dirname(sys.executable), "psautohint")
        r = subprocess.run([ps, path, "-o", path], capture_output=True, text=True, timeout=300)
        print(f"hinted {os.path.basename(path)} (psautohint rc={r.returncode})")
    except Exception as e:
        print(f"WARN: psautohint skipped ({e}) — shipping unhinted")
hint_otf(otf)

for fl in ("woff2", "woff"):
    f = TTFont(otf); f.flavor = fl; f.save(os.path.join(OUTDIR, f"MakedonkaCursive-Regular.{fl}"))

# ---- specimen with baseline guide lines ----
from PIL import ImageFont
face = ImageFont.truetype(otf, 100); dig = ImageFont.truetype(otf, 120); small = ImageFont.truetype(otf, 70)
img = Image.new("RGB", (2460, 4200), "white"); dr = ImageDraw.Draw(img); y = 20   # cropped to actual content height before save
def line(txt, font, fill):
    global y
    asc, desc = font.getmetrics()
    dr.text((30, y), txt, fill=fill, font=font); y += asc + desc + 24
# Caps shown as an evenly-spaced glyph chart, drawn with the SAME cap-body-band model as the shipped cap
# kern (kern_util._cap_body): PIL applies no GPOS, so the specimen reproduces the kerned spacing by hand.
# Each cap is placed so the left/right-most ink in the cap-body band sits a constant gap from the previous
# cap's — so the bodies read evenly spaced regardless of where the flourishes reach.
def _cap_body_px(font, ch, band_lo=14, band_hi=84):
    # body left/right (px, rel to pen origin) = left/right-most ink within the cap-body band (band_lo..
    # band_hi px above the baseline) — matches the kern's `_cap_body` (14/84 px @ size100 == 100/590 units).
    bb = font.getbbox(ch, anchor="ls")           # rel to left-baseline; t<0 above baseline, b>0 below
    if not bb:
        return 0.0, 0.0
    l, t, r, b = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
    ox = 20 - min(0, l); base = 20 - t
    tmp = Image.new("L", (r + ox + 20, base + max(0, b) + 20), 0)
    ImageDraw.Draw(tmp).text((ox, base), ch, fill=255, font=font, anchor="ls")
    a = np.asarray(tmp) >= 128
    band = a[max(0, base - band_hi): max(0, base - band_lo), :]
    cols = np.where(band.max(axis=0))[0]
    if len(cols) == 0:
        cols = np.where(a.max(axis=0))[0]
        if len(cols) == 0:
            return 0.0, 0.0
    return float(cols.min() - ox), float(cols.max() - ox)
def line_caps(txt, font, fill, gap=41.0):   # 41 px @ size 100 == CAP_BAND_GAP 290 units (290*100/700); matches the kern
    global y
    asc, desc = font.getmetrics(); prev_r = None
    for ch in txt.replace(" ", ""):
        bl, br = _cap_body_px(font, ch)
        penx = (30.0 - bl) if prev_r is None else (prev_r + gap - bl)
        dr.text((penx, y), ch, fill=fill, font=font)
        prev_r = penx + br
    y += asc + desc + 24
for L in ["АБВГДЃЕЖЗЅИЈ", "КЛЉМНЊОПРСТЌ", "УФХЦЧЏШ"]:
    line_caps(L, face, "black")
line_caps("МАКЕДОНИЈА", face, (90, 20, 20))   # all-caps word reads (uppercase kerning spaces the bodies; flourishes cross)
for L in ["абвгдѓежзѕиј", "клљмнњопрстќ", "уфхцчџш"]:
    line(L, face, "black")
# ---- Latin alphabet (same font) — kept in sync with each version ----
for L in ["ABCDEFGHIJKLM", "NOPQRSTUVWXYZ"]:
    line_caps(L, face, "black")
line_caps("MAKEDONIJA", face, (90, 20, 20))
for L in ["abcdefghijklm", "nopqrstuvwxyz"]:
    line(L, face, "black")
line("š č ž ć đ   Š Č Ž Ć Đ", face, "black")   # South-Slavic Latin diacritics
line("0 1 2 3 4 5 6 7 8 9", dig, (120, 20, 20))
line("«Охрид» · 3/4 · 50% · 20° … и така", small, (20, 20, 90))   # the v0.9.16 punctuation set
for L in ["Скопје 2025 — Македонија", "Охрид, Битола, Прилеп!", "100 денари; (бр. 7)", "вода, леб и убавина?"]:
    line(L, small, (20, 20, 90))
line("Latin: Makedonija, Ohrid — Amici (abvgd...)", small, (90, 20, 20))
img = img.crop((0, 0, 2460, min(img.height, int(y) + 20)))   # trim trailing whitespace to the real content height
img.save(os.path.join(OUTDIR, "specimen.png")); print(f"saved specimen.png ({img.height}px)")
