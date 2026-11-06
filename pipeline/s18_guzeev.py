# -*- coding: utf-8 -*-
"""S18: Гузеев Ж. «Къарачай-малкъар тилни омонимлерини сёзлюгю» (2013; survey #21, Н2) — survey step 3.

The PDF is a digital layout (InDesign, Minion Pro), not a scan: the text layer is clean and the font
data carry the structure — bold 11 pt = nest header / headword / bold forms in examples / sense
numbers, superscript 6.4 pt = homonym number, italic = labels and source sigla.  Parsed without a
language model.

Phases:
  parse   PDF -> local/guzeev/nests.jsonl (the book's text: gitignored, copyright — survey В3 open)
          + checkpoints/shards/s18/parse_report.json (counts, anomalies, book errata applied)

Book errata (numbering slips, header misprints, wrong labels) are fixed by the explicit ERRATA table
and recorded in each nest's "errata" list — never silently.
"""
import json, re, sys, argparse
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S18 = CK / "shards" / "s18"
LOC = ROOT / "local" / "guzeev"
F06 = CK / "06_lextagged.jsonl"
PDF = r"D:/Къагъыт/Къарачай/Китаб/Сёзлюкле/Гузеев Жамал Словарь омонимов карачаево-балкарского языка.pdf"
FIRST, LAST = 8, 487                       # dictionary body, 1-based pages

SUPS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
SUPMAP = {c: str(i) for i, c in enumerate(SUPS)}
UP = "А-ЯЁЪЬ"
LOW = "а-яёъь"
# part of speech labels of the book (Къысхартыула, p. 488–489) -> common tag set
POS = {"ат": "N", "сыф": "A", "сёзл": "ADV", "заман. сёзл": "ADV", "хал. сёзл": "ADV", "мард. сёзл": "ADV",
       "орун. сёзл": "ADV", "эт": "V", "межд": "INTJ", "кес": "PART", "кючл. кес": "PART", "сор. кес": "PART",
       "угъайл. кес": "PART", "бай": "CONJ", "байл": "CONJ", "сонг": "POSTP", "алм": "PRON", "сан": "NUM",
       "эрикл": "ONOM", "къарам. с": "MOD", "пред": "PRED",
       # rare forms of the same labels: «этим» (Сау⁶), «сёз.» (Умутлу²), «эрик. с.» (Хыбырт¹), «зат.» (Кириш³),
       # «атны магъ.» (Бирер²: in the noun meaning)
       "этим": "V", "сёз": "ADV", "эрик": "ONOM", "зат": "N", "атны магъ": "N",
       "бетл. алм": "PRON", "кёрг. алм": "PRON"}
# labels sometimes set in roman, not italic, right after the headword (Гуппур¹ «сыф.», Къыр¹ «эт.» …)
ROMAN_LABEL = re.compile(r"^\s*((?:(?:" + "|".join(sorted((re.escape(k) for k in POS), key=len, reverse=True)) +
                         r"|къарач|малкъ|эск|ц\. диал|грам|этн)\.?\s+)+)(?=\S)")
POS_RE = re.compile(r"(?:^|\s)(" + "|".join(sorted((re.escape(k) for k in POS), key=len, reverse=True)) + r")\.?(?=\s|$|,)")
SAME_AS = re.compile(r"^\s*деген бла (?:бир|бирча|тенг) магъана")


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def save_jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ parse
def style(s):
    if s["size"] < 8:
        return "S"
    if s["size"] > 14:
        return "L"
    if "Bold" in s["font"]:
        return "B"
    if "It" in s["font"]:
        return "I"
    return "R"


def visual_lines(pg):
    """lines of a page in reading order; fitz line objects on one baseline are merged"""
    raw = []
    for b in pg.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            sp = [s for s in l["spans"] if s["text"]]
            if sp:
                raw.append([l["bbox"][0], l["bbox"][1], l["bbox"][3], sp])
    raw.sort(key=lambda r: (r[1], r[0]))
    out = []
    for x, y0, y1, sp in raw:
        # same visual line: vertical overlap of most of the height (superscripts sit a little higher)
        if out and y0 < out[-1]["y1"] - 4 and x > out[-1]["x"]:
            out[-1]["spans"] += sp
            out[-1]["y1"] = max(out[-1]["y1"], y1)
            continue
        out.append({"x": x, "y": y0, "y1": y1, "spans": sp})
    return out


def toks_of(spans):
    toks = []
    for s in spans:
        st, t = style(s), s["text"]
        if st == "S":
            t = t.strip()
            if not t:
                continue
        if toks and toks[-1][0] == st:
            toks[-1][1] += t
        else:
            toks.append([st, t])
    return toks


def join_line(toks, line_toks):
    """append the tokens of the next line: a soft hyphen at the end joins the word, else a space"""
    if toks and line_toks:
        last = toks[-1][1]
        if last.endswith("\u00ad"):
            toks[-1][1] = last[:-1]
        elif not last.endswith((" ", "-", "–")) and not line_toks[0][1].startswith(" "):
            toks[-1][1] = last + " "
    for st, t in line_toks:
        if toks and toks[-1][0] == st:
            toks[-1][1] += t
        else:
            toks.append([st, t])


def paragraphs(doc):
    """paragraph = a line indented against the page text margin + its continuation lines"""
    paras, cur, letter = [], None, None
    for pno in range(FIRST, LAST + 1):
        lines = visual_lines(doc[pno - 1])
        body = [l for l in lines if not (l["y"] > 640 and re.fullmatch(r"\s*\d+\s*", "".join(s["text"] for s in l["spans"])))]
        if not body:
            continue
        margin = min(l["x"] for l in body if style(l["spans"][0]) != "L")
        for l in body:
            lt = toks_of(l["spans"])
            if lt and lt[0][0] == "L":
                letter = lt[0][1].strip()
                cur = None
                continue
            start = margin + 8 < l["x"] < margin + 25
            if start or cur is None:
                cur = {"page": pno, "y": round(l["y"], 1), "letter": letter, "toks": [], "pages": [pno]}
                paras.append(cur)
            elif pno not in cur["pages"]:
                cur["pages"].append(pno)
            join_line(cur["toks"], [list(t) for t in lt])
    for p in paras:
        for t in p["toks"]:
            t[1] = t[1].replace("\u00ad", "")
    return paras


def plain(toks):
    out = []
    for st, t in toks:
        if st == "S":
            out.append("".join(SUPS[int(c)] if c.isdigit() else c for c in t))
        else:
            out.append(t)
    return re.sub(r"\s+", " ", "".join(out)).strip()


HEAD_RE = re.compile(r"^\s*([%s][%s\-]*(?:[ \-][%s][%s\-]*)*)\s*([%s]+|\d+)?\s*$" % (UP, UP, UP, UP, SUPS))


def article_head(toks):
    """(head, number, index of the first body token, how the number was written) or None"""
    if not toks or toks[0][0] != "B":
        return None
    t0 = toks[0][1]
    m = re.match(r"^\s*([%s][%s\-]*(?:[ \-][%s][%s\-]*)*)" % (UP, UP, UP, UP), t0)
    if not m or len(m.group(1).replace(" ", "").replace("-", "")) < 1:
        return None
    head = m.group(1)
    rest = t0[m.end():]
    # lower-case letters right after the capitals: a header like «Агъач», not an article
    if re.match(r"^[%s]" % LOW, rest):
        return None
    mm = re.match(r"^\s*([%s]+)" % SUPS, rest)
    if mm:
        n = int("".join(SUPMAP[c] for c in mm.group(1)))
        tail = rest[mm.end():]
        body = ([["B", tail]] if tail.strip() else []) + toks[1:]
        return head.strip(), n, body, "sup_char"
    md = re.match(r"^\s*(\d+)(?=\s|$)", rest)
    if md and len(head) > 1:
        tail = rest[md.end():]
        body = ([["B", tail]] if tail.strip() else []) + toks[1:]
        return head.strip(), int(md.group(1)), body, "digit"
    if not rest.strip() and len(toks) > 1 and toks[1][0] == "S" and toks[1][1].isdigit():
        return head.strip(), int(toks[1][1]), toks[2:], "sup_span"
    if not rest.strip() and len(toks) > 1 and toks[1][0] == "R":
        mr = re.match(r"^\s*([%s]+)" % SUPS, toks[1][1])          # САУЛАЙ ² (p. 316): the sign in a regular span
        if mr:
            n = int("".join(SUPMAP[c] for c in mr.group(1)))
            return head.strip(), n, [["R", toks[1][1][mr.end():]]] + toks[2:], "sup_regular"
    return None


def is_header(toks):
    """nest header: one bold word in title case (or capitals without a number: КИЧИ, p. 187)"""
    txt = plain(toks)
    if not toks or any(st not in ("B",) for st, t in toks if t.strip()):
        return None
    if re.fullmatch(r"[%s][%s\-]*(?: [%s\-]+)*" % (UP, LOW, LOW), txt):
        return txt
    if re.fullmatch(r"[%s][%s\-]+" % (UP, UP), txt):
        return txt
    return None


def split_senses(body):
    """body tokens -> leading labels + senses split on bold «N.»"""
    senses, cur = [], {"num": None, "toks": []}
    for st, t in body:
        if st == "B":
            parts = re.split(r"(?<![^\s])(\d{1,2})\.(?=\s|$)", t)
            if len(parts) > 1:
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        senses.append(cur)
                        cur = {"num": int(part), "toks": []}
                    elif part:
                        cur["toks"].append(["B", part])
                continue
        cur["toks"].append([st, t])
    senses.append(cur)
    lead = senses[0]
    rest = [s for s in senses[1:]]
    if rest and not plain(lead["toks"]).strip(" .,;"):
        head_labels = lead["toks"]
        return labels_of(head_labels)[0], rest
    if rest:
        # text before «1.»: labels and maybe a common part
        labs, left = labels_of(lead["toks"])
        if plain(left).strip(" .,;"):
            lead["toks"] = left
            return labs, [dict(lead, num=0)] + rest
        return labs, rest
    labs, left = labels_of(lead["toks"])
    return labs, [{"num": None, "toks": left}]


def roman_labels(body):
    """no italic label but the body starts with a known label in roman: take it as the label"""
    if body and body[0][0] == "R":
        m = ROMAN_LABEL.match(body[0][1])
        if m:
            return [m.group(1).strip()], [["R", body[0][1][m.end():]]] + body[1:]
    return [], body


