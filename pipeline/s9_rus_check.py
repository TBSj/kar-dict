# -*- coding: utf-8 -*-
"""S9a: cross-check the Russian->KB dictionary (sources/5) against the corpus.

dict_2 translations are KB text outside <strong>/<em> tags. We extract
citation-form candidates, fold orthography (кь/гь -> къ/гъ, дж/ж -> j,
infinitive -> stem) and match against 07_final.jsonl headwords.

Outputs:
  checkpoints/qa/s9_rus_check.md
  checkpoints/review_queues/rus_missing_words.jsonl
  checkpoints/review_queues/rus_spelling_variants.jsonl
"""
import json, re, sys, io
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
SRC = ROOT / "sources" / "5" / "rus_kb_dict_33040.txt"

RE_TAG_SPAN = re.compile(r"<(strong|em)>.*?</\1>", re.S)
RE_TAG = re.compile(r"</?[a-z]+>")
RE_TOKEN = re.compile(r"[а-яё]+(?:-[а-яё]+)*")
RE_NUM = re.compile(r"^\d+[.)]?$")

# Russian morphology fragments / function words that survive tag stripping
STOP = {
    "ая", "ое", "ее", "ый", "ий", "ой", "яя", "ья", "ье", "ие", "ых", "их",
    "ого", "его", "ся", "то", "не", "или", "см", "тж", "мн", "ед", "др",
    "знач", "сущ", "прил", "гл", "нареч", "разг", "сов", "несов", "перен",
    "кого", "что", "чего", "чему", "чем", "ком", "кто", "также", "чаще",
    # русские пометы, оказавшиеся вне <em>
    "женск", "напр", "уст", "устар", "неопр", "безл", "прям", "скл", "вр",
    "буд", "наст", "прош", "повел", "кратк", "книжн", "обл", "спец", "тех",
    "поэт", "фольк", "этн", "рел", "бран", "ласк", "шутл", "ирон", "презр",
    "пренебр", "миф", "бот", "зоол", "анат", "астр", "биол", "геогр", "геол",
    "физ", "хим", "мат", "полит", "юр", "экон", "грам", "лингв", "муз",
    "спорт", "театр", "воен", "мед", "прич", "дееприч", "собир", "вводн",
    "числ", "мест", "межд", "союз", "частица", "предлог", "балк", "карач",
    "многокр", "однокр", "возвр", "взаимн", "страд", "понуд",
    "нескл", "прост", "разн", "сказ", "крат", "вопр", "усил", "отриц",
    "накл", "твор", "уменьш", "сравнит", "посл", "филос", "превосх",
    "изъяв", "сослагат", "деепр", "офиц", "дип", "горн", "стр", "информ",
    # русские частотные утечки и обрывки переносов
    "нибудь", "либо", "кое", "меня", "тебя", "себя", "него", "чтобы", "если",
    "времени", "работу", "лась", "лись", "гъан", "ргъа", "рге",
    "день", "прийти", "помещение", "физиол", "взнач", "относ",
}
RUS_GOV = {"кого", "кому", "кем", "чем", "что", "чему", "чего", "ком", "чём"}
KB_MARK = ("къ", "гъ", "j", "нг")


def rus_leak(t: str) -> bool:
    """Russian text leaked into the plain zone: -ся reflexives, -ть infinitives."""
    return (t.endswith("ся") or t.endswith("ть")) and not any(m in t for m in KB_MARK)

# КБ словоизменительные аффиксы (для отсечения словоформ известных слов)
SUFF = sorted([
    "ла", "ле",                                      # мн. число
    "ны", "ни", "ну", "ню", "гъа", "ге", "нга", "нге", "на", "не", "а", "е",
    "да", "де", "дан", "ден", "тан", "тен",           # падежи (с ассимиляцией)
    "ым", "им", "ум", "юм", "ынг", "инг", "унг", "юнг",
    "ын", "ин", "ун", "юн", "ха", "хе",
    "сы", "си", "су", "сю", "ы", "и", "у", "ю",       # притяж.
    "ыбыз", "ибиз", "убуз", "юбюз", "ыгъыз", "игиз",
    "ыб", "иб", "уб", "юб", "б", "й",                 # дееприч.
    "гъан", "ген", "хан", "нган", "ннган", "ннген",
    "гъанлай", "генлей", "ханлай",                    # прич.
    "ады", "еди", "йды", "йди", "йду", "йдю",
    "ды", "ди", "ду", "дю", "дыла", "диле",           # финитн.
    "ар", "ер", "ыр", "ир", "ур", "юр", "р",          # буд. прич.
    "ма", "ме", "май", "мей", "маз", "мез",           # отриц.
    "са", "се", "санг", "сенг", "сакъ", "сек",        # услов.
    "мы", "ми", "му", "мю", "йыкъ", "йик",            # вопрос., гортатив
    "гъыз", "гиз", "гъуз", "гюз", "угъуз", "югюз",    # императив мн.
    "ча", "че",                                       # экватив
    "ыракъ", "ирек", "уракъ", "юрек", "ракъ", "рек",  # компаратив
    "гъынчы", "гинчи", "гюнчю", "гъунчу",             # «пока не»
    "ал", "ел",                                       # возможностн.
    "лыкъ", "лик", "лукъ", "люк",
    "дагъы", "деги", "гъы", "ги",
], key=len, reverse=True)

