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
  voicing2   (2026-11-06) the other spelling of the same possessive: «~гъы», «~ги», «~гъынгы» —
             tilde + voiced consonant + high vowel — repeats the voicing hint, so the tilde is the
             headword minus its final къ/к (агрессиялыкъ (-гъы) … политиканы ~гъы = агрессиялыгъы,
             адамлыкъ … ~гъын билебиз = адамлыгъын).  S0a and s17 prep put the whole headword in
             front (агрессиялыкъгъы, джитиликги).  Raw texts: qmos + the s17 scan blocks.
  parse_losses (2026-11-06) 9 КБРС pieces the step-01 parser dropped, put back from the «clean» text;
             14 repairs of text lost or garbled later (step 1 cut a host's own gloss with its hyphen word's:
             къара «чёрный, тёмный», бет «совесть», сауутлу «вооружённый» …; «<u>~</u>» = ≅); a sense number
             left alone at the end of def1 after step 1 cut a hyphen tail out (6 entries).
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


def voicing2():
    """re-expand «~гъV»/«~гV» (V = ы у и ю) as stem-without-къ/к + suffix, at most as many times as
    the raw texts of the entry's dict-1 sources have such a tilde"""
    q = json.load(open(ROOT / "sources" / "1" / "qmos_def_32499.txt", encoding="utf-8"))
    raw_by_sid = {int(k.rsplit("_", 1)[1]): (kj(k.rsplit("_", 1)[0]), kj(v)) for k, v in q.items()}
    s17 = CK / "shards" / "s17" / "items.jsonl"          # КБРС blocks read from the scan (step 2)
    if s17.exists():
        for l in open(s17, encoding="utf-8"):
            it = json.loads(l)
            raw_by_sid[it["sid"]] = (it["W_print"], kj(it["raw"]))
    es = load()
    rows, skipped = [], []
    for e in es:
        need = Counter()
        for s in e.get("src1") or []:
            if int(s) not in raw_by_sid:
                continue
            word, raw = raw_by_sid[int(s)]
            if "hyphen_restored" in (e.get("flags") or []) and e.get("word1_orig"):
                word = e["word1_orig"]                    # the article cut out of a glued qmos value
            if word.endswith("къ"):
                stem, pat = word[:-2], r"~(гъ[ыуию][а-яёъь]*)"
            elif word.endswith("к"):
                stem, pat = word[:-1], r"~(г[ыуию][а-яёъь]*)"
            else:
                continue
            for m in re.finditer(pat, raw):
                need[(word + m.group(1), stem + m.group(1))] += 1
        for (bad, good), n in need.items():
            rx = re.compile(r"(?<![а-яёА-ЯЁ\-])" + re.escape(bad) + r"(?![а-яё])")
            hits = {f: len(rx.findall(e.get(f) or "")) for f in ("misc1", "def1")}
            if not sum(hits.values()):
                continue
            if sum(hits.values()) > n:
                skipped.append({"entry_id": e["entry_id"], "word": e["word"], "form": bad,
                                "in_text": sum(hits.values()), "tildes": n})
                continue
            for f, k in hits.items():
                if k:
                    e[f] = rx.sub(good, e[f])
            rows.append({"entry_id": e["entry_id"], "word": e["word"], "form": f"{bad}->{good}",
                         "count": sum(hits.values())})
            flag(e, "tilde_voicing_fixed")
            for k in [k for k in list(e) if k.startswith(("misc1_", "misc2_"))]:
                e.pop(k, None)
    save(es)
    log("voicing2", rows + [dict(r, skipped=True) for r in skipped])
    print(json.dumps({"replacements": sum(r["count"] for r in rows), "entries": len({r["entry_id"] for r in rows}),
                      "skipped": skipped}, ensure_ascii=False))


