# -*- coding: utf-8 -*-
"""S7i: apply the linguist's manual_review_ab.xlsx verdicts (2026-08-07).

Part A — mechanical actions interpreted by agents (checkpoints/shards/ab_actions.json,
adversarially verified): text_patch / rename / retag_tags / delete_entry.
Verify-flagged tasks 148/194/249 are corrected here (FIXUPS), structural
actions are skipped in Part A and hand-coded in Part B.

Part B — structural verdicts: merges of hidden pairs (сын, къайтар, айт, ий,
тур, jайыкъ), unglued articles (минералогия→мин, биядак→бла), splits
(дигил-мигил, къоянчакъ), new words (къурейш, сызлама, табанлатмакълыкъ,
щётка, вожатый, ауар), content move (эринлеринги чюйюр→эрин1).
Every block asserts the exact current state before touching it.
"""
import json, re, sys, io
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
SUB = ["misc1_proverbs", "misc1_riddles", "misc1_bukv", "misc1_folklore",
       "misc1_stem_note", "misc1_variants", "misc2_citations",
       "misc2_citations_periodical", "misc2_citations_collection",
       "misc2_proverb_illustr", "misc2_phras", "misc2_terms", "misc2_xref",
       "misc2_gram_note"]

def base_of(w):
    return re.sub(r"\d+$", "", w)

es = [json.loads(l) for l in open(CK / "06_lextagged.jsonl", encoding="utf-8")]
byid = {e["entry_id"]: e for e in es}
touched, dropped, new_entries = set(), set(), []
touched_bases = set()

def mark(e):
    e.setdefault("flags", [])
    if "ab_verdict" not in e["flags"]:
        e["flags"].append("ab_verdict")
    touched.add(e["entry_id"])

def patch(eid, field, old, new, count=1):
    e = byid[eid]
    v = e.get(field) or ""
    n = v.count(old)
    assert n == count, f"{eid}.{field}: {old!r} x{n}, expected {count}"
    e[field] = v.replace(old, new)
    mark(e)

def rename(eid, new_base):
    e = byid[eid]
    touched_bases.add(base_of(e["word"]))
    touched_bases.add(new_base)
    e["word"] = new_base
    e["word_base"] = new_base
    mark(e)

def delete(eid):
    e = byid[eid]
    touched_bases.add(base_of(e["word"]))
    dropped.add(eid)

def newcard(word_base, dict_id, **kw):
    e = {"word_base": word_base, "dict_id": dict_id, "tags": "", "def1": "",
         "def2": "", "misc1": "", "misc2": "", "src1": [], "src2": [],
         "word1_orig": None, "word2_orig": None, "decl": "",
         "hom_rank": kw.pop("hom_rank", 95), "flags": ["ab_verdict"],
         "word": word_base, "lextag": kw.pop("lextag", ""),
         "lextag_conf": "medium"}
    e.update(kw)
    new_entries.append(e)
    touched_bases.add(word_base)
    return e

def move_d1(src_id, dst_id, drop_src=True):
    """fold the d1 side of src entry into dst entry"""
    s, d = byid[src_id], byid[dst_id]
    assert s.get("src1"), f"{src_id} has no d1 side"
    assert not d.get("src1"), f"{dst_id} already has d1 side"
    for f in ("def1", "misc1", "decl"):
        if s.get(f):
            d[f] = s[f]
    if s.get("tags") and (s["tags"] or "") not in (d.get("tags") or ""):
        d["tags"] = f"{d['tags']}; {s['tags']}" if d.get("tags") else s["tags"]
    d["src1"] = s["src1"]
    d["word1_orig"] = s.get("word1_orig") or s["word"]
    d["dict_id"] = "both" if d.get("src2") or d.get("def2") or d.get("misc2") else "1"
    d["flags"] = [f for f in d.get("flags", []) if f not in ("no_d1_pair",)]
    mark(d)
    if drop_src:
        delete(src_id)

