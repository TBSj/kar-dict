# -*- coding: utf-8 -*-
"""S10b: qmos «pseudo-keys» — article tails that the export turned into separate keys.

At column/letter boundaries the OCR export sometimes started a new key in the middle of an
article: дери_8024 is the tail of «джик I» (КБРС с. 249), болгъан_3904, муну_18163 …
In the corpus they became false homonyms (дери2 «до мельчайших подробностей»).
Candidates = keys out of alphabetical order with respect to BOTH neighbours (and sharing
≤2 leading letters with them), plus the cases already confirmed by the survey verifier.

  prep   -> shards/s10/pk_in/batch_NN.json  (context + estimated КБРС page for page checks)
  apply  shards/s10/pk_out -> 06_lextagged.jsonl (move tail text to the owner entry, drop the
         false homonym; rename garbled keys), qa/s10_pseudokeys.jsonl
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S10 = CK / "shards" / "s10"
QMOS = ROOT / "sources" / "1" / "qmos_def_32499.txt"
ALPH = ["а", "б", "в", "г", "гъ", "д", "дж", "е", "ё", "ж", "з", "и", "й", "к", "къ", "л", "м", "н", "нг", "о",
        "п", "р", "с", "т", "у", "ў", "ф", "х", "ц", "ч", "ш", "щ", "ъ", "ы", "ь", "э", "ю", "я"]
RANK = {a: i for i, a in enumerate(ALPH)}
KNOWN = [8024, 3904, 18163, 19502, 21750, 24364, 29409]   # confirmed by the survey verifier on the scan
# (seqid, КБРС page) anchors checked on the scan during the survey and S10
ANCHORS = [(1, 15), (1000, 42), (2207, 89), (7344, 228), (8024, 249), (12360, 368), (15156, 451),
           (18362, 456), (21428, 522), (22608, 551), (22656, 553), (29327, 716), (32104, 777), (32499, 788)]


def toks(w):
    w = re.sub(r"_\d+$", "", w).lower().replace("кь", "къ").replace("гь", "гъ").replace("ё", "е")
    w = re.sub(r"[^а-яў]", "", w)
    out, i = [], 0
    while i < len(w):
        d = w[i:i + 2]
        if d in ("гъ", "дж", "къ", "нг"):
            out.append(RANK[d])
            i += 2
        else:
            out.append(RANK.get(w[i], 99))
            i += 1
    return tuple(out)


def cp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def est_page(sid, dup_shift):
    """seqid -> printed page by interpolation; the duplicated Къ section (15157–17885)
    is skipped (dup_shift = seqids of duplicates before sid)."""
    s = sid - dup_shift
    for (a, pa), (b, pb) in zip(ANCHORS, ANCHORS[1:]):
        a2, b2 = a - (2729 if a > 15156 else 0), b - (2729 if b > 15156 else 0)
        if a2 <= s <= b2:
            return round(pa + (pb - pa) * (s - a2) / max(1, b2 - a2))
    return None


def prep():
    q = json.load(open(QMOS, encoding="utf-8"))
    ks = list(q)
    vs = [q[k] for k in ks]
    sids = [int(k.rsplit("_", 1)[1]) for k in ks]
    T = [toks(k) for k in ks]
    cands = set()
    for i in range(1, len(ks) - 1):
        if vs[i].lstrip().startswith("-"):
            continue
        if T[i - 1] <= T[i + 1] and not (T[i - 1] <= T[i] <= T[i + 1]):
            if cp(T[i], T[i - 1]) <= 2 and cp(T[i], T[i + 1]) <= 2:
                cands.add(i)
    pos = {s: i for i, s in enumerate(sids)}
    cands |= {pos[s] for s in KNOWN if s in pos}
    corpus = defaultdict(list)
    for l in open(CK / "06_lextagged.jsonl", encoding="utf-8"):
        e = json.loads(l)
        for s in e.get("src1") or []:
            corpus[int(s)].append({"entry_id": e["entry_id"], "word": e["word"], "dict_id": e["dict_id"],
                                   "src1": e.get("src1"), "def1": (e.get("def1") or "")[:160],
                                   "misc1": (e.get("misc1") or "")[:160]})
    items = []
    for i in sorted(cands):
        sid = sids[i]
        shift = 2729 if sid > 17885 else (sid - 15156 if sid > 15156 else 0)
        ctx = [{"sid": sids[j], "key": ks[j].rsplit("_", 1)[0], "value": vs[j][:200]}
               for j in range(max(0, i - 3), min(len(ks), i + 4)) if j != i]
        items.append({"sid": sid, "key": ks[i].rsplit("_", 1)[0], "value": vs[i][:400],
                      "neighbours": ctx, "kbrs_page_est": est_page(sid, shift),
                      "corpus_entries": corpus.get(sid, []), "known_pseudo": sid in KNOWN})
    d = S10 / "pk_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    BS = 12
    for i in range(0, len(items), BS):
        json.dump(items[i:i + BS], open(d / f"batch_{i // BS:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps({"candidates": len(items), "known": len(KNOWN), "batches": (len(items) + BS - 1) // BS},
                     ensure_ascii=False))


SUB = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
       "misc1_stem_note", "misc1_variants", "misc2_citations",
       "misc2_citations_periodical", "misc2_citations_collection",
       "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
       "misc2_gram_note"]
RE_INF = re.compile(r"(ргъа|рге)$")
MANUAL = {22315, 22352, 29409, 30302}                         # handled by s10_postfix.py (shared with real entries)
JOIN_SPACE = {24364}                            # «бокъланнган суу» + «терен кёрюнюр погов. …»
TEXT_FIX = {10236: [("ингекци", "инъекци")]}   # export turned нъ into нг inside the Russian text too


def kj(s):
    return (s or "").replace("кь", "къ").replace("гь", "гъ")


def base_of(w):
    return re.sub(r"\d+$", "", w)


def fold(w):
    w = kj(base_of(w).lower()).replace("ё", "е").replace("дж", "j").replace("ж", "j")
    return w.replace("b", "п").replace("б", "п")


def corpus_form(old_print, old_corpus_base, new_print):
    """apply the S3 transformation that turned the garbled print form into the corpus
    headword (verb stem, j for initial дж) to the corrected print form"""
    op, nb = kj(old_print.lower()), kj(new_print.lower())
    ob = old_corpus_base
    cut = None
    if RE_INF.search(op):                          # verb: corpus has the stem
        o2 = ("j" + op[2:]) if op.startswith("дж") and ob.startswith("j") else op
        if o2.startswith(ob):
            cut = len(o2) - len(ob)
    w = nb
    if w.startswith("дж"):                         # native дж -> j (corpus rule for dict-1 words)
        w = "j" + w[2:]
    if cut:
        tail = op[-cut:]
        if w.endswith(tail):
            w = w[:-cut]
    return w


def apply():
    items = {}
    for f in sorted((S10 / "pk_out").glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            items[it["sid"]] = it
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byid = {e["entry_id"]: e for e in es}
    bysrc = defaultdict(list)
    for e in es:
        for s in e.get("src1") or []:
            bysrc[int(s)].append(e)
    q = json.load(open(QMOS, encoding="utf-8"))
    qkey = {int(k.rsplit("_", 1)[1]): k.rsplit("_", 1)[0] for k in q}
    log, dropped, bases, touched = [], set(), set(), set()
    old_parse = {}
    for l in open(CK / "01_dict1_parsed.jsonl", encoding="utf-8"):
        x = json.loads(l)
        old_parse[x["seqid"]] = x

    def mark(e, fl):
        e.setdefault("flags", [])
        if fl not in e["flags"]:
            e["flags"].append(fl)
        touched.add(e["entry_id"])
        bases.add(base_of(e["word"]))

    for sid, it in items.items():
        v = it["verdict"]
        hosts = bysrc.get(sid, [])
        if v == "ok" or not hosts:
            continue
        if v == "pseudo_tail":
            owners = bysrc.get(int(it["owner_sid"]), [])
            if len(owners) != 1:
                log.append({"sid": sid, "verdict": v, "status": f"owner not unique ({len(owners)})"})
                continue
            o = owners[0]
            before = {k: o.get(k, "") for k in ("def1", "misc1")}
            for f, add in (("def1", it.get("tail_def1")), ("misc1", it.get("tail_misc1"))):
                add = kj((add or "").strip())
                if add:
                    sep = " " if sid in JOIN_SPACE else "; "     # tail continues the owner's last example
                    o[f] = f"{o[f]}{sep}{add}" if o.get(f) else add
            if sid not in [int(x) for x in o.get("src1") or []]:
                o["src1"] = list(o.get("src1") or []) + [sid]
            mark(o, "pseudokey_fixed")
            for h in hosts:
                if h is o:
                    continue
                src1 = [int(x) for x in h.get("src1") or []]
                if src1 == [sid] and not h.get("src2"):
                    dropped.add(h["entry_id"])
                    bases.add(base_of(h["word"]))
                elif src1 == [sid]:
                    for f in ("def1", "misc1", "decl"):
                        h[f] = ""
                    h["src1"], h["word1_orig"], h["dict_id"] = [], None, "2"
                    mark(h, "pseudokey_fixed")
                else:
                    o_parse = old_parse.get(sid, {})
                    cut_ok = True
                    for f in ("def1", "misc1", "tags"):
                        frag = " ".join(kj(o_parse.get(f) or "").split())
                        if not frag:
                            continue
                        txt = " ".join(kj(h.get(f) or "").split())
                        if frag in txt:
                            h[f] = re.sub(r"^[\s;,]+|[\s;,]+$", "", re.sub(r";\s*;", ";", txt.replace(frag, " ", 1))).strip()
                        else:
                            cut_ok = False
                    h["src1"] = [x for x in h["src1"] if int(x) != sid]
                    mark(h, "pseudokey_fixed" if cut_ok else "needs_review")
            log.append({"sid": sid, "verdict": v, "owner": o["word"], "added": {k: o.get(k, "")[len(b):] for k, b in before.items()},
                        "dropped": [h["word"] for h in hosts if h["entry_id"] in dropped]})
        elif v in ("garbled_key", "split_word"):
            if len(hosts) != 1 or [int(x) for x in hosts[0].get("src1") or []] != [sid] or sid in MANUAL:
                log.append({"sid": sid, "verdict": v, "status": f"manual ({len(hosts)} hosts / shared sources)"})
                continue
            h = hosts[0]
            old_print = h.get("word1_orig") or qkey.get(sid, "")
            new_base = corpus_form(old_print, base_of(h["word"]), it["correct_headword"])
            rec = {"sid": sid, "verdict": v, "old_word": h["word"], "old_print": old_print,
                   "new_print": it["correct_headword"], "new_base": new_base}
            if fold(new_base) != fold(h["word"]):
                bases.add(base_of(h["word"]))
                # tilde expansions of the garbled print form inside the d1 texts
                for f in ("def1", "misc1", "tags"):
                    if h.get(f) and old_print:
                        h[f] = re.sub(r"(?<![а-яё])" + re.escape(kj(old_print.lower())), kj(it["correct_headword"].lower()), h[f])
                twins = [e for e in es if fold(e["word"]) == fold(new_base) and e["dict_id"] == "2" and e is not h]
                if len(twins) == 1 and not h.get("src2"):
                    t = twins[0]                       # hidden pair: d1 side joins the dict-2 entry
                    for f in ("def1", "misc1", "decl"):
                        t[f] = h.get(f, "")
                    if h.get("tags") and h["tags"] not in (t.get("tags") or ""):
                        t["tags"] = f"{t['tags']}; {h['tags']}" if t.get("tags") else h["tags"]
                    t["src1"], t["word1_orig"], t["dict_id"] = h.get("src1") or [], kj(it["correct_headword"]), "both"
                    t["flags"] = [f for f in t.get("flags") or [] if f != "no_d1_pair"]
                    if new_base.startswith("j") and t["word"].startswith("ж"):
                        bases.add(base_of(t["word"]))
                        t["word"] = t["word_base"] = "j" + base_of(t["word"])[1:]
                    mark(t, "pseudokey_fixed")
                    dropped.add(h["entry_id"])
                    rec["merged_into"] = t["word"]
                else:
                    h["word"] = h["word_base"] = new_base
                    rec["renamed"] = True
            for a_, b_ in TEXT_FIX.get(sid, []):
                for f in ("def1", "misc1"):
                    if h.get(f):
                        h[f] = h[f].replace(a_, b_)
            h["word1_orig"] = kj(it["correct_headword"])
            mark(h, "pseudokey_fixed")
            log.append(rec)
    es = [e for e in es if e["entry_id"] not in dropped]
    grp = defaultdict(list)
    for e in es:
        if base_of(e["word"]) in bases:
            grp[base_of(e["word"])].append(e)
    for b, g in grp.items():
        g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both", x["entry_id"]))
        for i, x in enumerate(g, 1):
            x["word"] = b if len(g) == 1 else f"{b}{i}"
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, dup[:10]
    for e in es:
        if e["entry_id"] in touched:
            for k in SUB:
                e.pop(k, None)
    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(CK / "qa" / "s10_pseudokeys.jsonl", "w", encoding="utf-8") as f:
        for r in log:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"applied": len(log), "dropped": len(dropped),
                      "verdicts": Counter(it["verdict"] for it in items.values())}, ensure_ascii=False, default=dict))
    for r in log:
        print(" ", json.dumps(r, ensure_ascii=False)[:220])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["prep", "apply"])
    a = ap.parse_args()
    {"prep": prep, "apply": apply}[a.phase]()
