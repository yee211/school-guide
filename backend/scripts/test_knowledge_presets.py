"""Offline regression for every frontend preset and its actual source data.

Run with PYTHONPATH=backend. No API keys, Redis or PostgreSQL connection needed.
Contracts describe expected answer facets, not model-generated answers.
"""
import json
from pathlib import Path
import re
import unittest

from app.agents.answer_requirements import admission_clarification
from app.rag.metadata import FilterCatalog, infer_retrieval_filters
from app.structured.parsers import parse_all, GROUP_FLOOR
from app.structured.query import structured_query_service

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "backend/data/raw"
CONTRACTS = Path(__file__).parent / "fixtures/knowledge_presets.json"


def read_modules():
    text = (ROOT / "frontend/src/data/knowledgeModules.ts").read_text(encoding="utf-8")
    matches = re.finditer(r"id: '([^']+)'.*?sources: \[([^\]]+)\].*?questions: \[([^\]]+)\]", text, re.S)
    return {m[1]: {"sources": re.findall(r"'([^']+)'", m[2]), "questions": re.findall(r"'([^']+)'", m[3])} for m in matches}


def matching_rows(case, scores, plans):
    filters = infer_retrieval_filters(case["question"], FilterCatalog())
    score_types = structured_query_service._infer_score_type(case["question"])
    rows = scores if "score" in case["fields"] else plans
    result = []
    for row in rows:
        if any(values and str(row.get(key)) not in values for values, key in (
            (filters.years, "year"), (filters.provinces, "province"),
            (filters.subject_categories, "subject_category"), (filters.majors, "major"),
        )):
            continue
        if filters.groups and not any(row.get("group_no") == g or (g.isdigit() and str(row.get("group_no", "")).endswith(g)) for g in filters.groups):
            continue
        if "score" in case["fields"] and score_types and row.get("score_type") not in score_types:
            continue
        result.append(row)
    return result


class PresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = read_modules()
        cls.cases = json.loads(CONTRACTS.read_text(encoding="utf-8"))
        cls.scores, cls.plans = parse_all(RAW)

    def test_every_displayed_question_has_a_contract(self):
        displayed = [(module, q) for module, data in self.modules.items() for q in data["questions"]]
        contracted = [(c["module"], c["question"]) for c in self.cases]
        self.assertTrue(displayed, "Preset extraction failed: update reader if TypeScript format changes")
        self.assertEqual(len(displayed), len(set(displayed)), "Duplicate displayed question")
        self.assertEqual(len(contracted), len(set(contracted)), "Duplicate regression contract")
        self.assertCountEqual(displayed, contracted, "Update expected evidence contracts when presets change")

    def test_sources_exist_and_stay_inside_raw_directory(self):
        for module, data in self.modules.items():
            for source in data["sources"]:
                with self.subTest(module=module, source=source):
                    path = (ROOT / source).resolve()
                    self.assertTrue(path.is_relative_to(RAW.resolve()), "Source outside knowledge directory")
                    self.assertTrue(path.is_file(), "Missing source file")
                    self.assertTrue(path.read_text(encoding="utf-8").strip(), "Empty source")

    def test_presets_do_not_require_extra_admission_conditions(self):
        for case in self.cases:
            with self.subTest(question=case["question"]):
                self.assertIsNone(admission_clarification(case["question"]), "Complete preset incorrectly triggers clarification")

    def test_document_presets_have_expected_answer_material(self):
        for case in self.cases:
            if case["kind"] != "document":
                continue
            with self.subTest(question=case["question"]):
                self.assertIn(case["source"], self.modules[case["module"]]["sources"])
                text = (ROOT / case["source"]).read_text(encoding="utf-8")
                for term in case["required_terms"]:
                    self.assertIn(term, text, f"Missing answer facet: {term}")

    def test_numeric_presets_have_matching_rows_and_required_fields(self):
        for case in self.cases:
            if case["kind"] != "structured":
                continue
            with self.subTest(question=case["question"]):
                rows = matching_rows(case, self.scores, self.plans)
                self.assertTrue(rows, "No matching parsed knowledge data")
                sources = set(self.modules[case["module"]]["sources"])
                complete = [row for row in rows if "backend/" + row["source_file"] in sources and all(row.get(field) is not None and row.get(field) != "" for field in case["fields"])]
                self.assertTrue(complete, f"No complete row for requested fields: {case['fields']}")
                if "expected_groups" in case:
                    self.assertEqual({r["group_no"] for r in rows}, set(case["expected_groups"]))
                    self.assertTrue(all(r["score_type"] == GROUP_FLOOR for r in rows), "Mixed group/major score definitions")


if __name__ == "__main__":
    unittest.main(verbosity=2)