def labels_of(toks):
    """leading italic tokens (and the bare punctuation between them) = labels"""
    labs, i = [], 0
    while i < len(toks):
        st, t = toks[i]
        if st == "I":
            labs.append(t.strip())
            i += 1
        elif st in ("R", "B") and not t.strip(" .,;"):
            i += 1
        elif st == "R" and labs and re.match(r"^[.,;]\s", t):
            toks = toks[:i] + [["R", t[1:]]] + toks[i + 1:]   # «къауум» + «. Адамны…»: the label's own dot
            labs[-1] += t[0]
            i += 1 if not t[1:].strip() else 0
            if t[1:].strip():
                break
        else:
            break
    return [x for x in " ".join(labs).replace(",", " ").split("  ") if x.strip()], toks[i:]


def sense_record(s):
    labs, toks = labels_of(s["toks"])
    text = plain(toks)
    refs = []
    for i, (st, t) in enumerate(toks):
        if st == "B" and i + 1 < len(toks):
            j = i + 1
            num = None
            if toks[j][0] == "S":
                num = int(toks[j][1]) if toks[j][1].isdigit() else None
                j += 1
            w = t.strip()
            mnum = re.search(r"([%s]+)$" % SUPS, w)
            if mnum:
                num = int("".join(SUPMAP[c] for c in mnum.group(1)))
                w = w[:mnum.start()]
            if j < len(toks) and toks[j][0] == "R" and SAME_AS.match(toks[j][1]):
                refs.append([w.lower(), num])
    # definition: text before the first example sentence (a bold form or «*»), cut at a sentence end
    d, acc = "", ""
    for i, (st, t) in enumerate(toks):
        if st == "B" and not any(r[0] == t.strip().lower().rstrip(SUPS) for r in refs):
            m = list(re.finditer(r"[.!?…](?=\s)", acc))
            if m:
                d = acc[:m[-1].end()]
                break
            if "*" in t:
                d = acc
                break
        acc += t if st != "S" else ""
    else:
        d = acc
    d = re.sub(r"\s+", " ", d).strip()
    return {"num": s["num"], "labels": labs, "def": d, "text": text, "refs": refs}


def parse():
    import fitz
    doc = fitz.open(PDF)
    paras = paragraphs(doc)
    nests, cur, orphans, anomalies = [], None, [], []
    for p in paras:
        h = is_header(p["toks"])
        a = article_head(p["toks"])
        if a:
            head, n, body, how = a
            labs, senses = split_senses(body)
            roman = False
            if not labs:
                rl, body2 = roman_labels(body)
                if rl:
                    labs, senses = split_senses(body2)
                    labs, roman = rl + labs, True
            hom = {"n": n, "head": head, "page": p["page"], "y": p["y"], "pages": p["pages"], "num_how": how,
                   "labels": labs, "senses": [sense_record(s) for s in senses],
                   "raw": plain(p["toks"])}
            if roman:
                hom["label_in_roman"] = True
            if cur is None:
                # articles right after the letter heading «А» (p. 8): the nest header is the heading itself
                cur = {"header": head.capitalize(), "page": p["page"], "letter": p["letter"], "homs": [],
                       "no_header": True}
                nests.append(cur)
                anomalies.append({"kind": "no_header", "page": p["page"], "header": cur["header"]})
            cur["homs"].append(hom)
        elif h:
            if cur is not None and cur["header"].lower() == h.lower() and not cur["homs"]:
                continue
            if cur is not None and cur["header"].lower() == h.lower():
                anomalies.append({"kind": "repeated_header", "page": p["page"], "header": h})
                cur["repeated_header"] = True
                continue
            cur = {"header": h, "page": p["page"], "letter": p["letter"], "homs": []}
            nests.append(cur)
        elif not plain(p["toks"]):
            continue
        else:
            if cur is not None and cur["homs"]:
                # a paragraph that is neither: continuation (poem lines, page breaks) of the last article
                last = cur["homs"][-1]
                last.setdefault("extra", []).append(plain(p["toks"]))
                anomalies.append({"kind": "loose_paragraph", "page": p["page"], "after": f"{last['head']}{last['n']}",
                                  "text": plain(p["toks"])[:80]})
            else:
                anomalies.append({"kind": "stray", "page": p["page"], "text": plain(p["toks"])[:80]})
    return nests, orphans, anomalies


def fold_head(s):
    return s.lower().replace("ё", "е").replace(" ", "").replace("-", "")


def report(nests, orphans, anomalies):
    for n in nests:
        nums = [h["n"] for h in n["homs"]]
        if nums != list(range(1, len(nums) + 1)):
            anomalies.append({"kind": "numbering", "page": n["page"], "header": n["header"], "nums": nums})
        heads = {fold_head(h["head"]) for h in n["homs"]}
        if heads != {fold_head(n["header"])}:
            anomalies.append({"kind": "header_vs_head", "page": n["page"], "header": n["header"],
                              "heads": sorted({h["head"] for h in n["homs"]})})
        if len(n["homs"]) < 2:
            anomalies.append({"kind": "single", "page": n["page"], "header": n["header"], "n": len(n["homs"])})
    return anomalies


# book errata (survey 21_deepdive §3; each confirmed on the parsed text): applied by an explicit list and
# recorded in the nest's "errata" — the linguist decides (survey В14) whether they stay silent
ERRATA = {
    # (header, page): {"nums": corrected numbers | "heads": corrected article headwords | "header": ... | "pos": {n: label}}
    ("Акъ", 19): {"nums": [1, 2, 3, 4], "why": "нумерация в книге 1, 1, 2, 3 (глагол АКЪ¹ на с. 19 и АКЪ¹⁻³ на с. 20)"},
    ("Ахыр", 47): {"nums": [1, 2], "why": "нумерация в книге 1, 1 и повторённый заголовок"},
    ("Тогъай", 387): {"nums": [1, 2, 3], "why": "нумерация в книге начинается с ²"},
    ("Чакъ", 452): {"nums": [1, 2, 3], "why": "нумерация в книге 1, 1, 2"},
    ("Чюй", 467): {"nums": [1, 2], "why": "нумерация в книге начинается с 4"},
    ("Буукъсуз", 84): {"header": "Бузукъсуз", "why": "опечатка в заголовке гнезда (статья БУЗУКЪСУЗ)"},
    ("Жарсыулу", 128): {"heads": "ЖАРСЫУЛУ", "why": "опечатка ЖАРСЫЛУ в статье"},
    ("Кемисз", 171): {"header": "Кемсиз", "why": "опечатка в заголовке гнезда (статья КЕМСИЗ)"},
    ("Къокъуусуз", 234): {"header": "Къоркъуусуз", "why": "опечатка в заголовке гнезда (статья КЪОРКЪУУСУЗ)"},
    ("Тутхучуз", 404): {"header": "Тутхучсуз", "why": "опечатка в заголовке гнезда (статья ТУТХУЧСУЗ)"},
    ("Факъыр", 435): {"heads": "ФАКЪЫР", "why": "опечатка ФАКЫР в статье"},
    ("Чексиз", 458): {"heads": "ЧЕКСИЗ", "why": "опечатка ЧЕКЧИЗ в статье"},
    ("Тёзюмсюз", 378): {"pos": {2: "сёзл."}, "why": "ТЁЗЮМСЮЗ² помечен «сыф.», по толкованию — наречие (сёзл.)"},
    ("Тышында", 414): {"pos": {1: "сёзл."}, "why": "ТЫШЫНДА¹ помечен «сан.», по толкованию — наречие (сёзл.)"},
}
NOTES = {  # anomalies kept as printed
    ("Хапарчы", 441): "в гнезде один омоним",
    ("Хубудий", 444): "в гнезде один омоним",
    ("КИЧИ", 187): "заголовок гнезда набран прописными",
    ("Саулукъ", 316): "заголовок гнезда повторён",
    ("А", 8): "заголовок гнезда совпал с буквой раздела",
}
NOTPOS = re.compile(r"кёпл\. сан\.?")          # «кёпл. сан» = plural, not «сан.» (numeral)


def pos_of(labels):
    """POS tag from the homonym-level labels (the book labels POS only where homonyms differ in it)"""
    L = NOTPOS.sub(" ", " " + " ".join(labels) + " ")
    found = POS_RE.findall(L)
    return [POS[f] for f in found]


def finalize(nests):
    out, used = [], set()
    for i, n in enumerate(nests, 1):
        key = (n["header"], n["page"])
        er = ERRATA.get(key)
        rec = {"nid": f"g{i:04d}", "header": n["header"], "page": n["page"], "letter": n.get("letter"),
               "errata": [], "notes": []}
        if key in NOTES:
            rec["notes"].append(NOTES[key])
        homs = n["homs"]
        if er:
            used.add(key)
            rec["errata"].append(er["why"])
            if "nums" in er:
                assert len(er["nums"]) == len(homs), key
                for h, k in zip(homs, er["nums"]):
                    h["n_printed"], h["n"] = h["n"], k
            if "header" in er:
                rec["header_printed"], rec["header"] = n["header"], er["header"]
            if "heads" in er:
                for h in homs:
                    if h["head"] != er["heads"]:
                        h["head_printed"], h["head"] = h["head"], er["heads"]
            if "pos" in er:
                for h in homs:
                    if h["n"] in er["pos"]:
                        h["labels_printed"] = list(h["labels"])
                        h["labels"] = [er["pos"][h["n"]]] + [x for x in h["labels"] if not POS_RE.search(" " + x + " ")]
        for h in homs:
            h["pos"] = pos_of(h["labels"])
            # sense-level POS (rare: «1. сыф.»); a homonym without its own label takes its senses' labels (Тап⁵)
            for s in h["senses"]:
                s["pos"] = pos_of(s["labels"])
            ss = h["senses"]
            if len(ss) > 1 and ss[0]["num"] == 0 and ss[1]["num"] == 2:
                ss[0]["num"] = 1                      # «1.» not printed (ОРТА¹ …: 52 homonyms)
                h["sense1_unnumbered"] = True
            if not h["pos"]:
                sp = [p for s in h["senses"] for p in s["pos"]]
                if sp and all(s["pos"] for s in h["senses"]):
                    h["pos"] = list(dict.fromkeys(sp))
                    h["pos_from_senses"] = True
        rec["homs"] = homs
        rec["kind"] = ("lexical" if not any(h["pos"] for h in homs) else
                       "partial" if not all(h["pos"] for h in homs) else
                       "grammatical" if len({tuple(h["pos"]) for h in homs}) > 1 else "same_pos_labelled")
        out.append(rec)
    missing = set(ERRATA) - used
    assert not missing, missing
    return out


