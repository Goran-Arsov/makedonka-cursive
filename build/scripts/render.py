#!/usr/bin/env python3
"""Render an SVG to PNG, trying multiple backends. Reads an untrusted SVG path
passed as argv[1]; writes PNG to argv[2]. Run with `python -I`."""
import sys

src, out = sys.argv[1], sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 1600
errors = []

# Backend 1: cairosvg (best quality, needs libcairo)
try:
    import cairosvg
    cairosvg.svg2png(url=src, write_to=out, output_width=width, background_color="white")
    print("OK: rendered with cairosvg")
    sys.exit(0)
except Exception as e:
    errors.append(("cairosvg", repr(e)))

# Backend 2: svglib + reportlab (pure-ish python, no system cairo)
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    drawing = svg2rlg(src)
    renderPM.drawToFile(drawing, out, fmt="PNG")
    print("OK: rendered with svglib/reportlab")
    sys.exit(0)
except Exception as e:
    errors.append(("svglib", repr(e)))

for name, e in errors:
    print(f"FAIL {name}: {e}")
sys.exit(1)
