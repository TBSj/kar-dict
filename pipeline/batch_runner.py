# -*- coding: utf-8 -*-
"""
batch_runner.py — прогон LLM-этапов конвейера kar-dict через Anthropic Message
Batches API (скидка 50% к ценам Messages API).

Заменяет Claude-Code-workflow-агентов пилота: каждый входной шард уходит одним
запросом Messages API внутри батча; JSON-ответ модели записывается в выходной
шард РОВНО в том формате, который ждут детерминированные скрипты конвейера
(s0_qa, s3_match, s4_merge --finalize, s5_prepare --finalize, s3b_apply, ...).

Требуется: pip install anthropic; переменная окружения ANTHROPIC_API_KEY
(ключ из Console с биллингом — подписочный логин Claude Code для Batch API не подходит).

ПОСЛЕДОВАТЕЛЬНОСТЬ ПОЛНОГО ПРОГОНА (см. также docs/PILOT_REPORT.md §7)

  0.  python pipeline/batch_runner.py init        # архив пилотных шардов -> shards_pilot/
  1.  python pipeline/s0_dict1_preparse.py --slice all --batch-size 40
      python pipeline/batch_runner.py estimate --stage s0
      python pipeline/batch_runner.py submit   --stage s0
      python pipeline/batch_runner.py watch    --stage s0
      python pipeline/s0_qa.py                    # ворота: покрытие >= 0.99
      # неудачные шарды: batch_runner.py retry --stage s0 [--model claude-opus-4-8]
  2.  python pipeline/s2_make_batches.py --slice all --batch-size 12
      submit/watch --stage s2;  python pipeline/s2_qa.py   # ворота: регресс "таукелсиз"
  3.  python pipeline/s3_match.py --slice all
      # собрать shards/s3b_verbs_in.json и shards/s3b_zhdzh_in.json из review_queues
      submit/watch --stage s3b_verbs_sonnet;  submit/watch --stage s3b_verbs_opus
      python pipeline/batch_runner.py merge-verbs          # согласие->verbs.json
      submit/watch --stage s3b_zhdzh
      python pipeline/s3b_apply.py
  4.  python pipeline/s4_merge.py --prepare
      submit/watch --stage s4;  python pipeline/s4_merge.py --finalize
  5.  python pipeline/s5_prepare.py
      submit/watch --stage s5;  python pipeline/s5_prepare.py --finalize
      python pipeline/s5_consistency.py
      submit/watch --stage s5_rejudge
      python pipeline/s5_consistency.py --apply-rejudge;  python pipeline/s5_repair.py
  6.  python pipeline/s6_apply.py                 # таксономия misc по правилам пилота, БЕЗ LLM
      python pipeline/s7_invariants.py            # ворота: только известные benign-проблемы
      python pipeline/s7_export.py                # -> 07_final.jsonl + final.csv
  7.  # аудит по сканам: нужны PDF ТСКБЯ в sources/2 + pip install pymupdf
      python pipeline/s7_audit_prep.py --n 60 --per-task 3
      submit/watch --stage s7_audit               # vision-батч: страницы PNG прикладываются к запросу
      # триаж вердиктов вручную/в сессии -> точечные правки в PATCHES (s7_fixes.py),
      # затем снова s7_export + s7_invariants; страница обзора:
      python pipeline/s7_review_data.py;  python pipeline/s7_build_review.py

Команды: init | estimate | submit | status | fetch | watch | retry | merge-verbs | cancel
Все команды принимают --stage (кроме init/merge-verbs). submit поддерживает
--limit N (дымовой тест на N шардов), --dry-run, --model/-­-effort/--max-tokens.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CK = ROOT / "checkpoints"
SHARDS = CK / "shards"
STATE_DIR = CK / "batch_state"
FAILED_DIR = STATE_DIR / "failed"
PARTS_DIR = STATE_DIR / "parts"

# ---------------------------------------------------------------- конфигурация

SONNET = "claude-sonnet-4-6"   # пилотная модель; дешевле: "claude-sonnet-5" (интро-цены до 2026-08-31)
OPUS = "claude-opus-4-8"
FABLE = "claude-fable-5"       # финальный аудит (как в пилоте); при недоступности: --model claude-opus-4-8

PRICES = {  # $ за 1M токенов (вход, выход) — ПОЛНАЯ цена, батч-скидка применяется отдельно
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-5": (2.0, 10.0),      # интро до 2026-08-31, далее (3.0, 15.0)
    "claude-opus-4-8": (5.0, 25.0),
    "claude-fable-5": (10.0, 50.0),
}
BATCH_DISCOUNT = 0.5

LEXTAGS = {
    "universe_and_nature", "living_things", "human_body", "mind_and_cognition",
    "emotions_and_will", "social_relations", "culture_and_spirituality",
    "language_and_communication", "actions_and_activities", "objects_and_technology",
    "daily_life_and_food", "economy_and_society", "space_and_time",
    "logic_and_function_words",
}

BATCH_NOTE = (
    "РЕЖИМ БАТЧ-ОБРАБОТКИ: у тебя НЕТ файловой системы. Содержимое входного файла "
    "дано в сообщении пользователя как JSON. Вместо записи результата в файл верни "
    "СОДЕРЖИМОЕ выходного файла — один JSON-объект ровно того вида, что описан в "
    "инструкции, — и это должен быть ВЕСЬ твой ответ: без пояснений, без markdown-"
    "ограждений, без какого-либо текста до или после JSON."
)

# out_ratio: отношение байт выхода к байтам входа, замерено на пилотных шардах
STAGES = {
    "s0": dict(kind="sharded", prompt="s0_parse.md", in_dir="s0_in", out_dir="s0_out",
               model=SONNET, effort="medium", max_tokens=24000, top_key="entries",
               out_ratio=0.95,
               prepare_hint="python pipeline/s0_dict1_preparse.py --slice all --batch-size 40"),
    "s2": dict(kind="sharded", prompt="s2_parse.md", in_dir="s2_in", out_dir="s2_out",
               model=SONNET, effort="medium", max_tokens=24000, top_key="entries",
               out_ratio=0.92,
               prepare_hint="python pipeline/s2_make_batches.py --slice all --batch-size 12"),
    "s4": dict(kind="sharded", prompt="s4_merge.md", in_dir="s4_in", out_dir="s4_out",
               model=OPUS, effort="high", max_tokens=32000, top_key="groups",
               out_ratio=1.0,
               prepare_hint="python pipeline/s4_merge.py --prepare"),
    "s5": dict(kind="sharded", prompt="s5_lextag.md", in_dir="s5_in", out_dir="s5_out",
               model=SONNET, effort="medium", max_tokens=16000, top_key="items",
               out_ratio=0.30,
               prepare_hint="python pipeline/s5_prepare.py"),
    "s3b_verbs_sonnet": dict(kind="single", prompt="s3b_verbs.md",
                             in_file="s3b_verbs_in.json", out_file="s3b_out/verbs_sonnet.json",
                             model=SONNET, effort="medium", max_tokens=16000,
                             top_key="items", chunk_size=60, key_field="word", out_ratio=0.7,
                             prepare_hint="см. PILOT_REPORT §7 шаг 3 (json-дамп очереди only1_verbs)"),
    "s3b_verbs_opus": dict(kind="single", prompt="s3b_verbs.md",
                           in_file="s3b_verbs_in.json", out_file="s3b_out/verbs_opus.json",
                           model=OPUS, effort="high", max_tokens=16000,
                           top_key="items", chunk_size=60, key_field="word", out_ratio=0.7,
                           prepare_hint="см. PILOT_REPORT §7 шаг 3 (json-дамп очереди only1_verbs)"),
    "s3b_zhdzh": dict(kind="single", prompt="s3b_zhdzh.md",
                      in_file="s3b_zhdzh_in.json", out_file="s3b_out/zhdzh.json",
                      model=OPUS, effort="high", max_tokens=24000,
                      top_key="items", chunk_size=120, key_field="word", out_ratio=0.5,
                      prepare_hint="см. PILOT_REPORT §7 шаг 3 (json-дамп очереди zh_dzh_unmatched)"),
    "s5_rejudge": dict(kind="single", prompt="s5_lextag.md",
                       in_file="s5_rejudge_in.json", out_file="s5_rejudge_out.json",
                       model=OPUS, effort="high", max_tokens=32000,
                       top_key="items", chunk_size=150, key_field="entry_id", out_ratio=0.1,
                       prepare_hint="python pipeline/s5_consistency.py"),
    "s7_audit": dict(kind="audit", prompt="s7_audit.md",
                     model=FABLE, effort="high", max_tokens=32000,
                     top_key="audits", out_ratio=0.3,
                     prepare_hint="python pipeline/s7_audit_prep.py --n 60 --per-task 3 "
                                  "(нужны PDF в sources/2 и pip install pymupdf)"),
}

AUDIT_DIR_REL = ("qa", "audit")

AUDIT_NOTE = (
    "К сообщению приложены PNG-изображения страниц ТСКБЯ: в JSON задания поле d2_pages "
    "содержит ИМЕНА файлов, а сами изображения идут после JSON, каждое с текстовой "
    "подписью-именем. Сверяй статьи с этими изображениями."
)

# --------------------------------------------------------------------- утилиты


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_client():
    try:
        import anthropic
    except ImportError:
        sys.exit("Не установлен пакет anthropic: .venv\\Scripts\\pip install anthropic")
    return anthropic.Anthropic()


def state_path(stage):
    return STATE_DIR / f"{stage}.json"


def load_state(stage):
    p = state_path(stage)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"stage": stage, "batches": [], "shards": {}, "usage": {}}


def save_state(stage, st):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = state_path(stage).with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(state_path(stage))


def read_prompt(cfg):
    return (ROOT / "pipeline" / "prompts" / cfg["prompt"]).read_text(encoding="utf-8")


def dump_json(obj):
    return json.dumps(obj, ensure_ascii=False)


def extract_json(text):
    """Достаёт JSON-объект из ответа модели (терпимо к ограждениям/преамбуле)."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        return json.loads(t[a:b + 1])
    raise json.JSONDecodeError("no JSON object found", t[:200], 0)


