"""show.py -- comparison / proof sheets with the owner's 10% margin rule.

Renders words with real shaping (PIL + RAQM layout engine == GPOS kern + default
GSUB, what a browser applies -- NOT the basic layout engine, which applies
neither) and crops to a sheet that carries a 10% white margin on EVERY edge,
sized from the real ink extent, so nothing is ever clipped. This is the owner's
standing rule (2026-11-02: a sheet once clipped the very underbar under
discussion) and the method quoted throughout the handoff for before/after proofs.

Give two fonts to stack an old-vs-new comparison (labelled); give one to proof a
single font. Default words include the owner's standing specimen phrases.

Usage:
  python build/scripts/qa/show.py "збор" "МАКЕДОНИЈА"           # one font (default Regular)
  python build/scripts/qa/show.py --font X.otf --cmp Y.otf "збор"   # old vs new
  python build/scripts/qa/show.py --out /tmp/proof.png "a'b" "I'd"
Reconstructed 2026-11-06 from the handoff / the render-margins rule.
"""
import argparse
from PIL import Image, ImageFont, ImageDraw

MARGIN = 0.10                       # white border on every edge, fraction of ink size
DEFAULT_WORDS = ["Македонка", "МАКЕДОНИЈА", "rock'n'roll",
                 "Let's use commin', 'cause I'mma go to Leno's"]


def render_line(font_path, text, size):
    """Render one line, cropped tight to its ink (RGBA, ink black on transparent)."""
    fnt = ImageFont.truetype(font_path, size, layout_engine=ImageFont.Layout.RAQM)
    tmp = Image.new("L", (16, 16), 0)
    x0, y0, x1, y1 = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=fnt)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    pad = size  # generous scratch canvas so nothing is cut before we crop
    img = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(img).text((pad - x0, pad - y0), text, font=fnt, fill=255)
    bbox = img.getbbox()            # real ink extent
    return img.crop(bbox) if bbox else img


def sheet(blocks, size):
    """blocks: list of (label, font_path, [words]). Stack all lines, add 10% margin."""
    lines = []          # (pil_L_image, is_label)
    gap = size // 3
    for label, font_path, words in blocks:
        if label:
            lab = render_line(font_path, label, max(14, size // 4))
            lines.append((lab, True))
        for w in words:
            lines.append((render_line(font_path, w, size), False))
    ink_w = max(im.width for im, _ in lines)
    ink_h = sum(im.height for im, _ in lines) + gap * (len(lines) - 1)
    mx, my = int(ink_w * MARGIN), int(ink_h * MARGIN)
    W, H = ink_w + 2 * mx, ink_h + 2 * my
    canvas = Image.new("L", (W, H), 255)
    y = my
    for im, is_label in lines:
        canvas.paste(Image.eval(im, lambda p: 255 - p), (mx, y))   # ink -> black
        y += im.height + gap
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words", nargs="*", default=DEFAULT_WORDS)
    ap.add_argument("--font", default="MakedonkaCursive-Regular.otf")
    ap.add_argument("--cmp", default=None, help="second font for an old-vs-new sheet")
    ap.add_argument("--size", type=int, default=130)
    ap.add_argument("--out", default="/tmp/show.png")
    a = ap.parse_args()
    words = a.words or DEFAULT_WORDS
    if a.cmp:
        blocks = [(f"[A] {a.font}", a.font, words), (f"[B] {a.cmp}", a.cmp, words)]
    else:
        blocks = [("", a.font, words)]
    sheet(blocks, a.size).save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
