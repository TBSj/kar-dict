# -*- coding: utf-8 -*-
"""S8a: tag facets + derivation links + word-variant links (ROADMAP items 1–3).

Adds fields to 06_lextagged.jsonl (original `tags` stays untouched):
  pos        — часть речи (список)
  dialect    — карач./балк./диал./ц. диал.
  style      — регистр/стилистика (разг., уст., пренебр., фольк. …)
  domain     — предметная область (мед., бот., воен. …)
  gram_note  — грамматические пометы вне деривации (возвр., собир., кёпл. сан. …)
  tags_other — неопознанные сегменты (для доразметки)
  derived            — [{type, base_raw, base}] по реляционным пометам
  derived_from       — заголовок базового слова, если найден в словаре
  variant_of / variants — связи вариантов написания (метатезы/элизии) по «см./тж./къ.»
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

# --- derivational relations (carry the base word) ---
RE_DERIV = re.compile(
    r"(?P<type>и\.\s?д\.|отвлеч\.|понуд\.|страд\.(?:-возвр\.)?|взаимн\.(?:\s?-?\s?совм\.|-возвр\.)?|взаим\.-совм\.|возвр\.|прич\.|кюч\.|усил\.|повел\.|парн\.|нареч\.)"
    r"\s*(?:к|от)\s+"
    r"(?P<base>[а-яёА-ЯЁjJb][а-яёъ\-]*(?:\s?[а-яёъ\-]+)?)"
    r"\s*(?P<hom>\d+|[IVX]+)?", re.U)
NOISE = {"к", "от", ".", "д.", "и.", "къ.", "сёз.", "жюр."}

MULTI = ["сёл. тил.", "хал. сёзл.", "аз жюр.", "в разн. знач.", "ц. диал.",
         "кёпл. сан.", "эрикл. сёз.", "мод. сёз.", "заман. сёзл.", "орун. сёзл.",
         "санчы сан.", "тизг. сан.", "къауум. сан.", "къауум. ат.", "мард. сёзл.",
         "сомгъа сан.", "юлюш. сан.", "нёгер. сёзл.", "себеп. сёзл."]

FACETS = {
    "pos": {"ат.": "сущ.", "эт.": "глаг.", "сыф.": "прил.", "хал. сёзл.": "нареч.",
            "межд.": "межд.", "междом.": "межд.", "кес.": "частица", "байл.": "союз",
            "сонг.": "послелог", "алм.": "мест.", "сан.": "числ.", "числ.": "числ.",
            "санчы сан.": "числ. колич.", "тизг. сан.": "числ. порядк.",
            "къауум. сан.": "числ. собир.", "сомгъа сан.": "числ.", "юлюш. сан.": "числ. дробн.",
            "мард. сёзл.": "нареч. меры", "заман. сёзл.": "нареч. времени",
            "орун. сёзл.": "нареч. места", "нёгер. сёзл.": "нареч.", "себеп. сёзл.": "нареч. причины",
            "эрикл. сёз.": "подражат.", "подр.": "подражат.", "мод. сёз.": "модальн.",
            "къауум. ат.": "сущ. собир.", "этимча": "дееприч.", "сёзл.": "нареч."},
    "dialect": {"карач.": "карач.", "къарач.": "карач.", "балк.": "балк.", "малкъ.": "балк.",
                "диал.": "диал.", "ц. диал.": "ц. диал."},
    "style": {"сёл. тил.": "разг.", "разг.": "разг.", "уст.": "уст.", "эск.": "уст.",
              "редко": "редко", "аз жюр.": "малоупотр.", "пренебр.": "пренебр.",
              "дет.": "дет.", "фольк.": "фольк.", "поэт.": "поэт.", "шутл.": "шутл.",
              "груб.": "груб.", "ласк.": "ласк.", "ирон.": "ирон.", "высок.": "высок.",
              "прост.": "прост.", "книжн.": "книжн.", "эвф.": "эвф.", "бран.": "бран.",
              "перен.": "перен.", "прям.": "прям.", "кёч.": "перен.", "в разн. знач.": "в разн. знач.",
              "нейтр.": "нейтр.", "презр.": "презр.", "неодобр.": "неодобр."},
    "domain": {"мед.": "мед.", "бот.": "бот.", "муз.": "муз.", "ист.": "ист.", "тех.": "тех.",
               "лингв.": "лингв.", "грам.": "грам.", "грамм.": "грам.", "мус.": "рел.",
               "дин.": "рел.", "рел.": "рел.", "воен.": "воен.", "мат.": "мат.", "хим.": "хим.",
               "текст.": "текст.", "зоол.": "зоол.", "лит.": "лит.", "спорт.": "спорт.",
               "физ.": "физ.", "анат.": "анат.", "с.-х.": "с.-х.", "этн.": "этн.",
               "полит.": "полит.", "юр.": "юр.", "биол.": "биол.", "геогр.": "геогр.",
               "астр.": "астр.", "экон.": "экон.", "эк.": "экон.", "фарм.": "фарм.",
               "кул.": "кул.", "охот.": "охот.", "карт.": "карт.", "шахм.": "шахм.",
               "театр.": "театр.", "мор.": "мор.", "стр.": "стр.", "горн.": "горн.",
               "эл.": "эл.", "радио.": "радио", "тип.": "тип.", "миф.": "миф.",
               "фин.": "фин.", "пед.": "пед.", "мифол.": "миф.", "церк.": "рел.",
               "филос.": "филос.", "геол.": "геол.", "метео.": "метео", "авиа.": "авиа"},
    "gram_note": {"возвр.": "возвр.", "взаимн.-возвр.": "взаимн.-возвр.", "страд": "страд.",
                  "страд.": "страд.", "взаимн.": "взаимн.", "кёпл. сан.": "мн. ч.",
                  "энчи.": "имя собств.", "собир.": "собир.", "безл.": "безл.",
                  "нескл.": "нескл.", "вводн. сл.": "вводн.", "буйр.": "повел.",
                  "страд.-возвр.": "страд.-возвр.", "совм.": "совм.",
                  "взаимн.совм.": "взаимн.-совм.", "взаим.-совм.": "взаимн.-совм.",
                  "возвр.-": "возвр.", "порядк.": "порядк.", "кёрг.": "указат."},
}
FACETS["style"].update({"сёл.": "разг.", "тил.": "разг.", "сёл.тил.": "разг.", "тил": "разг.",
                        "саб.": "дет.", "аз.": "малоупотр."})
FACETS["domain"].update({"полигр.": "полигр.", "спорт": "спорт.", "спец.": "спец."})
FACETS["pos"].update({"частица": "частица"})

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}


def _spellings(b):
    """a base as printed -> the corpus spellings it can have (дж/ж -> j); verbs also by their stem
    (джарыргъа -> jар: the corpus word of a verb is the imperative stem)"""
    out = [b, b.replace("дж", "j"), ("j" + b[1:]) if b.startswith("ж") else b]
    m = re.match(r"^(.*?)([уы]?ргъа|[юи]?рге)$", b)
    if m:
        s = m.group(1)
        out += [s, s.replace("дж", "j"), ("j" + s[1:]) if s.startswith("ж") else s]
    return list(dict.fromkeys(out))


def resolve_base(base_raw, byword, bybase, byw1o=None):
    """«солу 2» / «чайкъаргъа II» / «терсейирге» -> the corpus word it names.  The number of the reference
    is a corpus number (s18 refs renumbered the books' references after step 3), so it decides first; a КБРС
    headword (infinitive) names the entry that carries it as word1_orig; only then the first homonym"""
    parts = (base_raw or "").split()
    if not parts:
        return None
    b = parts[0].lower()
    num = None
    if len(parts) > 1:
        h = parts[-1]
        num = int(h) if h.isdigit() else ROMAN.get(h)
    if num:
        for c in _spellings(b):
            if f"{c}{num}" in byword:
                return byword[f"{c}{num}"]
    if byw1o is not None:
        ws = byw1o.get(b.replace("ё", "е"))
        if ws and len(ws) == 1:
            return ws[0]
    for c in [parts[0]] + _spellings(b):
        if c in bybase:
            return bybase[c]
        if c in byword:
            return byword[c]
    return None

def main():
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byword, bybase, byw1o = {}, {}, defaultdict(list)
    for e in es:
        byword.setdefault(e["word"].lower(), e["word"])
        bybase.setdefault(re.sub(r"\d+$", "", e["word"]).lower(), e["word"])
        if e.get("word1_orig") and e.get("dict_id") in ("1", "both"):
            byw1o[e["word1_orig"].lower().replace("ё", "е")].append(e["word"])

    other_tok = Counter()
    n_deriv = n_res = n_facet = 0
    for e in es:
        t = e.get("tags") or ""
        for k in ("pos", "dialect", "style", "domain", "gram_note", "tags_other",
                  "derived", "derived_from"):
            e.pop(k, None)
        if not t:
            continue
        derived = []
        rest = t
        for m in RE_DERIV.finditer(t):
            typ = re.sub(r"\s+", " ", m.group("type"))
            base = m.group("base").strip()
            derived.append({"type": typ, "base_raw": base + (f" {m.group('hom')}" if m.group("hom") else "")})
            rest = rest.replace(m.group(0), " ")
        facets = defaultdict(list)
        for seg in re.split(r"[;,]", rest):
            seg = seg.strip()
            if not seg:
                continue
            parts, s = [], seg
            for mu in MULTI:
                while mu in s:
                    parts.append(mu)
                    s = s.replace(mu, " ", 1)
            parts += [p for p in s.split() if p.strip()]
            for tokn in parts:
                hit = False
                for facet, mapping in FACETS.items():
                    if tokn in mapping:
                        v = mapping[tokn]
                        if v not in facets[facet]:
                            facets[facet].append(v)
                        hit = True
                        break
                if not hit:
                    if re.fullmatch(r"\d+|[IVX]+", tokn) or tokn in NOISE:
                        continue
                    other_tok[tokn] += 1
                    if tokn not in facets["other"]:
                        facets["other"].append(tokn)
        for facet in ("pos", "dialect", "style", "domain", "gram_note"):
            if facets.get(facet):
                e[facet] = facets[facet]
                n_facet += 1
        if facets.get("other"):
            e["tags_other"] = facets["other"]
        if derived:
            e["derived"] = derived
            n_deriv += 1
            r = resolve_base(derived[0]["base_raw"], byword, bybase, byw1o)
            if r and r != e["word"]:
                e["derived_from"] = r
                n_res += 1

    # ---- variants (см./тж./къ. + high letter similarity) ----
    RE_REF = re.compile(r"(?:см\.|тж\.|къ\.)\s+([а-яёj][а-яёъ\-]+)(?:\s?(\d{1,2})\b)?")
    def sim(a, b):
        if abs(len(a) - len(b)) > 2 or min(len(a), len(b)) < 4:
            return False
        if a.startswith(b) or b.startswith(a):
            return False  # суффиксация/мн. число = словообразование, не вариант
        if sorted(a) == sorted(b):
            return True   # метатеза/анаграмма (ахча/ачха)
        # элизия/одиночная замена: расстояние Левенштейна <= 2 (короткая проверка)
        la, lb = len(a), len(b)
        prev = list(range(lb + 1))
        for i in range(1, la + 1):
            cur = [i] + [0] * lb
            for j in range(1, lb + 1):
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            prev = cur
            if min(prev) > 2:
                return False
        return prev[lb] <= 2
    n_var = 0
    varlist = []
    bywordE = {e["word"]: e for e in es}
    for e in es:
        if e.get("variant_of"):
            e.pop("variant_of")
        if e.get("variants"):
            e.pop("variants")
    for e in es:
        text = " ".join(filter(None, [e.get("def1"), e.get("def2"), e.get("misc2", "")[:200]]))
        m = RE_REF.search(text)
        if not m:
            continue
        tgt_raw = m.group(1).lower()
        tgt = None
        if m.group(2):                                  # «къ. солуу 2»: that homonym
            for c in _spellings(tgt_raw):
                if f"{c}{m.group(2)}" in byword:
                    tgt = byword[f"{c}{m.group(2)}"]
                    break
        for c in (tgt_raw, tgt_raw.replace("дж", "j"),
                  ("j" + tgt_raw[1:]) if tgt_raw.startswith("ж") else tgt_raw):
            if tgt:
                break
            if c in bybase:
                tgt = bybase[c]
                break
        if not tgt or tgt == e["word"]:
            continue
        a = re.sub(r"\d+$", "", e["word"]).lower()
        b = re.sub(r"\d+$", "", tgt).lower()
        if a != b and sim(a, b):
            e["variant_of"] = tgt
            te = bywordE.get(tgt)
            if te is not None:
                te.setdefault("variants", [])
                if e["word"] not in te["variants"]:
                    te["variants"].append(e["word"])
            varlist.append((e["word"], tgt))
            n_var += 1

    # spellings of the 1965 Russian-KB dictionary the linguist linked to our words (s20; no «см.» to read them from)
    for e in es:
        tgt = e.get("variant_of_rkbs")
        if tgt and tgt in bywordE and not e.get("variant_of"):
            e["variant_of"] = tgt
            te = bywordE[tgt]
            te.setdefault("variants", [])
            if e["word"] not in te["variants"]:
                te["variants"].append(e["word"])
            varlist.append((e["word"], tgt))
            n_var += 1

    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(CK / "review_queues" / "variants_detected.jsonl", "w", encoding="utf-8") as f:
        for a, b in varlist:
            f.write(json.dumps({"variant": a, "of": b}, ensure_ascii=False) + "\n")
    json.dump({t: n for t, n in other_tok.most_common()},
              open(CK / "qa" / "s8_unmapped_tags.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps({"faceted_fields": n_facet, "derived": n_deriv, "derived_resolved": n_res,
                      "variants_linked": n_var, "variants_sample": varlist[:15],
                      "unmapped_unique": len(other_tok),
                      "unmapped_top": other_tok.most_common(25)}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