# --------------------------------------------------- перечисление единиц работы


def list_units(stage, cfg):
    """Возвращает [(unit_id, payload_list)] — по одному на запрос к API."""
    units = []
    if cfg["kind"] == "sharded":
        in_dir = SHARDS / cfg["in_dir"]
        files = sorted(in_dir.glob("batch_*.json"))
        if not files:
            sys.exit(f"[{stage}] входных шардов нет в {in_dir}.\n"
                     f"Сначала: {cfg['prepare_hint']}")
        for f in files:
            units.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
    elif cfg["kind"] == "audit":
        aud = CK.joinpath(*AUDIT_DIR_REL)
        files = sorted(aud.glob("task_*.json"))
        if not files:
            sys.exit(f"[{stage}] нет файлов заданий в {aud}.\nСначала: {cfg['prepare_hint']}")
        for f in files:
            units.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
    else:
        in_file = SHARDS / cfg["in_file"]
        if not in_file.exists():
            sys.exit(f"[{stage}] нет входного файла {in_file}.\nСначала: {cfg['prepare_hint']}")
        data = json.loads(in_file.read_text(encoding="utf-8"))
        items = data["items"] if isinstance(data, dict) else data
        cs = cfg["chunk_size"]
        for i in range(0, len(items), cs):
            units.append((f"chunk_{i // cs:04d}", items[i:i + cs]))
    return units


