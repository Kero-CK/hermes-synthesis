"""Deterministic ERIC connector tests; no test performs a real HTTP call."""

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
SPEC = importlib.util.spec_from_file_location("sysrev_search_eric_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


QUERY = {
    "query_mode": "eric",
    "search": '"generative AI" AND "student feedback"',
    "sort": "publicationdateyear desc",
}


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


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        search.ERIC_ENDPOINT,
        code,
        f"HTTP {code}",
        hdrs=None,
        fp=None,
    )


def eric_doc(index: int, *, eric_id: str | None = None, **extra) -> dict:
    doc = {
        "id": eric_id or f"EJ{index:06d}",
        "title": f"ERIC notice {index}",
        "description": f"Abstract for ERIC notice {index}.",
        "author": ["Ada Lovelace", "Alan Turing"],
        "publicationdateyear": 2025,
        "doi": f"https://doi.org/10.1000/eric{index}",
        "url": f"https://eric.ed.gov/?id=EJ{index:06d}",
        "publicationtype": ["Journal Articles"],
        "subject": ["Higher Education", "Artificial Intelligence"],
    }
    doc.update(extra)
    return doc


def eric_payload(count, docs=None):
    return {
        "response": {
            "numFound": count,
            "start": 0,
            "docs": [] if docs is None else docs,
        }
    }


def request_params(request):
    return parse_qs(urlparse(request.full_url).query, keep_blank_values=True)


