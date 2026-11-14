# -*- coding: utf-8 -*-
"""S20: the linguist's answers to manual_review_2.xlsx (filled 2026-11-13) — the S9 queues of the
«Русско-карачаево-балкарский словарь» (1965, ред. Суюнчев Х. И., Урусбиев И. Х.; sources/5 = survey #42).

The workbook's rule: an empty verdict = agree with what is proposed. Only sheet 1 has written verdicts.
  sheet 1  222 KB words of the 1965 dictionary missing from the corpus: add them (with the linguist's changes
           to the translation); 22 of them became headwords since (repairs of steps 1–3, s14), 4 were false
           (glued words of the txt)
  sheet 2  65 forms of the 1965 dictionary close to a corpus word: a spelling variant — linked (variant_of)
  sheet 3  739 variant links inside the corpus: kept as they are (s8 computes them)
  sheet 4  52 entries flagged needs_review after the first workbook: the flag removed
  sheets 5–9: tags tail «оставить», 2 names keep «Дж», the ◊ rule (answered 2026-11-05 in repair_review),
           notes, rejected forms stay rejected — nothing to change

Phases:
  answers  workbook (checkpoints/review_queues/, not in git) + the S9 triage queues
           -> checkpoints/shards/s20/answers.json (every row of sheets 1, 2, 4 with its verdict; tracked)
  pages    the printed 1965 dictionary (library PDF, FineReader text layer) -> local/rkbs/pages.jsonl (book text,
           gitignored) + checkpoints/shards/s20/pages.json (each form -> printed pages where it stands)
  plan     answers + decisions.json (the reading of every written verdict) + the corpus as it stands before this
           step -> checkpoints/shards/s20/plan.json (re-run it when anything before s20 changes the corpus)
  lextag_in the new entries -> lextag_in.json for an agent (prompt s5_lextag.md) -> lextag_out.json (tracked)
  apply    plan + lextag_out.json -> 06, after s18 postfix full (journal checkpoints/qa/s20_apply.jsonl)
New entries: dict_id «5» (only the 1965 dictionary), flag rus_kb_added (rus_kb_variant for the linked spellings),
fields src5 (keys of the txt articles that carry the word) and src5_pages (printed pages) -> sources «РКБС-1965 с. N».

The linguist's answers in chat, 2026-11-14 (decisions.json «chat_2026_11_14»): the KB names of юго-восток and
юго-запад, in no book of the corpus -> new entries with dict_id «L» (flags linguist_added, linguist_fix; sources
«правка лингвиста»); a translation for кюнбатыш, which ТСКБЯ gives only as a reference (flags linguist_gloss,
linguist_fix); бла3 of sheet 4, cut by step 3 into бла1 and бла2, unflagged on both.
"""
import json, re, sys, argparse, unicodedata
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
RQ = CK / "review_queues"
S20 = CK / "shards" / "s20"
LOC = ROOT / "local" / "rkbs"
F06 = CK / "06_lextagged.jsonl"
PDF = Path("D:/Къагъыт/Къарачай/Китаб/Сёзлюкле/Суюнчев Х.И. Русско-карачаево-балкарский словарь.pdf")
TXT = ROOT / "sources" / "5" / "rus_kb_dict_33040.txt"
WB = RQ / "manual_review_2.xlsx"
JOURNAL = CK / "qa" / "s20_apply.jsonl"
DATE = "2026-11-13"