def unit_keys(cfg, payload):
    """Ключи входных элементов для валидации ответа."""
    kf = cfg.get("key_field")
    if kf and isinstance(payload, list):
        return [str(x[kf]) for x in payload]
    return None


def content_text_chars(content):
    """(символов текста, число изображений) в содержимом сообщения."""
    if isinstance(content, str):
        return len(content), 0
    chars = sum(len(b.get("text", "")) for b in content if b.get("type") == "text")
    imgs = sum(1 for b in content if b.get("type") == "image")
    return chars, imgs


def build_audit_content(payload):
    """Контент vision-запроса аудита: JSON задания + PNG-страницы с подписями."""
    import base64
    aud = CK.joinpath(*AUDIT_DIR_REL)
    tasks, images, seen = [], [], set()
    for t in payload["tasks"]:
        t2 = dict(t)
        names = []
        for p in t.get("d2_pages", []):
            name = Path(p).name
            names.append(name)
            if name not in seen:
                seen.add(name)
                images.append(name)
        t2["d2_pages"] = names
        tasks.append(t2)
    content = [{"type": "text", "text": dump_json({"tasks": tasks})}]
    for name in images:
        path = aud / name
        if not path.exists():
            sys.exit(f"нет изображения {path} — перегенерируй задания: s7_audit_prep.py")
        data = base64.b64encode(path.read_bytes()).decode()
        content.append({"type": "text", "text": f"Изображение страницы {name}:"})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": data}})
    return content


# ------------------------------------------------------------------ построение


def build_request(stage, cfg, unit_id, payload, model=None, effort=None, max_tokens=None):
    note = BATCH_NOTE + (" " + AUDIT_NOTE if cfg["kind"] == "audit" else "")
    content = build_audit_content(payload) if cfg["kind"] == "audit" else dump_json(payload)
    return {
        "custom_id": unit_id,
        "params": {
            "model": model or cfg["model"],
            "max_tokens": max_tokens or cfg["max_tokens"],
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or cfg["effort"]},
            "system": [
                {"type": "text", "text": read_prompt(cfg)},
                {"type": "text", "text": note,
                 "cache_control": {"type": "ephemeral"}},
            ],
            "messages": [{"role": "user", "content": content}],
        },
    }


