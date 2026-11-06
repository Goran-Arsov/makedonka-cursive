"""Shared QA helpers: HarfBuzz shaping + FreeType per-glyph rasterisation.

These back the overlap / slant / tuck scans. The scans need each glyph's ink
*in isolation* at its shaped (kerned) position so overlap between neighbours can
be counted — PIL's whole-string render can't separate the two glyphs' ink, so we
shape with uHarfBuzz (GPOS kern + default GSUB, exactly what a browser applies)
and rasterise each glyph id with FreeType (correct non-zero winding, so the
disk-brush glyphs' overlapping contours and real counters both come out right).

Render resolution is 200 px/em: an "overlap of N px²" in the handoff / followups
is N overlapping pixels at this size. INK_CUTOFF treats a pixel as ink at >= half
coverage, so anti-aliased edges that merely touch don't register as a collision.

Reconstructed 2026-11-06 from the method descriptions in
macedonian-cursive-font-handoff.md (the originals lived in session scratch and
were not kept). Validated to reproduce the handoff's quoted numbers — see qa/README.md.
"""
import freetype
import uharfbuzz as hb
import numpy as np

PX = 200          # render size, px/em  (so "px²" == pixel count at this size)
INK_CUTOFF = 128  # grayscale >= this counts as solid ink


def open_fonts(path):
    """Return (ft_face, hb_font, upem) ready to shape+render at PX px/em."""
    ft = freetype.Face(path)
    ft.set_pixel_sizes(0, PX)
    blob = hb.Blob.from_file_path(path)
    face = hb.Face(blob)
    font = hb.Font(face)
    upem = face.upem
    font.scale = (upem, upem)   # keep positions in font units
    return ft, font, upem


def shape(hb_font, text, features=None, direction="ltr"):
    """Shape `text`; return [(gid, x_advance_fu, x_offset_fu, y_offset_fu), ...].

    features=None applies HarfBuzz's defaults (kern, calt, liga, clig ... on) —
    i.e. real-world shaping, including this font's apostrophe `.lc` calt rules.
    """
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    buf.direction = direction
    hb.shape(hb_font, buf, features)
    out = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((info.codepoint, pos.x_advance, pos.x_offset, pos.y_offset))
    return out


_BM_CACHE = {}


def _glyph_bitmap(ft, gid):
    """Return (ink_bool[rows,width], left_px, top_px). top = px from baseline up.

    Cached per (font, gid): only 294 glyphs, rendered thousands of times in a scan.
    """
    key = (id(ft), gid)
    hit = _BM_CACHE.get(key)
    if hit is not None:
        return hit
    ft.load_glyph(gid, freetype.FT_LOAD_RENDER)
    bm = ft.glyph.bitmap
    rows, width, pitch = bm.rows, bm.width, bm.pitch
    left, top = ft.glyph.bitmap_left, ft.glyph.bitmap_top
    if rows == 0 or width == 0:
        res = (np.zeros((0, 0), bool), left, top)
    else:
        arr = np.array(bm.buffer, dtype=np.uint8).reshape(rows, pitch)[:, :width]
        res = (arr >= INK_CUTOFF, left, top)
    _BM_CACHE[key] = res
    return res


def glyph_masks(ft, hb_font, upem, text, features=None, stack=False):
    """Shape `text`, rasterise each glyph on a common canvas.

    Returns (masks, canvas_shape) where masks[i] is a bool array (same shape for
    all i) holding glyph i's ink at its shaped position. Baseline is honoured so
    ascender/descender overlap is seen.

    stack=True ignores x_advance (every glyph pinned at pen x=0) — the deliberate
    collision used as a positive control: a working scanner must flag it.
    """
    s = PX / upem
    glyphs = shape(hb_font, text, features)
    placed = []   # (ink, col0_f, row_top_f)  in a baseline=0, y-down frame
    penx = 0.0
    for gid, adv, xoff, yoff in glyphs:
        ink, left, top = _glyph_bitmap(ft, gid)
        ox = (penx + xoff) * s
        oy = yoff * s                      # up-positive
        col0 = ox + left
        row_top = -(top) - oy              # y-down, baseline 0
        placed.append((ink, col0, row_top))
        if not stack:
            penx += adv
    # union bbox
    xs0 = [c for ink, c, r in placed if ink.size]
    if not xs0:
        return [], (0, 0)
    X0 = min(c for ink, c, r in placed if ink.size)
    X1 = max(c + ink.shape[1] for ink, c, r in placed if ink.size)
    Y0 = min(r for ink, c, r in placed if ink.size)
    Y1 = max(r + ink.shape[0] for ink, c, r in placed if ink.size)
    W = int(np.ceil(X1 - X0)) + 2
    H = int(np.ceil(Y1 - Y0)) + 2
    masks = []
    for ink, c, r in placed:
        m = np.zeros((H, W), bool)
        if ink.size:
            cc = int(round(c - X0))
            rr = int(round(r - Y0))
            m[rr:rr + ink.shape[0], cc:cc + ink.shape[1]] = ink
        masks.append(m)
    return masks, (H, W)


def overlap_px(mask_a, mask_b):
    """Overlapping ink pixels between two same-shaped masks."""
    return int(np.count_nonzero(mask_a & mask_b))


def cmap_has(ft, cp):
    """gid for codepoint cp, or 0 if the font has no glyph for it."""
    return ft.get_char_index(cp)


if __name__ == "__main__":
    # Smoke test + positive control.
    ft, hbf, upem = open_fonts("MakedonkaCursive-Regular.otf")
    masks, shape_ = glyph_masks(ft, hbf, upem, "Аб")
    print("normal 'Аб': canvas", shape_, "ink px",
          [int(m.sum()) for m in masks], "overlap", overlap_px(masks[0], masks[1]))
    sm, _ = glyph_masks(ft, hbf, upem, "Аб", stack=True)
    print("stacked 'Аб' (positive control): overlap", overlap_px(sm[0], sm[1]),
          "-> must be large")