sys.path.insert(0, str(ROOT / "pipeline"))


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def save_jsonl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def jdump(obj, p):
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ answers
def answers():
    import openpyxl
    wb = openpyxl.load_workbook(WB, read_only=True)
    status = {}
    for r in load_jsonl(RQ / "s9_recheck.jsonl"):
        status[(r["queue"], r["form"])] = {"status": r["status"], "why": r.get("why", "")}
    miss = {r["form_src"]: r for r in load_jsonl(RQ / "rus_missing_confirmed.jsonl")}
    var = {r["form_src"]: r for r in load_jsonl(RQ / "rus_variants_confirmed.jsonl")}
    out = {"date": DATE, "workbook": "manual_review_2.xlsx", "sheet1": [], "sheet2": [], "sheet4": []}
    for row in list(wb["1_Пропуски_ру-кб"].iter_rows(values_only=True))[1:]:
        r = miss[row[1]]
        out["sheet1"].append({"word": row[0], "form_src": r["form_src"], "canonical": r.get("canonical"),
                              "ru_gloss": r.get("ru_gloss", ""), "conf": r.get("conf"),
                              "contexts": [c["rus"] for c in r.get("contexts", [])],
                              "verdict": (row[8] or "").strip(),
                              **status.get(("rus_missing_confirmed", r["form"]), {"status": "?"})})
    for row in list(wb["2_Варианты_ру-кб"].iter_rows(values_only=True))[1:]:
        r = var[row[0]]
        out["sheet2"].append({"form": row[0], "corpus": row[1], "base": r.get("base"), "near": r.get("near", []),
                              "contexts": [c["rus"] for c in r.get("contexts", [])], "conf": r.get("conf"),
                              "verdict": (row[7] or "").strip(),
                              **status.get(("rus_variants_confirmed", r["form"]), {"status": "?"})})
    for row in list(wb["4_needs_review_новые"].iter_rows(values_only=True))[1:]:
        out["sheet4"].append({"word": row[0], "dict": row[1], "flags": row[6], "verdict": (row[7] or "").strip()})
    for name in ("3_Варианты_корпуса", "5_Пометы_хвост", "6_дж-ж_остаток", "9_Отклонено_ру-кб"):
        rows = list(wb[name].iter_rows(values_only=True))
        has_verdict = bool(re.match(r"ВЕРДИКТ|ФАСЕТ", str(rows[0][-1] or "")))   # sheet 9 is for reading only
        filled = [r for r in rows[1:] if r and r[-1]] if has_verdict else []
        out.setdefault("other_sheets", {})[name] = {"rows": len(rows) - 1, "verdict_column": has_verdict,
                                                    "verdicts_written": len(filled)}
    a2 = list(wb["7_Фраземы_ромб"].iter_rows(values_only=True))[1][0]
    out["other_sheets"]["7_Фраземы_ромб"] = {"rule_in_A2": a2 or ""}
    jdump(out, S20 / "answers.json")
    print(json.dumps({k: len(v) for k, v in out.items() if isinstance(v, list)} |
                     {"written_sheet1": sum(1 for r in out["sheet1"] if r["verdict"]),
                      "written_sheet2": sum(1 for r in out["sheet2"] if r["verdict"]),
                      "written_sheet4": sum(1 for r in out["sheet4"] if r["verdict"]),
                      "other": out["other_sheets"]}, ensure_ascii=False))


# ------------------------------------------------------------------ pages of the printed book
def norm_text(t):
    t = unicodedata.normalize("NFC", t).replace("\u00ad", "").replace("\u2010", "-")
    t = re.sub(r"-\s*\n\s*", "", t)               # a word broken at the line end
    t = t.replace("||", "").replace("|", "")       # «избыт||ок» marks the stem in the Russian headword
    return re.sub(r"\s+", " ", t).lower()


def book_pages():
    """[(printed page, normalized text)] — the header «— 201 —» gives the number; a page without it is the
    previous one + 1 (the last four PDF pages carry 741–744: one page of the scan is doubled or skipped)"""
    f = LOC / "pages.jsonl"
    if f.exists():
        return [(r["page"], r["text"]) for r in load_jsonl(f)]
    import fitz
    d = fitz.open(PDF)
    rows, prev = [], 0
    for i in range(d.page_count):
        t = d[i].get_text()
        m = re.search(r"—\s*(\d{1,3})\s*—", t[:200])
        p = int(m.group(1)) if m else prev + 1
        prev = p
        rows.append({"pdf": i + 1, "page": p, "text": norm_text(t)})
    LOC.mkdir(parents=True, exist_ok=True)
    save_jsonl(f, rows)
    return [(r["page"], r["text"]) for r in rows]


def spellings(form):
    """the printed form and the forms the scan's OCR may give it: дж/ж, кь/гь for къ/гъ, ё/е"""
    f = form.lower().replace("j", "дж")
    out = {f, f.replace("дж", "ж"), f.replace("къ", "кь").replace("гъ", "гь"), f.replace("ё", "е")}
    return [s for s in out if s]


LET = "а-яёa-z"


def compact(t):
    """the page text without spaces and hyphens + the position of each kept character in the text — the txt of
    the 1965 dictionary glues words the book prints apart («балкъош» = printed «бал къош»), and the scan's OCR
    splits words («деме нгили»)"""
    keep = [i for i, ch in enumerate(t) if ch not in " -"]
    return "".join(t[i] for i in keep), keep


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[-1]


