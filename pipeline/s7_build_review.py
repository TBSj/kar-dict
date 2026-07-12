# -*- coding: utf-8 -*-
"""S7f: build review/pilot_review.html — the linguist-facing pilot review page."""
import json, re, sys, io, html
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
OUT = ROOT / "review" / "pilot_review.html"

LEXTAG_RU = {
    "universe_and_nature": "Вселенная и природа", "living_things": "Живые существа",
    "human_body": "Тело и физиология", "mind_and_cognition": "Психика и сознание",
    "emotions_and_will": "Эмоции и воля", "social_relations": "Социальные отношения",
    "culture_and_spirituality": "Культура и духовная жизнь",
    "language_and_communication": "Язык и коммуникация",
    "actions_and_activities": "Деятельность и действия",
    "objects_and_technology": "Предметы и техника",
    "daily_life_and_food": "Быт и питание", "economy_and_society": "Экономика и общество",
    "space_and_time": "Пространство и время",
    "logic_and_function_words": "Служебные элементы",
}

def esc(s):
    return html.escape(s or "", quote=False)

def entry_card(e, note=""):
    word = esc(e["word"])
    tags = esc(e.get("tags") or "")
    rows = []
    for fld, label, cls in [("def1", "def1 · перевод (словарь 1)", "d1"),
                             ("def2", "def2 · русская часть (ТСКБЯ)", "d2"),
                             ("misc1", "misc1", "d1"), ("misc2", "misc2", "d2")]:
        v = e.get(fld) or ""
        if not v:
            continue
        body = esc(v if len(v) < 420 else v[:420] + " …")
        if fld.startswith("misc"):
            rows.append(f'<details class="fld {cls}"><summary>{label}'
                        f'<span class="len">{len(v)} зн.</span></summary><p>{body}</p></details>')
        else:
            rows.append(f'<div class="fld {cls}"><span class="lab">{label}</span><p>{body}</p></div>')
    meta = []
    if e.get("word1_orig"): meta.append(f'сл.1: {esc(e["word1_orig"])}')
    if e.get("word2_orig"): meta.append(f'ТСКБЯ: {esc(e["word2_orig"])}')
    if e.get("lextag"): meta.append(f'lextag: <b>{e["lextag"]}</b>')
    if e.get("flags"): meta.append("флаги: " + ", ".join(e["flags"]))
    notehtml = f'<p class="note">{note}</p>' if note else ""
    return (f'<article class="entry"><h4>{word} <span class="pos">{tags}</span>'
            f'<span class="dictid did-{e["dict_id"]}">{e["dict_id"]}</span></h4>'
            f'{notehtml}{"".join(rows)}<p class="meta">{" · ".join(meta)}</p></article>')

