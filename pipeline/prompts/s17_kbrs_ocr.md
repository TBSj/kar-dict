# S17 — transcribe pages of the printed КБРС-1989 (Karachay-Balkar–Russian dictionary)

You transcribe dictionary pages from a scan into JSON. Accuracy matters more than speed: this text
goes into a dictionary corpus. Work from the page images only.

**Independence rule.** Do NOT open `sources/`, `checkpoints/` (except writing your output file),
`local/sources_survey/` or any other transcription or dictionary file. Your text is checked against
an older OCR of the same book, so it must come from the images alone.

## Input

For page N (3 digits, e.g. 042) there are 6 pieces at zoom 3.0 in `local/s17_img/`:
`pNNN_L1.png, pNNN_L2.png, pNNN_L3.png` (left column, top → bottom), then `pNNN_R1.png … pNNN_R3.png`
(right column). Neighbouring pieces of one column overlap by 2–3 lines: transcribe each line once.
Skip the running head (capital letters at the top, e.g. «АКТ», «АКЪГЪ») and the page number at the bottom.

To look closer at a doubtful spot, render it at zoom 5 (coordinates are fractions of the page;
left column x 0–0.515, right column x 0.485–1; pieces 1/2/3 cover y 0.04–0.37 / 0.34–0.67 / 0.64–0.975):

    python local/sources_survey/tmp/v26/vclip.py <page> <x0> <y0> <x1> <y1> 5 local/s17_img/zoom/<name>.png

then Read the PNG. (Create `local/s17_img/zoom/` if missing.)

## Book layout

- An article starts with the **bold headword** at the beginning of a line. It may be followed by a
  homonym number in Roman numerals (**акъ I**, **акъ II**) and by a declension hint in parentheses
  (**акъыллыкъ (-гъы)**, **мал (-ны)**).
- Inside the article the headword is replaced by a tilde `~` (often with an ending glued: `~ы`, `~гъа`).
- Karachay-Balkar text is bold; Russian translations are regular; labels are italic
  (*отвлеч. к*, *понуд. к*, *и. д. к*, *загадка*, *погов.*, *разг.*, *карач.*, *балк.*, *см.*, *то же, что*).
- Meanings: `1)`, `2)` …; sub-meanings `а)`, `б)`; grammatical parts `1.`, `2.`; `||` and `◊` are book signs.
- 1989 orthography: **ў** (акъылланыў), **нъ** (тенъиз), **къ**, **гъ**. Keep them as printed.

## Scan traps (decide by the word — you know Karachay-Balkar and Russian)

- In the bold font **и** and **н** look almost the same: «бнйче» = **бийче**, «тншле» = **тишле**,
  «джыккырда» may be **джыккырда**. Choose the real word.
- **ъ / ь** and **ы / ь** are easily confused; Karachay-Balkar writes **къ, гъ** (never «кь, гь»).
- Lines broken with a hyphen at the line end: join the word (бы-|шлакъла → бышлакъла), but keep real
  hyphens of compound words (**акъгъан-букъгъан**, **акъ-къара**).
- Russian stress marks (á, é …) are NOT transcribed: write плохой, not плохóй. Keep **ё**.

## Output

Write one file per page: `checkpoints/shards/s17/ocr/pNNN.json` (create the folder if missing;
if the file already exists, skip that page — it was done before):

```json
{"page": 42,
 "entries": [
  {"col": "L", "cont": true,  "head": "", "hom": "", "decl": "", "text": "…end of an article from the previous page…", "doubt": []},
  {"col": "L", "cont": false, "head": "акъбет", "hom": "", "decl": "", "text": "белолицый; ~ къыз белолицая девушка", "doubt": []},
  {"col": "R", "cont": false, "head": "акъ", "hom": "II", "decl": "-гъы", "text": "1) молочные продукты, молочное; ~ ашарыкъ …", "doubt": ["…"]}
 ]}
```

- **Transcribe the whole page**, every article on it, in reading order (left column, then right).
- `cont: true` only for a piece at the very top of a column that continues an article from the
  previous column/page (no headword at its start). Its `head` is empty.
- `head`: headword as printed, lowercase, without the Roman numeral and without the parenthesised hint.
- `hom`: Roman numeral or "". `decl`: the hint inside the parentheses right after the headword, e.g. "-гъы", or "".
- `text`: everything after headword/hom/decl up to the next article, as ONE line, exact wording and
  punctuation, `~` kept, no markdown (no `*`, `**`), labels as plain words.
- Doubtful reading: put `[?]` right after the word in `text` and add a short note to `doubt`
  (e.g. `"акъбет: сыйлы or сыйлы[?] — blurred"`). Use zoom 5 before giving up.

Final reply: per page — number of entries and of doubts, nothing else. Do not paste the transcription.
