# -*- coding: utf-8 -*-
"""S7d: prepare the Fable audit sample.

Selects N entries from 07_final.jsonl (stratified: homonym groups, j/b words,
verbs, flagged, random), renders the source PDF pages to PNG for dict2 sides,
dumps dict1 raw source values, and writes audit tasks.

Output: checkpoints/qa/audit/task_##.json + page PNGs
"""
import json, re, sys, io, random, argparse
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
AUD = CK / "qa" / "audit"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=36)
    ap.add_argument("--per-task", type=int, default=3)
    args = ap.parse_args()
    import fitz

    entries = [json.loads(l) for l in open(CK / "07_final.jsonl", encoding="utf-8")]
    random.seed(7)

    strata = {
        "homonym": [e for e in entries if re.search(r"\d$", e["word"])],
        "jb": [e for e in entries if e["word"].startswith("j") or e["word"].rstrip("0123456789").endswith("b")],
        "verb": [e for e in entries if (e.get("word1_orig") or "").endswith(("ргъа", "рге")) and e.get("dict_id") == "both"],
        "flagged": [e for e in entries if e.get("flags")],
        "random": entries,
    }
    base = {"homonym": 8, "jb": 6, "verb": 6, "flagged": 6, "random": 10}
    scale = args.n / sum(base.values())
    quota = {k: max(1, round(v * scale)) for k, v in base.items()}
    chosen, seen = [], set()
    for k, q in quota.items():
        pool = [e for e in strata[k] if e["entry_id"] not in seen]
        for e in random.sample(pool, min(q, len(pool))):
            chosen.append(e); seen.add(e["entry_id"])
    chosen = chosen[:args.n]

    # dict1 raw values
    raw1 = json.load(open(ROOT / "sources" / "1" / "qmos_def_32499.txt", encoding="utf-8"))
    by_seqid = {int(k.rsplit("_", 1)[1]): (k.rsplit("_", 1)[0], v) for k, v in raw1.items()}

    # dict2 segments (for vol/page)
    seg = {}
    for l in open(CK / "02_dict2_segmented.jsonl", encoding="utf-8"):
        s = json.loads(l); seg[s["id"]] = s

    AUD.mkdir(parents=True, exist_ok=True)
    for f in AUD.glob("*"): f.unlink()

    VOLS = {1: "ТСКБЯ - 1.pdf", 2: "ТСКБЯ - 2.pdf", 3: "ТСКБЯ - 3.pdf"}
    docs = {}
    rendered = set()
    tasks = []
    for e in chosen:
        t = {"entry": e, "d1_raw": [], "d2_pages": []}
        for sid in e.get("src1", []):
            if sid in by_seqid:
                w, v = by_seqid[sid]
                t["d1_raw"].append({"key": f"{w}_{sid}", "value": v})
        pages = set()
        for sid in e.get("src2", []):
            if sid in seg:
                pages.add((seg[sid]["vol"], seg[sid]["page"]))
        for vol, pg in sorted(pages):
            png = AUD / f"v{vol}_p{pg}.png"
            if (vol, pg) not in rendered:
                if vol not in docs:
                    docs[vol] = fitz.open(str(ROOT / "sources" / "2" / VOLS[vol]))
                pix = docs[vol][pg].get_pixmap(dpi=170)
                pix.save(str(png))
                rendered.add((vol, pg))
            t["d2_pages"].append(str(png))
        tasks.append(t)

    per = args.per_task
    n_files = 0
    for i in range(0, len(tasks), per):
        json.dump({"tasks": tasks[i:i+per]},
                  open(AUD / f"task_{i//per:02d}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        n_files += 1
    print(json.dumps({"entries": len(tasks), "task_files": n_files,
                      "pages_rendered": len(rendered)}))

if __name__ == "__main__":
    main()
