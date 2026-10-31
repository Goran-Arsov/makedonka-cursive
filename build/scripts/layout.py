#!/usr/bin/env python3
"""Extract every <path> from the Macedonian cursive SVG, resolve its cumulative
transform, compute its placed bounding box + centroid, dump to JSON, and render
an index-annotated PNG so paths can be mapped to letters by eye.

Reads untrusted SVG at argv[1]. Run with `python -I`.
"""
import sys, os, re, math, json
from lxml import etree
from fontTools.misc.transform import Transform
from fontTools.svgLib.path import parse_path
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

SVG = sys.argv[1]
OUTDIR = sys.argv[2]
SVG_W, SVG_H = 2100.0, 1200.0  # root width/height, no viewBox

tree = etree.parse(SVG)
root = tree.getroot()


def ln(el):
    return etree.QName(el).localname


def parse_tf(s):
    t = Transform()
    if not s:
        return t
    for name, args in re.findall(r'([a-zA-Z]+)\s*\(([^)]*)\)', s):
        n = [float(v) for v in re.split(r'[\s,]+', args.strip()) if v != '']
        if name == 'matrix' and len(n) == 6:
            t = t.transform(tuple(n))
        elif name == 'translate':
            t = t.translate(n[0], n[1] if len(n) > 1 else 0.0)
        elif name == 'scale':
            t = t.scale(n[0], n[1] if len(n) > 1 else n[0])
        elif name == 'rotate':
            if len(n) == 3:
                t = t.translate(n[1], n[2]).rotate(math.radians(n[0])).translate(-n[1], -n[2])
            elif n:
                t = t.rotate(math.radians(n[0]))
    return t


def cumulative(el):
    chain = []
    node = el
    while node is not None:
        chain.append(node)
        node = node.getparent()
    chain.reverse()  # root -> leaf
    t = Transform()
    for node in chain:
        t = t.transform(tuple(parse_tf(node.get("transform"))))
    return t


paths = [el for el in root.iter() if ln(el) == "path"]
records = []
for i, p in enumerate(paths):
    d = p.get("d", "")
    mat = cumulative(p)
    rp = RecordingPen()
    try:
        parse_path(d, rp)
    except Exception as e:
        print(f"  parse FAIL idx {i} id {p.get('id')}: {e!r}")
        continue
    bp = BoundsPen(None)
    rp.replay(TransformPen(bp, tuple(mat)))
    if bp.bounds is None:
        print(f"  no-bounds idx {i} id {p.get('id')}")
        continue
    x0, y0, x1, y1 = bp.bounds
    records.append({
        "i": i, "id": p.get("id"),
        "matrix": list(mat),
        "bbox": [x0, y0, x1, y1],
        "cx": (x0 + x1) / 2.0, "cy": (y0 + y1) / 2.0,
        "w": x1 - x0, "h": y1 - y0,
        "d": d,
    })

os.makedirs(OUTDIR, exist_ok=True)
with open(os.path.join(OUTDIR, "paths.json"), "w") as f:
    json.dump({"svg_w": SVG_W, "svg_h": SVG_H, "paths": records}, f)

print(f"extracted {len(records)} / {len(paths)} paths")
xs = [r["cx"] for r in records]
ys = [r["cy"] for r in records]
print(f"centroid x range: {min(xs):.0f}..{max(xs):.0f}  y range: {min(ys):.0f}..{max(ys):.0f}")

# ---- annotate ----
import cairosvg
from PIL import Image, ImageDraw, ImageFont

png = os.path.join(OUTDIR, "chart_hi.png")
cairosvg.svg2png(url=SVG, write_to=png, output_width=int(SVG_W), background_color="white")
img = Image.open(png).convert("RGB")
draw = ImageDraw.Draw(img)
scale = img.width / SVG_W
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
except Exception:
    font = ImageFont.load_default()
for r in records:
    px, py = r["cx"] * scale, r["cy"] * scale
    draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(220, 0, 0))
    draw.text((px + 4, py - 24), str(r["i"]), fill=(200, 0, 0), font=font)
img.save(os.path.join(OUTDIR, "chart_annotated.png"))
print("wrote chart_annotated.png and paths.json")
