# -*- coding: utf-8 -*-
"""S3: Consolidate parsed shards, normalize, and match dict1 <-> dict2.

Inputs:  checkpoints/01_dict1_preparsed.jsonl (trivial entries)
         checkpoints/shards/s0_out/*.json     (LLM-parsed dict1)
         checkpoints/shards/s2_out/*.json     (LLM-parsed dict2)
Outputs: checkpoints/01_dict1_parsed.jsonl
         checkpoints/03_dict2_parsed.jsonl
         checkpoints/04_match_table.jsonl
         checkpoints/review_queues/*.jsonl
         checkpoints/qa/s3_report.json
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
RQ = CK / "review_queues"

PILOT_PREFIXES = ("та", "жаб", "жал", "джаб", "джал")

# ---------- canonicalization -------------------------------------------------
def canon(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"дж", "ж", s)
    s = s.replace("б", "п")
    return s

RE_INF = re.compile(r"(ргъа|рге)$")

def verb_stem_candidates(inf: str) -> list[str]:
    """барыргъа -> [бары, бар]; тагъаргъа -> [тагъа, тагъ, такъ]; табаргъа -> [таба, таб].

    ы/и/у/ю before -р- are epenthetic; а/е may be either the aorist vowel
    (таб-ар-гъа) or stem-final (тара-р-гъа) — both variants are candidates,
    matching against dict2 / LLM adjudication decides.
    """
    if not RE_INF.search(inf):
        return []
    base = RE_INF.sub("", inf)
    cands = [base]
    if base and base[-1] in "ыиуюае":
        cands.append(base[:-1])
    extra = []
    for c in cands:
        if c.endswith("гъ"):
            extra.append(c[:-2] + "къ")
        elif c.endswith("г"):
            extra.append(c[:-1] + "к")
    return cands + extra

def is_verb_d1(e) -> bool:
    return bool(RE_INF.search(e["word"])) or "эт." in (e.get("tags") or "")

# ---------- load -------------------------------------------------------------
def load_dict1(slice_):
    pre = {}
    for l in open(CK / "01_dict1_preparsed.jsonl", encoding="utf-8"):
        e = json.loads(l)
        pre[e["seqid"]] = e
    parsed = {}
    for f in sorted((CK / "shards" / "s0_out").glob("batch_*.json")):
        for oe in json.load(open(f, encoding="utf-8"))["entries"]:
            parsed[oe["seqid"]] = oe
    out = []
    RE_DECL_ANY = re.compile(r"\((-?г[ъь]?[ыиу]|-?[дн]и|-?[гк]и)\)")
    for sid, e in pre.items():
        if slice_ == "pilot" and not e["word"].lower().startswith(PILOT_PREFIXES):
            continue
        if not e.get("decl_hint"):
            m = RE_DECL_ANY.search(e.get("clean", "")[:40])
            if m:
                e["decl_hint"] = m.group(1).lstrip("-")
        if e["trivial"]:
            rec = {"seqid": sid, "word": e["word"], "hom_src": e["hom_marker"],
                   "decl": e["decl_hint"], "tags": e.get("tags",""),
                   "def1": e.get("def1",""), "misc1": e.get("misc1",""), "flags": []}
        elif sid in parsed:
            oe = parsed[sid]
            rec = {"seqid": sid, "word": e["word"], "hom_src": e["hom_marker"],
                   "decl": e["decl_hint"], "tags": oe.get("tags",""),
                   "def1": oe.get("def1",""), "misc1": oe.get("misc1",""),
                   "flags": oe.get("flags", [])}
        else:
            rec = {"seqid": sid, "word": e["word"], "hom_src": e["hom_marker"],
                   "decl": e["decl_hint"], "tags": "", "def1": "", "misc1": e["clean"],
                   "flags": ["unparsed"]}
        out.append(rec)
    return out

def load_dict2():
    out = []
    for f in sorted((CK / "shards" / "s2_out").glob("batch_*.json")):
        for oe in json.load(open(f, encoding="utf-8"))["entries"]:
            oe.setdefault("flags", [])
            out.append(oe)
    return out

# ---------- matching ---------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", choices=["pilot", "all"], default="pilot")
    args = ap.parse_args()

    d1 = load_dict1(args.slice)
    d2 = load_dict2()

    with open(CK / "01_dict1_parsed.jsonl", "w", encoding="utf-8") as f:
        for e in d1:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(CK / "03_dict2_parsed.jsonl", "w", encoding="utf-8") as f:
        for e in d2:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # group by headword
    g1 = defaultdict(list)
    for e in d1:
        g1[e["word"]].append(e)
    g2 = defaultdict(list)
    for e in d2:
        if e.get("word"):
            g2[e["word"]].append(e)

    # canon index for dict2; verb-capable dict2 words (some homonym tagged эт)
    idx2 = defaultdict(list)
    for w in g2:
        idx2[canon(w)].append(w)
    # verb-capable dict2 words: tagged эт., or relational verb tags (понуд./страд./взаимн. от X)
    verb2 = {w for w, es in g2.items()
             if any("эт" in (e.get("tags") or "") or
                    re.search(r"(понуд|страд|взаимн)[^/]{0,12}\bот\b", e.get("tags") or "")
                    for e in es)}

    rows, used2 = [], set()
    q_verbs, q_zh, q_spell = [], [], []
    claims = defaultdict(list)  # d2_word -> [{word, cls, word_final}]

    for w1 in sorted(g1):
        c1 = canon(w1)
        verb = any(is_verb_d1(e) for e in g1[w1])
        hit_words, match_class = [], None
        if c1 in idx2:
            hit_words = idx2[c1]
            match_class = "direct"
        elif verb:
            for cand in verb_stem_candidates(w1.lower()):
                cc = canon(cand)
                # a verb may only match a dict2 word that has a verb homonym
                cand_hits = [w for w in idx2.get(cc, []) if w in verb2]
                if cand_hits:
                    hit_words = cand_hits
                    match_class = "verb"
                    break
        if hit_words:
            w2 = hit_words[0]
            if len(hit_words) > 1:
                q_spell.append({"d1": w1, "d2_variants": hit_words, "why": "canon_collision"})
            used2.add(w2)
            word_final, reasons = decide_word(w1, w2, match_class)
            if reasons:
                q_spell.append({"d1": w1, "d2": w2, "why": ";".join(reasons)})
            claims[w2].append({"word": w1, "cls": match_class, "word_final": word_final})
        else:
            word_final = w1.lower()
            cls = "only1"
            if verb:
                cands = verb_stem_candidates(w1.lower())
                q_verbs.append({"word": w1, "candidates": cands,
                                "def1": (g1[w1][0].get("def1") or "")[:150]})
                cls = "only1_verb"
                word_final = None  # decided by LLM adjudication
            if w1.lower().startswith("дж") and w1.lower() not in ("дж",):
                q_zh.append({"dict": 1, "word": w1, "def": (g1[w1][0].get("def1") or "")[:150]})
            rows.append({"key": c1, "class": cls, "d1_word": w1,
                         "d1_items": [{"word": w1, "cls": cls, "word_final": word_final}],
                         "d2_word": None, "d1_n": len(g1[w1]), "d2_n": 0,
                         "word_final": word_final})

    for w2, items in sorted(claims.items()):
        bases = {it["word_final"] for it in items}
        if len(bases) == 1:
            base = items[0]["word_final"]
        else:
            base = w2.lower()
            q_spell.append({"d2": w2, "d1_variants": [it["word"] for it in items],
                            "why": "base_conflict:" + ",".join(sorted(bases))})
        cls = items[0]["cls"] if len(items) == 1 else "group"
        rows.append({"key": canon(w2), "class": cls,
                     "d1_word": items[0]["word"] if len(items) == 1 else None,
                     "d1_items": items, "d2_word": w2,
                     "d1_n": sum(len(g1[it["word"]]) for it in items),
                     "d2_n": len(g2[w2]), "word_final": base})

    for w2 in sorted(g2):
        if w2 in used2:
            continue
        if args.slice == "pilot" and not w2.lower().startswith(PILOT_PREFIXES):
            continue  # OCR strays repaired into out-of-slice headwords (e.g. ТА РА -> гара)
        rows.append({"key": canon(w2), "class": "only2", "d1_word": None, "d1_items": [],
                     "d2_word": w2, "d1_n": 0, "d2_n": len(g2[w2]), "word_final": w2.lower()})
        if w2.lower().startswith("ж"):
            q_zh.append({"dict": 2, "word": w2, "def": (g2[w2][0].get("def2") or "")[:150]})

    with open(CK / "04_match_table.jsonl", "w", encoding="utf-8") as f:
        for i, r in enumerate(rows):
            r["match_id"] = f"m_{i:05d}"
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    RQ.mkdir(parents=True, exist_ok=True)
    for name, q in [("only1_verbs", q_verbs), ("zh_dzh_unmatched", q_zh), ("spelling_conflicts", q_spell)]:
        with open(RQ / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in q:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    cls = Counter(r["class"] for r in rows)
    report = {"rows": len(rows), "classes": dict(cls),
              "queue_only1_verbs": len(q_verbs), "queue_zh_dzh": len(q_zh),
              "queue_spelling": len(q_spell)}
    json.dump(report, open(CK / "qa" / "s3_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

def decide_word(w1: str, w2: str, match_class: str):
    """Apply linguist rules -> final word form; returns (word, review_reasons).

    Built from the dict1 display form (it preserves ё reliably; dict2 OCR loses it),
    with the linguist's unification rules applied where dict2 disagrees:
      дж-(d1) / ж-(d2) word-initial  -> j
      -б(d1) / -п(d2) word-final     -> b
    Verbs: dict2 imperative form wins outright (dict1 shows only the infinitive).
    """
    a, b = w1.lower(), w2.lower()
    if match_class == "verb":
        out = b
        # J-rule applies to verbs as well: джабылыргъа + жабыл -> jабыл
        if a.startswith("дж") and b.startswith("ж") and not b.startswith("дж"):
            out = "j" + out[1:]
        # final б(d1 stem)/п(d2 imperative) -> b ; restore ё lost by dict2 OCR
        cand = next((c for c in verb_stem_candidates(a) if canon(c) == canon(b)), None)
        if cand:
            if cand.endswith("б") and out.endswith("п"):
                out = out[:-1] + "b"
            src = cand[2:] if cand.startswith("дж") and out.startswith("j") else cand
            dst_tail = out[1:] if out.startswith("j") else out
            if len(src) == len(dst_tail) and "ё" in src:
                fixed = "".join(s if (s == "ё" and d == "е") else d for s, d in zip(src, dst_tail))
                out = (out[0] + fixed) if out.startswith("j") else fixed
        return out, []
    if a == b:
        return a, []
    out = a
    if a.startswith("дж") and b.startswith("ж") and not b.startswith("дж"):
        out = "j" + out[2:]
    if out and b and out[-1] == "б" and b[-1] == "п":
        out = out[:-1] + "b"
    # verify residual difference is only ё/е (dict2 OCR) — else flag for review
    chk = out.replace("j", "ж", 1) if out.startswith("j") else out
    chk = chk[:-1] + "п" if chk.endswith("b") else chk
    reasons = []
    if canon(chk) != canon(b):
        reasons.append("residual_spelling_diff")
    return out, reasons

if __name__ == "__main__":
    main()
