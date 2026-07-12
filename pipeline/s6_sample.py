# -*- coding: utf-8 -*-
"""S6a: stratified sample of misc1/misc2 content for the taxonomy analysis agent."""
import json, random, re, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

def main():
    entries = [json.loads(l) for l in open(CK / "05_merged.jsonl", encoding="utf-8")]
    random.seed(11)
    strata = {
        "misc1_proverbs": [e for e in entries if re.search(r"посл\.|погов\.|загадка", e.get("misc1",""))],
        "misc1_long": sorted([e for e in entries if len(e.get("misc1","")) > 200], key=lambda e: -len(e["misc1"]))[:80],
        "misc1_short": [e for e in entries if 0 < len(e.get("misc1","")) <= 120],
        "misc2_phras": [e for e in entries if "◊" in e.get("misc2","")],
        "misc2_cit": [e for e in entries if re.search(r"ланы\s+[А-ЯЁ]\.|«[А-ЯЁ]", e.get("misc2",""))],
        "misc2_xref": [e for e in entries if re.search(r"\bкъ\.\s", e.get("misc2","")) or re.search(r"\bсм\.\s", e.get("misc1",""))],
        "misc2_terms": [e for e in entries if "□" in e.get("misc2","") or "▯" in e.get("misc2","")],
        "random": entries,
    }
    quota = {"misc1_proverbs": 15, "misc1_long": 10, "misc1_short": 10, "misc2_phras": 15,
             "misc2_cit": 15, "misc2_xref": 10, "misc2_terms": 10, "random": 35}
    chosen, seen = [], set()
    for k, q in quota.items():
        pool = [e for e in strata[k] if e["entry_id"] not in seen]
        for e in random.sample(pool, min(q, len(pool))):
            seen.add(e["entry_id"])
            chosen.append({"stratum": k, "entry_id": e["entry_id"], "word": e.get("word_base",""),
                           "tags": e.get("tags",""), "def1": e.get("def1",""), "def2": e.get("def2",""),
                           "misc1": e.get("misc1",""), "misc2": e.get("misc2","")})
    out = CK / "shards" / "s6_sample.json"
    json.dump({"samples": chosen}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"samples": len(chosen), "strata": {k: len(v) for k, v in strata.items()}}, ensure_ascii=False))

if __name__ == "__main__":
    main()
