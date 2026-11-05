# -*- coding: utf-8 -*-
"""S16: linguist answers to checkpoints/review_queues/repair_review.xlsx (2026-11-05).

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
                "source": "Ali 2026-11-05, repair_review В3"})

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
