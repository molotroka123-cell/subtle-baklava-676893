"""Тесты парсера витрины: редакция (пути/ключи), fail-closed, статьи, лента, бесплатное обогащение, целостность данных.

Запуск: python -m unittest discover -s tests -v   (только стандартная библиотека; git нужен для фикстуры)
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sync_bossman as sb  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def make_repo(tmp: Path, doc: str = "Choose one question.\n\nSecond paragraph.") -> Path:
    repo = tmp / "bossman"
    (repo / "command-center/bcc/pit").mkdir(parents=True)
    (repo / "command-center/tests").mkdir(parents=True)
    (repo / "command-center/bcc/pit/discovery.py").write_text(
        f'r"""{doc}"""\n\ndef choose_discovery_question(items):\n    """Return one item."""\n    return items[0]\n\nclass Mode:\n    pass\n', encoding="utf-8")
    (repo / "command-center/tests/test_discovery.py").write_text(
        "from bcc.pit.discovery import choose_discovery_question\n\ndef test_x():\n    assert choose_discovery_question([1]) == 1\n", encoding="utf-8")
    nodes = [
        {"id": "bossman", "label": "Bossman", "parent": "", "status": "blocked", "detail": "Корень.", "sources": []},
        {"id": "jeff", "label": "Jeff", "parent": "bossman", "status": "mixed", "detail": "Раскрой ветку: статусы относятся к отдельным возможностям.", "sources": []},
        {"id": "mod-1", "label": "command-center/bcc/pit/discovery.py", "parent": "jeff", "status": "code", "detail": "Найден исходный модуль. Наличие тестов и живой результат проверяются отдельно.",
         "sources": [{"path": "command-center/bcc/pit/discovery.py", "sha": "", "branch": "x"}], "next_action": "Проверить живой сценарий."},
        {"id": "oss-1", "label": "foo/bar", "parent": "jeff", "status": "recorded", "detail": "Ссылка в выбранном checkout.", "external_url": "https://github.com/foo/bar", "sources": []},
    ]
    (repo / "command-center/bcc/capability_tree_seed.json").write_text(
        json.dumps({"schema_version": "1.0", "as_of": "2026-10-05", "source_sha": "a" * 40, "nodes": nodes, "coverage": {}}), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat(jeff): add discovery.py")
    return repo


class Args:
    no_code_details = False
    enrich = None
    enrich_model = sb.FREE_MODELS[0]
    enrich_budget = 10
    days = 45
    timeline_limit = 20
    live = False
    live_url = None
    data_dir = None


class RedactionTests(unittest.TestCase):
    CASES = {
        "windows": r"смотри C:\Users\owner\Bossman\data\vault.json сейчас",
        "windows-fwd": "в C:/Users/owner/Bossman/x.txt",
        "unc": r"\\server\share\private\file.txt",
        "env": r"%LOCALAPPDATA%\Bossman\private\ids.txt",
        "posix-home": "лежит в /home/alice/project/secret.txt",
        "tilde": r"~/Bossman/data/x.db",
        "repo-file": "см. command-center/bcc/pit/discovery.py для деталей",
        "email": "пишите на owner@example.com",
        "localhost": "http://127.0.0.1:8801/api/health",
        "own-repo": "https://github.com/molotroka123-cell/AiMaxBossman/blob/main/x.md",
        "sk": "ключ sk-abcdefghijklmnopqrstuvwxyz0123456789",
        "ghp": "токен ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "kv": "api_key = abcdef1234567890zzz",
        "bearer": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    }

    def test_every_class_of_leak_is_removed_and_rescan_is_clean(self):
        for name, text in self.CASES.items():
            with self.subTest(name):
                out = sb.redact(text)
                self.assertEqual(sb.leak_scan(out), [], f"{name}: {out!r}")
                self.assertNotEqual(out, text)

    def test_negative_control_scanner_catches_raw_text(self):
        for name, text in self.CASES.items():
            with self.subTest(name):
                self.assertTrue(sb.leak_scan(text), f"сканер пропустил {name}")

    def test_third_party_links_survive(self):
        out = sb.redact("см. https://github.com/Zylann/godot_voxel и https://example.org/a/b.md")
        self.assertIn("https://github.com/Zylann/godot_voxel", out)
        self.assertIn("https://example.org/a/b.md", out)

    def test_json_scan_uses_decoded_strings(self):
        raw = json.dumps({"x": "C:\\Users\\owner\\a.txt"})
        self.assertTrue(sb.leak_scan(raw, as_json=True))
        self.assertEqual(sb.leak_scan(json.dumps({"x": "обычный текст 2026-10-06"}), as_json=True), [])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_article_has_real_content_from_code_tests_and_history(self):
        repo = make_repo(self.tmp)
        files, meta = sb.build(repo, Args())
        zone = json.loads(files["data/articles/jeff.json"])
        art = zone["mod-1"]
        self.assertEqual(art["title"], "discovery.py")                         # путь в подписи -> имя файла
        heads = [s["h"] for s in art["sections"]]
        for need in ("Что это", "Основные функции", "Чем это проверяется", "История изменений"):
            self.assertIn(need, heads)
        funcs = next(s for s in art["sections"] if s["h"] == "Основные функции")["list"]
        self.assertIn("choose_discovery_question()", [f["t"] for f in funcs])
        facts = dict(art["facts"])
        self.assertEqual(facts["Тестов-импортёров"], "1")
        self.assertEqual(art["summary"].split(".")[0], "Choose one question")      # из docstring
        self.assertEqual(meta["counts"]["articles"], 4)
        self.assertEqual(json.loads(files["data/timeline.json"])["items"][0]["kind"], "feat")

    def test_working_status_is_known_labelled_and_counted(self):
        repo = make_repo(self.tmp)
        seed = repo / "command-center/bcc/capability_tree_seed.json"
        data = json.loads(seed.read_text(encoding="utf-8"))
        for n in data["nodes"]:
            if n["id"] == "mod-1":
                n["status"] = "working"
        seed.write_text(json.dumps(data), encoding="utf-8")
        files, meta = sb.build(repo, Args())
        legend = meta["status_legend"]["working"]
        self.assertEqual((legend["label"], legend["tone"]), ("Работает в Bossman", "ok"))
        self.assertIn("не гарантия работы сегодня", legend["about"])
        self.assertEqual(meta["counts"]["by_status"].get("working"), 1)
        art = json.loads(files["data/articles/jeff.json"])["mod-1"]
        self.assertEqual(art["status"], "working")
        self.assertTrue(any("установленн" in " ".join(s.get("p", [])) for s in art["sections"]))
        zone = json.loads(files["data/articles/jeff.json"])["jeff"]
        self.assertIn("Что работает в установленном Bossman", [s["h"] for s in zone["sections"]])

    def test_front_end_knows_working_status_with_its_own_color(self):
        import re
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        colors = dict(re.findall(r"(\w+): '(#[0-9a-fA-F]{6})'", re.search(r"const COLORS = \{(.*?)\};", js).group(1)))
        self.assertIn("working", colors)
        self.assertEqual(len(set(colors.values())), len(colors))
        self.assertRegex(js, r"const ORDER = \['working', 'reported'")

    def test_zone_and_external_articles(self):
        repo = make_repo(self.tmp)
        files, _ = sb.build(repo, Args())
        jeff = json.loads(files["data/articles/jeff.json"])
        self.assertIn("Элементы зоны", [s["h"] for s in jeff["jeff"]["sections"]])
        self.assertTrue(jeff["jeff"]["summary"].startswith("Jeff — собеседник"))
        oss = jeff["oss-1"]
        self.assertTrue(any(s.get("link") == "https://github.com/foo/bar" for s in oss["sections"]))

    def test_paths_in_source_docstring_never_reach_output(self):
        repo = make_repo(self.tmp, doc=r"Reads C:\Users\owner\Bossman\data\x.db and /home/alice/key.pem for owner@example.com.")
        files, _ = sb.build(repo, Args())
        blob = "\n".join(files.values())
        for bad in (r"C:\\Users", "/home/alice", "owner@example.com", "x.db"):
            self.assertNotIn(bad, blob)
        for rel, body in files.items():
            self.assertEqual(sb.leak_scan(body, as_json=rel.endswith(".json")), [], rel)

    def test_fail_closed_when_redaction_is_broken(self):
        """Негативный контроль второго слоя: если redact() сломан, вывод НЕ записывается (код 3)."""
        repo = make_repo(self.tmp, doc=r"Reads C:\Users\owner\Bossman\data\x.db")
        out = self.tmp / "site"
        out.mkdir()
        orig = sb.redact
        sb.redact = lambda t: t
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = sb.main(["--source", str(repo), "--out", str(out)])
        finally:
            sb.redact = orig
        self.assertEqual(code, 3)
        self.assertIn("LEAK_BLOCKED", buf.getvalue())
        self.assertEqual(list(out.iterdir()), [], "при блокировке ничего не должно быть записано")

    def test_symlink_and_denied_names_are_not_read(self):
        repo = make_repo(self.tmp)
        (repo / ".env").write_text("TOKEN=abc", encoding="utf-8")
        self.assertEqual(sb.read_source(repo, ".env"), "")
        self.assertEqual(sb.read_source(repo, "../outside.txt"), "")
        outside = self.tmp / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = repo / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlink недоступен")
        self.assertEqual(sb.read_source(repo, "link.txt"), "")

    def test_no_code_details_mode_reads_no_source(self):
        repo = make_repo(self.tmp)
        a = Args()
        a.no_code_details = True
        files, _ = sb.build(repo, a)
        art = json.loads(files["data/articles/jeff.json"])["mod-1"]
        self.assertNotIn("Основные функции", [s["h"] for s in art["sections"]])


class HideTests(unittest.TestCase):
    def tearDown(self):
        sb.set_hide([])

    def test_hidden_topics_never_reach_text_nodes_or_timeline(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d), doc="Poker solver glue code. Choose one question.")
            (repo / "x.txt").write_text("x", encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "feat(poker): river dataset")
            a = Args()
            a.hide = ["poker"]
            files, meta = sb.build(repo, a)
            blob = "\n".join(files.values())
            self.assertNotIn("oker", blob)                                  # ни Poker, ни poker
            self.assertIn("«скрыто»", blob)
            tl = json.loads(files["data/timeline.json"])["items"]
            self.assertTrue(all("river dataset" not in r["title"] for r in tl))

    def test_node_with_hidden_word_becomes_placeholder(self):
        with tempfile.TemporaryDirectory() as d:
            repo = make_repo(Path(d))
            seed = repo / "command-center/bcc/capability_tree_seed.json"
            data = json.loads(seed.read_text(encoding="utf-8"))
            data["nodes"].append({"id": "p1", "label": "Poker coach", "parent": "jeff", "status": "code", "detail": "poker bot", "sources": []})
            seed.write_text(json.dumps(data), encoding="utf-8")
            a = Args()
            a.hide = ["poker"]
            files, meta = sb.build(repo, a)
            art = json.loads(files["data/articles/jeff.json"])["p1"]
            self.assertEqual(art["title"], "Скрытый элемент")
            self.assertEqual(meta["counts"]["hidden"], 1)
            self.assertEqual(meta["counts"]["nodes"], 5)                    # счётчики честные


class EnrichTests(unittest.TestCase):
    def arts(self):
        return {"a": {"title": "T", "summary": "S", "status": "code", "facts": [["k", "v"]], "children_total": 0, "words": 100,
                      "sections": [{"h": "Что это", "p": ["Текст."]}]}}

    def test_paid_model_is_refused(self):
        self.assertEqual(sb.enrich(self.arts(), "anthropic/claude-3.5-sonnet", Path("x.json"), 5)["state"], "refused")

    def test_no_key_is_skipped_not_faked(self):
        saved = {k: os.environ.pop(k, None) for k in ("OPENROUTER_API_KEY", "BOSSMAN_OPENROUTER_API_KEY")}
        try:
            self.assertEqual(sb.enrich(self.arts(), sb.FREE_MODELS[0], Path("x.json"), 5)["state"], "skipped")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_free_model_text_is_redacted_cached_and_not_repeated(self):
        calls = []
        def post(prompt):
            calls.append(prompt)
            return "Это модуль выбора вопроса, см. C:\\Users\\owner\\x.py."
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache.json"
            arts = self.arts()
            r1 = sb.enrich(arts, sb.FREE_MODELS[0], cache, 5, post=post)
            self.assertEqual((r1["state"], r1["requests"]), ("ok", 1))
            sec = arts["a"]["sections"][1]
            self.assertEqual(sec["h"], "Простыми словами")
            self.assertEqual(sb.leak_scan(sec["p"][0]), [])
            self.assertIn("бесплатной моделью", sec["note"])
            r2 = sb.enrich(self.arts(), sb.FREE_MODELS[0], cache, 5, post=post)
            self.assertEqual(r2["requests"], 0)
            self.assertEqual(len(calls), 1)


class CommittedDataTests(unittest.TestCase):
    """Данные, которые реально лежат в репозитории и уходят на сайт."""

    @classmethod
    def setUpClass(cls):
        if not (ROOT / "data/tree.json").exists():
            raise unittest.SkipTest("data/ ещё не сгенерирована")

    def test_no_leaks_in_published_files(self):
        for p in list((ROOT / "data").rglob("*.json")) + list((ROOT / "ai").rglob("*.md")) + [ROOT / "llms.txt"]:
            with self.subTest(p.name):
                self.assertEqual(sb.leak_scan(p.read_text(encoding="utf-8"), as_json=p.suffix == ".json"), [], str(p.relative_to(ROOT)))

    def test_every_node_has_an_article_and_links_resolve(self):
        tree = json.loads((ROOT / "data/tree.json").read_text(encoding="utf-8"))["nodes"]
        index = json.loads((ROOT / "data/articles/index.json").read_text(encoding="utf-8"))
        ids = {n["id"] for n in tree}
        self.assertEqual(set(index), ids)
        loaded: dict[str, dict] = {}
        for zone in set(index.values()):
            loaded.update(json.loads((ROOT / f"data/articles/{zone}.json").read_text(encoding="utf-8")))
        self.assertEqual(set(loaded), ids)
        for a in loaded.values():
            for ref in a["children"] + a["siblings"] + a["crumbs"]:
                self.assertIn(ref["id"], ids)
            self.assertGreaterEqual(a["words"], 20, a["id"])

    def test_no_node_label_is_a_hidden_path_marker(self):
        tree = json.loads((ROOT / "data/tree.json").read_text(encoding="utf-8"))["nodes"]
        self.assertFalse([n for n in tree if "«" in n["label"] or "/" in n["label"] and n["label"].endswith((".py", ".js", ".md"))])


class AuditSectionTest(unittest.TestCase):
    def _arts(self):
        return {"a": {"sections": [], "id": "a"}, "b": {"sections": [], "id": "b"}}

    def test_section_comes_only_from_the_audit_file_and_never_claims_benefit(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "audit.json"
            f.write_text(json.dumps({"rows": [{"id": "a", "verdict": "covered", "passed": 5, "failed": 0, "skipped": 1,
                                               "tests": ["x/tests/test_a.py"]}]}), encoding="utf-8")
            arts = self._arts()
            sb.attach_audit(arts, str(f))
        sec = arts["a"]["sections"][0]
        self.assertEqual(sec["h"], "Проверка тестами")
        self.assertIn("прошло 5, упало 0, пропущено 1", sec["p"][0])
        self.assertIn("НЕ доказывает", sec["p"][1])
        self.assertEqual(arts["b"]["sections"], [])           # a leaf absent from the audit gets no invented section

    def test_failing_tests_are_shown_as_failing(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "audit.json"
            f.write_text(json.dumps({"rows": [{"id": "a", "verdict": "fix", "passed": 1, "failed": 2, "skipped": 0, "tests": []}]}), encoding="utf-8")
            arts = self._arts()
            sb.attach_audit(arts, str(f))
        self.assertIn("ПАДАЮТ", arts["a"]["sections"][0]["p"][0])

    def test_missing_or_broken_audit_adds_nothing(self):
        for path in (None, "/nonexistent/audit.json"):
            arts = self._arts()
            with redirect_stdout(io.StringIO()):
                sb.attach_audit(arts, path)
            self.assertEqual(arts["a"]["sections"], [])


if __name__ == "__main__":
    unittest.main()


class PcLauncherContractTest(unittest.TestCase):
    """Статический контракт скриптов для Windows (запустить их здесь нельзя): что они обязаны делать."""

    def test_sync_launcher_updates_both_repos_logs_and_supports_unattended_run(self):
        s = (ROOT / "scripts" / "sync_from_pc.cmd").read_text(encoding="utf-8")
        self.assertIn('git -C "%BOSSMAN_REPO%" pull --ff-only', s)      # без этого парсер читает устаревший снимок Bossman
        self.assertIn("sync_bossman.py", s)
        self.assertIn("--push", s)
        self.assertIn("sync.log", s)
        self.assertIn('if /I not "%~1"=="auto" pause', s)               # по расписанию окно не должно висеть
        self.assertNotIn("--force", s)                                  # никаких принудительных перезаписей

    def test_installer_makes_an_hourly_task_that_runs_unattended(self):
        s = (ROOT / "scripts" / "install_autosync.cmd").read_text(encoding="utf-8")
        self.assertIn("schtasks /Create", s)
        self.assertIn("/SC HOURLY", s)
        self.assertIn("sync_from_pc.cmd", s)
        self.assertIn(" auto", s)
        self.assertIn("schtasks /Delete", s)                             # способ снять задачу объяснён


class TimelineLinkTest(unittest.TestCase):
    NODES = [{"id": "a", "sources": [{"path": "x/one.py"}]}, {"id": "b", "sources": [{"path": "x/one.py"}, {"path": "x/two.py"}]},
             {"id": "c", "sources": [{"path": "y/three.py"}]}, {"id": "d", "sources": []}]

    def test_links_follow_the_files_a_commit_touched_narrowest_leaf_first(self):
        items = [{"sha": "s1"}, {"sha": "s2"}, {"sha": "s3"}, {"sha": "s4"}]
        files = {"s1": ["x/one.py"], "s2": ["x/one.py", "x/two.py"], "s3": ["docs/readme.md"], "s4": ["y/three.py", "x/one.py"]}
        sb.link_leaves(items, files, sb.source_index(self.NODES))
        self.assertEqual(items[0]["nodes"], ["a", "b"])            # a has one source, b two: the narrower leaf is first
        self.assertEqual(items[1]["nodes"], ["b", "a"])            # b matches two files, a one
        self.assertEqual(items[2]["nodes"], [])                    # no leaf owns the file: nothing is invented
        self.assertEqual(set(items[3]["nodes"]), {"a", "b", "c"})

    def test_a_commit_without_a_known_file_list_gets_no_links_and_the_limit_holds(self):
        many = [{"id": f"n{i}", "sources": [{"path": "p.py"}]} for i in range(8)]
        items = [{"sha": "z"}, {"sha": "unknown"}]
        sb.link_leaves(items, {"z": ["p.py"]}, sb.source_index(many), max_links=3)
        self.assertEqual(len(items[0]["nodes"]), 3)
        self.assertEqual(items[1]["nodes"], [])


class RegistrySectionTest(unittest.TestCase):
    def _run(self, row):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "reg.json"
            f.write_text(json.dumps({"leaves": [row]}), encoding="utf-8")
            arts = {"a": {"sections": []}, "b": {"sections": []}}
            ok = sb.attach_registry(arts, str(f))
        return ok, arts

    def test_levels_are_shown_separately_and_a_passing_test_is_not_called_ci(self):
        row = {"id": "a", "proven_through": "tests", "integration_status": "code",
               "levels": {"code": {"state": "PRESENT"}, "tests": {"state": "PASSED_RECORDED_RUN", "passed": 4, "failed": 0, "skipped": 1},
                          "ci": {"state": "NOT_RUN", "sha": None}, "owner_pc": {"state": "NOT_RUN"}}}
        ok, arts = self._run(row)
        sec = arts["a"]["sections"][0]
        self.assertTrue(ok)
        self.assertEqual(sec["h"], "Уровни доказательства")
        self.assertIn("тесты прошли", sec["p"][0])
        d = {i["t"]: i["d"] for i in sec["list"]}
        self.assertIn("прошли: 4", d["2. Тесты"])
        self.assertIn("не подтверждено", d["3. CI"])
        self.assertIn("не проверено на ПК", d["4. ПК владельца"])
        self.assertEqual(arts["b"]["sections"], [])
        self.assertEqual(arts["a"]["proven_through"], "tests")

    def test_failing_tests_and_unreadable_registry_are_not_hidden(self):
        row = {"id": "a", "proven_through": "code", "integration_status": "code",
               "levels": {"code": {"state": "PRESENT"}, "tests": {"state": "FAILED", "passed": 1, "failed": 2, "skipped": 0},
                          "ci": {"state": "NOT_RUN"}, "owner_pc": {"state": "NOT_RUN"}}}
        _, arts = self._run(row)
        self.assertIn("ПАДАЮТ", {i["t"]: i["d"] for i in arts["a"]["sections"][0]["list"]}["2. Тесты"])
        with redirect_stdout(io.StringIO()):
            self.assertFalse(sb.attach_registry({"a": {"sections": []}}, "/nonexistent.json"))
        self.assertFalse(sb.attach_registry({}, None))