# ------------------------------------------------------------------- валидация


def validate(stage, cfg, payload, obj):
    """(ok: bool, problems: [str]). Мягкие проверки — жёсткие ворота у s*_qa.py."""
    problems = []
    top = cfg["top_key"]
    if not isinstance(obj, dict) or top not in obj or not isinstance(obj[top], list):
        return False, [f"нет ключа '{top}' со списком"]
    out = obj[top]
    if not out:
        return False, ["пустой список результата"]

    if stage == "s0":
        want = {str(x["seqid"]) for x in payload}
        got = {str(e.get("seqid")) for e in out}
        if want != got:
            return False, [f"seqid не совпали: потеряно {len(want - got)}, лишних {len(got - want)}"]
        need = {"word", "tags", "def1", "misc1", "flags"}
        bad = [e for e in out if not need.issubset(e)]
        if bad:
            return False, [f"{len(bad)} статей без обязательных полей"]
    elif stage == "s2":
        ids = {str(x["id"]) for x in payload}
        used = set()
        for e in out:
            if not {"source_ids", "word", "hom", "tags", "def2", "misc2", "flags"}.issubset(e):
                return False, ["статья без обязательных полей"]
            used.update(str(s) for s in e["source_ids"])
        alien = used - ids
        if alien:
            return False, [f"чужие source_ids: {sorted(alien)[:5]}"]
        unconsumed = ids - used
        if len(unconsumed) > max(2, len(ids) // 4):
            return False, [f"не использовано {len(unconsumed)}/{len(ids)} сегментов"]
        if unconsumed:
            problems.append(f"warn: не использовано {len(unconsumed)} сегментов: {sorted(unconsumed)[:8]}")
    elif stage == "s4":
        want = {g["match_id"] for g in payload}
        got = {g.get("match_id") for g in out}
        if want != got:
            return False, [f"match_id не совпали: нет {sorted(want - got)[:5]}, лишние {sorted(got - want)[:5]}"]
        need = {"word_base", "dict_id", "tags", "def1", "def2", "misc1", "misc2",
                "src1", "src2", "hom_rank", "flags"}
        for g in out:
            if not g.get("entries"):
                return False, [f"группа {g.get('match_id')} без статей"]
            for e in g["entries"]:
                if not need.issubset(e):
                    return False, [f"в группе {g.get('match_id')} статья без полей {sorted(need - set(e))[:4]}"]
    elif stage in ("s5", "s5_rejudge"):
        want = {str(x["entry_id"]) for x in payload}
        got = {str(i.get("entry_id")) for i in out}
        if want != got:
            return False, [f"entry_id не совпали: потеряно {len(want - got)}, лишних {len(got - want)}"]
        bad = [i for i in out if i.get("lextag") not in LEXTAGS]
        if bad:
            return False, [f"{len(bad)} статей с меткой вне списка 14: {bad[0].get('lextag')!r}"]
    elif stage in ("s3b_verbs_sonnet", "s3b_verbs_opus"):
        want = {str(x["word"]) for x in payload}
        got = {str(i.get("word")) for i in out}
        if want != got:
            return False, [f"слова не совпали: потеряно {len(want - got)}"]
        if any("imperative" not in i for i in out):
            return False, ["элемент без поля imperative"]
    elif stage == "s3b_zhdzh":
        want = {str(x["word"]) for x in payload}
        got = {str(i.get("word")) for i in out}
        if want != got:
            return False, [f"слова не совпали: потеряно {len(want - got)}"]
        bad = [i for i in out if i.get("kind") not in ("loanword", "native", "unsure")]
        if bad:
            return False, [f"{len(bad)} элементов с kind вне словаря"]
    elif stage == "s7_audit":
        tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        want = {str(t["entry"]["entry_id"]) for t in tasks}
        got = {str(a.get("entry_id")) for a in out}
        if want != got:
            return False, [f"entry_id не совпали: нет {sorted(want - got)[:4]}, "
                           f"лишние {sorted(got - want)[:4]}"]
        bad = [a for a in out if a.get("verdict") not in ("ok", "minor", "major")]
        if bad:
            return False, [f"{len(bad)} вердиктов вне ok|minor|major"]
    return True, problems


# --------------------------------------------------------------------- команды


def cmd_init(args):
    marker = SHARDS / ".full_run"
    if marker.exists():
        print("init уже выполнен (есть маркер .full_run)")
        return
    if SHARDS.exists() and any(SHARDS.iterdir()):
        arch = CK / "shards_pilot"
        if arch.exists():
            sys.exit(f"{arch} уже существует — разбери вручную")
        SHARDS.rename(arch)
        print(f"пилотные шарды -> {arch}")
    for d in ("s0_in", "s0_out", "s2_in", "s2_out", "s4_in", "s4_out",
              "s5_in", "s5_out", "s3b_out"):
        (SHARDS / d).mkdir(parents=True, exist_ok=True)
    marker.write_text(utcnow(), encoding="utf-8")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    print("готово: пустые каталоги шардов созданы, маркер .full_run записан")


def pending_units(stage, cfg, st, limit=None):
    """Единицы, которым нужен запрос: не ok и не в полёте."""
    units = list_units(stage, cfg)
    todo = []
    for uid, payload in units:
        rec = st["shards"].get(uid, {})
        if rec.get("status") in ("ok", "pending"):
            continue
        todo.append((uid, payload))
    if limit:
        todo = todo[:limit]
    return units, todo


def cmd_submit(args):
    stage, cfg = args.stage, STAGES[args.stage]
    if not (SHARDS / ".full_run").exists() and not args.force:
        sys.exit("Сначала: python pipeline/batch_runner.py init\n"
                 "(архивирует пилотные шарды; иначе их выходы будут ложно считаться готовыми).\n"
                 "Обойти проверку: --force")
    st = load_state(stage)
    units, todo = pending_units(stage, cfg, st, args.limit)

    # защита от чужих файлов в out-каталоге (не отслеженных стейтом)
    if cfg["kind"] == "sharded":
        out_dir = SHARDS / cfg["out_dir"]
        untracked = [f.name for f in out_dir.glob("batch_*.json")
                     if f.stem not in st["shards"]]
        if untracked and not args.force:
            sys.exit(f"[{stage}] в {out_dir} есть файлы вне стейта ({untracked[:3]}...) — "
                     f"это пилотные остатки? Сначала init, либо --force")
    elif cfg["kind"] == "audit":
        aud = CK.joinpath(*AUDIT_DIR_REL)
        untracked = [f.name for f in aud.glob("result_*.json")
                     if f.stem.replace("result", "task") not in st["shards"]]
        if untracked and not args.force:
            sys.exit(f"[{stage}] в {aud} есть result-файлы вне стейта ({untracked[:3]}...) — "
                     f"пилотные? Перегенерируй задания (s7_audit_prep) либо --force")

    print(f"[{stage}] всего единиц: {len(units)}, к отправке: {len(todo)}, "
          f"модель {args.model or cfg['model']}, effort {args.effort or cfg['effort']}")
    if not todo:
        print("отправлять нечего")
        return
    requests = [build_request(stage, cfg, uid, payload,
                              model=args.model, effort=args.effort,
                              max_tokens=args.max_tokens)
                for uid, payload in todo]
    if args.dry_run:
        r = requests[0]
        chars, imgs = content_text_chars(r["params"]["messages"][0]["content"])
        print(f"--dry-run: {len(requests)} запросов; первый custom_id={r['custom_id']}")
        print(f"  params.model={r['params']['model']}, max_tokens={r['params']['max_tokens']}")
        print(f"  system[0] {len(r['params']['system'][0]['text'])} зн., "
              f"user {chars} зн. текста + {imgs} изображений")
        return

    client = get_client()
    keys = {uid: unit_keys(cfg, payload) for uid, payload in todo}
    for i in range(0, len(requests), args.chunk):
        part = requests[i:i + args.chunk]
        batch = client.messages.batches.create(requests=part)
        ids = [r["custom_id"] for r in part]
        st["batches"].append({"id": batch.id, "submitted_at": utcnow(),
                              "custom_ids": ids, "processed": False,
                              "model": args.model or cfg["model"]})
        for uid in ids:
            st["shards"][uid] = {"status": "pending", "batch": batch.id,
                                 "keys": keys.get(uid)}
        save_state(stage, st)
        print(f"  batch {batch.id}: {len(ids)} запросов "
              f"({ids[0]}..{ids[-1]}), статус {batch.processing_status}")
    print(f"[{stage}] отправлено {len(requests)} запросов. Дальше: "
          f"python pipeline/batch_runner.py watch --stage {stage}")


def _get_text(message):
    return "".join(b.text for b in message.content if b.type == "text")


def _price(model, usage):
    inp, out = PRICES.get(model, (5.0, 25.0))
    cost = (usage.get("in", 0) * inp + usage.get("cache_w", 0) * inp * 1.25
            + usage.get("cache_r", 0) * inp * 0.1 + usage.get("out", 0) * out) / 1e6
    return cost * BATCH_DISCOUNT


def cmd_fetch(args, quiet=False):
    stage, cfg = args.stage, STAGES[args.stage]
    st = load_state(stage)
    client = get_client()
    payload_by_uid = None  # лениво

    def payloads():
        nonlocal payload_by_uid
        if payload_by_uid is None:
            payload_by_uid = dict(list_units(stage, cfg))
        return payload_by_uid

    any_open = False
    for b in st["batches"]:
        if b.get("processed"):
            continue
        mb = client.messages.batches.retrieve(b["id"])
        if mb.processing_status != "ended":
            any_open = True
            rc = mb.request_counts
            if not quiet:
                print(f"  {b['id']}: {mb.processing_status} "
                      f"(succeeded {rc.succeeded}, processing {rc.processing}, errored {rc.errored})")
            continue
        n_ok = n_bad = 0
        for res in client.messages.batches.results(b["id"]):
            uid = res.custom_id
            rec = st["shards"].setdefault(uid, {})
            rtype = res.result.type
            if rtype != "succeeded":
                err = getattr(getattr(res.result, "error", None), "type", rtype)
                rec.update(status="failed_api", error=str(err))
                n_bad += 1
                continue
            msg = res.result.message
            u = msg.usage
            rec["usage"] = {"in": u.input_tokens, "out": u.output_tokens,
                            "cache_r": getattr(u, "cache_read_input_tokens", 0) or 0,
                            "cache_w": getattr(u, "cache_creation_input_tokens", 0) or 0}
            if msg.stop_reason != "end_turn":
                rec["status"] = "truncated" if msg.stop_reason == "max_tokens" else "failed_stop"
                rec["error"] = f"stop_reason={msg.stop_reason}"
                n_bad += 1
                continue
            text = _get_text(msg)
            try:
                obj = extract_json(text)
            except json.JSONDecodeError as e:
                FAILED_DIR.mkdir(parents=True, exist_ok=True)
                (FAILED_DIR / f"{stage}__{uid}.txt").write_text(text, encoding="utf-8")
                rec.update(status="failed_parse", error=str(e)[:120])
                n_bad += 1
                continue
            payload = payloads().get(uid)
            ok, problems = validate(stage, cfg, payload or [], obj)
            warns = [p for p in problems if p.startswith("warn:")]
            if not ok:
                FAILED_DIR.mkdir(parents=True, exist_ok=True)
                (FAILED_DIR / f"{stage}__{uid}.txt").write_text(text, encoding="utf-8")
                rec.update(status="failed_validation", error="; ".join(problems)[:300])
                n_bad += 1
                continue
            # запись результата
            if cfg["kind"] == "sharded":
                out_path = SHARDS / cfg["out_dir"] / f"{uid}.json"
            elif cfg["kind"] == "audit":
                out_path = CK.joinpath(*AUDIT_DIR_REL) / f"{uid.replace('task', 'result')}.json"
            else:
                out_path = PARTS_DIR / stage / f"{uid}.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            rec.update(status="ok", warns=warns or None, error=None)
            n_ok += 1
        b["processed"] = True
        save_state(stage, st)
        print(f"  {b['id']}: ended -> ok {n_ok}, проблемных {n_bad}")

    # сборка единого файла для single-этапов
    if cfg["kind"] == "single":
        units = list_units(stage, cfg)
        if all(st["shards"].get(uid, {}).get("status") == "ok" for uid, _ in units):
            merged = []
            for uid, _ in units:
                part = json.loads((PARTS_DIR / stage / f"{uid}.json").read_text(encoding="utf-8"))
                merged.extend(part[cfg["top_key"]])
            out_file = SHARDS / cfg["out_file"]
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps({cfg["top_key"]: merged}, ensure_ascii=False),
                                encoding="utf-8")
            print(f"[{stage}] собран итоговый файл {out_file} ({len(merged)} элементов)")

    _print_summary(stage, cfg, st)
    return not any_open


