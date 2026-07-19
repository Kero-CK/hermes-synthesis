"""Regression tests for the read-only OpenAlex search contract.

All HTTP responses are deterministic in-memory fixtures.  The test module
never contacts OpenAlex and clears the API-key environment variable while a
request is being simulated.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "search.py"
SPEC = importlib.util.spec_from_file_location("sysrev_search_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


STRUCTURED_QUERY = {
    "query_mode": "search",
    "search": "(climate OR warming) AND adaptation",
    "filter": "from_publication_date:2020-01-01",
}
QUERY = STRUCTURED_QUERY
LEGACY_QUERY = "title_and_abstract.search:climate adaptation,from_publication_date:2020-01-01"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        if isinstance(self.payload, bytes):
            return self.payload
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def work(index: int, *, title: str | None = None, **extra):
    item = {
        "title": title if title is not None else f"Work {index}",
        "doi": f"https://doi.org/10.1234/work{index}",
        "publication_year": 2024,
        "abstract_inverted_index": {"Work": [0], str(index): [1]},
        "open_access": {"oa_url": f"https://example.org/{index}.pdf"},
    }
    item.update(extra)
    return item


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.openalex.org/works",
        code,
        f"HTTP {code}",
        hdrs=None,
        fp=None,
    )


class SearchTests(unittest.TestCase):
    def call_openalex(self, responses, *, query=QUERY, hard_limit=None):
        requests = []

        def fake_urlopen(request, timeout=30):
            requests.append((request, timeout))
            value = responses.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value if isinstance(value, FakeResponse) else FakeResponse(value)

        env = {
            "OPENALEX_API_KEY": "",
            "UNPAYWALL_EMAIL": "tests@example.org",
        }
        if hard_limit is not None:
            env["HARD_LIMIT"] = str(hard_limit)
        with patch.dict(search.os.environ, env, clear=False), \
                patch("urllib.request.urlopen", side_effect=fake_urlopen), \
                patch("time.sleep") as sleep:
            result = search._openalex_search(query)
            sleeps = [call.args[0] for call in sleep.call_args_list]
        return result, requests, sleeps

    def test_free_text_rejected_without_network(self):
        with patch("urllib.request.urlopen") as urlopen, \
                redirect_stderr(io.StringIO()) as stderr:
            result = search._openalex_search("climate adaptation")
        self.assertEqual(result[0], [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")
        urlopen.assert_not_called()
        self.assertIn("https://developers.openalex.org/guides/searching", stderr.getvalue())
        legacy_host = "docs." + "openalex.org"
        self.assertNotIn(legacy_host, stderr.getvalue())

    def test_retired_openalex_string_fails_before_network_and_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "manifest.json").write_text(
                json.dumps({"id": "fixture", "stage": "protocol_done"}),
                encoding="utf-8",
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            manifest_before = (review_dir / "manifest.json").read_bytes()
            with patch("urllib.request.urlopen") as urlopen, \
                    redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(search.InvalidOpenAlexQuery):
                    search.main(rid, {"openalex": LEGACY_QUERY}, use_mock=False)
            self.assertIn("chaîne historique est refusée", stderr.getvalue())
            self.assertFalse((review_dir / "candidates.csv").exists())
            self.assertEqual((review_dir / "manifest.json").read_bytes(), manifest_before)
            urlopen.assert_not_called()

    def test_legacy_query_is_rejected_without_conversion(self):
        for helper in (search.validate_openalex_query, search.prepare_openalex_query,
                       search.serialize_query_for_csv):
            with self.subTest(helper=helper.__name__):
                with self.assertRaises(search.InvalidOpenAlexQuery):
                    helper(LEGACY_QUERY)

    def test_structured_search_query_with_filter_is_prepared_separately(self):
        query = {
            "query_mode": "search",
            "search": "(climate OR warming) AND adaptation",
            "filter": "from_publication_date:2020-01-01",
        }
        prepared = search.prepare_openalex_query(query)
        self.assertEqual(prepared["query_mode"], "search")
        self.assertEqual(
            prepared["params"],
            {
                "search": query["search"],
                "filter": query["filter"],
            },
        )
        self.assertEqual(search.validate_openalex_query(query), query)

    def test_structured_search_query_without_filter_omits_filter(self):
        query = {"query_mode": "search", "search": "adaptation"}
        prepared = search.prepare_openalex_query(query)
        self.assertEqual(prepared, {"query_mode": "search", "params": {"search": "adaptation"}})
        self.assertNotIn("filter", prepared["params"])

    def test_structured_query_preserves_search_text_exactly(self):
        search_text = '("climat Δ" OR warming) AND NOT "sécheresse"'
        query = {"query_mode": "search", "search": search_text}
        prepared = search.prepare_openalex_query(query)
        self.assertEqual(prepared["params"]["search"], search_text)

    def test_structured_query_validation_rejects_invalid_fields(self):
        valid_search = {"query_mode": "search", "search": "climate"}
        invalid_queries = [
            ("search absent", {"query_mode": "search"}),
            ("search vide", {"query_mode": "search", "search": ""}),
            ("search espaces", {"query_mode": "search", "search": "   "}),
            ("search mauvais type", {"query_mode": "search", "search": 42}),
            ("query_mode absent", {"search": "climate"}),
            ("query_mode inconnu", {"query_mode": "other", "search": "climate"}),
            ("query_mode mauvais type", {"query_mode": True, "search": "climate"}),
            ("filter vide", {**valid_search, "filter": ""}),
            ("filter espaces", {**valid_search, "filter": "   "}),
            ("filter mauvais type", {**valid_search, "filter": 2020}),
            ("champ supplémentaire", {**valid_search, "extra": "refusé"}),
        ]
        for label, query in invalid_queries:
            with self.subTest(label=label):
                with self.assertRaises(search.InvalidOpenAlexQuery):
                    search.validate_openalex_query(query)

    def test_structured_query_validation_rejects_non_objects(self):
        for value in ([], 42, True, None):
            with self.subTest(value=value):
                with self.assertRaises(search.InvalidOpenAlexQuery):
                    search.validate_openalex_query(value)

    def test_query_serialization_requires_structured_object(self):
        with self.assertRaises(search.InvalidOpenAlexQuery):
            search.serialize_query_for_csv(LEGACY_QUERY)

    def test_query_serialization_is_canonical_for_structured_object(self):
        query = {
            "filter": "from_publication_date:2020-01-01",
            "search": '"climat Δ" AND adaptation',
            "query_mode": "search",
        }
        serialized = search.serialize_query_for_csv(query)
        self.assertEqual(
            serialized,
            '{"filter":"from_publication_date:2020-01-01",'
            '"query_mode":"search","search":"\\"climat Δ\\" AND adaptation"}',
        )
        self.assertEqual(serialized, search.serialize_query_for_csv(dict(query)))
        self.assertIn("Δ", serialized)
        self.assertEqual(serialized, search.serialize_query_for_csv(query))

    def test_non_openalex_string_provenance_is_exact(self):
        query = "term[Title/Abstract] AND 2020:2024"
        self.assertEqual(
            search.serialize_source_query_for_csv("pubmed", query),
            query,
        )

    def test_non_openalex_object_provenance_is_canonical(self):
        query = {
            "filters": {"date": "2020-01-01"},
            "term": "climate AND adaptation",
        }
        self.assertEqual(
            search.serialize_source_query_for_csv("pubmed", query),
            '{"filters":{"date":"2020-01-01"},"term":"climate AND adaptation"}',
        )

    def test_non_openalex_provenance_does_not_validate_openalex(self):
        query = {"term": "climate", "field": "title"}
        with patch.object(search, "validate_openalex_query") as validate:
            result = search.serialize_source_query_for_csv("pubmed", query)
        self.assertEqual(result, '{"field":"title","term":"climate"}')
        validate.assert_not_called()

    def test_source_provenance_rejects_unsupported_type(self):
        with self.assertRaises(TypeError):
            search.serialize_source_query_for_csv("pubmed", 42)

    def test_main_uses_generic_provenance_for_non_openalex_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "manifest.json").write_text(
                json.dumps({"id": "fixture", "stage": "protocol_done"}),
                encoding="utf-8",
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            query = {"term": "climate", "filters": {"year": 2020}}

            with patch.object(
                search,
                "mcp_search",
                return_value=([work(1)], 1, "complete", "fixture"),
            ), patch("urllib.request.urlopen") as urlopen:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(rid, {"pubmed": query}, use_mock=False)

            with (review_dir / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["source"], "pubmed")
            self.assertEqual(rows[0]["query"], '{"filters":{"year":2020},"term":"climate"}')
            urlopen.assert_not_called()

    def test_query_helpers_do_not_call_network(self):
        query = {"query_mode": "search", "search": "climate"}
        with patch("urllib.request.urlopen") as urlopen:
            search.validate_openalex_query(query)
            search.prepare_openalex_query(query)
            search.serialize_query_for_csv(query)
        urlopen.assert_not_called()

    def test_registry_contains_openalex_metadata(self):
        self.assertIn("openalex", search.CONNECTOR_REGISTRY)
        spec = search.CONNECTOR_REGISTRY["openalex"]
        self.assertIs(spec["search"], search._openalex_search)
        self.assertEqual(spec["endpoint"], "https://api.openalex.org/works")
        self.assertEqual(spec["api_version"], "unversioned")
        self.assertEqual(spec["query_mode"], "search")

    def test_search_source_routes_one_source_and_rejects_unknown_source(self):
        expected = ([{"title": "fixture"}], 1, "complete", "fixture")
        openalex = Mock(return_value=expected)
        with patch.dict(search.CONNECTOR_REGISTRY["openalex"], {"search": openalex}):
            self.assertEqual(search.search_source("openalex", QUERY), expected)
        openalex.assert_called_once_with(QUERY)
        with self.assertRaises(NotImplementedError):
            search.search_source("not-a-source", "source query")

    def test_search_source_accepts_structured_query(self):
        expected = ([{"title": "fixture"}], 1, "complete", "fixture")
        openalex = Mock(return_value=expected)
        query = dict(STRUCTURED_QUERY)
        with patch.dict(search.CONNECTOR_REGISTRY["openalex"], {"search": openalex}):
            self.assertEqual(search.search_source("openalex", query), expected)
        openalex.assert_called_once_with(query)

    def test_mcp_search_remains_compatible_alias(self):
        self.assertIs(search.mcp_search, search.search_source)
        expected = ([{"title": "fixture"}], 1, "complete", "fixture")
        openalex = Mock(return_value=expected)
        with patch.dict(search.CONNECTOR_REGISTRY["openalex"], {"search": openalex}):
            self.assertEqual(search.mcp_search("openalex", QUERY), expected)
        openalex.assert_called_once_with(QUERY)

    def test_mcp_search_accepts_structured_query(self):
        expected = ([{"title": "fixture"}], 1, "complete", "fixture")
        openalex = Mock(return_value=expected)
        query = dict(STRUCTURED_QUERY)
        with patch.dict(search.CONNECTOR_REGISTRY["openalex"], {"search": openalex}):
            self.assertEqual(search.mcp_search("openalex", query), expected)
        openalex.assert_called_once_with(query)

    def test_invalid_connector_contracts_are_rejected(self):
        invalid_results = [
            ("results non-list", ({"title": "fixture"}, 1, "complete", "ok")),
            ("expected négatif", ([], -1, "complete", "ok")),
            ("expected mauvais type", ([], "1", "complete", "ok")),
            ("expected booléen", ([], True, "complete", "ok")),
            ("statut inconnu", ([], 0, "unknown", "ok")),
            ("reason non-string", ([], 0, "complete", None)),
            ("tuple incomplet", ([], 0, "complete")),
        ]
        for label, result in invalid_results:
            with self.subTest(label=label):
                with self.assertRaises(search.InvalidSearchContract):
                    search._validate_search_result("openalex", result)

    def test_validator_accepts_unknown_expected_count(self):
        result = ([], None, "incomplete", "missing_or_invalid_expected_count")
        self.assertEqual(search._validate_search_result("openalex", result), result)

    def test_main_records_invalid_connector_contract_as_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "prisma.json").write_text(
                json.dumps({"identified": 0}, ensure_ascii=False), encoding="utf-8"
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            with patch.object(search, "mcp_search", return_value=([], 0, "unknown", "bad")):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(rid, {"openalex": QUERY}, use_mock=False)

            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            metadata = manifest["search_meta"]["openalex"]
            self.assertEqual(manifest["search_status"], "error")
            self.assertEqual(metadata["status"], "error")
            self.assertIsNone(metadata["expected"])
            self.assertIn("contrat de recherche invalide", metadata["reason"])
            self.assertEqual(metadata["endpoint"], "https://api.openalex.org/works")
            self.assertEqual(metadata["api_version"], "unversioned")
            self.assertEqual(metadata["query_mode"], "search")

    def test_main_records_unknown_source_with_expected_null(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                search.main(rid, {"not-a-source": QUERY}, use_mock=False)

            manifest_text = (review_dir / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            metadata = manifest["search_meta"]["not-a-source"]
            self.assertEqual(metadata["status"], "error")
            self.assertIsNone(metadata["expected"])
            self.assertIn('"expected": null', manifest_text)

    def test_manifest_serializes_unknown_expected_count_as_null(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            result = ([work(1)], None, "incomplete", "missing_or_invalid_expected_count")
            with patch.object(search, "mcp_search", return_value=result):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(rid, {"openalex": QUERY}, use_mock=False)

            manifest_text = (review_dir / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertIsNone(manifest["search_meta"]["openalex"]["expected"])
            self.assertIn('"expected": null', manifest_text)

    def test_manifest_preserves_structured_query_and_dynamic_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            query = dict(STRUCTURED_QUERY)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                search.main(rid, {"openalex": query}, use_mock=True)

            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            with (review_dir / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(manifest["queries"]["openalex"], query)
            self.assertEqual(manifest["search_meta"]["openalex"]["query_mode"], "search")
            self.assertTrue(rows)
            self.assertEqual(rows[0]["query"], search.serialize_query_for_csv(query))
            self.assertNotEqual(rows[0]["query"], repr(query))

    def test_invalid_structured_query_is_recorded_as_error_without_network(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            invalid = {"query_mode": "search", "search": "   "}

            with patch("urllib.request.urlopen") as urlopen:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(rid, {"openalex": invalid}, use_mock=True)

            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            metadata = manifest["search_meta"]["openalex"]
            self.assertEqual(manifest["queries"]["openalex"], invalid)
            self.assertEqual(manifest["search_status"], "error")
            self.assertEqual(metadata["query_mode"], "unknown")
            self.assertEqual(metadata["status"], "error")
            self.assertIsNone(metadata["expected"])
            self.assertIn("Requête OpenAlex invalide", metadata["reason"])
            urlopen.assert_not_called()

    def test_unknown_status_fails_closed_in_global_priority(self):
        self.assertEqual(
            search._global_search_status({"openalex": {"status": "unknown"}}),
            "error",
        )
        self.assertEqual(
            search._global_search_status({"openalex": {"status": []}}),
            "error",
        )
        self.assertEqual(
            search._global_search_status({"openalex": {"status": "complete"}}),
            "complete",
        )

    def test_mock_search_preserves_four_field_contract(self):
        results, expected, status, reason = search.mock_search(
            "openalex", dict(STRUCTURED_QUERY)
        )
        self.assertEqual(len(results), expected)
        self.assertEqual((status, reason), ("complete", "mock"))

    def test_mock_search_accepts_structured_query(self):
        results, expected, status, reason = search.mock_search(
            "openalex", dict(STRUCTURED_QUERY)
        )
        self.assertEqual(len(results), expected)
        self.assertEqual((status, reason), ("complete", "mock"))

    def test_mock_search_rejects_invalid_structured_query(self):
        result = search.mock_search(
            "openalex", {"query_mode": "search", "search": ""}
        )
        self.assertEqual(result[0], [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")
        self.assertIn("Requête OpenAlex invalide", result[3])

    def test_filter_is_transmitted_exactly(self):
        payload = {"meta": {"count": 0}, "results": []}
        result, requests, _ = self.call_openalex([payload])
        query_values = parse_qs(urlparse(requests[0][0].full_url).query)
        self.assertEqual(query_values["search"], [STRUCTURED_QUERY["search"]])
        self.assertEqual(query_values["filter"], [STRUCTURED_QUERY["filter"]])
        self.assertEqual(query_values["per_page"], ["100"])
        self.assertEqual(result, ([], 0, "complete", "zero_results"))

    def test_structured_query_transmits_search_and_filter_separately(self):
        payload = {"meta": {"count": 0}, "results": []}
        result, requests, _ = self.call_openalex([payload], query=STRUCTURED_QUERY)
        query_values = parse_qs(urlparse(requests[0][0].full_url).query)
        self.assertEqual(query_values["search"], [STRUCTURED_QUERY["search"]])
        self.assertEqual(query_values["filter"], [STRUCTURED_QUERY["filter"]])
        self.assertNotIn("search=", query_values["filter"])
        self.assertEqual(result, ([], 0, "complete", "zero_results"))

    def test_structured_query_without_filter_omits_filter_parameter(self):
        query = {"query_mode": "search", "search": "adaptation"}
        payload = {"meta": {"count": 0}, "results": []}
        result, requests, _ = self.call_openalex([payload], query=query)
        query_values = parse_qs(urlparse(requests[0][0].full_url).query)
        self.assertEqual(query_values["search"], [query["search"]])
        self.assertNotIn("filter", query_values)
        self.assertEqual(result, ([], 0, "complete", "zero_results"))

    def test_structured_query_preserves_special_text_after_url_encoding(self):
        search_text = '("climat Δ" OR warming) AND NOT "sécheresse"'
        query = {"query_mode": "search", "search": search_text}
        payload = {"meta": {"count": 0}, "results": []}
        _, requests, _ = self.call_openalex([payload], query=query)
        query_values = parse_qs(urlparse(requests[0][0].full_url).query)
        self.assertEqual(query_values["search"], [search_text])

    def test_structured_query_paginates_over_multiple_pages(self):
        first = {"meta": {"count": 150}, "results": [work(i) for i in range(100)]}
        second = {"meta": {"count": 150}, "results": [work(i) for i in range(100, 150)]}
        result, requests, _ = self.call_openalex(
            [first, second], query=STRUCTURED_QUERY
        )
        pages = [parse_qs(urlparse(request.full_url).query)["page"][0]
                 for request, _ in requests]
        self.assertEqual(pages, ["1", "2"])
        self.assertEqual(len(result[0]), 150)
        self.assertEqual(result[1:], (150, "complete", ""))

    def test_structured_query_respects_hard_limit(self):
        payload = {"meta": {"count": 3}, "results": [work(1), work(2), work(3)]}
        result, requests, _ = self.call_openalex(
            [payload], query=STRUCTURED_QUERY, hard_limit=2
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[1:3], (3, "capped"))

    def test_structured_query_retries_without_changing_status_logic(self):
        payload = {"meta": {"count": 0}, "results": []}
        result, requests, sleeps = self.call_openalex(
            [http_error(503), payload], query=STRUCTURED_QUERY
        )
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleeps, [1])
        self.assertEqual(result, ([], 0, "complete", "zero_results"))

    def test_invalid_structured_query_fails_before_network(self):
        invalid = {"query_mode": "search", "search": "   "}
        with patch("urllib.request.urlopen") as urlopen:
            result = search._openalex_search(invalid)
        self.assertEqual(result[0], [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")
        self.assertIn("Requête OpenAlex invalide", result[3])
        urlopen.assert_not_called()

    def test_abstract_reconstruction_doi_and_unicode(self):
        payload = {
            "meta": {"count": 1},
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "title": "Étude Δ",
                    "doi": "https://doi.org/10.1234/épreuve",
                    "publication_year": 2025,
                    "abstract_inverted_index": {"Résumé": [0], "été": [1], "✓": [2]},
                    "open_access": {"oa_url": "https://example.org/étude.pdf"},
                }
            ],
        }
        result, _, _ = self.call_openalex([payload])
        self.assertEqual(result[2], "complete")
        self.assertEqual(result[0][0]["abstract"], "Résumé été ✓")
        self.assertEqual(result[0][0]["doi"], "10.1234/épreuve")
        self.assertEqual(result[0][0]["source_id"], "https://openalex.org/W123")
        self.assertEqual(result[0][0]["title"], "Étude Δ")

    def test_missing_openalex_fields_use_empty_values(self):
        payload = {"meta": {"count": 1}, "results": [{}]}
        result, _, _ = self.call_openalex([payload])
        self.assertEqual(result[2], "complete")
        self.assertEqual(
            result[0][0],
            {
                "title": "",
                "doi": "",
                "source_id": "",
                "year": "",
                "abstract": "",
                "oa_url": "",
            },
        )

    def test_zero_results_have_explicit_reason(self):
        result, _, _ = self.call_openalex([{"meta": {"count": 0}, "results": []}])
        self.assertEqual(result, ([], 0, "complete", "zero_results"))

    def test_invalid_or_missing_expected_count_keeps_current_page(self):
        payloads = [
            ("absent", {"results": [work(1)]}),
            ("null", {"meta": {"count": None}, "results": [work(1)]}),
            ("invalid", {"meta": {"count": "many"}, "results": [work(1)]}),
            ("negative", {"meta": {"count": -1}, "results": [work(1)]}),
            ("boolean", {"meta": {"count": True}, "results": [work(1)]}),
        ]
        for label, payload in payloads:
            with self.subTest(label=label):
                result, requests, _ = self.call_openalex([payload])
                self.assertEqual(len(requests), 1)
                self.assertEqual(len(result[0]), 1)
                self.assertIsNone(result[1])
                self.assertEqual(result[2:], ("incomplete", "missing_or_invalid_expected_count"))

    def test_unknown_expected_count_with_no_results_is_incomplete(self):
        payloads = [
            {"results": []},
            {"meta": {"count": None}, "results": []},
            {"meta": {"count": "many"}, "results": []},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                result, requests, _ = self.call_openalex([payload])
                self.assertEqual(len(requests), 1)
                self.assertEqual(
                    result,
                    ([], None, "incomplete", "missing_or_invalid_expected_count"),
                )

    def test_invalid_expected_count_on_later_page_stops_after_that_page(self):
        first = {"meta": {"count": 150}, "results": [work(i) for i in range(100)]}
        second = {"results": [work(100)]}
        result, requests, _ = self.call_openalex([first, second])
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(result[0]), 101)
        self.assertEqual(result[1], 150)
        self.assertEqual(result[2:], ("incomplete", "missing_or_invalid_expected_count"))

    def test_pagination_over_multiple_pages(self):
        first = {"meta": {"count": 150}, "results": [work(i) for i in range(100)]}
        second = {"meta": {"count": 150}, "results": [work(i) for i in range(100, 150)]}
        result, requests, _ = self.call_openalex([first, second])
        pages = [parse_qs(urlparse(request.full_url).query)["page"][0] for request, _ in requests]
        self.assertEqual(pages, ["1", "2"])
        self.assertEqual(len(result[0]), 150)
        self.assertEqual(result[1:], (150, "complete", ""))

    def test_cursor_switch_reloads_first_page_without_duplicate(self):
        first = {"meta": {"count": 10001}, "results": [work(0, title="discarded")]}
        cursor_first = {"meta": {"count": 10001, "next_cursor": "cursor-1"}, "results": [work(1)]}
        cursor_second = {"meta": {"count": 10001, "next_cursor": None}, "results": [work(2)]}
        result, requests, _ = self.call_openalex([first, cursor_first, cursor_second], hard_limit=2)
        query_values = [parse_qs(urlparse(request.full_url).query) for request, _ in requests]
        self.assertEqual(query_values[0]["page"], ["1"])
        self.assertEqual(query_values[1]["cursor"], ["*"])
        self.assertEqual(query_values[2]["cursor"], ["cursor-1"])
        self.assertEqual([item["title"] for item in result[0]], ["Work 1", "Work 2"])
        self.assertEqual(len({item["doi"] for item in result[0]}), 2)
        self.assertEqual(result[2], "capped")

    def test_hard_limit_below_total_is_capped(self):
        payload = {"meta": {"count": 3}, "results": [work(1), work(2), work(3)]}
        result, _, _ = self.call_openalex([payload], hard_limit=2)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[1:3], (3, "capped"))

    def test_hard_limit_equal_total_is_complete(self):
        payload = {"meta": {"count": 2}, "results": [work(1), work(2)]}
        result, _, _ = self.call_openalex([payload], hard_limit=2)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[1:], (2, "complete", ""))

    def test_temporary_http_errors_are_retried(self):
        for code in (429, 500, 502, 503, 504):
            with self.subTest(code=code):
                payload = {"meta": {"count": 0}, "results": []}
                result, requests, sleeps = self.call_openalex(
                    [http_error(code), http_error(code), http_error(code), payload]
                )
                self.assertEqual(result, ([], 0, "complete", "zero_results"))
                self.assertEqual(len(requests), 4)
                self.assertEqual(sleeps, [1, 2, 4])

    def test_no_sleep_after_final_temporary_failure(self):
        result, requests, sleeps = self.call_openalex(
            [http_error(503), http_error(503), http_error(503), http_error(503)]
        )
        self.assertEqual(len(requests), 4)
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "incomplete")
        self.assertIn("503", result[3])

    def test_non_temporary_http_error_is_not_retried(self):
        result, requests, sleeps = self.call_openalex([http_error(400)])
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")
        self.assertIn("400", result[3])

    def test_timeout_is_error(self):
        result, requests, sleeps = self.call_openalex([TimeoutError("timed out")])
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")
        self.assertIn("timed out", result[3])

    def test_invalid_json_is_error(self):
        result, requests, sleeps = self.call_openalex([FakeResponse(b"not-json")])
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])
        self.assertIsNone(result[1])
        self.assertEqual(result[2], "error")

    def test_valid_total_is_preserved_after_later_error(self):
        first = {"meta": {"count": 150}, "results": [work(i) for i in range(100)]}
        result, requests, _ = self.call_openalex([first, http_error(400)])
        self.assertEqual(len(requests), 2)
        self.assertEqual(result[1], 150)
        self.assertEqual(result[2], "error")
        self.assertIn("400", result[3])

    def test_valid_total_is_preserved_after_later_invalid_json(self):
        first = {"meta": {"count": 150}, "results": [work(i) for i in range(100)]}
        result, requests, _ = self.call_openalex([first, FakeResponse(b"not-json")])
        self.assertEqual(len(requests), 2)
        self.assertEqual(result[1], 150)
        self.assertEqual(result[2], "error")

    def test_partial_result_is_incomplete(self):
        payload = {"meta": {"count": 3}, "results": [work(1), work(2)]}
        result, _, _ = self.call_openalex([payload])
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(result[1:3], (3, "incomplete"))
        self.assertIn("2/3", result[3])

    def test_main_outputs_and_global_status_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "prisma.json").write_text(
                json.dumps({"identified": 0}, ensure_ascii=False), encoding="utf-8"
            )
            (review_dir / "manifest.json").write_text(
                json.dumps({"id": "fixture", "stage": "protocol_done"}), encoding="utf-8"
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            def fake_dispatch(source, query):
                statuses = {
                    "openalex": ([work(1)], 1, "complete", "ok"),
                    "source_capped": ([work(2)], 2, "capped", "limit"),
                    "source_error": ([work(3)], 3, "error", "bad request"),
                }
                return statuses[source]

            queries = {
                "openalex": QUERY,
                "source_capped": "source query",
                "source_error": "another query",
            }
            with patch.object(search, "mcp_search", side_effect=fake_dispatch):
                with redirect_stdout(io.StringIO()):
                    search.main(rid, queries, use_mock=False)

            with (review_dir / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            prisma = json.loads((review_dir / "prisma.json").read_text(encoding="utf-8"))
            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(len(rows), 3)
            self.assertEqual(
                list(rows[0].keys()),
                [
                    "title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status",
                    "source", "query", "date",
                ],
            )
            self.assertIn("source_id", rows[0])
            self.assertEqual(prisma["identified"], 3)
            self.assertEqual(manifest["stage"], "search_done")
            self.assertEqual(manifest["search_status"], "error")
            self.assertEqual(manifest["queries"], queries)
            self.assertEqual(
                manifest["search_meta"]["openalex"]["endpoint"],
                "https://api.openalex.org/works",
            )
            self.assertEqual(
                manifest["search_meta"]["openalex"]["api_version"],
                "unversioned",
            )
            self.assertEqual(
                manifest["search_meta"]["openalex"]["query_mode"],
                "search",
            )
            self.assertEqual(manifest["search_meta"]["source_capped"]["status"], "capped")
            self.assertEqual(manifest["search_meta"]["source_error"]["status"], "error")
            self.assertEqual(rows[0]["source"], "openalex")
            self.assertEqual(rows[0]["query"], search.serialize_query_for_csv(QUERY))
            self.assertTrue(rows[0]["date"])


if __name__ == "__main__":
    unittest.main()
