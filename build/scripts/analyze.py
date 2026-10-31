#!/usr/bin/env python3
"""Group extracted paths into rows (by centroid y) and sort left-to-right,
printing a coordinate table to drive path->letter mapping."""
import sys, json

data = json.load(open(sys.argv[1]))
paths = data["paths"]

# cluster by cy into rows
ys = sorted(p["cy"] for p in paths)
rows = []
cur = [ys[0]]
for y in ys[1:]:
    if y - cur[-1] > 70:          # row gap
        rows.append((min(cur), max(cur)))
        cur = [y]
    else:
        cur.append(y)
rows.append((min(cur), max(cur)))
print(f"{len(rows)} rows detected (by cy):")
for lo, hi in rows:
    print(f"   row cy {lo:.0f}..{hi:.0f}")


def rowof(cy):
    for idx, (lo, hi) in enumerate(rows):
        if lo - 1 <= cy <= hi + 1:
            return idx
    return -1


print("\n#### paths by row, sorted by x ####")
for ridx in range(len(rows)):
    rps = sorted((p for p in paths if rowof(p["cy"]) == ridx), key=lambda p: p["cx"])
    print(f"\n== ROW {ridx} ==  ({len(rps)} paths)")
    for p in rps:
        x0, y0, x1, y1 = p["bbox"]
        print(f"  i={p['i']:>2}  cx={p['cx']:>5.0f} cy={p['cy']:>5.0f}  "
              f"w={p['w']:>5.0f} h={p['h']:>5.0f}  x[{x0:.0f}..{x1:.0f}] y[{y0:.0f}..{y1:.0f}]")