def _print_summary(stage, cfg, st):
    counts = {}
    usage = {"in": 0, "out": 0, "cache_r": 0, "cache_w": 0}
    cost = 0.0
    for uid, rec in st["shards"].items():
        counts[rec.get("status", "?")] = counts.get(rec.get("status", "?"), 0) + 1
        u = rec.get("usage")
        if u:
            for k in usage:
                usage[k] += u.get(k, 0)
    model = cfg["model"]
    for b in st["batches"]:
        model = b.get("model", model)
    cost = _price(model, usage)
    print(f"[{stage}] статусы: {counts}")
    if usage["in"]:
        print(f"[{stage}] токены: in {usage['in']:,}, out {usage['out']:,}, "
              f"cache_r {usage['cache_r']:,} -> ~${cost:,.2f} (с батч-скидкой)")
    bad = [uid for uid, r in st["shards"].items()
           if r.get("status", "").startswith(("failed", "truncated"))]
    if bad:
        print(f"[{stage}] на retry: {len(bad)} ({bad[:5]}...) -> "
              f"python pipeline/batch_runner.py retry --stage {stage}")


def cmd_status(args):
    stages = [args.stage] if args.stage else list(STAGES)
    client = get_client()
    for stage in stages:
        if not state_path(stage).exists():
            continue
        st = load_state(stage)
        print(f"== {stage}: батчей {len(st['batches'])}")
        for b in st["batches"]:
            if b.get("processed"):
                print(f"  {b['id']}: обработан")
                continue
            mb = client.messages.batches.retrieve(b["id"])
            rc = mb.request_counts
            print(f"  {b['id']}: {mb.processing_status} "
                  f"(ok {rc.succeeded} / wip {rc.processing} / err {rc.errored} / "
                  f"canceled {rc.canceled} / expired {rc.expired})")
        _print_summary(stage, STAGES[stage], st)


