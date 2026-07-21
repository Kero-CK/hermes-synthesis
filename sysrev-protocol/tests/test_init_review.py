from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "init_review.py"
SPEC = importlib.util.spec_from_file_location("sysrev_protocol_init_review", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
init_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(init_review)


OPENALEX_QUERY = {
    "query_mode": "search",
    "search": 'climate adaptation & resilience "$"',
    "filter": "from_publication_date:2020-01-01",
}
PUBMED_QUERY = {
    "query_mode": "pubmed",
    "term": '("climate adaptation"[Title/Abstract] AND 2020:2024[dp])',
}
ERIC_QUERY = {
    "query_mode": "eric",
    "search": '"generative AI" AND "student feedback"',
    "sort": "publicationdateyear desc",
}


def payload_for(sources):
    return {
        "id": "protocol-fixture",
        "question": "How do organisations adapt to climate change?",
        "review_mode": "scoping",
        "include": ["primary studies"],
        "exclude": ["editorials"],
        "codebook": [{"name": "population", "description": "Study population"}],
        "sources": copy.deepcopy(sources),
    }


class InitReviewTests(unittest.TestCase):
    def create_review(self, payload):
        temp_dir = tempfile.TemporaryDirectory()
        base = Path(init_review.main(payload, reviews_root=temp_dir.name))
        protocol = (base / "protocol.md").read_text(encoding="utf-8")
        manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        return temp_dir, base, protocol, manifest

    def assert_rejected_without_writing(self, payload):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                init_review.main(payload, reviews_root=temp_dir)
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_openalex_only_is_recorded_in_protocol_and_manifest(self):
        temp_dir, base, protocol, manifest = self.create_review(
            payload_for([
                {
                    "source": "openalex",
                    "reason": "Couverture multidisciplinaire générale",
                    "query": OPENALEX_QUERY,
                }
            ])
        )
        self.addCleanup(temp_dir.cleanup)

        self.assertTrue(base.joinpath("protocol.md").is_file())
        self.assertEqual(manifest["sources"], ["openalex"])
        self.assertEqual(manifest["queries"], {"openalex": OPENALEX_QUERY})
        self.assertEqual(
            manifest["source_reasons"],
            {"openalex": "Couverture multidisciplinaire générale"},
        )
        self.assertIn("## Plan de recherche multi-source", protocol)
        self.assertIn("### Source : `openalex`", protocol)
        self.assertIn("Couverture multidisciplinaire générale", protocol)
        self.assertIn(json.dumps(OPENALEX_QUERY, ensure_ascii=False, indent=2), protocol)

    def test_pubmed_only_is_recorded_in_protocol_and_manifest(self):
        temp_dir, _, protocol, manifest = self.create_review(
            payload_for([
                {
                    "source": "pubmed",
                    "reason": "Couverture biomédicale spécialisée",
                    "query": PUBMED_QUERY,
                }
            ])
        )
        self.addCleanup(temp_dir.cleanup)

        self.assertEqual(manifest["sources"], ["pubmed"])
        self.assertEqual(manifest["queries"], {"pubmed": PUBMED_QUERY})
        self.assertEqual(
            manifest["source_reasons"],
            {"pubmed": "Couverture biomédicale spécialisée"},
        )
        self.assertIn("### Source : `pubmed`", protocol)
        self.assertIn(json.dumps(PUBMED_QUERY, ensure_ascii=False, indent=2), protocol)

    def test_eric_only_is_recorded_in_protocol_and_manifest(self):
        temp_dir, _, protocol, manifest = self.create_review(
            payload_for([
                {
                    "source": "eric",
                    "reason": "Couverture spécialisée des publications en éducation",
                    "query": ERIC_QUERY,
                }
            ])
        )
        self.addCleanup(temp_dir.cleanup)

        self.assertEqual(manifest["sources"], ["eric"])
        self.assertEqual(manifest["queries"], {"eric": ERIC_QUERY})
        self.assertEqual(
            manifest["source_reasons"],
            {"eric": "Couverture spécialisée des publications en éducation"},
        )
        self.assertIn("### Source : `eric`", protocol)
        self.assertIn(json.dumps(ERIC_QUERY, ensure_ascii=False, indent=2), protocol)

    def test_both_sources_keep_order_reasons_and_exact_queries(self):
        sources = [
            {
                "source": "openalex",
                "reason": "Couverture multidisciplinaire générale",
                "query": OPENALEX_QUERY,
            },
            {
                "source": "pubmed",
                "reason": "Couverture biomédicale spécialisée",
                "query": PUBMED_QUERY,
            },
        ]
        temp_dir, _, protocol, manifest = self.create_review(payload_for(sources))
        self.addCleanup(temp_dir.cleanup)

        self.assertEqual(manifest["sources"], ["openalex", "pubmed"])
        self.assertEqual(
            manifest["queries"],
            {"openalex": OPENALEX_QUERY, "pubmed": PUBMED_QUERY},
        )
        self.assertEqual(
            manifest["source_reasons"],
            {
                "openalex": "Couverture multidisciplinaire générale",
                "pubmed": "Couverture biomédicale spécialisée",
            },
        )
        self.assertLess(protocol.index("`openalex`"), protocol.index("`pubmed`"))
        self.assertIn('"search": "climate adaptation & resilience \\\"$\\\""', protocol)
        self.assertIn(json.dumps(PUBMED_QUERY, ensure_ascii=False, indent=2), protocol)

    def test_three_sources_keep_exact_queries_and_reasons(self):
        sources = [
            {
                "source": "openalex",
                "reason": "Couverture multidisciplinaire générale",
                "query": OPENALEX_QUERY,
            },
            {
                "source": "pubmed",
                "reason": "Couverture biomédicale spécialisée",
                "query": PUBMED_QUERY,
            },
            {
                "source": "eric",
                "reason": "Couverture spécialisée des publications en éducation",
                "query": ERIC_QUERY,
            },
        ]
        temp_dir, _, protocol, manifest = self.create_review(payload_for(sources))
        self.addCleanup(temp_dir.cleanup)

        self.assertEqual(manifest["sources"], ["openalex", "pubmed", "eric"])
        self.assertEqual(
            manifest["queries"],
            {"openalex": OPENALEX_QUERY, "pubmed": PUBMED_QUERY, "eric": ERIC_QUERY},
        )
        self.assertEqual(
            manifest["source_reasons"],
            {
                "openalex": "Couverture multidisciplinaire générale",
                "pubmed": "Couverture biomédicale spécialisée",
                "eric": "Couverture spécialisée des publications en éducation",
            },
        )
        self.assertLess(protocol.index("`openalex`"), protocol.index("`pubmed`"))
        self.assertLess(protocol.index("`pubmed`"), protocol.index("`eric`"))
        self.assertIn(json.dumps(ERIC_QUERY, ensure_ascii=False, indent=2), protocol)

    def test_missing_or_empty_sources_are_rejected_before_writing(self):
        invalid_payloads = [
            payload_for([]),
            {
                **payload_for([{"source": "openalex", "reason": "r", "query": OPENALEX_QUERY}]),
                "sources": None,
            },
            {
                **payload_for([{"source": "openalex", "reason": "r", "query": OPENALEX_QUERY}]),
                "sources": "openalex",
            },
        ]
        for invalid_payload in invalid_payloads:
            with self.subTest(sources=invalid_payload.get("sources")):
                self.assert_rejected_without_writing(invalid_payload)

    def test_duplicate_or_unknown_source_is_rejected_before_writing(self):
        duplicate = payload_for([
            {"source": "openalex", "reason": "r1", "query": OPENALEX_QUERY},
            {"source": "openalex", "reason": "r2", "query": OPENALEX_QUERY},
        ])
        unknown = payload_for([
            {"source": "crossref", "reason": "r", "query": {"query_mode": "search"}},
        ])
        for invalid_payload in (duplicate, unknown):
            with self.subTest(payload=invalid_payload):
                self.assert_rejected_without_writing(invalid_payload)

    def test_empty_reason_is_rejected_before_writing(self):
        for reason in ("", "   ", None):
            invalid_payload = payload_for([
                {"source": "openalex", "reason": reason, "query": OPENALEX_QUERY},
            ])
            with self.subTest(reason=reason):
                self.assert_rejected_without_writing(invalid_payload)

    def test_missing_or_nonstructured_query_is_rejected_before_writing(self):
        invalid_entries = [
            {"source": "openalex", "reason": "r"},
            {"source": "openalex", "reason": "r", "query": "search"},
            {"source": "pubmed", "reason": "r", "query": []},
            {"source": "pubmed", "reason": "r", "query": {}},
            {"source": "eric", "reason": "r", "query": "search"},
            {"source": "eric", "reason": "r", "query": {}},
        ]
        for entry in invalid_entries:
            with self.subTest(entry=entry):
                self.assert_rejected_without_writing(payload_for([entry]))

    def test_incompatible_query_mode_is_rejected_before_writing(self):
        invalid_entries = [
            {
                "source": "openalex",
                "reason": "r",
                "query": {"query_mode": "pubmed", "term": "x"},
            },
            {
                "source": "pubmed",
                "reason": "r",
                "query": {"query_mode": "search", "search": "x"},
            },
            {
                "source": "eric",
                "reason": "r",
                "query": {"query_mode": "search", "search": "x"},
            },
        ]
        for entry in invalid_entries:
            with self.subTest(entry=entry):
                self.assert_rejected_without_writing(payload_for([entry]))


if __name__ == "__main__":
    unittest.main()
