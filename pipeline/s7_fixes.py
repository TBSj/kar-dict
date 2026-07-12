# -*- coding: utf-8 -*-
"""S7e: apply Fable-audit corrections + family J-propagation to 06_lextagged.jsonl.

Every text patch is exact-substring and asserts exactly one occurrence.
Family J-rule: dict1-only дж- words whose j-family base exists get the j too.
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

# (entry_id, field, old, new) — verified against PDF page scans by audit agents
PATCHES = [
    ("e_00546", "misc2", "бутларым къалтырап, балтакъларым талдыла", "бутларым къалтырап, билеклерим талмадыла"),
    ("e_00546", "misc2", "батыр, нарт къабакъ, сермешеди", "батыр, нарт кибик, сермешеди"),
    ("e_00076", "misc2", "«ким kumhuV» - деп", "«ким кимни?» — деп"),
    ("e_00076", "misc2", "Ныгъыш толкъусуз, ат жалкъасыз", "Ныгъыш талкъысыз, ат жалкъасыз"),
    ("e_00104", "misc2", "кеседи да, алай, патчахны кёлюн алырма", "кеседи да, алып, патчахны кёлюн алырма"),
    ("e_00692", "misc2", "«Элмюлк артельни юлгюлю уставы»", "«Эл мюлк артельни юлгюлю уставы»"),
    ("e_00048", "misc2", "Егюзге жалатыргъа билмегенди тюшюрюрге", "Егюзге жалатыргъа Билмегенди тюшюрюрге"),
    ("e_01042", "misc2", "Тартын дегенни къатланыучу", "Тартын 1 дегенни къатланыучу"),
    ("e_01205", "misc2", "«Нартла», 209. Сафар бла къызы", "«Нартла», 209. Сафир бла къызы"),
    ("e_00007", "misc2", "болду. ◊ Олимпиада оюнланы", "болду. ▯ Олимпиада оюнланы"),
    ("e_00066", "def1", "3) грам. аффикс, морфема", "аффикс, морфема"),
]
LEXTAG_FIXES = {
    "e_00097": "emotions_and_will",       # жалындырт < жалын 2 'умолять'
    "e_00692": "culture_and_spirituality",  # тамамлы 'основательный' — оценка качества
}

def main():
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byid = {e["entry_id"]: e for e in es}

    for eid, field, old, new in PATCHES:
        e = byid[eid]
        val = e.get(field) or ""
        n = val.count(old)
        assert n == 1, f"{eid}.{field}: expected 1 occurrence of {old!r}, found {n}"
        e[field] = val.replace(old, new)
        e.setdefault("flags", [])
        if "audit_fixed" not in e["flags"]:
            e["flags"].append("audit_fixed")
    for eid, tag in LEXTAG_FIXES.items():
        byid[eid]["lextag"] = tag
        byid[eid]["lextag_conf"] = "high"
        byid[eid]["lextag_src"] = "fable_audit"
    print(f"patches applied: {len(PATCHES)}, lextag fixes: {len(LEXTAG_FIXES)}")

    # ---- family J-propagation for dict1-only дж- words --------------------
    j_stems = sorted({re.sub(r"\d+$", "", e["word"]) for e in es if e["word"].startswith("j")},
                     key=len, reverse=True)
    renamed = []
    for e in es:
        w = e["word"]
        core = re.sub(r"\d+$", "", w)
        if not core.startswith("дж"):
            continue
        cand = "j" + core[2:]
        # family evidence: an existing j-word is a prefix of the candidate (base of the
        # derivative, >=4 chars incl. j) or the candidate is a prefix of an existing j-word
        fam = any((cand.startswith(s) and len(s) >= 5) or (s.startswith(cand) and len(cand) >= 5)
                  for s in j_stems)
        if fam:
            digits = w[len(core):]
            e["word"] = cand + digits
            e["word_base"] = cand
            e.setdefault("flags", [])
            if "j_family" not in e["flags"]:
                e["flags"].append("j_family")
            renamed.append((w, e["word"]))
    print(f"family J-propagation: {len(renamed)} words renamed")
    for r in renamed[:12]:
        print("  ", r[0], "->", r[1])

    # collision check after renames
    dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
    if dup:
        print("COLLISIONS to resolve:", dup)
        for w in dup:
            grp = [x for x in es if x["word"] == w]
            grp.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both"))
            for i, x in enumerate(grp, 1):
                x["word"] = f"{w}{i}"

    # drop renamed words from the manual zh/dzh queue
    q = CK / "review_queues" / "zh_dzh_unmatched.jsonl"
    if q.exists() and renamed:
        old_words = {r[0] for r in renamed} | {re.sub(r"\d+$", "", r[0]) for r in renamed}
        items = [json.loads(l) for l in open(q, encoding="utf-8")]
        keep = [it for it in items if it["word"].lower() not in old_words]
        with open(q, "w", encoding="utf-8") as f:
            for it in keep:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(f"zh/dzh queue: {len(items)} -> {len(keep)}")

    with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
        for e in es:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