# ---------------- Part A: mechanical actions ----------------
acts = json.load(open(CK / "shards" / "ab_actions.json", encoding="utf-8"))["items"]
SKIP_TASKS = {148}                     # re-coded in Part B
FIX_194 = ("e_19873", "def1", "лаборантлаборантский", "лаборант || лаборантский")
seen_renames = {}
seen_patches, seen_retags = set(), set()
nA = Counter()
for it in acts:
    ti = it["task_index"]
    if ti in SKIP_TASKS:
        continue
    for a in it["actions"]:
        t = a["type"]
        if t in ("already_done", "structural"):
            nA[t] += 1
            continue
        if ti == 194 and t == "text_patch":
            patch(*FIX_194); nA["text_patch"] += 1
            continue
        if t == "text_patch":
            key = (a["entry_id"], a["field"], a["old"], a["new"])
            if key in seen_patches:
                continue
            seen_patches.add(key)
            patch(a["entry_id"], a["field"], a["old"], a["new"], a.get("count", 1))
        elif t == "rename":
            prev = seen_renames.get(a["entry_id"])
            if prev is not None:
                assert prev == a["new_word_base"], (a["entry_id"], prev, a["new_word_base"])
                continue
            seen_renames[a["entry_id"]] = a["new_word_base"]
            rename(a["entry_id"], a["new_word_base"])
        elif t == "retag_tags":
            key = (a["entry_id"], a["new"])
            if key in seen_retags:
                continue
            seen_retags.add(key)
            e = byid[a["entry_id"]]
            e["tags"] = a["new"]
            mark(e)
        elif t == "delete_entry":
            delete(a["entry_id"])
        nA[t] += 1
# verify-flagged 249: the missing rename
if "e_37818" not in seen_renames:
    rename("e_37818", "эjиклет"); nA["rename"] += 1
# task 146: latin homoglyphs in сау (verdict's space fix done above; homoglyph repair is standard)
e = byid["e_25535"]
for f in ("def1", "misc1", "misc2"):
    v = e.get(f) or ""
    if "caу" in v or "cау" in v:
        e[f] = v.replace("caу", "сау").replace("cау", "сау")
        mark(e)
print("Part A:", dict(nA))

# ---------------- Part B: structural ----------------
# 148: сына2 -> merge into сын3 (d2 verb 'Ломаться') per verdict + verify diagnosis
assert byid["e_27683"]["word"] == "сына2" and byid["e_27681"]["word"] == "сын3"
move_d1("e_27683", "e_27681")

# 253: къайытар -> merge into къайтар (obsolete «ы»)
assert byid["e_15845"]["word"] == "къайытар" and byid["e_15796"]["word"] == "къайтар"
move_d1("e_15845", "e_15796")

# 251: айтыргъа split — d1 verb part into айт1; e_02215 keeps only the d2 modal adverb
s, d = byid["e_02215"], byid["e_02183"]
assert d["word"] == "айт1" and d["dict_id"] == "2"
assert s["def2"].startswith("Кстати")
for f in ("def1", "misc1"):
    d[f] = s[f]; s[f] = ""
d["src1"] = s["src1"]; s["src1"] = []
d["word1_orig"] = s.get("word1_orig") or "айтыргъа"; s["word1_orig"] = None
d["dict_id"] = "both"; s["dict_id"] = "2"
d["decl"] = s.get("decl", ""); s["decl"] = ""
mark(d); mark(s)
touched_bases.update({"айт", "айтыргъа"})

# 131: ий3 -> merge into ий1
assert byid["e_12797"]["word"] == "ий3" and byid["e_12795"]["word"] == "ий1"
move_d1("e_12797", "e_12795")

# 255: турургъа -> merge into тур2; existing d1 noun «подъём» becomes its own card
t2 = byid["e_31401"]
assert t2["word"] == "тур2" and t2["def1"] == "подъём (утренний)"
noun = newcard("тур", "1", tags="", def1=t2["def1"], misc1=t2["misc1"],
               src1=t2["src1"], word1_orig=t2.get("word1_orig"),
               hom_rank=91, lextag=t2.get("lextag", ""))
noun["flags"].append("needs_review")
for f in ("def1", "misc1"):
    t2[f] = ""
t2["src1"] = []
mark(t2)
move_d1("e_31470", "e_31401")

# 3: jайыгъырга (verb) pairs with d2 жайыкъ; adjective side of e_00134 splits out
v134, v9758 = byid["e_00134"], byid["e_09758"]
assert v134["word"] == "jайыкъ" and v134["def1"].startswith("широкий")
assert v9758["def1"].startswith("1) развеяться")
adj = newcard("jайыкъ", "1", tags="", def1=v134["def1"], misc1=v134["misc1"],
              src1=v134["src1"], word1_orig=v134.get("word1_orig"),
              hom_rank=91, lextag=v134.get("lextag", ""))
