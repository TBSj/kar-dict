# -*- coding: utf-8 -*-
"""S2a: Build LLM parse batches from segmented dict-2 entries.

Batches keep consecutive entries together and never start with a flagged
entry (alpha_break/very_short/noise_in_head stay with their predecessor).

  python s2_make_batches.py --slice pilot   # headwords та*/жаб*/жал*/джаб*/джал*
  python s2_make_batches.py --slice all
"""
import json, re, sys, io, argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "checkpoints" / "02_dict2_segmented.jsonl"
SHARD_IN = ROOT / "checkpoints" / "shards" / "s2_in"

PILOT_PREFIXES = ("та", "жаб", "жал", "джаб", "джал")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", choices=["pilot", "all"], default="pilot")
    ap.add_argument("--batch-size", type=int, default=12)
    args = ap.parse_args()

    entries = [json.loads(l) for l in open(SEG, encoding="utf-8")]
    if args.slice == "pilot":
        sel = []
        for i, e in enumerate(entries):
            take = e["headword_fixed"].startswith(PILOT_PREFIXES)
            # flagged entries follow their predecessor (may be continuations)
            if not take and sel and e["flags"] and entries[i-1] is sel[-1]:
                take = True
            if take:
                sel.append(e)
    else:
        sel = entries

    SHARD_IN.mkdir(parents=True, exist_ok=True)
    for f_old in SHARD_IN.glob("batch_*.json"):
        f_old.unlink()

    batches, cur = [], []
    for e in sel:
        boundary_ok = not e["flags"] or not cur
        if len(cur) >= args.batch_size and boundary_ok:
            batches.append(cur)
            cur = []
        cur.append(e)
        if len(cur) >= args.batch_size * 2:  # safety: force break on runaway
            batches.append(cur)
            cur = []
    if cur:
        batches.append(cur)

    for i, b in enumerate(batches):
        payload = [{"id": e["id"], "vol": e["vol"], "page": e["page"],
                    "head_hint": e["headword_fixed"], "hom_hint": e["hom"],
                    "flags": e["flags"], "text": e["text"]} for e in b]
        with open(SHARD_IN / f"batch_{i:04d}.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)

    total = sum(len(b) for b in batches)
    print(json.dumps({"slice": args.slice, "entries": total, "batches": len(batches)}))

if __name__ == "__main__":
    main()
