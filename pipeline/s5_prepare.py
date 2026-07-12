# -*- coding: utf-8 -*-
"""S5a: batches for lextag classification. S5b (--finalize): fold results in.

  python s5_prepare.py            # make batches from 05_merged.jsonl
  python s5_prepare.py --finalize # apply shards/s5_out -> 06_lextagged.jsonl
"""
import json, sys, io, argparse, re
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S5_IN = CK / "shards" / "s5_in"
S5_OUT = CK / "shards" / "s5_out"

VALID = {"universe_and_nature","living_things","human_body","mind_and_cognition",
         "emotions_and_will","social_relations","culture_and_spirituality",
         "language_and_communication","actions_and_activities","objects_and_technology",
         "daily_life_and_food","economy_and_society","space_and_time","logic_and_function_words"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()
    merged = [json.loads(l) for l in open(CK / "05_merged.jsonl", encoding="utf-8")]

    if not args.finalize:
        S5_IN.mkdir(parents=True, exist_ok=True)
        for f in S5_IN.glob("batch_*.json"): f.unlink()
        bs = args.batch_size
        for i in range(0, len(merged), bs):
            payload = [{"entry_id": e["entry_id"], "word": e["word"],
                        "tags": e.get("tags",""),
                        "def1": (e.get("def1") or "")[:220],
                        "def2": (e.get("def2") or "")[:220]} for e in merged[i:i+bs]]
            json.dump(payload, open(S5_IN / f"batch_{i//bs:04d}.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        print(json.dumps({"entries": len(merged), "batches": (len(merged)+bs-1)//bs}))
        return

    tags = {}
    bad = []
    for f in sorted(S5_OUT.glob("batch_*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            if it.get("lextag") in VALID:
                tags[it["entry_id"]] = it
            else:
                bad.append(it)
    missing = []
    # derivational-family consistency: group by rough stem (first 6 letters of word_base)
    for e in merged:
        it = tags.get(e["entry_id"])
        if it:
            e["lextag"] = it["lextag"]
            e["lextag_conf"] = it.get("confidence", "medium")
        else:
            e["lextag"] = ""
            e["lextag_conf"] = "missing"
            missing.append(e["entry_id"])
    fam = defaultdict(list)
    for e in merged:
        stem = re.sub(r"\d+$", "", e.get("word", ""))[:6]
        fam[stem].append(e)
    mixed_fams = sum(1 for k, es in fam.items()
                     if len(es) > 2 and len({x["lextag"] for x in es if x["lextag"]}) > 2)
    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in merged:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    dist = Counter(e["lextag"] for e in merged)
    conf = Counter(e["lextag_conf"] for e in merged)
    rep = {"entries": len(merged), "missing": len(missing), "invalid_tags": len(bad),
           "confidence": dict(conf), "distribution": dict(dist.most_common()),
           "mixed_families_gt2tags": mixed_fams}
    json.dump(rep, open(CK / "qa" / "s5_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
