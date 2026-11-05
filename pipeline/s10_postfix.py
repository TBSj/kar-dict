# -*- coding: utf-8 -*-
"""S10c: explicit post-fixes after s10_hyphen.py / s10_pseudokeys.py (2026-11-05).

Every block asserts the state it expects, so the script refuses to run twice or on a
different corpus.  Sources for each fix: КБРС-1989 scan pages named in the comments
(checked by the pseudo-key agents, reports in shards/s10/pk_out) and the qmos export.
"""
import json, re, sys, io
from pathlib import Path
from collections import defaultdict, Counter

# stdout is already re-wrapped by the s10_hyphen import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from s10_hyphen import expand_tilde, kj, base_of, SUB  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
F06 = CK / "06_lextagged.jsonl"

es = [json.loads(l) for l in open(F06, encoding="utf-8")]
byid = {e["entry_id"]: e for e in es}
q = json.load(open(ROOT / "sources" / "1" / "qmos_def_32499.txt", encoding="utf-8"))
log, dropped, new_entries, bases, touched = [], set(), [], set(), set()


def get(eid, word):
    e = byid[eid]
    assert base_of(e["word"]) == base_of(word), (eid, e["word"], word)
    return e


def mark(e, fl="s10_postfix"):
    e.setdefault("flags", [])
    if fl not in e["flags"]:
        e["flags"].append(fl)
    touched.add(e.get("entry_id"))
    bases.add(base_of(e["word"]))


def cut(e, field, frag):
    t = e.get(field) or ""
    assert frag in t, (e["word"], field, frag, t[:200])
    e[field] = re.sub(r"\s*;\s*;", ";", t.replace(frag, "", 1)).strip(" ;")


def newcard(word, **kw):
    e = {"word": word, "word_base": word, "dict_id": "1", "tags": "", "def1": "", "def2": "", "misc1": "",
         "misc2": "", "src1": [], "src2": [], "word1_orig": None, "word2_orig": None, "decl": "",
         "hom_rank": 99, "lextag": "", "lextag_conf": "", "flags": ["s10_postfix"]}
    e.update(kw)
    new_entries.append(e)
    bases.add(word)
    return e


# A. bare headword left between separators after cutting a split word out of a host
#    («…; джан», «… ◆ той»): the merge had written «джан-къан …», the cut took «-къан …».
n_rem = 0
for e in es:
    if "hyphen_detached" not in (e.get("flags") or []):
        continue
    forms = {base_of(e["word"]).lower(), (e.get("word1_orig") or "").lower()}
    for sid in e.get("src1") or []:
        k = next((k for k in q if k.endswith(f"_{sid}")), None)
        if k:
            forms.add(kj(k.rsplit("_", 1)[0].lower()))
    for f in ("def1", "misc1"):
        t = e.get(f) or ""
        for w in sorted(filter(None, forms), key=len, reverse=True):
            pat = re.compile(r"(^|[;◊◆]\s*)" + re.escape(w) + r"(\s*\(\s*\))?\s*(?=$|[;◊◆])")
            while pat.search(t):
                t = pat.sub(r"\1", t, count=1)
                n_rem += 1
        t = re.sub(r"\s*[◊◆]\s*(?=$|;)", "", t)
        t = re.sub(r"(;\s*)+;", ";", t).strip(" ;◊◆")
        if t != (e.get(f) or ""):
            e[f] = t
            mark(e)
log.append({"fix": "A bare-headword remnants removed", "count": n_rem})

# B. linguist-restored кеп-керексиз / кеп-керти: tail «-керексиз;» left in misc1 and the
#    tilde was expanded as «кеп» (S0 parse of the restored headwords, shards/s10/s0_out)
e = get("e_14152", "кеп-керексиз")
assert e["misc1"].startswith("-керексиз;")
e["misc1"] = ("кеп-керексиз сёз лишний разговор; кеп-керексизге попусту; зря; кеп-керексизге къыйналдынг "
              "ты попусту трудился; кеп-керексиз урушду он отругал [меня] ни за что, ни про что")
