# -*- coding: utf-8 -*-
"""S5c: derivational-family consistency pass over 06_lextagged.jsonl.

1. Entries whose tags contain a relational reference (и. д. от X / понуд. к X /
   отвлеч. к X / страд. / взаимн. / прич. от X ...) inherit the lextag of the
   base entry X when that base is classified with medium/high confidence.
2. Remaining low-confidence entries are exported for an Opus re-judge batch,
   each with its derivational family context.
"""
import json, re, sys, io, argparse
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

RE_REL = re.compile(r"(?:и\.\s?д\.|понуд\.|отвлеч\.|страд\.|взаимн\.[-а-я.]*|прич\.|усил\.|кюч\.)\s*(?:от|к)\s+([а-яёa-z]+)")

def norm(w):
    return re.sub(r"\d+$", "", (w or "").lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-rejudge", action="store_true",
                    help="fold shards/s5_rejudge_out.json back in")
    args = ap.parse_args()
    entries = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]

    if args.apply_rejudge:
        rj = {x["entry_id"]: x for x in json.load(open(CK / "shards" / "s5_rejudge_out.json", encoding="utf-8"))["items"]}
        n = 0
        for e in entries:
            x = rj.get(e["entry_id"])
            if x:
                e["lextag"] = x["lextag"]
                e["lextag_conf"] = x.get("confidence", "medium")
                e["lextag_src"] = "opus_rejudge"
                n += 1
        with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"re-judge applied to {n} entries")
        return

    # index: word -> best-confidence entry
    byword = defaultdict(list)
    for e in entries:
        byword[norm(e.get("word"))].append(e)
    rank = {"high": 2, "medium": 1, "low": 0, "missing": -1}

    inherited = 0
    for e in entries:
        m = RE_REL.search(e.get("tags") or "")
        if not m:
            continue
        base_w = norm(m.group(1))
        # base may be j-/b-normalized or verb-imperative; try direct, j-fold, and both-dict originals
        cands = byword.get(base_w, [])
        if not cands and base_w.startswith("ж"):
            cands = byword.get("j" + base_w[1:], [])
        if not cands and base_w.startswith("дж"):
            cands = byword.get("j" + base_w[2:], []) or byword.get("ж" + base_w[2:], [])
        if not cands:
            continue
        best = max(cands, key=lambda x: rank.get(x.get("lextag_conf"), 0))
        if rank.get(best.get("lextag_conf"), 0) >= 1 and best["entry_id"] != e["entry_id"]:
            if e.get("lextag") != best["lextag"] or e.get("lextag_conf") == "low":
                e["lextag"] = best["lextag"]
                e["lextag_conf"] = "medium"
                e["lextag_src"] = f"family:{best['entry_id']}"
                inherited += 1

    # export remaining low-confidence for re-judge, with family context
    low = [e for e in entries if e.get("lextag_conf") == "low"]
    fam_ctx = []
    for e in low:
        stem = norm(e["word"])[:5]
        family = [x for x in entries if norm(x["word"])[:5] == stem and x["entry_id"] != e["entry_id"]][:6]
        fam_ctx.append({
            "entry_id": e["entry_id"], "word": e["word"], "tags": e.get("tags",""),
            "def1": (e.get("def1") or "")[:200], "def2": (e.get("def2") or "")[:200],
            "misc1": (e.get("misc1") or "")[:150], "misc2": (e.get("misc2") or "")[:150],
            "current": e.get("lextag"),
            "family": [{"word": x["word"], "def": ((x.get("def1") or x.get("def2") or ""))[:90],
                        "lextag": x.get("lextag"), "conf": x.get("lextag_conf")} for x in family],
        })
    json.dump({"items": fam_ctx}, open(CK / "shards" / "s5_rejudge_in.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    conf = Counter(e.get("lextag_conf") for e in entries)
    print(json.dumps({"family_inherited": inherited, "still_low": len(low),
                      "confidence": dict(conf)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
