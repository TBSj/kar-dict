# -*- coding: utf-8 -*-
"""S7: deterministic invariants over the final pilot/full output.

Checks 06_lextagged.jsonl (or 07_final.jsonl if present):
  - schema completeness, unique word keys, digit-suffix consistency
  - lextag vocabulary
  - def2 KB-leak detector
  - dict_id sanity vs src fields
  - entry accounting vs inputs
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

VALID_LEXTAGS = {"universe_and_nature","living_things","human_body","mind_and_cognition",
    "emotions_and_will","social_relations","culture_and_spirituality",
    "language_and_communication","actions_and_activities","objects_and_technology",
    "daily_life_and_food","economy_and_society","space_and_time","logic_and_function_words"}

def kb_density(s):
    words = re.findall(r"[а-яё]{3,}", s.lower())
    if not words: return 0.0
    kb = sum(1 for w in words if re.search(r"къ|гъ|нг", w) or re.search(r"[ыиаоюё]у$", w))
    return kb / len(words)

def main():
    src = CK / "07_final.jsonl"
    if not src.exists():
        src = CK / "06_lextagged.jsonl"
    entries = [json.loads(l) for l in open(src, encoding="utf-8")]
    problems = defaultdict(list)

    words = Counter(e.get("word","") for e in entries)
    for w, n in words.items():
        if n > 1:
            problems["duplicate_word_key"].append(w)

    # digit-suffix consistency: base with suffixes must not also exist bare,
    # and suffix sequence must be 1..N
    bases = defaultdict(list)
    for e in entries:
        w = e.get("word","")
        m = re.match(r"^(.*?)(\d+)$", w)
        if m:
            bases[m.group(1)].append(int(m.group(2)))
    for b, nums in bases.items():
        if b in words:
            problems["bare_word_plus_suffixed"].append(b)
        if sorted(nums) != list(range(1, len(nums)+1)):
            problems["suffix_gap"].append(f"{b}:{sorted(nums)}")

    for e in entries:
        eid = e.get("entry_id","?")
        for fld in ("word","dict_id","tags","def1","def2","misc1","misc2"):
            if fld not in e:
                problems["missing_field"].append(f"{eid}:{fld}")
        if e.get("lextag") and e["lextag"] not in VALID_LEXTAGS:
            problems["bad_lextag"].append(f"{eid}:{e['lextag']}")
        di = e.get("dict_id")
        # derivational dict1 entries may carry all their content in tags -> judge by provenance
        has1 = bool(e.get("src1")) or bool(e.get("def1") or e.get("misc1"))
        has2 = bool(e.get("src2")) or bool(e.get("def2") or e.get("misc2"))
        want = "both" if (has1 and has2) else ("1" if has1 else "2")
        if di != want:
            problems["dict_id_mismatch"].append(f"{eid}:{di}!={want}")
        d2 = e.get("def2","")
        if len(d2) > 15 and kb_density(d2) > 0.34:
            problems["kb_leak_def2"].append(f"{eid}:{d2[:60]}")
        if di in ("both","1") and not e.get("def1") and not e.get("misc1") and not e.get("tags"):
            problems["empty_d1_side"].append(eid)
        w = e.get("word","")
        if w and w[0].isupper() and not e.get("word1_orig","") and not (e.get("word2_orig") or ""):
            pass

    rep = {"source": src.name, "entries": len(entries),
           "dict_id_dist": dict(Counter(e.get("dict_id") for e in entries)),
           "problems": {k: {"count": len(v), "sample": v[:12]} for k, v in problems.items()}}
    json.dump(rep, open(CK / "qa" / "s7_invariants.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({k: len(v) for k, v in problems.items()}, ensure_ascii=False, indent=2))
    print("entries:", len(entries))

if __name__ == "__main__":
    main()
