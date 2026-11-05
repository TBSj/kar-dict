# -*- coding: utf-8 -*-
"""S12: recover the ТСКБЯ pages that stage S1 never extracted.

s1_dict2_extract.py used body_start = {1: 29, 2: 17, 3: 17} (0-based page index), but
the vocabulary of volumes 2 and 3 starts at index 10 (PDF p. 11), right after the legend
page (index 9).  Pages 10–16 of both volumes were skipped:
    т. 2  ЗАВА … ЗАКОНСУЗ          т. 3  САБА … САБЫРЛАНДЫРЫУ
and the continuation lines at the top of index 17 of т. 3 (end of «сабырландырыу»)
were dropped because no entry was open there.

Re-running S1 would renumber every d2_ id, so the gap is appended instead:
  extract    pages 10–16 (+ lead of 17) -> 00_dict2_pages/vol{2,3}.jsonl (inserted),
             new segments appended to 02_dict2_segmented.jsonl (ids after the current max),
             S2 batches -> shards/s12/s2_in/
  integrate  shards/s12/s2_out -> 03_dict2_parsed.jsonl (appended) + match/merge plan against
             the corpus: shards/s12/plan.json, S4-style groups -> shards/s12/s4_in/
  apply      plan (+ s12/s4_out) -> 06_lextagged.jsonl
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fitz  # noqa: E402
from s1_dict2_extract import page_lines, dehyphenate, segment_volume  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S12 = CK / "shards" / "s12"
GAP = {2: range(10, 17), 3: range(10, 17)}     # 0-based page indices missing from stage 00
NEXT = 17


def extract():
    seg_path = CK / "02_dict2_segmented.jsonl"
    segs = [json.loads(l) for l in open(seg_path, encoding="utf-8")]
    if any(s.get("gap_fill") for s in segs):
        print("gap segments already appended — nothing to do")
        return
    maxid = max(int(s["id"][3:]) for s in segs)
    new_segs, new_pages = [], {}
    for vol, rng in GAP.items():
        doc = fitz.open(str(ROOT / "sources" / "2" / f"ТСКБЯ - {vol}.pdf"))
        pages = [{"vol": vol, "page": pg, "text": dehyphenate(page_lines(doc[pg]))}
                 for pg in list(rng) + [NEXT]]
        doc.close()
        new_pages[vol] = pages[:-1]
        out = segment_volume(vol, pages)
        keep = [s for s in out if s["page"] < NEXT]   # entries starting on 17 already exist
        for s in keep:
            maxid += 1
            s["id"] = f"d2_{maxid:05d}"
            s["gap_fill"] = True
            new_segs.append(s)
    with open(seg_path, "a", encoding="utf-8") as f:
        for s in new_segs:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    for vol, pages in new_pages.items():
        p = CK / "00_dict2_pages" / f"vol{vol}.jsonl"
        old = [json.loads(l) for l in open(p, encoding="utf-8")]
        have = {x["page"] for x in old}
        add = [x for x in pages if x["page"] not in have]
        with open(p, "w", encoding="utf-8") as f:
            for x in sorted(add + old, key=lambda x: x["page"]):
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
    # S2 batches (same payload as s2_make_batches.py)
    d = S12 / "s2_in"
    d.mkdir(parents=True, exist_ok=True)
    for f_old in d.glob("batch_*.json"):
        f_old.unlink()
    batches, cur = [], []
    for e in new_segs:
        if len(cur) >= 12 and (not e["flags"] or not cur):
            batches.append(cur)
            cur = []
        cur.append(e)
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches):
        json.dump([{"id": e["id"], "vol": e["vol"], "page": e["page"], "head_hint": e["headword_fixed"],
                    "hom_hint": e["hom"], "flags": e["flags"], "text": e["text"]} for e in b],
                  open(d / f"batch_{i:02d}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"new_segments": len(new_segs), "by_vol": Counter(s["vol"] for s in new_segs),
                      "id_range": [new_segs[0]["id"], new_segs[-1]["id"]], "batches": len(batches),
                      "pages_added": {v: len(p) for v, p in new_pages.items()}}, ensure_ascii=False, default=dict))


ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
SUB = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
       "misc1_stem_note", "misc1_variants", "misc2_citations",
       "misc2_citations_periodical", "misc2_citations_collection",
       "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
       "misc2_gram_note"]


def base_of(w):
    return re.sub(r"\d+$", "", w)


def fold(w):
    w = base_of(w).lower().replace("кь", "къ").replace("гь", "гъ").replace("ё", "е")
    return w.replace("дж", "j").replace("ж", "j").replace("b", "п").replace("б", "п")


def hom_order(h):
    h = (h or "").strip()
    return ROMAN.get(h, int(h) if h.isdigit() else 99)


def load_parsed():
    out = []
    for f in sorted((S12 / "s2_out").glob("batch_*.json")):
        for e in json.load(open(f, encoding="utf-8"))["entries"]:
            e.setdefault("flags", [])
            out.append(e)
    return out


def integrate():
    parsed = load_parsed()
    segs = {json.loads(l)["id"] for l in open(CK / "02_dict2_segmented.jsonl", encoding="utf-8")
            if json.loads(l).get("gap_fill")}
    got = {s for e in parsed for s in e["source_ids"]}
    assert segs <= got, f"segments without parse: {sorted(segs - got)[:10]}"
    # keep 03_dict2_parsed.jsonl complete (idempotent)
    p03 = CK / "03_dict2_parsed.jsonl"
    have = {tuple(json.loads(l)["source_ids"]) + (json.loads(l).get("word"),) for l in open(p03, encoding="utf-8")}
    with open(p03, "a", encoding="utf-8") as f:
        for e in parsed:
            if tuple(e["source_ids"]) + (e.get("word"),) not in have:
                f.write(json.dumps(dict(e, gap_fill=True), ensure_ascii=False) + "\n")
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byfold = defaultdict(list)
    for e in es:
        byfold[fold(e["word"])].append(e)
    groups = defaultdict(lambda: {"d2": [], "d1": []})
    for i, p in enumerate(parsed):
        if not p.get("word"):
            continue
        groups[fold(p["word"])]["d2"].append(i)
    plan, s4 = [], []
    for k, g in groups.items():
        ex = byfold.get(k, [])
        d1 = [e["entry_id"] for e in ex if e["dict_id"] == "1"]
        clash = [e["entry_id"] for e in ex if e["dict_id"] != "1"]
        rec = {"fold": k, "d2": g["d2"], "d1": d1, "clash": clash,
               "complex": len(g["d2"]) > 1 or len(d1) > 1 or bool(clash)}
        plan.append(rec)
        if rec["complex"]:
            byid = {e["entry_id"]: e for e in ex}
            wb = base_of(byid[d1[0]]["word"]) if d1 else parsed[g["d2"][0]]["word"].lower()
            s4.append({
                "match_id": f"s12_{len(s4):03d}", "word_final": wb,
                "word_base_map": {byid[x].get("word1_orig") or byid[x]["word"]: base_of(byid[x]["word"]) for x in d1}
                                 | {"_d2only": wb},
                "d1": [{"seqid": int(byid[x]["src1"][0]) if byid[x].get("src1") else None, "_entry_id": x,
                        "d1_word": byid[x].get("word1_orig") or byid[x]["word"], "word_base": base_of(byid[x]["word"]),
                        "hom_src": "", "tags": byid[x].get("tags", ""), "decl": byid[x].get("decl", ""),
                        "def1": byid[x].get("def1", ""), "misc1": byid[x].get("misc1", "")} for x in d1],
                "d2": [{"source_ids": parsed[i]["source_ids"], "hom": parsed[i].get("hom", ""),
                        "tags": parsed[i].get("tags", ""), "def2": parsed[i].get("def2", ""),
                        "misc2": parsed[i].get("misc2", ""), "_parsed": i} for i in g["d2"]]
                      + [{"source_ids": byid[x].get("src2") or [], "hom": str(byid[x].get("hom_rank", "")),
                          "tags": byid[x].get("tags", ""), "def2": byid[x].get("def2", ""),
                          "misc2": byid[x].get("misc2", ""), "_entry_id": x} for x in clash],
            })
            # d1 side of a clashing 'both' entry has to travel with it
            for x in clash:
                if byid[x].get("src1"):
                    s4[-1]["d1"].append({"seqid": int(byid[x]["src1"][0]), "_entry_id": x, "_with_d2": True,
                                         "d1_word": byid[x].get("word1_orig") or byid[x]["word"],
                                         "word_base": base_of(byid[x]["word"]), "hom_src": "",
                                         "tags": byid[x].get("tags", ""), "decl": byid[x].get("decl", ""),
                                         "def1": byid[x].get("def1", ""), "misc1": byid[x].get("misc1", "")})
    json.dump({"parsed": parsed, "plan": plan}, open(S12 / "plan.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    d = S12 / "s4_in"
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("batch_*.json"):
        f.unlink()
    for i in range(0, len(s4), 6):
        json.dump(s4[i:i + 6], open(d / f"batch_{i // 6:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(json.dumps({"parsed_entries": len(parsed), "groups": len(plan),
                      "simple_merge": sum(1 for r in plan if not r["complex"] and r["d1"]),
                      "simple_new_d2": sum(1 for r in plan if not r["complex"] and not r["d1"]),
                      "complex": len(s4),
                      "complex_words": [r["fold"] for r in plan if r["complex"]]}, ensure_ascii=False))


def apply():
    P = json.load(open(S12 / "plan.json", encoding="utf-8"))
    parsed = P["parsed"]
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byid = {e["entry_id"]: e for e in es}
    if any("gap_fill" in (e.get("flags") or []) for e in es):
        print("gap entries already applied — nothing to do")
        return
    s4_in, s4_out = {}, {}
    for f in sorted((S12 / "s4_in").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8")):
            s4_in[g["match_id"]] = g
    for f in sorted((S12 / "s4_out").glob("batch_*.json")):
        for g in json.load(open(f, encoding="utf-8"))["groups"]:
            s4_out[g["match_id"]] = g
    new_entries, touched, dropped, bases, changes = [], set(), set(), set(), []

    def mark(e):
        e.setdefault("flags", [])
        if "gap_fill" not in e["flags"]:
            e["flags"].append("gap_fill")
        touched.add(e.get("entry_id"))

    for r in P["plan"]:
        if r["complex"]:
            continue
        p = parsed[r["d2"][0]]
        if r["d1"]:
            e = byid[r["d1"][0]]
            before = {k: e.get(k) for k in ("word", "dict_id", "tags")}
            t1, t2 = e.get("tags") or "", p.get("tags") or ""
            e["tags"] = t2 if not t1 else (t1 if not t2 else (t2 if t1 in t2 else f"{t2}; {t1}"))
            e["def2"], e["misc2"] = p.get("def2", ""), p.get("misc2", "")
            e["src2"], e["word2_orig"] = p["source_ids"], p["word"]
            e["dict_id"] = "both"
            e["hom_rank"] = hom_order(p.get("hom"))
            e["flags"] = [f for f in e.get("flags", []) if f != "no_d2_pair"] + \
                         [f for f in p.get("flags", []) if f not in e.get("flags", [])]
            mark(e)
            bases.add(base_of(e["word"]))
            changes.append({"action": "merged_d2_into_d1", "entry_id": e["entry_id"], "word": e["word"],
                            "before": before, "src2": p["source_ids"]})
        else:
            w = p["word"].lower()
            e = {"word": w, "word_base": w, "dict_id": "2", "tags": p.get("tags", ""), "def1": "",
                 "def2": p.get("def2", ""), "misc1": "", "misc2": p.get("misc2", ""), "src1": [],
                 "src2": p["source_ids"], "word1_orig": None, "word2_orig": p["word"], "decl": "",
                 "hom_rank": hom_order(p.get("hom")), "lextag": "", "lextag_conf": "",
                 "flags": ["gap_fill", "no_d1_pair"] + list(p.get("flags", []))}
            new_entries.append(e)
            bases.add(w)
            changes.append({"action": "new_d2", "word": w, "src2": p["source_ids"]})
    for mid, gin in s4_in.items():
        gout = s4_out.get(mid)
        assert gout, f"no S4 output for {mid}"
        existing = [d["_entry_id"] for d in gin["d1"] + gin["d2"] if d.get("_entry_id")]
        existing = list(dict.fromkeys(existing))
        want2 = {s for d in gin["d2"] for s in d["source_ids"]}
        got2 = {s for x in gout["entries"] for s in x.get("src2") or []}
        assert want2 <= got2, (mid, want2 - got2)
        used = set()
        for x in gout["entries"]:
            x1 = {int(s) for s in x.get("src1") or []}
            match = next((eid for eid in existing if eid not in used and
                          (({int(s) for s in byid[eid].get("src1") or []} & x1) or
                           (set(byid[eid].get("src2") or []) & set(x.get("src2") or [])))), None)
            if match:
                e = byid[match]
                used.add(match)
            else:
                e = {"lextag": "", "lextag_conf": "", "flags": []}
                new_entries.append(e)
            for k in ("tags", "def1", "def2", "misc1", "misc2", "decl", "word1_orig", "word2_orig"):
                e[k] = x.get(k) or ("" if k not in ("word1_orig", "word2_orig") else None)
            e["src1"] = sorted(x1)
            e["src2"] = x.get("src2") or []
            e["dict_id"] = "both" if e["src1"] and e["src2"] else ("1" if e["src1"] else "2")
            e["hom_rank"] = x.get("hom_rank", 99)
            e["word"] = e["word_base"] = x["word_base"]
            for f in x.get("flags") or []:
                if f not in e["flags"]:
                    e["flags"].append(f)
            mark(e)
            bases.add(x["word_base"])
        for eid in existing:
            if eid not in used:
                dropped.add(eid)
                bases.add(base_of(byid[eid]["word"]))
        changes.append({"action": "s4_group", "match_id": mid, "entries_out": len(gout["entries"]),
                        "replaced": existing})
    es = [e for e in es if e["entry_id"] not in dropped] + new_entries
    maxid = max(int(e["entry_id"][2:]) for e in es if e.get("entry_id"))
    for i, e in enumerate([e for e in new_entries], 1):
        e["entry_id"] = f"e_{maxid + i:05d}"
        touched.add(e["entry_id"])
        if "gap_fill" not in e["flags"]:
            e["flags"].append("gap_fill")
    grp = defaultdict(list)
    for e in es:
        if base_of(e["word"]) in bases:
            grp[base_of(e["word"])].append(e)
    for b, g in grp.items():
        g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both", x["entry_id"]))
        for i, x in enumerate(g, 1):
            x["word"] = b if len(g) == 1 else f"{b}{i}"
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    assert not dup, f"collisions: {dup[:10]}"
    for e in es:
        if e["entry_id"] in touched:
            for k in SUB:
                e.pop(k, None)
    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(CK / "qa" / "s12_changes.jsonl", "w", encoding="utf-8") as f:
        for c in changes:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    need = [e for e in es if e["entry_id"] in touched and not e.get("lextag")]
    json.dump([{"entry_id": e["entry_id"], "word": e["word"], "tags": e.get("tags", ""),
                "def1": e.get("def1", ""), "def2": e.get("def2", "")} for e in need],
              open(S12 / "lextag_in.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"entries": len(es), "touched": len(touched), "new": len(new_entries),
                      "dropped": len(dropped), "needs_lextag": len(need),
                      "actions": Counter(c["action"] for c in changes)}, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["extract", "integrate", "apply"])
    a = ap.parse_args()
    {"extract": extract, "integrate": integrate, "apply": apply}[a.phase]()
