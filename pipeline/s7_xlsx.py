# -*- coding: utf-8 -*-
"""S7d: final.xlsx from final.csv (same columns, sheet «словарь») + sheet «источники» (legend of «sources»).

Excel limits a cell to 32 767 characters; the two longest misc2 fields (баш1, кёз1) are
cut there and end with «…[обрезано, см. final.csv]».  final.csv / 07_final.jsonl stay complete.
"""
import csv, sys, io
from collections import Counter
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
LIMIT = 32767
TAIL = "…[обрезано, см. final.csv]"


def legend(wb, rows):
    """sheet «источники»: what the codes of the column «sources» stand for (s19_sources.LEGEND)"""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from s19_sources import LEGEND
    col = rows[0].index("sources")
    n, paged = Counter(), Counter()
    for r in rows[1:]:
        for part in filter(None, r[col].split(", ")):
            code = part.split(" с. ")[0].split(" т. ")[0]
            n[code] += 1
            paged[code] += " с. " in part
    ws = wb.create_sheet("источники")
    ws.append(["Столбец sources листа «словарь»: откуда взята статья — источники через запятую, у каждого страница "
               "(у ТСКБЯ ещё том). Подробнее — docs/SOURCES.md."])
    ws["A1"].font = Font(bold=True)
    ws.append([])
    ws.append(["код", "издание", "что берётся в корпус", "как получено", "статей", "из них со страницей", "права (как в книге)"])
    for c in ws[3]:
        c.font = Font(bold=True)
    for s in LEGEND:
        ws.append([s["code"], s["record"], s["fields"], s["how"], n[s["code"]], paged[s["code"]], s["rights"]])
    for row in ws.iter_rows(min_row=4):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for colname, w in {"A": 18, "B": 60, "C": 50, "D": 50, "E": 9, "F": 12, "G": 30}.items():
        ws.column_dimensions[colname].width = w


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
    widths = {"A": 22, "B": 7, "C": 16, "D": 40, "E": 40, "F": 40, "G": 40, "H": 22, "I": 30}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    legend(wb, rows)
    wb.save(CK / "final.xlsx")
    print(f"final.xlsx: {len(rows) - 1} entries, {cut} cells cut at {LIMIT} chars")


if __name__ == "__main__":
    main()
