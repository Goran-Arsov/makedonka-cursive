#!/usr/bin/env python3
"""Authoritative inspection of the SVG coordinate system + transform structure.
Reads untrusted SVG at argv[1]. Run with `python -I`."""
import sys
from lxml import etree


def ln(el):
    return etree.QName(el).localname


tree = etree.parse(sys.argv[1])
root = tree.getroot()
print("ROOT tag:", ln(root))
print("ROOT width/height:", root.get("width"), root.get("height"))
print("ROOT viewBox:", root.get("viewBox"))

trs = []
for el in root.iter():
    tf = el.get("transform")
    if tf:
        trs.append((ln(el), el.get("id"), tf))
print("elements with transform:", len(trs))
for x in trs[:25]:
    print("   TF", x)

paths = [el for el in root.iter() if ln(el) == "path"]
print("paths:", len(paths))
for p in paths[:3]:
    d = p.get("d", "")
    print("   path", p.get("id"), "| transform=", p.get("transform"),
          "| dlen=", len(d), "| head=", d[:70])

# parent chain of the first path (to see nesting + inherited transforms)
first = paths[0]
chain = []
node = first
while node is not None:
    chain.append((ln(node), node.get("id"), node.get("transform")))
    node = node.getparent()
print("parent chain of first path (leaf->root):")
for c in chain:
    print("   ", c)
