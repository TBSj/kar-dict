# -*- coding: utf-8 -*-
"""S15: workbook for the linguist — what the S10–S14 repairs changed («было → стало»).

  review_queues/repair_review.xlsx
    Инструкция               what was done, why, what to check; questions
    1_Дефисные_слова          every restored split headword: as printed, as now in the corpus, what happened
    2_Хозяева_было_стало      cards that had swallowed a split word: def1/misc1 before -> after
    3_Опечатки_псевдоключи    misprints of КБРС, OCR-garbled keys, article tails filed under a wrong key
    4_ТСКБЯ_пропуск           entries from the 14 ТСКБЯ pages that were never extracted
    5_Знаки_ромб              how ◊ / ▯ / ▭ / ○ were restored + examples
    6_Прочее                  word2_orig, ёт2, tilde voicing, no_russian_def, S9 queue status
Yellow column «ВЕРДИКТ»: empty = agree.  manual_review_2.xlsx is NOT touched.
"""
import json, re, sys, io, random
from pathlib import Path
from collections import Counter, defaultdict
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
QA = CK / "qa"
YEL = PatternFill("solid", start_color="FFF3B0")
HDR = Font(bold=True)


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")] if Path(p).exists() else []


def short(s, n=260):
    s = s or ""
    return s if len(s) <= n else s[:n] + "…"


