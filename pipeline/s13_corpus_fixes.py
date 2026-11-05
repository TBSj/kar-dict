# -*- coding: utf-8 -*-
"""S13: deterministic corpus repairs found by the 2026-11-04 sources survey (step 1б).

  word2orig  entries split out of one ТСКБЯ record (406 records -> 863 entries) had all
             inherited the record's word2_orig (гюттюлюк/гюх/гямпир -> «гяпчи»); take each
             entry's own headword from 03_dict2_parsed.jsonl (same source_ids, same word).
  et2        ёт2 «проходить» carries «ат.» (noun) — a typo of the printed ТСКБЯ
             («ЁТ² ат. 1. Проходить…», т. 1 PDF-с. 740); the verb gets «эт.».
  voicing    dict-1 examples: «~» before a vowel-initial suffix stands for the stem with a
             voiced final consonant when the entry has a voicing hint (-гъы, -ги, -гю …)
             (КБРС, «О структуре словаря», п. 2: ёзек (-ги) … агъачны ~и = ёзеги).  S0a
             expanded every «~» to the bare headword (хапчюкю instead of хапчюгю).
  flags      no_russian_def := def1 and def2 both empty (the S2 flag meant «the ТСКБЯ
             article has no Russian part» and survived merges with dict-1 translations).
Every phase logs its changes to checkpoints/qa/s13_<phase>.jsonl.
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
F06 = CK / "06_lextagged.jsonl"
VOWELS = "аеёиоуыэюяў"


def load():
    return [json.loads(l) for l in open(F06, encoding="utf-8")]


def save(es):
    with open(F06, "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def log(name, rows):
    with open(CK / "qa" / f"s13_{name}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def flag(e, fl):
    e.setdefault("flags", [])
    if fl not in e["flags"]:
        e["flags"].append(fl)


def kj(s):
    return s.replace("кь", "къ").replace("гь", "гъ")


def fold(w):
    w = re.sub(r"\d+$", "", (w or "").lower()).replace("ё", "е")
    w = w.replace("дж", "j").replace("ж", "j").replace("b", "п").replace("б", "п")
    return kj(w)


def to_d2(w):
    """corpus headword -> dict-2 (Balkar) spelling for word2_orig fallbacks"""
    return re.sub(r"\d+$", "", w).replace("j", "ж").replace("b", "п")


def word2orig():
    es = load()
    bysrc = defaultdict(list)
    for l in open(CK / "03_dict2_parsed.jsonl", encoding="utf-8"):
        p = json.loads(l)
        for s in p.get("source_ids") or []:
            bysrc[s].append(p)
    rows = []
    for e in es:
        if not e.get("src2"):
            continue
        w2 = e.get("word2_orig")
        if w2 and fold(w2) == fold(e["word"]):
            continue
        cands = {p["word"] for s in e["src2"] for p in bysrc.get(s, [])}
        m = sorted({w for w in cands if fold(w) == fold(e["word"])})
        if len(m) == 1:
            new, how = m[0], "own_headword_in_record"
        elif not m:
            new, how = to_d2(e["word"]), "corpus_word_in_d2_spelling(ocr_garbage_in_parse)"
        else:
            continue
        rows.append({"entry_id": e["entry_id"], "word": e["word"], "old": w2, "new": new, "how": how})
        e["word2_orig"] = new
        flag(e, "word2_orig_fixed")
    save(es)
    log("word2orig", rows)
    print(json.dumps({"fixed": len(rows), "how": Counter(r["how"] for r in rows)}, ensure_ascii=False, default=dict))


def et2():
    es = load()
    rows = []
    for e in es:
        if e["entry_id"] == "e_39551":
            assert e["word"] == "ёт2" and e["tags"] == "ат." and e["def2"].startswith("1. Проходить"), e
            rows.append({"entry_id": e["entry_id"], "word": e["word"], "field": "tags", "old": e["tags"],
                         "new": "эт.", "why": "опечатка ТСКБЯ: «ЁТ² ат.» у глагола «проходить» (т. 1, PDF-с. 740)"})
            e["tags"] = "эт."
            flag(e, "source_typo_fixed")
    assert rows, "ёт2 not found (already fixed?)"
    save(es)
    log("et2", rows)
    print(rows)


def voiced_stem(word, decl):
    d = kj((decl or "").strip().lstrip("-"))
    if d.startswith("гъ") and word.endswith("къ"):
        return word[:-2] + "гъ"
    if d.startswith("г") and not d.startswith("гъ") and word.endswith("к") and not word.endswith("къ"):
        return word[:-1] + "г"
    return None


def voicing():
    """re-expand «~V» with the voiced stem, exactly as many times as the raw text has «~V»"""
    q = json.load(open(ROOT / "sources" / "1" / "qmos_def_32499.txt", encoding="utf-8"))
    raw_by_sid = {int(k.rsplit("_", 1)[1]): (k.rsplit("_", 1)[0], v) for k, v in q.items()}
    pre = {}
    for l in open(CK / "01_dict1_preparsed.jsonl", encoding="utf-8"):
        p = json.loads(l)
        pre[p["seqid"]] = p
    es = load()
    rows, skipped = [], Counter()
    for e in es:
        sids = [int(s) for s in (e.get("src1") or [])]
        if not sids or "hyphen_restored" in (e.get("flags") or []):
            continue
        # (unvoiced form, voiced form) -> expected count from the raw texts of this entry's sources
        need = Counter()
        for sid in sids:
            if sid not in raw_by_sid or sid not in pre:
                continue
            word, raw = raw_by_sid[sid]
            word = kj(word)
            decl = pre[sid].get("decl_hint") or ""
            if not decl:
                m = re.search(r"\((-?г[ъь]?[ыиуюе]|-?[дн]и|-?[гк]и)\)", raw[:60])
                decl = m.group(1) if m else ""
            v = voiced_stem(word, decl)
            if not v:
                continue
            for m in re.finditer(r"~([" + VOWELS + "])", raw):
                need[(word, v, m.group(1))] += 1
        if not need:
            continue
        for (word, v, vow), n in need.items():
            pat = re.compile(r"(?<![а-яёА-ЯЁ\-])" + re.escape(word) + "(?=" + vow + ")")
            for f in ("misc1", "def1"):
                txt = e.get(f) or ""
                hits = pat.findall(txt)
                already = len(re.findall(r"(?<![а-яёА-ЯЁ\-])" + re.escape(v) + "(?=" + vow + ")", txt))
                if not hits:
                    continue
                if len(hits) + already > n:
                    # more bare forms than tildes: some are genuine text — fix only if all are tilde slots
                    skipped["more_hits_than_tildes"] += 1
                    continue
                new = pat.sub(v, txt)
                rows.append({"entry_id": e["entry_id"], "word": e["word"], "field": f,
                             "form": f"{word}{vow}->{v}{vow}", "count": len(hits)})
                e[f] = new
                need[(word, v, vow)] -= len(hits)
                flag(e, "tilde_voicing_fixed")
                for k in [k for k in list(e) if k.startswith("misc1_")]:
                    e.pop(k, None)
    save(es)
    log("voicing", rows)
    print(json.dumps({"replacements": sum(r["count"] for r in rows), "entries": len({r["entry_id"] for r in rows}),
                      "skipped": skipped}, ensure_ascii=False, default=dict))


def flags():
    es = load()
    before = sum("no_russian_def" in (e.get("flags") or []) for e in es)
    for e in es:
        fl = [f for f in (e.get("flags") or []) if f != "no_russian_def"]
        if not (e.get("def1") or "").strip() and not (e.get("def2") or "").strip():
            fl.append("no_russian_def")
        e["flags"] = fl
    after = sum("no_russian_def" in e["flags"] for e in es)
    save(es)
    print(json.dumps({"no_russian_def_before": before, "after": after}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["word2orig", "et2", "voicing", "flags"])
    a = ap.parse_args()
    {"word2orig": word2orig, "et2": et2, "voicing": voicing, "flags": flags}[a.phase]()
