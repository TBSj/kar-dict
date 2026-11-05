"""Prepare shared survey data: full text-layer dumps, qmos headword list, corpus headword sample."""
import json
import random
import re
import sys
from pathlib import Path

import fitz

SV = Path(sys.argv[1])
REPO = Path(r"D:/Projects/My_projects/Python/Py_projects/kar-dict")
probe = json.loads((SV / "probe" / "probe.json").read_text(encoding="utf-8"))
(SV / "text").mkdir(exist_ok=True)
(SV / "reports").mkdir(exist_ok=True)
(SV / "verify").mkdir(exist_ok=True)
(SV / "png").mkdir(exist_ok=True)

for rec in probe:
    if rec["idx"] in (28, 29, 30):
        continue
    if rec["file"].lower().endswith(".pdf") and rec.get("text_coverage", 0) > 0.5:
        doc = fitz.open(rec["path"])
        out = []
        for i in range(doc.page_count):
            out.append(f"===== PAGE {i + 1} =====\n{doc[i].get_text('text')}")
        (SV / "text" / f"{rec['idx']:02d}.txt").write_text("\n".join(out), encoding="utf-8")
        print("dumped", rec["idx"], doc.page_count, "pages")
        doc.close()
    elif rec["file"].lower().endswith(".doc"):
        src = SV / "probe" / "samples" / f"{rec['idx']:02d}_full.txt"
        (SV / "text" / f"{rec['idx']:02d}.txt").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print("copied doc", rec["idx"])

# qmos (dict-1 digital export) headwords: word<TAB>seqid
q = json.loads((REPO / "sources/1/qmos_def_32499.txt").read_text(encoding="utf-8"))
lines = []
for k in q:
    m = re.match(r"^(.*)_(\d+)$", k)
    lines.append(f"{m.group(1)}\t{m.group(2)}" if m else f"{k}\t")
(SV / "qmos_heads.txt").write_text("\n".join(lines), encoding="utf-8")
print("qmos heads", len(lines))

# corpus headword sample (deterministic) for reverse-coverage checks
words = []
with (REPO / "checkpoints/07_final.jsonl").open(encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        words.append(f"{d['word']}\t{d['dict_id']}\t{d.get('word1_orig') or ''}\t{d.get('word2_orig') or ''}\t{(d.get('def1') or d.get('def2') or '')[:60]}")
random.seed(20261103)
sample = random.sample(words, 400)
(SV / "corpus_sample_400.tsv").write_text("word\tdict_id\tword1_orig\tword2_orig\tgloss\n" + "\n".join(sample), encoding="utf-8")
print("corpus sample 400 of", len(words))
