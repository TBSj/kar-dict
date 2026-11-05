# -*- coding: utf-8 -*-
"""S17: read back the three КБРС-1989 blocks lost by the qmos export (survey step 2, Н1).

The qmos export came in «pages» of 100 records; three of them were lost (a copy of the neighbour
page came instead).  The lost articles are read from the printed book (scan #26, no text layer)
by vision agents and sent through the usual dict-1 path (S0 parse -> merge with ТСКБЯ).

  block 1  p. 42–45    after актриса (qmos 1000)   .. before акъыллашыргъа (1001)
  block 2  p. 456–458  after маймул I (18262)      .. before мальдир (18363)
  block 3  p. 228–231  after джангырыу (7345)      .. before джарашыулукъ (7346)

Restored articles have no qmos seqid: they get synthetic src1 ids 101001.. / 102001.. / 103001..
(block * 1000 + 100000 + n) and the flag kbrs_scan_block.

Phases (files under checkpoints/shards/s17/, page images under local/s17_img/ — book scans):
  crops   page column crops (zoom 3.0, 3 overlapping pieces per column) for the OCR agents
  prep    ocr/pNNN.json -> stitched articles, gap selection by the qmos anchors, accuracy check of
          the overlap articles against qmos, items.jsonl + s0_in/ batches (S0 prompt)
  plan    s0_out -> plan.json (target corpus entry per article, complex groups -> s4_in/)
  apply   plan (+ s4_out/) -> checkpoints/06_lextagged.jsonl, qa/s17_changes.jsonl
"""
import json, re, sys, argparse, difflib, unicodedata
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s10_hyphen import (kj, base_of, expand_tilde, fold, normalize_headword, corpus_index,  # noqa: E402
                        load_jsonl, save_jsonl, snap, SUB, ROMAN)

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S17 = CK / "shards" / "s17"
IMG = ROOT / "local" / "s17_img"
F06 = CK / "06_lextagged.jsonl"
QMOS = ROOT / "sources" / "1" / "qmos_def_32499.txt"
PDF = r"D:/Къагъыт/Къарачай/Китаб/Сёзлюкле/Карачаево-балкарско-русский словарь.pdf"

BLOCKS = {1: {"pages": [42, 43, 44, 45], "after": 1000, "before": 1001},
          2: {"pages": [456, 457, 458], "after": 18262, "before": 18363},
          3: {"pages": [228, 229, 230, 231], "after": 7345, "before": 7346}}
# column pieces as page fractions: x0, x1 per column, y ranges overlap by ~3 % (2–3 lines)
COLS = {"L": (0.0, 0.515), "R": (0.485, 1.0)}
ROWS = [(0.040, 0.370), (0.340, 0.670), (0.640, 0.975)]


# ------------------------------------------------------------------ crops
def crops(zoom=3.0):
    import fitz
    IMG.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    n = 0
    for b in BLOCKS.values():
        for p in b["pages"]:
            pg = doc[p - 1]
            r = pg.rect
            for c, (x0, x1) in COLS.items():
                for i, (y0, y1) in enumerate(ROWS, 1):
                    clip = fitz.Rect(r.width * x0, r.height * y0, r.width * x1, r.height * y1)
                    pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
                    pix.save(IMG / f"p{p:03d}_{c}{i}.png")
                    n += 1
    print(json.dumps({"crops": n, "dir": str(IMG)}))


# ------------------------------------------------------------------ prep
def qmos_list():
    q = json.load(open(QMOS, encoding="utf-8"))
    return [(int(k.rsplit("_", 1)[1]), k.rsplit("_", 1)[0], v) for k, v in q.items()]


def to_corpus_orth(s):
    """1989 print orthography -> qmos/corpus: ў -> у, нъ -> нг, no stress marks"""
    s = unicodedata.normalize("NFD", s).replace("\u0301", "").replace("\u0300", "")
    s = unicodedata.normalize("NFC", s)
    return (s.replace("ў", "у").replace("Ў", "У").replace("нъ", "нг").replace("Нъ", "Нг")
             .replace("НЪ", "НГ"))


