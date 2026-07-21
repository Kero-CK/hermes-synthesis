from __future__ import annotations

import contextlib
import csv
import io
import importlib.util
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_fulltext_unpaywall", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fulltext)


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.unpaywall.org/v2/10.1234/article",
        code,
        f"HTTP {code}",
        hdrs=None,
        fp=io.BytesIO(),
    )


def lookup_payload(**overrides) -> dict:
    payload = {
        "doi": "10.1234/article",
        "title": "Article",
        "best_oa_location": {
            "url_for_pdf": "https://repo.example/article.pdf",
            "url": "https://repo.example/article",
        },
        "oa_locations": [
            {"url_for_pdf": "https://repo.example/article.pdf"},
            {"url": "https://other.example/article.pdf"},
        ],
    }
    payload.update(overrides)
    return payload


def make_review(root: Path, *, doi: str = "10.1234/article", oa_url: str = "") -> tuple[str, dict]:
    (root / "inputs" / "pdfs").mkdir(parents=True)
    row = {
        "title": "Article",
        "doi": doi,
        "source_id": "https://openalex.org/W123",
        "year": "2024",
        "abstract": "",
        "oa_url": oa_url,
        "pdf_status": "",
        "source": "openalex",
        "query": "q",
        "date": "",
    }
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    (root / "decisions.jsonl").write_text(
        json.dumps({
            "doc": doi,
            "stage": "screen_title_abstract",
            "decision": "include",
            "identity_type": "doi",
        }) + "\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({
            "id": "unpaywall",
            "stage": "review_done",
            "search_meta": {"openalex": {"status": "complete"}},
        }),
        encoding="utf-8",
    )
    (root / "prisma.json").write_text(
        json.dumps({"identified": 1, "included": 1}), encoding="utf-8"
    )
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
    return rid, row


class UnpaywallLookupTests(unittest.TestCase):
    def test_doi_absent_does_not_consult_unpaywall(self):
        with patch.dict(os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False), \
                patch.object(fulltext.urllib.request, "urlopen") as urlopen:
            result = fulltext.fetch_unpaywall("")
        self.assertEqual(result["reason"], "unpaywall_doi_absent")
        urlopen.assert_not_called()

    def test_email_is_required_before_network(self):
        with patch.dict(os.environ, {"UNPAYWALL_EMAIL": ""}, clear=False), \
                patch.object(fulltext.urllib.request, "urlopen") as urlopen:
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_email_missing")
        urlopen.assert_not_called()

    def test_best_location_priority_and_urls_are_deduplicated(self):
        requests = []

        def fake_urlopen(request, timeout=30):
            requests.append((request, timeout))
            return FakeResponse(lookup_payload())

        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(fulltext.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = fulltext.fetch_unpaywall("https://doi.org/10.1234/article")

        self.assertEqual(
            result["urls"],
            [
                "https://repo.example/article.pdf",
                "https://repo.example/article",
                "https://other.example/article.pdf",
            ],
        )
        self.assertEqual(requests[0][0].method, "GET")
        self.assertIn("email=secret%40example.org", requests[0][0].full_url)

    def test_returned_doi_contradiction_is_rejected(self):
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request,
            "urlopen",
            return_value=FakeResponse(lookup_payload(doi="10.9999/other")),
        ):
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_identity_mismatch")

    def test_returned_doi_absent_is_rejected(self):
        payload = lookup_payload()
        payload.pop("doi")
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload),
        ):
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_identity_mismatch")

    def test_unknown_doi_is_distinct(self):
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request, "urlopen", side_effect=http_error(404)
        ):
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_doi_unknown")

    def test_api_403_is_not_retried(self):
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request, "urlopen", side_effect=http_error(403)
        ) as urlopen, patch.object(fulltext.time, "sleep") as sleep:
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_api_http_403")
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_no_open_copy_is_distinct(self):
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request,
            "urlopen",
            return_value=FakeResponse({"doi": "10.1234/article", "is_oa": False}),
        ):
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_no_open_copy")

    def test_retries_429_and_server_errors_without_wait_after_success(self):
        responses = [http_error(429), http_error(503), FakeResponse(lookup_payload())]
        requests = []

        def fake_urlopen(request, timeout=30):
            requests.append(request)
            value = responses.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value

        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request, "urlopen", side_effect=fake_urlopen
        ), patch.object(fulltext.time, "sleep") as sleep:
            result = fulltext.fetch_unpaywall("10.1234/article")

        self.assertEqual(result["reason"], "")
        self.assertEqual(len(requests), 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_fourth_server_error_has_no_final_wait(self):
        with patch.dict(
            os.environ, {"UNPAYWALL_EMAIL": "secret@example.org"}, clear=False
        ), patch.object(
            fulltext.urllib.request,
            "urlopen",
            side_effect=[http_error(503)] * 4,
        ), patch.object(fulltext.time, "sleep") as sleep:
            result = fulltext.fetch_unpaywall("10.1234/article")
        self.assertEqual(result["reason"], "unpaywall_api_http_503")
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4])


