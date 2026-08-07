# -*- coding: utf-8 -*-
"""S9b-prep: build triage batches for workflow agents.

Selects top candidates from rus_missing_words.jsonl / rus_spelling_variants.jsonl,
attaches usage snippets from the rus->KB dictionary, writes batches of 100 to
checkpoints/shards/s9_batches/batch_NN.json.
"""
import json, re, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
RQ = CK / "review_queues"
OUT = CK / "shards" / "s9_batches"
OUT.mkdir(parents=True, exist_ok=True)

RE_TAG = re.compile(r"</?[a-z]+>")


def main():
    rus = json.load(open(ROOT / "sources" / "5" / "rus_kb_dict_33040.txt", encoding="utf-8"))
    plain = {k: RE_TAG.sub(" ", v.replace("­", "")) for k, v in rus.items()}

    def contexts(form_src, sources, n=3):
        out = []
        for key in sources[:n]:
            txt = plain.get(key, "")
            i = txt.lower().find(form_src)
            snip = txt[max(0, i - 80):i + len(form_src) + 80].strip() if i >= 0 else txt[:160]
            out.append({"rus": re.sub(r"_\d+$", "", key), "snippet": re.sub(r"\s+", " ", snip)})
        return out

    def load(p):
        return [json.loads(l) for l in open(RQ / p, encoding="utf-8")]

    cand = []
    for r in load("rus_missing_words.jsonl"):
        if r["is_rus_loan"]:
            continue
        if r["count_cite"] >= 2 or (r["count_cite"] >= 1 and r["kb_marker"]) or r["count_ctx"] >= 8:
            cand.append({**{k: r[k] for k in ("form", "form_src", "count_cite", "count_ctx", "kb_marker")},
                         "queue": "missing", "contexts": contexts(r["form_src"], r["sources"])})
    for r in load("rus_spelling_variants.jsonl"):
        if r["is_rus_loan"]:
            continue
        if r["count_cite"] >= 1 or r["count_ctx"] >= 5:
            cand.append({**{k: r[k] for k in ("form", "form_src", "count_cite", "count_ctx", "kb_marker")},
                         "queue": "variant", "near": r["near"],
                         "contexts": contexts(r["form_src"], r["sources"])})

    cand = cand[:600]
    B = 100
    paths = []
    for i in range(0, len(cand), B):
        p = OUT / f"batch_{i // B:02d}.json"
        json.dump(cand[i:i + B], open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        paths.append(str(p))
    n_miss = sum(1 for c in cand if c["queue"] == "missing")
    print(f"candidates: {len(cand)} (missing {n_miss}, variant {len(cand) - n_miss}) "
          f"-> {len(paths)} batches")
    json.dump(paths, open(OUT / "batches.json", "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