# (field, anchor, piece, where): a КБРС piece the step-01 parser dropped (it is in the «clean» text of
# 01_dict1_preparsed, not in 01_dict1_parsed), put back next to the text it follows («after») or precedes
# («before») in the source. The anchor is unique in the corpus, so the entry is found whatever its number
# or id after later steps. Found by comparing the two texts of every record (2026-11-06; the 10th, тона
# «пулемётну тонаргъа разобрать пулемёт», went back with step 3, s18).
PARSE_LOSSES = [
    ("def1", "1) подсказывание", "; суфлирование театр.", "after"),                                  # айтдырыу
    ("misc1", "рысхыны басдырыб турургъа прятать добро; ", "б) перен. держать в тайне; ", "after"),  # басдыр
    ("misc1", "къой бокъ овечий помёт; ", "юй бокъ мусор; ", "after"),                               # бокъ
    ("misc1", "дыб демезге не издать ни звука; ни пикнуть; ", "дыб демей турургъа молчать; ", "after"),  # дыб
    ("misc1", "чего греха таить!; ", "честно говоря!; ", "after"),                                   # джашырыу
    ("misc1", "джорукъ джокълукъ беспорядочность; ", "коммунист джорукъ коммунистическая мораль; ", "after"),
    ("misc1", "тошно на него смотреть; ", "къусарынг келиу тошнота; ", "after"),                     # къус
    ("misc1", "пайгъа къошулургъа войти в пай", "пай взнос паевой взнос; ", "before"),              # пай
    ("misc1", "высказать кому сокровенные мысли; ", "ышаныб къалыучу доверчивый; ", "after"),       # ышан
]
# (word, field, old, new, why): text the corpus lost or garbled on the way, put back as the source has it.
# word = the entry's current word when «old» is not unique in the corpus (a bare «ат.» tag, an empty field).
# Found by the post-apply check of step 3 (2026-11-06) and a sweep of every removal of step 1 (s10_hyphen)
# that also took the host's own text: s10 cut the gloss of a hyphen word out of its host with replace(…, 1),
# and where the host's own sense had the same words, the host's sense went (къара «чёрный, тёмный»).
REPAIRS = [
    (None, "def1", "1) 2) вороной (о масти)", "1) чёрный, тёмный 2) вороной (о масти)", "s10: собственное значение къара1"),
    (None, "def1", "иметь отношение к кому-чему; (в форме къара!)", "иметь отношение к кому-чему",
     "s10: помета глоссы «вишь!, ого!», ушедшей в къара-къара, повисла"),
    (None, "misc1", "<u>агъашчы</u>сапожник без сапог", "≅ сапожник без сапог", "S0: подчёркнутая тильда КБРС = знак ≅"),
    (None, "misc1", "<u>кёпюр</u> коломенская верста", "≅ коломенская верста", "S0: подчёркнутая тильда КБРС = знак ≅"),
    (None, "def1", "4) || уклончиво, неопределённо", "4) уклончивый, неопределённый || уклончиво, неопределённо",
     "s10: собственное значение башсыз"),
    (None, "def1", "2) перен., честь ж; стыд", "2) перен. совесть ж, честь ж; стыд", "s10: собственное значение бет"),
    (None, "def1", "бедняга м, ж,; горемыка м, ж", "бедняга м, ж, бедолага м, ж; горемыка м, ж", "s10: часть значения хариб"),
    (None, "def1", "1) таркъ о стуке тук!", "1) подр. таркъ о стуке тук!", "s10: помета таркъ"),
    (None, "def1", "1), верование 2) вера 3) ийман", "1) вера, верование 2) вера",
     "s10: «вера» ушла с ийман-дин, обрывок «3) ийман» — от ийман-ислам"),
    ("ийман", "tags", "ат. дин.", "ат. дин.; мус.", "s10: помета КБРС ийман"),
    ("jаным", "tags", "ат.", "ат.; обращение", "s10: помета КБРС джаным"),
    ("муру", "tags", "ат.", "ат.; балк.", "s10: помета КБРС муру"),
    ("къах", "def1", "", "къах о кашле", "s10: перевод КБРС къах"),
    ("сауутлу", "def1", "", "вооружённый", "s10: перевод КБРС сауутлу"),
]
DANGLING = re.compile(r"\s+\d{1,2}\)\s*$")