def cmd_watch(args):
    while True:
        done = cmd_fetch(args, quiet=False)
        st = load_state(args.stage)
        if done:
            pending = [u for u, r in st["shards"].items() if r.get("status") == "pending"]
            if not pending:
                print(f"[{args.stage}] все батчи обработаны")
                return
        time.sleep(args.interval)


def cmd_retry(args):
    stage, cfg = args.stage, STAGES[args.stage]
    st = load_state(stage)
    units = dict(list_units(stage, cfg))
    todo = []
    for uid, rec in st["shards"].items():
        s = rec.get("status", "")
        if s.startswith("failed") or s == "truncated":
            if uid not in units:
                print(f"  ! {uid} нет во входных данных, пропуск")
                continue
            todo.append((uid, units[uid], s == "truncated"))
    if not todo:
        print("нечего повторять")
        return
    client = get_client()
    requests = []
    for uid, payload, truncated in todo:
        mt = args.max_tokens or (int(cfg["max_tokens"] * 1.5) if truncated else cfg["max_tokens"])
        requests.append(build_request(stage, cfg, uid, payload,
                                      model=args.model, effort=args.effort, max_tokens=mt))
    batch = client.messages.batches.create(requests=requests)
    st["batches"].append({"id": batch.id, "submitted_at": utcnow(),
                          "custom_ids": [r["custom_id"] for r in requests],
                          "processed": False, "model": args.model or cfg["model"]})
    for uid, payload, _ in todo:
        st["shards"][uid] = {"status": "pending", "batch": batch.id,
                             "keys": unit_keys(cfg, payload)}
    save_state(stage, st)
    print(f"[{stage}] retry: {len(requests)} запросов в {batch.id} "
          f"(модель {args.model or cfg['model']})")


