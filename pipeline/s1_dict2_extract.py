# -*- coding: utf-8 -*-
"""S1: Extract dict-2 (ТСКБЯ, 3 volumes) page text and segment into entries.

Outputs:
  checkpoints/00_dict2_pages/vol{N}.jsonl   {vol, page, text}
  checkpoints/02_dict2_segmented.jsonl      {id, vol, page, headword_raw, headword_fixed, hom, text, flags}
  checkpoints/qa/s1_report.json
"""
import fitz, json, re, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "2"
OUT_PAGES = ROOT / "checkpoints" / "00_dict2_pages"
OUT_SEG = ROOT / "checkpoints" / "02_dict2_segmented.jsonl"
QA = ROOT / "checkpoints" / "qa" / "s1_report.json"

VOLS = {1: "ТСКБЯ - 1.pdf", 2: "ТСКБЯ - 2.pdf", 3: "ТСКБЯ - 3.pdf"}

CAPS = "А-ЯЁ"
LAT_HOMO = "ABEKMHOPCTXY"  # Latin caps OCR-confused with Cyrillic

RE_PAGENUM = re.compile(r"^\s*\d{1,4}\s*$")
RE_CAPS_FRAG = re.compile(rf"^[{CAPS}{LAT_HOMO}\s£$]{{2,10}}$")
# running head glued to body text: 'ТАУ 400 ТАУ Т А З2 am к...'
RE_HEAD_PREFIX = re.compile(rf"^\s*[{CAPS}{LAT_HOMO}£$\s]{{2,8}}\s+\d{{1,4}}\s+[{CAPS}{LAT_HOMO}£$]{{2,6}}\s+")

def is_running_head(line: str) -> bool:
    s = line.strip()
    if RE_PAGENUM.match(s):
        return True
    if re.match(rf"^[{CAPS}{LAT_HOMO}£$\s]{{2,8}}\s+\d{{1,4}}\s+[{CAPS}{LAT_HOMO}£$\s]{{2,8}}$", s):
        return True
    if len(s) <= 10 and (RE_CAPS_FRAG.match(s) or re.match(r"^[а-яё]( [а-яё]){1,5}$", s)):
        return True
    return False

def page_lines(page) -> list[str]:
    lines = page.get_text().split("\n")
    out, i = [], 0
    for i, ln in enumerate(lines):
        if i < 4 and is_running_head(ln):
            continue
        if i < 2:
            ln = RE_HEAD_PREFIX.sub("", ln)  # glued running head
        out.append(ln)
    return out

def dehyphenate(lines: list[str]) -> str:
    buf = []
    for ln in lines:
        ln = ln.rstrip()
        if not ln:
            continue
        if buf and buf[-1].endswith(("­", "-")):
            buf[-1] = buf[-1].rstrip("­-") + ln.lstrip()
        else:
            buf.append(ln)
    return "\n".join(buf)

# --- entry segmentation ------------------------------------------------------
# head: caps run (may embed spaces from letter-spacing, hyphens, and OCR noise 1/I/|)
# hom: optional Roman/Arabic homonym numeral, attached or spaced
# boundary: must NOT be a lowercase letter attached directly (rejects 'ТАСС-ны')
RE_ENTRY = re.compile(
    rf"^(?P<head>[{CAPS}{LAT_HOMO}](?:[{CAPS}{LAT_HOMO}1I|'ЪЬ ­.-]*[{CAPS}{LAT_HOMO}])?)"
    rf"(?P<hom>\s{{0,2}}(?:I{{1,3}}|IV|V|VI|[1-9])(?![0-9]))?"
    rf"(?=$|[\s:;,.!?/(\[«»)\"]|-(?![а-яё]))"
)
RE_LEAD_GARBAGE = re.compile(r"^[.,'\"`„\s]{1,3}")

def fix_spaced_caps(s: str) -> str:
    return re.sub(r"[\s­]+", "", s)

def normalize_headword(raw: str) -> str:
    s = fix_spaced_caps(raw)
    table = str.maketrans("ABEKMHOPCTXYaeopcxy|", "АВЕКМНОРСТХУаеорсхуІ")
    s = s.translate(table)
    return s.strip(".-'").lower()

def cyr_caps_count(s: str) -> int:
    return sum(1 for ch in s if ("А" <= ch <= "Я") or ch in "ЁЪЬ")

def match_entry_start(line: str):
    """Return (head_raw, hom, garbage_stripped) or None."""
    s = line.strip()
    g = RE_LEAD_GARBAGE.match(s)
    stripped = False
    if g and not RE_ENTRY.match(s):
        s = s[g.end():]
        stripped = True
    m = RE_ENTRY.match(s)
    if not m:
        return None
    head = m.group("head")
    core = fix_spaced_caps(head)
    if cyr_caps_count(core) < 2 or len(core) < 2 or len(core) > 28:
        return None
    return head.strip(), (m.group("hom") or "").strip(), stripped

def segment_volume(vol: int, pages: list[dict]) -> list[dict]:
    entries, cur = [], None
    for p in pages:
        for ln in p["text"].split("\n"):
            hit = match_entry_start(ln)
            if hit:
                if cur:
                    entries.append(cur)
                head_raw, hom, garb = hit
                cur = {
                    "vol": vol, "page": p["page"],
                    "headword_raw": head_raw,
                    "headword_fixed": normalize_headword(head_raw),
                    "hom": hom,
                    "lines": [ln.strip()],
                    "garb": garb,
                }
            elif cur:
                cur["lines"].append(ln.strip())
    if cur:
        entries.append(cur)
    out, prev_key = [], ""
    for e in entries:
        text = "\n".join(e.pop("lines"))
        key = e["headword_fixed"]
        flags = []
        if prev_key and key < prev_key:
            flags.append("alpha_break")
        if len(text) < 25:
            flags.append("very_short")
        if re.search(r"[A-Za-z0-9|]", e["headword_raw"]):
            flags.append("noise_in_head")
        if e.pop("garb"):
            flags.append("lead_garbage")
        e.update(text=text, flags=flags)
        out.append(e)
        prev_key = key
    return out

def main():
    body_start = {1: 29, 2: 17, 3: 17}
    OUT_PAGES.mkdir(parents=True, exist_ok=True)
    all_entries, report = [], {}
    for vol, fname in VOLS.items():
        doc = fitz.open(str(SRC / fname))
        pages = []
        for pg in range(body_start[vol], len(doc)):
            pages.append({"vol": vol, "page": pg, "text": dehyphenate(page_lines(doc[pg]))})
        with open(OUT_PAGES / f"vol{vol}.jsonl", "w", encoding="utf-8") as f:
            for p in pages:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        entries = segment_volume(vol, pages)
        all_entries.extend(entries)
        report[f"vol{vol}"] = {
            "pages": len(pages), "entries": len(entries),
            "alpha_breaks": sum(1 for e in entries if "alpha_break" in e["flags"]),
            "very_short": sum(1 for e in entries if "very_short" in e["flags"]),
            "noise_in_head": sum(1 for e in entries if "noise_in_head" in e["flags"]),
        }
        doc.close()
        print(f"vol{vol}: {report[f'vol{vol}']}")
    with open(OUT_SEG, "w", encoding="utf-8") as f:
        for i, e in enumerate(all_entries):
            e["id"] = f"d2_{i:05d}"
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    QA.parent.mkdir(parents=True, exist_ok=True)
    report["total_entries"] = len(all_entries)
    with open(QA, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("TOTAL:", len(all_entries))

if __name__ == "__main__":
    main()