def find_printed(form, pages, rus=()):
    """-> (pages, printed forms): exact spelling first, then the same letters with any spaces / hyphens between
    them (a printed form with a space is a phrase), then — on the page of the Russian headwords the word was
    found under — the closest string within 1 edit per 6 letters (OCR noise of the scan: «бупьуна»)"""
    hits, printed = set(), Counter()
    for s in spellings(form):
        rx = re.compile(r"(?<![" + LET + r"])" + re.escape(s) + r"(?![" + LET + r"])")
        for p, t in pages:
            for m in rx.finditer(t):
                hits.add(p)
                printed[m.group(0)] += 1
    if hits:
        return sorted(hits), printed.most_common(), "exact"
    for s in spellings(form):
        c = s.replace("-", "").replace(" ", "")
        for p, t in pages:
            ct, pos = compact(t)
            for m in re.finditer(re.escape(c), ct):
                a, b = pos[m.start()], pos[m.end() - 1] + 1
                if (a == 0 or not re.match("[" + LET + "]", t[a - 1])) and (b >= len(t) or not re.match("[" + LET + "]", t[b])):
                    hits.add(p)
                    printed[t[a:b]] += 1
    if hits:
        return sorted(hits), printed.most_common(), "spacing"
    c = form.lower().replace("j", "дж").replace("-", "").replace(" ", "")
    tol = max(1, len(c) // 6)
    for r in rus:
        head = re.compile(r"(?<![" + LET + r"])" + re.escape(r.lower()[:8]))
        for p, t in pages:
            for m in head.finditer(t):
                ent = t[m.start():m.start() + 700]
                ct, pos = compact(ent)
                best = min(((lev(c, ct[i:i + len(c) + d]), i, d) for i in range(len(ct) - len(c) + 2)
                            for d in (-1, 0, 1) if i + len(c) + d <= len(ct)), default=None)
                if best and best[0] <= tol:
                    _, i, d = best
                    a, b = pos[i], pos[i + len(c) + d - 1] + 1
                    hits.add(p)
                    printed[ent[a:b]] += 1
    return sorted(hits), printed.most_common(), ("fuzzy" if hits else "none")


def txt_keys(form, art):
    rx = re.compile(r"(?<![а-яёА-ЯЁ])" + re.escape(form.lower()) + r"(?![а-яёА-ЯЁ])")
    return [k for k, v in art.items() if rx.search(re.sub(r"<[^>]+>", "", v).lower())]


def pages_phase():
    pages = book_pages()
    a = json.load(open(S20 / "answers.json", encoding="utf-8"))
    art = json.load(open(TXT, encoding="utf-8"))
    out = {}
    rus = {r["form_src"]: r["contexts"] for r in a["sheet1"]} | {r["form"]: r["contexts"] for r in a["sheet2"]}
    for f in sorted(rus):
        keys = txt_keys(f, art)
        heads = list(dict.fromkeys(list(rus[f]) + [k.rsplit("_", 1)[0] for k in keys]))
        ps, printed, how = find_printed(f, pages, heads)
        out[f] = {"pages": ps, "printed": printed, "how": how, "txt_keys": keys}
    jdump(out, S20 / "pages.json")
    c = Counter(v["how"] for v in out.values())
    print(json.dumps({"forms": len(out), **c,
                      "spacing": {f: v["printed"][:2] for f, v in out.items() if v["how"] == "spacing"},
                      "fuzzy": {f: v["printed"][:2] for f, v in out.items() if v["how"] == "fuzzy"},
                      "none": [f for f, v in out.items() if v["how"] == "none"]}, ensure_ascii=False, indent=0))


# ------------------------------------------------------------------ plan
RE_INF = re.compile(r"(ы?ргъа|и?рге|у?ргъа|ю?рге)$")


def plan():
    import s10_hyphen as h                      # its headword rules: verbs as stems, component-initial дж -> j
    es = load_jsonl(F06)
    idx = h.corpus_index(es)
    byfold = defaultdict(list)
    for e in es:
        byfold[h.fold(e["word"])].append(e["word"])
    byw = {e["word"]: e for e in es}
    a = json.load(open(S20 / "answers.json", encoding="utf-8"))
    pj = json.load(open(S20 / "pages.json", encoding="utf-8"))
    dec = json.load(open(S20 / "decisions.json", encoding="utf-8"))

    def head(form):
        """a printed form -> a corpus headword (a phrase: each word on its own)"""
        return " ".join(h.normalize_headword(h.kj(x.lower()), idx)[0] for x in form.split())

    def in_text(phrase):
        p = phrase.lower().replace("дж", "j").replace("ж", "j")
        rx = re.compile(r"(?<![а-яёj])" + re.escape(p) + r"(?![а-яёj])")
        return [f"{e['word']}:{f}" for e in es for f in ("def1", "misc1", "misc2")
                if rx.search((e.get(f) or "").lower().replace("дж", "j").replace("ж", "j"))]

    out = {"new": [], "update": [], "variant_new": [], "variant_link": [], "unflag": [], "skip": []}
    taken = set()
    for r in a["sheet1"]:
        w = r["word"]
        v = pj[r["form_src"]]
        printed = dec["printed_override"].get(w) or (v["printed"][0][0] if v["printed"] else r["form_src"])
        why = dec["skip"].get(w)
        if why:
            out["skip"].append({"sheet": 1, "item": w, "why": why})
            continue
        phrase = " " in printed.strip() and v["how"] == "spacing"
        W = head(printed) if phrase else head(w)
        gloss = dec["gloss"].get(w, r["ru_gloss"])
        by_linguist = w in dec["gloss"]
        have = byfold.get(h.fold(W), [])
        rec = {"item": w, "word": W, "printed": printed, "pages": v["pages"], "src5": v["txt_keys"],
               "verdict": r["verdict"]}
        if have:
            tgt = byw[have[0]]
            extra = dec["add_to_existing"].get(w)
            if not (tgt.get("def1") or tgt.get("def2")):
                g = gloss + ("; " + dec["existing_gloss_extra"][w] if w in dec["existing_gloss_extra"] else "")
                out["update"].append({**rec, "word": tgt["word"], "set_def1": g,
                                      "linguist": by_linguist or w in dec["existing_gloss_extra"]})
            elif extra and extra not in (tgt.get("def1") or ""):
                out["update"].append({**rec, "word": tgt["word"], "append_def1": extra, "linguist": True})
            else:
                out["skip"].append({"sheet": 1, "item": w, "why": f"already in the corpus: {', '.join(have)}"})
            continue
        if phrase:
            hits = in_text(W)
            if hits:
                out["skip"].append({"sheet": 1, "item": w, "why": f"printed as two words «{printed}» — the phrase "
                                    f"is already in the corpus: {', '.join(hits[:3])}"})
                continue
        if h.fold(W) in taken:
            out["skip"].append({"sheet": 1, "item": w, "why": f"the same headword as another item: {W}"})
            continue
        taken.add(h.fold(W))
        out["new"].append({**rec, "gloss": gloss, "tags": dec["tags"].get(w, ""), "linguist": by_linguist,
                           "phrase": phrase})
    for r in a["sheet2"]:
        f = r["form"]
        v = pj[f]
        printed = v["printed"][0][0] if v["printed"] else ""
        if v["how"] == "none" or (printed and printed.replace("-", "") != f.replace("-", "") and v["how"] != "exact"):
            out["skip"].append({"sheet": 2, "item": f, "why": f"an error of the txt, not of the book: the book prints "
                                f"«{printed}»" if printed else "an error of the txt: not in the book"})
            continue
        if v["how"] == "spacing" and printed.replace(" ", "") == printed:
            out["skip"].append({"sheet": 2, "item": f, "why": f"a line-end hyphen of the txt: the book prints «{printed}»"})
            continue
        W = head(f)
        T = dec["variant_target"].get(f) or r["base"]
        Tw = byfold.get(h.fold(head(T)), []) if T else []
        Fw = byfold.get(h.fold(W), [])
        if not T and Fw:
            out["skip"].append({"sheet": 2, "item": f, "why": f"a corpus headword now (the repairs of step 1): {Fw[0]}"})
            continue
        if not Tw:
            out["skip"].append({"sheet": 2, "item": f, "why": f"no corpus word for the target «{T}»"})
            continue
        if Fw and h.fold(W) == h.fold(Tw[0]):
            out["skip"].append({"sheet": 2, "item": f, "why": f"the same corpus word: {Fw[0]}"})
            continue
        if Fw:
            if h.fold(Fw[0]) in {h.fold(x) for x in Tw}:
                out["skip"].append({"sheet": 2, "item": f, "why": f"the same corpus word: {Fw[0]}"})
            else:
                out["variant_link"].append({"item": f, "word": Fw[0], "target": Tw[0], "pages": v["pages"]})
            continue
        if h.fold(W) in taken:
            out["skip"].append({"sheet": 2, "item": f, "why": f"the same headword as an item of sheet 1: {W}"})
            continue
        taken.add(h.fold(W))
        out["variant_new"].append({"item": f, "word": W, "printed": printed or f, "target": Tw[0], "pages": v["pages"],
                                   "src5": v["txt_keys"]})
    ch = dec.get("chat_2026_11_14", {})            # the linguist's answers in chat, 2026-11-14
    for r in a["sheet4"]:
        if r["word"] in ch.get("split_unflag", {}):    # cut by step 3; the linguist approved its text (бла3)
            hits = [x for x in ch["split_unflag"][r["word"]] if "needs_review" in (byw.get(x, {}).get("flags") or [])]
            if hits:
                out["unflag"].append({"item": r["word"], "words": hits})
            else:
                out["skip"].append({"sheet": 4, "item": r["word"], "why": "no part of the split entry carries needs_review"})
            continue
        same = [r["word"]] if r["word"] in byw else byfold.get(h.fold(r["word"]), [])
        hits = [x for x in same if "needs_review" in (byw[x].get("flags") or [])]
        if r["word"] not in byw and len(hits) > 1:      # renumbered since (бла3 -> бла1 / бла2): which one is unknown
            out["skip"].append({"sheet": 4, "item": r["word"], "why": f"renumbered since; candidates {hits} — flag kept"})
            continue
        if hits:
            out["unflag"].append({"item": r["word"], "words": hits})
        else:
            out["skip"].append({"sheet": 4, "item": r["word"], "why": "no entry with this word carries needs_review now"})
    out["linguist_new"], out["linguist_gloss"] = [], []
    for w, d in ch.get("new_words", {}).items():   # words in no book of the corpus: the linguist's own
        W = head(w)
        have = byfold.get(h.fold(W), [])
        if have:
            out["skip"].append({"sheet": "chat", "item": w, "why": f"already in the corpus: {', '.join(have)}"})
            continue
        out["linguist_new"].append({"item": w, "word": W, "def1": d["def1"], "tags": d.get("tags", ""),
                                    "lextag": d.get("lextag", "")})
    for w, g in ch.get("gloss", {}).items():       # a translation for an entry that has none
        e = byw.get(w)
        if e is None or e.get("def1") or e.get("def2"):
            out["skip"].append({"sheet": "chat", "item": w,
                                "why": "no such entry" if e is None else "it has a translation already"})
            continue
        out["linguist_gloss"].append({"item": w, "word": w, "set_def1": g})
    jdump(out, S20 / "plan.json")
    print(json.dumps({k: len(v) for k, v in out.items()} |
                     {"skip_by_sheet": Counter(x["sheet"] for x in out["skip"])}, ensure_ascii=False))


# ------------------------------------------------------------------ apply
def apply():
    p = json.load(open(S20 / "plan.json", encoding="utf-8"))
    es = load_jsonl(F06)
    byw = {e["word"]: e for e in es}
    if any("rus_kb_added" in (e.get("flags") or []) for e in es):
        print("already applied (entries with rus_kb_added in 06); restore 06 and re-run the sequence to redo")
        return
    lex = {}
    if (S20 / "lextag_out.json").exists():
        lex = {x["word"]: x for x in json.load(open(S20 / "lextag_out.json", encoding="utf-8"))["items"]}
    maxid = max(int(e["entry_id"][2:]) for e in es)
    rows = []

    def new_entry(word, def1, tags, flags, pages, src5, printed, dict_id="5"):
        nonlocal maxid
        maxid += 1
        e = {"entry_id": f"e_{maxid:05d}", "word": word, "word_base": word, "dict_id": dict_id, "tags": tags,
             "def1": def1, "def2": "", "misc1": "", "misc2": "", "lextag": "", "lextag_conf": "",
             "src1": [], "src2": [], "src5": src5, "src5_pages": pages, "word1_orig": "", "word2_orig": "",
             "word5_orig": printed, "decl": "", "hom_rank": 99, "flags": flags}
        if dict_id != "5":                              # not from the 1965 dictionary: no fields of it
            for k in ("src5", "src5_pages", "word5_orig"):
                e.pop(k)
        if word in lex:
            e["lextag"], e["lextag_conf"] = lex[word]["lextag"], lex[word].get("confidence", "")
        es.append(e)
        byw[word] = e
        return e

    for n in p["new"]:
        fl = ["rus_kb_added"] + (["linguist_fix"] if n["linguist"] else [])
        new_entry(n["word"], n["gloss"], n["tags"], fl, n["pages"], n["src5"], n["printed"])
        rows.append({"op": "new", "word": n["word"], "def1": n["gloss"], "item": n["item"], "pages": n["pages"],
                     "verdict": n["verdict"]})
    for u in p["update"]:
        e = byw[u["word"]]
        old = e.get("def1") or ""
        if "set_def1" in u:                             # the translation of the 1965 dictionary: its pages
            e["def1"] = u["set_def1"]
            e["src5"], e["src5_pages"] = u["src5"], u["pages"]
            fl = ["rus_kb_gloss"]
        else:                                           # only the linguist's words: no page of the book
            e["def1"] = (old.rstrip("; ") + "; " + u["append_def1"]) if old.strip() else u["append_def1"]
            fl = []
        e["flags"] = list(dict.fromkeys((e.get("flags") or []) + fl + (["linguist_fix"] if u["linguist"] else [])))
        rows.append({"op": "update", "word": e["word"], "old_def1": old, "def1": e["def1"], "item": u["item"],
                     "verdict": u["verdict"]})
    for v in p["variant_new"]:
        t = byw[v["target"]]
        e = new_entry(v["word"], "", "", ["rus_kb_variant"], v["pages"], v["src5"], v["printed"])
        e["variant_of_rkbs"] = t["word"]
        if not e["lextag"]:
            e["lextag"], e["lextag_conf"] = t.get("lextag", ""), t.get("lextag_conf", "")
        rows.append({"op": "variant_new", "word": e["word"], "variant_of": t["word"], "item": v["item"]})
    for n in p.get("linguist_new", []):                # the linguist's own words (chat 2026-11-14): dict_id L
        e = new_entry(n["word"], n["def1"], n["tags"], ["linguist_added", "linguist_fix"], [], [], "", dict_id="L")
        e["lextag"], e["lextag_conf"] = n["lextag"], ("high" if n["lextag"] else "")
        rows.append({"op": "linguist_new", "word": e["word"], "def1": e["def1"], "item": n["item"]})
    for u in p.get("linguist_gloss", []):              # the linguist's translation for an entry without one
        e = byw[u["word"]]
        e["def1"] = u["set_def1"]
        e["flags"] = list(dict.fromkeys((e.get("flags") or []) + ["linguist_gloss", "linguist_fix"]))
        rows.append({"op": "linguist_gloss", "word": e["word"], "old_def1": "", "def1": e["def1"], "item": u["item"]})
    for v in p["variant_link"]:
        e = byw[v["word"]]
        e["variant_of_rkbs"] = v["target"]
        e["flags"] = list(dict.fromkeys((e.get("flags") or []) + ["rus_kb_variant_link"]))
        rows.append({"op": "variant_link", "word": e["word"], "variant_of": v["target"], "item": v["item"]})
    for u in p["unflag"]:
        for w in u["words"]:
            e = byw[w]
            e["flags"] = [f for f in e["flags"] if f != "needs_review"]
            rows.append({"op": "unflag", "word": w, "flag": "needs_review"})
    for e in es:
        if e["word"] in {r["word"] for r in rows if r["op"] in ("update", "variant_link", "linguist_gloss")}:
            for k in [k for k in list(e) if k.startswith(("misc1_", "misc2_"))]:
                e.pop(k, None)
    es.sort(key=lambda e: e["word"])
    save_jsonl(F06, es)
    save_jsonl(JOURNAL, rows)
    print(json.dumps({"entries": len(es), **Counter(r["op"] for r in rows),
                      "without_lextag": sum(1 for e in es if e.get("dict_id") == "5" and not e.get("lextag"))},
                     ensure_ascii=False))


def lextag_in():
    """the new entries without a lextag -> checkpoints/shards/s20/lextag_in.json (for an agent, prompt s5_lextag.md;
    its answer: lextag_out.json {"items": [{word, lextag, confidence}]}, read by apply)"""
    p = json.load(open(S20 / "plan.json", encoding="utf-8"))
    items = [{"word": n["word"], "tags": n["tags"], "def1": n["gloss"], "def2": ""} for n in p["new"]]
    jdump(items, S20 / "lextag_in.json")
    print(len(items))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["answers", "pages", "plan", "apply", "lextag_in"])
    a = ap.parse_args()
    {"answers": answers, "pages": pages_phase, "plan": plan, "apply": apply, "lextag_in": lextag_in}[a.phase]()
