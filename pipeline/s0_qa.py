# -*- coding: utf-8 -*-
"""S0 QA gate: content preservation + structural checks for dict-1 LLM parse.

For every parsed entry, tokens of (tags + def1 + misc1) must cover the tokens
of the pre-cleaned input text. Reports per-batch coverage; lists offenders.
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "checkpoints" / "shards" / "s0_in"
OUT_DIR = ROOT / "checkpoints" / "shards" / "s0_out"
QA = ROOT / "checkpoints" / "qa" / "s0_qa_report.json"

def toks(s):
    return Counter(re.findall(r"[а-яёА-ЯЁa-zA-Z]{2,}", s.lower()))

def main():
    batches = sorted(IN_DIR.glob("batch_*.json"))
    report = {"batches": {}, "offenders": [], "missing_outputs": [], "missing_entries": []}
    tot_in = tot_out = 0
    cov_sum = 0.0
    for bf in batches:
        outf = OUT_DIR / bf.name
        if not outf.exists():
            report["missing_outputs"].append(bf.name)
            continue
        inp = {e["seqid"]: e for e in json.load(open(bf, encoding="utf-8"))}
        try:
            out = json.load(open(outf, encoding="utf-8"))["entries"]
        except Exception as ex:
            report["batches"][bf.name] = {"error": str(ex)}
            continue
        omap = {e["seqid"]: e for e in out}
        tot_in += len(inp); tot_out += len(out)
        losses = []
        for sid, ie in inp.items():
            oe = omap.get(sid)
            if oe is None:
                report["missing_entries"].append({"batch": bf.name, "seqid": sid, "word": ie["word"]})
                continue
            src = toks(ie["text"])
            dst = toks(" ".join([oe.get("tags",""), oe.get("def1",""), oe.get("misc1","")]))
            missing = src - dst
            n_missing = sum(missing.values())
            cov = 1 - n_missing / max(1, sum(src.values()))
            cov_sum += cov
            if cov < 0.98:
                losses.append({"seqid": sid, "word": ie["word"], "coverage": round(cov, 3),
                               "missing_tokens": list(missing.keys())[:15]})
        report["batches"][bf.name] = {
            "n_in": len(inp), "n_out": len(out),
            "low_coverage": len(losses),
        }
        report["offenders"].extend(losses)
    n_checked = tot_in - len(report["missing_entries"])
    report["summary"] = {
        "total_in": tot_in, "total_out": tot_out,
        "mean_coverage": round(cov_sum / max(1, n_checked), 4),
        "entries_below_98pct": len(report["offenders"]),
        "missing_entries": len(report["missing_entries"]),
        "missing_outputs": len(report["missing_outputs"]),
    }
    report["offenders"] = sorted(report["offenders"], key=lambda x: x["coverage"])[:60]
    QA.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(QA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for o in report["offenders"][:10]:
        print(o["word"], o["coverage"], o["missing_tokens"][:8])

if __name__ == "__main__":
    main()
