from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_fulltext_pmc_xml", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fulltext)


def article_xml(pmcid: str, title: str, *, with_body: bool = True) -> str:
    body = ""
    if with_body:
        body = (
            "<body><sec><title>Methods</title>"
            "<p>"
            + "This paragraph contains the complete article body and enough detail " * 25
            + "</p></sec></body>"
        )
    return (
        "<article article-type=\"research-article\">"
        "<front><article-meta>"
        f"<article-id pub-id-type=\"pmc\">{pmcid}</article-id>"
        f"<title-group><article-title>{title} <italic>study</italic></article-title></title-group>"
        "<abstract><title>Background</title><p>Structured abstract text.</p></abstract>"
        "</article-meta></front>"
        f"{body}</article>"
    )


def efetch_xml(*articles: str) -> bytes:
    return ("<pmc-articleset>" + "".join(articles) + "</pmc-articleset>").encode()


class _FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


def make_pmc_review(root: Path) -> tuple[str, str]:
    (root / "inputs" / "pdfs").mkdir(parents=True)
    row = {
        "title": "PMC paper",
        "doi": "10.1234/pmc-paper",
        "source_id": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "year": "2024",
        "abstract": "",
        "oa_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC111111/",
        "pdf_status": "",
        "source": "pubmed",
        "query": "q",
        "date": "",
    }
    fields = list(row)
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    decision = {
        "doc": row["doi"],
        "stage": "screen_title_abstract",
        "decision": "include",
        "identity_type": "doi",
        "source_id": row["source_id"],
        "oa_url": row["oa_url"],
    }
    (root / "decisions.jsonl").write_text(
        json.dumps(decision) + "\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text(
        json.dumps({"id": "pmc", "stage": "review_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
    return rid, row["doi"]


class PmcXmlTests(unittest.TestCase):
    def test_grouped_post_associates_each_pmcid_and_preserves_jats_content(self):
        requests = []
        payload = efetch_xml(
            article_xml("PMC111111", "First <bold>article</bold>"),
            article_xml("PMC222222", "Second article"),
        )

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            return _FakeResponse(payload)

        with patch.dict(
            os.environ,
            {"NCBI_EMAIL": "test-email@example.invalid", "NCBI_API_KEY": "test-key"},
            clear=False,
        ), patch.object(fulltext.urllib.request, "urlopen", side_effect=fake_urlopen):
            results = fulltext.fetch_pmc_xml(["PMC111111", "PMC222222"])

        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertEqual(timeout, 60)
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.headers["Content-type"], "application/x-www-form-urlencoded"
        )
        params = fulltext.urllib.parse.parse_qs(request.data.decode("utf-8"))
        self.assertEqual(params["db"], ["pmc"])
        self.assertEqual(params["id"], ["PMC111111,PMC222222"])
        self.assertEqual(params["retmode"], ["xml"])
        self.assertEqual(params["tool"], ["hermes_synthesis"])
        self.assertNotIn("test-email", request.full_url)
        self.assertIn("# First article study", results["PMC111111"]["markdown"])
        self.assertIn("## Abstract", results["PMC111111"]["markdown"])
        self.assertIn("## Methods", results["PMC111111"]["markdown"])
        self.assertIn("complete article body", results["PMC111111"]["markdown"])
        self.assertEqual(results["PMC111111"]["title"], "First article study")
        self.assertNotEqual(results["PMC111111"], results["PMC222222"])

    def test_article_without_body_is_mapped_as_unusable(self):
        payload = efetch_xml(article_xml("PMC333333", "No body", with_body=False))
        with patch.dict(os.environ, {"NCBI_EMAIL": "test@example.invalid"}, clear=False), \
                patch.object(fulltext.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
            results = fulltext.fetch_pmc_xml(["PMC333333"])

        self.assertIn("PMC333333", results)
        self.assertIsNone(results["PMC333333"]["markdown"])

    def test_invalid_xml_and_http_error_are_sanitized(self):
        secret_email = "test-email@example.invalid"
        secret_key = "test-key-not-real"
        with patch.dict(
            os.environ,
            {"NCBI_EMAIL": secret_email, "NCBI_API_KEY": secret_key},
            clear=False,
        ), patch.object(
            fulltext.urllib.request,
            "urlopen",
            return_value=_FakeResponse(b"<not-xml"),
        ):
            with self.assertRaisesRegex(fulltext.PmcFetchError, "XML invalide") as caught:
                fulltext.fetch_pmc_xml(["PMC1"])
        self.assertNotIn(secret_email, str(caught.exception))
        self.assertNotIn(secret_key, str(caught.exception))

        http_error = urllib.error.HTTPError(
            fulltext.PMC_EFETCH_ENDPOINT, 503, "unavailable", {}, io.BytesIO()
        )
        with patch.dict(
            os.environ,
            {"NCBI_EMAIL": secret_email, "NCBI_API_KEY": secret_key},
            clear=False,
        ), patch.object(
            fulltext.urllib.request, "urlopen", side_effect=http_error
        ):
            with self.assertRaisesRegex(fulltext.PmcFetchError, "HTTP 503") as caught:
                fulltext.fetch_pmc_xml(["PMC1"])
        self.assertNotIn(secret_email, str(caught.exception))
        self.assertNotIn(secret_key, str(caught.exception))

    def test_global_efetch_failure_happens_before_review_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, _ = make_pmc_review(root)
            decisions_before = (root / "decisions.jsonl").read_bytes()
            prisma_before = (root / "prisma.json").read_bytes()
            manifest_before = (root / "manifest.json").read_bytes()

            with patch.object(
                fulltext,
                "fetch_pmc_xml",
                side_effect=fulltext.PmcFetchError("EFetch PMC HTTP 503"),
            ), patch("sys.stderr", new_callable=io.StringIO) as stderr:
                with self.assertRaises(SystemExit):
                    fulltext.main(rid, use_mock=False)

            self.assertEqual((root / "decisions.jsonl").read_bytes(), decisions_before)
            self.assertEqual((root / "prisma.json").read_bytes(), prisma_before)
            self.assertEqual((root / "manifest.json").read_bytes(), manifest_before)
            self.assertFalse((root / "sources").exists())
            self.assertNotIn("test-email", stderr.getvalue())
            self.assertNotIn("test-key", stderr.getvalue())

    def test_dropzone_is_tried_after_non_pmc_oa_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(root, reviews_root).replace(os.sep, "/")
            row = {
                "title": "Non PMC",
                "doi": "10.1234/dropzone",
                "source_id": "https://openalex.org/W1",
                "year": "2024",
                "abstract": "",
                "oa_url": "https://example.org/fails.pdf",
                "pdf_status": "",
                "source": "openalex",
                "query": "q",
                "date": "",
            }
            (root / "inputs" / "pdfs").mkdir(parents=True)
            with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            (root / "decisions.jsonl").write_text(
                json.dumps({"doc": row["doi"], "stage": "screen_title_abstract", "decision": "include"}) + "\n",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(json.dumps({"stage": "review_done"}), encoding="utf-8")
            (root / "prisma.json").write_text(json.dumps({"included": 1}), encoding="utf-8")
            dropzone = root / "inputs" / "pdfs" / "10.1234_dropzone.pdf"
            dropzone.write_bytes(b"pdf")

            with patch.object(fulltext, "download_pdf", return_value=None), \
                    patch.object(fulltext, "parse_pdf_real", return_value="x" * 600):
                fulltext.main(rid, use_mock=False)

            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_retrieved"], 1)
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(entries[-1]["decision"], "retrieved")
            self.assertIn("dropzone", entries[-1]["reason"])

    def test_pmc_doi_contradiction_refuses_write_and_is_journaled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, doi = make_pmc_review(root)
            record = {
                "markdown": "x" * 600,
                "doi": "10.1234/other-paper",
                "title": "PMC paper",
            }
            with patch.object(fulltext, "fetch_pmc_xml", return_value={"PMC111111": record}):
                fulltext.main(rid, use_mock=False)

            safe = fulltext.safe_document_filename(doi, "doi")
            self.assertFalse((root / "sources" / f"{safe}.md").exists())
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(entries[-1]["decision"], "retrieval_failed")
            self.assertIn("DOI XML", entries[-1]["reason"])

    def test_pmc_missing_xml_doi_uses_normalized_title_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, doi = make_pmc_review(root)
            record = {
                "markdown": "# PMC paper\n\n" + "x" * 600,
                "doi": "",
                "title": "PMC: paper",
            }
            with patch.object(fulltext, "fetch_pmc_xml", return_value={"PMC111111": record}):
                fulltext.main(rid, use_mock=False)

            safe = fulltext.safe_document_filename(doi, "doi")
            self.assertTrue((root / "sources" / f"{safe}.md").exists())

    def test_pmc_title_contradiction_is_refused_when_xml_doi_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid, doi = make_pmc_review(root)
            record = {
                "markdown": "# Other paper\n\n" + "x" * 600,
                "doi": "",
                "title": "Other paper",
            }
            with patch.object(fulltext, "fetch_pmc_xml", return_value={"PMC111111": record}):
                fulltext.main(rid, use_mock=False)

            safe = fulltext.safe_document_filename(doi, "doi")
            self.assertFalse((root / "sources" / f"{safe}.md").exists())
            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertIn("titre XML différent", entries[-1]["reason"])


if __name__ == "__main__":
    unittest.main()
