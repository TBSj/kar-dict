# -*- coding: utf-8 -*-
"""S10: restore dict-1 hyphenated headwords split by the qmos export.

КБРС-1989, «О структуре словаря» п. 1: «Каждое слово (в том числе и сложное слово,
пишущееся через дефис) со всем относящимся к нему материалом образует самостоятельную
словарную статью».  The qmos OCR export cut such headwords at the hyphen: key «эт»,
value «-джен родственник(и)».  The pipeline then treated them as material of «эт»
(false homonyms ат5–ат10, glosses glued to the wrong word: эт1 4)… -джен).

Phases (each idempotent, files under checkpoints/shards/s10/):
  val-prep    qmos values starting with «-…» -> val_in/batch_NN.json (headword-boundary check by agents)
  parse-prep  val_out -> items.jsonl (+ deterministic parse of trivial items) and s0_in/ batches
              (same S0 prompt, tilde expanded to the restored headword with stem voicing)
  plan        s0_out -> plan.json: target corpus entry for each restored word, host surgery,
              complex groups for S4-style merge (s4_in/), unresolved surgery (surg_in/)
  apply       plan (+ s4_out/, surg_out/) -> checkpoints/06_lextagged.jsonl, qa/s10_changes.jsonl
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S10 = CK / "shards" / "s10"
QMOS = ROOT / "sources" / "1" / "qmos_def_32499.txt"
F06 = CK / "06_lextagged.jsonl"

RE_TAIL = re.compile(r"^-\s*([а-яёА-ЯЁ]+(?:-[а-яёА-ЯЁ]+)*)")
RE_ROMAN = re.compile(r"^@?(I{1,3}|IV|V|VI{0,3})#?\s*")
RE_DECL = re.compile(r"^\s*\((-?[а-яё]{1,4})\)\s*")
VOWELS = "аеёиоуыэюяў"
SUB = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
       "misc1_stem_note", "misc1_variants", "misc2_citations",
       "misc2_citations_periodical", "misc2_citations_collection",
       "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
       "misc2_gram_note"]


def kj(s):
    return (s.replace("кь", "къ").replace("гь", "гъ").replace("Кь", "Къ")
             .replace("Гь", "Гъ").replace("КЬ", "КЪ").replace("ГЬ", "ГЪ"))


def base_of(w):
    return re.sub(r"\d+$", "", w)


def voiced(word, decl):
    """КБРС п. 2: with a voicing hint (-гъы, -ги, -гю …) the tilde before a vowel
    stands for the stem with voiced final consonant: ёзек (-ги) ~и = ёзеги."""
    d = kj((decl or "").lstrip("-"))
    if d.startswith("гъ") and word.endswith("къ"):
        return word[:-2] + "гъ"
    if d.startswith("г") and not d.startswith("гъ") and word.endswith("к") and not word.endswith("къ"):
        return word[:-1] + "г"
    return None


def expand_tilde(text, word, decl):
    """S0a clean_markup with stem voicing before vowel-initial suffixes."""
    v = voiced(word, decl)
    if v:
        text = re.sub(r"~(?=[" + VOWELS + "])", v, text)
    t = text.replace("~", word)
    t = re.sub(r"[@#$%]", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ([,;:.!?)])", r"\1", t)
    t = re.sub(r"\( ", "(", t)
    return t.strip()


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def save_jsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def tail_items():
    """qmos values starting with '-word', restricted to seqids kept by S0a dedup."""
    q = json.load(open(QMOS, encoding="utf-8"))
    kept = {json.loads(l)["seqid"] for l in open(CK / "01_dict1_preparsed.jsonl", encoding="utf-8")}
    out = []
    for k, v in q.items():
        x, sid = k.rsplit("_", 1)
        sid = int(sid)
        m = RE_TAIL.match(v.strip())
        if not m or sid not in kept:
            continue
        out.append({"sid": sid, "X": x, "raw": v.strip(), "naive_Y": m.group(1),
                    "naive_headword": kj(f"{x}-{m.group(1)}").lower()})
    return out


# ------------------------------------------------------------------ val-prep
def val_prep(bs=190):
    items = tail_items()
    d = S10 / "val_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    for i in range(0, len(items), bs):
        payload = [{"sid": it["sid"], "key_word": it["X"], "raw": it["raw"][:220],
                    "naive_headword": it["naive_headword"]} for it in items[i:i + bs]]
        json.dump(payload, open(d / f"batch_{i // bs:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps({"tail_items": len(items), "batches": (len(items) + bs - 1) // bs}))


# ------------------------------------------------------------------ parse-prep
def load_decisions():
    """validator decisions, overridden by the verifier where it disagreed and by
    manual overrides (shards/s10/val_overrides.json: {sid: {is_hyphen, cut, headword, why}})"""
    dec = {}
    for f in sorted((S10 / "val_out").glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            dec[it["sid"]] = dict(it, src="validator")
    for f in sorted((S10 / "val_verify").glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            if it.get("verdict") == "disagree":
                dec[it["sid"]] = {"sid": it["sid"], "is_hyphen": it["is_hyphen"], "cut": it.get("cut", ""),
                                  "headword": it.get("headword", ""), "note": it.get("reason", ""), "src": "verifier"}
    ov = S10 / "val_overrides.json"
    if ov.exists():
        for k, it in json.load(open(ov, encoding="utf-8")).items():
            dec[int(k)] = dict(it, sid=int(k), src="manual")
    return dec


def parse_prep(bs=40):
    items = tail_items()
    dec = load_decisions()
    missing = [it["sid"] for it in items if it["sid"] not in dec]
    assert not missing, f"no decision for {len(missing)} items: {missing[:10]}"
    out, s0 = [], []
    for it in items:
        d = dec[it["sid"]]
        rec = {"key": str(it["sid"]), "sid": it["sid"], "X": it["X"], "raw": it["raw"], "decision_src": d["src"],
               "is_hyphen": bool(d["is_hyphen"]), "note": d.get("note", ""), "typo_fixed": bool(d.get("typo_fixed"))}
        if not rec["is_hyphen"]:
            out.append(rec)
            continue
        cut = d["cut"]
        assert it["raw"].startswith(cut) and cut.startswith("-"), (it["sid"], cut, it["raw"][:40])
        W = kj(d["headword"].strip().lower())
        assert "-" in W, (it["sid"], W)
        rest = d.get("rest_override") or it["raw"][len(cut):].strip()
        hom = ""
        m = RE_ROMAN.match(rest)
        if m and m.group(1):
            hom, rest = m.group(1), rest[m.end():]
        decl = ""
        md = RE_DECL.match(rest)
        if md:
            decl, rest = md.group(1), rest[md.end():]
        if not decl:  # S3 fallback: hint glued without dash further in the first 40 chars
            m2 = re.search(r"\((-?г[ъь]?[ыиу]|-?[дн]и|-?[гк]и)\)", rest[:40])
            decl = m2.group(1).lstrip("-") if m2 else ""
        clean = kj(expand_tilde(rest, W, decl))
        trivial = "@" not in rest and "$" not in rest and len(rest) <= 80 and ";" not in rest
        rec.update(W_print=W, cut=cut, rest=rest, hom=hom, decl=decl, clean=clean, trivial=trivial)
        if trivial:
            rec["parsed"] = {"tags": "", "def1": clean, "misc1": "", "flags": []}
        else:
            s0.append({"seqid": it["sid"], "word": W, "hom": hom, "decl": decl, "text": clean})
        out.append(rec)
        for n, x in enumerate(d.get("extra") or [], 1):
            out.append({"key": f"{it['sid']}.{n}", "sid": it["sid"], "X": it["X"], "raw": it["raw"],
                        "decision_src": "manual", "is_hyphen": True, "extra": True, "note": x.get("note", ""),
                        "typo_fixed": False, "W_print": kj(x["headword"].lower()), "cut": "", "rest": "",
                        "hom": "", "decl": x.get("decl", ""), "clean": "", "trivial": True,
                        "parsed": dict(x["parsed"], flags=[])})
    save_jsonl(S10 / "items.jsonl", out)
    d = S10 / "s0_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    for i in range(0, len(s0), bs):
        json.dump(s0[i:i + bs], open(d / f"batch_{i // bs:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps({"items": len(out), "hyphen": sum(r["is_hyphen"] for r in out),
                      "not_hyphen": sum(not r["is_hyphen"] for r in out),
                      "extra": sum(1 for r in out if r.get("extra")),
                      "trivial": sum(r.get("trivial", False) for r in out), "s0_llm": len(s0),
                      "s0_batches": (len(s0) + bs - 1) // bs,
                      "decision_src": Counter(r["decision_src"] for r in out),
                      "voiced_tildes": sum(1 for r in out if r.get("decl") and voiced(r["W_print"], r["decl"])
                                           and re.search(r"~[" + VOWELS + "]", r.get("rest", "")))},
                     ensure_ascii=False, default=dict))


# ------------------------------------------------------------------ plan
RE_INF = re.compile(r"(ргъа|рге)$")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}


def fold(w):
    w = kj(base_of(w).lower()).replace("ё", "е").replace("дж", "j").replace("ж", "j")
    return w.replace("b", "п").replace("б", "п")


def verb_stem_candidates(inf):
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


def normalize_headword(W, es_index):
    """КБРС print form -> corpus headword: verbs as imperative stems, component-initial
    дж -> j (native; kept for loanwords attested only with дж), кь/гь fixed."""
    w1map, bases, verb2 = es_index["w1map"], es_index["bases"], es_index["verb2"]
    notes, comps = [], []
    for c in W.split("-"):
        if RE_INF.search(c) and len(c) > 5:
            if c in w1map and len(w1map[c]) == 1:
                c = next(iter(w1map[c]))
            else:
                cands = verb_stem_candidates(c)
                hit = [x for x in cands if fold(x) in verb2]
                if hit:
                    c = next(b for b in bases.get(fold(hit[0]), [hit[0]]))
                else:
                    c = cands[1] if len(cands) > 1 and cands[0][-1] in "ыиую" else cands[0]
                    notes.append(f"verb_stem_guess:{c}")
            c = base_of(c)
        if c.startswith("дж"):
            cj = "j" + c[2:]
            if c in bases.get(fold(c), set()) and cj not in bases.get(fold(c), set()):
                notes.append(f"kept_dzh:{c}")
            else:
                c = cj
        comps.append(c)
    return "-".join(comps), notes


def corpus_index(es):
    w1map = defaultdict(set)
    bases = defaultdict(set)
    verb2 = set()
    for e in es:
        b = base_of(e["word"])
        bases[fold(b)].add(b)
        if e.get("word1_orig"):
            w1map[kj(e["word1_orig"].lower())].add(b)
        if "эт" in (e.get("tags") or "") and e.get("src2"):
            verb2.add(fold(b))
    return {"w1map": w1map, "bases": bases, "verb2": verb2}


def plan():
    es = load_jsonl(F06)
    byid = {e["entry_id"]: e for e in es}
    idx = corpus_index(es)
    items = [r for r in load_jsonl(S10 / "items.jsonl") if r["is_hyphen"]]
    parsed = {}
    for f in sorted((S10 / "s0_out").glob("batch_*.json")):
        for oe in json.load(open(f, encoding="utf-8"))["entries"]:
            parsed[oe["seqid"]] = oe
    old = {}
    for l in open(CK / "01_dict1_parsed.jsonl", encoding="utf-8"):
        p = json.loads(l)
        old[p["seqid"]] = p
    bysrc1 = defaultdict(list)
    byfold = defaultdict(list)
    for e in es:
        for s in (e.get("src1") or []):
            bysrc1[int(s)].append(e["entry_id"])
        byfold[fold(e["word"])].append(e["entry_id"])

    restored, skipped = [], []
    for r in items:
        sid = r["sid"]
        if r["trivial"]:
            P = dict(r["parsed"])
        elif sid in parsed and not r.get("extra"):
            oe = parsed[sid]
            P = {"tags": oe.get("tags", ""), "def1": oe.get("def1", ""), "misc1": oe.get("misc1", ""),
                 "flags": oe.get("flags", [])}
        else:
            skipped.append({"sid": sid, "why": "no S0 parse"})
            continue
        Wn, notes = normalize_headword(r["W_print"], idx)
        fW = fold(Wn)
        hosts = [] if r.get("extra") else bysrc1.get(sid, [])
        if any(fold(byid[h]["word"]) == fW for h in hosts):
            skipped.append({"sid": sid, "why": "already restored in corpus", "W": Wn,
                            "hosts": [byid[h]["word"] for h in hosts]})
            continue
        targets = [t for t in byfold.get(fW, []) if t not in hosts]
        d1_conf = [t for t in targets if byid[t].get("src1")]
        restored.append({"key": r["key"], "sid": sid, "W_print": r["W_print"], "W": Wn, "fold": fW, "notes": notes,
                         "typo_fixed": r.get("typo_fixed", False), "item_note": r.get("note", ""),
                         "hom": r.get("hom", ""), "decl": r.get("decl", ""), "P": P,
                         "hosts": hosts, "d2_targets": [t for t in targets if not byid[t].get("src1")],
                         "d1_conflicts": d1_conf})

    # host surgery: remove the old (S0) parse of the item from shared hosts
    def frag_norm(s):
        return " ".join(kj(s or "").split())
    surgery, surg_llm = [], []
    for rr in restored:
        o = old.get(rr["sid"], {})
        for h in rr["hosts"]:
            e = byid[h]
            src1 = [int(s) for s in e.get("src1") or []]
            kind = ("solo" if src1 == [rr["sid"]] else "shared") + ("+d2" if e.get("src2") else "")
            ops, ok = [], True
            if kind.startswith("shared"):
                for f in ("tags", "def1", "misc1"):
                    frag = frag_norm(o.get(f))
                    if not frag:
                        continue
                    where = [g for g in ("def1", "misc1", "tags") if frag in frag_norm(e.get(g))]
                    if where:
                        ops.append({"field": where[0], "remove": frag})
                    else:
                        ok = False
            surgery.append({"key": rr["key"], "sid": rr["sid"], "host": h, "host_word": e["word"], "kind": kind,
                            "ops": ops, "deterministic": ok})
            if not ok:
                surg_llm.append({"id": f"{h}#{rr['sid']}", "host_word": e["word"],
                                 "host": {k: e.get(k, "") for k in ("tags", "def1", "misc1")},
                                 "remove_item": {"restored_headword": rr["W_print"],
                                                 **{k: o.get(k, "") for k in ("tags", "def1", "misc1")}},
                                 "other_d1_sources": [s for s in src1 if s != rr["sid"]]})
    # groups by restored word
    groups = defaultdict(lambda: {"d1": [], "d2": set(), "conf": set()})
    for rr in restored:
        g = groups[rr["fold"]]
        g["d1"].append(rr["key"])
        g["d2"].update(rr["d2_targets"])
        g["conf"].update(rr["d1_conflicts"])
    s4 = []
    rmap = {rr["key"]: rr for rr in restored}
    plan_groups = []
    for fW, g in groups.items():
        complex_ = len(g["d1"]) > 1 or len(g["d2"]) > 1 or g["conf"]
        plan_groups.append({"fold": fW, "d1": g["d1"], "d2": sorted(g["d2"]), "conf": sorted(g["conf"]),
                            "complex": bool(complex_)})
        if complex_:
            W = rmap[g["d1"][0]]["W"]
            s4.append({
                "match_id": f"s10_{len(s4):04d}", "word_final": W,
                "word_base_map": {rmap[s]["W_print"]: rmap[s]["W"] for s in g["d1"]} | {"_d2only": W},
                "d1": [{"seqid": rmap[s]["sid"], "_key": s, "d1_word": rmap[s]["W_print"], "word_base": rmap[s]["W"],
                        "hom_src": rmap[s]["hom"], "tags": rmap[s]["P"]["tags"], "decl": rmap[s]["decl"],
                        "def1": rmap[s]["P"]["def1"], "misc1": rmap[s]["P"]["misc1"]} for s in g["d1"]]
                      + [{"seqid": int(byid[c]["src1"][0]), "d1_word": byid[c].get("word1_orig") or byid[c]["word"],
                          "word_base": base_of(byid[c]["word"]), "hom_src": "", "tags": byid[c].get("tags", ""),
                          "decl": byid[c].get("decl", ""), "def1": byid[c].get("def1", ""),
                          "misc1": byid[c].get("misc1", ""), "_entry_id": c} for c in sorted(g["conf"])],
                "d2": [{"source_ids": byid[t]["src2"], "hom": str(byid[t].get("hom_rank", "")),
                        "tags": byid[t].get("tags", ""), "def2": byid[t].get("def2", ""),
                        "misc2": byid[t].get("misc2", ""), "_entry_id": t} for t in sorted(g["d2"])],
            })
    json.dump({"restored": restored, "skipped": skipped, "surgery": surgery, "groups": plan_groups},
              open(S10 / "plan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for sub, rows, bs in (("s4_in", s4, 6), ("surg_in", surg_llm, 20)):
        d = S10 / sub
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("batch_*.json"):
            f.unlink()
        for i in range(0, len(rows), bs):
            json.dump(rows[i:i + bs], open(d / f"batch_{i // bs:02d}.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
    print(json.dumps({
        "restored": len(restored), "skipped": len(skipped), "skip_why": Counter(s["why"] for s in skipped),
        "groups": len(plan_groups), "complex_groups": len(s4),
        "simple_merge_into_d2": sum(1 for g in plan_groups if not g["complex"] and g["d2"]),
        "simple_new": sum(1 for g in plan_groups if not g["complex"] and not g["d2"]),
        "host_kinds": Counter(s["kind"] for s in surgery),
        "surgery_llm": len(surg_llm),
        "notes": Counter(n.split(":")[0] for rr in restored for n in rr["notes"]),
    }, ensure_ascii=False, indent=1, default=dict))


# ------------------------------------------------------------------ apply
def norm_ws(s):
    return " ".join(kj(s or "").split())


def cleanup(s):
    """tidy separators left after cutting a fragment out of a merged d1 field"""
    s = re.sub(r"\s*◊\s*(?=[;|]|$)", "", s)              # pipeline-inserted ◊ left alone
    s = re.sub(r"(^|[;|]\s*)◊\s*", r"\1", s)
    for _ in range(3):
        s = re.sub(r";\s*;", ";", s)
        s = re.sub(r"\|\|\s*\|\|", "||", s)
        s = re.sub(r"\s+([;,])", r"\1", s)
    s = re.sub(r"^[\s;,|◊◆]+|[\s;,|◊◆]+$", "", s)
    return " ".join(s.split())


SNAP = ("word", "dict_id", "tags", "def1", "def2", "misc1", "src1", "src2", "word1_orig", "word2_orig")


def snap(e):
    return {k: (e.get(k)[:300] if isinstance(e.get(k), str) else e.get(k)) for k in SNAP}


def apply():
    es = load_jsonl(F06)
    byid = {e["entry_id"]: e for e in es}
    P = json.load(open(S10 / "plan.json", encoding="utf-8"))
    rmap = {r["key"]: r for r in P["restored"]}
    d2parsed = defaultdict(list)
    for l in open(CK / "03_dict2_parsed.jsonl", encoding="utf-8"):
        p = json.loads(l)
        for s in p.get("source_ids") or []:
            d2parsed[s].append(p)
    surg_llm = {}
    for f in sorted((S10 / "surg_out").glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            surg_llm[it["id"]] = it
    s4_out = {}
    for f in sorted((S10 / "s4_out").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8"))["groups"]:
            s4_out[g["match_id"]] = g
    s4_in = {}
    for f in sorted((S10 / "s4_in").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8")):
            s4_in[g["match_id"]] = g

    before = {}
    touched, dropped, new_entries, touched_bases, needs_lextag = set(), set(), [], set(), []
    unresolved = []

    def touch(e, fl):
        if e["entry_id"] not in before and e.get("entry_id"):
            before[e["entry_id"]] = snap(e)
        touched.add(e["entry_id"])
        touched_bases.add(base_of(e["word"]))
        e.setdefault("flags", [])
        if fl not in e["flags"]:
            e["flags"].append(fl)

    def newcard(rr, P_):
        e = {"word": rr["W"], "word_base": rr["W"], "dict_id": "1", "tags": P_["tags"], "def1": P_["def1"],
             "def2": "", "misc1": P_["misc1"], "misc2": "", "src1": [rr["sid"]], "src2": [],
             "word1_orig": rr["W_print"], "word2_orig": None, "decl": rr["decl"],
             "hom_rank": ROMAN.get(rr["hom"], 99), "lextag": "", "lextag_conf": "",
             "flags": ["hyphen_restored"] + [f for f in P_.get("flags", []) if f]}
        new_entries.append(e)
        touched_bases.add(rr["W"])
        return e

    def add_item_flags(e, rr):
        for f in rr["P"].get("flags") or []:
            if f and f not in e["flags"]:
                e["flags"].append(f)
        if rr.get("typo_fixed") and "source_typo_fixed" not in e["flags"]:
            e["flags"].append("source_typo_fixed")

    # 1. detach the item from its hosts
    solo_hosts = {}
    warnings = []
    tail_sids = {r["sid"] for r in P["restored"]}
    # agent-made surgeries rewrite whole fields, so they go first; deterministic cuts of other
    # restored words in the same host are then applied on top of the agent's text
    for s in sorted(P["surgery"], key=lambda x: x["deterministic"]):
        e = byid[s["host"]]
        if s["kind"] == "solo":
            solo_hosts[s["key"]] = s["host"]
            continue
        all_tails = {int(x) for x in e.get("src1") or []} <= tail_sids
        if s["kind"] == "shared" and all_tails:
            touch(e, "hyphen_restored")          # every d1 source of this card was a split word
            dropped.add(e["entry_id"])
            continue
        touch(e, "hyphen_detached")
        if s["kind"] == "solo+d2" or (s["kind"] == "shared+d2" and all_tails):
            tags2 = ""
            for src in e.get("src2") or []:
                for p in d2parsed.get(src, []):
                    if fold(p["word"]) == fold(e.get("word2_orig") or e["word"]):
                        tags2 = p.get("tags", "")
            for f in ("def1", "misc1", "decl"):
                e[f] = ""
            e["src1"], e["word1_orig"], e["dict_id"] = [], None, "2"
            e["tags"] = tags2 if tags2 else e.get("tags", "")
            continue
        # shared host: cut the fragments of the item's old S0 parse
        key = f"{s['host']}#{s['sid']}"
        if s["deterministic"]:
            for op in s["ops"]:
                txt = norm_ws(e.get(op["field"]))
                if op["remove"] not in txt:      # identical fragment already cut for another item
                    warnings.append({"key": key, "op": op})
                    continue
                e[op["field"]] = cleanup(txt.replace(op["remove"], " ", 1))
        elif key in surg_llm:
            for f in ("tags", "def1", "misc1"):
                e[f] = surg_llm[key][f]
        else:
            unresolved.append(key)
            e["flags"].append("needs_review")
        e["src1"] = [x for x in e.get("src1") or [] if int(x) != s["sid"]]
        if not e["src1"]:
            e["word1_orig"] = None
            e["dict_id"] = "2" if e.get("src2") else "1"

    # 2. place the restored words
    for g in P["groups"]:
        if g["complex"]:
            continue
        key = g["d1"][0]
        rr = rmap[key]
        sid = rr["sid"]
        Pp = rr["P"]
        host = solo_hosts.get(key)
        if g["d2"]:
            t = byid[g["d2"][0]]
            touch(t, "hyphen_restored")
            t["dict_id"] = "both"
            t["def1"], t["misc1"], t["decl"] = Pp["def1"], Pp["misc1"], rr["decl"]
            t["src1"], t["word1_orig"] = [sid], rr["W_print"]
            if Pp["tags"] and Pp["tags"] not in (t.get("tags") or ""):
                t["tags"] = f"{t['tags']}; {Pp['tags']}" if t.get("tags") else Pp["tags"]
            assert fold(t["word"]) == fold(rr["W"]), (t["word"], rr["W"])
            touched_bases.add(base_of(t["word"]))
            W = rr["W"]
            if W.endswith("б") and base_of(t["word"]).endswith("п"):   # S3 b-rule: -б(d1) / -п(d2)
                W = W[:-1] + "b"
            t["word"] = t["word_base"] = W
            touched_bases.add(W)
            t["flags"] = [f for f in t["flags"] if f != "no_d1_pair"]
            add_item_flags(t, rr)
            if host:
                touch(byid[host], "hyphen_restored")
                dropped.add(host)
        elif host:
            e = byid[host]
            touch(e, "hyphen_restored")
            e["word"] = e["word_base"] = rr["W"]
            e["tags"], e["def1"], e["misc1"], e["decl"] = Pp["tags"], Pp["def1"], Pp["misc1"], rr["decl"]
            e["word1_orig"] = rr["W_print"]
            e["hom_rank"] = ROMAN.get(rr["hom"], 99)
            add_item_flags(e, rr)
            touched_bases.add(rr["W"])
        else:
            add_item_flags(newcard(rr, Pp), rr)
            needs_lextag.append(new_entries[-1])

    # 3. complex groups (S4-style agent output)
    for mid, gin in s4_in.items():
        gout = s4_out.get(mid)
        if not gout:
            unresolved.append(mid)
            continue
        want1 = {d["seqid"] for d in gin["d1"]}
        keys1 = [d["_key"] for d in gin["d1"] if d.get("_key")]
        want2 = {s for d in gin["d2"] for s in d["source_ids"]}
        got1 = {int(s) for x in gout["entries"] for s in x.get("src1") or []}
        got2 = {s for x in gout["entries"] for s in x.get("src2") or []}
        assert want1 <= got1 and want2 <= got2, (mid, want1 - got1, want2 - got2)
        existing = {d["_entry_id"]: d for d in gin["d2"]} | {d["_entry_id"]: d for d in gin["d1"] if d.get("_entry_id")}
        used = set()
        for x in gout["entries"]:
            match = next((eid for eid in existing if eid not in used and
                          (set(byid[eid].get("src2") or []) & set(x.get("src2") or []) or
                           {int(s) for s in byid[eid].get("src1") or []} & {int(s) for s in x.get("src1") or []})), None)
            if match:
                e = byid[match]
                used.add(match)
                touch(e, "hyphen_restored")
            else:
                e = {"lextag": "", "lextag_conf": "", "flags": ["hyphen_restored"]}
                new_entries.append(e)
                needs_lextag.append(e)
            for k in ("tags", "def1", "def2", "misc1", "misc2", "decl", "word1_orig", "word2_orig"):
                e[k] = x.get(k) or ("" if k not in ("word1_orig", "word2_orig") else None)
            e["src1"] = [int(s) for s in x.get("src1") or []]
            e["src2"] = x.get("src2") or []
            e["dict_id"] = "both" if e["src1"] and e["src2"] else ("1" if e["src1"] else "2")
            e["hom_rank"] = x.get("hom_rank", 99)
            e["word"] = e["word_base"] = x["word_base"]
            for f in x.get("flags") or []:
                if f not in e["flags"]:
                    e["flags"].append(f)
            touched_bases.add(x["word_base"])
        for eid in existing:
            if eid not in used:
                touch(byid[eid], "hyphen_restored")
                dropped.add(eid)
        for k1 in keys1:
            h = solo_hosts.get(k1)
            if h and h not in used:
                touch(byid[h], "hyphen_restored")
                dropped.add(h)

    # 4. finalize: drop, ids, digits
    es = [e for e in es if e["entry_id"] not in dropped] + new_entries
    maxid = max(int(e["entry_id"][2:]) for e in es if e.get("entry_id"))
    for i, e in enumerate(new_entries, 1):
        e["entry_id"] = f"e_{maxid + i:05d}"
        touched.add(e["entry_id"])
    grp = defaultdict(list)
    for e in es:
        b = base_of(e["word"])
        if b in touched_bases:
            grp[b].append(e)
    renamed = {}
    for b, g in grp.items():
        g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both", x["entry_id"]))
        for i, x in enumerate(g, 1):
            neww = b if len(g) == 1 else f"{b}{i}"
            if x["word"] != neww:
                renamed[x["entry_id"]] = (x["word"], neww)
                if x["entry_id"] not in before and x["entry_id"] not in {n["entry_id"] for n in new_entries}:
                    before[x["entry_id"]] = snap(x)
                touched.add(x["entry_id"])
            x["word"] = neww
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, f"collisions: {dup[:10]}"
    for e in es:
        if e["entry_id"] in touched:
            for k in SUB:
                e.pop(k, None)
    save_jsonl(F06, es)
    byid2 = {e["entry_id"]: e for e in es}
    changes = []
    for eid in sorted(touched | dropped):
        changes.append({"entry_id": eid,
                        "action": "deleted" if eid in dropped else ("new" if eid not in before else "changed"),
                        "before": before.get(eid), "after": snap(byid2[eid]) if eid in byid2 else None})
    save_jsonl(CK / "qa" / "s10_changes.jsonl", changes)
    json.dump([{"entry_id": e["entry_id"], "word": e["word"], "tags": e.get("tags", ""),
                "def1": e.get("def1", ""), "def2": e.get("def2", "")} for e in needs_lextag],
              open(S10 / "lextag_in.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"entries": len(es), "touched": len(touched), "deleted": len(dropped),
                      "new": len(new_entries), "renamed_digits": len(renamed), "needs_lextag": len(needs_lextag),
                      "unresolved": unresolved, "warnings": warnings,
                      "actions": Counter(c["action"] for c in changes)},
                     ensure_ascii=False, indent=1, default=dict))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["val-prep", "parse-prep", "plan", "apply"])
    a = ap.parse_args()
    if a.phase == "val-prep":
        val_prep()
    elif a.phase == "parse-prep":
        parse_prep()
    elif a.phase == "plan":
        plan()
    elif a.phase == "apply":
        apply()
