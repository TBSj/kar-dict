# -*- coding: utf-8 -*-
"""S3b apply: fold LLM adjudication results back into the match table.

- shards/s3b_out/verbs.json  -> word_final for only1_verb rows (imperative form)
- shards/s3b_out/zhdzh.json  -> kind annotations; loanwords removed from manual queue
"""
import json, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
S3B = CK / "shards" / "s3b_out"

def main():
    rows = [json.loads(l) for l in open(CK / "04_match_table.jsonl", encoding="utf-8")]
    verbs = {}
    vf = S3B / "verbs.json"
    if vf.exists():
        for it in json.load(open(vf, encoding="utf-8"))["items"]:
            verbs[it["word"]] = it
    kinds = {}
    zf = S3B / "zhdzh.json"
    if zf.exists():
        for it in json.load(open(zf, encoding="utf-8"))["items"]:
            kinds[(it["dict"], it["word"])] = it["kind"]

    n_verb = n_kind = 0
    for r in rows:
        if r["class"] == "only1_verb":
            if r["word_final"] is None or r.get("verb_conf") == "unresolved":
                it = verbs.get(r["d1_word"])
                if it:
                    r["word_final"] = it["imperative"].lower()
                    r["verb_conf"] = it.get("confidence", "medium")
                    n_verb += 1
                else:
                    r["word_final"] = r["d1_word"].lower()
                    r["verb_conf"] = "unresolved"
            for d1i in r.get("d1_items", []):
                if d1i.get("word") == r["d1_word"] and d1i.get("word_final") != r["word_final"]:
                    d1i["word_final"] = r["word_final"]
        if r["class"] in ("only1", "only1_verb") and (r["d1_word"] or "").lower().startswith("дж"):
            k = kinds.get((1, r["d1_word"]))
            if k:
                r["zh_kind"] = k; n_kind += 1
        if r["class"] == "only2" and (r["d2_word"] or "").lower().startswith("ж"):
            k = kinds.get((2, r["d2_word"]))
            if k:
                r["zh_kind"] = k; n_kind += 1

    with open(CK / "04_match_table.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # rebuild the manual zh/dzh queue: natives + unsure only
    q = CK / "review_queues" / "zh_dzh_unmatched.jsonl"
    if q.exists() and kinds:
        items = [json.loads(l) for l in open(q, encoding="utf-8")]
        keep = []
        for it in items:
            k = kinds.get((it["dict"], it["word"]), "unsure")
            it["kind"] = k
            if k != "loanword":
                keep.append(it)
        with open(q, "w", encoding="utf-8") as f:
            for it in keep:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(f"zh/dzh queue: {len(items)} -> {len(keep)} (loanwords excluded)")
    print(json.dumps({"verbs_resolved": n_verb, "zh_kinds_applied": n_kind}))

if __name__ == "__main__":
    main()
