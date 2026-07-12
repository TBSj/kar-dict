# -*- coding: utf-8 -*-
"""S7b: gather data for the linguist review artifact (JSON consumed by HTML builder).

Collects: stage stats, dict_id/lextag distributions, sample entries
(таукелсиз group + random + flagged), review queue sizes.
"""
import json, random, sys, io, re
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

def jload(p, default=None):
    p = Path(p)
    if not p.exists(): return default
    return json.load(open(p, encoding="utf-8"))

def main():
    src = CK / "07_final.jsonl"
    if not src.exists():
        src = CK / "06_lextagged.jsonl"
    entries = [json.loads(l) for l in open(src, encoding="utf-8")]
    random.seed(42)

    taukel = [e for e in entries if re.match(r"^таукелсиз\d*$", e.get("word","")) ]
    flagged = [e for e in entries if e.get("flags")]
    verbs = [e for e in entries if (e.get("word2_orig") or "") and (e.get("word1_orig") or "").endswith(("ргъа","рге"))]
    jw = [e for e in entries if e.get("word","").startswith("j")]
    bw = [e for e in entries if e.get("word","").rstrip("0123456789").endswith("b")]
    sample = random.sample(entries, min(25, len(entries)))

    data = {
        "generated": "pilot",
        "counts": {
            "entries": len(entries),
            "dict_id": dict(Counter(e.get("dict_id") for e in entries)),
            "lextag": dict(Counter(e.get("lextag") for e in entries).most_common()),
            "flagged": len(flagged),
            "homonym_words": len({re.sub(r"\d+$","",e["word"]) for e in entries if re.search(r"\d$", e.get("word",""))}),
            "j_words": len(jw), "b_words": len(bw), "verb_merged": len(verbs),
        },
        "qa": {
            "s0": jload(CK/"qa"/"s0_qa_report.json", {}).get("summary"),
            "s1": jload(CK/"qa"/"s1_report.json", {}),
            "s2": jload(CK/"qa"/"s2_qa_report.json", {}).get("summary"),
            "s3": jload(CK/"qa"/"s3_report.json", {}),
            "s4": jload(CK/"qa"/"s4_report.json", {}),
            "s5": jload(CK/"qa"/"s5_report.json", {}),
            "s7": jload(CK/"qa"/"s7_invariants.json", {}),
        },
        "queues": {
            "only1_verbs": sum(1 for _ in open(CK/"review_queues"/"only1_verbs.jsonl", encoding="utf-8")) if (CK/"review_queues"/"only1_verbs.jsonl").exists() else 0,
            "zh_dzh": sum(1 for _ in open(CK/"review_queues"/"zh_dzh_unmatched.jsonl", encoding="utf-8")) if (CK/"review_queues"/"zh_dzh_unmatched.jsonl").exists() else 0,
            "spelling": sum(1 for _ in open(CK/"review_queues"/"spelling_conflicts.jsonl", encoding="utf-8")) if (CK/"review_queues"/"spelling_conflicts.jsonl").exists() else 0,
        },
        "samples": {
            "taukelsiz": taukel,
            "j_words": jw[:8], "b_words": bw[:8], "verbs": verbs[:8],
            "flagged": random.sample(flagged, min(10, len(flagged))),
            "random": sample,
        },
    }
    out = CK / "review_data.json"
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("counts:", json.dumps(data["counts"], ensure_ascii=False))
    print("queues:", json.dumps(data["queues"], ensure_ascii=False))

if __name__ == "__main__":
    main()