for f in ("def1", "misc1"):
    v134[f] = ""
v134["src1"] = []
v134["dict_id"] = "2"
mark(v134)
move_d1("e_09758", "e_00134")

# 199: минералогия — unglue минерге verb material into «мин» (def1 empty there)
m, mineral = byid["e_21070"], byid["e_21118"]
assert m["word"] == "мин" and not m["def1"]
gd = mineral["def1"]
assert gd.startswith("минералогия ")
m["def1"] = gd[len("минералогия "):].replace("минерге ", "", 1)
if mineral.get("misc1"):
    m["misc1"] = mineral["misc1"] if not m.get("misc1") else f"{m['misc1']}; {mineral['misc1']}"
mineral["def1"] = "минералогия"
mineral["misc1"] = ""
mark(m); mark(mineral)

# 252: дигил split — колесо stays, мелочный goes to new «дигил-мигил»
dg = byid["e_10698"]
assert dg["word"] == "дигил"
d2p = [json.loads(l) for l in open(CK / "03_dict2_parsed.jsonl", encoding="utf-8")]
dm_src = [x for x in d2p if x.get("word") == "дигил-мигил"]
dm = newcard("дигил-мигил", "both", tags="ат. къарач.",
             def1="карач. пренебр. мелочный",
             misc1="дигил-мигил чот мелочи; мелочные затеи; дигил этерге мелочиться",
             src1=dg["src1"], word1_orig="дигил", hom_rank=95,
             lextag=dg.get("lextag", ""))
if dm_src:
    x = dm_src[0]
    dm["def2"] = x.get("def2", ""); dm["misc2"] = x.get("misc2", "")
    dm["src2"] = x.get("source_ids", []); dm["word2_orig"] = "дигил-мигил"
else:
    dm["def2"] = "Мелочь, пустяк"
    dm["misc2"] = ("Керексиз, бош, сан этмезча зат. Башалырлагъым излеуню, дигил-мигиллени, "
                   "хыйлалыкъны [Жандыу] кёрюп да болмайды. Хубийланы О., Аманат, III, 296. "
                   "▯ Дигил-мигил эт къарач. мелочиться / бош затла бла кюреш, керексиз ишле "
                   "этип айлан. Тиширыулада эрге бармайма деген да жокъду, жарашдырып эрге бара "
                   "билген да жокъду, дигил-мигил эте, къача-бугъа айланадыла. Лайпанланы С., Гургумлу, 109.")
    dm["flags"].append("needs_review")   # text supplied by linguist verdict, no source id yet
dg["def1"] = "балк. разг. колесо"
dg["misc1"] = ""
mark(dg)

# 260: къоянчакъ split into two homonyms
k = byid["e_17474"]
assert k["word"] == "къоянчакъ"
m2 = k.get("misc2") or ""
i_phr = m2.find("◊")
kb = newcard("къоянчакъ", "2", tags=k["tags"], def2="Болезнь сухожилий",
             misc2=m2[:i_phr].strip() if i_phr >= 0 else m2,
             src2=k["src2"], word2_orig=k.get("word2_orig"),
             hom_rank=2, lextag=k.get("lextag", ""))
kb["decl"] = k.get("decl", "")
k["def2"] = ""
k["misc2"] = m2[i_phr:].strip() if i_phr >= 0 else ""
k["src2"] = []
k["dict_id"] = "1"
k["hom_rank"] = 1
mark(k)

# 153: эринлеринги чюйюр — misc2 belongs to эрин1
s, d = byid["e_38353"], byid["e_38343"]
assert d["word"] == "эрин1"
if s.get("misc2"):
    d["misc2"] = (d.get("misc2") or "").rstrip() + " " + s["misc2"]
    d["src2"] = (d.get("src2") or []) + (s.get("src2") or [])
    mark(d)
delete("e_38353")

