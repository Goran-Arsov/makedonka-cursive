"""Outline clean-up shared by build_font.py and make_bold.py.

Unioning many near-coincident copies of an outline (the ѕ `embolden`, the old Bold dilation) makes
skia-pathops leave hairline SLIVER contours behind — a few units wide, tens of units long: holes
render as white cracks inside the stroke at display size (ѕ/s/š in v0.9.34), same-wound ones as
detached specks. Neither can be intentional ink, so both are dropped by width/area.
"""
import pathops
from fontTools.pens.recordingPen import RecordingPen


def contours_of(path):
    """Split a path into per-contour lists of (op, args) and their signed polygon areas."""
    rp = RecordingPen(); path.draw(rp)
    cs, cur = [], []
    for op, args in rp.value:
        cur.append((op, args))
        if op in ("closePath", "endPath"):
            cs.append(cur); cur = []
    if cur:
        cs.append(cur)
    out = []
    for c in cs:
        pts = []
        for op, args in c:
            if op in ("moveTo", "lineTo"):
                pts.append(args[0])
            elif op in ("curveTo", "qCurveTo"):
                pts.extend(a for a in args if a is not None)
        a = 0.0; per = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % len(pts)]
            a += x1 * y2 - x2 * y1; per += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        out.append((c, a / 2.0, per))
    return out


def purge_slivers(path, max_width=4.0, max_area=120.0, holes_only=False):
    """Return a copy of `path` without sliver contours: mean width (2·area/perimeter) < max_width units,
    or |area| < max_area (the smallest intentional mark, a thinned colon dot, is ~300u²). With holes_only
    only contours wound OPPOSITE to the dominant (largest) contour are removed — cracks, never specks."""
    cs = contours_of(path)
    if not cs:
        return path
    dom_sign = max(cs, key=lambda t: abs(t[1]))[1] >= 0
    out = pathops.Path(); pen = out.getPen(); dropped = 0
    for c, a, per in cs:
        width = 2.0 * abs(a) / per if per else 0.0
        if (width < max_width or abs(a) < max_area) and (not holes_only or (a >= 0) != dom_sign):
            dropped += 1; continue
        for op, args in c:
            getattr(pen, op)(*args)
    return out if dropped else path