# чередование конечного согласного основы при аффиксации: джюрек -> джюрег+и
MUT = [("г", "к"), ("гъ", "къ"), ("б", "п")]


def base_fold(w: str) -> str:
    return w.replace("кь", "къ").replace("гь", "гъ")


def variants(w: str):
    b = base_fold(w)
    j1 = b.replace("дж", "j")
    return {b, j1, j1.replace("ж", "j")}


def inf_stems(w: str):
    """бёлерге -> бёле, бёл; айтыргъа -> айты, айт"""
    out = set()
    if w.endswith("ргъа"):
        s1 = w[:-4]
    elif w.endswith("рге"):
        s1 = w[:-3]
    else:
        return out
    if len(s1) >= 2:
        out.add(s1)
        if s1[-1] in "аеёиоуыюя" and len(s1) >= 3:
            out.add(s1[:-1])
    return out


def all_forms(w: str):
    out = set()
    for v in variants(w):
        out.add(v)
        out.update(inf_stems(v))
    return out


def norm_head(w: str) -> str:
    return re.sub(r"\d+$", "", w.replace("­", "").strip().lower())


def main():
    entries = [json.loads(l) for l in open(CK / "07_final.jsonl", encoding="utf-8")]
    pool = set()
    for e in entries:
        for k in ("word", "word1_orig", "word2_orig"):
            w = norm_head(e.get(k, "") or "")
            if w:
                pool.add(w)
                pool.update(inf_stems(w))
        for v in e.get("variants") or []:
            w = norm_head(v)
            if w:
                pool.add(w)
    print(f"corpus pool: {len(pool)} forms from {len(entries)} entries")

    rus = json.load(open(SRC, encoding="utf-8"))
    rus_heads = {re.sub(r"_\d+$", "", k).lower() for k in rus}

    def rusish(t):
        """t is a Russian headword or a transparent case form of one."""
        if t in rus_heads:
            return True
        for cut in (1, 2):
            base = t[:-cut]
            if len(base) >= 3:
                for end in ("", "а", "о", "я", "ь", "е", "й", "ый", "ой", "ия"):
                    if base + end in rus_heads:
                        return True
        return False

    # form (j-folded) -> stats
    stat = {}

    def bump(form_j, form_src, kind, key):
        st = stat.setdefault(form_j, {"src": form_src, "cite": 0, "ctx": 0, "sources": []})
        st[kind] += 1
        if len(st["sources"]) < 5 and key not in st["sources"]:
            st["sources"].append(key)

    _strip_memo = {}

    def strip_match(w, depth=3):
        """True if w is an inflected form of a pool word (suffix peeling)."""
        if w in pool:
            return True
        if depth == 0 or len(w) < 3:
            return False
        key = (w, depth)
        if key in _strip_memo:
            return _strip_memo[key]
        res = False
        for s in SUFF:
            if w.endswith(s) and len(w) - len(s) >= 2:
                stem = w[:-len(s)]
                stems = [stem]
                for soft, hard in MUT:
                    if stem.endswith(soft):
                        stems.append(stem[:-len(soft)] + hard)
                if any(strip_match(st, depth - 1) for st in stems):
                    res = True
                    break
        _strip_memo[key] = res
        return res

    n_tok = 0
    n_inflected = 0
    seen_pool = set()
    for key, val in rus.items():
        txt = val.replace("­", "")
        txt = RE_TAG_SPAN.sub(" ; ", txt)
        txt = RE_TAG.sub(" ", txt)
        for seg in re.split(r"[;.]", txt):
            for piece in seg.split(","):
                toks = [t.strip("-") for t in RE_TOKEN.findall(piece.lower())]
                toks = [t for t in toks if len(t) >= 2 and t not in STOP and not RE_NUM.match(t)
                        and not (set(t.split("-")) & (RUS_GOV | {"л"})) and not rus_leak(t)]
                if not toks:
                    continue
                kind = "cite" if len(toks) == 1 else "ctx"
                for t in toks:
                    n_tok += 1
                    forms = all_forms(t)
                    hit = forms & pool
                    if hit:
                        seen_pool.update(hit)
                    elif len(t) < 4:
                        pass  # unmatched shorties are OCR/pometa fragments
                    elif any(strip_match(v) for v in forms):
                        n_inflected += 1
                    else:
                        fj = sorted(variants(t))[-1]  # j-folded representative
                        bump(fj, t, kind, key)

    print(f"tokens: {n_tok}, inflected-of-known dropped: {n_inflected}, "
          f"unique unmatched forms: {len(stat)}")

    # symmetric-deletion index for distance<=1 neighbours
    def deletes(w):
        return {w} | {w[:i] + w[i + 1:] for i in range(len(w))}

    index = defaultdict(set)
    for p in pool:
        if len(p) >= 4:
            for d in deletes(p):
                index[d].add(p)

    def near(w):
        if len(w) < 4:
            return []
        cand = set()
        for d in deletes(w):
            cand |= index.get(d, set())
        out = [c for c in cand if c != w and _ed1(w, c)]
        return sorted(out)[:4]

    def _ed1(a, b):
        if abs(len(a) - len(b)) > 1:
            return False
        if len(a) > len(b):
            a, b = b, a
        i = j = diff = 0
        while i < len(a) and j < len(b):
            if a[i] == b[j]:
                i += 1; j += 1
            else:
                diff += 1
                if diff > 1:
                    return False
                if len(a) == len(b):
                    i += 1; j += 1
                else:
                    j += 1
        return diff + (len(b) - j) <= 1

    missing, variants_q = [], []
    for fj, st in sorted(stat.items(), key=lambda kv: -(kv[1]["cite"] * 3 + kv[1]["ctx"])):
        if st["cite"] == 0 and st["ctx"] < 3:
            continue
        rec = {
            "form": fj, "form_src": st["src"],
            "count_cite": st["cite"], "count_ctx": st["ctx"],
            "kb_marker": any(m in fj for m in KB_MARK) or fj.endswith(("ргъа", "рге")),
            "is_rus_loan": not any(m in st["src"] for m in KB_MARK) and rusish(st["src"]),
            "sources": st["sources"],
        }
        nb = near(fj)
        if nb:
            rec["near"] = nb
            variants_q.append(rec)
        else:
            missing.append(rec)

    order = lambda r: (r["is_rus_loan"], -min(r["count_cite"], 1),
                       -(r["count_cite"] * 3 + r["count_ctx"]))
    missing.sort(key=order)
    variants_q.sort(key=order)

    RQ = CK / "review_queues"
    with open(RQ / "rus_missing_words.jsonl", "w", encoding="utf-8") as f:
        for r in missing:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(RQ / "rus_spelling_variants.jsonl", "w", encoding="utf-8") as f:
        for r in variants_q:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cov = len(seen_pool) / len(pool) * 100
    n_loan = sum(1 for r in missing if r["is_rus_loan"])
    n_kb = sum(1 for r in missing if r["kb_marker"] and not r["is_rus_loan"])
    n_cite = sum(1 for r in missing if r["count_cite"] > 0)

    akyl = [k for k, v in rus.items() if re.search(r"\bакъыл", v.replace("­", "").lower())][:10]

    qa = CK / "qa" / "s9_rus_check.md"
    with open(qa, "w", encoding="utf-8") as f:
        f.write("# S9a: сверка русско-КБ словаря (33 040 статей) с корпусом\n\n")
        f.write(f"- токенов КБ-текста извлечено: {n_tok:,}\n")
        f.write(f"- словоформ известных слов отсечено аффикс-стриппингом: {n_inflected:,}\n")
        f.write(f"- покрытие корпуса переводами: {len(seen_pool):,}/{len(pool):,} форм ({cov:.1f}%)\n")
        f.write(f"- непокрытых кандидатов (порог: цитатная форма либо >=3 употр.): {len(missing) + len(variants_q):,}\n")
        f.write(f"  - с соседом в корпусе (дистанция 1) -> rus_spelling_variants.jsonl: {len(variants_q):,}\n")
        f.write(f"  - без соседа -> rus_missing_words.jsonl: {len(missing):,}\n")
        f.write(f"    - из них цитатных: {n_cite:,}; русизмов: {n_loan:,}; с КБ-маркерами (къ/гъ/j/нг/-ргъа): {n_kb:,}\n\n")
        f.write("## Топ-40 пропущенных (без соседа)\n\n")
        f.write("| форма | src | cite | ctx | КБ-маркер | русизм | источники |\n|---|---|---|---|---|---|---|\n")
        for r in missing[:40]:
            f.write(f"| {r['form']} | {r['form_src']} | {r['count_cite']} | {r['count_ctx']} | "
                    f"{'+' if r['kb_marker'] else ''} | {'+' if r['is_rus_loan'] else ''} | "
                    f"{', '.join(r['sources'][:3])} |\n")
        f.write("\n## Топ-25 вариантов написания (дистанция 1 от корпуса)\n\n")
        f.write("| форма | сосед(и) в корпусе | cite | ctx | источники |\n|---|---|---|---|---|\n")
        for r in variants_q[:25]:
            f.write(f"| {r['form']} | {', '.join(r['near'])} | {r['count_cite']} | {r['count_ctx']} | "
                    f"{', '.join(r['sources'][:3])} |\n")
        f.write(f"\n## акъыл в переводах\n\nнайден в {len(akyl)}+ статьях: {', '.join(akyl)}\n")
    print(f"missing: {len(missing)}, variants: {len(variants_q)}, coverage {cov:.1f}% -> {qa}")


if __name__ == "__main__":
    main()
