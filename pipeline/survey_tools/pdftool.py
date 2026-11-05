"""PDF helper for survey agents (read-only on the PDF).

  text <pdf> <p1> [<p2>]                 text layer of pages p1..p2 (1-based, max 15 pages/call)
  png  <pdf> <page> <out.png> [zoom] [part]
                                         render a page to PNG. zoom default 2.0.
                                         part: full|left|right|top|bottom|tl|tr|bl|br  (default full)
                                         use left/right for 2-column dictionary pages (keeps resolution)
  find <pdf> <regex> [max_hits] [p1-p2]  case-insensitive regex over the text layer -> page + context
  info <pdf>                             page count, page size, metadata, TOC head

Run: <venv python> -I -X utf8 pdftool.py <cmd> ...
"""
import re
import sys

import fitz


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd, pdf = sys.argv[1], sys.argv[2]
    doc = fitz.open(pdf)
    n = doc.page_count
    if cmd == "info":
        print("pages", n, "size_pt", [round(x) for x in doc[0].rect[2:]])
        print("meta", {k: v for k, v in (doc.metadata or {}).items() if v})
        for t in doc.get_toc()[:40]:
            print("toc", t)
    elif cmd == "text":
        p1 = int(sys.argv[3])
        p2 = int(sys.argv[4]) if len(sys.argv) > 4 else p1
        p2 = min(p2, p1 + 14, n)
        for p in range(p1, p2 + 1):
            t = doc[p - 1].get_text("text")
            print(f"===== PAGE {p} / {n} chars={len(t)} =====")
            print(t)
    elif cmd == "png":
        p = int(sys.argv[3])
        out = sys.argv[4]
        zoom = float(sys.argv[5]) if len(sys.argv) > 5 else 2.0
        part = sys.argv[6] if len(sys.argv) > 6 else "full"
        page = doc[p - 1]
        r = page.rect
        w, h = r.width, r.height
        clips = {
            "full": r,
            "left": fitz.Rect(0, 0, w * 0.53, h),
            "right": fitz.Rect(w * 0.47, 0, w, h),
            "top": fitz.Rect(0, 0, w, h * 0.53),
            "bottom": fitz.Rect(0, h * 0.47, w, h),
            "tl": fitz.Rect(0, 0, w * 0.53, h * 0.53),
            "tr": fitz.Rect(w * 0.47, 0, w, h * 0.53),
            "bl": fitz.Rect(0, h * 0.47, w * 0.53, h),
            "br": fitz.Rect(w * 0.47, h * 0.47, w, h),
        }
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clips[part])
        pix.save(out)
        print("saved", out, pix.width, "x", pix.height, "page", p, "/", n, "part", part)
    elif cmd == "find":
        rx = re.compile(sys.argv[3], re.I)
        mx = int(sys.argv[4]) if len(sys.argv) > 4 else 30
        a, b = 1, n
        if len(sys.argv) > 5:
            a, b = (int(x) for x in sys.argv[5].split("-"))
        hits = 0
        for p in range(a, min(b, n) + 1):
            t = doc[p - 1].get_text("text")
            for m in rx.finditer(t):
                s = max(0, m.start() - 80)
                e = min(len(t), m.end() + 120)
                print(f"p{p}: ...{t[s:e]!r}...")
                hits += 1
                if hits >= mx:
                    print("(max hits reached)")
                    return
        print("hits", hits)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
