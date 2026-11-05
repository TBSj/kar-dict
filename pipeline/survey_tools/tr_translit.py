"""Turkish-Latin KB spelling (Yılmaz Nevruz, "Karaçay-Malkar Türkçesinden Türkiye Türkçesine
Açıklamalı Büyük Sözlük") -> Karachay-Balkar Cyrillic candidates, optionally checked against the corpus.

Usage:
  tr_translit.py word1 "two words" ...            print Cyrillic candidates (best first)
  tr_translit.py --file words.txt                  one item per line; optional TAB + Turkish gloss
  add --lookup                                     check candidates against the corpus index
                                                   (lookup.py in the same folder) and print the best status
  add --verb                                       treat every -mak/-mek item as a verb (strip to stem)

Verb detection: an item ending in -mak/-mek gets two readings, the verb (KB imperative stem = item
minus -mak/-mek) and the noun (-макъ/-мек, e.g. бармакъ 'finger'); the verb is tried first when
--verb is given, when there is no gloss, or when the first chunk of the Turkish gloss (after TAB)
contains a -mak/-mek word; otherwise the noun is tried first. With --lookup the first HEAD wins.
Variants inside a headword ("Alka, alkan", "Kanıva / ganaba", "Alif (elif)") are split.

Letter mapping (author's spelling -> KB Cyrillic, Karachay orthography; corpus folds дж/ж, б/п, ё/е):
  a а | b б | c дж | ç ч | d д | e е (word-initial э) | f ф | g г (alt гъ next to back vowels)
  ğ гъ | h ħ х | ı ы | i и | j ж | k къ next to back vowels a ı o u, к next to front vowels (alt: the other)
  l л | m м | n н | ŋ ñ нг | o о | ö ё | p п | r р | s с | ş ш | t т | u у | ü ю
  v у (word-initial v -> в: Russian loans; alt в elsewhere) | y й ; y+vowel after a vowel or
  word-initially -> я ю ё е (alt й+vowel); but vowel+y+ü/ö -> йю/йё first (сюйюмчю, айю)
  | z з | â а, î и, û у (Arabic/Persian loans) | ~ in examples = the headword
  homonym indices (¹ ² ³, digits, trailing Roman I/II) are dropped.
Validated on 600 random headwords (seed 2026): 91% HEAD; the default (first) candidate is the
matching one in ~97% of HEAD cases; residual ambiguity is mostly k = к vs къ next to back vowels
(чабук, минафык, мусук, аккыллан) - resolved by trying alternatives against the corpus.
"""
import itertools
import re
import sys
from pathlib import Path

BACK = set("aıou")
FRONT = set("eiöü")
VOW = BACK | FRONT
SIMPLE = {"a": "а", "b": "б", "c": "дж", "ç": "ч", "d": "д", "f": "ф", "ğ": "гъ", "h": "х",
          "ı": "ы", "i": "и", "j": "ж", "l": "л", "m": "м", "n": "н", "ŋ": "нг", "o": "о",
          "ö": "ё", "p": "п", "r": "р", "s": "с", "ş": "ш", "t": "т", "u": "у", "ü": "ю",
          "z": "з", "x": "кс", "w": "у", "q": "къ"}
Y_VOWEL = {"a": "я", "u": "ю", "ü": "ю", "o": "ё", "ö": "ё", "e": "е"}
MAX_CAND = 24


def norm(w: str) -> str:
    w = w.strip().replace("I", "ı").replace("İ", "i").lower()
    w = w.replace("i̇", "i")  # combining dot left by lower() on İ
    w = w.translate(str.maketrans({"ħ": "h", "ñ": "ŋ", "â": "a", "î": "i", "û": "u", "ä": "a",
                                   "’": "", "'": "", "‘": "", "`": ""}))
    w = re.sub(r"[¹²³⁴\d]+", "", w)
    w = re.sub(r"\s+(?:ı{1,3}|iv|v)$", "", w)  # trailing Roman homonym numbers (I -> ı after norm)
    return re.sub(r"\s+", " ", w).strip(" .,;:!?~")


def nearest_vowel(w, i):
    """vowel of the syllable of position i: the next char if it is a vowel, else the previous
    vowel (k/g closing a syllable), else the first following vowel (initial cluster)."""
    if i + 1 < len(w) and w[i + 1] in VOW:
        return w[i + 1]
    p = _prev(w, i)
    if p:
        return p
    for j in range(i + 1, len(w)):
        if w[j] in VOW:
            return w[j]
        if w[j] in " -":
            break
    return None


def _prev(w, i):
    for j in range(i - 1, -1, -1):
        if w[j] in VOW:
            return w[j]
        if w[j] in " -":
            return None
    return None


