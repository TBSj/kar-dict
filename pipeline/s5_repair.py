# -*- coding: utf-8 -*-
"""S5d: deterministic repairs on 06_lextagged.jsonl.

- strip stray Latin homoglyphs inside word/word_base (allowed: leading j, final b)
- restore word1_orig/word2_orig from parsed-source provenance (src1/src2)
- verify word-key uniqueness afterwards
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

def fix_word(w):
    core, digits = re.match(r"^(.*?)(\d*)$", w).groups()
    head = ""
    if core.startswith("j"):
        head, core = "j", core[1:]
    tail = ""
    if core.endswith("b"):
        core, tail = core[:-1], "b"
    core = core.replace("g", "г").replace("e", "е").replace("o", "о").replace("a", "а").replace("c", "с").replace("p", "р").replace("y", "у").replace("x", "х")
    return head + core + tail + digits

def main():
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    d1w = {}
    for l in open(CK / "01_dict1_parsed.jsonl", encoding="utf-8"):
        e = json.loads(l); d1w[e["seqid"]] = e["word"]
    d2w = {}
    for l in open(CK / "03_dict2_parsed.jsonl", encoding="utf-8"):
        e = json.loads(l)
        for sid in e.get("source_ids", []):
            d2w[sid] = e.get("word")

    n_fix = n_orig = 0
    for e in es:
        for f in ("word", "word_base"):
            w = e.get(f) or ""
            fw = fix_word(w)
            if fw != w:
                e[f] = fw; n_fix += 1
        if e.get("src1"):
            w1 = d1w.get(e["src1"][0])
            if w1 and e.get("word1_orig") != w1:
                e["word1_orig"] = w1; n_orig += 1
        if e.get("src2"):
            w2 = d2w.get(e["src2"][0])
            if w2 and e.get("word2_orig") != w2:
                e["word2_orig"] = w2; n_orig += 1

    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps({"latin_fixed": n_fix, "orig_restored": n_orig,
                      "dup_word_keys": dup}, ensure_ascii=False))

if __name__ == "__main__":
    main()
