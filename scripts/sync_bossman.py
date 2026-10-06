#!/usr/bin/env python3
"""Парсер развития Bossman -> публичные данные витрины (data/*.json, ai/*.md, llms.txt).

Запуск (на ПК владельца или в облаке; только стандартная библиотека, ИИ и ключи не нужны, $0):

    python scripts/sync_bossman.py --source C:\\путь\\к\\AiMaxBossman            # снимок из git/кода
    python scripts/sync_bossman.py --source ... --live auto                       # + живые счётчики с запущенного Bossman
    python scripts/sync_bossman.py --source ... --push                            # + git commit/push -> Netlify соберёт сам
    python scripts/sync_bossman.py --source ... --enrich openrouter-free          # + «простыми словами» бесплатной моделью (нужен ключ)

Что делает: читает карту возможностей (capability_tree_seed.json), для каждого узла собирает СТАТЬЮ
из того, что реально лежит в коде и документах (docstring, README, заголовки, функции, тесты-импортёры, история git),
строит ленту развития из git log и положение на лестнице North Star.

Публичность (fail-closed): локальные пути, домашние каталоги, UNC, адреса localhost/LAN, e-mail, токены/ключи,
пути файлов репозитория в тексте и ссылки на приватный репозиторий вырезаются; после генерации весь вывод
проверяется ещё раз, и при любой находке запись данных ОТМЕНЯЕТСЯ (код выхода 3). Личные заметки владельца
из живого API не экспортируются. Карта показывает уровень доказательства, а не PASS: «код есть» ≠ «работает».
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SEED_REL = "command-center/bcc/capability_tree_seed.json"
SCHEMA = 1

# ---------------------------------------------------------------- человеческие статусы
STATUS = {
    "reported": ("Есть сохранённый прогон", "ok",
                 "Был живой прогон, и результат записан. Это отчёт о прошлом запуске: дата и условия важны, "
                 "сегодняшнюю работоспособность он не доказывает."),
    "code": ("Код написан", "info",
             "Реализация есть в коде, но запуск «в живую» отдельно не подтверждён. Это не значит, что не работает — "
             "это значит, что доказательства пока нет."),
    "branch": ("Лежит в отдельной ветке", "warn",
               "Работа существует в отдельной ветке разработки и ещё не влита в основную линию. "
               "Как она поведёт себя после слияния — не проверено."),
    "prepared": ("Подготовлено", "warn",
                 "Артефакт подготовлен, но ещё не загружен в рабочую систему и не запускался."),
    "idea": ("Идея", "idea", "Только замысел или предложение. Реализации нет."),
    "blocked": ("Блокер", "err",
                "Известно, что чего-то не хватает или проверка не пройдена. Это честная отметка проблемы, а не скрытая ошибка."),
    "recorded": ("Запись / ссылка", "idle",
                 "Запись в справочнике: внешний проект или документ, на который Bossman ссылается. "
                 "Это не утверждение, что он установлен или встроен."),
    "mixed": ("Смешанная зона", "mixed", "Сводная зона: внутри элементы с разным уровнем доказательства — смотрите вложенные."),
}
LADDER = [
    ("SELF_IMPROVEMENT_INFRASTRUCTURE_PRESENT", "Инфраструктура самоулучшения есть",
     "Изолированные кандидаты, проверки, одобрения и память уже встроены в Bossman."),
    ("SELF_REPAIR_SINGLE_CYCLE_PASS", "Один цикл самоисправления пройден",
     "Bossman сам нашёл дефект, исправил в изолированной копии, независимая проверка прошла."),
    ("SELF_REPAIR_3_CYCLE_PASS", "Три цикла подряд", "Тот же результат повторён три раза."),
    ("TRANSFER_MEASURED_GAIN", "Перенос навыка измерен", "Выигрыш виден на новых задачах, а не на выученных."),
    ("24H_SOAK_PASS", "24 часа без сбоев", "Сутки непрерывной работы под наблюдением."),
    ("48H_SOAK_PASS", "48 часов без сбоев", "Двое суток непрерывной работы."),
    ("WEEK_MODE_READY", "Недельный режим", "Автономная неделя с остановкой по команде владельца."),
    ("REVENUE_CAPABLE_PILOT", "Пилот с доходом", "Первые коммерческие результаты по одобренным владельцем задачам."),
]
LADDER_REACHED = {"SELF_IMPROVEMENT_INFRASTRUCTURE_PRESENT"}   # правится файлом data/ladder.override.json

ZONE_ABOUT = {
    "bossman": "Корень карты: всё, что относится к Bossman. Единая готовность владельцу не доказана — карта показывает возможности и уровень доказательства, а не сертификат релиза.",
    "jeff": "Jeff — собеседник Bossman в Telegram: диалог, память участников с их согласием, паспорта, голос, фото, звонки, рассылки и защита от сбоев (heartbeat, watchdog, перезапуск).",
    "ux": "Всё, чем человек управляет Bossman: чат со стримингом ответов, командная строка (CMD), слэш-команды, панели и сам интерфейс.",
    "apps": "Приложения и бизнес-сценарии на базе Bossman: сервисы, админки и мастерские со своими проверками. Реальные учётки, публикация и доход здесь отдельно не подтверждаются.",
    "models": "Локальные модели: запуск, выбор и сравнение моделей на оборудовании владельца.",
    "cloud": "Облачные API и бесплатные маршруты моделей: как Bossman выбирает внешнего исполнителя. Для самоулучшения и Jeff действует правило $0 — только бесплатные и локальные модели.",
    "computer": "Работа с браузером и компьютером: действия на экране выполняются под одобрение владельца, с возможностью остановки.",
    "media": "Motion, видео и медиа: генерация и обработка изображений, анимации и видео.",
    "memory": "Память и обучение: сохранённый опыт, навыки, выросшие из опыта, и цикл самоулучшения. Это не заявление об обучении весов модели.",
    "agents": "Агенты и оркестрация: кто что делает, как делится работа и как проверяется результат.",
    "skills": "Навыки: переиспользуемые инструкции и инструменты (включая MCP) с их политиками.",
    "plugins": "Плагины и коннекторы: подключение внешних сервисов и источников данных.",
    "ops": "Система и проверки: тесты, автоматические проверки CI, сборки, аудит безопасности и состояние выпуска.",
    "oss": "Каталог open-source проектов, на которые ссылается карта. Это справочник ссылок, а не список установленного.",
}

SOURCE_DENY = re.compile(r"(^|/)(\.env[^/]*|[^/]*secret[^/]*|[^/]*vault[^/]*|[^/]*credential[^/]*|[^/]*\.pem|[^/]*\.key|id_rsa[^/]*)$", re.I)
SENSITIVE_PATH = "«локальный путь скрыт»"

# ---------------------------------------------------------------- редакция
_URL = re.compile(r"https?://[^\s)>\]\"'`]+")
_PRIVATE_URL = re.compile(r"https?://(?:127\.\d+\.\d+\.\d+|localhost|0\.0\.0\.0|\[::1\]|192\.168\.|10\.|172\.(?:1[6-9]|2\d|3[01])\.)[^\s)>\]\"'`]*", re.I)
_OWN_REPO = re.compile(r"https?://(?:www\.)?github\.com/molotroka123-cell[^\s)>\]\"'`]*", re.I)
_WIN = re.compile(r"(?<![\w/])[A-Za-z]:[\\/](?:[^\s\"'<>|*?`]+)")
_UNC = re.compile(r"\\\\[\w.$-]+\\[^\s\"'<>`]+")
_POSIX_HOME = re.compile(r"(?<![\w.:/-])(?:/home|/Users|/root|/mnt|/tmp|/var|/opt|/etc|/srv|/proc)(?:/[^\s\"'<>)\]`,;]*)?")
_TILDE = re.compile(r"~[\\/][^\s\"'<>`]+")
_ENV_PATH = re.compile(r"(?:%[A-Za-z_][A-Za-z0-9_]*%|\$env:[A-Za-z_]\w*|\$\{?[A-Z_]{3,}\}?)[\\/][^\s\"'<>`]*", re.I)
_BACKSLASH_PATH = re.compile(r"(?<![\w\\])\\?(?:[\w.$ -]+\\){1,}[\w.$-]+")
_REPO_FILE = re.compile(r"(?<![\w@:/.-])(?:[\w.-]+/)+[\w.-]+\.(?:py|js|mjs|cjs|md|json|jsonl|ps1|psm1|yaml|yml|toml|html|css|ts|tsx|sh|bat|cmd|txt|ini|cfg)\b")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_SECRET_KV = re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\b(\s*[:=]\s*)(?!\«)[^\s\"',;]+")
_TOKENS = [re.compile(p) for p in (
    r"\bsk-[A-Za-z0-9_-]{16,}", r"\bghp_[A-Za-z0-9]{20,}", r"\bgithub_pat_[A-Za-z0-9_]{20,}", r"\bgho_[A-Za-z0-9]{20,}",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_-]{30,}", r"\bAKIA[0-9A-Z]{12,}", r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", r"\b\d{8,10}:[A-Za-z0-9_-]{30,}")]


_HIDE: re.Pattern | None = None


def set_hide(words: list[str]) -> None:
    """Слова/темы, которые владелец не хочет видеть на публичной витрине (data/hide.txt и --hide)."""
    global _HIDE
    words = [w.strip() for w in words if w.strip() and not w.strip().startswith("#")]
    _HIDE = re.compile("|".join(re.escape(w) for w in words), re.I) if words else None


def load_hide(extra: list[str] | None) -> list[str]:
    path = HERE / "data" / "hide.txt"
    try:
        base = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        base = []
    return base + list(extra or [])


def redact(text: str) -> str:
    """Публичная версия текста: без путей, адресов, ключей, ссылок на приватный репозиторий и скрытых владельцем тем."""
    if not text:
        return text
    if _HIDE is not None:
        text = _HIDE.sub("«скрыто»", text)
    keep: list[str] = []

    def stash(m: re.Match) -> str:
        url = m.group(0)
        if _PRIVATE_URL.match(url):
            return "«локальный адрес скрыт»"
        if _OWN_REPO.match(url):
            return "«ссылка скрыта»"
        keep.append(url)
        return f"\x00{len(keep) - 1}\x00"

    text = _URL.sub(stash, text)
    for rx in _TOKENS:
        text = rx.sub("«ключ скрыт»", text)
    text = _SECRET_KV.sub(lambda m: f"{m.group(1)}{m.group(2)}«скрыто»", text)
    text = _EMAIL.sub("«почта скрыта»", text)
    for rx in (_UNC, _WIN, _ENV_PATH, _TILDE, _BACKSLASH_PATH, _POSIX_HOME):
        text = rx.sub(SENSITIVE_PATH, text)
    text = _REPO_FILE.sub("«файл»", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)


_LEAK_CHECKS = [
    ("windows-path", re.compile(r"(?<![\w/])[A-Za-z]:[\\/][^\s\"']{2,}")),
    ("unc-path", re.compile(r"\\\\[\w.$-]+\\[^\s\"']+")),
    ("backslash-path", re.compile(r"(?<![\w\\])(?:[\w.$-]+\\){2,}[\w.$-]+")),
    ("env-path", _ENV_PATH),
    ("tilde-path", re.compile(r"(?<![\w])~[\\/][^\s\"']+")),
    ("posix-home", re.compile(r"(?<![\w.:/-])(?:/home|/Users|/root)/[^\s\"']+")),
    ("private-url", _PRIVATE_URL),
    ("own-repo-url", _OWN_REPO),
    ("email", _EMAIL),
    ("token", re.compile("|".join(r.pattern for r in _TOKENS))),
    ("secret-kv", re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*[A-Za-z0-9_\-]{12,}")),
    ("repo-file-path", _REPO_FILE),
]


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [x for k, v in value.items() for x in (_strings(k) + _strings(v))]
    if isinstance(value, list):
        return [x for v in value for x in _strings(v)]
    return []


def leak_scan(text: str, as_json: bool = False) -> list[tuple[str, str]]:
    """Повторная проверка уже готового вывода (JSON — по декодированным строкам). Пустой список = утечек не найдено."""
    if as_json:
        try:
            text = "\n".join(_strings(json.loads(text)))
        except ValueError:
            pass
    hits: list[tuple[str, str]] = []
    scrub = _URL.sub(lambda m: "" if not (_PRIVATE_URL.match(m.group(0)) or _OWN_REPO.match(m.group(0))) else m.group(0), text)
    for name, rx in _LEAK_CHECKS:
        for m in rx.finditer(scrub):
            hits.append((name, m.group(0)[:80]))
            if len(hits) > 20:
                return hits
    return hits


# ---------------------------------------------------------------- git / файлы
def git(repo: Path, *args: str, timeout: int = 60) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def read_source(repo: Path, rel: str, sha: str = "", cap: int = 400_000) -> str:
    """Файл из рабочей копии (внутри репозитория) или из объекта git по SHA из карты. Секретные имена не читаются."""
    rel = rel.replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/") or SOURCE_DENY.search(rel):
        return ""
    p = (repo / rel)
    try:
        if p.is_file() and not p.is_symlink() and repo.resolve() in p.resolve().parents:
            return p.read_bytes()[:cap].decode("utf-8", "replace")
    except OSError:
        pass
    if re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        return git(repo, "show", f"{sha}:{rel}")[:cap]
    return ""


def first_paragraphs(text: str, limit: int = 1100) -> list[str]:
    out, size = [], 0
    for block in re.split(r"\n\s*\n", text.strip()):
        block = re.sub(r"\s+", " ", block).strip()
        if not block or block.startswith(("```", "|", "---", "===")):
            continue
        out.append(block)
        size += len(block)
        if size >= limit:
            break
    return out


def one_line(text: str, n: int = 170) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def inspect_python(src: str) -> dict:
    info: dict = {"doc": "", "funcs": [], "classes": [], "lines": src.count("\n") + 1}
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return info
    info["doc"] = ast.get_docstring(tree) or ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            info["funcs"].append((node.name, one_line(ast.get_docstring(node) or "")))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            info["classes"].append((node.name, one_line(ast.get_docstring(node) or "")))
    return info


def inspect_text(rel: str, src: str) -> dict:
    low = rel.lower()
    info: dict = {"doc": "", "headings": [], "lines": src.count("\n") + 1}
    if low.endswith(".md"):
        m = re.match(r"---\n(.*?)\n---", src, re.S)
        if m:
            d = re.search(r"(?mi)^description:\s*(.+)$", m.group(1))
            if d:
                info["doc"] = d.group(1).strip().strip("\"'")
        body = src[m.end():] if m else src
        info["headings"] = [re.sub(r"[#*`]", "", h).strip() for h in re.findall(r"(?m)^#{1,3}\s+(.+)$", body)][:10]
        info["doc"] = info["doc"] or "\n\n".join(first_paragraphs(re.sub(r"(?m)^#.*$", "", body)))
    elif low.endswith((".js", ".mjs")):
        m = re.match(r"\s*/\*+(.*?)\*/", src, re.S)
        if m:
            info["doc"] = re.sub(r"(?m)^\s*\*\s?", "", m.group(1)).strip()
        else:
            lead = []
            for line in src.splitlines():
                if line.strip().startswith("//"):
                    lead.append(line.strip()[2:].strip())
                elif lead or line.strip():
                    break
            info["doc"] = " ".join(lead)
        info["funcs"] = [(n, "") for n in re.findall(r"(?m)^export\s+(?:async\s+)?function\s+(\w+)", src)][:10]
    elif low.endswith((".yaml", ".yml")):
        d = re.search(r"(?mi)^description:\s*(.+)$", src)
        info["doc"] = d.group(1).strip().strip("\"'") if d else ""
    return info


# ---------------------------------------------------------------- индекс тестов
def build_test_index(repo: Path) -> list[str]:
    texts: list[str] = []
    for base in ("tests", "command-center/tests", "bossman-core/tests"):
        root = repo / base
        if not root.is_dir():
            continue
        for p in root.rglob("test_*.py"):
            try:
                texts.append(p.read_text(encoding="utf-8", errors="replace")[:200_000])
            except OSError:
                pass
    return texts


def dotted_module(rel: str) -> str:
    rel = rel[:-3] if rel.endswith(".py") else rel
    for prefix in ("command-center/", "bossman-core/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    return rel.replace("/", ".")


_IMPORT_FROM = re.compile(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import\s+(\([^)]*\)|[^\n]+)", re.M)
_IMPORT_PLAIN = re.compile(r"^\s*import\s+([A-Za-z_][\w., ]*)", re.M)
_DOTTED = re.compile(r"\b(?:bcc|bossman|bossman_v3|pokervision)(?:\.[A-Za-z_]\w*)+")


def import_index(tests: list[str]) -> Counter:
    """Сколько тестовых файлов упоминают каждое имя модуля (импорт или строка вида bcc.pit.discovery)."""
    seen: Counter = Counter()
    for text in tests:
        names: set[str] = set()
        for mod, tail in _IMPORT_FROM.findall(text):
            names.add(mod)
            for part in re.split(r"[,\s()]+", tail):
                if re.fullmatch(r"[A-Za-z_]\w*", part) and part not in ("as", "import"):
                    names.add(f"{mod}.{part}")
        for chunk in _IMPORT_PLAIN.findall(text):
            names.update(x.strip().split(" as ")[0] for x in chunk.split(","))
        names.update(_DOTTED.findall(text))
        seen.update(names)
    return seen


def tests_importing(rel: str, index: Counter) -> int:
    if not rel.endswith(".py"):
        return 0
    mod = dotted_module(rel)
    parent, _, stem = mod.rpartition(".")
    return index.get(mod, 0) if parent and len(stem) >= 4 else 0


def file_history(repo: Path, rel: str, sha: str) -> dict:
    ref = sha if re.fullmatch(r"[0-9a-f]{7,40}", sha or "") else "HEAD"
    out = git(repo, "log", "-n", "6", "--no-merges", "--format=%h\x1f%ad\x1f%s", "--date=short", ref, "--", rel)
    rows = [r.split("\x1f") for r in out.splitlines() if r.count("\x1f") == 2]
    total = git(repo, "rev-list", "--count", ref, "--", rel).strip()
    return {"rows": rows, "total": int(total) if total.isdigit() else len(rows)}


# ---------------------------------------------------------------- статьи
KIND_LABEL = {"py": "модуль на Python", "js": "модуль интерфейса", "md": "документ", "yaml": "манифест",
              "skill": "навык", "other": "файл"}


def kind_of(rel: str) -> str:
    low = rel.lower()
    if low.endswith("skill.md"):
        return "skill"
    return {".py": "py", ".js": "js", ".mjs": "js", ".md": "md", ".yaml": "yaml", ".yml": "yaml"}.get(Path(low).suffix, "other")


_PATHY = re.compile(r"[\w.-]+(?:/[\w.-]+)+")


def display_label(label: str) -> str:
    """Подпись узла для людей: пути файлов в карте превращаются в имя файла (без каталогов)."""
    label = (label or "").strip()
    if _PATHY.fullmatch(label) and ("/" in label):
        return Path(label).name
    return label


def plural(n: int, one: str, few: str, many: str) -> str:
    n10, n100 = n % 10, n % 100
    return one if n10 == 1 and n100 != 11 else few if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else many


AUDIT_WORDS = {"covered": "тесты, импортирующие модуль, прошли", "covered-skipped": "тесты есть, но не выполнялись (пропущены или не запускались)",
               "untested": "ни один тест не импортирует этот модуль", "fix": "тесты, импортирующие модуль, ПАДАЮТ",
               "non-python": "не Python-источник, автотест не сопоставлен", "unclear": "в карте нет пути к источнику"}


def attach_audit(articles: dict, path: str | None) -> None:
    """Раздел «Проверка тестами» из tools/blue_leaf_audit.py. Только факты файла аудита; статус листа не меняется."""
    if not path:
        return
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("AUDIT=UNREADABLE (раздел не добавлен)")
        return
    rows = {r["id"]: r for r in doc.get("rows", [])}
    for nid, a in articles.items():
        r = rows.get(nid)
        if not r:
            continue
        p = [f"{AUDIT_WORDS.get(r['verdict'], r['verdict'])}: прошло {r['passed']}, упало {r['failed']}, пропущено {r['skipped']}.",
             "Это регрессионное покрытие на одном коммите в облаке. Пользу, повторяемое сравнение с базовой версией и живую работу оно НЕ доказывает."]
        a["sections"].append({"h": "Проверка тестами", "p": p, "list": [{"t": Path(t).name, "d": ""} for t in r["tests"][:8]]})
        a["audit"] = r["verdict"]


LEVEL_NAMES = {"none": "ничего не подтверждено", "code": "код есть", "tests": "тесты прошли в записанном прогоне", "ci": "зелёный CI на SHA",
               "owner_pc": "проверено на ПК владельца"}


def attach_registry(articles: dict, path: str | None) -> bool:
    """Раздел «Уровни доказательства» из реестра дерева (tools/tree_registry_sync.py): четыре уровня отдельно, без общего зелёного статуса."""
    if not path:
        return False
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("REGISTRY=UNREADABLE (раздел не добавлен)")
        return False
    rows = {r["id"]: r for r in doc.get("leaves", [])}
    for nid, a in articles.items():
        r = rows.get(nid)
        if not r:
            continue
        lv = r["levels"]
        t = lv["tests"]
        tests_txt = {"PASSED_RECORDED_RUN": f"прошли: {t['passed']}, упало {t['failed']}, пропущено {t['skipped']}", "FAILED": f"ПАДАЮТ: упало {t['failed']}",
                     "NO_TEST": "ни один тест не импортирует этот исходник", "NOT_RUN": "не запускались"}.get(t["state"], t["state"])
        ci_txt = f"зелёный на {str(lv['ci']['sha'])[:8]}" if lv["ci"]["state"] == "GREEN_ON_SHA" else "не подтверждено (нет записи CI на SHA)"
        pc_txt = "подтверждено владельцем" if lv["owner_pc"]["state"] == "VERIFIED" else "не проверено на ПК владельца"
        items = [{"t": "1. Код", "d": "файл есть" if lv["code"]["state"] == "PRESENT" else "файла нет или путь не записан"},
                 {"t": "2. Тесты", "d": tests_txt}, {"t": "3. CI", "d": ci_txt}, {"t": "4. ПК владельца", "d": pc_txt}]
        a["sections"].append({"h": "Уровни доказательства", "p": [f"Дошёл до: {LEVEL_NAMES.get(r['proven_through'], r['proven_through'])}. "
                                                              "Уровни считаются по порядку и отдельно; зелёный цвет не ставится за код или за тест.",
                                                              f"Статус интеграции на карте: {r.get('integration_status')}."], "list": items})
        a["proven_through"] = r["proven_through"]
    return True


def build_articles(nodes: list[dict], repo: Path, deep: bool) -> dict[str, dict]:
    byid = {n["id"]: n for n in nodes}
    kids: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        kids[n["parent"]].append(n)
    tests = import_index(build_test_index(repo)) if deep else Counter()
    articles: dict[str, dict] = {}
    history: dict[tuple[str, str], dict] = {}
    if deep:
        from concurrent.futures import ThreadPoolExecutor
        wanted = {(s["path"], s.get("sha", "")) for n in nodes for s in (n.get("sources") or [])[:1] if s.get("path")}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for key, value in zip(sorted(wanted), pool.map(lambda k: file_history(repo, *k), sorted(wanted))):
                history[key] = value

    def crumbs(n: dict) -> list[dict]:
        chain, cur, guard = [], n, 0
        while cur and cur["parent"] and guard < 12:
            cur = byid.get(cur["parent"])
            if cur:
                chain.append({"id": cur["id"], "label": cur["label"]})
            guard += 1
        return list(reversed(chain))

    def subtree_count(i: str) -> Counter:
        c: Counter = Counter()
        stack = list(kids.get(i, []))
        while stack:
            x = stack.pop()
            c[x["status"]] += 1
            stack.extend(kids.get(x["id"], []))
        return c

    for n in nodes:
        label_ru, tone, explain = STATUS.get(n["status"], (n["status"], "idle", ""))
        sections: list[dict] = []
        facts: list[list[str]] = [["Уровень доказательства", label_ru]]
        children = kids.get(n["id"], [])
        detail = redact(n.get("detail") or "")
        if children and n["id"] in ZONE_ABOUT and re.match(r"^(Раскрой|Единая готовность)", n.get("detail") or ""):
            detail = ZONE_ABOUT[n["id"]]
        sections.append({"h": "Что это", "p": [detail or "Описание в карте не записано."]})

        if children:
            counts = subtree_count(n["id"])
            total = sum(counts.values())
            parts = [f"{v} — {STATUS.get(k, (k,))[0].lower()}" for k, v in counts.most_common()]
            sections.append({"h": "Что внутри", "p": [
                f"В этой зоне {total} {plural(total, 'элемент', 'элемента', 'элементов')}: " + "; ".join(parts) + ".",
                "Ниже — вложенные направления. Цвет листа на дереве показывает уровень доказательства, а не оценку качества."]})
            facts.append(["Вложенных элементов", str(total)])
            direct = [c for c in children if c["label"]][:30]
            sections.append({"h": "Элементы зоны", "list": [
                {"t": f"{redact(c['label'])} — {STATUS.get(c['status'], (c['status'],))[0].lower()}",
                 "d": one_line(redact(c.get("detail") or ""), 200)} for c in direct],
                **({"note": f"Показано {len(direct)} из {len(children)} прямых элементов; остальные — в списке «Внутри»."}
                   if len(children) > len(direct) else {})})

        src_infos = []
        for s in (n.get("sources") or [])[:3]:
            rel, sha = s.get("path", ""), s.get("sha", "")
            body = read_source(repo, rel, sha) if deep else ""
            if not body:
                continue
            kind = kind_of(rel)
            info = inspect_python(body) if kind == "py" else inspect_text(rel, body)
            src_infos.append((rel, sha, kind, info))

        for rel, sha, kind, info in src_infos[:1]:
            facts.append(["Тип", KIND_LABEL.get(kind, "файл")])
            facts.append(["Размер", f"{info['lines']} {plural(info['lines'], 'строка', 'строки', 'строк')}"])
            facts.append(["Имя файла", Path(rel).name])
            doc = redact(info.get("doc") or "")
            if doc:
                paras = first_paragraphs(doc, 1300) or [one_line(doc, 600)]
                sections.append({"h": "Как это устроено (из описания в коде)", "p": paras[:4],
                                 "note": "Дословно из описания разработчика; без пересказа ИИ."})
            members = [(f"{name}()", d) for name, d in info.get("funcs", [])[:12]] + \
                      [(f"класс {name}", d) for name, d in info.get("classes", [])[:6]]
            if members:
                sections.append({"h": "Основные функции", "list": [
                    {"t": redact(name), "d": redact(desc)} for name, desc in members]})
            if info.get("headings"):
                sections.append({"h": "О чём документ", "list": [{"t": redact(h), "d": ""} for h in info["headings"]]})
            if kind == "py":
                t = tests_importing(rel, tests)
                facts.append(["Тестов-импортёров", str(t)])
                sections.append({"h": "Чем это проверяется", "p": [
                    (f"Модуль импортируют {t} {plural(t, 'тестовый файл', 'тестовых файла', 'тестовых файлов')}. "
                     if t else "Тестовых файлов, которые импортируют этот модуль напрямую, не найдено. ")
                    + "Это наличие тестов, а не результат их прогона: прогон на конкретном коммите смотрите в CI."]})
            hist = history.get((rel, sha)) or file_history(repo, rel, sha)
            if hist["rows"]:
                facts.append(["Изменений в истории", str(hist["total"])])
                facts.append(["Последнее изменение", f"{hist['rows'][0][1]} · {hist['rows'][0][0]}"])
                sections.append({"h": "История изменений", "list": [
                    {"t": f"{d} · {h}", "d": redact(s)} for h, d, s in hist["rows"]]})

        if n.get("external_url") and not _OWN_REPO.match(n["external_url"]):
            sections.append({"h": "Внешний проект", "p": [
                "Это сторонний проект, на который ссылается карта. Он не часть Bossman и не утверждается как установленный."],
                "link": n["external_url"]})
        ci = re.match(r"GitHub check (\S+?);\s*([^;]+);\s*SHA\s*([0-9a-f]{7,40})\.?\s*(.*)$", n.get("detail") or "")
        if n["id"].startswith("ci-") and ci:
            when, branch, sha40, tail = ci.groups()
            outcome = n["label"].rsplit("·", 1)[-1].strip()
            sections[0] = {"h": "Что это", "p": [
                f"Запись об автоматической проверке (GitHub Actions): «{redact(n['label'])}». Исход: {outcome}.",
                f"Проверка снята {when} на ветке «{redact(branch.strip())}», коммит {sha40[:8]}. {redact(tail)}".strip()]}
            facts[1:1] = [["Исход проверки", outcome], ["Снято", when], ["Коммит", sha40[:8]]]
        if children:
            groups: dict[str, list[str]] = defaultdict(list)
            for c in children:
                groups[c["status"]].append(c["label"])
            for status, head in (("reported", "Что подтверждено сохранённым прогоном"), ("blocked", "Что блокирует"),
                                 ("idea", "Какие идеи в зоне"), ("branch", "Что ещё в отдельных ветках")):
                if groups.get(status):
                    sections.append({"h": head, "list": [{"t": redact(x), "d": ""} for x in groups[status][:10]],
                                     **({"note": f"Показано {min(10, len(groups[status]))} из {len(groups[status])}."}
                                        if len(groups[status]) > 10 else {})})
        sections.append({"h": "Как читать уровень доказательства",
                         "p": [explain, "Правило карты: PASS не выводится из кода, названий файлов или ветки — только из сохранённой проверки "
                                        "на точном коммите."]})
        generic = re.match(r"(Найден исходный модуль|Файлы приложения присутствуют|Ссылка в выбранном)", n.get("detail") or "")
        if generic and src_infos:
            info0 = src_infos[0][3]
            doc = redact(info0.get("doc") or "")
            lead = first_paragraphs(doc, 260)[0] if doc else ""
            if not lead:
                named = next(((nm, d) for nm, d in list(info0.get("funcs", [])) + list(info0.get("classes", [])) if d), None)
                if named:
                    lead = f"Главная функция — {redact(named[0])}(): {redact(named[1])}"
            if lead:
                sections[0]["p"] = [one_line(lead, 320)] + sections[0]["p"]
                detail = lead
        nxt = redact(n.get("next_action") or "")
        if nxt:
            sections.append({"h": "Что дальше", "p": [nxt]})
        facts.append(["Родитель", byid[n["parent"]]["label"] if n["parent"] in byid else "корень"])

        articles[n["id"]] = {
            "id": n["id"], "title": redact(n["label"]), "status": n["status"], "status_label": label_ru, "tone": tone,
            "summary": one_line(detail, 240), "crumbs": crumbs(n), "facts": [[redact(a), redact(b)] for a, b in facts],
            "sections": sections,
            "children": [{"id": c["id"], "label": redact(c["label"]), "status": c["status"]} for c in children][:80],
            "children_total": len(children),
            "siblings": [{"id": c["id"], "label": redact(c["label"])} for c in kids.get(n["parent"], []) if c["id"] != n["id"]][:12],
            "words": 0,
        }
        a = articles[n["id"]]
        a["words"] = sum(len(" ".join(sec.get("p", []) + [i["t"] + " " + i["d"] for i in sec.get("list", [])]).split())
                         for sec in a["sections"])
    return articles


# ---------------------------------------------------------------- лента развития
def source_index(nodes: list[dict]) -> dict[str, list[str]]:
    """путь исходника -> id узлов, у которых он записан (для привязки изменений ленты к листьям)."""
    idx: dict[str, list[str]] = defaultdict(list)
    for n in nodes:
        for src in n.get("sources") or []:
            path = (src.get("path") or "").replace("\\", "/")
            if path and n["id"] not in idx[path]:
                idx[path].append(n["id"])
    return idx


def commit_files(repo: Path, shas: list[str]) -> dict[str, list[str]]:
    """Изменённые файлы каждого коммита одним вызовом git (без слияний)."""
    out = git(repo, "log", "--no-walk=unsorted", "--no-merges", "--name-only", "--format=\x1e%h", *shas, timeout=180) if shas else ""
    files: dict[str, list[str]] = {}
    for block in out.split("\x1e"):
        lines = [x for x in block.splitlines() if x.strip()]
        if lines:
            files[lines[0].strip()] = [x.strip().replace("\\", "/") for x in lines[1:]]
    return files


def link_leaves(items: list[dict], files: dict[str, list[str]], idx: dict[str, list[str]], max_links: int = 3) -> None:
    """Каждому изменению ленты — до max_links листьев, чьи исходники оно тронуло. Больше затронутых файлов листа — выше; при равенстве
    раньше идёт лист с меньшим числом исходников (узкий лист точнее общего). Нет совпадения — nodes пуст: ссылка никогда не выдумывается."""
    size: dict[str, int] = defaultdict(int)
    for ids in idx.values():
        for nid in ids:
            size[nid] += 1
    for it in items:
        score: dict[str, int] = defaultdict(int)
        for f in files.get(it["sha"], []):
            for nid in idx.get(f, []):
                score[nid] += 1
        it["nodes"] = sorted(score, key=lambda i: (-score[i], size[i], i))[:max_links]


def build_timeline(repo: Path, days: int, limit: int, nodes: list[dict] | None = None) -> dict:
    out = git(repo, "log", "--all", "--no-merges", f"--since={days}.days", f"-n{limit * 3}",
              "--format=%h\x1f%ad\x1f%s", "--date=short", timeout=120)
    rows, seen = [], set()
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, day, subj = parts
        if _HIDE is not None and _HIDE.search(subj):
            continue
        key = (day, subj)
        if key in seen:
            continue
        seen.add(key)
        m = re.match(r"^(\w+)(?:\([^)]*\))?!?:\s*(.*)$", subj)
        kind = (m.group(1).lower() if m else "other")
        kind = kind if kind in {"feat", "fix", "docs", "test", "chore", "refactor", "perf", "ci", "build"} else "other"
        rows.append({"sha": sha, "day": day, "kind": kind, "title": one_line(redact(m.group(2) if m else subj), 200)})
        if len(rows) >= limit:
            break
    if nodes:
        link_leaves(rows, commit_files(repo, [r["sha"] for r in rows]), source_index(nodes))
    per_day = Counter(r["day"] for r in rows)
    return {"items": rows, "per_day": dict(sorted(per_day.items())), "kinds": dict(Counter(r["kind"] for r in rows))}


# ---------------------------------------------------------------- живые данные (необязательно)
def fetch_live(repo: Path, url: str | None, data_dir: str | None) -> dict:
    """Счётчики с запущенного Bossman тем же клиентом, что CLI/дашборд. Заметки владельца и id задач не экспортируются."""
    sys.path[:0] = [str(repo / "command-center"), str(repo / "bossman-core"), str(repo)]
    try:
        from bcc.terminal_cli.api_client import BossmanError, Client, discover  # type: ignore
    except Exception as exc:                                                       # noqa: BLE001
        return {"state": "unavailable", "why": redact(f"bcc не импортируется: {type(exc).__name__}")}
    try:
        with Client(discover(None if url in (None, "auto") else url, data_dir), timeout=30.0) as client:
            live = client.get("/api/capability-tree", params={"lite": 1})
    except BossmanError as exc:
        return {"state": "unavailable", "why": one_line(redact(str(exc)), 160)}
    except Exception as exc:                                                       # noqa: BLE001
        return {"state": "unavailable", "why": redact(f"{type(exc).__name__}")}
    jobs = live.get("work") or []
    earned = Counter(j.get("earned") or "none" for j in jobs)
    act = live.get("activity") or {}
    camp = act.get("campaign") or {}
    return {"state": "live", "jobs_total": len(jobs),
            "jobs_completed": sum(1 for j in jobs if j.get("status") == "completed"),
            "jobs_failed": sum(1 for j in jobs if j.get("status") in ("failed", "blocked")),
            "improved": earned.get("verified", 0) + earned.get("applied", 0) + earned.get("unverified", 0),
            "applied": earned.get("applied", 0), "verified": earned.get("verified", 0) + earned.get("applied", 0),
            "unverified": earned.get("unverified", 0),
            "campaign": {k: camp.get(k) for k in ("status", "loop_running", "paused", "stopped", "cycles_closed")}}


# ---------------------------------------------------------------- бесплатное обогащение (необязательно)
FREE_MODELS = ("nvidia/nemotron-3-super-120b-a12b:free", "nvidia/llama-3.1-nemotron-ultra-253b-v1:free")


def refuse_model(model: str) -> str | None:
    return None if model.endswith(":free") else f"модель {model!r} не бесплатная; правило $0 запрещает"


def enrich(articles: dict[str, dict], model: str, cache_path: Path, budget: int, post=None) -> dict:
    """Простыми словами — только бесплатной моделью (id оканчивается на :free), с кэшем и лимитом запросов."""
    why = refuse_model(model)
    if why:
        return {"state": "refused", "why": why}
    key = os.environ.get("BOSSMAN_OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if post is None and not key:
        return {"state": "skipped", "why": "нет ключа OPENROUTER_API_KEY / BOSSMAN_OPENROUTER_API_KEY"}
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}

    def call(prompt: str) -> str:
        if post is not None:
            return post(prompt)
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", method="POST",
                                     data=json.dumps({"model": model, "max_tokens": 420, "temperature": 0.2,
                                                      "messages": [{"role": "user", "content": prompt}]}).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]

    done = used = 0
    for aid, art in articles.items():
        if art["children_total"] > 0 and art["words"] < 40:
            continue
        digest = f"{model}|{art['title']}|{art['summary']}|{art['status']}"
        text = cache.get(aid, {}).get("text") if cache.get(aid, {}).get("digest") == digest else None
        if text is None:
            if used >= budget:
                continue
            used += 1
            facts = "; ".join(f"{a}: {b}" for a, b in art["facts"][:8])
            body = " ".join(p for s in art["sections"][:3] for p in s.get("p", []))[:1500]
            prompt = ("Объясни по-русски простыми словами для владельца продукта, что это за возможность Bossman, "
                      "зачем она нужна и что уже подтверждено. 3–5 коротких предложений. Используй ТОЛЬКО факты ниже, "
                      "ничего не выдумывай, не обещай результатов, не называй пути, ключи и адреса. "
                      f"Название: {art['title']}\nФакты: {facts}\nТекст: {body}")
            try:
                text = redact(re.sub(r"\s+", " ", call(prompt)).strip())[:900]
            except (urllib.error.URLError, OSError, KeyError, ValueError, IndexError) as exc:
                return {"state": "partial", "enriched": done, "why": one_line(redact(str(exc)), 120)}
            cache[aid] = {"digest": digest, "text": text}
            time.sleep(1.2)
        if text:
            art["sections"].insert(1, {"h": "Простыми словами", "p": [text],
                                       "note": f"Пересказ бесплатной моделью ({model}) по фактам из этой статьи; может содержать неточности."})
            done += 1
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"state": "ok", "enriched": done, "requests": used, "model": model}


# ---------------------------------------------------------------- сборка и запись
def article_markdown(a: dict) -> str:
    lines = [f"## {a['title']}", f"*Уровень доказательства: {a['status_label']}* · id: `{a['id']}`", ""]
    if a["crumbs"]:
        lines += ["Путь: " + " → ".join(c["label"] for c in a["crumbs"]), ""]
    for sec in a["sections"]:
        lines.append(f"### {sec['h']}")
        lines += sec.get("p", [])
        for it in sec.get("list", []):
            lines.append(f"- {it['t']}" + (f" — {it['d']}" if it["d"] else ""))
        if sec.get("link"):
            lines.append(sec["link"])
        lines.append("")
    lines.append("Факты: " + "; ".join(f"{k}: {v}" for k, v in a["facts"]))
    return "\n".join(lines) + "\n"


def build(repo: Path, args) -> tuple[dict[str, str], dict]:
    seed_path = repo / SEED_REL
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    nodes = [{"id": n["id"], "label": display_label(n["label"]), "parent": n.get("parent") or "", "status": n.get("status") or "code",
              "detail": n.get("detail") or "", "next_action": n.get("next_action") or "",
              "external_url": n.get("external_url") or "", "sources": n.get("sources") or []} for n in seed["nodes"]]
    set_hide(load_hide(getattr(args, "hide", None)))
    hidden = 0
    if _HIDE is not None:
        for n in nodes:
            blob = " ".join([n["label"], n["detail"], n["next_action"], n["external_url"], *[x.get("path", "") for x in n["sources"]]])
            if _HIDE.search(blob):
                n.update(label="Скрытый элемент", detail="Подробности скрыты владельцем витрины.", next_action="", external_url="", sources=[])
                hidden += 1
    articles = build_articles(nodes, repo, deep=not args.no_code_details)
    if not attach_registry(articles, getattr(args, "registry", None)):
        attach_audit(articles, getattr(args, "audit", None))
    enrichment = {"state": "off"}
    if args.enrich:
        enrichment = enrich(articles, args.enrich_model, HERE / "data" / "enrich-cache.json", args.enrich_budget)
    timeline = build_timeline(repo, args.days, args.timeline_limit, nodes)
    live = fetch_live(repo, args.live_url, args.data_dir) if args.live else {"state": "off"}
    head = git(repo, "rev-parse", "HEAD").strip()
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    counts = Counter(n["status"] for n in nodes)
    zones = [n["id"] for n in nodes if n["parent"] == "bossman"]
    ladder_reached = set(LADDER_REACHED)
    override = HERE / "data" / "ladder.override.json"
    if override.exists():
        try:
            ladder_reached = set(json.loads(override.read_text(encoding="utf-8")).get("reached", []))
        except (OSError, ValueError):
            pass
    meta = {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "source": {"head": head[:12], "branch": branch if branch != "HEAD" else "detached",
                       "map_as_of": seed.get("as_of"), "map_sha": (seed.get("source_sha") or "")[:12],
                       "mode": "live+git" if live.get("state") == "live" else "git-snapshot"},
            "counts": {"nodes": len(nodes), "zones": len(zones), "hidden": hidden, "by_status": dict(counts),
                       "articles": len(articles), "words": sum(a["words"] for a in articles.values())},
            "live": live, "enrichment": enrichment, "coverage": {k: seed.get("coverage", {}).get(k) for k in
                                                                 ("branch_trees", "public_symbols", "live_tests_run", "current_ci_audited")},
            "ladder": [{"id": i, "title": t, "about": d, "reached": i in ladder_reached} for i, t, d in LADDER],
            "status_legend": {k: {"label": v[0], "tone": v[1], "about": v[2]} for k, v in STATUS.items()},
            "rules": ["Карта показывает уровень доказательства, а не PASS.",
                      "Код, имя файла или ветка не доказывают работоспособность.",
                      "Витрина не имеет доступа к файлам, настройкам и данным установленного Bossman."]}
    tree = {"schema": SCHEMA, "nodes": [{"id": n["id"], "label": redact(n["label"]), "parent": n["parent"], "status": n["status"],
                                         "short": one_line(redact(ZONE_ABOUT[n["id"]] if n["id"] in ZONE_ABOUT and n["id"] != "bossman" and re.match(r"^Раскрой", n["detail"]) else n["detail"]), 230)}
                                        for n in nodes]}
    files: dict[str, str] = {}
    dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
    files["data/meta.json"] = dump(meta)
    files["data/tree.json"] = dump(tree)
    files["data/timeline.json"] = dump(timeline)
    by_zone: dict[str, dict] = defaultdict(dict)
    zone_of: dict[str, str] = {}
    byid = {n["id"]: n for n in nodes}
    for n in nodes:
        cur, guard = n, 0
        while cur["parent"] not in ("bossman", "") and guard < 12:
            cur = byid[cur["parent"]]
            guard += 1
        zone_of[n["id"]] = cur["id"] if n["id"] != "bossman" else "bossman"
    for aid, art in articles.items():
        by_zone[zone_of[aid]][aid] = art
    index = {"zones": {}}
    for zone, items in sorted(by_zone.items()):
        files[f"data/articles/{zone}.json"] = dump(items)
        for aid in items:
            index["zones"][aid] = zone
    files["data/articles/index.json"] = dump(index["zones"])
    md = ["# Bossman — развитие: полный текст для ИИ", "",
          f"Снимок: {meta['generated_at']} · коммит {meta['source']['head']} · режим {meta['source']['mode']}.",
          "Правило: уровень доказательства ≠ PASS. Ниже — все статьи карты (зона → элементы).", ""]
    for zone, items in sorted(by_zone.items(), key=lambda kv: (kv[0] != "bossman", kv[0])):
        for aid, art in items.items():
            md.append(article_markdown(art))
    files["ai/bossman-development.md"] = "\n".join(md)
    files["llms.txt"] = ("# Bossman — витрина развития\n\n"
                         "> Живая карта развития Bossman: что существует, что меняется и чем это доказано.\n\n"
                         "- [Весь текст одним файлом](/ai/bossman-development.md): статьи по всем узлам карты\n"
                         "- [Дерево](/data/tree.json): узлы, родители, уровни доказательства\n"
                         "- [Сводка](/data/meta.json): счётчики, лестница North Star, источник и время снимка\n"
                         "- [Лента](/data/timeline.json): последние изменения из git\n"
                         "- Статьи по зонам: /data/articles/<зона>.json\n\n"
                         "Правило чтения: статус «код написан» не означает «работает»; PASS здесь нигде не выводится из кода.\n")
    return files, meta


def write_all(files: dict[str, str], out: Path) -> None:
    for rel, body in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(body, encoding="utf-8", newline="\n")
        os.replace(tmp, p)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="папка репозитория AiMaxBossman")
    ap.add_argument("--out", default=str(HERE), help="куда писать (по умолчанию корень витрины)")
    ap.add_argument("--live", nargs="?", const="auto", default=None, metavar="auto|URL", help="взять счётчики у запущенного Bossman")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--timeline-limit", type=int, default=120)
    ap.add_argument("--hide", action="append", default=[], metavar="СЛОВО", help="скрыть тему на витрине (дополняет data/hide.txt)")
    ap.add_argument("--no-code-details", action="store_true", help="не читать код/доки: только карта (минимум раскрытия)")
    ap.add_argument("--enrich", nargs="?", const="openrouter-free", default=None, help="пересказ бесплатной моделью (нужен ключ)")
    ap.add_argument("--enrich-model", default=FREE_MODELS[0])
    ap.add_argument("--enrich-budget", type=int, default=120, help="максимум запросов за запуск")
    ap.add_argument("--registry", default=None, help="docs/architecture/tree-registry.json (уровни доказательства по листьям; заменяет --audit)")
    ap.add_argument("--audit", default=None, help="JSON из tools/blue_leaf_audit.py (раздел «Проверка тестами»)")
    ap.add_argument("--push", action="store_true", help="git add/commit/push в репозиторий витрины")
    args = ap.parse_args(argv)
    args.live_url = None if args.live in (None, "auto") else args.live
    args.live = args.live is not None
    repo = Path(args.source).expanduser().resolve()
    if not (repo / SEED_REL).is_file():
        print(f"SYNC=NOT_RUN\nне найден {SEED_REL} в {repo.name}")
        return 2
    files, meta = build(repo, args)
    hits = []
    for rel, body in files.items():
        for name, sample in leak_scan(body, as_json=rel.endswith('.json')):
            hits.append(f"{rel}: {name}: {sample}")
    if hits:
        print("SYNC=LEAK_BLOCKED\nвывод не записан:\n  " + "\n  ".join(hits[:20]))
        return 3
    out = Path(args.out).resolve()
    write_all(files, out)
    c = meta["counts"]
    print(f"SYNC=OK\nузлов {c['nodes']}, статей {c['articles']}, слов {c['words']}, коммит {meta['source']['head']}, "
          f"режим {meta['source']['mode']}, live={meta['live']['state']}, enrich={meta['enrichment']['state']}")
    if args.push:
        sh = lambda *a: subprocess.run(["git", "-C", str(out), *a], capture_output=True, text=True)  # noqa: E731
        sh("add", "data", "ai", "llms.txt")
        if sh("diff", "--cached", "--quiet").returncode == 0:
            print("PUSH=NOTHING_TO_COMMIT")
            return 0
        msg = f"data: снимок развития Bossman {meta['generated_at']} ({meta['source']['head']})"
        r = sh("commit", "-m", msg)
        if r.returncode:
            print("PUSH=FAILED\n" + (r.stderr or r.stdout)[-300:])
            return 4
        r = sh("push")
        print("PUSH=OK" if r.returncode == 0 else "PUSH=FAILED\n" + (r.stderr or r.stdout)[-300:])
        return 0 if r.returncode == 0 else 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