def options(w):
    """list of option lists, one per source position group"""
    out = []
    i = 0
    n = len(w)
    while i < n:
        ch = w[i]
        prev = w[i - 1] if i > 0 else " "
        nxt = w[i + 1] if i + 1 < n else " "
        if ch == " " or ch == "-":
            out.append([ch])
        elif ch == "k":
            v = nearest_vowel(w, i)
            out.append(["къ", "к"] if (v in BACK) else ["к", "къ"])
        elif ch == "g":
            v = nearest_vowel(w, i)
            out.append(["г", "гъ"] if v in BACK else ["г"])
        elif ch == "e":
            out.append(["э", "е"] if prev in " -" else (["е", "э"] if prev in VOW else ["е"]))
        elif ch == "y":
            if nxt in Y_VOWEL and (prev in VOW or prev in " -"):
                iot, plain = Y_VOWEL[nxt], "й" + {"e": "е"}.get(nxt, SIMPLE.get(nxt, nxt))
                # front rounded vowels: KB writes сюйюмчю, юйюн, айю (й + ю/ё); back: боюнса, къая, мия
                out.append([plain, iot] if (nxt in "üö" and prev in VOW) else [iot, plain])
                i += 2
                continue
            out.append(["й"])
        elif ch == "v":
            if prev in " -" and nxt in VOW:
                out.append(["в", "у"])
            elif prev in VOW or nxt in VOW:
                out.append(["у", "в"])
            else:
                out.append(["у"])
        elif ch in SIMPLE:
            out.append([SIMPLE[ch]])
        else:
            out.append([ch])
        i += 1
    return out


def candidates(w):
    opts = options(w)
    # order: fewest non-default choices first
    alt_pos = [k for k, o in enumerate(opts) if len(o) > 1]
    res = []
    for nalt in range(0, len(alt_pos) + 1):
        for combo in itertools.combinations(alt_pos, nalt):
            s = "".join(o[1] if k in combo else o[0] for k, o in enumerate(opts))
            if s not in res:
                res.append(s)
            if len(res) >= MAX_CAND:
                return res
    return res


def items_for(raw, gloss=None, force_verb=False):
    """returns list of (reading, cyrillic candidates)"""
    w = norm(raw)
    w = re.split(r"\s+bk\.\s*", w)[0]
    readings = []
    m = re.match(r"^(.*?)\s*\((.+)\)\s*$", w)
    parts = [m.group(1), m.group(2)] if m else [w]
    expanded = []
    for p in parts:
        expanded += [x.strip() for x in re.split(r"[,/]", p) if x.strip()]
    first = re.split(r"[,;.:]", gloss)[0] if gloss else ""
    gl_verb = bool(re.search(r"\w(?:mak|mek)\b", first))
    for p in expanded:
        if re.search(r"(mak|mek)$", p) and len(p.split(" ")[-1]) > 4:
            stem = p[:-3]
            if force_verb or gl_verb or not gloss:
                readings += [("verb", stem), ("noun", p)]
            else:
                readings += [("noun", p), ("verb", stem)]
        else:
            readings.append(("word", p))
    return [(r, candidates(s)) for r, s in readings]


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    do_lookup = "--lookup" in args
    force_verb = "--verb" in args
    args = [a for a in args if a not in ("--lookup", "--verb")]
    rows = []
    if args and args[0] == "--file":
        for line in Path(args[1]).read_text(encoding="utf-8").splitlines():
            if line.strip():
                w, _, g = line.partition("\t")
                rows.append((w.strip(), g.strip() or None))
    else:
        rows = [(a, None) for a in args]
    if do_lookup:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lookup as L  # noqa: E402
        D = L.load()
        E, H, T = D["entries"], D["head"], D["tok"]
    stats = {"HEAD": 0, "NEAR": 0, "INSIDE": 0, "NONE": 0}
    for w, g in rows:
        its = items_for(w, g, force_verb)
        if not do_lookup:
            print(w, "->", " || ".join(f"{r}: " + " | ".join(c[:6]) for r, c in its))
            continue
        best = None
        rank = {"HEAD": 0, "INSIDE": 1, "NEAR": 2, "NONE": 3}
        for r, cands in its:
            for ci, c in enumerate(cands):
                k = L.fold(c)
                hit = H.get(k, set())
                if hit:
                    res = ("HEAD", c, L.fmt(hit, E, 2))
                elif ci < 12:
                    if " " in k:
                        ins = [i for i, e in enumerate(E) if k in e[3]]
                    else:
                        ins = T.get(k, [])
                    if ins:
                        txt = E[ins[0]][3]
                        p = txt.find(k)
                        res = ("INSIDE", c, f"x{len(ins)} [{E[ins[0]][0]}: …{txt[max(0, p - 30):p + 50]}…]")
                    else:
                        nr = L.near(k, H) if " " not in k else []
                        if nr:
                            nh = set()
                            for x in nr:
                                nh |= H[x]
                            res = ("NEAR", c, L.fmt(nh, E, 3))
                        else:
                            res = ("NONE", c, "")
                else:
                    continue
                if best is None or rank[res[0]] < rank[best[0]]:
                    best = res
                if best[0] == "HEAD":
                    break
            if best and best[0] == "HEAD":
                break
        stats[best[0]] += 1
        print(f"{w} | {best[0]} | {best[1]} | {best[2]}")
    if do_lookup:
        print("STATS", stats)


if __name__ == "__main__":
    main()
