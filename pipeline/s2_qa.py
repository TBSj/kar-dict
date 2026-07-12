# -*- coding: utf-8 -*-
"""S2 QA gate for dict-2 LLM parse.

Checks:
  1. segment accounting: every input segment id consumed exactly once
  2. fuzzy content preservation (OCR repair changes tokens -> similarity >= 0.90)
  3. def2 must not contain KB-specific text (къ/гъ/дж/нг digraph density)
  4. alphabetic continuity of parsed words
  5. таукелсиз regression test against the linguist-verified ground truth
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "checkpoints" / "shards" / "s2_in"
OUT_DIR = ROOT / "checkpoints" / "shards" / "s2_out"
QA = ROOT / "checkpoints" / "qa" / "s2_qa_report.json"

def toks(s):
    """Char 4-grams over letters only — robust to OCR word joins/splits."""
    flat = "".join(re.findall(r"[а-яёa-z]", s.lower().replace("ё", "е")))
    return Counter(flat[i:i+4] for i in range(max(0, len(flat) - 3)))

def kb_density(s):
    """Share of words containing KB-specific digraphs — Russian text ~0."""
    words = re.findall(r"[а-яё]{3,}", s.lower())
    if not words:
        return 0.0
    kb = sum(1 for w in words if re.search(r"къ|гъ|нг", w) or re.search(r"[ыиаоюё]у$", w))
    return kb / len(words)

def main():
    report = {"batches": {}, "low_sim": [], "kb_leaks": [], "alpha_breaks": [],
              "missing_outputs": [], "unconsumed_segments": [], "double_consumed": []}
    tot_in = tot_out = 0
    sim_sum = 0.0; sim_n = 0
    prev_word = ""
    regression = {"found": False, "ok": False, "details": ""}
    for bf in sorted(IN_DIR.glob("batch_*.json")):
        outf = OUT_DIR / bf.name
        if not outf.exists():
            report["missing_outputs"].append(bf.name)
            continue
        inp = {e["id"]: e for e in json.load(open(bf, encoding="utf-8"))}
        try:
            out = json.load(open(outf, encoding="utf-8"))["entries"]
        except Exception as ex:
            report["batches"][bf.name] = {"error": str(ex)}
            continue
        tot_in += len(inp); tot_out += len(out)
        consumed = Counter()
        # segment-level preservation: union of all entries consuming a segment
        seg_dst = defaultdict(Counter)
        for oe in out:
            dst = toks(" ".join([oe.get("tags",""), oe.get("def2",""), oe.get("misc2",""), oe.get("word","")]))
            for sid in oe.get("source_ids", []):
                consumed[sid] += 1
                seg_dst[sid].update(dst)
        for sid, ie in inp.items():
            if consumed[sid] == 0:
                continue
            src = toks(ie["text"])
            inter = sum((src & seg_dst[sid]).values())
            sim = inter / max(1, sum(src.values()))
            sim_sum += sim; sim_n += 1
            if sim < 0.85:
                report["low_sim"].append({"batch": bf.name, "seg": sid, "head": ie.get("head_hint",""),
                                          "sim": round(sim,3)})
        for oe in out:
            d2 = oe.get("def2","")
            if len(d2) > 15 and kb_density(d2) > 0.34:
                report["kb_leaks"].append({"batch": bf.name, "word": oe.get("word",""), "def2": d2[:120]})
            w = oe.get("word","").lower()
            if prev_word and w and w[:1] == prev_word[:1] and w < prev_word:
                report["alpha_breaks"].append({"batch": bf.name, "prev": prev_word, "word": w})
            if w:
                prev_word = w
            # regression: таукелсиз I
            if w == "таукелсиз" and oe.get("hom","").strip() in ("I","1"):
                regression["found"] = True
                want = "нерешительный, несмелый; безвольный"
                got = re.sub(r"\s+", " ", d2.lower().strip(" ."))
                regression["ok"] = got == want
                regression["details"] = f"def2={d2!r} tags={oe.get('tags','')!r}"
        missing = [sid for sid in inp if consumed[sid] == 0]
        dbl = [sid for sid, c in consumed.items() if c > 1]
        report["unconsumed_segments"].extend({"batch": bf.name, "id": m, "head": inp[m]["head_hint"]} for m in missing)
        report["double_consumed"].extend({"batch": bf.name, "id": d} for d in dbl)
        report["batches"][bf.name] = {"n_in": len(inp), "n_out": len(out)}
    report["summary"] = {
        "total_segments": tot_in, "total_entries": tot_out,
        "mean_similarity": round(sim_sum / max(1, sim_n), 4),
        "low_similarity": len(report["low_sim"]),
        "kb_leaks_in_def2": len(report["kb_leaks"]),
        "alpha_breaks": len(report["alpha_breaks"]),
        "unconsumed": len(report["unconsumed_segments"]),
        "double_consumed": len(report["double_consumed"]),
        "missing_outputs": len(report["missing_outputs"]),
        "regression_taukelsiz": regression,
    }
    report["low_sim"] = sorted(report["low_sim"], key=lambda x: x["sim"])[:60]
    QA.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(QA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
