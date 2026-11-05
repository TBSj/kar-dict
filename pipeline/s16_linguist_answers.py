# -*- coding: utf-8 -*-
"""S16: linguist answers to the review workbooks (2026-11-05) — repair_review.xlsx (В1–В3 below)
and kbrs_blocks_review.xlsx (В1 jапхыч = jабхыч, В2 акъ «белогвардеец» = «акъ гвардиячы», В3 the two
book misprints fixed in s17 — confirmed, nothing to change).

В1 (book misprints fixed in s10, flag source_typo_fixed) and В2 («phraseology» = ◊ only) —
confirmed by Ali, nothing to change.
В3 эт-jен (Ali): «эт-джен» = плоть; «эт-джен адам» = родственник.  КБРС gives «родственник(и)»
to эт-джен itself (qmos эт_32114 «-джен родственник(и)», джен_7744 «эт-джен своя кровь,
родственник») — that meaning moves to the phrase «эт-джен адам» (misc1, КБРС spelling).

Idempotent: every fix checks the current value; already-applied fixes are skipped.
Then run: s6_apply -> s8_facets -> s7_export -> s7_invariants -> s7_xlsx.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s10_hyphen import SUB  # noqa: E402  (also re-wraps stdout as utf-8)

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
F06 = CK / "06_lextagged.jsonl"
FLAG = "linguist_fix"

# (entry_id, word, field, old, new)
FIXES = [
    ("e_38679", "эт-jен", "def1", "родственник(и)", "плоть"),
    ("e_38679", "эт-jен", "misc1", "", "эт-джен адам родственник(и)"),
    ("e_10093", "jен", "def1", "эт-джен своя кровь, родственник",
     "эт-джен плоть; эт-джен адам своя кровь, родственник"),
    # kbrs_blocks_review.xlsx В2 (Ali): «белогвардеец» is the phrase «акъ гвардиячы» (акъ as an adjective) —
    # the КБРС sense «ист. белый, белогвардеец» (printed under the noun part 2.) moves to the adjective акъ1,
    # as in ТСКБЯ; «белогвардеец» becomes the phrase
    ("e_02446", "акъ2", "def1", "2. (агъы) 1) бельмо 2) белок 3) ист. белый, белогвардеец", "2. (агъы) 1) бельмо 2) белок"),
    ("e_02446", "акъ2", "misc1",
     "аны кёзюне акъ тюшгенди у него на глазу появилось бельмо; гаккыны агъы белок яйца; кёзню агъы а) бельмо на глазу; "
     "б) белок глаза; кёзлеринги агъын айландырыргъа закатить глаза; акъла белые",
     "аны кёзюне акъ тюшгенди у него на глазу появилось бельмо; гаккыны агъы белок яйца; кёзню агъы а) бельмо на глазу; "
     "б) белок глаза; кёзлеринги агъын айландырыргъа закатить глаза"),
    ("e_02445", "акъ1", "def1", "1. 1) белый; светлый 2) бледный; матовый 3) седой",
     "1. 1) белый; светлый 2) бледный; матовый 3) седой 4) ист. белый"),
]
APPEND = [  # (entry_id, word, field, text appended with «; »)
    ("e_02445", "акъ1", "misc1", "акъла белые; акъ гвардиячы белогвардеец"),
]
# kbrs_blocks_review.xlsx В1 (Ali): КБРС «джапхыч» (read back from the scan, p. 228) is a variant of
# «джабхыч» -> merged into jабхыч1 (its def1 «заслонка, задвижка, вьюшка (у печки)» covers it)
MERGES = [  # (from entry_id, from word, into entry_id, into word)
    ("e_39995", "jапхыч", "e_00008", "jабхыч1"),
]

es = [json.loads(l) for l in open(F06, encoding="utf-8")]
byid = {e["entry_id"]: e for e in es}
log, touched = [], set()
for eid, word, field, old, new in FIXES:
    e = byid[eid]
    assert e["word"] == word, (eid, e["word"], word)
    cur = e.get(field) or ""
    if cur == new:
        log.append({"entry_id": eid, "word": word, "field": field, "status": "already"})
        continue
    assert cur == old, (eid, field, cur)
    e[field] = new
    if FLAG not in e.setdefault("flags", []):
        e["flags"].append(FLAG)
    touched.add(eid)
    log.append({"entry_id": eid, "word": word, "field": field, "old": old, "new": new,
                "source": "Ali 2026-11-05, linguist answer"})

for eid, word, field, add in APPEND:
    e = byid[eid]
    assert e["word"] == word, (eid, e["word"], word)
    cur = e.get(field) or ""
    if cur.endswith(add):
        log.append({"entry_id": eid, "word": word, "field": field, "status": "already"})
        continue
    e[field] = f"{cur}; {add}" if cur else add
    if FLAG not in e.setdefault("flags", []):
        e["flags"].append(FLAG)
    touched.add(eid)
    log.append({"entry_id": eid, "word": word, "field": field, "appended": add, "source": "Ali 2026-11-05, linguist answer"})

dropped = set()
for src, sw, dst, dw in MERGES:
    d = byid[dst]
    assert d["word"] == dw, (dst, d["word"], dw)
    if src not in byid:
        log.append({"entry_id": src, "word": sw, "merged_into": dst, "status": "already"})
        continue
    s = byid[src]
    assert s["word"] == sw and not s.get("src2"), (src, s["word"])
    d["src1"] = list(d.get("src1") or []) + [x for x in s.get("src1") or [] if x not in (d.get("src1") or [])]
    for f in ("def1", "misc1"):
        if s.get(f) and s[f] not in (d.get(f) or "") and not (f == "def1" and d.get(f)):
            d[f] = f"{d[f]}; {s[f]}" if d.get(f) else s[f]
    for fl in [FLAG] + [x for x in s.get("flags") or [] if x in ("kbrs_scan_block", "uncertain_ocr")]:
        if fl not in d.setdefault("flags", []):
            d["flags"].append(fl)
    dropped.add(src)
    touched.add(dst)
    log.append({"entry_id": src, "word": sw, "merged_into": dst, "into_word": dw, "src1": s.get("src1"),
                "def1_dropped_as_covered": s.get("def1"), "misc1_moved": s.get("misc1"),
                "source": "Ali 2026-11-05, kbrs_blocks_review В1"})
if dropped:
    es = [e for e in es if e["entry_id"] not in dropped]

if touched:
    for e in es:
        if e["entry_id"] in touched:
            for k in SUB:          # re-extracted by s6_apply
                e.pop(k, None)
    with open(F06, "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
with open(CK / "qa" / "s16_linguist.jsonl", "a", encoding="utf-8") as f:
    for r in log:
        if r.get("status") != "already":
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
for r in log:
    print(json.dumps(r, ensure_ascii=False))
print("touched:", len(touched))