class EricTests(unittest.TestCase):
    def call_eric(self, responses, *, query=QUERY, hard_limit=None):
        requests = []

        def fake_urlopen(request, timeout=30):
            requests.append((request, timeout))
            value = responses.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value if isinstance(value, FakeResponse) else FakeResponse(value)

        env = {}
        if hard_limit is not None:
            env["HARD_LIMIT"] = str(hard_limit)
        with patch.dict(search.os.environ, env, clear=False), \
                patch("urllib.request.urlopen", side_effect=fake_urlopen), \
                patch("time.sleep") as sleep:
            result = search._eric_search(query)
            sleeps = [call.args[0] for call in sleep.call_args_list]
        return result, requests, sleeps

    def test_query_contract_and_serialization_preserve_exact_values(self):
        query = {
            "query_mode": "eric",
            "search": '  "IA générative" & feedback  ',
            "sort": "publicationdateyear desc",
        }
        self.assertEqual(search.validate_eric_query(query), query)
        self.assertEqual(
            search.prepare_eric_query(query),
            {
                "query_mode": "eric",
                "params": {
                    "search": query["search"],
                    "sort": query["sort"],
                },
            },
        )
        self.assertEqual(
            search.serialize_eric_query_for_csv(query),
            json.dumps(query, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(
            search.serialize_source_query_for_csv("eric", query),
            search.serialize_eric_query_for_csv(query),
        )

    def test_invalid_query_shapes_are_rejected(self):
        invalid_queries = [
            "generative AI",
            {"query_mode": "search", "search": "AI"},
            {"query_mode": "eric", "search": ""},
            {"query_mode": "eric", "search": "   "},
            {"query_mode": "eric", "search": 42},
            {"query_mode": "eric", "search": "AI", "sort": 42},
            {"query_mode": "eric", "search": "AI", "sort": " "},
            {"search": "AI"},
            {"query_mode": "eric", "search": "AI", "unknown": True},
            [],
            None,
            True,
        ]
        for invalid in invalid_queries:
            with self.subTest(invalid=invalid):
                with self.assertRaises(search.InvalidEricQuery):
                    search.validate_eric_query(invalid)

    def test_invalid_query_is_rejected_before_network_and_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            manifest_before = json.dumps(
                {"id": "fixture", "stage": "protocol_done"}, ensure_ascii=False
            )
            (review_dir / "manifest.json").write_text(manifest_before, encoding="utf-8")
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            invalid = {"query_mode": "eric", "search": "AI", "extra": "no"}

            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(search.InvalidEricQuery):
                    search.main(rid, {"eric": invalid}, use_mock=False)

            urlopen.assert_not_called()
            self.assertFalse((review_dir / "candidates.csv").exists())
            self.assertEqual(
                (review_dir / "manifest.json").read_text(encoding="utf-8"),
                manifest_before,
            )

    def test_exact_parameters_are_url_encoded_without_rewriting(self):
        query = {
            "query_mode": "eric",
            "search": '  "IA générative" & feedback / students  ',
            "sort": "publicationdateyear desc",
        }
        result, requests, _ = self.call_eric([eric_payload(0)], query=query)
        self.assertEqual(result, ([], 0, "complete", "zero_results"))
        self.assertEqual(len(requests), 1)
        params = request_params(requests[0][0])
        self.assertEqual(params["search"], [query["search"]])
        self.assertEqual(params["sort"], [query["sort"]])
        self.assertEqual(params["format"], ["json"])
        self.assertEqual(params["start"], ["0"])
        self.assertEqual(params["rows"], ["200"])
        self.assertIn("fields", params)
        self.assertNotIn("api_key", params)
        self.assertNotIn("email", params)

    def test_zero_results_are_complete(self):
        result, requests, sleeps = self.call_eric([eric_payload(0)])
        self.assertEqual(result, ([], 0, "complete", "zero_results"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])

    def test_multiple_pages_use_start_rows_at_most_200(self):
        responses = [
            eric_payload(401, [eric_doc(i) for i in range(200)]),
            eric_payload(401, [eric_doc(i) for i in range(200, 400)]),
            eric_payload(401, [eric_doc(400)]),
        ]
        result, requests, _ = self.call_eric(responses)
        self.assertEqual(len(result[0]), 401)
        self.assertEqual(result[1:], (401, "complete", ""))
        params = [request_params(request) for request, _ in requests]
        self.assertEqual([item["start"] for item in params], [["0"], ["200"], ["400"]])
        self.assertEqual([item["rows"] for item in params], [["200"], ["200"], ["20"]])

    def test_hard_limit_is_capped_without_fetching_beyond_limit(self):
        responses = [
            eric_payload(401, [eric_doc(i) for i in range(200)]),
            eric_payload(401, [eric_doc(i) for i in range(200, 250)]),
        ]
        result, requests, _ = self.call_eric(responses, hard_limit=250)
        self.assertEqual(len(result[0]), 250)
        self.assertEqual(result[1:3], (401, "capped"))
        params = [request_params(request) for request, _ in requests]
        self.assertEqual([item["rows"] for item in params], [["200"], ["50"]])

    def test_hard_limit_below_minimum_requests_20_but_keeps_only_limit(self):
        result, requests, _ = self.call_eric(
            [eric_payload(401, [eric_doc(i) for i in range(20)])],
            hard_limit=5,
        )
        self.assertEqual(len(result[0]), 5)
        self.assertEqual(result[1:3], (401, "capped"))
        params = [request_params(request) for request, _ in requests]
        self.assertEqual([item["rows"] for item in params], [["20"]])

    def test_hard_limit_zero_fetches_counter_with_rows_20_and_keeps_zero(self):
        result, requests, _ = self.call_eric(
            [eric_payload(401, [eric_doc(i) for i in range(20)])],
            hard_limit=0,
        )
        self.assertEqual(result, ([], 401, "capped", "plafond 0 atteint"))
        params = [request_params(request) for request, _ in requests]
        self.assertEqual([item["rows"] for item in params], [["20"]])

    def test_all_eric_requests_keep_rows_between_20_and_200(self):
        responses = [
            eric_payload(401, [eric_doc(i) for i in range(200)]),
            eric_payload(401, [eric_doc(i) for i in range(200, 400)]),
            eric_payload(401, [eric_doc(400)]),
        ]
        _, requests, _ = self.call_eric(responses)
        for request, _ in requests:
            rows = int(request_params(request)["rows"][0])
            self.assertGreaterEqual(rows, search.ERIC_MIN_PAGE_SIZE)
            self.assertLessEqual(rows, search.ERIC_PAGE_SIZE)

        _, requests, _ = self.call_eric(
            [eric_payload(401, [eric_doc(i) for i in range(20)])],
            hard_limit=5,
        )
        for request, _ in requests:
            rows = int(request_params(request)["rows"][0])
            self.assertGreaterEqual(rows, search.ERIC_MIN_PAGE_SIZE)
            self.assertLessEqual(rows, search.ERIC_PAGE_SIZE)

        _, requests, _ = self.call_eric(
            [eric_payload(401, [eric_doc(i) for i in range(20)])],
            hard_limit=0,
        )
        for request, _ in requests:
            rows = int(request_params(request)["rows"][0])
            self.assertGreaterEqual(rows, search.ERIC_MIN_PAGE_SIZE)
            self.assertLessEqual(rows, search.ERIC_PAGE_SIZE)

    def test_missing_or_invalid_counter_is_incomplete_without_pagination(self):
        invalid_payloads = [
            {"response": {"docs": []}},
            {"response": {"numFound": None, "docs": []}},
            {"response": {"numFound": "many", "docs": []}},
            {"response": {"numFound": -1, "docs": []}},
            {"response": {"numFound": True, "docs": []}},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                result, requests, _ = self.call_eric([payload])
                self.assertEqual(
                    result,
                    ([], None, "incomplete", "missing_or_invalid_expected_count"),
                )
                self.assertEqual(len(requests), 1)

    def test_invalid_json_is_error_before_counter_and_incomplete_after_counter(self):
        result, requests, _ = self.call_eric([b"{not-json"])
        self.assertEqual(result[:3], ([], None, "error"))
        self.assertEqual(len(requests), 1)

        result, requests, _ = self.call_eric(
            [eric_payload(2, [eric_doc(1)]), b"not-json"]
        )
        self.assertEqual(result[0], [search._eric_notice_to_result(eric_doc(1))])
        self.assertEqual(result[1:3], (2, "incomplete"))
        self.assertEqual(len(requests), 2)

    def test_http_400_is_total_error_and_503_retries_four_times(self):
        result, requests, sleeps = self.call_eric([http_error(400)])
        self.assertEqual(result[:3], ([], None, "error"))
        self.assertIn("400", result[3])
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])

        result, requests, sleeps = self.call_eric([http_error(503)] * 4)
        self.assertEqual(result[:3], ([], None, "error"))
        self.assertEqual(len(requests), 4)
        self.assertEqual(sleeps, [1, 2, 4])

    def test_page_http_503_retry_exhaustion_preserves_counter(self):
        result, requests, sleeps = self.call_eric(
            [eric_payload(2, [eric_doc(1)]), http_error(503), http_error(503),
             http_error(503), http_error(503)]
        )
        self.assertEqual(len(requests), 5)
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(result[0], [search._eric_notice_to_result(eric_doc(1))])
        self.assertEqual(result[1], 2)
        self.assertEqual(result[2], "incomplete")

    def test_invalid_notice_is_incomplete_without_silent_loss(self):
        result, requests, _ = self.call_eric(
            [eric_payload(2, [eric_doc(1), {"title": "missing id"}])]
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(result[0]), 1)
        self.assertEqual(result[1:3], (2, "incomplete"))
        self.assertEqual(result[3], "invalid_eric_notice")

    def test_notice_metadata_and_stable_source_id_are_mapped(self):
        doc = {
            "id": "ED123456",
            "title": "A <b>complex</b> ERIC title",
            "description": "Abstract with &amp; markup.",
            "author": [{"name": "Ada Lovelace"}, "Alan Turing"],
            "publicationdateyear": "2026",
            "doi": "https://doi.org/10.1000/ABC-123.",
            "url": "https://example.org/fulltext",
            "publicationtype": ["Reports - Research"],
            "subject": ["Feedback", "Higher Education"],
        }
        result, _, _ = self.call_eric([eric_payload(1, [doc])])
        row = result[0][0]
        self.assertEqual(row["source"], "eric")
        self.assertEqual(row["source_id"], "https://eric.ed.gov/?id=ED123456")
        self.assertEqual(row["title"], "A complex ERIC title")
        self.assertEqual(row["abstract"], "Abstract with & markup.")
        self.assertEqual(row["authors"], "Ada Lovelace; Alan Turing")
        self.assertEqual(row["year"], "2026")
        self.assertEqual(row["doi"], "10.1000/ABC-123")
        self.assertEqual(row["oa_url"], "https://example.org/fulltext")
        self.assertEqual(row["publication_type"], "Reports - Research")
        self.assertEqual(row["subjects"], "Feedback; Higher Education")

    def test_realistic_doi_is_extracted_from_requested_url_field(self):
        doc = eric_doc(1)
        doc.pop("doi")
        doc["url"] = "https://doi.org/10.1016/j.chb.2024.108123"
        result, requests, _ = self.call_eric([eric_payload(1, [doc])])
        row = result[0][0]
        fields = request_params(requests[0][0])["fields"][0].split(",")
        self.assertIn("url", fields)
        self.assertEqual(row["doi"], "10.1016/j.chb.2024.108123")

    def test_registry_routes_eric(self):
        self.assertIn("eric", search.CONNECTOR_REGISTRY)
        spec = search.CONNECTOR_REGISTRY["eric"]
        self.assertIs(spec["search"], search._eric_search)
        self.assertEqual(spec["endpoint"], search.ERIC_ENDPOINT)
        self.assertEqual(spec["query_mode"], "eric")

        expected = ([{"title": "ERIC fixture", "source_id": "eric-1"}], 1, "complete", "fixture")
        routed = Mock(return_value=expected)
        with patch.dict(search.CONNECTOR_REGISTRY["eric"], {"search": routed}):
            self.assertEqual(search.search_source("eric", QUERY), expected)
        routed.assert_called_once_with(QUERY)

    def test_source_id_and_query_provenance_survive_csv_in_three_source_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "prisma.json").write_text('{"identified":0}', encoding="utf-8")
            (review_dir / "manifest.json").write_text(
                '{"id":"fixture","stage":"protocol_done"}', encoding="utf-8"
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            eric_row = search._eric_notice_to_result(eric_doc(1))
            openalex_row = {"title": "OA", "doi": "", "source_id": "oa-1", "year": "2025", "abstract": "", "oa_url": ""}
            pubmed_row = {"title": "PM", "doi": "", "source_id": "pm-1", "year": "2025", "abstract": "", "oa_url": ""}

            def dispatch(source, query):
                if source == "openalex":
                    return [openalex_row], 1, "complete", "fixture"
                if source == "pubmed":
                    return [pubmed_row], 1, "complete", "fixture"
                return [eric_row], 1, "complete", "fixture"

            with patch.object(search, "mcp_search", side_effect=dispatch):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(
                        rid,
                        {
                            "openalex": {"query_mode": "search", "search": "OA"},
                            "pubmed": {"query_mode": "pubmed", "term": "PM"},
                            "eric": QUERY,
                        },
                        use_mock=False,
                    )

            with (review_dir / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            eric_csv_row = next(row for row in rows if row["source"] == "eric")
            self.assertEqual(eric_csv_row["source_id"], eric_row["source_id"])
            self.assertEqual(eric_csv_row["query"], search.serialize_eric_query_for_csv(QUERY))
            self.assertEqual(manifest["search_meta"]["eric"]["endpoint"], search.ERIC_ENDPOINT)
            self.assertEqual(manifest["search_meta"]["eric"]["query_mode"], "eric")
            self.assertEqual(manifest["search_status"], "complete")
            self.assertEqual({row["source"] for row in rows}, {"openalex", "pubmed", "eric"})

    def test_no_secret_like_values_are_added_to_eric_request_or_errors(self):
        secret_email = "private@example.org"
        secret_key = "ERIC-API-SECRET"
        with patch.dict(
            search.os.environ,
            {"NCBI_EMAIL": secret_email, "NCBI_API_KEY": secret_key},
            clear=False,
        ), redirect_stderr(io.StringIO()) as stderr:
            result, requests, _ = self.call_eric([http_error(503)] * 4)
        serialized_requests = "\n".join(request.full_url for request, _ in requests)
        self.assertNotIn(secret_email, serialized_requests)
        self.assertNotIn(secret_key, serialized_requests)
        self.assertNotIn(secret_email, stderr.getvalue())
        self.assertNotIn(secret_key, stderr.getvalue())
        self.assertNotIn(secret_email, result[3])
        self.assertNotIn(secret_key, result[3])


if __name__ == "__main__":
    unittest.main()