def main():
    es = [json.loads(l) for l in open(CK / "07_final.jsonl", encoding="utf-8")]
    byword = {e["word"]: e for e in es}
    rd = json.load(open(CK / "review_data.json", encoding="utf-8"))
    c = rd["counts"]

    # cards
    taukel = [byword[w] for w in ("таукелсиз1", "таукелсиз2") if w in byword]
    tab = [byword[w] for w in ("таb1", "таb2", "таb3", "таb4", "таb5") if w in byword]
    jx = [byword[w] for w in ("jабагъы", "jабыл", "jалан3") if w in byword]
    tk = [byword[w] for w in ("тарыкъ1", "тарыкъ2") if w in byword]

    flags = Counter()
    for e in es:
        for f in e.get("flags", []): flags[f] += 1

    sub_stats = Counter()
    for e in es:
        for k in e:
            if k.startswith(("misc1_", "misc2_")): sub_stats[k] += 1

    lex_rows = "".join(
        f'<tr><td>{LEXTAG_RU.get(k, k)}</td><td class="mono">{k}</td><td class="num">{v}</td>'
        f'<td class="num">{100*v/c["entries"]:.1f}%</td></tr>'
        for k, v in c["lextag"].items())
    sub_rows = "".join(
        f'<tr><td class="mono">{k}</td><td class="num">{v}</td></tr>'
        for k, v in sub_stats.most_common())
    flag_rows = "".join(
        f'<tr><td class="mono">{k}</td><td class="num">{v}</td></tr>'
        for k, v in flags.most_common())

    cards_taukel = "".join(entry_card(e, "Эталон лингвиста: разметка воспроизведена, включая исправления OCR в цитатах.") for e in taukel)
    cards_tab = "".join(entry_card(e) for e in tab)
    cards_jx = "".join(entry_card(e) for e in jx)
    cards_tk = "".join(entry_card(e, "Коллизия «словарь-1 глагол + ТСКБЯ» разведена цифрами.") for e in tk)

    page = f"""<title>Пилот объединённого карачаево-балкарского словаря</title>
<style>
:root {{
  --bg:#FAFAF7; --ink:#22262D; --mut:#6C7370; --line:#DDDDD4;
  --acc:#1F6E5C; --acc-ink:#14523F; --d1:#39567E; --d2:#1F6E5C; --warn:#A44A3F;
  --card:#FFFFFF; --chip:#EDEFE8;
}}
@media (prefers-color-scheme: dark) {{ :root {{
  --bg:#14181D; --ink:#E6E4DC; --mut:#9AA19C; --line:#2C333A;
  --acc:#4FA98D; --acc-ink:#7CC7AE; --d1:#7D9CC9; --d2:#4FA98D; --warn:#D07A6C;
  --card:#1B2127; --chip:#232B31;
}} }}
:root[data-theme="dark"] {{
  --bg:#14181D; --ink:#E6E4DC; --mut:#9AA19C; --line:#2C333A;
  --acc:#4FA98D; --acc-ink:#7CC7AE; --d1:#7D9CC9; --d2:#4FA98D; --warn:#D07A6C;
  --card:#1B2127; --chip:#232B31;
}}
:root[data-theme="light"] {{
  --bg:#FAFAF7; --ink:#22262D; --mut:#6C7370; --line:#DDDDD4;
  --acc:#1F6E5C; --acc-ink:#14523F; --d1:#39567E; --d2:#1F6E5C; --warn:#A44A3F;
  --card:#FFFFFF; --chip:#EDEFE8;
}}
body {{ background:var(--bg); color:var(--ink); font:16px/1.55 Georgia,'Times New Roman',serif;
  margin:0; padding:0 20px 80px; }}
main {{ max-width:1020px; margin:0 auto; }}
header {{ border-bottom:3px double var(--acc); padding:44px 0 18px; margin-bottom:30px; }}
h1 {{ font-size:1.9rem; margin:0 0 6px; text-wrap:balance; }}
.sub {{ color:var(--mut); font-family:'Segoe UI',system-ui,sans-serif; font-size:.92rem; }}
h2 {{ font-size:1.3rem; margin:44px 0 12px; color:var(--acc-ink); }}
h3 {{ font-size:1.05rem; margin:26px 0 8px; }}
.tiles {{ display:flex; flex-wrap:wrap; gap:10px; font-family:'Segoe UI',system-ui,sans-serif; }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:12px 18px; }}
.tile b {{ display:block; font-size:1.5rem; font-variant-numeric:tabular-nums; color:var(--acc-ink); }}
.tile span {{ font-size:.8rem; color:var(--mut); }}
table {{ border-collapse:collapse; font-family:'Segoe UI',system-ui,sans-serif; font-size:.88rem; width:100%; }}
.twrap {{ overflow-x:auto; }}
th, td {{ text-align:left; padding:5px 12px; border-bottom:1px solid var(--line); }}
th {{ color:var(--mut); font-weight:600; font-size:.78rem; letter-spacing:.04em; text-transform:uppercase; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.mono {{ font-family:Consolas,monospace; font-size:.84rem; }}
.entry {{ background:var(--card); border:1px solid var(--line); border-radius:6px;
  padding:14px 18px; margin:12px 0; }}
.entry h4 {{ margin:0 0 6px; font-size:1.15rem; }}
.entry .pos {{ font-style:italic; font-weight:normal; color:var(--mut); font-size:.95rem; }}
.dictid {{ float:right; font:600 .7rem 'Segoe UI',sans-serif; padding:2px 8px; border-radius:10px;
  background:var(--chip); color:var(--mut); }}
.did-both {{ color:var(--acc-ink); }}
.fld {{ margin:7px 0; border-left:3px solid var(--line); padding-left:12px; }}
.fld.d1 {{ border-left-color:var(--d1); }}
.fld.d2 {{ border-left-color:var(--d2); }}
.fld .lab, .fld summary {{ font:600 .72rem 'Segoe UI',sans-serif; letter-spacing:.05em;
  text-transform:uppercase; color:var(--mut); cursor:default; }}
.fld summary {{ cursor:pointer; }}
.fld summary .len {{ font-weight:400; margin-left:8px; opacity:.7; }}
.fld p {{ margin:3px 0 0; }}
.meta {{ font:italic .82rem Georgia,serif; color:var(--mut); margin:8px 0 0; }}
.note {{ font:.85rem 'Segoe UI',sans-serif; color:var(--acc-ink); margin:4px 0 8px; }}
.qs li {{ margin-bottom:10px; }}
.warn {{ color:var(--warn); font-weight:600; }}
.ok {{ color:var(--acc-ink); font-weight:600; }}
ul {{ padding-left:22px; }}
code {{ font-family:Consolas,monospace; font-size:.85em; background:var(--chip); padding:1px 5px; border-radius:3px; }}
p {{ max-width:72ch; }}
</style>
<main>
<header>
  <h1>Пилот объединённого карачаево-балкарского словаря</h1>
  <p class="sub">Срез: та-* + джаб-/джал-* (словарь 1) и ТА-* + ЖАБ-/ЖАЛ-* (ТСКБЯ) · конвейер S0–S7 · июль 2026</p>
</header>

<section class="tiles">
  <div class="tile"><b>{c["entries"]}</b><span>статей в пилоте</span></div>
  <div class="tile"><b>{c["dict_id"]["both"]}</b><span>слиты из обоих словарей</span></div>
  <div class="tile"><b>{c["dict_id"]["1"]} / {c["dict_id"]["2"]}</b><span>только словарь 1 / только ТСКБЯ</span></div>
  <div class="tile"><b>{c["homonym_words"]}</b><span>омонимических гнёзд (цифры)</span></div>
  <div class="tile"><b>{c["j_words"]}</b><span>слов с латинской j (дж/ж)</span></div>
  <div class="tile"><b>{c["b_words"]}</b><span>слов с латинской b (п/б)</span></div>
  <div class="tile"><b>{c["verb_merged"]}</b><span>глаголов сведено к повелит. форме</span></div>
</section>

<h2>Эталон лингвиста</h2>
{cards_taukel}

<h2>Показательные случаи</h2>
<h3>Гнездо таб/тап — пять омонимов, три слова словаря-1 в одной группе</h3>
{cards_tab}
<h3>Правило J и глаголы</h3>
{cards_jx}
<h3>Разведение коллизий цифрами</h3>
{cards_tk}

<h2>Качество по этапам</h2>
<div class="twrap"><table>
<tr><th>Этап</th><th>Метод</th><th>Контроль</th><th>Результат</th></tr>
<tr><td>S0 разбор словаря 1</td><td>детерминир. + Sonnet (24 батча)</td><td>пословная сохранность текста</td><td class="ok">99,6 % средняя полнота, 0 потерянных статей</td></tr>
<tr><td>S1 извлечение ТСКБЯ</td><td>PyMuPDF, детерминир.</td><td>алфавитная непрерывность, счёт статей</td><td class="ok">25 875 статей на весь корпус; ~37 потерянных заголовков (очередь)</td></tr>
<tr><td>S2 разбор ТСКБЯ + правка OCR</td><td>Sonnet (81 батч)</td><td>4-граммная сохранность, регресс-тест</td><td class="ok">эталон «таукелсиз» пройден; 94 % сходства (разница = правки OCR)</td></tr>
<tr><td>S3 нормализация и сцепка</td><td>детерминир. + Sonnet/Opus</td><td>двойное мнение по глаголам</td><td class="ok">51/51 совпадение Sonnet и Opus; POS-фильтр после аудита</td></tr>
<tr><td>S4 слияние омонимов</td><td>Opus (высокое усилие)</td><td>учёт всех статей, флаги</td><td class="ok">1 404 статьи, 0 потерь; 60 семантических разделений def1</td></tr>
<tr><td>S5 lextag</td><td>Sonnet → наследование по семье → Opus</td><td>согласованность гнёзд</td><td class="ok">101 статья осталась с низкой уверенностью (7 %)</td></tr>
<tr><td>S7 финальный аудит</td><td>Fable, 36 статей против сканов</td><td>визуальная сверка с PDF</td><td>23 ok · 9 minor · <span class="warn">4 major — все исправлены</span></td></tr>
</table></div>

<h2>Аудит Fable: что нашли и что исправлено</h2>
<ul>
<li><span class="warn">major</span> — «гиперкоррекция» OCR в двух цитатах (тал2: «билеклерим талмадыла» было искажено с инверсией смысла; jалкъа: остался мусор «kumhuV»). <b>Исправлено точечно по сканам.</b> Для полного прогона добавим правило: правки внутри цитат — только при полной уверенности.</li>
<li><span class="warn">major</span> — два слова словаря-1 без пары (джабдырыу, джаланлатмакълыкъ) не получили латинскую j, хотя их основа в словаре есть с j. <b>Исправлено системно: 51 слово получило j по семейному правилу, очередь ручной проверки сократилась со 129 до 82.</b></li>
<li>minor (9) — единичные буквенные расхождения в цитатах, потерянный индекс омонима, спорные lextag. <b>Все исправлены точечно.</b></li>
</ul>

<h2>Распределение lextag</h2>
<div class="twrap"><table>
<tr><th>Категория</th><th>метка</th><th>статей</th><th>доля</th></tr>
{lex_rows}
</table></div>

<h3>Открытые вопросы политики классификации — нужно решение лингвиста</h3>
<ol class="qs">
<li><b>Нагота и раздетость</b> (jалан «голый» и семья) — сейчас <code>human_body</code>. Альтернатива: <code>daily_life_and_food</code> (одежда).</li>
<li><b>Текстуры и свойства поверхностей</b> (липкий, скользкий) — сейчас <code>universe_and_nature</code>; отдельной категории для физических свойств нет.</li>
<li><b>Оценочные качества</b> (таб «удобный», тамамлы «основательный») — сейчас <code>culture_and_spirituality</code> (оценка); можно завести иное правило.</li>
</ol>

<h2>Структура misc: таксономия и типизированные подполя</h2>
<p>Исследование по 120 стратифицированным статьям выявило 11 типов содержимого в misc1 и 13 в misc2
(отчёт: <code>checkpoints/qa/s6_misc_taxonomy.md</code>). Ниже — сколько статей получили
автоматически извлечённые подполя (misc1/misc2 при этом сохранены целиком):</p>
<div class="twrap"><table>
<tr><th>Подполе</th><th>статей</th></tr>
{sub_rows}
</table></div>
<p>Два типа надёжно не извлекаются регулярными выражениями и потребуют LLM на полном прогоне:
граница «КБ-текст ↔ русский перевод» внутри обычных примеров misc1 и различение «◊ фразема» от «◊ цитата».</p>

<h2>Флаги статей</h2>
<div class="twrap"><table>
<tr><th>Флаг</th><th>статей</th></tr>
{flag_rows}
</table></div>
<p><code>no_russian_def</code> — норма для производных статей ТСКБЯ (толкование только по-карачаево-балкарски);
реальная очередь ручного просмотра — <code>needs_review</code> и <code>split_unclear</code>.</p>

<h2>Очереди на ручную проверку</h2>
<ul>
<li><b>82</b> исконных слова на ж-/дж- без пары во втором словаре — <code>checkpoints/review_queues/zh_dzh_unmatched.jsonl</code> (по указанию лингвиста — ручная обработка; заимствования исключены автоматически).</li>
<li><b>50</b> глаголов только из словаря 1 — повелительная форма выведена моделями (Sonnet и Opus дали одинаковые ответы), файл <code>only1_verbs.jsonl</code>.</li>
<li><b>2</b> статьи с отсылками «къ.» внутри def2 (тагъаландыр, свидетель→шагъат) — пограничная политика.</li>
</ul>

<h2>Файлы</h2>
<ul>
<li><code>checkpoints/07_final.jsonl</code> — итог пилота (схема лингвиста + служебные поля и подполя misc)</li>
<li><code>checkpoints/final.csv</code> — то же для Excel</li>
<li><code>checkpoints/qa/</code> — отчёты контроля по этапам, аудит (<code>audit/result_*.json</code>), таксономия misc</li>
<li><code>checkpoints/review_queues/</code> — очереди ручной проверки</li>
</ul>

<h2>Дальше: полный прогон</h2>
<p>Объём: ~29 400 статей словаря 1 + ~25 900 статей ТСКБЯ → ориентировочно 40–45 тыс. статей в объединённом словаре.
Все исправления пилота уже встроены в конвейер (группировка притязаний, POS-фильтр глаголов, семейное правило J,
консервативная правка цитат). Оценка: ~4 500 вызовов агентов, несколько часов фоновой работы.</p>
</main>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"written {OUT} ({len(page)} chars)")

if __name__ == "__main__":
    main()
