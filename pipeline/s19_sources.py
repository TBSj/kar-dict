# -*- coding: utf-8 -*-
"""S19: where every corpus entry comes from — source + page (linguist's request 2026-11-06, copyright).

The export (s7_export.py) adds the field «sources» to 07_final.jsonl / final.csv / final.xlsx:
the printed sources of the entry with their pages, comma-separated, e.g.
    КБРС-1989 с. 101, ТСКБЯ т. 1 с. 230
The legend (full bibliographic records, what is taken from each source) is docs/SOURCES.md and the
sheet «источники» of final.xlsx.

Pages:
  ТСКБЯ   02_dict2_segmented.jsonl keeps vol + page of every d2 record; «page» there is the 0-based PDF
          index, which equals the printed page number in all three volumes (checked on page images:
          т. 1 PDF 40 = с. 39, т. 2 PDF 300 = с. 299, т. 3 PDF 300 = с. 299).
  КБРС    the qmos export has no pages.  The scan (#26, no text layer; PDF page = printed page) is read
          by vision agents: the first article headwords at the top of both columns of every page
          (phase kbrs_crops -> agents -> kbrs_check), then aligned to the qmos sequence, which is in
          book order (phase kbrs_align -> checkpoints/shards/s19/kbrs_pages.json).  The 299 articles of
          the three lost blocks (s17) have their pages from the scan reading.
  Гузеев  page of the homonym (step 3, s18), once the corpus carries the Гузеев link.

Phases:
  kbrs_crops   local/kbrs_pages/img/pNNN.png: top 30 % of every dictionary page, both columns
  kbrs_check   validate an agent's file local/kbrs_pages/out/kNN.json
  kbrs_crops2  second pass: whole pages (two halves) whose left column shows no article start at the top
  kbrs_check2  validate an agent's file local/kbrs_pages/out2/qN.json
  kbrs_align   heads -> qmos seqid -> page (+ the page range of an article that runs over whole pages);
               report of unplaced / doubtful pages; heads with no qmos record near their page
  qmos_gaps    КБРС articles qmos may have lost: those heads + KB words qmos articles point to that are
               no qmos key -> checkpoints/shards/s19/qmos_gaps.json
  gapprep      scan check of those candidates: page halves + batches local/kbrs_pages/gaps_in/gNN
  gapcheck     validate an agent's file local/kbrs_pages/gaps_out/gNN.json
  stats        how many entries cite each source, entries without a page
"""
import json, re, sys, argparse, unicodedata
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S19 = CK / "shards" / "s19"
LOC = ROOT / "local" / "kbrs_pages"
QMOS = ROOT / "sources" / "1" / "qmos_def_32499.txt"
KBRS_PDF = r"D:/Къагъыт/Къарачай/Китаб/Сёзлюкле/Карачаево-балкарско-русский словарь.pdf"
KBRS_FIRST, KBRS_LAST = 15, 832          # p. 14 = end of the abbreviations; the body starts on p. 15
BATCH = 63


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


# ------------------------------------------------------------------ КБРС crops for the agents
def kbrs_batches():
    pages = list(range(KBRS_FIRST, KBRS_LAST + 1))
    return {f"k{i // BATCH + 1:02d}": pages[i:i + BATCH] for i in range(0, len(pages), BATCH)}


def kbrs_crops(zoom=2.0):
    import fitz
    (LOC / "img").mkdir(parents=True, exist_ok=True)
    doc = fitz.open(KBRS_PDF)
    for p in range(KBRS_FIRST, KBRS_LAST + 1):
        pg = doc[p - 1]
        r = pg.rect
        pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(0, r.height * 0.04, r.width, r.height * 0.34))
        pix.save(LOC / "img" / f"p{p:03d}.png")
    b = kbrs_batches()
    json.dump(b, open(LOC / "batches.json", "w", encoding="utf-8"))
    print(json.dumps({"pages": KBRS_LAST - KBRS_FIRST + 1, "batches": {k: [v[0], v[-1]] for k, v in b.items()}}))


