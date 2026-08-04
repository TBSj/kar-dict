# -*- coding: utf-8 -*-
"""S4: Merge matched entries; prepare LLM batches for homonym alignment.

  python s4_merge.py --prepare    # deterministic merges + batches for complex groups
  python s4_merge.py --finalize   # fold in LLM outputs, assign homonym digits, write 05_merged.jsonl
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S4_IN = CK / "shards" / "s4_in"
S4_OUT = CK / "shards" / "s4_out"
SIMPLE = CK / "shards" / "s4_simple.jsonl"

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}

def hom_order(h):
    h = (h or "").strip()
    if h in ROMAN: return ROMAN[h]
    if h.isdigit(): return int(h)
    return 99

def load():
    rows = [json.loads(l) for l in open(CK / "04_match_table.jsonl", encoding="utf-8")]
    d1 = defaultdict(list)
    for l in open(CK / "01_dict1_parsed.jsonl", encoding="utf-8"):
        e = json.loads(l); d1[e["word"]].append(e)
    d2 = defaultdict(list)
    for l in open(CK / "03_dict2_parsed.jsonl", encoding="utf-8"):
        e = json.loads(l)
        if e.get("word"): d2[e["word"]].append(e)
    for k in d2:
        d2[k].sort(key=lambda e: hom_order(e.get("hom")))
    return rows, d1, d2

def mk_simple(row, e1, e2):
    tags2 = (e2 or {}).get("tags", "") or ""
    tags1 = (e1 or {}).get("tags", "") or ""
    tags = tags2 if tags2 else tags1
    if tags2 and tags1 and tags1 not in tags2:
        tags = f"{tags2}; {tags1}"
    return {
        "word_base": row["word_final"],
        "dict_id": "both" if e1 and e2 else ("1" if e1 else "2"),
        "tags": tags,
        "def1": (e1 or {}).get("def1", ""),
        "def2": (e2 or {}).get("def2", ""),
        "misc1": (e1 or {}).get("misc1", ""),
        "misc2": (e2 or {}).get("misc2", ""),
        "src1": [e1["seqid"]] if e1 else [],
        "src2": (e2 or {}).get("source_ids", []),
        "word1_orig": (e1 or {}).get("word"),
        "word2_orig": (e2 or {}).get("word"),
        "decl": (e1 or {}).get("decl", ""),
        "flags": sorted(set((e1 or {}).get("flags", [])) | set((e2 or {}).get("flags", []))),
        "hom_rank": hom_order((e2 or {}).get("hom")) if e2 else hom_order((e1 or {}).get("hom_src")),
    }

def prepare():
    rows, d1, d2 = load()
    simple, complex_groups = [], []
    for row in rows:
        items = row.get("d1_items") or ([{"word": row["d1_word"], "cls": row["class"],
                                          "word_final": row["word_final"]}] if row.get("d1_word") else [])
        for it in items:
            if it["word_final"] is None:  # unresolved verb adjudication fallback
                it["word_final"] = it["word"].lower()
        if row["word_final"] is None:
            row["word_final"] = items[0]["word_final"] if items else (row.get("d2_word") or "").lower()
        e1s = [(it, e) for it in items for e in d1.get(it["word"], [])]
        e2s = d2.get(row["d2_word"], []) if row["d2_word"] else []
        if len(e1s) <= 1 and len(e2s) <= 1 and not row.get("note"):
            it_e = e1s[0] if e1s else None
            r = dict(row, word_final=it_e[0]["word_final"] if it_e else row["word_final"])
            simple.append(mk_simple(r, it_e[1] if it_e else None, e2s[0] if e2s else None))
        else:
            complex_groups.append({
                **({"note": row["note"]} if row.get("note") else {}),
                "match_id": row["match_id"], "word_final": row["word_final"],
                "word_base_map": {it["word"]: it["word_final"] for it in items} | {"_d2only": row["word_final"]},
                "d1": [{"seqid": e["seqid"], "d1_word": it["word"], "word_base": it["word_final"],
                        "hom_src": e.get("hom_src",""), "tags": e.get("tags",""),
                        "decl": e.get("decl",""), "def1": e.get("def1",""), "misc1": e.get("misc1","")}
                       for it, e in e1s],
                "d2": [{"source_ids": e.get("source_ids",[]), "hom": e.get("hom",""), "tags": e.get("tags",""),
                        "def2": e.get("def2",""), "misc2": e.get("misc2","")} for e in e2s],
            })
    with open(SIMPLE, "w", encoding="utf-8") as f:
        for r in simple:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    S4_IN.mkdir(parents=True, exist_ok=True)
    for f_old in S4_IN.glob("batch_*.json"): f_old.unlink()
    BS = 6
    for i in range(0, len(complex_groups), BS):
        with open(S4_IN / f"batch_{i//BS:04d}.json", "w", encoding="utf-8") as f:
            json.dump(complex_groups[i:i+BS], f, ensure_ascii=False, indent=1)
    print(json.dumps({"simple": len(simple), "complex_groups": len(complex_groups),
                      "batches": (len(complex_groups)+BS-1)//BS}, ensure_ascii=False))

def finalize():
    merged = [json.loads(l) for l in open(SIMPLE, encoding="utf-8")]
    missing = []
    for bf in sorted(S4_IN.glob("batch_*.json")):
        outf = S4_OUT / bf.name
        if not outf.exists():
            missing.append(bf.name); continue
        data = json.load(open(outf, encoding="utf-8"))
        for g in data["groups"]:
            for e in g["entries"]:
                e.setdefault("flags", [])
                e.setdefault("hom_rank", 99)
                merged.append(e)
    # global homonym digit assignment over final word
    byword = defaultdict(list)
    for e in merged:
        byword[e["word_base"]].append(e)
    out = []
    for w, es in sorted(byword.items()):
        if len(es) == 1:
            es[0]["word"] = w
        else:
            es.sort(key=lambda e: (e.get("hom_rank", 99), e.get("dict_id") != "both"))
            for i, e in enumerate(es, 1):
                e["word"] = f"{w}{i}"
        out.extend(es)
    with open(CK / "05_merged.jsonl", "w", encoding="utf-8") as f:
        for i, e in enumerate(out):
            e["entry_id"] = f"e_{i:05d}"
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    cls = Counter(e["dict_id"] for e in out)
    rep = {"entries": len(out), "dict_id": dict(cls),
           "homonym_words": sum(1 for w, es in byword.items() if len(es) > 1),
           "missing_llm_outputs": missing}
    json.dump(rep, open(CK / "qa" / "s4_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    if a.prepare: prepare()
    if a.finalize: finalize()
