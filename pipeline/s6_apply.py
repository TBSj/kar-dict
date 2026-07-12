# -*- coding: utf-8 -*-
"""S6b: apply the taxonomy extraction rules -> typed misc subfields.

misc1/misc2 stay intact; extracted content is ADDED as arrays. Rules come from
checkpoints/qa/s6_misc_rules.json (validated by the taxonomy agent on the sample).
Ordering: periodical citations extracted before collection citations (overlap).
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

ORDER = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
         "misc1_stem_note", "misc1_variants",
         "misc2_citations", "misc2_citations_periodical", "misc2_citations_collection",
         "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
         "misc2_gram_note"]

def main():
    rules = {r["field"]: r for r in json.load(open(CK / "qa" / "s6_misc_rules.json", encoding="utf-8"))["rules"]}
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    stats = Counter()
    for e in es:
        consumed_coll = []
        for field in ORDER:
            r = rules.get(field)
            if not r:
                continue
            src = e.get(r["source"]) or ""
            if not src:
                continue
            try:
                pat = re.compile(r["regex"])
            except re.error:
                continue
            vals = []
            if r["mode"] == "extract_all":
                if field == "misc2_citations_collection":
                    # skip spans already claimed by the periodical rule
                    per = rules["misc2_citations_periodical"]
                    spans = [m.span() for m in re.finditer(per["regex"], src)]
                    for m in pat.finditer(src):
                        if not any(a <= m.start() < b for a, b in spans):
                            vals.append(m.group(0).strip())
                else:
                    for m in pat.finditer(src):
                        g = m.group(0).strip()
                        if field == "misc1_folklore" and re.search(r"[аб]\)\s*$", (m.group(1) or "")):
                            continue  # stylistic label, not a folklore formula
                        vals.append(g)
            elif r["mode"] == "split_after_marker":
                parts = pat.split(src)
                if len(parts) > 1:
                    if field == "misc2_phras":
                        for block in parts[1:]:
                            block = block.strip()
                            if block:
                                vals.append(block.split("◊")[0].strip()[:800])
                    else:
                        vals = [p.strip()[:800] for p in parts[1:] if p.strip()]
            if vals:
                e[field] = vals
                stats[field] += 1
    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps({"entries_with_subfields": dict(stats.most_common())}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
