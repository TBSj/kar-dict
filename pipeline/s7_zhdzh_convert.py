# -*- coding: utf-8 -*-
"""S7h: apply the linguist's zh/dzh verdicts (manual_review_ab.xlsx, 2026-08-07).

Empty verdict on the дж-ж sheet = accept the recommendation:
  - native unmatched words get the latin-j headword (общая форма дж/ж);
  - per the linguist's NEW principle, EVERY дж (dict-1) / ж (dict-2 native)
    instance inside the word converts, not just the initial one;
  - unfilled proper-name rows stay as printed (Джабакку, Джабраил);
    the linguist explicitly overrode Джетегейле/Джетиджеген to j-form.
Also sweeps ALREADY-converted j-words for residual internal дж/ж and fixes
the кь/гь artifacts inside the queue file itself.
"""
import json, re, sys, io
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
Q = CK / "review_queues" / "zh_dzh_unmatched.jsonl"

def kjgj(s):
    return (s.replace("кь", "къ").replace("гь", "гъ")
             .replace("Кь", "Къ").replace("Гь", "Гъ"))

def to_j_d1(w):   # every дж -> j
    return w.replace("Дж", "J").replace("дж", "j")

def to_j_d2(w):   # every ж -> j (native Balkar correspondence)
    return w.replace("Ж", "J").replace("ж", "j")

def base_of(w):
    return re.sub(r"\d+$", "", w)

def main():
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    bybase = defaultdict(list)
    idx = defaultdict(list)
    for e in es:
        bybase[base_of(e["word"]).lower()].append(e)
        for f in ("word", "word_base", "word1_orig", "word2_orig"):
            v = e.get(f)
            if v:
                idx[v.lower()].append(e)
        idx[base_of(e["word"]).lower()].append(e)

    queue = [json.loads(l) for l in open(Q, encoding="utf-8")]
    verdicts = json.load(open(CK / "shards" / "ab_verdicts_raw.json", encoding="utf-8"))["dzh"]
    vq = {kjgj(v["word"].lower()): v for v in verdicts}

    KEEP = set()          # unfilled proper-name rows keep printed form
    for v in verdicts:
        wl = kjgj(v["word"].lower())
        if (v["rec"] or "").startswith("оставить") and not v["verdict"]:
            KEEP.add(wl)

    # explicit j-rule reminders from the needs_review sheet
    EXTRA_D2 = ["жаябел", "жаякълан"]

    converted, kept, missing = [], [], []
    touched_bases = set()

    def convert_word(wl, dic):
        new_base = to_j_d1(wl) if dic == 1 else to_j_d2(wl)
        hits = {id(e): e for e in idx.get(wl, [])}
        if not hits:
            missing.append(wl)
            return
        for e in hits.values():
            old = e["word"]
            b = base_of(old)
            digits = old[len(b):]
            if b.lower() == wl:                      # headword carries the queue spelling
                e["word"] = new_base + digits
                e["word_base"] = new_base
            elif "дж" in b or b.startswith("ж"):     # reduced verb-stem headword etc.
                nb = to_j_d1(b) if dic == 1 else to_j_d2(b)
                e["word"] = nb + digits
                e["word_base"] = nb
            else:
                continue                             # already j-form entry sharing the nest
            e.setdefault("flags", [])
            if "zh_dzh_verdict" not in e["flags"]:
                e["flags"].append("zh_dzh_verdict")
            touched_bases.add(base_of(e["word"]))
            touched_bases.add(b)
            converted.append((old, e["word"]))

    for it in queue:
        wl = kjgj(it["word"].lower())
        if wl in KEEP:
            kept.append(it["word"])
            continue
        convert_word(wl, it["dict"])
    for w in EXTRA_D2:
        convert_word(w, 2)

    # sweep: existing j-words with residual internal дж/ж (linguist's multi-instance rule)
    resid = []
    for e in es:
        b = base_of(e["word"])
        if b.startswith("j") and ("дж" in b or "ж" in b):
            nb = to_j_d1(b).replace("ж", "j")
            digits = e["word"][len(b):]
            resid.append((e["word"], nb + digits))
            e["word"] = nb + digits
            e["word_base"] = nb
            e.setdefault("flags", [])
            if "zh_dzh_verdict" not in e["flags"]:
                e["flags"].append("zh_dzh_verdict")
            touched_bases.add(nb)

    # collisions: same new base from different sources
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    coll_pairs = []
    for w in dup:
        grp = [x for x in es if x["word"] == w]
        ids = {x["dict_id"] for x in grp}
        coll_pairs.append((w, sorted(ids)))
        grp.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both"))
        for i, x in enumerate(grp, 1):
            x["word"] = f"{w}{i}"

    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # queue file: mark resolution, keep as archive; live queue now only the kept names
    with open(CK / "review_queues" / "zh_dzh_resolved.jsonl", "w", encoding="utf-8") as f:
        for it in queue:
            wl = kjgj(it["word"].lower())
            it2 = dict(it, word=kjgj(it["word"]),
                       resolution="kept_as_printed" if wl in KEEP else
                                  ("converted_to_j" if wl not in set(missing) else "NOT_FOUND"))
            f.write(json.dumps(it2, ensure_ascii=False) + "\n")
    with open(Q, "w", encoding="utf-8") as f:
        for it in queue:
            if kjgj(it["word"].lower()) in KEEP:
                f.write(json.dumps(dict(it, word=kjgj(it["word"])), ensure_ascii=False) + "\n")

    print(json.dumps({
        "converted_entries": len(converted), "kept_proper_names": kept,
        "residual_j_sweep": len(resid), "resid_sample": resid[:8],
        "missing": missing, "collisions_digitized": coll_pairs,
    }, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