def stitched(page):
    """articles of one page in reading order; a leading 'cont' piece is glued to the previous one"""
    d = json.load(open(S17 / "ocr" / f"p{page:03d}.json", encoding="utf-8"))
    return d["entries"]


def qmos_clean(v, word):
    return " ".join(kj(expand_tilde(re.sub(r"^(I{1,3}|IV|V)(?=\S)", "", v), word, "")).split())


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


RE_DECL = re.compile(r"^\(\s*(-?[а-яёў~]{1,5})\s*\)\s*")


def prep(bs=25):
    q = qmos_list()
    qidx = {sid: i for i, (sid, _, _) in enumerate(q)}
    items, overlap, report = [], [], {}
    ovf = S17 / "ocr_overrides.json"   # manual decisions on the agents' doubts: {sid: {W_print|decl|replace|typo_fixed|note}}
    overrides = json.load(open(ovf, encoding="utf-8")) if ovf.exists() else {}
    for bno, b in BLOCKS.items():
        arts = []
        for p in b["pages"]:
            for e in stitched(p):
                e = dict(e, page=p)
                if e.get("cont") and arts:
                    prev, nxt = arts[-1]["text"].rstrip(), e["text"].lstrip()
                    if re.search(r"[а-яёўъь]-$", prev) and re.match(r"[а-яёў]", nxt):
                        # word broken across columns/pages (угне-|тение); logged for review
                        report.setdefault("joined_across_columns", []).append(prev[-25:] + "|" + nxt[:15])
                        arts[-1]["text"] = prev[:-1] + nxt
                    else:
                        arts[-1]["text"] = (prev + " " + nxt).strip()
                    arts[-1]["doubt"] = arts[-1].get("doubt", []) + e.get("doubt", [])
                elif e.get("cont"):
                    continue                       # tail of an article from before the block pages
                else:
                    arts.append(e)
        for a in arts:
            # «-мальдир» (second part of a pair word, «парн. к шальдир-») is keyed without the hyphen
            # in qmos and in the corpus (jен «парн. к эт-»)
            a["head_c"] = kj(to_corpus_orth(a["head"].strip().lower())).lstrip("-")
            a["text_c"] = to_corpus_orth(a["text"])
        # anchors: last qmos head before the gap and first one after it
        i_after, i_before = qidx[b["after"]], qidx[b["before"]]
        w_after, w_before = q[i_after][1], q[i_before][1]
        hom_after = re.match(r"^(I{1,3}|IV|V)(?=\S)", q[i_after][2])
        pos_a = [i for i, a in enumerate(arts) if a["head_c"] == kj(w_after)
                 and (not hom_after or a.get("hom") == hom_after.group(1))]
        pos_b = [i for i, a in enumerate(arts) if a["head_c"] == kj(w_before)]
        assert pos_a and pos_b, (bno, w_after, w_before, [a["head_c"] for a in arts][:40])
        lo, hi = pos_a[-1], pos_b[0]
        gap = arts[lo + 1:hi]
        # accuracy: overlap articles (present in qmos) vs qmos text
        qby = defaultdict(list)
        for sid, w, v in q[max(0, i_after - 120):i_before + 120]:
            qby[kj(w)].append((sid, v))
        sims = []
        for a in arts[:lo + 1] + arts[hi:]:
            cands = qby.get(a["head_c"]) or []
            if not cands:
                continue
            best = max(cands, key=lambda c: sim(qmos_clean(c[1], a["head_c"]),
                                                 " ".join(kj(expand_tilde(a["text_c"], a["head_c"], "")).split())))
            qa = qmos_clean(best[1], a["head_c"])
            oa = " ".join(kj(expand_tilde(RE_DECL.sub("", a["text_c"]), a["head_c"], "")).split())
            s = sim(qa, oa)
            sims.append(s)
            overlap.append({"block": bno, "head": a["head_c"], "sid": best[0], "sim": round(s, 3),
                            "qmos": qa[:300], "ocr": oa[:300]})
        for n, a in enumerate(gap, 1):
            sid = 100000 + bno * 1000 + n
            ov = overrides.get(str(sid), {})
            text = a["text_c"].strip()
            for old, new in ov.get("replace", []):
                assert old in text, (sid, old)
                text = text.replace(old, new)
            text = re.sub(r"^:\s*", "", text.replace("[?]", ""))   # doubts -> flag uncertain_ocr, not text
            decl = ov.get("decl") or (a.get("decl") or "").strip().strip("()")
            m = RE_DECL.match(text)
            if not decl and m:
                decl, text = m.group(1), text[m.end():]
            W = kj(to_corpus_orth(ov["W_print"])) if ov.get("W_print") else a["head_c"]
            # qmos has no ◊ (the rest of dict-1 neither): the phraseology zone sign becomes a plain
            # separator for S0; the raw transcription keeps it (items.jsonl «raw»)
            text = re.sub(r"\s*◊\s*", "; ", text).strip("; ")
            clean = kj(expand_tilde(text, W, decl))
            items.append({"key": str(sid), "sid": sid, "block": bno, "page": a["page"], "col": a.get("col", ""),
                          "W_print": W, "head_printed": a["head"], "hom": a.get("hom") or "", "decl": decl,
                          "raw": a["text"], "rest": text, "clean": clean,
                          "doubt": [] if ov else a.get("doubt", []),     # an override settles the doubts
                          "typo_fixed": bool(ov.get("typo_fixed")), "override_note": ov.get("note", "")})
        report[f"block{bno}"] = {"articles_on_pages": len(arts), "gap": len(gap),
                                 "first": gap[0]["head_c"] if gap else None,
                                 "last": gap[-1]["head_c"] if gap else None,
                                 "overlap_checked": len(sims),
                                 "overlap_sim_mean": round(sum(sims) / len(sims), 3) if sims else None,
                                 "overlap_sim_lt_0.9": sum(1 for s in sims if s < 0.9),
                                 "with_doubts": sum(1 for a in gap if a.get("doubt"))}
    save_jsonl(S17 / "items.jsonl", items)
    save_jsonl(S17 / "overlap_check.jsonl", overlap)
    d = S17 / "s0_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    s0 = [{"seqid": it["sid"], "word": it["W_print"], "hom": it["hom"], "decl": it["decl"], "text": it["clean"]}
          for it in items]
    for i in range(0, len(s0), bs):
        json.dump(s0[i:i + bs], open(d / f"batch_{i // bs:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    report["items"] = len(items)
    report["s0_batches"] = (len(s0) + bs - 1) // bs
    print(json.dumps(report, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ plan
def load_s0():
    parsed = {}
    for f in sorted((S17 / "s0_out").glob("batch_*.json")):
        for oe in json.load(open(f, encoding="utf-8"))["entries"]:
            parsed[int(oe["seqid"])] = oe
    return parsed


def plan():
    es = load_jsonl(F06)
    byid = {e["entry_id"]: e for e in es}
    idx = corpus_index(es)
    items = load_jsonl(S17 / "items.jsonl")
    parsed = load_s0()
    byfold = defaultdict(list)
    for e in es:
        byfold[fold(e["word"])].append(e["entry_id"])
    restored, missing = [], []
    for r in items:
        oe = parsed.get(r["sid"])
        if not oe:
            missing.append(r["sid"])
            continue
        P = {"tags": oe.get("tags", ""), "def1": oe.get("def1", ""), "misc1": oe.get("misc1", ""),
             "flags": [f for f in oe.get("flags") or [] if f]}
        Wn, notes = normalize_headword(r["W_print"], idx)
        fW = fold(Wn)
        targets = byfold.get(fW, [])
        restored.append({"key": r["key"], "sid": r["sid"], "block": r["block"], "W_print": r["W_print"], "W": Wn,
                         "fold": fW, "notes": notes, "hom": r["hom"], "decl": r["decl"], "P": P,
                         "doubt": r.get("doubt", []), "typo_fixed": r.get("typo_fixed", False),
                         "d2_targets": [t for t in targets if not byid[t].get("src1")],
                         "d1_conflicts": [t for t in targets if byid[t].get("src1")]})
    assert not missing, f"no S0 parse for {len(missing)}: {missing[:10]}"
    groups = defaultdict(lambda: {"d1": [], "d2": set(), "conf": set()})
    for rr in restored:
        g = groups[rr["fold"]]
        g["d1"].append(rr["key"])
        g["d2"].update(rr["d2_targets"])
        g["conf"].update(rr["d1_conflicts"])
    rmap = {rr["key"]: rr for rr in restored}
    s4, plan_groups = [], []
    for fW, g in groups.items():
        complex_ = len(g["d1"]) > 1 or len(g["d2"]) > 1 or bool(g["conf"])
        plan_groups.append({"fold": fW, "d1": g["d1"], "d2": sorted(g["d2"]), "conf": sorted(g["conf"]),
                            "complex": complex_})
        if not complex_:
            continue
        W = rmap[g["d1"][0]]["W"]
        s4.append({
            "match_id": f"s17_{len(s4):04d}", "word_final": W,
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
    json.dump({"restored": restored, "groups": plan_groups}, open(S17 / "plan.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    d = S17 / "s4_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    for i in range(0, len(s4), 6):
        json.dump(s4[i:i + 6], open(d / f"batch_{i // 6:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({
        "restored": len(restored), "groups": len(plan_groups), "complex_groups": len(s4),
        "simple_merge_into_d2": sum(1 for g in plan_groups if not g["complex"] and g["d2"]),
        "simple_new": sum(1 for g in plan_groups if not g["complex"] and not g["d2"]),
        "with_d1_conflict": sum(1 for g in plan_groups if g["conf"]),
        "notes": Counter(n.split(":")[0] for rr in restored for n in rr["notes"]),
    }, ensure_ascii=False, indent=1, default=dict))


# ------------------------------------------------------------------ apply
FLAG = "kbrs_scan_block"


def apply():
    es = load_jsonl(F06)
    assert not any(FLAG in (e.get("flags") or []) for e in es), "s17 already applied"
    src_before1 = {int(s) for e in es for s in e.get("src1") or []}
    src_before2 = {s for e in es for s in e.get("src2") or []}
    byid = {e["entry_id"]: e for e in es}
    P = json.load(open(S17 / "plan.json", encoding="utf-8"))
    rmap = {r["key"]: r for r in P["restored"]}
    s4_in, s4_out = {}, {}
    for f in sorted((S17 / "s4_in").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8")):
            s4_in[g["match_id"]] = g
    for f in sorted((S17 / "s4_out").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8"))["groups"]:
            s4_out[g["match_id"]] = g
    before, touched, dropped, new_entries, touched_bases, needs_lextag, unresolved = {}, set(), set(), [], set(), [], []

    def touch(e):
        if e.get("entry_id") and e["entry_id"] not in before:
            before[e["entry_id"]] = snap(e)
        touched.add(e.get("entry_id"))
        touched_bases.add(base_of(e["word"]))
        e.setdefault("flags", [])
        if FLAG not in e["flags"]:
            e["flags"].append(FLAG)

    def item_flags(e, rr):
        for f in (rr["P"]["flags"] + (["uncertain_ocr"] if rr.get("doubt") else [])
                  + (["source_typo_fixed"] if rr.get("typo_fixed") else [])):
            if f not in e["flags"]:
                e["flags"].append(f)

    for g in P["groups"]:
        if g["complex"]:
            continue
        rr = rmap[g["d1"][0]]
        Pp = rr["P"]
        if g["d2"]:
            t = byid[g["d2"][0]]
            touch(t)
            assert fold(t["word"]) == fold(rr["W"]), (t["word"], rr["W"])
            t["dict_id"] = "both"
            t["def1"], t["misc1"], t["decl"] = Pp["def1"], Pp["misc1"], rr["decl"]
            t["src1"], t["word1_orig"] = [rr["sid"]], rr["W_print"]
            if Pp["tags"] and Pp["tags"] not in (t.get("tags") or ""):
                t["tags"] = f"{t['tags']}; {Pp['tags']}" if t.get("tags") else Pp["tags"]
            W = rr["W"]
            if W.endswith("б") and base_of(t["word"]).endswith("п"):   # S3 b-rule: -б(d1) / -п(d2)
                W = W[:-1] + "b"
            t["word"] = t["word_base"] = W
            touched_bases.add(W)
            t["flags"] = [f for f in t["flags"] if f != "no_d1_pair"]
            item_flags(t, rr)
        else:
            e = {"word": rr["W"], "word_base": rr["W"], "dict_id": "1", "tags": Pp["tags"], "def1": Pp["def1"],
                 "def2": "", "misc1": Pp["misc1"], "misc2": "", "src1": [rr["sid"]], "src2": [],
                 "word1_orig": rr["W_print"], "word2_orig": None, "decl": rr["decl"],
                 "hom_rank": ROMAN.get(rr["hom"], 99), "lextag": "", "lextag_conf": "", "flags": [FLAG]}
            item_flags(e, rr)
            new_entries.append(e)
            needs_lextag.append(e)
            touched_bases.add(rr["W"])

    for mid, gin in s4_in.items():
        gout = s4_out.get(mid)
        if not gout:
            unresolved.append(mid)
            continue
        want1 = {d["seqid"] for d in gin["d1"]}
        want2 = {s for d in gin["d2"] for s in d["source_ids"]}
        got1 = {int(s) for x in gout["entries"] for s in x.get("src1") or []}
        got2 = {s for x in gout["entries"] for s in x.get("src2") or []}
        assert want1 <= got1 and want2 <= got2, (mid, want1 - got1, want2 - got2)
        doubt_sids = {rmap[d["_key"]]["sid"] for d in gin["d1"] if d.get("_key") and rmap[d["_key"]].get("doubt")}
        existing = {d["_entry_id"]: d for d in gin["d2"]} | {d["_entry_id"]: d for d in gin["d1"] if d.get("_entry_id")}
        used = set()
        for x in gout["entries"]:
            match = next((eid for eid in existing if eid not in used and
                          (set(byid[eid].get("src2") or []) & set(x.get("src2") or []) or
                           {int(s) for s in byid[eid].get("src1") or []} & {int(s) for s in x.get("src1") or []})), None)
            if match:
                e = byid[match]
                used.add(match)
                touch(e)
            else:
                e = {"lextag": "", "lextag_conf": "", "flags": [FLAG]}
                new_entries.append(e)
                needs_lextag.append(e)
            for k in ("tags", "def1", "def2", "misc1", "misc2", "decl", "word1_orig", "word2_orig"):
                e[k] = x.get(k) or ("" if k not in ("word1_orig", "word2_orig") else None)
            e["src1"] = [int(s) for s in x.get("src1") or []]
            e["src2"] = x.get("src2") or []
            e["dict_id"] = "both" if e["src1"] and e["src2"] else ("1" if e["src1"] else "2")
            e["hom_rank"] = x.get("hom_rank", 99)
            e["word"] = e["word_base"] = x["word_base"]
            for f in (x.get("flags") or []) + (["uncertain_ocr"] if set(e["src1"]) & doubt_sids else []):
                if f not in e["flags"]:
                    e["flags"].append(f)
            if e["src1"] and e["src2"]:
                e["flags"] = [f for f in e["flags"] if f != "no_d1_pair"]
            touched_bases.add(x["word_base"])
        for eid in existing:
            if eid not in used:
                touch(byid[eid])
                dropped.add(eid)

    es = [e for e in es if e["entry_id"] not in dropped] + new_entries
    maxid = max(int(e["entry_id"][2:]) for e in es if e.get("entry_id"))
    for i, e in enumerate(new_entries, 1):
        e["entry_id"] = f"e_{maxid + i:05d}"
        touched.add(e["entry_id"])
    grp = defaultdict(list)
    for e in es:
        if base_of(e["word"]) in touched_bases:
            grp[base_of(e["word"])].append(e)
    renamed = 0
    new_ids = {n["entry_id"] for n in new_entries}
    for b, g in grp.items():
        g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both", x["entry_id"]))
        for i, x in enumerate(g, 1):
            neww = b if len(g) == 1 else f"{b}{i}"
            if x["word"] != neww:
                renamed += 1
                if x["entry_id"] not in before and x["entry_id"] not in new_ids:
                    before[x["entry_id"]] = snap(x)
                touched.add(x["entry_id"])
            x["word"] = neww
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, f"collisions: {dup[:10]}"
    # nothing lost: every source id of the old corpus is still there, every restored article placed.
    # (S4 input shows only the d1 side of an existing d1 entry; its output replaces the whole entry,
    #  so a d2 half that S4 did not copy would vanish here.)
    src_after1 = {int(s) for e in es for s in e.get("src1") or []}
    src_after2 = {s for e in es for s in e.get("src2") or []}
    lost1, lost2 = src_before1 - src_after1, src_before2 - src_after2
    assert not lost1 and not lost2, f"lost src1 {sorted(lost1)[:10]} src2 {sorted(lost2)[:10]}"
    unplaced = {r["sid"] for r in P["restored"]} - src_after1
    assert not unplaced, f"restored articles not placed: {sorted(unplaced)[:10]}"
    # the flag marks text read from the scan: entries only touched by the merge (акъ «течь», маймул I) lose it
    rsids = {r["sid"] for r in P["restored"]}
    for e in es:
        if FLAG in (e.get("flags") or []) and not ({int(s) for s in e.get("src1") or []} & rsids):
            e["flags"].remove(FLAG)
    for e in es:
        if e["entry_id"] in touched:
            for k in SUB:
                e.pop(k, None)
    save_jsonl(F06, es)
    byid2 = {e["entry_id"]: e for e in es}
    changes = [{"entry_id": eid, "action": "deleted" if eid in dropped else ("new" if eid not in before else "changed"),
                "before": before.get(eid), "after": snap(byid2[eid]) if eid in byid2 else None}
               for eid in sorted(touched | dropped)]
    save_jsonl(CK / "qa" / "s17_changes.jsonl", changes)
    json.dump([{"entry_id": e["entry_id"], "word": e["word"], "tags": e.get("tags", ""), "def1": e.get("def1", ""),
                "def2": e.get("def2", ""), "misc1": (e.get("misc1") or "")[:200]} for e in needs_lextag],
              open(S17 / "lextag_in.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"entries": len(es), "touched": len(touched), "deleted": len(dropped), "new": len(new_entries),
                      "renamed_digits": renamed, "needs_lextag": len(needs_lextag), "unresolved": unresolved,
                      "actions": Counter(c["action"] for c in changes)}, ensure_ascii=False, indent=1, default=dict))


# ------------------------------------------------------------------ lextag
def lextag():
    """lextag_out_*.json ({"items": [{entry_id, lextag, confidence}]}, prompt s5_lextag.md) -> 06"""
    out = {}
    for f in sorted(S17.glob("lextag_out_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            out[it["entry_id"]] = it
    want = {x["entry_id"] for x in json.load(open(S17 / "lextag_in.json", encoding="utf-8"))}
    assert want <= set(out), f"missing lextag for {sorted(want - set(out))[:10]}"
    es = load_jsonl(F06)
    n = 0
    for e in es:
        if e["entry_id"] in want and not e.get("lextag"):
            e["lextag"], e["lextag_conf"] = out[e["entry_id"]]["lextag"], out[e["entry_id"]]["confidence"]
            n += 1
    save_jsonl(F06, es)
    print(json.dumps({"lextagged": n}))


# ------------------------------------------------------------------ review
# judgement calls of the S4 merge agents (their reports, 2026-11-05), shown to the linguist; key = sid
S4_NOTES = {
    101013: "КБРС «акъ I» разделён по его же частям: 1. (прил.) → ТСКБЯ акъ 1, 2. (сущ., «агъы») → акъ 2. "
            "Поэтому «3) ист. белый, белогвардеец» и «акъла белые» попали в акъ2, хотя в ТСКБЯ это значение у прилагательного.",
    103020: "Новое из КБРС «джапхыч — вьюшка, задвижка (печи)», почти наверняка вариант «джабхыч» "
            "(в корпусе jабхыч1, уже в паре с ТСКБЯ жапхыч). Оставлено отдельной статьёй — слить?",
    103048: "Статья КБРС — только помета «понуд. к джаратыргъа I»; отнесена к ТСКБЯ жарат 2 «сотворить» по нумерации КБРС.",
    103049: "Только помета; поставлено к ТСКБЯ омониму 2, но пример ТСКБЯ «Къызны жашха жаратдырыу» скорее о значении «нравиться».",
    103057: "КБРС «джаратылыргъа II» (только помета) отнесено к значению «использовать» (ТСКБЯ омоним 3); омоним 1 «быть одобренным» остался без пары.",
    103061: "КБРС «джаратыргъа II» охватывает «использовать» и «одобрять» — разделено по значениям между ТСКБЯ омонимами 3 и 1.",
    103063: "То же, что джаратыргъа II: разделено между омонимами 3 и 1.",
    103077: "«годный, полезный» → ТСКБЯ омоним 1 (общая пословица), хотя «годный» подходит и к омониму 2.",
    103078: "«см. джарагъан» → ТСКБЯ омоним 2.",
    103091: "Одна статья КБРС на два омонима ТСКБЯ: примеры «помирить, уладить, устроить на работу, расквартировать, баш джарашдырыргъа» → омоним 1, остальные → 2.",
    103092: "Омоним 1 — «упорядочение… умиротворение» и пословица о мире, омоним 2 — полное def1.",
    103098: "Значения 1. (сущ.) → омоним 1, 2. (прил.) → омоним 2; наречные примеры («джарашыу джашаргъа») → омоним 3 без def1.",
    101011: "«1. акция 2. акционерный» → ТСКБЯ омоним 1 (ценная бумага); омоним 2 (кампания) без пары.",
    103026: "«хороший, настоящий…» → ТСКБЯ «Замечательный».",
    103027: "Причастие «благоприятный» осталось отдельной статьёй КБРС (пары в ТСКБЯ нет).",
}


def review():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    yel, hdr = PatternFill("solid", start_color="FFF3B0"), Font(bold=True)

    def sheet(wb, title, header, rows, widths, verdict=True):
        ws = wb.create_sheet(title)
        ws.append(header + (["ВЕРДИКТ"] if verdict else []))
        for c in ws[1]:
            c.font = hdr
        for r in rows:
            ws.append(list(r) + ([""] if verdict else []))
        for i, w in enumerate(widths + ([28] if verdict else [])):
            ws.column_dimensions[chr(65 + i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if verdict:
                row[-1].fill = yel
        ws.freeze_panes = "B2"

    def short(s, n=220):
        s = s or ""
        return s if len(s) <= n else s[:n] + "…"

    es = load_jsonl(F06)
    items = {r["sid"]: r for r in load_jsonl(S17 / "items.jsonl")}
    rep = json.load(open(S17 / "prep_report.json", encoding="utf-8"))
    overrides = json.load(open(S17 / "ocr_overrides.json", encoding="utf-8"))
    doubts_ru = json.load(open(S17 / "doubts_ru.json", encoding="utf-8"))
    miss = [sid for sid, it in items.items() if it.get("doubt") and str(sid) not in doubts_ru]
    assert not miss, f"doubts without a Russian note in doubts_ru.json: {miss}"
    by_sid = defaultdict(list)
    for e in es:
        for s in e.get("src1") or []:
            if int(s) in items:
                by_sid[int(s)].append(e)
    rows, doubt_rows = [], []
    for sid, it in sorted(items.items(), key=lambda x: (x[1]["block"], x[0])):
        ents = by_sid[sid]
        words = ", ".join(e["word"] for e in ents)
        if len(ents) > 1:
            what = f"разделена между {len(ents)} омонимами ТСКБЯ"
        elif ents and ents[0]["dict_id"] == "both":
            what = "слита со статьёй ТСКБЯ (получила русский перевод КБРС)"
        else:
            what = "новая статья (только КБРС)"
        flags = sorted({f for e in ents for f in e.get("flags") or []}
                       & {"uncertain_ocr", "needs_review", "source_typo_fixed", "split_def1", "ref_only"})
        printed = it["head_printed"] + (f" {it['hom']}" if it["hom"] else "")
        note = " | ".join(filter(None, [overrides.get(str(sid), {}).get("note", ""), *doubts_ru.get(str(sid), []),
                                        S4_NOTES.get(sid, "")]))
        row = (it["block"], it["page"], printed, words, what, short(ents[0].get("def1") if ents else ""),
               short(it["raw"], 300), ", ".join(flags), note)
        rows.append(row)
        if note or "needs_review" in flags:
            doubt_rows.append(row)
    wb = Workbook()
    ws = wb.active
    ws.title = "Инструкция"
    b = {k: v for k, v in rep.items() if k.startswith("block")}
    ws.append(["Шаг 2 обзора: три блока КБРС-1989, потерянные выгрузкой qmos, прочитаны с печати (5 ноября 2026)"])
    ws["A1"].font = Font(bold=True, size=12)
    for line in [
        "",
        "Что сделано. Выгрузка qmos шла «страницами» по 100 статей; три такие страницы пропали. "
        f"Их статьи прочитаны со скана книги (с. 42–45, 456–458, 228–231): {b['block1']['gap']} + {b['block2']['gap']} + {b['block3']['gap']} = "
        f"{rep['items']} статей, ровно между соседними ключами qmos. Дальше — обычный путь словаря 1: разбор на поля (S0), "
        "слияние со статьями ТСКБЯ и омонимами (S4), метка тематики.",
        "Точность чтения. Статья «акъыл», прочитанная и сверенная с печатью при обзоре, совпала с новым чтением на 99,98 % "
        "(2 расхождения на 1 018 слов). Статьи тех же страниц, которые в qmos есть, совпали с qmos в среднем на 97–98 %; "
        "разница — в основном ошибки старого распознавания qmos (хлопкоподческий → хлопководческий).",
        "Орфография приведена к словарю 1: ў → у, нъ → нг, ударения сняты, знак ◊ заменён разделителем «;» (в qmos его нет).",
        "Флаги: uncertain_ocr — у агента было сомнение в чтении (часто правый край с. 230 сжат на скане); "
        "source_typo_fixed — исправлена опечатка книги; split_def1 — одна статья КБРС разделена между омонимами ТСКБЯ; "
        "needs_review — спорное слияние.",
        "",
        "Листы: 1_Статьи — все прочитанные статьи и что с ними стало; 2_Спорное — только статьи с пометками. "
        "Жёлтый столбец «ВЕРДИКТ»: пусто = согласен.",
        "",
        "Вопросы:",
        "В1. jапхыч («вьюшка, задвижка (печи)») — вариант jабхыч? Слить с jабхыч1?",
        "В2. акъ: значение «3) ист. белый, белогвардеец» оставить у акъ2 (сущ., как в КБРС) или перенести к акъ1 (прил., как в ТСКБЯ)?",
        "В3. Опечатки книги исправлены: «акълатдырыгъа» → акълатдырыргъа, «чачхан» → чычхан (макъыргъан киштик чычхан тутмаз). Согласны?",
    ]:
        ws.append([line])
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 140
    hdr_cols = ["блок", "стр.", "как напечатано", "в корпусе", "что стало", "def1 в корпусе", "текст со скана", "флаги", "заметки"]
    widths = [6, 6, 22, 22, 26, 45, 60, 22, 50]
    sheet(wb, "1_Статьи", hdr_cols, rows, widths)
    sheet(wb, "2_Спорное", hdr_cols, doubt_rows, widths)
    out = CK / "review_queues" / "kbrs_blocks_review.xlsx"
    wb.save(out)
    print(json.dumps({"file": str(out), "articles": len(rows), "disputed": len(doubt_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["crops", "prep", "plan", "apply", "lextag", "review"])
    a = ap.parse_args()
    {"crops": crops, "prep": prep, "plan": plan, "apply": apply, "lextag": lextag, "review": review}[a.phase]()
