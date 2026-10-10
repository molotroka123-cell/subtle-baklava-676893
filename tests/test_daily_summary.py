import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import daily_summary as ds  # noqa: E402


def fake(content):
    def post(_body):
        return content
    return post


GOOD = json.dumps({"headline": "Итоги дня", "done": ["Сделали одно"], "works": [], "not_yet": ["Не вышло другое"], "tomorrow": []},
                  ensure_ascii=False)


class DailySummary(unittest.TestCase):
    def setUp(self):
        self._key = ds.api_key
        ds.api_key = lambda: "x"

    def tearDown(self):
        ds.api_key = self._key

    def test_good_output_is_accepted(self):
        day = json.loads((ROOT / "data" / "timeline.json").read_text(encoding="utf-8"))["items"][0]["day"]
        rec = ds.build(day, "факт", post=fake(GOOD))
        self.assertEqual(rec["headline"], "Итоги дня")
        self.assertEqual(rec["not_yet"], ["Не вышло другое"])

    def test_truncated_output_is_rejected_not_invented(self):
        with self.assertRaises(SystemExit) as c:
            ds.build("2026-01-01", "", post=fake('{"headline": "x", "done": ["обрыв'))
        self.assertIn("MODEL_OUTPUT_UNUSABLE", str(c.exception))

    def test_leak_in_model_output_is_redacted_or_blocked(self):
        leaky = json.dumps({"headline": "Итоги", "done": [r"Файл C:\Users\owner\secret.txt и почта a@b.ru"], "works": [],
                            "not_yet": [], "tomorrow": []}, ensure_ascii=False)
        rec = ds.build("2026-01-01", "", post=fake(leaky))
        text = json.dumps(rec, ensure_ascii=False)
        self.assertNotIn('secret.txt', text)
        self.assertNotIn("a@b.ru", text)


if __name__ == "__main__":
    unittest.main()