def parse_losses():
    """(2026-11-06) put back the КБРС pieces the step-01 parser dropped (PARSE_LOSSES) and the text later
    steps lost or garbled (REPAIRS); drop a sense number left alone at the end of def1 of an entry whose hyphen
    tail step 1 made an entry of its own («… 7) нравы, обычаи; мораль ж 8)», «1) крик 2) 3)»); a number
    closing a reference («(см. тюб 7)») stays"""
    es = load()
    byw = {e["word"]: e for e in es}
    rows = []

    def unique(f, anchor):
        hit = [e for e in es if anchor in (e.get(f) or "")]
        assert len(hit) == 1, (f, anchor, [e["word"] for e in hit][:5])
        return hit[0]

    def touched(e):
        for k in [k for k in list(e) if k.startswith(("misc1_", "misc2_"))]:
            e.pop(k, None)

    for f, anchor, piece, where in PARSE_LOSSES:
        e = unique(f, anchor)
        put = anchor + piece if where == "after" else piece + anchor
        if put in e[f]:
            continue                                       # already back (checked at its place: «честно
        e[f] = e[f].replace(anchor, put, 1)                # говоря!» is in other entries too)
        flag(e, "kbrs_text_restored")
        touched(e)
        rows.append({"entry_id": e["entry_id"], "word": e["word"], "field": f, "restored": piece.strip("; ")})
    for w, f, old, new, why in REPAIRS:
        if w:
            e = byw[w]
            cur = e.get(f) or ""
            if cur == new or (old and new in cur):
                continue
            assert (cur == old) if not old or old == cur else cur.count(old) == 1, (w, f, cur, old)
            e[f] = new if (not old or cur == old) else cur.replace(old, new, 1)
        else:
            if any(new in (e.get(f) or "") for e in es) and not any(old in (e.get(f) or "") for e in es):
                continue
            e = unique(f, old)
            e[f] = e[f].replace(old, new, 1)
        flag(e, "kbrs_text_restored")
        touched(e)
        rows.append({"entry_id": e["entry_id"], "word": e["word"], "field": f, "old": old, "new": new, "why": why})
    for e in es:
        # only where step 1 cut a hyphen tail out of the entry («джорукъ … 8) -джол» -> джорукъ-джол): the
        # number was the tail's.  КБРС «2): таза къанлылыкъ …» (a sense shown by its examples alone, which
        # are in misc1) keeps its number — къанлылыкъ, къысыкълыкъ, кёчер
        if "hyphen_detached" not in (e.get("flags") or []):
            continue
        d = e.get("def1") or ""
        new = d
        while DANGLING.search(new):
            cand = DANGLING.sub("", new)
            bare = re.sub(r"\d{1,2}\)|(?<![а-яё])[а-е]\)", "", cand)    # sense numbers / letters have no «(»
            if bare.count("(") != bare.count(")"):          # «(см. тюб 7)»: the number closes a reference
                break
            new = cand
        if new != d:
            e["def1"] = new
            rows.append({"entry_id": e["entry_id"], "word": e["word"], "field": "def1",
                         "dangling_number": d[len(new):].strip()})
    save(es)
    log("parse_losses", rows)
    print(json.dumps({"restored": sum(1 for r in rows if "restored" in r), "repaired": sum(1 for r in rows if "why" in r),
                      "dangling_numbers": sum(1 for r in rows if "dangling_number" in r)}, ensure_ascii=False))


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
    ap.add_argument("phase", choices=["word2orig", "et2", "voicing", "voicing2", "parse_losses", "flags"])
    a = ap.parse_args()
    {"word2orig": word2orig, "et2": et2, "voicing": voicing, "voicing2": voicing2, "parse_losses": parse_losses,
     "flags": flags}[a.phase]()
