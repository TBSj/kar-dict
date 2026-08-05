# -*- coding: utf-8 -*-
"""S7e: apply Fable-audit corrections + family J-propagation to 06_lextagged.jsonl.

Full-run audit 2026-08-04 (60 entries, 20 Fable agents, page-verified).
PATCHES use current-run entry_ids and assert exact occurrence counts.
PILOT_PATCHES carry over the pilot's page-verified fixes by unique substring
(entry_ids changed between runs); a pilot fix already absorbed by the hardened
S2 prompts simply doesn't match and is skipped.
After text patches, extracted misc-subfields of touched entries are dropped so
s6_apply can re-extract them fresh (◊→▯ fixes change phras splits).
"""
import json, re, sys, io
from pathlib import Path
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"

# (entry_id, field, old, new) — verified against PDF page scans by audit agents
PATCHES = [
    ("e_18019", "misc2", "Къууумну man ётдюрюу", "Къууумну тап ётдюрюу"),
    ("e_23165", "misc2", "Ши неда аман болмагъан", "Иги неда аман болмагъан"),
    ("e_23165", "misc2", "сын таил кёрюнёди", "сын таш кёрюнеди"),
    ("e_00076", "misc2", "ними хычауман, ними да никкола", "кими хычауман, кими да никкола"),
    ("e_00076", "misc2", "59. О Адамла", "59. ▯ Адамла"),
    ("e_00176", "misc2", "тубан кёкшо", "тубан кёкню"),
    ("e_00176", "misc2", "Емюрлюк", "Ёмюрлюк"),
    ("e_00185", "misc2", "стансе жерлени альт", "стансе жерлени алып"),
    ("e_04091", "misc2", "Байрамукъланы X.", "Байрамукъланы Х."),  # латинская X -> Х
    ("e_11070", "misc2", "Къаракюбюр", "Къара кюбюр"),
    ("e_00972", "misc2", "am сирелди", "ат сирелди"),
    ("e_00972", "misc2", "185. ◊ [Жанчыкъ:]", "185. ▯ [Жанчыкъ:]"),
    ("e_21107", "misc2", "may башында", "тау башында"),
    ("e_17362", "misc2", "man жерчиклеринде", "тап жерчиклеринде"),
    ("e_07889", "misc2", "хуржунунба", "хуржунунда"),
    ("e_06502", "misc2", "Ахмагъны", "Ахматны"),
    ("e_06502", "misc2", "Елчелеулери", "Ёлчелеулери"),
    ("e_06773", "misc2", "Налъчикден", "Нальчикден"),
    ("e_24435", "misc1", "удовлет ворённость", "удовлетворённость"),
    ("e_24435", "misc1", "разылыкъгьынгы", "разылыкъгъынгы"),
    ("e_06404", "misc2", "311. ◊ Халкъны", "311. ▯ Халкъны"),
    ("e_00888", "misc2", "43. ◊ Артда", "43. ▯ Артда"),
    ("e_00888", "misc2", "11. ◊ Бислиймат", "11. ▯ Бислиймат"),
    ("e_01335", "def1", "-то; V, присоединяемая", "-то; частица, присоединяемая"),
    ("e_29613", "def2", "2. Красть, присваивать", "2. къарач. Красть, присваивать"),
    ("e_02623", "misc1", "у негопрекрасное", "у него прекрасное"),
    ("e_02623", "misc1", "болмагьан", "болмагъан"),
    ("e_00176", "tags", "эт. понуд. от жаланла", "эт. понуд. от жаланла; понуд. к джаланларгъа"),
    ("e_37028", "tags", "шохайлашыр-гъа", "шохайлашыргъа"),
]
# replace-all with an exact expected count (tilde mis-expansions etc.)
PATCHES_N = [
    ("e_06404", "misc1", "бирлики", "бирлиги", 3),
]
# pilot fixes, re-applied by unique substring; silently skipped when the
# hardened S2 prompt already produced the correct text
PILOT_PATCHES = [
    ("misc2", "бутларым къалтырап, балтакъларым талдыла", "бутларым къалтырап, билеклерим талмадыла"),
    ("misc2", "батыр, нарт къабакъ, сермешеди", "батыр, нарт кибик, сермешеди"),
    ("misc2", "«ким kumhuV» - деп", "«ким кимни?» — деп"),
    ("misc2", "Ныгъыш толкъусуз, ат жалкъасыз", "Ныгъыш талкъысыз, ат жалкъасыз"),
    ("misc2", "кеседи да, алай, патчахны кёлюн алырма", "кеседи да, алып, патчахны кёлюн алырма"),
    ("misc2", "«Элмюлк артельни юлгюлю уставы»", "«Эл мюлк артельни юлгюлю уставы»"),
    ("misc2", "Егюзге жалатыргъа билмегенди тюшюрюрге", "Егюзге жалатыргъа Билмегенди тюшюрюрге"),
    ("misc2", "Тартын дегенни къатланыучу", "Тартын 1 дегенни къатланыучу"),
    ("misc2", "«Нартла», 209. Сафар бла къызы", "«Нартла», 209. Сафир бла къызы"),
    ("misc2", "болду. ◊ Олимпиада оюнланы", "болду. ▯ Олимпиада оюнланы"),
    ("def1", "3) грам. аффикс, морфема", "аффикс, морфема"),
]
LEXTAG_FIXES = {
    "e_00076": "language_and_communication",  # jаздыр1 — понуд. от жаз-3 'писать'
    "e_04091": "actions_and_activities",      # атдыр1 — понуд. от ат 'бросать/стрелять'
    "e_00856": "living_things",               # jортууукъ — 'рысак || рысистый'
    "e_06773": "social_relations",            # болушдуртуу — 'заставить помогать'
    "e_06404": "social_relations",            # бирлик — 'единство, общность'
    "e_03923": "objects_and_technology",      # асмалыкъ — 'висячий, подвесной'
}
SUBFIELD_KEYS = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
                 "misc1_stem_note", "misc1_variants",
                 "misc2_citations", "misc2_citations_periodical",
                 "misc2_citations_collection", "misc2_proverb_illustr",
                 "misc2_phras", "misc2_terms", "misc2_xref", "misc2_gram_note"]