def main_parse():
    nests, orphans, anomalies = parse()
    anomalies = report(nests, orphans, anomalies)
    final = finalize(nests)
    homs = sum(len(n["homs"]) for n in final)
    LOC.mkdir(parents=True, exist_ok=True)
    save_jsonl(LOC / "nests.jsonl", final)
    rep = {"pdf": PDF, "pages": [FIRST, LAST], "nests": len(final), "homonyms": homs,
           "nest_size": dict(sorted(Counter(len(n["homs"]) for n in final).items())),
           "kind": dict(Counter(n["kind"] for n in final)),
           "number_written_as": dict(Counter(h["num_how"] for n in final for h in n["homs"])),
           "pos_tags": dict(Counter(p for n in final for h in n["homs"] for p in (h["pos"] or ["—"]))),
           "anomalies": [{k: v for k, v in a.items() if k != "text"} for a in anomalies],
           "errata": [{"nid": n["nid"], "header": n["header"], "page": n["page"], "why": n["errata"]} for n in final if n["errata"]],
           "notes": [{"nid": n["nid"], "header": n["header"], "page": n["page"], "note": n["notes"]} for n in final if n["notes"]]}
    S18.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(S18 / "parse_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rep[k] for k in ("nests", "homonyms", "nest_size", "kind", "number_written_as", "pos_tags")},
                     ensure_ascii=False))
    print("errata", len(rep["errata"]), "anomalies", Counter(a["kind"] for a in anomalies))


# ------------------------------------------------------------------ align
CPOS = [("сущ", "N"), ("прил", "A"), ("нареч", "ADV"), ("глаг", "V"), ("межд", "INTJ"), ("частица", "PART"),
        ("союз", "CONJ"), ("послелог", "POSTP"), ("мест", "PRON"), ("числ", "NUM"), ("подражат", "ONOM"),
        ("модальн", "MOD"), ("предикатив", "PRED")]
TPOS = [(r"сёзл", "ADV"), (r"(^|\s)ат\.?(\s|$)", "N"), (r"(^|\s)сыф\.", "A"), (r"(^|\s)эт\.", "V"), (r"межд", "INTJ"),
        (r"(^|\s)кес\.", "PART"), (r"байл", "CONJ"), (r"сонг", "POSTP"), (r"алм", "PRON"), (r"(^|\s)сан\.", "NUM"),
        (r"эрикл", "ONOM"), (r"къарам", "MOD")]


def our_pos(e):
    for p in e.get("pos") or []:
        for pre, v in CPOS:
            if p.startswith(pre):
                return v
    first = (e.get("tags") or "").split(";")[0]
    for pat, v in TPOS:
        if re.search(pat, first):
            return v
    return "?"


def base_of(w):
    return re.sub(r"\d+$", "", w)


def num_of(w):
    m = re.search(r"(\d+)$", w)
    return int(m.group(1)) if m else 0


def kj(s):
    return s.replace("кь", "къ").replace("гь", "гъ")


def tkey(s):
    """ТСКБЯ / Гузеев spelling key: lower case, кь/гь -> къ/гъ, corpus j -> ж, b -> п, no digits"""
    s = kj(re.sub(r"[\d¹²³⁴⁵⁶⁷⁸⁹⁰]+$", "", s.strip().lower()))
    return s.replace("j", "ж").replace("b", "п").replace("ў", "у")


def key_e(s):
    return tkey(s).replace("ё", "е")


def key_fold(s):
    return key_e(s).replace("дж", "ж").replace("б", "п").replace(" ", "").replace("-", "")


def corpus_side(es):
    by_base = defaultdict(list)
    for e in es:
        by_base[base_of(e["word"])].append(e)
    idx = [defaultdict(set), defaultdict(set), defaultdict(set)]
    for b, ents in by_base.items():
        cands = {b} | {e["word2_orig"] for e in ents if e.get("word2_orig")}
        for c in cands:
            for lvl, f in enumerate((tkey, key_e, key_fold)):
                idx[lvl][f(c)].add(b)
    return by_base, idx


def gkeys(n):
    ks = [n["header"]] + [h["head"] for h in n["homs"]]
    return list(dict.fromkeys(ks))


def classify(G, O):
    O2 = [e for e in O if e.get("dict_id") in ("both", "2")]
    O1 = [e for e in O if e.get("dict_id") == "1"]
    gp = [(h["pos"][0] if h["pos"] else "?") for h in G]
    op = [our_pos(e) for e in O2]
    lexical = all(x == "?" for x in gp)
    if not O:
        return "absent", ""
    if not O2:
        return "d1_only", ""
    if len(O2) == len(G):
        if lexical:
            return "equal", ("lexical" if len(set(op) - {"?"}) <= 1 else "lexical_ours_mixed_pos")
        if gp == op:
            return "equal", "same_pos_same_order"
        if sorted(gp) == sorted(op):
            return "equal", "order_differs"
        if "?" in gp or "?" in op:
            return "equal", "pos_unknown"
        return "equal", "pos_differ"
    if len(O2) < len(G):
        if lexical:
            return "fewer", "lexical"
        miss = Counter(gp) - Counter(op)
        miss.pop("?", None)
        return "fewer", ("missing:" + "+".join(sorted(miss.elements())) if miss else "same_pos_split")
    return "more", ("extra_tskbya" if not lexical else "extra_tskbya_lexical")


