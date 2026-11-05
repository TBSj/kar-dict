# -*- coding: utf-8 -*-
"""S11a: restore the structural markers of ТСКБЯ (dict-2) inside misc2.

The S2 prompt mapped the OCR glyph «О» at a line start to ◊ («фразеологизм»), but in
ТСКБЯ the legend (т. 1, PDF-с. 30; т. 2–3, PDF-с. 10) says:
    ▭  знак, отделяющий цитаты от словосочетаний   (in the body printed as a hollow ❑)
    ○  знак, отделяющий цитаты от пословиц и поговорок
    ❑  знак, отделяющий сложные слова от простых
    ▼  знак, отделяющий фразеологизмы (иногда и сложные слова) — in the body a filled ■
So ≈2/3 of the corpus ◊ and most □/▯ open CITATION blocks.  Corpus convention after
this step (misc2 only):
    ◊  phraseology block   (printed ■/▼)        -> misc2_phras
    ▯  compound-word block (printed hollow ❑)   -> misc2_terms
    ▭  start of citations after word combinations
    ○  start of citations after a proverb «(Нарт сёз)»
Decision = content of the block (citation vs phrase) + the OCR glyph found at the same
place in the raw page text (checkpoints/02_dict2_segmented.jsonl).

  python s11_markers.py analyze   # -> shards/s11/markers.jsonl, mk_in/ (LLM), vis_in/ (page crops)
  python s11_markers.py apply     # uses markers.jsonl + mk_out/ + vis_out/ -> 06_lextagged.jsonl
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S11 = CK / "shards" / "s11"
F06 = CK / "06_lextagged.jsonl"

MARKS = "◊▯□■♦▲▼"
HOMO = str.maketrans("ABEKMHOPCTXYaeopcxykmt", "АВЕКМНОРСТХУаеорсхукмт")
# OCR renderings of the printed glyphs (checked on page images 2026-11-05)
HOLLOW = set("□ОO0QDUоo")              # ❑ / ○ (hollow square, circle) — vision-checked
NOGLYPH = set(".,)")
DIAMOND = set("♦❖◊ф+^4tfу$")            # т.2–3: OCR of the filled diamond ♦ (phraseology)
# other filled OCR (■ I l i Ш И Н Я В Б М digits …) = the filled square ■ (compound words in т.2–3)                    # text runs on after a citation: no printed glyph
# anything else the OCR left there (■ ♦ ▲ I Ш В А ф + ^ digits, stray letters) was a
# filled ■ in every vision-checked case; None/«:» (alignment failed / mixed) -> vision
SUB = ["misc2_citations", "misc2_citations_periodical", "misc2_citations_collection",
       "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref", "misc2_gram_note"]

RE_CIT = re.compile(
    r"(?:[А-ЯЁ][а-яёъ]+(?:ланы|лены)|[А-ЯЁ]\.(?:\s?[А-ЯЁ]\.)?)\s+[А-ЯЁ][а-яё]*\.?(?:-[А-ЯЁ][а-яё]*\.?)?,"
    r"\s+[^.,«»]{2,60},\s+(?:[IVX]+,\s+)?\d+[.;]"
    r"|«[^»]{2,60}»,\s*(?:\d{4},\s*)?№\s*\d+"
    r"|«[^»]{2,60}»,\s*(?:[IVX]+,\s*)?\d+[.;]")
RE_PROV_END = re.compile(r"\(\s*(?:Нарт\s+сёз|Фольк|Айтыу|айтыу)\s*\.?\s*\)\s*\.?\s*$")
LABEL = (r"(?:къарач\.|малкъ\.|балк\.|грамм?\.|сёл\.\s*тил\.|кёч\.|эск\.|ц\.\s*диал\.|диал\.|этн\.|эт\.|ат\.|сыф\.|"
         r"мат\.|физ\.|биол\.|бот\.|мед\.|хим\.|тех\.|муз\.|спорт\.|ист\.|лингв\.|юр\.|экон\.|полит\.|дин\.)")


def normalize(s):
    s2 = s.translate(HOMO)
    out, idx = [], []
    for i, ch in enumerate(s2):
        c = ch.lower()
        c = {"ё": "е", "ь": "ъ", "й": "и"}.get(c, c)
        if "а" <= c <= "я":
            out.append(c)
            idx.append(i)
    return "".join(out), idx


RE_PROV = re.compile(r"\(\s*(?:Нарт\s+сёз|Фольк|Айтыу|айтыу)")


def content_type(block):
    """-> (type, reason): type in phrase / citation / uncertain.
    Tuned on a vision-checked sample (2026-11-05): dialogue/quotes first, the «/» of a
    phrase sub-entry is spaced and comes before any sentence end, «:» only after 1–3 words."""
    b = block.strip()
    head = b[:170]
    if b[:1] in "[-–—«\"'„“”(":
        return "citation", "dialog"
    cit = RE_CIT.search(b)
    prov = RE_PROV.search(b)
    cpos = min(cit.start() if cit else 10 ** 6, prov.start() if prov else 10 ** 6)
    m = re.search(r"\s/\s?|/\s", head)
    if m and m.start() < cpos:
        pre = head[:m.start()]
        if (re.search(r"[а-яё]{3,}", pre) and len(pre.split()) <= 14
                and not re.search(r"[.!?»]\s+[А-ЯЁ]", pre) and not re.search(r"(?:^|\s)\d[.)]\s", pre)):
            return "phrase", "slash"
    m = re.search(r"(?:^|[\s(])къ\.\s", head[:110])
    if m and m.start() < cpos and not re.search(r"[.!?]\s", head[:m.start()]) and len(head[:m.start()].split()) <= 9:
        return "phrase", "ref"
    if re.match(r"^[А-ЯЁ][а-яёъ\-]+(?:\s[а-яёъ\-]+){0,3}\s" + LABEL, head):
        return "phrase", "label"
    if cit or prov:
        return "citation", "attrib"
    return "uncertain", ""


def _sim(a, b):
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def glyph_at(raw, nraw, ridx, after, rel):
    """Locate the text that follows the marker in the raw OCR text; return the glyph
    just before it.  A hit found with a short probe must be confirmed by similarity of
    the following 60 letters (S2 repaired OCR, so exact equality is not required)."""
    na, _ = normalize(after)
    for L in (24, 16, 10):
        if len(na) < L:
            continue
        probe = na[:L]
        hits = [m.start() for m in re.finditer(re.escape(probe), nraw)]
        if L < 24 or len(hits) > 1:
            hits = [h for h in hits if _sim(nraw[h:h + 60], na[:60]) >= 0.8]
        if hits:
            h = min(hits, key=lambda x: abs(x / max(1, len(nraw)) - rel))
            ri = ridx[h]
            j = ri - 1
            while j >= 0 and (raw[j] in " \t\n\r" or raw[j] in "-–—[«\"“”„("):
                j -= 1
            return (raw[j] if j >= 0 else ""), ri
    return None, None


def analyze():
    seg = {}
    for l in open(CK / "02_dict2_segmented.jsonl", encoding="utf-8"):
        d = json.loads(l)
        seg[d["id"]] = d
    es = [json.loads(l) for l in open(F06, encoding="utf-8")]
    S11.mkdir(parents=True, exist_ok=True)
    recs = []
    for e in es:
        m2 = e.get("misc2") or ""
        if not any(c in m2 for c in MARKS):
            continue
        srcs = [s for s in (e.get("src2") or []) if s in seg]
        raw = "\n".join(seg[s]["text"] for s in srcs)
        nraw, ridx = normalize(raw)
        pos = [i for i, ch in enumerate(m2) if ch in MARKS]
        for k, p in enumerate(pos):
            nxt = pos[k + 1] if k + 1 < len(pos) else len(m2)
            block = m2[p + 1:nxt]
            before = m2[max(0, p - 80):p]
            ctype, why = content_type(block)
            glyph, ri = glyph_at(raw, nraw, ridx, m2[p + 1:p + 200], p / max(1, len(m2))) if raw else (None, None)
            gcls = ("hollow" if glyph in HOLLOW else "none" if glyph in NOGLYPH
                    else "unknown" if glyph in (None, "", ":") else "filled")
            seg0 = seg[srcs[0]] if srcs else {}
            recs.append({"eid": e["entry_id"], "word": e["word"], "k": k, "pos": p, "mark": m2[p],
                         "glyph": glyph, "gcls": gcls, "ctype": ctype, "why": why,
                         "after_proverb": bool(RE_PROV_END.search(before)),
                         "vol": seg0.get("vol"), "page": seg0.get("page"),
                         "raw_snip": raw[ri:ri + 60] if ri is not None else "",
                         "before": before[-80:], "block": block[:400]})
    # decisions already collected (text agents: mk_out; vision: vis_out, ver_out)
    textdec, visdec = load_dec()
    pending_llm, pending_vis = [], []
    for r in recs:
        key = f"{r['eid']}@{r['pos']}"
        if key in textdec and textdec[key].get("type") in ("citation", "phrase"):
            r["ctype_final"], r["ctype_src"] = textdec[key]["type"], "llm"
        elif r["ctype"] != "uncertain":
            r["ctype_final"], r["ctype_src"] = r["ctype"], "rule"
        else:
            r["ctype_final"], r["ctype_src"] = None, "pending_llm"
            pending_llm.append(r)
        if r["ctype_final"] != "citation" and r["gcls"] == "unknown" and key not in visdec:
            pending_vis.append(r)
    with open(S11 / "markers.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # new batches only for pending ids not already queued (existing batches are never rewritten)
    for sub, rows, bs, fmt in (
            ("mk_in", pending_llm, 150, lambda r: {"id": f"{r['eid']}@{r['pos']}", "word": r["word"], "glyph": r["glyph"],
                                                   "before": r["before"], "block": r["block"]}),
            ("vis_in", pending_vis, 60, lambda r: {"id": f"{r['eid']}@{r['pos']}", "word": r["word"], "vol": r["vol"],
                                                   "page": r["page"], "raw_snip": r["raw_snip"] or r["block"][:80],
                                                   "block": r["block"][:160]})):
        d = S11 / sub
        d.mkdir(exist_ok=True)
        queued = {it["id"] for f in d.glob("batch_*.json") for it in json.load(open(f, encoding="utf-8"))}
        todo = [fmt(r) for r in rows if f"{r['eid']}@{r['pos']}" not in queued]
        n0 = len(list(d.glob("batch_*.json")))
        for i in range(0, len(todo), bs):
            json.dump(todo[i:i + bs], open(d / f"batch_{n0 + i // bs:02d}.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        print(sub, "new pending:", len(todo), "batches from", n0)
    print(json.dumps({"markers": len(recs), "ctype_src": Counter(r["ctype_src"] for r in recs),
                      "ctype_final": Counter(r["ctype_final"] for r in recs),
                      "gcls": Counter(r["gcls"] for r in recs)}, ensure_ascii=False, indent=1, default=dict))


def load_dec():
    textdec, visdec = {}, {}
    for f in sorted((S11 / "mk_out").glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            textdec[it["id"]] = it
    for sub in ("vis_out", "ver_out", "vis2_out"):
        for f in sorted((S11 / sub).glob("batch_*.json")):
            for it in json.load(open(f, encoding="utf-8"))["items"]:
                n = (it.get("note") or "") + " " + (it.get("shape") or "")
                if it.get("glyph") == "filled" and "shape" not in it:
                    it["shape"] = ("diamond" if re.search(r"♦|❖|ромб|diamond", n) else
                                   "triangle" if re.search(r"▲|▼|треуг|triangle", n) else
                                   "square" if re.search(r"■|квадрат|square", n) else None)
                visdec[it["id"]] = it
    return textdec, visdec


def decide(recs, visdec):
    """final marker per record, in entry order (zone state follows decisions):
    citation -> ▭ (○ after a proverb); phrase -> ◊ under a filled ■, ▯ under a hollow ❑;
    no printed glyph -> the zone of the previous phrase unit of the same entry."""
    out, unresolved = {}, []
    zone, cur = None, None
    for r in recs:
        if r["eid"] != cur:
            cur, zone = r["eid"], None
        key = f"{r['eid']}@{r['pos']}"
        ct = r.get("ctype_final")
        if ct not in ("citation", "phrase"):
            unresolved.append(key)
            continue
        if ct == "citation":
            out[key] = "○" if r["after_proverb"] else "▭"
            continue
        g, shape = r["gcls"], None
        vd = visdec.get(key)
        if vd and vd.get("glyph") in ("filled", "hollow", "circle", "none"):
            g = {"circle": "hollow"}.get(vd["glyph"], vd["glyph"])
            shape = vd.get("shape")
        if g == "filled":
            if r["vol"] == 1:
                new = "◊"                   # т.1: filled ▲/▼ = phraseology
            else:
                if shape is None:
                    shape = "diamond" if (r["glyph"] or "") in DIAMOND else "square"
                new = "◊" if shape == "diamond" else "▯"   # т.2–3: ♦ phraseology, ■ compound
        elif g == "hollow":
            new = "▯"
        elif zone:
            new = zone                      # continuation unit inside a ▼/❑ zone
        elif r["mark"] in "◊▯":
            new = r["mark"]                 # nothing better known: keep S2's choice
        else:
            new = "▯"
        zone = new
        out[key] = new
    return out, unresolved


def apply():
    recs = [json.loads(l) for l in open(S11 / "markers.jsonl", encoding="utf-8")]
    textdec, visdec = load_dec()
    for r in recs:   # text decisions that arrived after the last analyze
        key = f"{r['eid']}@{r['pos']}"
        if r.get("ctype_final") is None and textdec.get(key, {}).get("type") in ("citation", "phrase"):
            r["ctype_final"] = textdec[key]["type"]
    final, unresolved = decide(recs, visdec)
    es = [json.loads(l) for l in open(F06, encoding="utf-8")]
    byid = {e["entry_id"]: e for e in es}
    per = defaultdict(list)
    for r in recs:
        key = f"{r['eid']}@{r['pos']}"
        if key in final:
            per[r["eid"]].append((r["pos"], r["mark"], final[key]))
    changed = Counter()
    touched = 0
    for eid, lst in per.items():
        e = byid.get(eid)
        if e is None:
            continue
        m2 = list(e.get("misc2") or "")
        hit = False
        for pos, old, new in lst:
            assert m2[pos] == old, (eid, pos, old, m2[pos])
            if new != old:
                m2[pos] = new
                changed[f"{old}->{new}"] += 1
                hit = True
        if hit:
            e["misc2"] = "".join(m2)
            for k in SUB:
                e.pop(k, None)
            e.setdefault("flags", [])
            if "marker_fixed" not in e["flags"]:
                e["flags"].append("marker_fixed")
            touched += 1
    with open(F06, "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    json.dump({"entries_touched": touched, "changes": dict(changed), "unresolved": unresolved},
              open(CK / "qa" / "s11_markers_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"entries_touched": touched, "changes": changed, "final": Counter(final.values()),
                      "unresolved": len(unresolved)}, ensure_ascii=False, indent=1, default=dict))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["analyze", "apply"])
    a = ap.parse_args()
    {"analyze": analyze, "apply": apply}[a.phase]()