def sheet(wb, title, header, rows, widths, verdict=True):
    ws = wb.create_sheet(title)
    ws.append(header + (["ВЕРДИКТ"] if verdict else []))
    for c in ws[1]:
        c.font = HDR
    for r in rows:
        ws.append(list(r) + ([""] if verdict else []))
    for i, w in enumerate(widths + ([28] if verdict else [])):
        ws.column_dimensions[chr(65 + i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if verdict:
            row[-1].fill = YEL
    ws.freeze_panes = "B2"
    return ws


def main():
    es = jl(CK / "06_lextagged.jsonl")
    byid = {e["entry_id"]: e for e in es}
    bysrc1 = defaultdict(list)
    for e in es:
        for s in e.get("src1") or []:
            bysrc1[int(s)].append(e)
    plan = json.load(open(CK / "shards" / "s10" / "plan.json", encoding="utf-8"))
    changes = {c["entry_id"]: c for c in jl(QA / "s10_changes.jsonl")}
    wb = Workbook()
    ws = wb.active
    ws.title = "Инструкция"
    restored = plan["restored"]
    n_new = sum(1 for r in restored if any(e["dict_id"] == "1" for e in bysrc1.get(r["sid"], [])))
    n_both = sum(1 for r in restored if any(e["dict_id"] == "both" for e in bysrc1.get(r["sid"], [])))
    mk = {"changes": Counter()}
    for fn in ("s11_markers_report.pass1.json", "s11_markers_report.json"):
        if (QA / fn).exists():
            mk["changes"].update(json.load(open(QA / fn, encoding="utf-8"))["changes"])
    lines = [
        ("Починка корпуса по итогам обзора словарей (шаги 1 и 1б), ноябрь 2026",),
        ("",),
        ("Жёлтая колонка «ВЕРДИКТ»: пусто = согласен; иначе — коротко, что не так. Файл сохраните как repair_review_ab.xlsx.",),
        ("Книга manual_review_2.xlsx НЕ менялась. Её лист «7_Фраземы_ромб» составлен до починки знаков: примерно 2/3 его примеров на деле — начала цитат (см. лист 5).",),
        ("",),
        ("1. Дефисные слова КБРС (лист 1, лист 2).",),
        ("   Выгрузка словаря 1 резала заглавные слова по дефису: ключ «эт», текст «-джен родственник(и)». По правилу самого КБРС (с. 11, п. 1: «Каждое слово (в том числе и сложное слово, пишущееся через дефис) … образует самостоятельную словарную статью») они восстановлены отдельными статьями.",),
        (f"   Восстановлено {len(restored)} слов: {n_both} слились со статьями ТСКБЯ в общие статьи, {n_new} — новые статьи только из словаря 1. Ложные омонимы (ат5–ат10, тёшек2, jер5–7…) и чужие переводы внутри статей убраны.",),
        ("   Форма заглавного слова — по правилам корпуса: глаголы основой (jалын-jалбар), дж в начале части → j, при слиянии с ТСКБЯ ж/дж → j (ашау-jашау).",),
        ("2. Опечатки КБРС, искажённые ключи, хвосты статей (лист 3). Проверено по скану печатного КБРС; исправленная форма поставлена в заглавное слово, напечатанная — в журнал.",),
        ("3. Пропущенные страницы ТСКБЯ (лист 4): т. 2 и т. 3, PDF-с. 11–17 (ЗАВА…ЗАКОНСУЗ, САБА…САБЫРЛАНДЫРЫУ) не извлекались никогда; теперь разобраны и слиты со статьями словаря 1.",),
        ("4. Знаки ◊ ▯ ▭ ○ (лист 5). Раньше ◊ стоял на месте разных печатных знаков ТСКБЯ. Теперь по легенде каждого тома:",),
        (f"   ◊ — фразеологизм (≈1 000 вместо ≈5 900); ▯ — составное слово; ▭ — начало цитат после словосочетаний; ○ — начало цитат после пословицы «(Нарт сёз)». Замен всего: {sum(mk['changes'].values())}.",),
        ("   Внимание: легенды томов различаются (т.1: ❑ составные / ▼ фразеологизмы; т.2: ❒ / ◊; т.3: ■ / ♦), в тексте т.2–3 составные слова отмечены залитым квадратом ■.",),
        ("5. Прочее (лист 6): word2_orig у статей, выделенных из одной записи ТСКБЯ; ёт2 — опечатка ТСКБЯ «ат.» у глагола; тильда с озвончением (хапчюгю вместо хапчюкю); флаг no_russian_def теперь означает «нет ни def1, ни def2»; статус очереди S9 после починки.",),
        ("",),
        ("Вопросы:",),
        ("В1. Опечатки КБРС (хыппа-харха → хыппа-хырха, харттылы-мырттылы → хырттылы-мырттылы, аталыкъ-аналыкъ, сеп-семиз, ажымла, атылышыу, джангызлыкъ, сымарлат, хурттаклыкъ, хыртламакълыкъ, чарпыулу): согласны с исправленными формами?",),
        ("В2. В т.2–3 залитый квадрат ■ отмечает составные слова, а не фразеологизмы — они теперь под ▯. Устраивает, что «фразеологизм» в корпусе = только ◊ (печатные ▼/♦)?",),
        ("В3. эт-джен: КБРС «родственник(и)» и ТСКБЯ «тело, организм» стоят теперь в одной статье эт-jен. Разделить на омонимы?",),
    ]
    for l in lines:
        ws.append(l)
    ws.column_dimensions["A"].width = 160

    # 1. restored hyphen words
    rows = []
    for r in sorted(restored, key=lambda r: r["sid"]):
        ents = bysrc1.get(r["sid"], [])
        for e in ents or [None]:
            if e is None:
                rows.append((r["sid"], r["W_print"], "—", "НЕ НАЙДЕНО", "", "", r.get("item_note", "")))
                continue
            how = ("новая статья (только словарь 1)" if e["dict_id"] == "1" else
                   "слита со статьёй ТСКБЯ" if "hyphen_restored" in e.get("flags", []) else "группа")
            note = r.get("item_note", "")
            if "source_typo_fixed" in e.get("flags", []):
                note = ("ОПЕЧАТКА/ОШИБКА ВЫГРУЗКИ ИСПРАВЛЕНА. " + note).strip()
            rows.append((r["sid"], r["W_print"], e["word"], how, short(e.get("def1"), 200), short(e.get("def2"), 120), note))
    sheet(wb, "1_Дефисные_слова", ["seqid КБРС", "как напечатано", "в корпусе", "что сделано", "def1", "def2", "пометка"],
          rows, [10, 26, 26, 24, 50, 40, 40])

    # 2. hosts before -> after
    rows = []
    tails = {r["sid"] for r in restored}
    for eid, c in changes.items():
        b = c.get("before") or {}
        if not b or not (set(int(x) for x in b.get("src1") or []) & tails):
            continue
        if "-" in (b.get("word") or ""):       # already a hyphenated card (linguist-restored), not a host
            continue
        a = c.get("after") or {}
        if c["action"] == "changed" and b.get("def1") == a.get("def1") and b.get("misc1") == a.get("misc1") and b.get("word") == a.get("word"):
            continue
        rows.append((b.get("word"), a.get("word") if a else "УДАЛЕНА (ложный омоним / слита)", c["action"],
                     short(b.get("def1"), 220), short(a.get("def1") if a else "", 220),
                     short(b.get("misc1"), 220), short(a.get("misc1") if a else "", 220)))
    sheet(wb, "2_Хозяева_было_стало", ["было: слово", "стало: слово", "действие", "def1 было", "def1 стало", "misc1 было", "misc1 стало"],
          sorted(rows, key=lambda x: x[0] or ""), [18, 24, 10, 45, 45, 45, 45])

    # 3. misprints / garbled keys / pseudo keys
    rows = []
    for r in restored:
        if r.get("typo_fixed"):
            rows.append(("дефисное слово", r["W_print"], ", ".join(e["word"] for e in bysrc1.get(r["sid"], [])), r.get("item_note", "")))
    for r in jl(QA / "s10_pseudokeys.jsonl"):
        if r.get("status"):
            continue
        if r["verdict"] == "pseudo_tail":
            rows.append(("хвост чужой статьи", f"ключ seqid {r['sid']}", r.get("owner", ""), "перенесён к владельцу: " + short(" ".join(r.get("added", {}).values()), 200)))
        else:
            rows.append(("искажённый ключ" if r["verdict"] == "garbled_key" else "разрезанное слово",
                         r.get("old_print", ""), r.get("merged_into") or r.get("new_base", ""),
                         ("слита со статьёй ТСКБЯ " + r["merged_into"]) if r.get("merged_into") else "переименована"))
    for r in jl(QA / "s10_postfix.jsonl"):
        if not r["fix"].startswith("A"):
            rows.append(("ручная правка", "", "", r["fix"]))
    for r in jl(QA / "s13_et2.jsonl"):
        rows.append(("опечатка ТСКБЯ", r["word"], r["word"], r["why"]))
    sheet(wb, "3_Опечатки_псевдоключи", ["вид", "было (печать/выгрузка)", "в корпусе", "что сделано"], rows, [20, 30, 26, 90])

    # 4. recovered ТСКБЯ pages
    rows = []
    for e in es:
        if "gap_fill" in (e.get("flags") or []):
            rows.append((e["word"], e["dict_id"], e.get("tags", ""), short(e.get("def2"), 160), short(e.get("def1"), 160), short(e.get("misc2"), 200)))
    sheet(wb, "4_ТСКБЯ_пропуск", ["слово", "dict_id", "пометы", "def2 (ТСКБЯ)", "def1 (КБРС)", "misc2"], sorted(rows), [22, 8, 14, 45, 45, 60])

    # 5. markers: examples from a direct comparison of misc2 before/after the marker pass
    before_m = {json.loads(l)["entry_id"]: json.loads(l).get("misc2") or "" for l in open(CK / "06_lextagged.pre_s11.jsonl", encoding="utf-8")}
    after_m = {json.loads(l)["entry_id"]: json.loads(l).get("misc2") or "" for l in open(CK / "06_lextagged.pre_s10apply.jsonl", encoding="utf-8")}
    random.seed(5)
    diffs = []
    for eid, m0 in before_m.items():
        m1 = after_m.get(eid)
        if m1 is None or m1 == m0 or len(m1) != len(m0):
            continue
        for i, (x, y) in enumerate(zip(m0, m1)):
            if x != y:
                diffs.append((eid, i, x, y))
    tot = Counter(f"{x}→{y}" for _, _, x, y in diffs)
    rows = [("итог в корпусе", " ".join(f"{ch} {sum((e.get('misc2') or '').count(ch) for e in es)}" for ch in "◊▯▭○"),
             "", "замены: " + ", ".join(f"{k} {v}" for k, v in tot.most_common()), "")]
    for kind in ("◊→▭", "◊→○", "◊→▯", "□→▭", "▯→▭", "▯→◊", "◊→◊"):
        pool = [d for d in diffs if f"{d[2]}→{d[3]}" == kind]
        for eid, i, x, y in random.sample(pool, min(10, len(pool))):
            m1 = after_m[eid]
            w = byid[eid]["word"] if eid in byid else eid
            rows.append((w, f"{x} → {y}", "", short(m1[max(0, i - 70):i], 70), short(m1[i:i + 170], 170)))
    sheet(wb, "5_Знаки_ромб", ["слово", "знак было → стало", "", "текст перед знаком", "текст со знаком"], rows, [18, 16, 4, 45, 90])

    # 6. other
    rows = []
    w2 = jl(QA / "s13_word2orig.jsonl")
    rows.append(("word2_orig", f"исправлено {len(w2)}", "пример: " + "; ".join(f"{r['word']}: {r['old']} → {r['new']}" for r in w2[:6])))
    vo = jl(QA / "s13_voicing.jsonl")
    rows.append(("тильда с озвончением", f"{sum(r['count'] for r in vo)} замен в {len({r['entry_id'] for r in vo})} статьях",
                 "пример: " + "; ".join(f"{r['word']}: {r['form']}" for r in vo[:8])))
    s9 = jl(CK / "review_queues" / "s9_recheck.jsonl")
    c9 = Counter((r["queue"], r["status"]) for r in s9)
    rows.append(("очередь S9 (лист 1–2 manual_review_2)", ", ".join(f"{k[0]}/{k[1]}: {v}" for k, v in sorted(c9.items())),
                 "закрыто починкой: " + "; ".join(f"{r['form']} ({r['why']})" for r in s9 if r["status"] != "still_open")[:900]))
    sheet(wb, "6_Прочее", ["что", "сколько", "подробности"], rows, [30, 40, 120], verdict=False)

    out = CK / "review_queues" / "repair_review.xlsx"
    wb.save(out)
    print("saved", out, {ws.title: ws.max_row - 1 for ws in wb.worksheets})


if __name__ == "__main__":
    main()
