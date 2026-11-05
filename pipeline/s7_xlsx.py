# -*- coding: utf-8 -*-
"""S7d: final.xlsx from final.csv (same columns, sheet «словарь»).

Excel limits a cell to 32 767 characters; the two longest misc2 fields (баш1, кёз1) are
cut there and end with «…[обрезано, см. final.csv]».  final.csv / 07_final.jsonl stay complete.
"""
import csv, sys, io
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
LIMIT = 32767
TAIL = "…[обрезано, см. final.csv]"


def main():
    rows = list(csv.reader(open(CK / "final.csv", encoding="utf-8-sig")))
    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = "словарь"
    cut = 0
    for i, r in enumerate(rows):
        out = []
        for v in r:
            if len(v) > LIMIT:
                v = v[:LIMIT - len(TAIL)] + TAIL
                cut += 1
            out.append(v)
        ws.append(out)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "B2"
    widths = {"A": 22, "B": 7, "C": 16, "D": 40, "E": 40, "F": 40, "G": 40, "H": 22}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    wb.save(CK / "final.xlsx")
    print(f"final.xlsx: {len(rows) - 1} entries, {cut} cells cut at {LIMIT} chars")


if __name__ == "__main__":
    main()
