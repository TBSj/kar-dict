# -*- coding: utf-8 -*-
"""S7g: systematic кь/гь -> къ/гъ repair (OCR ь/ъ confusion in dict-1 source).

Karachay-Balkar orthography has no кь/гь; linguist verdict 2026-08-05: every
occurrence is an OCR artifact for къ/гъ.

  python s7_kjgj_fix.py --phase1   # text fields + collision-free headword renames;
                                   # exports merge/nest candidates to shards/kjgj_cases.json
  python s7_kjgj_fix.py --apply    # fold agent verdicts (shards/kjgj_verdicts.json) back in
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
F = CK / "06_lextagged.jsonl"

RX = re.compile(r"[кгКГ][ьЬ]")
TEXT_FIELDS = ("tags", "def1", "def2", "misc1", "misc2", "decl",
               "word1_orig", "word2_orig")
SUBFIELD_KEYS = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
                 "misc1_stem_note", "misc1_variants",
                 "misc2_citations", "misc2_citations_periodical",
                 "misc2_citations_collection", "misc2_proverb_illustr",
                 "misc2_phras", "misc2_terms", "misc2_xref", "misc2_gram_note"]

def fix(s):
    return (s.replace("кь", "къ").replace("гь", "гъ")
             .replace("Кь", "Къ").replace("Гь", "Гъ")
             .replace("КЬ", "КЪ").replace("ГЬ", "ГЪ")
             .replace("кЬ", "къ").replace("гЬ", "гъ"))

def base_of(w):
    return re.sub(r"\d+$", "", w)

def load():
    return [json.loads(l) for l in open(F, encoding="utf-8")]

def save(es):
    with open(F, "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def mark(e, flag="kjgj_fixed"):
    e.setdefault("flags", [])
    if flag not in e["flags"]:
        e["flags"].append(flag)

def redigit(es, bases):
    """reassign homonym digits inside the given word bases"""
    grp = defaultdict(list)
    for e in es:
        b = base_of(e["word"])
        if b in bases:
            grp[b].append(e)
    for b, g in grp.items():
        if len(g) == 1:
            g[0]["word"] = b
        else:
            g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both"))
            for i, x in enumerate(g, 1):
                x["word"] = f"{b}{i}"

def phase1():
    es = load()
    # 1. text fields everywhere
    n_text = 0
    for e in es:
        hit = False
        for f in TEXT_FIELDS:
            v = e.get(f)
            if v and RX.search(v):
                e[f] = fix(v); hit = True
        if hit:
            n_text += 1
            mark(e)
            for k in SUBFIELD_KEYS:   # re-extracted later by s6_apply
                e.pop(k, None)
    # 2. headwords
    bybase = defaultdict(list)
    for e in es:
        bybase[base_of(e["word"])].append(e)
    bad = [e for e in es if RX.search(e["word"])]
    renames, cases = [], []
    for e in bad:
        b = base_of(e["word"])
        fb = fix(b)
        others = [o for o in bybase.get(fb, []) if o is not e]
        if not others:
            renames.append((e, b, fb))
        else:
            cases.append({
                "entry_id": e["entry_id"], "old_base": b, "new_base": fb,
                "entry": {k: e.get(k) for k in
                          ("word", "dict_id", "tags", "def1", "def2", "misc1", "misc2",
                           "hom_rank", "src1", "src2", "word1_orig")},
                "existing": [{k: o.get(k) for k in
                              ("entry_id", "word", "dict_id", "tags", "def1", "def2",
                               "misc1", "misc2", "hom_rank")} for o in others],
            })
    touched_bases = set()
    for e, b, fb in renames:
        e["word"] = fix(e["word"])
        e["word_base"] = fix(e.get("word_base") or fb)
        mark(e)
        touched_bases.add(fb)
    # two clean renames may land on the same new base -> redigit
    redigit(es, touched_bases)
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, f"collisions after phase1: {dup[:10]}"
    json.dump({"cases": cases}, open(CK / "shards" / "kjgj_cases.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    save(es)
    print(json.dumps({"text_entries_fixed": n_text, "clean_renames": len(renames),
                      "cases_for_verdict": len(cases)}, ensure_ascii=False))

def apply_verdicts():
    es = load()
    byid = {e["entry_id"]: e for e in es}
    cases = {c["entry_id"]: c for c in
             json.load(open(CK / "shards" / "kjgj_cases.json", encoding="utf-8"))["cases"]}
    verdicts = json.load(open(CK / "shards" / "kjgj_verdicts.json", encoding="utf-8"))["items"]
    assert sorted(v["entry_id"] for v in verdicts) == sorted(cases), "verdict/case id mismatch"
    n_merge = n_sep = 0
    drop, touched_bases = set(), set()
    for v in verdicts:
        c = cases[v["entry_id"]]
        e = byid[v["entry_id"]]
        touched_bases.add(c["new_base"])
        if v["action"] == "merge":
            t = byid[v["merge_into"]]
            assert base_of(t["word"]) == c["new_base"], (v, t["word"])
            assert t["dict_id"] == "2" and e["dict_id"] == "1", \
                f"merge only d1-into-d2: {e['entry_id']}->{t['entry_id']}"
            assert not (set(e.get("src1") or []) & set(t.get("src1") or []))
            t["dict_id"] = "both"
            for f in ("def1", "misc1", "decl"):
                if e.get(f): t[f] = e[f]
            if e.get("tags") and (e["tags"] or "") not in (t.get("tags") or ""):
                t["tags"] = f"{t['tags']}; {e['tags']}" if t.get("tags") else e["tags"]
            t["src1"] = e.get("src1") or []
            t["word1_orig"] = fix(e.get("word1_orig") or c["new_base"])
            mark(t)
            for k in SUBFIELD_KEYS:
                t.pop(k, None)
            drop.add(e["entry_id"])
            n_merge += 1
        else:
            assert v["action"] == "separate", v
            e["word"] = c["new_base"]           # digit assigned by redigit below
            e["word_base"] = c["new_base"]
            mark(e)
            if "needs_review" not in e["flags"] and v.get("unsure"):
                e["flags"].append("needs_review")
            n_sep += 1
    es = [e for e in es if e["entry_id"] not in drop]
    redigit(es, touched_bases)
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, f"collisions after apply: {dup[:10]}"
    # nothing lost: every src1 seqid present before must remain
    save(es)
    print(json.dumps({"merged": n_merge, "separate": n_sep, "entries": len(es)},
                     ensure_ascii=False))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase1", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.phase1: phase1()
    if a.apply: apply_verdicts()
