"""Check Karachay-Balkar words against the merged corpus (checkpoints/07_final.jsonl, 39,632 entries).

Usage:
  lookup.py word1 word2 "multi word phrase" ...      (any number; batch your queries)
  lookup.py --file words.txt                          (one query per line)

Folding applied to both sides (so spelling conventions do not hide matches):
  lowercase; ё->е; homonym digits / roman numerals dropped; кь->къ, гь->гъ (OCR);
  дж and ж -> j (corpus writes native дж/ж as Latin j); б and Latin b -> п (corpus writes final б/п as b);
  Latin homoglyphs a e o p c x y k m t -> Cyrillic.
  Infinitives (-ргъа/-рге/-ыргъа/-ирге/-уургъа ...) also tried as imperative stems
  (corpus headwords for verbs are imperative stems: бар, ишле, тап/таb).

Output per query, one line:
  HEAD  = exists as a headword (also matches original spellings word1_orig/word2_orig)
  NEAR  = no exact headword, but headwords at edit distance 1 (spelling variant / OCR?)
  INSIDE= not a headword, but the folded form occurs inside article texts (misc1/misc2 = examples,
          phrases, derivatives inside nests); phrases (with spaces) are searched as substrings
  NONE  = nothing found
"""
import json
import pickle
import re
import sys
from pathlib import Path

CORPUS = Path(r"D:/Projects/My_projects/Python/Py_projects/kar-dict/checkpoints/07_final.jsonl")
CACHE = Path(__file__).with_name("corpus_index.pkl")

HOMO = str.maketrans({"a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у",
                      "k": "к", "m": "м", "t": "т", "ё": "е", "ў": "у", "b": "п", "б": "п"})
ROMAN_TAIL = re.compile(r"\s+(?:[ivx]{1,4}|і{1,3})$")
ALPHA = "абвгдеёжзийклмнопрстуфхцчшщъыьэюяj"


def fold(w: str) -> str:
    w = w.strip().lower().replace("\u0301", "")
    w = re.sub(r"[\d¹²³⁴⁵⁶⁷⁸⁹]+$", "", w).strip()
    w = ROMAN_TAIL.sub("", w)
    w = w.replace("дж", "j")
    w = w.translate(HOMO)
    w = w.replace("ж", "j").replace("кь", "къ").replace("гь", "гъ")
    w = re.sub(r"\s+", " ", w)
    return w.strip(" .,;:!?()[]«»\"'")


def verb_stems(k: str):
    out = []
    m = re.match(r"^(.+?)(ргъа|рге|рга|ргьа)$", k)
    if not m:
        return out
    base = m.group(1)
    out.append(base)
    if base and base[-1] in "ыиуюае":  # epenthetic vowel, or aorist vowel (таб-ар-гъа)
        out.append(base[:-1])
    for b in list(out):
        if b.endswith("гъ"):
            out.append(b[:-2] + "къ")
        elif b.endswith("г"):
            out.append(b[:-1] + "к")
    return [x for x in dict.fromkeys(out) if len(x) >= 2]


def build():
    entries, head, tok = [], {}, {}
    with CORPUS.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            d = json.loads(line)
            gloss = (d.get("def1") or d.get("def2") or "")[:70]
            entries.append((d["word"], d.get("dict_id", ""), gloss,
                            fold((d.get("misc1") or "") + " || " + (d.get("misc2") or ""))))
            for w in {d["word"], d.get("word1_orig") or "", d.get("word2_orig") or ""}:
                if w:
                    head.setdefault(fold(w), set()).add(i)
            toks = set()
            for t in re.findall(r"[а-яj\-]+", entries[-1][3]):
                t = t.strip("-")
                if t:
                    toks.add(t)
                    toks.update(x for x in t.split("-") if x)
            for t in toks:
                tok.setdefault(t, []).append(i)
    data = {"entries": entries, "head": head, "tok": tok}
    with CACHE.open("wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    return data


def load():
    if CACHE.exists() and CACHE.stat().st_mtime > CORPUS.stat().st_mtime:
        with CACHE.open("rb") as f:
            return pickle.load(f)
    return build()


def near(k, head):
    res = set()
    for i in range(len(k) + 1):
        if i < len(k):
            c = k[:i] + k[i + 1:]
            if c in head:
                res.add(c)
        for a in ALPHA:
            if i < len(k) and a != k[i]:
                c = k[:i] + a + k[i + 1:]
                if c in head:
                    res.add(c)
            c = k[:i] + a + k[i:]
            if c in head:
                res.add(c)
    return sorted(res)[:6]


def fmt(idxs, E, n=3):
    return "; ".join(f"{E[i][0]}({E[i][1]}) «{E[i][2]}»" for i in sorted(idxs)[:n])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--file":
        args = [l.strip() for l in Path(args[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    D = load()
    E, H, T = D["entries"], D["head"], D["tok"]
    stats = {"HEAD": 0, "NEAR": 0, "INSIDE": 0, "NONE": 0}
    for q in args:
        k = fold(q)
        keys = [k] + verb_stems(k)
        hit = set()
        for kk in keys:
            hit |= H.get(kk, set())
        if hit:
            stats["HEAD"] += 1
            print(f"{q} | HEAD: {fmt(hit, E)}")
            continue
        nr = []
        for kk in keys:
            nr += near(kk, H)
        if " " in k:
            ins = [i for i, e in enumerate(E) if k in e[3]]
        else:
            ins = []
            for kk in keys:
                ins += T.get(kk, [])
        ins = sorted(set(ins))
        if ins:
            stats["INSIDE"] += 1
            ex = []
            for i in ins[:2]:
                txt = E[i][3]
                kk = next((x for x in keys if x in txt), k)
                p = txt.find(kk)
                ex.append(f"[{E[i][0]}: …{txt[max(0, p - 40):p + 60]}…]")
            extra = f" | near-heads: {', '.join(nr[:4])}" if nr else ""
            print(f"{q} | INSIDE x{len(ins)}: {' '.join(ex)}{extra}")
            continue
        if nr:
            stats["NEAR"] += 1
            nh = set()
            for x in nr:
                nh |= H[x]
            print(f"{q} | NEAR: {fmt(nh, E, 4)}")
            continue
        stats["NONE"] += 1
        print(f"{q} | NONE")
    print("STATS", json.dumps(stats))


if __name__ == "__main__":
    main()
