"""Render page crops for a batch of ТСКБЯ marker items (vision check of the printed glyph).

  crop_batch.py <batch.json> <out_dir>

Each item needs: id, vol, page (0-based page index of the dict-2 segment, as in
02_dict2_segmented.jsonl), raw_snip (raw OCR text that starts right AFTER the marker).
The snippet is located through the page word list (letters-only matching, so letter
spacing, hyphenation and line breaks do not matter), on the segment page or the next two.
The crop shows the line with the snippet plus the line above it, across the whole column;
the first word of the snippet is boxed in red — the marker is the glyph immediately
before that box (possibly at the end of the line above).
Prints one line per item: id -> png path | NOT_FOUND.
"""
import json
import re
import sys
from pathlib import Path

import fitz

SRC = r"D:/Projects/My_projects/Python/Py_projects/kar-dict/sources/2"
HOMO = str.maketrans("ABEKMHOPCTXYaeopcxykmt", "АВЕКМНОРСТХУаеорсхукмт")


def norm(s):
    out = []
    for ch in s.translate(HOMO).lower():
        ch = {"ё": "е", "ь": "ъ", "й": "и"}.get(ch, ch)
        if "а" <= ch <= "я":
            out.append(ch)
    return "".join(out)


def find(doc, pidx, snip):
    probe_full = norm(snip)
    for L in (20, 14, 9):
        probe = probe_full[:L]
        if len(probe) < L:
            continue
        for p in range(max(0, pidx - 1), pidx + 6):
            if p >= doc.page_count:
                break
            page = doc[p]
            words = page.get_text("words")
            letters, owner = [], []
            for wi, w in enumerate(words):
                for ch in norm(w[4]):
                    letters.append(ch)
                    owner.append(wi)
            s = "".join(letters)
            i = s.find(probe)
            if i >= 0 and s.find(probe, i + 1) < 0:
                w = words[owner[i]]
                return page, fitz.Rect(w[:4])
    return None, None


def main():
    items = json.load(open(sys.argv[1], encoding="utf-8"))
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for it in items:
        v = it["vol"]
        if v not in docs:
            docs[v] = fitz.open(f"{SRC}/ТСКБЯ - {v}.pdf")
        page, hit = find(docs[v], it["page"], it.get("raw_snip") or "")
        if hit is None and it.get("block"):
            page, hit = find(docs[v], it["page"], it["block"])
        safe = re.sub(r"[^\w@]", "_", it["id"])
        if hit is None:
            print(f"{it['id']} -> NOT_FOUND")
            continue
        page.add_rect_annot(fitz.Rect(hit.x0 - 1, hit.y0 - 1, hit.x1 + 1, hit.y1 + 1)).set_colors(stroke=(1, 0, 0))
        mid = page.rect.width / 2
        col0, col1 = (0, mid + 4) if hit.x0 < mid else (mid - 4, page.rect.width)
        clip = fitz.Rect(col0, max(0, hit.y0 - 15), col1, min(page.rect.y1, hit.y1 + 3))
        p = out / f"{safe}.png"
        page.get_pixmap(matrix=fitz.Matrix(2.6, 2.6), clip=clip).save(str(p))
        print(f"{it['id']} -> {p}")


if __name__ == "__main__":
    main()