class UnpaywallDocumentTests(unittest.TestCase):
    def test_url_refused_is_distinct(self):
        with patch.object(
            fulltext,
            "fetch_unpaywall",
            return_value={"reason": "", "doi": "10.1234/article", "title": "Article", "urls": ["https://repo.example/article.pdf"]},
        ), patch.object(fulltext, "download_pdf", return_value=None):
            content, reason = fulltext.retrieve_unpaywall_pdf(
                "10.1234/article", "Article"
            )
        self.assertIsNone(content)
        self.assertEqual(reason, "unpaywall_url_refused")

    def test_html_presented_as_pdf_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "fake.pdf"
            html_path.write_text("<html>not a pdf</html>", encoding="utf-8")
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={"reason": "", "doi": "10.1234/article", "title": "Article", "urls": ["https://repo.example/article"]},
            ), patch.object(fulltext, "download_pdf", return_value=str(html_path)), \
                    patch.object(fulltext, "parse_pdf_real", side_effect=ValueError("not pdf")):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Article"
                )
        self.assertIsNone(content)
        self.assertEqual(reason, "unpaywall_invalid_document")

    def test_invalid_short_markdown_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={"reason": "", "doi": "10.1234/article", "title": "Article", "urls": ["https://repo.example/article.pdf"]},
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value="short"):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Article"
                )
        self.assertIsNone(content)
        self.assertEqual(reason, "unpaywall_invalid_document")

    def test_success_requires_identity_and_long_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            markdown = "# Article\n\n" + "Valid article text " * 40
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={"reason": "", "doi": "10.1234/article", "title": "Article", "urls": ["https://repo.example/article.pdf"]},
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value=markdown):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Article"
                )
        self.assertEqual(content, markdown)
        self.assertIn("Unpaywall", reason)
        self.assertFalse(pdf_path.exists())

    def test_api_doi_correct_but_pdf_is_another_article(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            markdown = "# Other article\n\n" + "Wrong article text " * 40
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={"reason": "", "doi": "10.1234/article", "title": "Target clinical article", "urls": ["https://repo.example/article.pdf"]},
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value=markdown):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Target clinical article"
                )
        self.assertIsNone(content)
        self.assertEqual(reason, "unpaywall_identity_mismatch")

    def test_pdf_without_main_title_and_doi_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            markdown = "Unidentified article text " * 40
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={
                    "reason": "",
                    "doi": "10.1234/article",
                    "title": "Target clinical article",
                    "urls": ["https://repo.example/article.pdf"],
                },
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value=markdown):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Target clinical article"
                )
        self.assertIsNone(content)
        self.assertEqual(reason, "unpaywall_identity_mismatch")

    def test_success_when_candidate_doi_is_in_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            markdown = "# Unrelated heading\n\nDOI: 10.1234/article\n\n" + (
                "Recovered article text " * 40
            )
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={
                    "reason": "",
                    "doi": "10.1234/article",
                    "title": "Different API title",
                    "urls": ["https://repo.example/article.pdf"],
                },
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value=markdown):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Target clinical article"
                )
        self.assertEqual(content, markdown)
        self.assertIn("Unpaywall", reason)

    def test_success_when_candidate_title_is_in_document(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "fake.pdf"
            pdf_path.write_bytes(b"%PDF-1.7")
            markdown = "Background\n\nTarget clinical article\n\n" + (
                "Recovered article text " * 40
            )
            with patch.object(
                fulltext,
                "fetch_unpaywall",
                return_value={
                    "reason": "",
                    "doi": "10.1234/article",
                    "title": "",
                    "urls": ["https://repo.example/article.pdf"],
                },
            ), patch.object(fulltext, "download_pdf", return_value=str(pdf_path)), \
                    patch.object(fulltext, "parse_pdf_real", return_value=markdown):
                content, reason = fulltext.retrieve_unpaywall_pdf(
                    "10.1234/article", "Target clinical article"
                )
        self.assertEqual(content, markdown)
        self.assertIn("Unpaywall", reason)


class UnpaywallIntegrationTests(unittest.TestCase):
    def run_main(self, rid: str):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            fulltext.main(rid, use_mock=False)

    def test_previous_successes_never_consult_unpaywall(self):
        scenarios = ("markdown", "pmc", "oa", "dropzone")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                oa_url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/" if scenario == "pmc" else ""
                if scenario == "oa":
                    oa_url = "https://repo.example/article.pdf"
                rid, row = make_review(root, oa_url=oa_url)
                safe = fulltext.safe_document_filename(row["doi"], "doi")
                sources = root / "sources"
                if scenario == "markdown":
                    sources.mkdir()
                    (sources / f"{safe}.md").write_text("cached " * 120, encoding="utf-8")
                if scenario == "dropzone":
                    (root / "inputs" / "pdfs" / f"{safe}.pdf").write_bytes(b"%PDF-1.7")

                pmc_record = {
                    "markdown": "# Article\n\n" + "PMC text " * 80,
                    "doi": row["doi"],
                    "title": row["title"],
                }
                with patch.dict(os.environ, {"UNPAYWALL_EMAIL": ""}, clear=False), \
                        patch.object(fulltext, "retrieve_unpaywall_pdf", side_effect=AssertionError("Unpaywall must not be called")), \
                        patch.object(fulltext, "fetch_pmc_xml", return_value={"PMC123456": pmc_record}), \
                        patch.object(fulltext, "download_pdf", return_value=str(root / "download.pdf")), \
                        patch.object(fulltext, "parse_pdf_real", return_value="PDF text " * 80):
                    self.run_main(rid)

    def test_unpaywall_is_last_fallback_and_does_not_change_search_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, row = make_review(root)
            candidates_before = (root / "candidates.csv").read_bytes()
            manifest_before = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            prisma_before = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            content = "# Article\n\n" + "Recovered legally " * 80
            with patch.object(
                fulltext,
                "retrieve_unpaywall_pdf",
                return_value=(content, "PDF parsé avec pymupdf4llm (Unpaywall)"),
            ) as fallback:
                self.run_main(rid)

            fallback.assert_called_once_with(row["doi"], row["title"])
            self.assertEqual((root / "candidates.csv").read_bytes(), candidates_before)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["search_meta"], manifest_before["search_meta"])
            self.assertEqual(prisma["identified"], prisma_before["identified"])
            self.assertEqual(prisma["included"], prisma_before["included"])

    def test_email_never_enters_decisions_or_manifest(self):
        secret_email = "private-contact@example.org"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_review(root)
            with patch.dict(os.environ, {"UNPAYWALL_EMAIL": secret_email}, clear=False), \
                    patch.object(
                        fulltext,
                        "retrieve_unpaywall_pdf",
                        return_value=(None, "unpaywall_email_missing"),
                    ):
                self.run_main(rid)

            for path in (root / "decisions.jsonl", root / "manifest.json"):
                self.assertNotIn(secret_email, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