# 259: биядак — glued бла material split out (conservative, flagged for linguist)
b = byid["e_06577"]
assert b["word"] == "биядак"
bd1 = b["def1"]
i8 = bd1.find(" 8) ")
assert i8 > 0
bla_def = bd1[i8 + 1:]
b["def1"] = bd1[:i8].strip()                       # «пятак, грош»
bm = b.get("misc1") or ""
i_gl = bm.find(", образует сочетания")
keep1 = bm[:i_gl].strip() if i_gl >= 0 else bm
bla_m = bm[i_gl + 2:].strip() if i_gl >= 0 else ""
b["misc1"] = keep1
bla = newcard("бла", "1", tags="", def1=bla_def.replace("биядак", "бла"),
              misc1=bla_m.replace("биядак", "бла"),
              src1=b["src1"], word1_orig="бла", hom_rank=93, lextag="logic_and_function_words")
bla["flags"] += ["needs_review", "uncertain_ocr"]
mark(b)

# 147: сол — junk сол2 deleted by Part A; verify meanings intact on сол1 (nothing to pull: d1+d2 both present)
assert byid["e_26559"]["dict_id"] == "both"

# new words from misc moves (161 ауар, 228 сызлама, 229 табанлатмакълыкъ, 246 щётка, 168 вожатый, 261 къурейш)
def move_misc1_to_new(src_id, new_word, new_misc1, dict_id="1", **kw):
    s = byid[src_id]
    e = newcard(new_word, dict_id, misc1=new_misc1, lextag=kw.pop("lextag", s.get("lextag", "")), **kw)
    s["misc1"] = ""
    mark(s)
    return e

s = byid["e_04252"]; assert "ауар" in (s.get("misc1") or "")
move_misc1_to_new("e_04252", "ауар", "то же, что авар", src1=list(s["src1"]))
s = byid["e_27413"]; assert (s.get("misc1") or "").startswith("сызлама")
move_misc1_to_new("e_27413", "сызлама", "ломота, нытьё", dict_id="both", src1=list(s["src1"]))
s = byid["e_28347"]; assert "табанлатмакълыкъ" in (s.get("misc1") or "")
e = move_misc1_to_new("e_28347", "табанлатмакълыкъ", "", src1=list(s["src1"]))
e["tags"] = "отвлеч. к табанлатыргъа"
s = byid["e_37345"]                     # misc1 already truncated by task 246 text_patch
assert (s.get("misc1") or "") == "тж. силти", s.get("misc1")
sch = newcard("щётка", "1", def1="щётка, ёрш",
              misc1="тиш щётка зубная щётка; кийим щётка одёжная щётка",
              src1=list(s["src1"]), lextag="daily_life_and_food")
s = byid["e_08074"]                     # misc1 already cleared by task 168 text_patch
assert not (s.get("misc1") or "")
vozh = newcard("вожатый", "1", def1="вожатый (пионерского отряда)",
               src1=list(s["src1"]), lextag="economy_and_society")
s = byid["e_17690"]; assert (s.get("misc1") or "").startswith("къурейш")
move_misc1_to_new("e_17690", "къурейш", "къурейт бий уст. князь знатного рода",
                  dict_id="1", src1=list(s["src1"]), tags="уст.")

# unresolvable without sources — flag and report
for eid, why in (("e_02520", "статья акъыл отсутствует в OCR-экспорте словаря-1"),
                 ("e_38679", "статья эт-джен не найдена в экспорте словаря-1")):
    e = byid[eid]
    e.setdefault("flags", [])
    if "needs_review" not in e["flags"]:
        e["flags"].append("needs_review")
    mark(e)
print("Part B done")

# ---------------- finalize ----------------
es = [e for e in es if e["entry_id"] not in dropped] + new_entries
maxid = max(int(e["entry_id"][2:]) for e in es if e.get("entry_id"))
for i, e in enumerate(new_entries, 1):
    e["entry_id"] = f"e_{maxid + i:05d}"

grp = defaultdict(list)
for e in es:
    b = base_of(e["word"])
    if b in touched_bases:
        grp[b].append(e)
for b, g in grp.items():
    if len(g) == 1:
        g[0]["word"] = b
    else:
        g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both"))
        for i, x in enumerate(g, 1):
            x["word"] = f"{b}{i}"

dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
assert not dup, f"collisions: {dup[:10]}"
for e in es:
    if e["entry_id"] in touched:
        for k in SUB:
            e.pop(k, None)
with open(CK / "06_lextagged.jsonl", "w", encoding="utf-8") as f:
    for e in es:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
print(json.dumps({"entries": len(es), "deleted": len(dropped), "new": len(new_entries),
                  "touched": len(touched)}, ensure_ascii=False))