def align():
    nests = load_jsonl(LOC / "nests.jsonl")
    es = load_jsonl(F06)
    by_base, idx = corpus_side(es)
    rows, used_bases = [], set()
    for n in nests:
        bases, level = set(), None
        for lvl, f in enumerate((tkey, key_e, key_fold)):
            for k in gkeys(n):
                bases |= idx[lvl].get(f(k), set())
            if bases:
                level = ("exact", "yo_e", "fold")[lvl]
                break
        O = sorted((e for b in bases for e in by_base[b]), key=lambda e: (base_of(e["word"]), num_of(e["word"])))
        used_bases |= bases
        cls, sub = classify(n["homs"], O)
        rows.append({
            "nid": n["nid"], "header": n["header"], "page": n["page"], "match": level, "bases": sorted(bases),
            "cls": cls, "sub": sub, "kind": n["kind"],
            "g": [{"n": h["n"], "pos": h["pos"], "labels": h["labels"]} for h in n["homs"]],
            "ours": [{"entry_id": e["entry_id"], "word": e["word"], "dict_id": e["dict_id"], "pos": our_pos(e),
                      "hom_rank": e.get("hom_rank")} for e in O],
            "n_g": len(n["homs"]), "n_ours": len(O),
            "n_tskbya": sum(1 for e in O if e.get("dict_id") in ("both", "2")),
            "n_d1only": sum(1 for e in O if e.get("dict_id") == "1"),
            "errata": n["errata"]})
    save_jsonl(S18 / "align.jsonl", rows)
    # corpus nests outside the book
    numbered = {b: v for b, v in by_base.items() if len(v) > 1}
    outside = {b: v for b, v in numbered.items() if b not in used_bases}
    vn = [b for b in outside if re.search(r"(ыу|иу|уу|юу)$", b)]
    stat = Counter(r["cls"] for r in rows)
    sub = Counter(f"{r['cls']}:{r['sub']}" for r in rows)
    summary = {"nests": len(rows), "classes": dict(stat), "subclasses": dict(sorted(sub.items(), key=lambda x: -x[1])),
               "match_level": dict(Counter(r["match"] for r in rows)),
               "with_d1only_entries": sum(1 for r in rows if r["n_d1only"]),
               "corpus_nests_2plus": len(numbered), "covered": len(numbered) - len(outside),
               "outside_book": len(outside), "outside_verbal_nouns": len(vn)}
    json.dump(summary, open(S18 / "align_summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ map: semantic alignment by agents
MAP_IN = LOC / "map_in"                     # batches carry the book's text -> local/ (gitignored)
MAP_OUT = S18 / "map_out"


def cut(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


def kb_senses(misc2, n=8, w=170):
    """ТСКБЯ original KB text (misc2): one short piece per numbered sense"""
    m = misc2 or ""
    # sense numbers run 1, 2, 3 …; other «N.» are page numbers of citations («…, Октябрни саугъасы, 21.»)
    cuts, want = [], None
    for mt in re.finditer(r"(?:^|(?<=\s))(\d{1,2})\.(?=\s)", m):
        k = int(mt.group(1))
        if (want is None and k in (1, 2)) or k == want:
            cuts.append((mt.start(1), k))
            want = k + 1
    if not cuts:
        return [cut(m, 2 * w)] if m else []
    out = []
    if m[:cuts[0][0]].strip():
        out.append(cut(m[:cuts[0][0]], w))
    for i, (pos, k) in enumerate(cuts):
        end = cuts[i + 1][0] if i + 1 < len(cuts) else len(m)
        out.append(cut(m[pos:end], w))
    return out[:n]


def g_record(h):
    senses = []
    for sn in h["senses"]:
        ex = sn["text"][len(sn["def"]):] if sn["text"].startswith(sn["def"][:20]) else ""
        senses.append({"num": sn["num"], "labels": " ".join(sn["labels"]), "def": cut(sn["def"] or sn["text"], 260),
                       "ex": cut(ex, 110)})
    refs = [f"{w}{n or ''}" for sn in h["senses"] for w, n in sn["refs"]]
    return {"n": h["n"], "labels": " ".join(h["labels"]), "senses": senses, **({"same_as": refs} if refs else {})}


def o_record(e):
    r = {"entry_id": e["entry_id"], "word": e["word"], "dict": e["dict_id"], "pos": " ".join(e.get("pos") or []),
         "tags": e.get("tags") or "", "def1_KBRS": cut(e.get("def1"), 420), "def2_TSKBYa": cut(e.get("def2"), 420),
         "TSKBYa_KB": kb_senses(e.get("misc2"))}
    fl = [f for f in e.get("flags") or [] if f in ("split_unclear", "merged_continuation", "hyphen_restored",
                                                   "no_d1_pair", "no_d2_pair", "split_def1")]
    if fl:
        r["flags"] = fl
    if not r["def1_KBRS"] and e.get("misc1"):
        r["misc1"] = cut(e["misc1"], 200)
    return r


def auto_ok(r):
    gp = [(g["pos"][0] if g["pos"] else "?") for g in r["g"]]
    return (r["cls"] == "equal" and r["sub"] == "same_pos_same_order" and len(set(gp)) == len(gp)
            and not r["n_d1only"])


SUPN = {1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹"}


def batch_text(name, items):
    """the agents' view of a batch: short lines, one block per nest"""
    L = [f"BATCH {name}: {len(items)} nests. Гузеев = the homonym dictionary (KB text); OURS = corpus entries."]
    for it in items:
        L += ["", f"=== {it['nid']}  {it['header']}  (Гузеев p. {it['page']})   [auto class: {it['auto_class']}]",
              "GUZEEV:"]
        for g in it["guzeev"]:
            L.append(f"  {it['header'].upper()}{SUPN.get(g['n'], g['n'])}  (n={g['n']})  labels: {g['labels'] or '—'}"
                     + (f"   same as: {', '.join(g['same_as'])}" if g.get("same_as") else ""))
            for sn in g["senses"]:
                num = f"{sn['num']}." if sn["num"] else "-"
                lab = f"[{sn['labels']}] " if sn["labels"] else ""
                L.append(f"     {num} {lab}{sn['def']}" + (f"  || ex: {sn['ex']}" if sn["ex"] else ""))
        L.append("OURS:")
        for o in it["ours"]:
            L.append(f"  {o['entry_id']}  {o['word']}   dict={o['dict']}  pos={o['pos'] or '—'}  tags={o['tags'] or '—'}"
                     + (f"  flags={','.join(o['flags'])}" if o.get("flags") else ""))
            if o["def1_KBRS"]:
                L.append(f"     def1 (КБРС, Russian): {o['def1_KBRS']}")
            if o.get("misc1"):
                L.append(f"     КБРС examples: {o['misc1']}")
            if o["def2_TSKBYa"]:
                L.append(f"     def2 (ТСКБЯ, Russian): {o['def2_TSKBYa']}")
            for k in o["TSKBYa_KB"]:
                L.append(f"     ТСКБЯ KB: {k}")
    return "\n".join(L) + "\n"


def mapcheck(batch, who, out_name=None):
    """validate a mapper's file against its batch: every nest, every corpus entry once, valid numbers"""
    b = json.load(open(MAP_IN / f"{batch}.json", encoding="utf-8"))
    f = MAP_OUT / f"{out_name or batch + '_' + who}.json"
    try:
        out = json.load(open(f, encoding="utf-8"))
    except Exception as ex:
        print(f"INVALID JSON {f}: {ex}")
        return 1
    got = {n.get("nid"): n for n in out.get("nests", [])}
    errs = []
    for it in b["nests"]:
        r = got.get(it["nid"])
        if not r:
            errs.append(f"{it['nid']}: missing")
            continue
        gn = {g["n"] for g in it["guzeev"]}
        ids = [e.get("entry_id") for e in r.get("entries", [])]
        want = [o["entry_id"] for o in it["ours"]]
        if sorted(ids) != sorted(want):
            errs.append(f"{it['nid']}: entries {sorted(set(want) - set(ids))} missing, {sorted(set(ids) - set(want))} unknown"
                        + (" (duplicates)" if len(ids) != len(set(ids)) else ""))
        for e in r.get("entries", []):
            bad = [x for x in e.get("g", []) if x not in gn]
            if bad:
                errs.append(f"{it['nid']}: {e.get('entry_id')} g={bad} not in Гузеев numbers {sorted(gn)}")
            if e.get("role") not in ROLES:
                errs.append(f"{it['nid']}: {e.get('entry_id')} role {e.get('role')!r}")
            if e.get("role") == "covers_several" and len(e.get("g", [])) < 2:
                errs.append(f"{it['nid']}: {e.get('entry_id')} covers_several needs >= 2 g")
            if e.get("role") in ("not_in_guzeev", "fragment", "other_word") and e.get("g"):
                errs.append(f"{it['nid']}: {e.get('entry_id')} role {e['role']} must have g=[]")
        for x in r.get("g_missing", []):
            if x not in gn:
                errs.append(f"{it['nid']}: g_missing {x} not a Гузеев number")
        covered = {x for e in r.get("entries", []) for x in e.get("g", [])} | set(r.get("g_missing", []))
        if covered != gn:
            errs.append(f"{it['nid']}: Гузеев homonyms {sorted(gn - covered)} neither mapped nor in g_missing")
        if r.get("confidence") not in ("high", "medium", "low"):
            errs.append(f"{it['nid']}: confidence")
    extra = set(got) - {it["nid"] for it in b["nests"]}
    if extra:
        errs.append(f"unknown nids {sorted(extra)}")
    print("OK" if not errs else "ERRORS:\n" + "\n".join(errs))
    return 0 if not errs else 1


ROLES = ("same", "covers_several", "part_of", "not_in_guzeev", "fragment", "other_word")


def mapprep(bs=30):
    nests = {n["nid"]: n for n in load_jsonl(LOC / "nests.jsonl")}
    es = {e["entry_id"]: e for e in load_jsonl(F06)}
    rows = load_jsonl(S18 / "align.jsonl")
    todo = [r for r in rows if not auto_ok(r)]
    MAP_IN.mkdir(parents=True, exist_ok=True)
    for f in MAP_IN.glob("b*.json"):
        f.unlink()
    batches = [todo[i:i + bs] for i in range(0, len(todo), bs)]
    sizes = []
    for bi, b in enumerate(batches, 1):
        items = []
        for r in b:
            n = nests[r["nid"]]
            items.append({"nid": r["nid"], "header": n["header"], "page": n["page"],
                          "guzeev": [g_record(h) for h in n["homs"]],
                          "ours": [o_record(es[o["entry_id"]]) for o in r["ours"]],
                          "auto_class": f"{r['cls']}:{r['sub']}"})
        txt = json.dumps({"batch": f"b{bi:02d}", "nests": items}, ensure_ascii=False, indent=1)
        (MAP_IN / f"b{bi:02d}.json").write_text(txt, encoding="utf-8")
        view = batch_text(f"b{bi:02d}", items)
        (MAP_IN / f"b{bi:02d}.txt").write_text(view, encoding="utf-8")
        sizes.append(len(view))
    print(json.dumps({"auto_accepted": len(rows) - len(todo), "to_map": len(todo), "batches": len(batches),
                      "chars_min_max_avg": [min(sizes), max(sizes), sum(sizes) // len(sizes)]}))


def load_map(name):
    f = MAP_OUT / f"{name}.json"
    if not f.exists():
        return None
    try:
        return {n["nid"]: n for n in json.load(open(f, encoding="utf-8"))["nests"]}
    except Exception:
        return None


def sig(n):
    """what two readers must agree on: the Гузеев numbers of every entry (and, for entries without one,
    whether it is a real extra homonym or a fragment) + the Гузеев homonyms missing from the corpus"""
    ent = []
    for e in n.get("entries", []):
        g = tuple(sorted(e.get("g") or []))
        ent.append((e["entry_id"], g, "" if g else ("fragment" if e.get("role") == "fragment" else "extra")))
    return tuple(sorted(ent)), tuple(sorted(n.get("g_missing") or []))


def mapcompare():
    rows = []
    for bf in sorted(MAP_IN.glob("b*.json")):
        batch = bf.stem
        b = json.load(open(bf, encoding="utf-8"))
        A, B = load_map(f"{batch}_A"), load_map(f"{batch}_B")
        for it in b["nests"]:
            a = (A or {}).get(it["nid"])
            bb = (B or {}).get(it["nid"])
            st = ("agree" if a and bb and sig(a) == sig(bb) else "disagree" if a and bb else
                  "missing_A" if bb else "missing_B" if a else "missing_both")
            rows.append({"nid": it["nid"], "batch": batch, "auto_class": it["auto_class"], "status": st, "A": a, "B": bb})
    save_jsonl(S18 / "map_cmp.jsonl", rows)
    by = defaultdict(Counter)
    for r in rows:
        by[r["auto_class"].split(":")[0]][r["status"]] += 1
    print(json.dumps({"status": dict(Counter(r["status"] for r in rows)), "by_class": by}, ensure_ascii=False))


def map_text(who, n):
    if not n:
        return f"  reader {who}: —"
    L = [f"  reader {who}:  g_missing={n.get('g_missing') or []}  confidence={n.get('confidence')}"]
    for e in n.get("entries", []):
        sp = "; ".join(f"{k}: {e[k]}" for k in ("def2_split", "def1_split") if e.get(k))
        L.append(f"     {e['entry_id']} -> g={e.get('g')} {e.get('role')}" + (f"  [{sp}]" if sp else ""))
    L.append(f"     note: {n.get('note_ru', '')}" + (f"   parse_issue: {n['parse_issue']}" if n.get("parse_issue") else ""))
    return "\n".join(L)


ADJ_IN = LOC / "adj_in"


def adjprep(bs=20):
    rows = [r for r in load_jsonl(S18 / "map_cmp.jsonl") if r["status"] != "agree"]
    blocks = {}
    for f in sorted(MAP_IN.glob("b*.txt")):
        txt = f.read_text(encoding="utf-8")
        for part in re.split(r"\n(?==== g\d{4})", txt)[1:]:
            blocks[part[4:9]] = part.rstrip()
    ADJ_IN.mkdir(parents=True, exist_ok=True)
    for f in ADJ_IN.glob("a*.*"):
        f.unlink()
    groups = [rows[i:i + bs] for i in range(0, len(rows), bs)]
    for gi, g in enumerate(groups, 1):
        name = f"a{gi:02d}"
        L = [f"ADJUDICATION {name}: {len(g)} nests on which two independent readers disagree."]
        for r in g:
            L += ["", blocks[r["nid"]], "READINGS:", map_text("A", r["A"]), map_text("B", r["B"])]
        (ADJ_IN / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump({"nids": [r["nid"] for r in g], "batches": {r["nid"]: r["batch"] for r in g}},
                  open(ADJ_IN / f"{name}.json", "w", encoding="utf-8"))
    print(json.dumps({"to_adjudicate": len(rows), "groups": len(groups)}))


def outcome(n):
    """short label of a mapping: identity / split / extra / reorder / g_missing / part_of / fragment / other_word"""
    ents = n.get("entries", [])
    roles = Counter(e.get("role") for e in ents)
    tags = [t for r, t in (("covers_several", "split"), ("part_of", "part_of"), ("not_in_guzeev", "extra"),
                           ("fragment", "fragment"), ("other_word", "other_word")) if roles[r]]
    if n.get("g_missing"):
        tags.append("g_missing")
    seq = [e["g"][0] for e in ents if len(e.get("g") or []) == 1 and e.get("role") == "same"]
    if seq != sorted(seq):
        tags.append("reorder")
    return "+".join(tags) or "identity"


AUDIT_PLAN = {"split": 20, "reorder": 10, "extra": 10, "part_of": 8, "g_missing": 8, "other": 4}


def auditprep(mode="sample", per_file=30):
    """AGREED non-identity mappings for auditors who try to refute them: a stratified sample (u01–u02), or
    mode=rest: all the others (u03 …) — after the sample found 3 shared mistakes in 60"""
    rows = [r for r in load_jsonl(S18 / "map_cmp.jsonl") if r["status"] == "agree"]
    by = defaultdict(list)
    for r in rows:
        o = outcome(r["A"])
        if o == "identity":
            continue
        k = next((t for t in ("split", "part_of", "g_missing", "reorder", "extra") if t in o.split("+")), "other")
        by[k].append(r)
    pick = []
    if mode == "sample":
        for k, n in AUDIT_PLAN.items():
            lst = by[k]
            step = max(1, len(lst) // n)
            pick += lst[::step][:n]
        first = 1
    else:
        done = set()
        for f in ADJ_IN.glob("u*.json"):
            done |= set(json.load(open(f, encoding="utf-8"))["nids"])
        pick = sorted((r for lst in by.values() for r in lst if r["nid"] not in done), key=lambda r: r["nid"])
        first = 1 + len(list(ADJ_IN.glob("u*.json")))
    blocks = {}
    for f in sorted(MAP_IN.glob("b*.txt")):
        for part in re.split(r"\n(?==== g\d{4})", f.read_text(encoding="utf-8"))[1:]:
            blocks[part[4:9]] = part.rstrip()
    ADJ_IN.mkdir(parents=True, exist_ok=True)
    groups = [pick[i:i + per_file] for i in range(0, len(pick), per_file)]
    for gi, g in enumerate(groups, first):
        name = f"u{gi:02d}"
        L = [f"AUDIT {name}: {len(g)} nests; two independent readers AGREED on the mapping shown under each nest."]
        for r in g:
            L += ["", blocks[r["nid"]], "AGREED READING:", map_text("A", r["A"]).replace("reader A:", "agreed:")]
        (ADJ_IN / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump({"nids": [r["nid"] for r in g], "batches": {r["nid"]: r["batch"] for r in g}},
                  open(ADJ_IN / f"{name}.json", "w", encoding="utf-8"))
    print(json.dumps({"sample": len(pick), "files": len(groups), "by_kind": {k: len(by[k]) for k in by}}))


# ------------------------------------------------------------------ rebuild: split / merge nests by Гузеев
# Linguist's answers (2026-11-06): В9, В10 — split our entries by Гузеев's homonyms (conversion and lexical);
# Г1 — merge our entries that are one Гузеев homonym; В11 — our homonyms absent from Гузеев stay, flag
# not_in_guzeev, numbered after his; В13 — numbering in Гузеев's order; Г2 — Гузеев homonyms missing from the
# corpus become stubs (dict_id 3, no translation, «нареч. к X» for adverbs); В15 — no text from the book.
REB_IN = LOC / "rebuild_in"
REB_OUT = S18 / "rebuild_out"
FIELDS = ("def1", "def2", "misc1", "misc2")
# what a rebuild may drop or add: sense numbers, «||» / «//», «В позиции определения:» before the sense that
# becomes an adjective homonym, the zone marks ◊ / ▯ repeated when a phrase or compound block is split
DROPPABLE = re.compile(r"^(?:\d{1,2}[.)]?|[а-е]\)|\|\||//|в|позиции|определения:?|◊|▯|i{1,3}|iv|v)$")
# a sense number glued to its word in КБРС def1 («1.смелый», «1)липнуть», ~750 in 06) is a sense number too:
# peeled off after the edge strip, so «1.смелый» and «смелый» count as the same word
GLUED_NUM = re.compile(r"^\d{1,2}[.)](?=[^\W\d_])")
PUNCT = ".,;:!?()«»\"'—–-"


def tokens(s):
    # «||» glued to its word in КБРС def1 («лысина||», «акула||акулий», 64 in 06) is the separator too: split off,
    # so a rebuild may drop it once the adjective / adverb after it has moved to a homonym of its own
    toks = [t.strip(PUNCT) for t in (s or "").replace("||", " || ").lower().split()]
    toks = [GLUED_NUM.sub("", t).strip(PUNCT) for t in toks]
    return Counter(t for t in toks if t and not DROPPABLE.match(t))


def dup_dropped(h):
    """{field: [text, …]} a homonym dropped because it repeats a sense the homonym keeps — two merged entries
    that carry the same sense (КБРС чот 5) copied into чот1, flag dup_def1, and kept in чот2)"""
    return {k: v if isinstance(v, list) else [v] for k, v in (h.get("dup_dropped") or {}).items()}


def needs_rebuild(m):
    return any(x.get("role") in ("covers_several", "part_of") for x in m.get("entries", []))


ALLOW = S18 / "rebuild_allow.json"


def allowances():
    """{nid: {...}} what the second round (revision of a rebuilt nest) may do beyond cutting and moving text:
      add    {field: [text]}  a phrase head repeated in the homonym its sub-sense went to («арты бла» а) / б)),
                              a translation shared by two homonyms (ставка), a КБРС example lost at step 01
      drop   {field: [text]}  a cross-reference left pointing nowhere («Топ окъ къ. топ 1.»), and every glued
                              article that leaves the nest (fixes.json, action move_out — added here)
      extra_from [entry_id]   entries that may feed a homonym of our own (g = 0: a sense Гузеев does not
                              have, numbered after his homonyms like any not_in_guzeev entry)"""
    al = json.load(open(ALLOW, encoding="utf-8")) if ALLOW.exists() else {}
    al = {k: v for k, v in al.items() if not k.startswith("_")}
    fixes = json.load(open(S18 / "fixes.json", encoding="utf-8")) if (S18 / "fixes.json").exists() else {}
    for fx in fixes.values():
        if fx["action"] == "move_out":
            a = al.setdefault(fx["nid"], {})
            a.setdefault("drop", {}).setdefault(fx["field"], []).append(fx["text"])
    return al


def load_rebuilt():
    """nid -> rebuilt nest: first round r*.json, overridden by the second round x*.json"""
    reb = {}
    for rnd, pat in ((1, "r*.json"), (2, "x*.json")):
        for f in sorted(REB_OUT.glob(pat)):
            for r in json.load(open(f, encoding="utf-8"))["nests"]:
                reb[r["nid"]] = dict(r, _round=rnd, _file=f.stem)
    return reb


def rebuildprep(per_file=8):
    nests = {n["nid"]: n for n in load_jsonl(LOC / "nests.jsonl")}
    es = {e["entry_id"]: e for e in load_jsonl(F06)}
    todo = [m for m in load_jsonl(S18 / "mapping.jsonl") if needs_rebuild(m)]
    REB_IN.mkdir(parents=True, exist_ok=True)
    for f in REB_IN.glob("r*.*"):
        f.unlink()
    groups = [todo[i:i + per_file] for i in range(0, len(todo), per_file)]
    for gi, grp in enumerate(groups, 1):
        name = f"r{gi:02d}"
        L = [f"REBUILD {name}: {len(grp)} nests."]
        meta = []
        for m in grp:
            n = nests[m["nid"]]
            mapped = [x for x in m["entries"] if x.get("g")]
            gs = sorted({k for x in mapped for k in x["g"]})
            L += ["", f"=== {m['nid']}  {n['header']}  (Гузеев p. {n['page']})   build homonyms g = {gs}",
                  "GUZEEV:"]
            for h in n["homs"]:
                if h["n"] in gs:
                    L.append(f"  n={h['n']}  labels: {' '.join(h['labels']) or '—'}")
                    for sn in h["senses"]:
                        L.append(f"     {str(sn['num']) + '.' if sn['num'] else '-'} {cut(sn['def'] or sn['text'], 220)}")
            L.append("MAPPING (agreed by two readers or settled by an adjudicator):")
            for x in mapped:
                hint = "; ".join(f"{k}: {x[k]}" for k in sorted(x) if k.endswith("_split") and x.get(k))
                L.append(f"  {x['entry_id']} {es[x['entry_id']]['word']} -> g={x['g']} {x['role']}" + (f"   [{hint}]" if hint else ""))
            L.append(f"  note: {m.get('note_ru', '')}")
            L.append("ENTRIES (full text of every field):")
            for x in mapped:
                e = es[x["entry_id"]]
                L.append(f"  --- {e['entry_id']}  {e['word']}  dict={e['dict_id']}")
                for k in ("tags",) + FIELDS:
                    L.append(f"    {k}: {e.get(k) or ''}")
            meta.append({"nid": m["nid"], "g": gs, "entries": {x["entry_id"]: x["g"] for x in mapped}})
        (REB_IN / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump(meta, open(REB_IN / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({"nests": len(todo), "files": len(groups)}))


def rebuildcheck(name):
    """every final homonym is built from the right entries; every word of every field is kept (no loss,
    no addition; sense numbers and «В позиции определения» excepted, and a repeat listed in "dup_dropped"
    if its words are still in that field of the homonym)"""
    meta = json.load(open(REB_IN / f"{name}.json", encoding="utf-8"))
    es = {e["entry_id"]: e for e in load_jsonl(F06)}
    al = allowances()
    try:
        out = {r["nid"]: r for r in json.load(open(REB_OUT / f"{name}.json", encoding="utf-8"))["nests"]}
    except Exception as ex:
        print(f"INVALID JSON: {ex}")
        return 1
    errs = []
    for t in meta:
        r = out.get(t["nid"])
        a = al.get(t["nid"], {})
        if not r:
            errs.append(f"{t['nid']}: missing")
            continue
        homs = r.get("homs", [])
        gs = [h.get("g") for h in homs if h.get("g") != 0]
        if sorted(gs) != t["g"]:
            errs.append(f"{t['nid']}: homs g={sorted(gs)}, expected {t['g']}")
        used = set()
        for h in homs:
            for eid in h.get("from", []):
                if eid not in t["entries"]:
                    errs.append(f"{t['nid']} g={h.get('g')}: unknown entry {eid}")
                elif h.get("g") == 0:
                    if eid not in a.get("extra_from", []):
                        errs.append(f"{t['nid']} g=0: {eid} may not feed a homonym of our own (rebuild_allow extra_from)")
                elif h.get("g") not in t["entries"][eid]:
                    errs.append(f"{t['nid']} g={h.get('g')}: {eid} is mapped to {t['entries'][eid]}, not to {h.get('g')}")
                used.add(eid)
            if not any((h.get(k) or "").strip() for k in FIELDS):
                errs.append(f"{t['nid']} g={h.get('g')}: empty homonym")
            for k, lst in dup_dropped(h).items():
                for d in lst:
                    # a repeat: its words are still in that field of this homonym or of another one in the nest
                    # (суу: the КБРС river block copied into both суу1 and суу2 by an earlier split)
                    if k not in FIELDS or not tokens(d) or all(tokens(d) - tokens(o.get(k)) for o in homs):
                        errs.append(f"{t['nid']} g={h.get('g')}: dup_dropped {k} {d!r} is not a repeat of its {k}")
        for eid in t["entries"]:
            if eid not in used:
                errs.append(f"{t['nid']}: entry {eid} not used")
        for k in FIELDS:
            want = Counter()
            for eid in t["entries"]:
                want += tokens(es[eid].get(k))
            for s in a.get("add", {}).get(k, []):
                want += tokens(s)
            got = Counter()
            for h in homs:
                got += tokens(h.get(k))
                for d in dup_dropped(h).get(k, []):
                    got += tokens(d)
            for s in a.get("drop", {}).get(k, []):
                got += tokens(s)
            if want != got:
                lost, added = want - got, got - want
                errs.append(f"{t['nid']} {k}: lost {dict(lost) or '—'}; added {dict(added) or '—'}")
    extra = set(out) - {t["nid"] for t in meta}
    if extra:
        errs.append(f"unknown nests {sorted(extra)}")
    print("OK" if not errs else "ERRORS:\n" + "\n".join(errs))
    return 0 if not errs else 1


REVISE = S18 / "revise.json"


def reviseprep(budget=80000, per_file=7):
    """second round: the rebuild agents flagged 34 nests where a needed move was outside the mapping (an entry
    must also feed another homonym), needed a phrase head repeated, or a glued article had to leave the nest.
    revise.json = {nid: {"decision": text, "hand": bool}} — the decision taken on each flag (map_amend.json and
    rebuild_allow.json carry the matching mapping and allowances; run mapmerge first).  Writes
    rebuild_in/xNN.json (meta, as for r*) + xNN.txt (the nest as rebuilt, the flag, the decision, the texts);
    the nests marked "hand" go to x00 (edited by a script, not by an agent)."""
    rev = {k: v for k, v in json.load(open(REVISE, encoding="utf-8")).items() if not k.startswith("_")}
    nests = {n["nid"]: n for n in load_jsonl(LOC / "nests.jsonl")}
    es = {e["entry_id"]: e for e in load_jsonl(F06)}
    mp = {m["nid"]: m for m in load_jsonl(S18 / "mapping.jsonl")}
    first = {}
    for f in sorted(REB_OUT.glob("r*.json")):
        for r in json.load(open(f, encoding="utf-8"))["nests"]:
            first[r["nid"]] = r
    al = allowances()
    for f in REB_IN.glob("x*.*"):
        f.unlink()
    blocks = {}
    for nid in rev:
        L, meta = [], []
        m, n, r = mp[nid], nests[nid], first[nid]
        assert needs_rebuild(m), nid
        mapped = [x for x in m["entries"] if x.get("g")]
        gs = sorted({k for x in mapped for k in x["g"]})
        L += ["", f"=== {nid}  {n['header']}  (Гузеев p. {n['page']})   homonyms g = {gs}", "GUZEEV:"]
        for h in n["homs"]:
            if h["n"] in gs:
                L.append(f"  n={h['n']}  labels: {' '.join(h['labels']) or '—'}")
                for sn in h["senses"]:
                    L.append(f"     {str(sn['num']) + '.' if sn['num'] else '-'} {cut(sn['def'] or sn['text'], 220)}")
        L.append("MAPPING NOW (after the amendment of this round, if any):")
        for x in mapped:
            hint = "; ".join(f"{k}: {x[k]}" for k in sorted(x) if k.endswith("_split") and x.get(k))
            L.append(f"  {x['entry_id']} {es[x['entry_id']]['word']} -> g={x['g']} {x['role']}" + (f"   [{hint}]" if hint else ""))
        a = al.get(nid, {})
        if a:
            L.append("ALLOWED BEYOND CUT-AND-MOVE (rebuild_allow.json; the check counts exactly these words):")
            for kind in ("add", "drop"):
                for k, lst in a.get(kind, {}).items():
                    for s in lst:
                        L.append(f"  {kind} {k}: {s}")
            if a.get("extra_from"):
                L.append(f"  homonym of our own (g = 0) may be built from: {a['extra_from']}")
        L.append("FLAG OF THE FIRST ROUND (mapping_issue):")
        L.append("  " + (r.get("mapping_issue") or "").strip())
        L.append("DECISION (do exactly this):")
        L.append("  " + rev[nid]["decision"].strip())
        L.append("NEST AS REBUILT IN THE FIRST ROUND (start from this; change only what the decision says):")
        L.append(json.dumps({k: r[k] for k in ("nid", "homs")}, ensure_ascii=False, indent=1))
        L.append("ENTRIES (full text of every field, as in the corpus):")
        for x in mapped:
            e = es[x["entry_id"]]
            L.append(f"  --- {e['entry_id']}  {e['word']}  dict={e['dict_id']}")
            for k in ("tags",) + FIELDS:
                L.append(f"    {k}: {e.get(k) or ''}")
        meta.append({"nid": nid, "g": gs, "entries": {x["entry_id"]: x["g"] for x in mapped}})
        blocks[nid] = (L, meta)
    # the nests marked "hand" -> x00; the rest packed by size (first fit, largest first): a few nests are huge
    # (къара 84 000 characters with its entries), most are small
    size = {k: sum(len(s) + 1 for s in blocks[k][0]) for k in blocks}
    bins = []
    for nid in sorted((k for k in rev if not rev[k].get("hand")), key=lambda k: -size[k]):
        b = next((b for b in bins if sum(size[k] for k in b) + size[nid] <= budget and len(b) < per_file), None)
        if b is None:
            bins.append([nid])
        else:
            b.append(nid)
    hand = sorted(k for k, v in rev.items() if v.get("hand"))
    groups = ([("x00", hand)] if hand else []) + [(f"x{i:02d}", sorted(b)) for i, b in enumerate(bins, 1)]
    for name, grp in groups:
        L = [f"REVISE {name}: {len(grp)} nests."]
        meta = []
        for nid in grp:
            L += blocks[nid][0]
            meta += blocks[nid][1]
        (REB_IN / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump(meta, open(REB_IN / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(json.dumps({"nests": len(rev), "files": {g[0]: g[1] for g in groups}}, ensure_ascii=False))


KB_POS = {"N": "ат.", "A": "сыф.", "ADV": "сёзл.", "V": "эт.", "INTJ": "межд.", "PART": "кес.", "CONJ": "байл.",
          "POSTP": "сонг.", "PRON": "алм.", "NUM": "сан.", "ONOM": "эрикл.", "MOD": "къарам. с.", "PRED": "пред."}
DROP_FLAGS = {"no_d1_pair", "no_d2_pair", "split_def1"}


def apply_s18():
    """mapping + rebuilt nests + fixes -> 06 (numbering by Гузеев, splits, merges, stubs, links)"""
    nests = {n["nid"]: n for n in load_jsonl(LOC / "nests.jsonl")}
    mp = {m["nid"]: m for m in load_jsonl(S18 / "mapping.jsonl")}
    assert not [k for k, m in mp.items() if m.get("source") == "unresolved"], "unresolved nests in mapping"
    reb = load_rebuilt()
    fixes = json.load(open(S18 / "fixes.json", encoding="utf-8")) if (S18 / "fixes.json").exists() else {}
    fixes = {k: v for k, v in fixes.items() if not k.startswith("_")}
    es = load_jsonl(F06)
    byid = {e["entry_id"]: e for e in es}
    maxid = max(int(e["entry_id"][2:]) for e in es)
    newid = iter(f"e_{k:05d}" for k in range(maxid + 1, maxid + 100000))
    out_entries, consumed, log, stat = [], set(), [], Counter()

    def sub_free(e):
        return {k: v for k, v in e.items() if not k.startswith(("misc1_", "misc2_"))}

    for nid, m in sorted(mp.items()):
        n = nests[nid]
        G = {h["n"]: h for h in n["homs"]}
        mapped = [x for x in m["entries"] if x.get("g")]
        if not mapped and not m.get("g_missing"):
            continue
        ids_in_nest = [x["entry_id"] for x in m["entries"]]
        if not ids_in_nest:
            # the word itself is absent from the corpus (5 nests; 4 are spelling variants of our words:
            # Жанпик ~ jампик, Иничке ~ иничге …) — no stubs for whole words, listed in the report
            stat["absent_nest"] += 1
            continue
        old_words = {i: byid[i]["word"] for i in ids_in_nest}
        bases = Counter(base_of(byid[x["entry_id"]]["word"]) for x in mapped) or \
            Counter(base_of(byid[i]["word"]) for i in ids_in_nest)
        base = bases.most_common(1)[0][0]
        final = {}                                   # Гузеев n -> entry
        own = []                                     # g = 0: a sense of ours Гузеев does not have (second round)
        if needs_rebuild(m):
            r = reb[nid]
            claimed = set()
            spread = {i for i, c in Counter(i for h in r["homs"] for i in h["from"]).items() if c > 1}
            # g = 0 last, so that Гузеев's homonyms keep the entry ids of the entries they are built from
            for h in sorted(r["homs"], key=lambda h: (h["g"] == 0, h["g"])):
                srcs = [byid[i] for i in h["from"]]
                main = next((s for s in srcs if s["entry_id"] not in claimed), None)
                e = sub_free(main if main else srcs[0])
                if main:
                    claimed.add(main["entry_id"])
                else:
                    e["entry_id"] = next(newid)
                for k in FIELDS:
                    e[k] = (h.get(k) or "").strip()
                e["tags"] = (h.get("tags") or "").strip()
                has1 = bool(e["def1"] or e["misc1"])
                has2 = bool(e["def2"] or e["misc2"])
                if not has1 and not has2:
                    has1 = any(s.get("src1") for s in srcs)
                e["src1"] = list(dict.fromkeys(x for s in srcs for x in (s.get("src1") or []))) if has1 else []
                e["src2"] = list(dict.fromkeys(x for s in srcs for x in (s.get("src2") or []))) if has2 else []
                e["dict_id"] = "both" if has1 and has2 else ("1" if has1 else "2")
                e["word1_orig"] = next((s.get("word1_orig") for s in srcs if s.get("word1_orig")), "") if has1 else ""
                e["word2_orig"] = next((s.get("word2_orig") for s in srcs if s.get("word2_orig")), "") if has2 else ""
                if not has1:
                    e["decl"] = ""
                fl = [f for s in srcs for f in (s.get("flags") or []) if f not in DROP_FLAGS]
                if any(s["entry_id"] in spread or len(next(x for x in mapped if x["entry_id"] == s["entry_id"])["g"]) > 1
                       for s in srcs):
                    fl.append("guzeev_split")
                if len(srcs) > 1:
                    fl.append("guzeev_merged")
                if e["dict_id"] == "2":
                    fl.append("no_d1_pair")
                if e["dict_id"] == "1":
                    fl.append("no_d2_pair")
                e["flags"] = list(dict.fromkeys(fl))
                e["built_from"] = [old_words[s["entry_id"]] for s in srcs]
                if h["g"] == 0:
                    own.append(e)
                else:
                    final[h["g"]] = e
            consumed |= {x["entry_id"] for x in mapped}
        else:
            for x in mapped:
                final[x["g"][0]] = dict(byid[x["entry_id"]])
                consumed.add(x["entry_id"])
        # stubs for Гузеев homonyms the corpus lacks (Г2)
        for k in m.get("g_missing") or []:
            h = G[k]
            pos = h["pos"][0] if h["pos"] else None
            if pos is None:                          # lexical nest: the homonyms share the POS of ours
                pos = next((p for x in mapped for p in [our_pos(byid[x["entry_id"]])] if p != "?"), None)
            final[k] = {"entry_id": next(newid), "dict_id": "3", "tags": KB_POS.get(pos, ""), "def1": "", "def2": "",
                        "misc1": "", "misc2": "", "lextag": "", "src1": [], "src2": [], "word1_orig": "",
                        "word2_orig": "", "flags": ["guzeev_stub", "no_russian_def"], "_pos": pos}
            stat["stub"] += 1
        extras = [dict(byid[x["entry_id"]]) for x in m["entries"] if x["role"] == "not_in_guzeev"] + own
        consumed |= {x["entry_id"] for x in m["entries"] if x["role"] == "not_in_guzeev"}
        order = [final[k] for k in sorted(final)] + extras
        total = len(order)
        for i, (e, k) in enumerate([(final[k], k) for k in sorted(final)] + [(e, None) for e in extras], 1):
            w = base + (str(i) if total > 1 else "")
            if e.get("word") and e["word"] != w:
                e.setdefault("flags", []).append("guzeev_renumbered")
            e["word"] = w
            e["word_base"] = base
            e["hom_rank"] = i if total > 1 else 99
            if k is not None:
                h = G[k]
                e["guzeev"] = {"nid": nid, "n": k, "page": h["page"]}
            else:
                e.setdefault("flags", []).append("not_in_guzeev")
                e.pop("guzeev", None)
            e["flags"] = list(dict.fromkeys(e.get("flags") or []))
        # adverb stubs point to the adjective of the nest: «нареч. к адетли1»
        adj = next((final[k]["word"] for k in sorted(final) if G[k]["pos"][:1] == ["A"] and
                    "guzeev_stub" not in final[k]["flags"]), None)
        for k in sorted(final):
            e = final[k]
            if e.pop("_pos", None) == "ADV" and adj and "guzeev_stub" in e["flags"]:
                e["tags"] = f"{e['tags']}; нареч. к {adj}".strip("; ")
        for e in order:
            out_entries.append(e)
        log.append({"nid": nid, "header": n["header"], "old": [old_words[i] for i in ids_in_nest],
                    "new": [e["word"] for e in order], "stubs": [e["word"] for e in order if "guzeev_stub" in e["flags"]],
                    "rebuilt": reb[nid]["_file"] if needs_rebuild(m) else False})
        stat["nests"] += 1
    # corpus errors found on the way (fixes.json, by entry_id), in this order:
    #   split_kbrs  an entry where КБРС and ТСКБЯ texts of two different words were merged: the КБРС side
    #               becomes its own entry (къур: КБРС «о курлыканье» + ТСКБЯ «строить»)
    #   merge_into  a КБРС verb filed under a wrong stem (кесерге -> кёсе) / a ТСКБЯ entry with a misread
    #               headword (кий = кийин) joins the entry of its real word
    #   rename      a misread headword or a loanword (аула -> ауна, jаз6 -> джаз), a paired-word stub without
    #               its pair (буршу -> эрши-буршу)
    #   delete      a stub «парн. к X-» whose paired word is already an entry
    #   moved       the entry went to another nest through map_amend.json
    def find(eid):
        x = next((x for x in out_entries if x["entry_id"] == eid), None)
        if x is None:
            assert eid not in consumed, eid
            x = byid[eid]
        return x

    def set_dict(t):
        has1 = bool(t.get("def1") or t.get("misc1") or t.get("src1"))
        has2 = bool(t.get("def2") or t.get("misc2") or t.get("src2"))
        t["dict_id"] = "both" if has1 and has2 else ("1" if has1 else "2")
        t["flags"] = [f for f in dict.fromkeys((t.get("flags") or []) + ["guzeev_fix"])
                      if not (f == "no_d1_pair" and has1) and not (f == "no_d2_pair" and has2)]
        for k in [k for k in t if k.startswith(("misc1_", "misc2_"))]:
            t.pop(k)

    order_fx = {"split_kbrs": 0, "merge_into": 1, "rename": 2, "delete": 3, "moved": 4, "move_out": 5}
    for key, fx in sorted(fixes.items(), key=lambda kv: order_fx[kv[1]["action"]]):
        eid = key.split("#")[0]                      # «e_16214#glued»: several fixes of one entry
        stat[f"fix_{fx['action']}"] += 1
        log.append({"fix": key, "word": byid[eid]["word"], **fx})
        if fx["action"] == "moved":
            continue
        if fx["action"] == "move_out":
            #   move_out  an article of another word glued into this entry by the segmenter of its dictionary
            #             (ТСКБЯ «▭ АЗ-АЗ мард. сёзл. …» inside аз2, «тюйгюч ат. Ступка …» inside тюй3; КБРС
            #             «къандес …, къандис …» inside къандагъай II): the second round cut it out of the
            #             rebuilt nest (rebuild_allow drop), here it joins the entry of its own word or becomes
            #             one. The words that arrive are the words that left: the head of the article, the
            #             marks dropped with it («▭» taken for a citation start) and a tilde expanded to the
            #             wrong head («~ оюн» = къандис оюн, not къандагъай оюн) excepted.
            tk = lambda s: tokens((s or "").replace("/", " "))
            want = tk(fx["text"])
            for a, b in (fx.get("corrected") or {}).items():
                want = want - Counter({a.lower(): 1}) + Counter({b.lower(): 1})
            got = tk(" ".join(fx.get("discard", [])))
            for t in fx["to"]:
                got += tk(" ".join([t["head"], t.get("tags", "")] + [t.get(k, "") for k in FIELDS]))
            assert want == got, (key, dict(want - got), dict(got - want))
            src = byid[eid]
            for t in fx["to"]:
                if t.get("target"):
                    tgt = find(t["target"])
                    if not any(x is tgt for x in out_entries):
                        out_entries.append(tgt)
                        consumed.add(t["target"])
                else:
                    tgt = {"entry_id": next(newid), "word": t["new"], "word_base": t["new"], "dict_id": "", "tags": "", "def1": "",
                           "def2": "", "misc1": "", "misc2": "", "lextag": t.get("lextag", ""), "src1": [], "src2": [],
                           "word1_orig": "", "word2_orig": "", "decl": "", "flags": [], "hom_rank": 99}
                    out_entries.append(tgt)
                tgt["tags"] = tgt.get("tags") or t.get("tags", "")
                for k in FIELDS:
                    if t.get(k):
                        sep = "; " if k == "misc1" else " "
                        tgt[k] = ((tgt.get(k) or "") + (sep if tgt.get(k) else "") + t[k]).strip()
                if t.get("def1") or t.get("misc1"):
                    tgt["src1"] = list(dict.fromkeys((tgt.get("src1") or []) + (src.get("src1") or [])))
                if t.get("def2") or t.get("misc2"):
                    tgt["src2"] = list(dict.fromkeys((tgt.get("src2") or []) + (src.get("src2") or [])))
                tgt["flags"] = list(dict.fromkeys((tgt.get("flags") or []) + ["glued_article_split"]))
                tgt.setdefault("built_from", [])
                tgt["built_from"] = list(dict.fromkeys(tgt["built_from"] + [byid[eid]["word"]]))
                set_dict(tgt)
            continue
        if fx["action"] == "split_kbrs":
            e = find(eid)
            k1 = {"entry_id": next(newid), "word": fx["kbrs_word"], "word_base": base_of(fx["kbrs_word"]), "dict_id": "1", "tags": fx.get("kbrs_tags", ""),
                  "def1": e.get("def1", ""), "def2": "", "misc1": e.get("misc1", ""), "misc2": "",
                  "lextag": fx.get("kbrs_lextag", e.get("lextag", "")), "src1": e.get("src1") or [], "src2": [],
                  "word1_orig": e.get("word1_orig", ""), "word2_orig": "", "decl": e.get("decl", ""),
                  "flags": ["guzeev_fix", "no_d2_pair"], "hom_rank": 2}
            e.update({"word": fx["word"], "word_base": base_of(fx["word"]), "tags": fx.get("tags", e.get("tags", "")), "def1": "", "misc1": "",
                      "src1": [], "word1_orig": "", "decl": "", "hom_rank": 1})
            set_dict(e)
            if not any(x is e for x in out_entries):
                out_entries.append(e)
                consumed.add(eid)
            out_entries.append(k1)
            continue
        e = byid[eid]
        consumed.add(eid)
        if fx["action"] == "delete":
            continue
        if fx["action"] == "rename":
            r = dict(e, word=fx["word"], word_base=base_of(fx["word"]))
            if fx.get("word2_orig"):
                r["word2_orig"] = fx["word2_orig"]
            set_dict(r)
            out_entries.append(r)
            continue
        if fx["action"] == "merge_into":
            tgt = find(fx["target"])
            if not any(x is tgt for x in out_entries):
                out_entries.append(tgt)
                consumed.add(fx["target"])
            for k in FIELDS:
                if e.get(k):
                    sep = "; " if k == "misc1" else " "
                    tgt[k] = ((tgt.get(k) or "") + (sep if tgt.get(k) else "") + e[k]).strip()
            for k in ("src1", "src2"):
                tgt[k] = list(dict.fromkeys((tgt.get(k) or []) + (e.get(k) or [])))
            for k in ("word1_orig", "word2_orig", "decl", "tags"):
                tgt[k] = tgt.get(k) or e.get(k, "")
            if fx.get("word2_orig"):
                tgt["word2_orig"] = fx["word2_orig"]
            tgt.setdefault("built_from", [])
            tgt["built_from"] = list(dict.fromkeys(tgt["built_from"] + [e["word"]]))
            set_dict(tgt)
    loose = [x["entry_id"] for m in mp.values() for x in m["entries"]
             if x.get("role") in ("fragment", "other_word") and x["entry_id"] not in fixes]
    assert not loose, f"fragments / other words without a decision in fixes.json: {loose}"
    rest = [e for e in es if e["entry_id"] not in consumed]
    new = rest + out_entries
    ids = Counter(e["entry_id"] for e in new)
    words = Counter(e["word"] for e in new)
    assert not [i for i, c in ids.items() if c > 1], [i for i, c in ids.items() if c > 1][:10]
    dup = [w for w, c in words.items() if c > 1]
    assert not dup, dup[:20]
    new.sort(key=lambda e: e["word"])
    save_jsonl(F06, new)
    save_jsonl(CK / "qa" / "s18_apply.jsonl", log)
    print(json.dumps({"entries_before": len(es), "entries_after": len(new), **stat}, ensure_ascii=False))



def adjcheck(name, who="J"):
    """validate an adjudicator's file: its nests only, same rules as mapcheck"""
    meta = json.load(open(ADJ_IN / f"{name}.json", encoding="utf-8"))
    items = {}
    for nid, batch in meta["batches"].items():
        b = json.load(open(MAP_IN / f"{batch}.json", encoding="utf-8"))
        items[nid] = next(it for it in b["nests"] if it["nid"] == nid)
    tmp = MAP_IN / f"_{name}.json"
    json.dump({"batch": name, "nests": [items[n] for n in meta["nids"]]}, open(tmp, "w", encoding="utf-8"),
              ensure_ascii=False)
    try:
        return mapcheck(f"_{name}", who, out_name=f"{name}_{who}")
    finally:
        tmp.unlink()


def resolveprep(per_file=15):
    """audit verdicts «wrong» -> a fresh resolver sees the agreed reading and the auditor's correction"""
    cmp_ = {r["nid"]: r for r in load_jsonl(S18 / "map_cmp.jsonl")}
    wrong = []
    for f in sorted(MAP_OUT.glob("u*_U.json")):
        for n in json.load(open(f, encoding="utf-8"))["nests"]:
            if n.get("verdict") == "wrong" and sig(n) != sig(cmp_[n["nid"]]["A"]):
                wrong.append((cmp_[n["nid"]], n))
    blocks = {}
    for f in sorted(MAP_IN.glob("b*.txt")):
        for part in re.split(r"\n(?==== g\d{4})", f.read_text(encoding="utf-8"))[1:]:
            blocks[part[4:9]] = part.rstrip()
    for f in ADJ_IN.glob("v*.*"):
        f.unlink()
    rows_by_nid = {r["nid"]: r for r in load_jsonl(S18 / "align.jsonl")}
    es = {e["entry_id"]: e for e in load_jsonl(F06)}
    groups = [wrong[i:i + per_file] for i in range(0, len(wrong), per_file)]
    for gi, g in enumerate(groups, 1):
        name = f"v{gi:02d}"
        L = [f"RESOLVE {name}: {len(g)} nests. Two independent readers agreed on reading A; an auditor says it is "
             f"wrong and proposes reading B."]
        for c, u in g:
            L += ["", blocks[c["nid"]]] + misc1_appendix(c["nid"], rows_by_nid, es) + [
                  "READINGS:", map_text("A", c["A"]).replace("reader A:", "agreed (A):"),
                  map_text("B", u).replace("reader B:", "auditor (B):")]
        (ADJ_IN / f"{name}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
        json.dump({"nids": [c["nid"] for c, u in g], "batches": {c["nid"]: c["batch"] for c, u in g}},
                  open(ADJ_IN / f"{name}.json", "w", encoding="utf-8"))
    print(json.dumps({"to_resolve": len(wrong), "files": len(groups)}))


def misc1_appendix(nid, rows_by_nid, es):
    """the readers' view hid КБРС examples (misc1) of entries that have def1 — the resolvers see them all"""
    L = ["КБРС EXAMPLES (misc1, full) of the OURS entries:"]
    for o in rows_by_nid[nid]["ours"]:
        m = es[o["entry_id"]].get("misc1") or ""
        if m:
            L.append(f"  {o['entry_id']} {o['word']}: {cut(m, 900)}")
    return L if len(L) > 1 else []


def mapmerge():
    """final semantic mapping: auto (1:1 by part of speech) + agreed readings + adjudications + audit
    resolutions (a resolver's decision wins over the agreed reading)"""
    rows = load_jsonl(S18 / "align.jsonl")
    cmp_ = {r["nid"]: r for r in load_jsonl(S18 / "map_cmp.jsonl")}
    adj, res, hints = {}, {}, {}
    for f in sorted(MAP_OUT.glob("a*_J.json")):
        adj.update(load_map(f.stem) or {})
    for f in sorted(MAP_OUT.glob("v*_R.json")):
        res.update(load_map(f.stem) or {})
    for f in sorted(MAP_OUT.glob("u*_U.json")):          # auditor kept the mapping but corrected the hints
        for nid, n in (load_map(f.stem) or {}).items():
            if n.get("verdict") == "wrong" and nid in cmp_ and sig(n) == sig(cmp_[nid]["A"]):
                hints[nid] = n
    out, stat = [], Counter()
    for r in rows:
        if auto_ok(r):
            o2 = [o for o in r["ours"] if o["dict_id"] in ("both", "2")]
            rec = {"nid": r["nid"], "source": "auto_pos",
                   "entries": [{"entry_id": o["entry_id"], "g": [g["n"]], "role": "same"} for o, g in zip(o2, r["g"])],
                   "g_missing": [], "confidence": "high", "note_ru": "1:1 (по частям речи)"}
        elif r["nid"] in res:
            rec = dict(res[r["nid"]], source="audit_resolved")
        elif r["nid"] in hints:
            rec = dict(hints[r["nid"]], source="audit_hints")
        elif r["nid"] in adj:
            rec = dict(adj[r["nid"]], source="adjudicated")
        elif cmp_.get(r["nid"], {}).get("status") == "agree":
            c = cmp_[r["nid"]]
            rec = dict(c["A"], source="agreed", note_B=c["B"].get("note_ru", ""))
        else:
            rec = {"nid": r["nid"], "source": "unresolved"}
        stat[rec["source"]] += 1
        out.append(rec)
    # hand amendments (map_amend.json): an entry moved from the nest of a wrong stem to its real nest
    # (ата3 = КБРС «атаргъа» -> nest Ат), a role corrected after looking at the corpus
    am = json.load(open(S18 / "map_amend.json", encoding="utf-8")) if (S18 / "map_amend.json").exists() else {}
    by = {r["nid"]: r for r in out}
    for nid, a in am.items():
        r = by[nid]
        r["entries"] = [x for x in r["entries"] if x["entry_id"] not in set(a.get("remove", []))]
        for x in a.get("set", []):
            r["entries"] = [y for y in r["entries"] if y["entry_id"] != x["entry_id"]] + [x]
        r["amended"] = a.get("why", True)
        stat["amended"] += 1
    save_jsonl(S18 / "mapping.jsonl", out)
    print(json.dumps(dict(stat)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["parse", "align", "mapprep", "mapcheck", "mapcompare", "adjprep", "adjcheck",
                                      "auditprep", "resolveprep", "mapmerge", "rebuildprep", "rebuildcheck", "reviseprep",
                                      "apply"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    if a.phase == "mapcheck":
        sys.exit(mapcheck(*a.args))
    if a.phase == "adjcheck":
        sys.exit(adjcheck(*a.args))
    if a.phase == "rebuildcheck":
        sys.exit(rebuildcheck(*a.args))
    if a.phase == "auditprep":
        sys.exit(auditprep(*a.args))
    {"parse": main_parse, "align": align, "mapprep": mapprep, "mapcompare": mapcompare, "adjprep": adjprep,
     "resolveprep": resolveprep, "mapmerge": mapmerge, "rebuildprep": rebuildprep, "reviseprep": reviseprep,
     "apply": apply_s18}[a.phase]()
