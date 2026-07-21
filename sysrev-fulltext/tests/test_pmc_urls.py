from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_fulltext_pmc_urls", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fulltext)


class PmcUrlTests(unittest.TestCase):
    def test_canonical_pmc_url_returns_pmcid(self):
        url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12826715/"
        self.assertEqual(fulltext.extract_pmcid_from_url(url), "PMC12826715")

    def test_legacy_pmc_pdf_url_returns_same_pmcid(self):
        url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12826715/pdf/"
        self.assertEqual(fulltext.extract_pmcid_from_url(url), "PMC12826715")

    def test_non_pmc_pdf_url_is_not_rewritten_or_fetched_as_pmc(self):
        url = "https://example.org/article.pdf"
        request = None

        class _FakeResponse:
            headers = {"Content-Type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b"%PDF-1.7 fake"

        with patch.object(
            fulltext.urllib.request, "urlopen", return_value=_FakeResponse()
        ) as urlopen:
            pdf_path = fulltext.download_pdf(url)
            request = urlopen.call_args.args[0]

        try:
            self.assertIsNotNone(pdf_path)
            self.assertEqual(request.full_url, url)
        finally:
            if pdf_path:
                Path(pdf_path).unlink(missing_ok=True)

    def test_pmc_pdf_download_is_disabled_without_network_call(self):
        url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12826715/pdf/"
        with patch.object(
            fulltext.urllib.request,
            "urlopen",
            side_effect=AssertionError("PMC PDF must not be fetched"),
        ), patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertIsNone(fulltext.download_pdf(url))

        self.assertIn("EFetch XML", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