def mark(e):
    e.setdefault("flags", [])
    if "audit_fixed" not in e["flags"]:
        e["flags"].append("audit_fixed")

def main():
    es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
    byid = {e["entry_id"]: e for e in es}
    touched = set()

    for eid, field, old, new in PATCHES:
        e = byid[eid]
        val = e.get(field) or ""
        n = val.count(old)
        assert n == 1, f"{eid}.{field}: expected 1 occurrence of {old!r}, found {n}"
        e[field] = val.replace(old, new)
        mark(e); touched.add(eid)
    for eid, field, old, new, want in PATCHES_N:
        e = byid[eid]
        val = e.get(field) or ""
        n = val.count(old)
        assert n == want, f"{eid}.{field}: expected {want} occurrences of {old!r}, found {n}"
        e[field] = val.replace(old, new)
        mark(e); touched.add(eid)

    applied_pilot = skipped_pilot = 0
    for field, old, new in PILOT_PATCHES:
        hits = [e for e in es if old in (e.get(field) or "")]
        if not hits:
            skipped_pilot += 1
            continue
        assert len(hits) == 1, f"pilot patch {old!r}: {len(hits)} entries match"
        e = hits[0]
        assert e[field].count(old) == 1
        e[field] = e[field].replace(old, new)
        mark(e); touched.add(e["entry_id"])
        applied_pilot += 1

    for eid, tag in LEXTAG_FIXES.items():
        byid[eid]["lextag"] = tag
        byid[eid]["lextag_conf"] = "high"
        byid[eid]["lextag_src"] = "fable_audit"

    # ---- audit-verified word-form repairs ---------------------------------
    # шохайлашмакьлыкъ: «кь» — OCR-артефакт, в орфографии только «къ»
    e = byid["e_37028"]
    assert e["word"] == "шохайлашмакьлыкъ"
    e["word"] = e["word_base"] = "шохайлашмакълыкъ"
    e["word1_orig"] = "шохайлашмакълыкъ"
    mark(e); touched.add("e_37028")

    # КЪУУУМ (три «у», стр. 737 т.2): ТСКБЯ «къуум» — OCR-потеря «у».
    # КЪУУУМ-2 'Предположение' = слово-1 «къууум» — сливаем в одну карточку.
    g1, g2, d1e = byid["e_18019"], byid["e_18020"], byid["e_18034"]
    assert g1["word"] == "къуум1" and g2["word"] == "къуум2" and d1e["word"] == "къууум"
    d1e.update({
        "dict_id": "both",
        "tags": g2["tags"] if not d1e.get("tags") else f"{g2['tags']}; {d1e['tags']}",
        "def2": g2["def2"], "misc2": g2["misc2"],
        "src2": g2["src2"], "word2_orig": "къууум", "hom_rank": 2,
    })
    mark(d1e); touched.add("e_18034")
    g1.update({"word_base": "къууум", "word": "къууум1", "word2_orig": "къууум",
               "hom_rank": 1})
    mark(g1); touched.add("e_18019")
    d1e["word"] = "къууум2"
    es = [x for x in es if x["entry_id"] != "e_18020"]
    print(f"patches: {len(PATCHES) + len(PATCHES_N)} strict, {applied_pilot} pilot applied, "
          f"{skipped_pilot} pilot obsolete; lextag fixes: {len(LEXTAG_FIXES)}; "
          f"куум merged -> {len(es)} entries")

    # drop extracted subfields of touched entries -> s6_apply re-extracts
    for eid in touched:
        if eid in byid:
            for k in SUBFIELD_KEYS:
                byid[eid].pop(k, None)

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
