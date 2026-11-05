"""Deterministic probe of every file in the dictionaries folder.

For each PDF: page count, metadata, TOC, text-layer coverage over a stride sample,
character statistics (Cyrillic share, mojibake / private-use indicators, KB digraphs),
and full text of a few sample pages. For .doc: antiword text dump.

Usage: python -I -X utf8 probe.py <src_dir> <out_dir>
Writes <out_dir>/probe.json and <out_dir>/samples/NN.txt (one per file).
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import fitz  # pymupdf

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
(OUT / "samples").mkdir(parents=True, exist_ok=True)

MOJI = set("ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ")
KB_DIGRAPHS = ["къ", "гъ", "нг", "дж", "кь", "гь", "уу", "ё"]


def char_stats(text):
    letters = cyr = lat = moji = pua = repl = 0
    for ch in text:
        o = ord(ch)
        if 0xE000 <= o <= 0xF8FF:
            pua += 1
        if ch == "�":
            repl += 1
        if ch in MOJI:
            moji += 1
        if ch.isalpha():
            letters += 1
            if 0x0400 <= o <= 0x04FF:
                cyr += 1
            elif o < 0x0250:
                lat += 1
    low = text.lower()
    dig = {d: low.count(d) for d in KB_DIGRAPHS}
    return {
        "letters": letters,
        "cyr_share": round(cyr / letters, 3) if letters else 0,
        "lat_share": round(lat / letters, 3) if letters else 0,
        "mojibake_chars": moji,
        "private_use_chars": pua,
        "replacement_chars": repl,
        "kb_digraphs": dig,
    }


def probe_pdf(path, idx):
    doc = fitz.open(path)
    n = doc.page_count
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    toc = doc.get_toc()[:60]
    stride = max(1, n // 40)
    sampled = list(range(0, n, stride))[:45]
    lens, imgs, all_text = [], [], []
    for p in sampled:
        page = doc[p]
        t = page.get_text("text")
        lens.append(len(t.strip()))
        try:
            imgs.append(len(page.get_images()))
        except Exception:
            imgs.append(-1)
        all_text.append(t)
    with_text = sum(1 for L in lens if L > 80)
    stats = char_stats("\n".join(all_text))
    # sample pages for agents
    picks = sorted(set([0, 1, 2, 3] + [int(n * f) for f in (0.04, 0.12, 0.3, 0.5, 0.7, 0.9)]))
    picks = [p for p in picks if 0 <= p < n]
    lines = [f"### FILE {idx:02d}: {path.name}", f"### pages={n}", ""]
    for p in picks:
        t = doc[p].get_text("text")
        lines.append(f"===== PAGE {p + 1} (1-based) chars={len(t)} =====")
        lines.append(t[:5000])
        lines.append("")
    (OUT / "samples" / f"{idx:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    w0, h0 = (doc[0].rect.width, doc[0].rect.height) if n else (0, 0)
    doc.close()
    return {
        "pages": n,
        "page_size_pt": [round(w0), round(h0)],
        "meta": meta,
        "toc_len": len(toc),
        "toc_head": toc[:25],
        "sampled_pages": len(sampled),
        "sampled_with_text": with_text,
        "text_coverage": round(with_text / len(sampled), 3) if sampled else 0,
        "median_chars_per_page": sorted(lens)[len(lens) // 2] if lens else 0,
        "images_per_page_median": sorted(imgs)[len(imgs) // 2] if imgs else 0,
        "chars": stats,
    }


def probe_doc(path, idx):
    try:
        out = subprocess.run(
            ["antiword", "-m", "UTF-8.txt", str(path)], capture_output=True, timeout=120
        )
        text = out.stdout.decode("utf-8", errors="replace")
        err = out.stderr.decode("utf-8", errors="replace")[:500]
    except Exception as e:  # noqa: BLE001
        text, err = "", repr(e)
    full = OUT / "samples" / f"{idx:02d}_full.txt"
    full.write_text(text, encoding="utf-8")
    head = text[:12000]
    mid = text[len(text) // 2 : len(text) // 2 + 6000]
    (OUT / "samples" / f"{idx:02d}.txt").write_text(
        f"### FILE {idx:02d}: {path.name}\n### antiword chars={len(text)} full text: {full}\n\n"
        f"===== HEAD =====\n{head}\n\n===== MIDDLE =====\n{mid}\n",
        encoding="utf-8",
    )
    return {"antiword_chars": len(text), "antiword_err": err, "full_text": str(full),
            "chars": char_stats(text)}


results = []
files = sorted(SRC.iterdir(), key=lambda p: p.name)
for i, f in enumerate(files, 1):
    rec = {"idx": i, "file": f.name, "path": str(f), "size_mb": round(f.stat().st_size / 1e6, 1)}
    try:
        if f.suffix.lower() == ".pdf":
            rec.update(probe_pdf(f, i))
        elif f.suffix.lower() == ".doc":
            rec.update(probe_doc(f, i))
        else:
            rec["note"] = "unsupported type"
    except Exception as e:  # noqa: BLE001
        rec["error"] = repr(e)
    results.append(rec)
    c = rec.get("chars", {})
    print(f"{i:02d} {rec['size_mb']:>6}MB pages={rec.get('pages', '-'):>5} "
          f"txt={rec.get('text_coverage', rec.get('antiword_chars', '-'))} "
          f"med={rec.get('median_chars_per_page', '-')} cyr={c.get('cyr_share', '-')} "
          f"moji={c.get('mojibake_chars', '-')} pua={c.get('private_use_chars', '-')} | {f.name[:70]}",
          flush=True)

(OUT / "probe.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
print("WROTE", OUT / "probe.json")
