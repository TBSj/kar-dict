"""Render a crop of a ТСКБЯ page around a text snippet (to see the printed marker glyph).

  crop_marker.py <vol> <page_idx0> "<raw snippet text>" <out.png> [zoom] [left_pad_pt]

page_idx0 = 0-based page index as stored in checkpoints/02_dict2_segmented.jsonl ("page").
The snippet is searched in the PDF text layer (fitz search_for, first hit; tries shorter
prefixes if needed); the crop spans the snippet line plus one line above/below and
`left_pad_pt` points to the left (default 40) so the marker before the snippet is visible.
"""
import sys
import fitz

ROOT = r"D:/Projects/My_projects/Python/Py_projects/kar-dict/sources/2"


def main():
    vol, pidx, snip, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
    zoom = float(sys.argv[5]) if len(sys.argv) > 5 else 3.0
    pad = float(sys.argv[6]) if len(sys.argv) > 6 else 40
    doc = fitz.open(f"{ROOT}/ТСКБЯ - {vol}.pdf")
    page = doc[pidx]
    words = snip.split()
    hit = None
    for n in (len(words), 4, 3, 2, 1):
        q = " ".join(words[:n])
        if not q:
            continue
        r = page.search_for(q)
        if r:
            hit = r[0]
            break
    if hit is None:
        print("NOT_FOUND")
        return
    clip = fitz.Rect(max(0, hit.x0 - pad), max(0, hit.y0 - 14), min(page.rect.x1, hit.x0 + 230),
                     min(page.rect.y1, hit.y1 + 14))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
    pix.save(out)
    print("saved", out, pix.width, "x", pix.height, "hit", [round(v) for v in hit])


if __name__ == "__main__":
    main()
