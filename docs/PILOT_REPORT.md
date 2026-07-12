# Karachay-Balkar Dictionary Merge — Pilot Report & Continuation Guide

*Written 2026-07-11 after completing the pilot run (S0–S7). This document is self-sufficient:
a fresh session should be able to continue the project from here alone.*

---

## 1. Project goal

Merge two Karachay-Balkar dictionaries into one machine-readable lexicon (JSONL + CSV) for
native speakers and learners. **Final quality is critical** — the linguist (Ali) and end users
will work with this data.

Target schema per entry (linguist's spec; extra provenance fields allowed after it):

```json
{"word": "таукелсиз1", "dict_id": "both|1|2", "tags": "сыф.",
 "def1": "русский перевод из словаря 1", "def2": "только русская часть определения словаря 2",
 "misc1": "всё остальное из статьи словаря 1", "misc2": "всё остальное из словаря 2",
 "lextag": "emotions_and_will"}
```

## 2. Sources

| | Dict 1 («однотомник», qmos) | Dict 2 (ТСКБЯ, «трехтомник») |
|---|---|---|
| Path | `sources/1/qmos_def_32499.txt` | `sources/2/ТСКБЯ - {1,2,3}.pdf` |
| Type | КБ→рус переводной словарь | толковый словарь (КБ толкования + рус. переводы) |
| Format | valid JSON `{"word_seqid": "markup"}` | scanned PDF with OCR text layer, two columns |
| Orthography | карачаевская: **дж-**, **-б** finals, verbs = infinitive **-ргъа/-рге** | балкарская: **ж-**, **-п** finals, verbs = imperative sg |
| Size | 32,499 raw → **29,404 after dedup** (3,095 exact OCR duplicates), 28,072 unique headwords, 1,084 homonym groups, 5,129 infinitive verbs | 3,355 pages → **25,875 segmented entries** (vol I=А-Ж 8,245; II=З-Р 7,950; III=С-Я 9,680) |
| Dict 1 markup | `@…#` KB text, `$…%` italic labels, `~` = headword, `\|\|` parallel POS translation, Roman numerals = homonyms, `(-гъы)` declension hints | headword CAPS + homonym numeral (Roman/Arabic) + tag (ат./эт./сыф./хал. сёзл.) + рус. перевод + `/` + КБ толкование + примеры с цитатами + `◊` фразеология + `□/▯` термины + `къ.` отсылки |
| OCR quirks | ргьа↔ргъа, і/ё noise (minor) | Latin homoglyphs («am.»→«ат.»), Ё→Е loss, разрядка «Х у б и й л а н ы», Ш→III/1Е, hyphenation, «◊»→«♦»/«О» |

Facts that make the merge rules work: dict 2 keeps дж-loanwords under its own ДЖ section
(ДЖУНГЛИ vol1 p.669) and ж-loanwords under Ж (ЖУРНАЛ vol1 p.949), so **дж↔ж mismatch across
dicts reliably signals a native word**; identical spelling signals a loanword.

Ground truth: ТАУКЕЛСИЗ I/II (vol 3 p.401) matches the linguist's verified screenshot —
wired in as an automated regression test (`pipeline/s2_qa.py`).

## 3. Linguist's rules → implementation

1. **Ж/ДЖ → J**: matched дж-(d1)↔ж-(d2) ⇒ Latin `j` (lowercase, words are lowercase).
   Same spelling in both ⇒ loanword ⇒ keep. Applied to verbs too (jабыл). *Pilot addition*:
   **family J-propagation** — dict1-only derivatives whose j-family base exists get j as well
   (`pipeline/s7_fixes.py`); truly isolated ж/дж words stay in the manual queue.
2. **Final П/Б → b**: matched -б(d1)↔-п(d2) ⇒ Latin `b` (таб+тап→таb). For verbs, applied when
   the d1 stem candidate ends in б and the d2 imperative in п.
3. **Verbs → imperative sg** (dict 2 form). Infinitive = stem + (epenthetic vowel) + р + гъа/ге.
   ы/и/у/ю before -р- are epenthetic; **а/е may be aorist vowel (таб-ар-гъа) or stem-final
   (тара-р-гъа) — both candidates generated**, plus stem-final гъ→къ/г→к devoicing (тагъаргъа→такъ).
   Matching against dict 2 resolves most; dict1-only verbs adjudicated by LLM
   (Sonnet+Opus double opinion; pilot: 51/51 agreement).
4. **Homonyms**: digit suffix (таукелсиз1/2) assigned **globally over the final word form**
   during S4 finalize, ordered by dict 2 numbering (hom_rank), then dict1-only (rank 90+).
5. **def2 = Russian-only**; the `/` separator in ТСКБЯ articles anchors the split. KB text → misc2.
6. **misc taxonomy** (final step): 11 misc1 + 13 misc2 content types identified;
   14 typed subfields extracted by validated regexes, misc1/misc2 kept intact.

Match-key canonicalization (`pipeline/s3_match.py: canon`): lowercase, ё→е, дж→ж, **б→п
everywhere** (mid-stem табдыр↔ТАПДЫР validated). Verb matching is **POS-filtered**: a d1 verb
may only match a d2 word that has a verb homonym (tags contain «эт» or relational
«понуд/страд/взаимн … от»).

## 4. Pipeline (all code in `pipeline/`, prompts in `pipeline/prompts/`)

| Stage | Script(s) | LLM | Prompt | Checkpoint out |
|---|---|---|---|---|
| S0a dict1 pre-parse | `s0_dict1_preparse.py --slice pilot\|all` | — | — | `01_dict1_preparsed.jsonl`, `shards/s0_in/` |
| S0b dict1 field-split | Workflow fan-out | Sonnet, effort medium | `s0_parse.md` | `shards/s0_out/` |
| S0 QA | `s0_qa.py` | — | — | `qa/s0_qa_report.json` |
| S1 dict2 extract+segment | `s1_dict2_extract.py` (full corpus already done) | — | — | `00_dict2_pages/`, `02_dict2_segmented.jsonl`, `qa/s1_report.json` |
| S2a batching | `s2_make_batches.py --slice pilot\|all` | — | — | `shards/s2_in/` |
| S2b dict2 parse+OCR repair | Workflow fan-out | Sonnet, effort medium | `s2_parse.md` | `shards/s2_out/` |
| S2 QA | `s2_qa.py` (incl. таукелсиз regression) | — | — | `qa/s2_qa_report.json` |
| S3 consolidate+match | `s3_match.py --slice pilot\|all` | — | — | `01_dict1_parsed.jsonl`, `03_dict2_parsed.jsonl`, `04_match_table.jsonl`, `review_queues/` |
| S3b adjudication | Workflow (verbs double-opinion + zh/dzh triage) → `s3b_apply.py` | Sonnet+Opus | `s3b_verbs.md`, `s3b_zhdzh.md` | `shards/s3b_out/`, updated match table |
| S4 merge | `s4_merge.py --prepare` → Workflow → `s4_merge.py --finalize` | Opus, effort high | `s4_merge.md` | `shards/s4_{in,out}/`, `05_merged.jsonl`, `qa/s4_report.json` |
| S5 lextag | `s5_prepare.py` → Workflow → `s5_prepare.py --finalize` → `s5_consistency.py` → rejudge Workflow → `s5_consistency.py --apply-rejudge` → `s5_repair.py` | Sonnet; Opus rejudge | `s5_lextag.md` | `shards/s5_{in,out}/`, `06_lextagged.jsonl`, `qa/s5_report.json` |
| S6 misc taxonomy | `s6_sample.py` → Workflow (1 agent) → `s6_apply.py` | Fable, effort high | `s6_taxonomy.md` | `qa/s6_misc_taxonomy.md`, `qa/s6_misc_rules.json`, subfields in `06_…` |
| S7 QA+audit+export | `s7_invariants.py`, `s7_export.py`, `s7_audit_prep.py` → audit Workflow → `s7_fixes.py`, `s7_review_data.py`, `s7_build_review.py` | Fable audit | `s7_audit.md` | `07_final.jsonl`, `final.csv`, `qa/audit/`, `review/pilot_review.html` |

Conventions: all scripts run from repo root with `PYTHONIOENCODING=utf-8 python pipeline/<script>`.
Workflow agents **read their input shard and write their output shard themselves** and return
only stats — orchestration stays light and every batch is an independent checkpoint.
Deterministic steps between workflows are run by the main session.

## 5. Checkpoint inventory (current state = pilot complete)

```
checkpoints/
  00_dict2_pages/vol{1,2,3}.jsonl   page text {vol,page,text} — FULL CORPUS (done once)
  01_dict1_preparsed.jsonl          all 29,404 dict1 entries pre-parsed {word,seqid,raw,clean,hom_marker,decl_hint,trivial,def1?,misc1?}
  01_dict1_parsed.jsonl             PILOT slice, parsed {seqid,word,hom_src,decl,tags,def1,misc1,flags}
  02_dict2_segmented.jsonl          all 25,875 dict2 entries {id,vol,page,headword_raw,headword_fixed,hom,text,flags} — FULL CORPUS
  03_dict2_parsed.jsonl             PILOT slice, parsed {source_ids,word,hom,tags,def2,misc2,flags}
  04_match_table.jsonl              match rows {key,class,d1_items[],d2_word,word_final,…} class ∈ direct/verb/group/only1/only1_verb/only2
  05_merged.jsonl                   merged entries pre-lextag {word,word_base,dict_id,tags,def1,def2,misc1,misc2,src1,src2,word1_orig,word2_orig,decl,hom_rank,flags,entry_id}
  06_lextagged.jsonl                + lextag, lextag_conf, lextag_src, misc subfields
  07_final.jsonl                    FINAL PILOT: linguist schema first, then provenance + subfields; sorted by word
  final.csv                         same for Excel (utf-8-sig)
  review_data.json                  stats snapshot for the review page
  qa/                               per-stage reports; s6_misc_taxonomy.md + s6_misc_rules.json; audit/{task,result}_*.json + page PNGs
  review_queues/
    zh_dzh_unmatched.jsonl          82 native ж/дж words w/o pair — MANUAL review per linguist
    only1_verbs.jsonl               50 dict1-only verbs (imperatives resolved by LLM, kept for reference)
    spelling_conflicts.jsonl        2 canon collisions (таб/тап, табанча/тапанча) — informational
  shards/                           all workflow batch inputs/outputs (s0/s2/s4/s5 × in/out, s3b, rejudge, s6_sample)
review/pilot_review.html            linguist review page (source of the published artifact)
docs/PILOT_REPORT.md                this file
```

Published review artifact: https://claude.ai/code/artifact/b40123cf-9e79-453d-9bfb-17d59375d136
(redeploy: edit `review/pilot_review.html` via `pipeline/s7_build_review.py`, republish with the
Artifact tool passing that URL as `url` from a new conversation).

## 6. Pilot results

Slice: dict1 `та*`+`джаб*`+`джал*`; dict2 `ТА*`+`ЖАБ*`+`ЖАЛ*` → **1,404 merged entries**
(607 both / 444 dict1-only / 353 dict2-only), 111 homonym groups, 161 j-words, 5 b-words,
156 verbs merged to imperative.

QA per stage: S0 token-coverage **99.6 %**, 0 lost entries. S2 char-4-gram similarity 94 %
(difference = intended OCR repairs), **таукелсиз regression passes**. S3 verb dry-run validated;
Sonnet↔Opus imperative agreement 51/51. S4 zero lost entries. S5 confidence: 488 high / 815
medium / 101 low after family inheritance (171 fixed) + Opus rejudge (161 reviewed, 41 changed).
S7 invariants: clean except 2 borderline «къ.» cross-refs inside def2 (policy question).

**Fable audit** (36 stratified entries vs dict1 raw + PDF page scans): 23 ok / 9 minor /
4 major — **all fixed** (`pipeline/s7_fixes.py`, exact-substring patches + family-J propagation).

### Bugs found and FIXED in code during the pilot (already active for the full run)

1. Multiple d1 words claiming the same d2 word (noun+verb pairs) now merge into one group
   (`claims` dict in s3_match).
2. Verb matching is POS-filtered (was matching табаргъа to noun таба «сковорода»).
3. Verb candidates include а/е aorist stripping (таб-ар-гъа) — else common verbs unmatched.
4. `s3b_apply.py` syncs `d1_items[].word_final` (stale-infinitive bug).
5. J-rule extended to verbs and to dict1-only family derivatives.
6. Latin homoglyph repair on final word forms (`s5_repair.py`); word1_orig/word2_orig restored
   from provenance.
7. Digit-suffix collisions resolved globally after every rename.

### Known issues to address in the FULL RUN (not yet coded)

1. **S2 hypercorrection risk**: Sonnet occasionally «fixes» quotes into wrong text (тал2 case:
   negation inverted). Before the full run, add to `pipeline/prompts/s2_parse.md`:
   *«Внутри цитат (после которых стоит атрибуция автора) исправляй ТОЛЬКО однозначные
   OCR-артефакты (гомоглифы, разрядку); если прочтение слова сомнительно — оставь как есть и
   поставь flag uncertain_ocr. НИКОГДА не подбирай "по смыслу" другое слово в цитате.»*
2. **◊-ambiguity**: ◊ precedes both phrasemes and plain quotations; regex subfield `misc2_phras`
   is approximate. Needs an LLM disambiguation pass (or accept noise; linguist to decide).
3. **misc1 KB↔RU boundary** inside plain examples has no formal marker — typed extraction of
   example pairs needs LLM if the linguist wants it.
4. lextag policy decisions pending linguist (see review page): nakedness→human_body?
   textures→universe_and_nature? evaluatives→culture_and_spirituality?
5. ~37 OCR-mangled dict2 headwords lost at segmentation (list reproducible via the
   candidate-miss scan in git history / re-run of the diagnostic in §7 below) + 7 glued-entry
   cases — recover manually or via targeted re-parse.
6. Two borderline «къ.» cross-refs inside def2 (e_00377, e_00849 in pilot numbering).

## 7. HOW TO CONTINUE IN A FRESH SESSION

Read this file + memory (`kab-dict-pipeline` memory) first. The pilot is DONE and approved
artifacts exist; the remaining work is the **full-corpus run** (после одобрения лингвистом),
then final deliverables.

### Step 0 — prerequisites

- Working dir `D:\git\kab-dict`, Python 3.12 with PyMuPDF (`import fitz` works).
- Full-corpus S1 is ALREADY DONE (`02_dict2_segmented.jsonl` covers all 3 volumes) — do not redo.
- Apply the S2 prompt hardening from §6.1 before launching S2.
- Decide with the user whether to archive pilot shards (`checkpoints/shards/*`) — the full run
  REGENERATES `s0_in/s2_in/...`; pilot outputs will be overwritten by same-name batches.
  Recommended: `git add` checkpoints first or move `shards/` → `shards_pilot/`.

### Step 1 — S0 full

```bash
PYTHONIOENCODING=utf-8 python pipeline/s0_dict1_preparse.py --slice all --batch-size 40
```
≈ 26.6k non-trivial entries → ≈ 670 batches. Launch the parse workflow (same pattern as pilot —
see `~/.claude/.../workflows/scripts/parse-pilot-*.js` for the exact template): agents read
`pipeline/prompts/s0_parse.md` + `checkpoints/shards/s0_in/batch_NNNN.json`, write
`s0_out/batch_NNNN.json`, return stats `{batch,n_in,n_out,flagged,notes}`; model sonnet,
effort medium. Then `python pipeline/s0_qa.py` — gate: mean coverage ≥ 0.99, no missing entries.
Escalate failing batches to Opus (re-run just those batch indices in a small workflow).

### Step 2 — S2 full

```bash
PYTHONIOENCODING=utf-8 python pipeline/s2_make_batches.py --slice all --batch-size 12
```
≈ 25.9k entries → ≈ 2,160 batches. Same workflow pattern with `s2_parse.md` (hardened per §6.1).
This is the long pole: at ~14 concurrent Sonnet agents expect several hours; run as ONE
background workflow (resume with `resumeFromRunId` if interrupted **within the session**;
across sessions, count existing `s2_out` files and launch a workflow for the missing indices —
this exact recovery was done in the pilot and works cleanly).
Then `python pipeline/s2_qa.py` — gates: таукелсиз regression ok; unconsumed ≈ 0; inspect
low-sim tail (mostly false positives from OCR repair, but scan for hypercorrection).

### Step 3 — S3 + S3b full

```bash
PYTHONIOENCODING=utf-8 python pipeline/s3_match.py --slice all
```
Queues will grow (est. several hundred only1-verbs, ~2-3k unmatched ж/дж words corpus-wide).
Regenerate `shards/s3b_verbs_in.json` / `s3b_zhdzh_in.json` from the queues (see pilot command in
history: simple json dump of the two queue files), split verbs into batches of ~60 if large.
Run the adjudication workflow: verbs = Sonnet + Opus in parallel (compare; disagreements → decide
in-session at Fable level), zh/dzh triage = Opus. Then:
```bash
PYTHONIOENCODING=utf-8 python pipeline/s3b_apply.py
```

### Step 4 — S4 full

```bash
PYTHONIOENCODING=utf-8 python pipeline/s4_merge.py --prepare
```
Est. ≈ 2.5–3k complex groups → ≈ 450–500 batches of 6. Workflow with `s4_merge.md`, **model opus,
effort high** (semantic homonym alignment is the highest-stakes step). Then:
```bash
PYTHONIOENCODING=utf-8 python pipeline/s4_merge.py --finalize
```
Check `qa/s4_report.json`: no missing_llm_outputs; verify a few known groups (таб/тап, jалгъан).

### Step 5 — S5 full

```bash
PYTHONIOENCODING=utf-8 python pipeline/s5_prepare.py            # ~850 batches of 50
# workflow: s5_lextag.md, sonnet, effort medium
PYTHONIOENCODING=utf-8 python pipeline/s5_prepare.py --finalize
PYTHONIOENCODING=utf-8 python pipeline/s5_consistency.py        # family inheritance + rejudge export
# workflow: single/multiple Opus agents over shards/s5_rejudge_in.json (split if >300 items)
PYTHONIOENCODING=utf-8 python pipeline/s5_consistency.py --apply-rejudge
PYTHONIOENCODING=utf-8 python pipeline/s5_repair.py
```
Apply the linguist's answers to the 3 policy questions as global re-tags before finalizing
(simple filtered update over 06_lextagged.jsonl).

### Step 6 — S6 + S7 full

- Re-run `s6_sample.py` (larger sample, e.g. 200) + taxonomy agent ONLY if the linguist wants
  the taxonomy revalidated; otherwise reuse `qa/s6_misc_rules.json` and just run:
```bash
PYTHONIOENCODING=utf-8 python pipeline/s6_apply.py
PYTHONIOENCODING=utf-8 python pipeline/s7_invariants.py   # gate: only known-benign problems
PYTHONIOENCODING=utf-8 python pipeline/s7_export.py
PYTHONIOENCODING=utf-8 python pipeline/s7_audit_prep.py --n 60 --per-task 3
# workflow: s7_audit.md, model fable, effort high, one agent per task file
```
- Triage audit results; apply fixes via a new PATCHES list in `s7_fixes.py` (keep the pilot list,
  append; each patch asserts exactly-one occurrence). Re-run export + invariants after fixes.
- `python pipeline/s7_review_data.py && python pipeline/s7_build_review.py`, publish
  `review/pilot_review.html` to the SAME artifact URL (pass `url:` param, see §5) or a new one
  for the full run.

### Expected full-run volumes

≈ 670 (S0) + 2,160 (S2) + ~10 (S3b) + ~480 (S4) + ~850 + rejudge (S5) + ~20 (S7) ≈ **4,300–4,600
agent calls**; dominated by S2. Token order: 40–60 M (mostly Sonnet). Merged size estimate:
**40–45k entries**.

### Quality gates recap (do not skip)

1. S0: coverage ≥ 99 %, zero missing.
2. S2: таукелсиз regression; unconsumed segments ≈ 0; hypercorrection spot-check on citations.
3. S4: entry accounting zero-loss; digit-suffix invariants.
4. S7: `s7_invariants.py` clean; Fable audit ≥ 60 entries incl. PDF-crop verification; ALL major
   findings fixed before delivery.

### Model policy (validated in pilot)

- Parsing/classification bulk: **Sonnet** (quality confirmed).
- Homonym alignment (S4), morphology adjudication, lextag rejudge: **Opus**.
- Taxonomy analysis, final audit: **Fable** agents; final judgment calls: main session (Fable).

## 8. Where everything else lives

- Approved plan: `C:\Users\aver\.claude\plans\important-linguistics-task-abour-valiant-map.md`
- Session memory: `C:\Users\aver\.claude\projects\D--git-kab-dict\memory\kab-dict-pipeline.md`
- Pilot workflow script templates: `C:\Users\aver\.claude\projects\D--git-kab-dict\*\workflows\scripts\`
  (parse-pilot, merge-homonyms-v2, lextag-pilot, final-audit, misc-taxonomy — reuse the agent()
  prompt patterns verbatim, only change batch counts/paths)
- Nothing is committed to git yet (`sources/`, `checkpoints/`, `pipeline/` are untracked) —
  ask the user whether to commit pipeline+docs (recommended) and whether checkpoints belong in
  git or just on disk.
