"""Offline evaluation checks: source labels, scoring, and reporting boundaries."""
import unittest
from pathlib import Path
from scripts.eval_quality import grade, read_cases, summary, percentile

ROOT = Path(__file__).resolve().parents[1]

class EvaluationTests(unittest.TestCase):
    def test_retrieval_labels_have_actual_source_evidence(self):
        cases = read_cases(ROOT / "evals/retrieval_cases_extended.jsonl")
        self.assertEqual(len(cases), 50)
        for case in cases:
            with self.subTest(case=case["id"]):
                sources = [p for p in (ROOT / "data/raw").rglob("*") if p.is_file()
                           and any(p.as_posix().endswith(s) for s in case["relevant_sources"])]
                self.assertTrue(sources)
                self.assertTrue(any(all(term in p.read_text(encoding="utf-8") for term in case["must_contain"])
                                    for p in sources), "Expected terms must exist together in at least one source")

    def test_answer_corpus_has_history_composite_and_missing(self):
        cases = read_cases(ROOT / "evals/answer_cases.jsonl")
        self.assertEqual(len(cases), 50)
        categories = {c["category"] for c in cases}
        self.assertTrue({"history", "composite", "missing", "clarification", "adversarial"} <= categories)
        for case in cases:
            self.assertTrue(case["question"])
            for source in case.get("sources", []):
                self.assertTrue(any(p.as_posix().endswith(source) for p in (ROOT / "data/raw").rglob("*")))

    def test_keyword_score_cannot_be_called_factual_accuracy(self):
        result = grade("有空调，但并非四人间", [], {"checks": [["空调"], ["四人间"]]})
        self.assertEqual(result["keyword_facet_coverage"], 1)
        self.assertIsNone(result["human_factual_correct"])
        self.assertTrue(result["needs_human_review"])

    def test_numeric_presence_does_not_match_a_larger_number(self):
        case = {"numeric_values": [4800]}
        self.assertEqual(grade("48000元", [], case)["numeric_value_presence"], 0)
        self.assertEqual(grade("4,800元", [], case)["numeric_value_presence"], 1)
        self.assertIsNone(grade("不是4800元", [], case)["human_factual_correct"])

    def test_retrieval_report_accepts_rows_without_generation_latency(self):
        import tempfile
        from scripts.eval_quality import write_report
        with tempfile.TemporaryDirectory() as folder:
            report = write_report(Path(folder) / "report.json", [{"id": "one", "mode": "semantic", "mrr": 1}], {})
        self.assertIsNone(report["summary"]["elapsed_ms_p95"])
        self.assertEqual(report["by_mode"]["semantic"]["completed"], 1)

    def test_failure_and_missing_metrics_are_not_reported_as_zero(self):
        result = summary([{"error": "TimeoutError"}, {"elapsed_ms": 10}])
        self.assertEqual(result["failed"], 1)
        self.assertIsNone(result["first_token_ms_mean"])
        self.assertEqual(percentile([1, 2, 3, 4], .95), 4)

if __name__ == "__main__":
    unittest.main()