def cmd_cancel(args):
    stage = args.stage
    st = load_state(stage)
    client = get_client()
    for b in st["batches"]:
        if not b.get("processed"):
            mb = client.messages.batches.cancel(b["id"])
            print(f"  {b['id']}: {mb.processing_status}")


def cmd_estimate(args):
    stage, cfg = args.stage, STAGES[args.stage]
    units = list_units(stage, cfg)
    n = len(units)
    sample = units[:: max(1, n // args.sample)][:args.sample]
    reqs = [build_request(stage, cfg, uid, p) for uid, p in sample]
    model = args.model or cfg["model"]
    in_tokens = None
    try:
        import anthropic
        client = anthropic.Anthropic()
        tot = 0
        for r in reqs:
            tot += client.messages.count_tokens(
                model=model, system=r["params"]["system"],
                messages=r["params"]["messages"]).input_tokens
        in_tokens = round(tot / len(reqs))
    except Exception as e:
        print(f"count_tokens недоступен ({e}); грубая оценка по символам")
        stats = [content_text_chars(r["params"]["messages"][0]["content"]) for r in reqs]
        avg_chars = sum(c for c, _ in stats) / len(stats)
        avg_imgs = sum(i for _, i in stats) / len(stats)
        prompt_chars = len(read_prompt(cfg)) + len(BATCH_NOTE)
        in_tokens = round((avg_chars + prompt_chars) / 2.8 + avg_imgs * 2500)
    prompt_tokens_est = round((len(read_prompt(cfg)) + len(BATCH_NOTE)) / 2.8)
    content_tokens = max(in_tokens - prompt_tokens_est, 1)
    out_low = round(content_tokens * cfg["out_ratio"])
    out_high = round(out_low * 2.2)  # + adaptive thinking (тоже биллится как выход)
    pin, pout = PRICES.get(model, (5.0, 25.0))
    cost_low = n * (in_tokens * pin + out_low * pout) / 1e6 * BATCH_DISCOUNT
    cost_high = n * (in_tokens * pin + out_high * pout) / 1e6 * BATCH_DISCOUNT
    print(f"[{stage}] единиц: {n}; модель {model}")
    print(f"  вход ~{in_tokens:,} ток./запрос (из них промпт ~{prompt_tokens_est:,})")
    print(f"  выход ~{out_low:,}..{out_high:,} ток./запрос (верх — с учётом мышления)")
    print(f"  ИТОГО с батч-скидкой: ~${cost_low:,.2f} .. ${cost_high:,.2f}")
    print("  (кэш промпта может дополнительно удешевить вход; оценка без него)")


def cmd_merge_verbs(args):
    pa = SHARDS / "s3b_out" / "verbs_sonnet.json"
    pb = SHARDS / "s3b_out" / "verbs_opus.json"
    if not (pa.exists() and pb.exists()):
        sys.exit("нужны оба файла: verbs_sonnet.json и verbs_opus.json")
    a = {i["word"]: i for i in json.loads(pa.read_text(encoding="utf-8"))["items"]}
    b = {i["word"]: i for i in json.loads(pb.read_text(encoding="utf-8"))["items"]}
    conf_rank = {"low": 0, "medium": 1, "high": 2}
    agreed, disputed = [], []
    for w in a:
        if w not in b:
            disputed.append({"word": w, "sonnet": a[w], "opus": None})
        elif a[w]["imperative"] == b[w]["imperative"]:
            conf = min(a[w].get("confidence", "medium"), b[w].get("confidence", "medium"),
                       key=lambda c: conf_rank.get(c, 1))
            agreed.append({"word": w, "imperative": a[w]["imperative"], "confidence": conf})
        else:
            disputed.append({"word": w, "sonnet": a[w], "opus": b[w]})
    for w in b:
        if w not in a:
            disputed.append({"word": w, "sonnet": None, "opus": b[w]})
    out = SHARDS / "s3b_out" / "verbs.json"
    out.write_text(json.dumps({"items": agreed}, ensure_ascii=False), encoding="utf-8")
    print(f"согласий: {len(agreed)} -> {out}")
    if disputed:
        dp = SHARDS / "s3b_out" / "verbs_disagreements.json"
        dp.write_text(json.dumps({"items": disputed}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
        print(f"РАСХОЖДЕНИЙ: {len(disputed)} -> {dp}")
        print("реши их вручную/в сессии и ДОПИШИ решённые в items файла verbs.json до s3b_apply")
    else:
        print("расхождений нет")


# ------------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, stage_required=True):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if stage_required:
            p.add_argument("--stage", required=(name != "status"), choices=list(STAGES))
        return p

    add("init", cmd_init, stage_required=False)

    p = add("estimate", cmd_estimate)
    p.add_argument("--sample", type=int, default=12)
    p.add_argument("--model")

    p = add("submit", cmd_submit)
    p.add_argument("--limit", type=int, help="дымовой тест: только N первых единиц")
    p.add_argument("--chunk", type=int, default=500, help="запросов на один батч")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--model")
    p.add_argument("--effort", choices=["low", "medium", "high"])
    p.add_argument("--max-tokens", type=int)

    add("status", cmd_status).set_defaults(stage=None)
    add("fetch", cmd_fetch)

    p = add("watch", cmd_watch)
    p.add_argument("--interval", type=int, default=120)

    p = add("retry", cmd_retry)
    p.add_argument("--model")
    p.add_argument("--effort", choices=["low", "medium", "high"])
    p.add_argument("--max-tokens", type=int)

    add("cancel", cmd_cancel)
    add("merge-verbs", cmd_merge_verbs, stage_required=False)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
