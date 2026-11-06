# -*- coding: utf-8 -*-
"""S7c: build 07_final.jsonl (+ final.csv) from 06_lextagged.jsonl.

Field order follows the linguist's schema; provenance/QA fields kept after it.
«sources» (right after the schema fields): printed sources of the entry with pages, comma-separated —
«КБРС-1989 с. 101, ТСКБЯ т. 1 с. 230» (s19_sources.py; legend: docs/SOURCES.md, sheet «источники»).
"""
import json, csv, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s19_sources import SourceRefs  # noqa: E402

MAIN = ["word", "dict_id", "tags", "def1", "def2", "misc1", "misc2", "lextag"]
EXTRA = ["entry_id", "word1_orig", "word2_orig", "decl", "hom_rank",
         "lextag_conf", "src1", "src2", "flags",
         "pos", "dialect", "style", "domain", "gram_note", "tags_other",
         "derived", "derived_from", "variant_of", "variants", "guzeev", "built_from",
         "misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
         "misc1_stem_note", "misc1_variants",
         "misc2_citations", "misc2_citations_periodical", "misc2_citations_collection",
         "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
         "misc2_gram_note"]

def main():
    entries = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    entries.sort(key=lambda e: e.get("word", ""))
    refs = SourceRefs()
    for e in entries:
        e["sources"] = refs.of(e)
    with open(CK / "07_final.jsonl", "w", encoding="utf-8") as f:
        for e in entries:
            rec = {k: e.get(k, "") for k in MAIN}
            rec["sources"] = e["sources"]
            for k in EXTRA:
                if e.get(k) not in (None, "", []):
                    rec[k] = e[k]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    FCT = ["pos", "dialect", "style", "domain", "gram_note"]
    with open(CK / "final.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(MAIN + ["sources"] + FCT + ["derived_from", "variant_of", "flags", "word1_orig", "word2_orig"])
        for e in entries:
            w.writerow([e.get(k, "") for k in MAIN] + [e["sources"]] +
                       ["; ".join(e.get(k) or []) for k in FCT] +
                       [e.get("derived_from", ""), e.get("variant_of", ""),
                        ";".join(e.get("flags", [])), e.get("word1_orig", ""), e.get("word2_orig", "")])
    print(f"exported {len(entries)} entries -> 07_final.jsonl, final.csv")

if __name__ == "__main__":
    main()