def kbrs_crops2(zoom=1.8):
    """second pass: dictionary pages whose top third showed no article start (a long article runs over
    the top) — the whole page, so the first article that starts lower down is found"""
    import fitz
    heads = {}
    for f in sorted((LOC / "out").glob("k*.json")):
        for r in json.load(open(f, encoding="utf-8"))["pages"]:
            heads[r["page"]] = r
    # the first article of a page is the first start in the LEFT column; when the top third of the left
    # column shows none, it may start lower down in that column (before anything in the right column)
    todo = [p for p, r in sorted(heads.items())
            if not r["L"] and "not a dictionary" not in (r.get("note") or "").lower()]
    (LOC / "img2").mkdir(parents=True, exist_ok=True)
    doc = fitz.open(KBRS_PDF)
    for p in todo:
        pg = doc[p - 1]
        r = pg.rect
        for i, (y0, y1) in enumerate(((0.04, 0.53), (0.47, 0.97)), 1):
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(0, r.height * y0, r.width, r.height * y1))
            pix.save(LOC / "img2" / f"p{p:03d}_{i}.png")
    json.dump(todo, open(LOC / "pass2_pages.json", "w", encoding="utf-8"))
    n = 3
    parts = {f"q{i + 1}": todo[i * len(todo) // n:(i + 1) * len(todo) // n] for i in range(n)}
    json.dump(parts, open(LOC / "pass2_batches.json", "w", encoding="utf-8"))
    print(json.dumps({"pages": len(todo), "batches": {k: [v[0], v[-1], len(v)] for k, v in parts.items()}}))


def kbrs_check2(name):
    todo = json.load(open(LOC / "pass2_batches.json", encoding="utf-8"))[name]
    try:
        d = json.load(open(LOC / "out2" / f"{name}.json", encoding="utf-8"))
    except Exception as ex:
        print(f"INVALID JSON: {ex}")
        return 1
    got = {r.get("page"): r for r in d.get("pages", [])}
    errs = [f"missing page {p}" for p in todo if p not in got]
    for p, r in got.items():
        if p not in todo:
            errs.append(f"page {p} not in the list")
        v = r.get("first")
        if not isinstance(v, list) or len(v) > 2 or not all(isinstance(x, str) and x.strip() for x in v):
            errs.append(f"page {p}: «first» must be a list of 0–2 headwords")
    print("OK" if not errs else "ERRORS:\n" + "\n".join(errs))
    return 0 if not errs else 1


def kbrs_check(name):
    pages = kbrs_batches()[name]
    f = LOC / "out" / f"{name}.json"
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as ex:
        print(f"INVALID JSON {f}: {ex}")
        return 1
    errs = []
    got = {}
    for r in d.get("pages", []):
        if not isinstance(r.get("page"), int):
            errs.append(f"bad page record {r}")
            continue
        if r["page"] in got:
            errs.append(f"page {r['page']} twice")
        got[r["page"]] = r
        for c in ("L", "R"):
            v = r.get(c)
            if not isinstance(v, list) or len(v) > 2 or not all(isinstance(x, str) and x.strip() for x in v):
                errs.append(f"page {r['page']}: {c} must be a list of 0–2 non-empty headwords")
    miss = [p for p in pages if p not in got]
    extra = [p for p in got if p not in pages]
    if miss:
        errs.append(f"missing pages {miss}")
    if extra:
        errs.append(f"pages not in this batch {extra}")
    print("OK" if not errs else "ERRORS:\n" + "\n".join(errs))
    return 0 if not errs else 1


# ------------------------------------------------------------------ КБРС alignment
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}


def kfold(w):
    """print form / qmos key -> comparison key: no stress, ў -> у, нъ -> нг, кь/гь -> къ/гъ, ё -> е"""
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn" or c == "\u0306")
    w = unicodedata.normalize("NFC", w).replace("ў", "у").replace("нъ", "нг")
    w = w.replace("кь", "къ").replace("гь", "гъ").replace("ё", "е").replace("й", "й")
    return re.sub(r"[^а-яъь\-]", "", w)


def split_head(h):
    """«акъ II» -> ("акъ", 2); «акъ» -> ("акъ", None)"""
    m = re.match(r"^(.*?)\s*\b(I{1,3}|IV|V|VI{0,2})\s*$", h.strip())
    if m and m.group(1):
        return kfold(m.group(1)), ROMAN[m.group(2)]
    return kfold(h), None


def qmos_seq():
    q = json.load(open(QMOS, encoding="utf-8"))
    seq = []
    for k, v in q.items():
        w, sid = k.rsplit("_", 1)
        m = re.match(r"^\W*(VI{0,2}|IV|I{1,3})(?![IVXa-zA-Z])", v or "")   # «I1. …», «IIминеральный …»
        t = re.match(r"^\W*-([а-яёА-ЯЁўЎ́]+)", v or "")              # «аман-аман» = key аман + «-аман …»
        p = re.match(r"^\W*пар[нк][.,]", v or "")                     # «$парн. к %@аз-#» (once «парк,»)
        seq.append({"sid": int(sid), "key": kfold(w), "hom": ROMAN.get(m.group(1)) if m else None,
                    "tail": kfold(t.group(1)) if t else None, "parn": bool(p)})
    return seq


def lev(a, b, cap):
    """edit distance of a and b, or cap + 1 as soon as it exceeds cap"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def head_candidates(h, pos_of, seq, fuzzy=None):
    """qmos positions where a page head can be:
      - the key itself (+ homonym numeral);
      - «X-Y»: key X whose value starts with the tail «-Y» — qmos glues the tail to the translation
        («башсыз» = «-тюбсюзуклончивый …»), so the tail is compared by its beginning;
      - «-Y»: the second part of a paired word, printed as an article of its own, is kept in qmos under
        key Y with the value «парн. к X-» («-буз» = буз «парн. к аз-»);
      - fuzzy = {first two letters: {key: [positions]}}: a key garbled in qmos (ратификацион printed,
        «ратификацией» in qmos) within 1 edit, 2 for keys of 8 letters and more — only if nothing else
        matched; the page order (longest chain in kbrs_align) drops a wrong guess"""
    h = re.sub(r"\(.*?\)", "", h)
    h = re.sub(r"\s+(I{1,3}|IV|V)(\s*,\s*(I{1,3}|IV|V))+\s*$", r" \1", h)   # «… I, II» -> first numeral
    key, hom = split_head(h)
    if key.startswith("-"):
        key = key.lstrip("-")
        out = list(pos_of.get(key, []))
        out = [i for i in out if seq[i]["parn"]] or out
    else:
        out = list(pos_of.get(key, []))
    if "-" in key and not out:
        a, b = key.split("-", 1)
        b = b.replace("-", "")
        out = [i for i in pos_of.get(a, []) if b and (seq[i]["tail"] or "").startswith(b)]
    if not out and fuzzy is not None and len(key) >= 5:
        # a garble keeps the length (letters misread: ратификацион / «ратификацией», тюлень / «тюленг») or
        # loses a final soft / hard sign (коммуналь / «коммунал»); a word a suffix longer or shorter is
        # another article of the same family (джылан ≠ джыланлы), not a garble
        cap = 2 if len(key) >= 8 else 1
        out = [i for k, ps in fuzzy.get(key[:2], {}).items()
               if k != key and (len(k) == len(key) or k.rstrip("ьъ") == key.rstrip("ьъ")) and lev(key, k, cap) <= cap
               for i in ps]
    if hom is not None:
        out = [i for i in out if seq[i]["hom"] == hom] or out
    return out


def dup_runs(min_len=20):
    """qmos stretches the corpus never uses: copies of whole sections inside the export (the Къ section
    twice: 12360–15156 and 15157–17885; Гъ twice: 5914–5945) and the three neighbour pages that came
    instead of the lost blocks (801–900, 7246–7345, 18263–18362). Out of book order -> not aligned."""
    used = {int(s) for e in load_jsonl(CK / "06_lextagged.jsonl") for s in e.get("src1") or []}
    sids = [int(k.rsplit("_", 1)[1]) for k in json.load(open(QMOS, encoding="utf-8"))]
    runs, cur = [], []
    for s in sids:
        if s in used:
            if len(cur) >= min_len:
                runs.append((cur[0], cur[-1]))
            cur = []
        else:
            cur.append(s)
    if len(cur) >= min_len:
        runs.append((cur[0], cur[-1]))
    return runs


def kbrs_align(window=6000):
    runs = dup_runs()
    seq = [r for r in qmos_seq() if not any(a <= r["sid"] <= b for a, b in runs)]
    pos_of = defaultdict(list)
    for i, r in enumerate(seq):
        pos_of[r["key"]].append(i)
    fuzzy = defaultdict(lambda: defaultdict(list))
    for i, r in enumerate(seq):
        fuzzy[r["key"][:2]][r["key"]].append(i)
    heads = {}
    for f in sorted((LOC / "out").glob("k*.json")):
        for r in json.load(open(f, encoding="utf-8"))["pages"]:
            heads[r["page"]] = r
    # the top third of the left column has no article start: the article before continues onto the page
    cont_top = {p: not r.get("L") for p, r in heads.items()}
    for f2 in sorted((LOC / "out2").glob("q*.json")):   # whole-page reading of pages without a start
        for r in json.load(open(f2, encoding="utf-8"))["pages"]:      # in the top third of the left column
            if r.get("first"):
                h1 = heads.get(r["page"], {})
                if r.get("where") == "R":                 # the first starts are in R: L has none
                    L, R = [], r["first"] + [h for h in h1.get("R", []) if h not in r["first"]]
                else:                                     # first starts lower in L: R of the first pass stays
                    L, R = r["first"], h1.get("R", [])
                heads[r["page"]] = {"page": r["page"], "L": L, "R": R, "note": "pass2"}
    # pages with no article start at all (both columns continue one long article: алыргъа, аман, бир …)
    no_start = {p for p, r in heads.items() if not r.get("L") and not r.get("R")}
    # every head -> its candidate positions near the linear estimate (≈ 42 records a page), then the longest
    # chain of pages whose positions grow with the page number (heads of one page must also be in order)
    body = [p for p in range(KBRS_FIRST, KBRS_LAST + 1) if heads.get(p) and
            "not a dictionary" not in (heads[p].get("note") or "").lower()]
    last_body = max(body)
    per_page = len(seq) / (last_body - KBRS_FIRST + 1)
    cand = []                                     # (page, rank of the head on the page, position)
    report, unmatched = [], []
    for p in body:
        r = heads[p]
        hs = [(c, h) for c in ("L", "R") for h in r.get(c, [])]
        est = (p - KBRS_FIRST) * per_page
        exact = [[i for i in head_candidates(h, pos_of, seq) if abs(i - est) <= window] for c, h in hs]
        for rank, (c, h) in enumerate(hs):
            near = exact[rank]
            if not near:
                # a key garbled in qmos: taken only 1–3 records before an exact match of the next head of
                # the same page (ратификацией -> ратификация); a near-spelled other word (айырыргъа, lost in
                # qmos, ~ айырылыргъа seven records earlier) is not
                nxt = exact[rank + 1] if rank + 1 < len(hs) else []
                fz = [i for i in head_candidates(h, pos_of, seq, fuzzy) if any(1 <= j - i <= 3 for j in nxt)]
                unmatched.append({"page": p, "column": c, "rank": rank, "head": h,
                                  "fuzzy": [seq[i]["key"] for i in fz]})
                near = fz
            for i in near:
                cand.append((p, rank, i, c, h))
    # longest chain: pages strictly increasing, positions strictly increasing (one candidate per page,
    # the page's first head preferred)
    import bisect
    by_page = defaultdict(list)
    for x in cand:
        by_page[x[0]].append(x)
    # LIS over positions, at most one candidate per page: a page's candidates extend only chains built
    # from earlier pages (snapshot), and for every chain length the smallest end position is kept
    lis_pos, lis_item, prev_of = [], [], {}
    for p in sorted(by_page):
        snap_pos, snap_item = list(lis_pos), list(lis_item)
        ups = {}
        for x in by_page[p]:
            k = bisect.bisect_left(snap_pos, x[2])
            if k not in ups or x[2] < ups[k][2]:
                ups[k] = x
        for k, x in ups.items():
            prev_of[x] = snap_item[k - 1] if k > 0 else None
            if k == len(lis_pos):
                lis_pos.append(x[2]); lis_item.append(x)
            elif x[2] < lis_pos[k]:
                lis_pos[k] = x[2]; lis_item[k] = x
    chain, x = [], (lis_item[-1] if lis_item else None)
    while x is not None:
        chain.append(x)
        x = prev_of.get(x)
    chain.reverse()
    starts = {}
    for p, rank, i, c, h in chain:
        starts[p] = i
        if rank > 0:                              # an earlier head of the page matched nothing
            report.append({"page": p, "problem": "start from a later head", "head": h, "column": c})
    # the three blocks lost by qmos (s17): the qmos record right after a block is printed on the block's
    # last page, whose own first articles are not in qmos — anchor it there
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from s17_kbrs_blocks import BLOCKS
    idx = {r["sid"]: i for i, r in enumerate(seq)}
    for b in BLOCKS.values():
        last = max(b["pages"])
        i = idx[b["before"]]
        if last not in starts or starts[last] > i:
            starts[last] = i
            report.append({"page": last, "problem": "anchored after a lost block", "sid": b["before"]})
    for p in body:
        if p not in starts:
            report.append({"page": p, "problem": "not located", "heads": [h for c in ("L", "R") for h in heads[p].get(c, [])],
                           "note": heads[p].get("note", "")})
    # every qmos record -> the last page whose first article starts at or before it
    page_of, plist = {}, sorted(starts.items())
    for (p, i0), nxt in zip(plist, plist[1:] + [(None, len(seq))]):
        for i in range(i0, nxt[1]):
            page_of[seq[i]["sid"]] = p
    first_p = plist[0][0] if plist else None
    for i in range(0, plist[0][1] if plist else 0):
        page_of[seq[i]["sid"]] = first_p                # records before the first located start
    # the last article before a page's first start runs on through the pages without any start, and onto
    # the next page when the top third of its left column has no start (only what the reading shows:
    # an article that ends a few lines into the next page keeps its start page alone)
    span_of = {}
    for (p, i0), (q, i1) in zip(plist, plist[1:]):
        if i1 == 0:
            continue
        end = p
        while end + 1 < q and end + 1 in no_start:
            end += 1
        if end + 1 == q and cont_top.get(q):
            end = q
        if end > p:
            span_of[seq[i1 - 1]["sid"]] = end
    S19.mkdir(parents=True, exist_ok=True)
    json.dump({"pages_located": len(starts), "records": len(page_of), "page_of": page_of, "span_of": span_of},
              open(S19 / "kbrs_pages.json", "w", encoding="utf-8"))
    json.dump(report, open(S19 / "kbrs_pages_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # heads read on the scan that match no qmos record near their page: candidates for articles qmos lost,
    # glued into a neighbour or garbled beyond the fuzzy match (s17 block pages excluded: lost on purpose)
    blk = {p for b in BLOCKS.values() for p in b["pages"]}
    unmatched = [u for u in unmatched if u["page"] not in blk]
    for u in unmatched:
        p = u["page"]
        prev = max((x for x in plist if x[0] <= p), default=None)
        u["qmos_near"] = [seq[i]["key"] for i in range(max(0, prev[1] - 3), min(len(seq), prev[1] + 6))] if prev else []
    json.dump(unmatched, open(S19 / "kbrs_unmatched_heads.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"pages_located": len(starts), "records_paged": len(page_of), "records_spanning": len(span_of),
                      "heads_unmatched": len(unmatched), "problems": Counter(x["problem"] for x in report)},
                     ensure_ascii=False))


# ------------------------------------------------------------------ КБРС articles missing from qmos
# a KB word a qmos article points to: «$отвлеч. к %@айырыргъа#», «$и. д.%$к %@тёлерге#», «$то же, что %@…»
REF = re.compile(r"(?:\bк|\bот|\bсм\.|\bчто)\s+[$%#\s]*@([А-Яа-яЁёЎў́]+(?:-[А-Яа-яЁёЎў́]+)?)")


def qmos_gaps(near=40):
    """КБРС articles the qmos export does not have. The survey (Н1) found none in a sample of 365 heads
    (upper bound ≈0.8 %); two independent signals over the whole book:
      head  an article start read on the scan for kbrs_align (the first 1–2 starts of both columns of
            every page, ≈3 000 heads) with no qmos key near its page: hyphen compounds (qmos keeps «X-Y»
            as key X + tail, or glued into X) and garbled keys taken by the anchored fuzzy match excluded;
      ref   a KB word that qmos articles point to and that is no qmos key;
    every candidate -> qmos keys within 2 edits among the records near it (a garble of the key or of the
    reference, not a loss), its estimated page, and the corpus: has the word a КБРС side (an entry whose
    word1_orig is that word)?  -> checkpoints/shards/s19/qmos_gaps.json"""
    q = json.load(open(QMOS, encoding="utf-8"))
    runs = dup_runs()
    seq = [r for r in qmos_seq() if not any(a <= r["sid"] <= b for a, b in runs)]
    pos = {r["sid"]: i for i, r in enumerate(seq)}
    keys = {r["key"] for r in seq}
    vals = {int(k.rsplit("_", 1)[1]): v for k, v in q.items()}
    page_of = {int(k): v for k, v in json.load(open(S19 / "kbrs_pages.json", encoding="utf-8"))["page_of"].items()}
    es = load_jsonl(CK / "06_lextagged.jsonl")
    kb_side = {kfold(e["word1_orig"]) for e in es if e.get("dict_id") in ("1", "both") and e.get("word1_orig")}
    stem = lambda w: re.sub(r"(?<=[аеёиоуыэюя])(ргъа|рге)$|(ыргъа|ирге|урургъа|юрюрге|ургъа|юрге)$", "", w)
    d2_only = defaultdict(list)                     # stem of the corpus word -> ТСКБЯ-only entries
    for e in es:
        if e.get("dict_id") == "2":
            d2_only[kfold(re.sub(r"\d+$", "", e.get("word2_orig") or e["word"]))].append(e["word"])

    def near_keys(w, i):
        cap = 2 if len(w) >= 8 else 1
        lo, hi = max(0, i - near), min(len(seq), i + near)
        # a garble keeps the length or loses a final ь / ъ (as in head_candidates): a word a suffix longer
        # is a neighbour of the same family (айырыргъа ~ айырылыргъа), not the same article garbled
        return sorted({k for j in range(lo, hi) for k in [seq[j]["key"]]
                       if k != w and (len(k) == len(w) or k.rstrip("ьъ") == w.rstrip("ьъ")) and lev(w, k, cap) <= cap})

    cands = {}
    for u in json.load(open(S19 / "kbrs_unmatched_heads.json", encoding="utf-8")):
        h = kfold(re.sub(r"\(.*?\)", "", u["head"])).strip("-")
        if "-" in h or u["fuzzy"]:
            continue
        c = cands.setdefault(h, {"word": h, "signals": [], "pages": set(), "refs": []})
        c["signals"].append("head")
        c["pages"].add(u["page"])
    for r in seq:
        for m in REF.finditer(vals.get(r["sid"], "") or ""):
            w = kfold(m.group(1)).strip("-")
            if len(w) < 3 or w in keys:
                continue
            c = cands.setdefault(w, {"word": w, "signals": [], "pages": set(), "refs": []})
            if "ref" not in c["signals"]:
                c["signals"].append("ref")
            c["refs"].append(r["sid"])
            if r["sid"] in page_of:
                c["pages"].add(page_of[r["sid"]])
    out = []
    for w, c in cands.items():
        anchor = [pos[s] for s in c["refs"] if s in pos]
        if not anchor and c["pages"]:
            p = min(c["pages"])
            anchor = [i for i, r in enumerate(seq) if page_of.get(r["sid"]) == p][:1]
        nk = sorted({k for i in anchor[:3] for k in near_keys(w, i)})
        st = stem(w)
        out.append({"word": w, "signals": c["signals"], "refs": len(c["refs"]),
                    "referred_by": [seq[pos[s]]["key"] for s in c["refs"][:4] if s in pos],
                    "pages": sorted(c["pages"]), "near_keys": nk,
                    "kbrs_side_in_corpus": w in kb_side,
                    "tskbya_only_entries": sorted(set(d2_only.get(st, []) + d2_only.get(w, [])))[:4],
                    "kind": "garbled" if nk else ("in_corpus" if w in kb_side else "lost?")})
    out.sort(key=lambda x: (x["kind"] != "lost?", -len(x["signals"]), -x["refs"], x["word"]))
    S19.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(S19 / "qmos_gaps.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by = Counter(x["kind"] for x in out)
    lost = [x for x in out if x["kind"] == "lost?"]
    print(json.dumps({"candidates": len(out), "by_kind": by,
                      "lost_both_signals": sum(1 for x in lost if len(x["signals"]) == 2),
                      "lost_with_tskbya_entry": sum(1 for x in lost if x["tskbya_only_entries"]),
                      "top": [(x["word"], x["signals"], x["refs"], x["pages"][:2], x["tskbya_only_entries"][:2]) for x in lost[:40]]},
                     ensure_ascii=False, indent=0))


GAP_STATUS = ("lost", "garbled_key", "glued", "ref_typo", "not_printed", "unsure")


def gapprep(per_file=14, zoom=2.0):
    """qmos_gaps candidates «lost?» and «garbled» -> scan check: half-page images of the pages where each
    should be printed (local/kbrs_pages/img3/pNNN_{1,2}.png) and batches local/kbrs_pages/gaps_in/gNN.txt
    (+ .json: the candidate words of the batch).  The page: that of the article pointing to the word
    (and the page before when that article is among the first three of its page), or that of the head."""
    import fitz
    G = [x for x in json.load(open(S19 / "qmos_gaps.json", encoding="utf-8")) if x["kind"] in ("lost?", "garbled")]
    q = json.load(open(QMOS, encoding="utf-8"))
    runs = dup_runs()
    seq = [r for r in qmos_seq() if not any(a <= r["sid"] <= b for a, b in runs)]
    raw = {int(k.rsplit("_", 1)[1]): (k.rsplit("_", 1)[0], v) for k, v in q.items()}
    pos = {r["sid"]: i for i, r in enumerate(seq)}
    page_of = {int(k): v for k, v in json.load(open(S19 / "kbrs_pages.json", encoding="utf-8"))["page_of"].items()}
    first3 = defaultdict(list)
    for r in seq:
        p = page_of.get(r["sid"])
        if p is not None and len(first3[p]) < 3:
            first3[p].append(r["sid"])
    refs_of = defaultdict(list)
    for r in seq:
        for m in REF.finditer(raw[r["sid"]][1] or ""):
            refs_of[kfold(m.group(1)).strip("-")].append(r["sid"])
    items = []
    for x in G:
        sids = refs_of.get(x["word"], [])[:4]
        pages = set(x["pages"]) if "head" in x["signals"] else set()
        for s in sids:
            p = page_of.get(s)
            if p:
                pages.add(p)
                if s in first3[p] and p - 1 >= KBRS_FIRST:
                    pages.add(p - 1)
        pages = sorted(pages)[:3]
        if not pages:
            continue
        i0 = pos[sids[0]] if sids else min((i for i, r in enumerate(seq) if page_of.get(r["sid"]) == pages[0]), default=0)
        around = [f"{raw[seq[j]['sid']][0]}_{seq[j]['sid']}: {cut_text(raw[seq[j]['sid']][1], 90)}"
                  for j in range(max(0, i0 - 6), min(len(seq), i0 + 5))]
        items.append({"word": x["word"], "signals": x["signals"], "pages": pages, "near_keys": x["near_keys"],
                      "refs": [f"{raw[s][0]}_{s}: {cut_text(raw[s][1], 140)}" for s in sids], "around": around})
    items.sort(key=lambda it: it["pages"][0])
    need = sorted({p for it in items for p in it["pages"]})
    (LOC / "img3").mkdir(parents=True, exist_ok=True)
    doc = fitz.open(KBRS_PDF)
    for p in need:
        if (LOC / "img3" / f"p{p:03d}_2.png").exists():
            continue
        pg = doc[p - 1]
        r = pg.rect
        for k, (y0, y1) in enumerate(((0.03, 0.53), (0.47, 0.98)), 1):
            pix = pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(0, r.height * y0, r.width, r.height * y1))
            pix.save(LOC / "img3" / f"p{p:03d}_{k}.png")
    out = LOC / "gaps_in"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("g*.*"):
        f.unlink()
    groups = [items[i:i + per_file] for i in range(0, len(items), per_file)]
    for gi, grp in enumerate(groups, 1):
        name = f"g{gi:02d}"
        L = [f"GAPS {name}: {len(grp)} candidate words."]
        for it in grp:
            L += ["", f"=== {it['word']}   signals: {', '.join(it['signals'])}   look on pages: {it['pages']}",
                  "  images: " + ", ".join(str(LOC / 'img3' / f'p{p:03d}_{k}.png') for p in it["pages"] for k in (1, 2))]
            if it["refs"]:
                L.append("  qmos articles pointing to it:")
                L += [f"    {s}" for s in it["refs"]]
            if it["near_keys"]:
                L.append(f"  qmos keys spelled within 2 letters of it near there: {it['near_keys']}")
            L.append("  qmos records around the place (key_seqid: value; qmos markup: $ italic label, % / @ / # font switches, ~ = headword):")
            L += [f"    {s}" for s in it["around"]]
        (out / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump([it["word"] for it in grp], open(out / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({"candidates": len(items), "pages": len(need), "batches": len(groups)}))


def cut_text(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def gapcheck(name):
    words = json.load(open(LOC / "gaps_in" / f"{name}.json", encoding="utf-8"))
    try:
        d = json.load(open(LOC / "gaps_out" / f"{name}.json", encoding="utf-8"))
    except Exception as ex:
        print(f"INVALID JSON: {ex}")
        return 1
    got = {r.get("word"): r for r in d.get("items", [])}
    errs = [f"missing {w}" for w in words if w not in got]
    errs += [f"not in the batch: {w}" for w in got if w not in words]
    for w, r in got.items():
        if r.get("status") not in GAP_STATUS:
            errs.append(f"{w}: status must be one of {GAP_STATUS}")
        if r.get("status") in ("lost", "garbled_key", "glued") and not isinstance(r.get("page"), int):
            errs.append(f"{w}: page (int) required for {r.get('status')}")
        if r.get("status") in ("garbled_key", "glued", "ref_typo") and not (r.get("qmos_key") or "").strip():
            errs.append(f"{w}: qmos_key required for {r.get('status')} (the qmos key it hides under / the real headword)")
        if r.get("status") in ("lost", "garbled_key", "glued") and not (r.get("printed_head") or "").strip():
            errs.append(f"{w}: printed_head required (the headword as printed)")
    print("OK" if not errs else "ERRORS:\n" + "\n".join(errs))
    return 0 if not errs else 1


# ------------------------------------------------------------------ the «sources» field
# code, full record, what the corpus takes, how it was obtained, rights (as printed) — the legend of the
# sheet «источники» in final.xlsx; docs/SOURCES.md says the same in more words
LEGEND = [
    {"code": "КБРС-1989",
     "record": "Гочияева С. А., Суюнчев Х. И. Карачаево-балкарско-русский словарь: около 30 000 слов / "
               "Карачаево-Черкесский НИИ истории, филологии и экономики; под ред. Э. Р. Тенишева и Х. И. Суюнчева. — "
               "М.: Русский язык, 1989. — 832 с. — ISBN 5-200-00325-3",
     "fields": "word1_orig, def1 (русский перевод), misc1 (примеры, фразеология, пословицы с переводом), decl, "
               "часть помет в tags (dict_id 1 и both)",
     "how": "цифровая выгрузка qmos (sources/1/qmos_def_32499.txt, 32 499 записей в порядке книги); 3 блока "
            "по ≈100 статей, потерянные выгрузкой (с. 42–45, 228–231, 456–458), прочитаны со скана; страницы — по скану",
     "rights": "© Издательство «Русский язык», 1989 (так на обороте титула)"},
    {"code": "ТСКБЯ",
     "record": "Къарачай-малкъар тилни ангылатма сёзлюгю. Ючтомлукъ / Толковый словарь карачаево-балкарского языка: "
               "в 3 т. / Институт гуманитарных исследований (КБНЦ РАН); гл. ред. Ж. М. Гузеев. — Нальчик: Эль-Фа. "
               "Т. 1: А–Ж. — 1996; т. 2: З–Р. — 2002; т. 3: С–Я. — 2005",
     "fields": "word2_orig, def2 (русский перевод значений, он есть в самом словаре), misc2 (толкования на КБ, "
               "примеры, цитаты с указанием источника), пометы в tags (ат., сыф., эт., къарач. …), номера омонимов "
               "(dict_id 2 и both)",
     "how": "PDF sources/2/ТСКБЯ - 1..3.pdf (текстовый слой FineReader) -> разбор статей моделью (этапы S1–S2); "
            "т. 2–3, с. 11–17 добавлены отдельно (s12); страница = печатный номер",
     "rights": "Издательский центр «Эль-Фа», Нальчик; тираж 5000 экз. каждого тома"},
    {"code": "Гузеев-2013",
     "record": "Гузеев Ж. М. (Гузеланы Ж. М.) Къарачай-малкъар тилни омонимлерини сёзлюгю / Словарь омонимов "
               "карачаево-балкарского языка / Институт гуманитарных исследований КБНЦ РАН; науч. ред. Б. А.-К. Мусукаев. — "
               "М.: Эльбрусоид, 2013. — 496 с. — ISBN 978-5-4245-0002-2",
     "fields": "деление на омонимы и их нумерация, пометы части речи при омонимах (шаг 3 обзора); заготовки омонимов, "
               "которых нет ни в КБРС, ни в ТСКБЯ (dict_id 3: слово, номер, часть речи, без перевода); текст толкований "
               "и цитаты книги в корпус не берутся (решение по В15, 6 ноября 2026)",
     "how": "PDF из вёрстки (чистый текстовый слой), разбор по шрифтам (pipeline/s18_guzeev.py)",
     "rights": "издание 2013 г., тираж 1000 экз."},
    {"code": "правка лингвиста",
     "record": "решения лингвиста проекта по вопросам в таблицах review_queues (pipeline/s16_linguist_answers.py)",
     "fields": "исправленные толкования, слияния статей (флаг linguist_fix)", "how": "ответы в чате, с датой в коде",
     "rights": "—"},
]


def page_runs(pages):
    """[101, 102, 105] -> «101–102; 105»"""
    ps = sorted(set(pages))
    runs, start = [], None
    for i, p in enumerate(ps):
        if start is None:
            start = p
        if i + 1 == len(ps) or ps[i + 1] != p + 1:
            runs.append(f"{start}" if start == p else f"{start}–{p}")
            start = None
    return "; ".join(runs)


class SourceRefs:
    """entry -> «КБРС-1989 с. 101, ТСКБЯ т. 1 с. 230, Гузеев-2013 с. 295, правка лингвиста»"""

    def __init__(self):
        self.d2 = {}
        for l in open(CK / "02_dict2_segmented.jsonl", encoding="utf-8"):
            r = json.loads(l)
            self.d2[r["id"]] = (r["vol"], r["page"])
        self.kbrs, self.kbrs_end = {}, {}
        f = S19 / "kbrs_pages.json"
        if f.exists():
            d = json.load(open(f, encoding="utf-8"))
            self.kbrs = {int(k): v for k, v in d["page_of"].items()}
            self.kbrs_end = {int(k): v for k, v in d.get("span_of", {}).items()}
        f17 = CK / "shards" / "s17" / "items.jsonl"
        if f17.exists():
            for r in load_jsonl(f17):
                self.kbrs[r["sid"]] = r["page"]

    def kbrs_pages(self, sid):
        p = self.kbrs[sid]
        return list(range(p, self.kbrs_end.get(sid, p) + 1))

    def of(self, e):
        out = []
        if e.get("dict_id") in ("1", "both"):
            pages = [p for s in e.get("src1") or [] if int(s) in self.kbrs for p in self.kbrs_pages(int(s))]
            out.append("КБРС-1989" + (f" с. {page_runs(pages)}" if pages else ""))
        if e.get("dict_id") in ("2", "both"):
            vols = defaultdict(list)
            for s in e.get("src2") or []:
                if s in self.d2:
                    v, p = self.d2[s]
                    vols[v].append(p)
            out += [f"ТСКБЯ т. {v} с. {page_runs(ps)}" for v, ps in sorted(vols.items())] or ["ТСКБЯ"]
        g = e.get("guzeev")
        if g:
            out.append(f"Гузеев-2013 с. {g['page']}" if g.get("page") else "Гузеев-2013")
        if "linguist_fix" in (e.get("flags") or []):
            out.append("правка лингвиста")
        return ", ".join(out)


def stats():
    es = load_jsonl(CK / "06_lextagged.jsonl")
    sr = SourceRefs()
    c, nopage = Counter(), Counter()
    for e in es:
        s = sr.of(e)
        for part in s.split(", "):
            code = part.split(" с. ")[0].split(" т. ")[0]
            c[code] += 1
            if " с. " not in part and code in ("КБРС-1989", "ТСКБЯ"):
                nopage[code] += 1
    print(json.dumps({"entries": len(es), "by_source": c, "without_page": nopage,
                      "example": [(e["word"], sr.of(e)) for e in es[1610:1616]]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["kbrs_crops", "kbrs_check", "kbrs_crops2", "kbrs_check2", "kbrs_align", "qmos_gaps",
                                      "gapprep", "gapcheck", "stats"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.phase == "kbrs_check":
        sys.exit(kbrs_check(*a.args))
    if a.phase == "kbrs_check2":
        sys.exit(kbrs_check2(*a.args))
    if a.phase == "gapcheck":
        sys.exit(gapcheck(*a.args))
    {"kbrs_crops": kbrs_crops, "kbrs_crops2": kbrs_crops2, "kbrs_align": kbrs_align, "qmos_gaps": qmos_gaps,
     "gapprep": gapprep, "stats": stats}[a.phase]()