e["word1_orig"] = "кеп-керексиз"
mark(e)
e = get("e_14153", "кеп-керти")
assert e["misc1"].startswith("-керти;")
e["misc1"] = "кеп-керти зат неопровержимый факт; кеп-кертисин айтыргъа сказать истинную правду"
e["word1_orig"] = "кеп-керти"
mark(e)
get("e_14154", "кеп-керти")["word1_orig"] = "кеп-керти"
log.append({"fix": "B кеп-керексиз / кеп-керти misc1 re-expanded"})

# C. сувенир_23482 + pseudo key сувенир_22315 = surviving tail of «саугъалыкъ» (КБРС с. 544–545);
#    its beginning («(-гъы) 1) отвлеч. к саугъа; 2) то, что предназначено для подарка; сувенир») was
#    not exported at all and is taken from the scan
e = get("e_27032", "сувенир")
assert sorted(e["src1"]) == [22315, 23482]
e["def1"] = "сувенир || сувенирный"
e["src1"] = [23482]
mark(e)
newcard("саугъалыкъ", decl="-гъы", src1=[22315], word1_orig="саугъалыкъ",
        def1="1) отвлеч. к саугъа 2) то, что предназначено для подарка; сувенир || подарочный, сувенирный",
        misc1="саугъалыкъ затла сувенирные изделия", flags=["s10_postfix", "pseudokey_fixed", "restored_from_scan"])
log.append({"fix": "C саугъалыкъ separated from сувенир"})

# D. саламат_22352 is «сау-саламат» (с. 546; «сау-» lost by the export) -> dict-2 сау-саламат1/2
s1, s2 = get("e_25022", "саламат"), get("e_25023", "саламат")
cut(s1, "def1", "; то же, что саламат")
cut(s1, "misc1", "; саламатма я жив здоров")
s1["src1"] = [21960]
mark(s1)
assert s2["src1"] == [22352]
for f in ("def1", "misc1", "decl"):
    s2[f] = ""
s2["src1"], s2["word1_orig"], s2["dict_id"] = [], None, "2"
mark(s2)
for eid, misc in (("e_25510", "сау-саламатма я жив-здоров"),
                  ("e_25511", "сау-саламат джетдик мы добрались целы и невредимы")):
    t = get(eid, "сау-саламат")
    assert t["dict_id"] == "2" and not t.get("src1")
    t["def1"], t["misc1"], t["src1"], t["word1_orig"], t["dict_id"] = "то же, что саламат", misc, [22352], "сау-саламат", "both"
    t["flags"] = [f for f in t.get("flags") or [] if f != "no_d1_pair"] + ["split_def1"]
    mark(t, "pseudokey_fixed")
log.append({"fix": "D сау-саламат: d1 22352 moved from саламат1/2 to сау-саламат1/2"})

# E. «целый_29409» = article «сау I» whose head «сау I 1) целый» was lost (с. 544 лев.):
#    meaning 1 -> dict-2 сау3 «Целый, неначатый, нераздельный», meaning 2 -> сау2 «Целый, весь»
raw = q["целый_29409"]
i2 = raw.index(" 2) весь, целый")
m1 = expand_tilde(raw[:i2].lstrip("; "), "сау", "")
m2 = expand_tilde(raw[i2 + len(" 2) весь, целый; полный;"):], "сау", "")
src = get("e_34968", "целый")
assert src["src1"] == [29409]
dropped.add(src["entry_id"])
for eid, d1, misc in (("e_25508", "1) целый; неначатый, нераздельный", m1.split(";", 1)[1].strip()),
                      ("e_25507", "2) весь, целый; полный", m2)):
    t = get(eid, "сау")
    assert t["dict_id"] == "2"
    t["def1"], t["misc1"], t["src1"], t["word1_orig"], t["dict_id"] = d1, kj(misc), [29409], "сау", "both"
    t["flags"] = [f for f in t.get("flags") or [] if f != "no_d1_pair"] + ["split_def1"]
    mark(t, "pseudokey_fixed")
log.append({"fix": "E сау I restored from pseudo key «целый»", "m1": m1[:80], "m2": m2[:80]})

