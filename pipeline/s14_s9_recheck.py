# -*- coding: utf-8 -*-
"""S14: re-check the S9 queues (Russian–KB dictionary cross-check) after the S10–S13 repairs.

manual_review_2.xlsx may already be in the linguist's hands, so it is NOT rewritten.
Instead every row of the two S9 queues gets a status against the repaired corpus:
  resolved_by_repair   the word is now a headword (restored hyphen word, recovered ТСКБЯ page…)
  false_positive       known artefacts of the S9 scan (glued words of the txt, existing two-word form)
  still_open           unchanged — the linguist's verdict is still needed
Output: review_queues/s9_recheck.jsonl (+ counts printed); used by the repair review workbook.
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
RQ = CK / "review_queues"

# found by the 2026-11-04 survey (SOURCES_SURVEY.md, раздел 7, находка 10)
FALSE = {"гылынкъуш": "в корпусе есть «гылын къуш» (раздельно)",
         "азшагъырей": "склейка в txt, в печати слова раздельно",
         "акъылыjарты": "склейка в txt, в печати слова раздельно",
         "акъылыджарты": "склейка в txt, в печати слова раздельно",
         "сазтопракълы": "склейка в txt, в печати слова раздельно"}


def fold(w):
    w = re.sub(r"\d+$", "", (w or "").lower().strip()).replace("ё", "е")
    w = w.replace("кь", "къ").replace("гь", "гъ").replace("дж", "j").replace("ж", "j")
    return w.replace("b", "п").replace("б", "п")


def main():
    heads = {}
    for l in open(CK / "06_lextagged.jsonl", encoding="utf-8"):
        e = json.loads(l)
        for w in (e["word"], e.get("word1_orig") or "", e.get("word2_orig") or ""):
            if w:
                heads.setdefault(fold(w), e)
    out = []
    for name in ("rus_missing_confirmed", "rus_variants_confirmed"):
        for r in (json.loads(l) for l in open(RQ / f"{name}.jsonl", encoding="utf-8")):
            form = r.get("canonical") or r["form"]
            st, why = "still_open", ""
            if fold(r["form"]) in {fold(k) for k in FALSE} or fold(form) in {fold(k) for k in FALSE}:
                st, why = "false_positive", FALSE.get(r["form"], FALSE.get(form, ""))
            elif name == "rus_missing_confirmed" and fold(form) in heads:
                e = heads[fold(form)]
                if any(f in (e.get("flags") or []) for f in ("hyphen_restored", "gap_fill")):
                    st, why = "resolved_by_repair", f"теперь заглавное слово «{e['word']}» ({e['dict_id']})"
            out.append({"queue": name, "form": r["form"], "canonical": form, "status": st, "why": why,
                        "ru_gloss": r.get("ru_gloss", "")})
    with open(RQ / "s9_recheck.jsonl", "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print({f"{k[0]}/{k[1]}": v for k, v in Counter((r["queue"], r["status"]) for r in out).items()})
    print([ (r["form"], r["why"]) for r in out if r["status"] != "still_open"][:40])


if __name__ == "__main__":
    main()
