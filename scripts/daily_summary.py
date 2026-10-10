"""End-of-day human-language summary for the public site, written by Claude Haiku 5.5 via OpenRouter.

Input: today's commit titles from data/timeline.json (already public-safe) + optional --facts file (plain
sanitized notes of measured outcomes). Output: data/daily/<day>.json and data/daily/index.json.
Fail-closed: every string is redacted, then leak_scan must be empty; otherwise nothing is written (exit 3).
One model call per day, small max_tokens. No key = no output (never fabricated text).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from sync_bossman import leak_scan, redact  # noqa: E402

MODEL = "anthropic/claude-haiku-5.5"
URL = "https://openrouter.ai/api/v1/chat/completions"
KEYS = Path(os.environ.get("LOCALAPPDATA", "")) / "Bossman" / "keys" / "provider-keys.env"
PROMPT = """Ты пишешь раздел «Итоги дня» для публичной страницы проекта Bossman. Читатель не программист.
Пиши по-человечески, коротко, честно: что реально сделано сегодня, что уже работает, что НЕ получилось или не доказано,
что дальше. Используй только факты из списка ниже, ничего не выдумывай, не придумывай числа. Не пиши пути, ключи, адреса,
имена людей. Провалы называй провалами. Без восторгов и рекламных слов.
Верни ТОЛЬКО JSON: {"headline": "одна фраза до 120 знаков", "done": ["3-6 пунктов"], "works": ["0-4 пункта"],
"not_yet": ["0-5 пунктов"], "tomorrow": ["0-4 пункта"]}. Каждый пункт до 180 знаков.

ДЕНЬ: %s
КОММИТЫ (заголовки):
%s

ИЗМЕРЕННЫЕ ИТОГИ ОТ ВЛАДЕЛЬЦА ПРОЕКТА:
%s
"""


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key and KEYS.exists():
        for line in KEYS.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    return key


def call_model(prompt: str, key: str, post=None) -> str:
    body = json.dumps({"model": MODEL, "max_tokens": 4500, "temperature": 0.3,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    if post is not None:
        return post(body)
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Authorization": "Bearer " + key,
                                             "User-Agent": "bossman-daily-summary"})
    data = json.load(urllib.request.urlopen(req, timeout=120))
    return data["choices"][0]["message"]["content"]


def parse(text: str) -> dict:
    text = text or ""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("model returned no JSON object")
    obj = json.loads(text[a:b + 1])
    out = {"headline": str(obj.get("headline", ""))[:160]}
    for k, lim in (("done", 8), ("works", 6), ("not_yet", 6), ("tomorrow", 6)):
        v = obj.get(k) or []
        out[k] = [str(x)[:260] for x in v][:lim] if isinstance(v, list) else []
    if not out["headline"] or not out["done"]:
        raise ValueError("model output has no headline/done")
    return out


def build(day: str, facts: str, post=None) -> dict:
    tl = json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))
    titles = [redact(i.get("title", "")) for i in tl.get("items", []) if i.get("day") == day]
    prompt = PROMPT % (day, "\n".join("- " + t for t in titles[:60]) or "(нет коммитов)", redact(facts) or "(нет)")
    last = None
    for _ in range(3):  # the model occasionally returns an empty/non-JSON answer; one call per attempt, max 3
        try:
            summary = parse(call_model(prompt, api_key(), post))
            break
        except (ValueError, KeyError, TypeError) as e:
            last = e
    else:
        raise SystemExit("MODEL_OUTPUT_UNUSABLE " + type(last).__name__)
    summary = json.loads(redact(json.dumps(summary, ensure_ascii=False)))
    hits = leak_scan(json.dumps(summary, ensure_ascii=False), as_json=True)
    if hits:
        raise SystemExit("LEAK " + repr(hits[:3]))
    return {"day": day, "model": MODEL, "commits": len(titles), **summary}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=date.today().isoformat())
    ap.add_argument("--facts", default="")
    ap.add_argument("--auto", action="store_true", help="only after 21:00 local time and only if today's file is missing")
    a = ap.parse_args()
    if a.auto:
        from datetime import datetime
        if datetime.now().hour < 21 or (ROOT / "data" / "daily" / f"{a.day}.json").exists():
            print("auto: not due")
            return 0
        auto_facts = ROOT / "data" / "daily" / f"facts-{a.day}.txt"
        if not a.facts and auto_facts.exists():
            a.facts = str(auto_facts)
    facts = Path(a.facts).read_text(encoding="utf-8") if a.facts else ""
    if not api_key():
        print("no OpenRouter key: nothing written")
        return 2
    try:
        rec = build(a.day, facts)
    except SystemExit as e:
        print(str(e))
        return 3
    d = ROOT / "data" / "daily"
    d.mkdir(exist_ok=True)
    (d / f"{a.day}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    idx = sorted({p.stem for p in d.glob("2*.json")}, reverse=True)
    items = []
    for day in idx:
        r = json.loads((d / f"{day}.json").read_text(encoding="utf-8"))
        items.append({"day": day, "headline": r.get("headline", ""), "commits": r.get("commits", 0)})
    (d / "index.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", a.day, "commits", rec["commits"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