# F. чубар_30302 «то же, что чуп-чубар» is the article «чуппа-чубар» (с. 738 прав.)
e = get("e_35980", "чубар")
cut(e, "def1", "; то же, что чуп-чубар")
e["src1"] = [30249]
mark(e)
cp = get("e_36050", "чуп-чубар")
newcard("чуппа-чубар", src1=[30302], word1_orig="чуппа-чубар", def1="то же, что чуп-чубар",
        lextag=cp.get("lextag", ""), lextag_conf="medium", flags=["s10_postfix", "pseudokey_fixed"])
log.append({"fix": "F чуппа-чубар separated from чубар"})

# G. сылтаучу_21750 = tail of байлам 3) «грам. союз» (с. 113)
t = get("e_05164", "байлам")
assert t["def1"].startswith("грам. союз")
t["misc1"] = t["misc1"].rstrip(" ;") + ("; сылтаучу байламла условные союзы; тенг джарашдырыучу байламла "
                                        "сочинительные союзы; байлам сёз союзное слово")
t["src1"] = sorted(set(t["src1"]) | {21750})
mark(t, "pseudokey_fixed")
p = get("e_27630", "сылтаучу")
assert p["src1"] == [21750] and p["dict_id"] == "1"
dropped.add(p["entry_id"])
bases.add("сылтаучу")
log.append({"fix": "G сылтаучу tail -> байлам3, false homonym сылтаучу2 dropped"})

# H. чинар_30444 (OCR for «чынар», с. 743 лев.) -> dict-2 чынар1 «Бук, чинара»
d1 = get("e_35781", "чынар")
t = get("e_36249", "чынар")
assert d1["src1"] == [30444] and t["dict_id"] == "2" and t["def2"].startswith("1. Бук")
t["def1"], t["misc1"], t["src1"], t["word1_orig"], t["dict_id"] = d1["def1"], d1["misc1"], [30444], "чынар", "both"
t["flags"] = [f for f in t.get("flags") or [] if f != "no_d1_pair"]
mark(t, "pseudokey_fixed")
dropped.add(d1["entry_id"])
log.append({"fix": "H чынар: d1 merged into dict-2 чынар1"})

# I. джёрмелениу (d1) = жёрмелениу (d2): matched pair -> j
e = get("e_12089", "жёрмелениу")
bases.add("жёрмелениу")
e["word"] = e["word_base"] = "jёрмелениу"
mark(e)
log.append({"fix": "I жёрмелениу -> jёрмелениу"})

# J. эт-jен: needs_review was set because the article was missing from the dict-1 export — now restored
e = get("e_38679", "эт-jен")
e["flags"] = [f for f in e["flags"] if f != "needs_review"]
mark(e)
log.append({"fix": "J эт-jен needs_review cleared"})

# finalize
es = [e for e in es if e["entry_id"] not in dropped] + new_entries
maxid = max(int(e["entry_id"][2:]) for e in es if e.get("entry_id"))
for i, e in enumerate(new_entries, 1):
    e["entry_id"] = f"e_{maxid + i:05d}"
    touched.add(e["entry_id"])
grp = defaultdict(list)
for e in es:
    if base_of(e["word"]) in bases:
        grp[base_of(e["word"])].append(e)
for b, g in grp.items():
    g.sort(key=lambda x: (x.get("hom_rank", 99), x.get("dict_id") != "both", x["entry_id"]))
    for i, x in enumerate(g, 1):
        x["word"] = b if len(g) == 1 else f"{b}{i}"
dup = [w for w, n in Counter(x["word"] for x in es).items() if n > 1]
assert not dup, dup[:10]
for e in es:
    if e["entry_id"] in touched:
        for k in SUB:
            e.pop(k, None)
with open(F06, "w", encoding="utf-8") as f:
    for e in es:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
with open(CK / "qa" / "s10_postfix.jsonl", "w", encoding="utf-8") as f:
    for r in log:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(json.dumps({"entries": len(es), "dropped": len(dropped), "new": len(new_entries), "touched": len(touched)},
                 ensure_ascii=False))
for r in log:
    print(" ", json.dumps(r, ensure_ascii=False)[:200])
