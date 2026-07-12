# -*- coding: utf-8 -*-
"""S0a: Deterministic pre-parse of dict 1 (qmos, КБ->рус translation dictionary).

- dedup exact-duplicate entries per headword (OCR doubling)
- detect homonym Roman-numeral markers
- expand tilde (~) to the headword, strip typographic markup @ # $ %
- classify entries as trivial (def1 = whole text, no LLM needed) vs LLM-needed
- emit LLM batch inputs for the requested slice (--pilot or --all)

Outputs:
  checkpoints/01_dict1_preparsed.jsonl
  checkpoints/shards/s0_in/batch_####.json
  checkpoints/qa/s0_preparse_report.json
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "1" / "qmos_def_32499.txt"
OUT = ROOT / "checkpoints" / "01_dict1_preparsed.jsonl"
SHARD_IN = ROOT / "checkpoints" / "shards" / "s0_in"
QA = ROOT / "checkpoints" / "qa" / "s0_preparse_report.json"

RE_ROMAN = re.compile(r"^@?(I{1,3}|IV|V|VI{0,3})#?\s*")
RE_DECL = re.compile(r"^\s*\((-[а-яё]{1,4})\)\s*")

def clean_markup(text: str, word: str) -> str:
    """Expand ~ to headword, drop @ # $ % font marks, normalize whitespace."""
    t = text.replace("~", word)
    t = re.sub(r"[@#$%]", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" ([,;:.!?)])", r"\1", t)
    t = re.sub(r"\( ", "(", t)
    return t.strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", choices=["pilot", "all"], default="pilot")
    ap.add_argument("--batch-size", type=int, default=40)
    args = ap.parse_args()

    data = json.load(open(SRC, encoding="utf-8"))

    # ---- dedup ----------------------------------------------------------
    byword = defaultdict(list)
    for k, v in data.items():
        word, seqid = k.rsplit("_", 1)
        byword[word].append((int(seqid), v))
    entries, dropped = [], []
    for word, lst in byword.items():
        seen = {}
        for seqid, v in sorted(lst):
            if v in seen:
                dropped.append({"word": word, "seqid": seqid, "dup_of": seen[v]})
            else:
                seen[v] = seqid
                entries.append({"word": word, "seqid": seqid, "raw": v})
    entries.sort(key=lambda e: e["seqid"])

    # ---- pre-parse ------------------------------------------------------
    n_trivial = 0
    for e in entries:
        raw = e["raw"]
        m = RE_ROMAN.match(raw.strip())
        hom = ""
        rest = raw.strip()
        if m and m.group(1):
            hom = m.group(1)
            rest = rest[m.end():]
        md = RE_DECL.match(rest)
        decl = ""
        if md:
            decl = md.group(1)
            rest = rest[md.end():]
        e["hom_marker"] = hom
        e["decl_hint"] = decl
        e["clean"] = clean_markup(rest, e["word"])
        # trivial: no KB examples (@), no italic labels beyond none, short
        if "@" not in rest and "$" not in rest and len(rest) <= 80 and ";" not in rest:
            e["trivial"] = True
            e["def1"] = e["clean"]
            e["misc1"] = ""
            e["tags"] = ""
            n_trivial += 1
        else:
            e["trivial"] = False

    with open(OUT, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ---- batches for LLM ------------------------------------------------
    if args.slice == "pilot":
        sel = [e for e in entries if e["word"].lower().startswith(("та", "джаб", "джал"))]
    else:
        sel = entries
    need_llm = [e for e in sel if not e["trivial"]]
    SHARD_IN.mkdir(parents=True, exist_ok=True)
    for f_old in SHARD_IN.glob("batch_*.json"):
        f_old.unlink()
    bs = args.batch_size
    for i in range(0, len(need_llm), bs):
        batch = need_llm[i:i + bs]
        payload = [{"seqid": e["seqid"], "word": e["word"], "hom": e["hom_marker"],
                    "decl": e["decl_hint"], "text": e["clean"]} for e in batch]
        with open(SHARD_IN / f"batch_{i//bs:04d}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)

    report = {
        "entries_in": len(data), "after_dedup": len(entries),
        "dropped_dups": len(dropped), "trivial": n_trivial,
        "slice": args.slice, "slice_size": len(sel),
        "llm_needed": len(need_llm), "batches": (len(need_llm) + bs - 1) // bs,
    }
    QA.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if QA.exists():
        existing = json.load(open(QA, encoding="utf-8"))
    existing[args.slice] = report
    existing["dropped_sample"] = dropped[:20]
    with open(QA, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
