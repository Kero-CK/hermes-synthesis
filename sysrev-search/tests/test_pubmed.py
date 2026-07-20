"""Deterministic PubMed connector tests; no test performs a real HTTP call."""

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
SPEC = importlib.util.spec_from_file_location("sysrev_search_pubmed_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


QUERY = {
    "query_mode": "pubmed",
    "term": '("climate adaptation"[Title/Abstract] AND 2020:2024[dp])',
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


def http_error(code: int, endpoint: str = search.PUBMED_ESEARCH_ENDPOINT):
    return urllib.error.HTTPError(
        endpoint,
        code,
        f"HTTP {code}",
        hdrs=None,
        fp=None,
    )


def esearch(count, *, webenv="NCID_TEST", querykey="1"):
    result = {"esearchresult": {"count": count}}
    if webenv is not None:
        result["esearchresult"]["webenv"] = webenv
    if querykey is not None:
        result["esearchresult"]["querykey"] = querykey
    return result


def article_xml(
    pmid: int,
    *,
    title: str | None = None,
    doi: str | None = "10.1234/example",
    pmcid: str | None = None,
    year: int = 2024,
    abstract: str = "Abstract text.",
) -> str:
    title = title if title is not None else f"Article {pmid}"
    doi_xml = f'<ArticleId IdType="doi">{doi}</ArticleId>' if doi else ""
    pmc_xml = f'<ArticleId IdType="pmc">{pmcid}</ArticleId>' if pmcid else ""
    return f"""
      <PubmedArticle>
        <MedlineCitation>
          <PMID Version="1">{pmid}</PMID>
          <Article>
            <ArticleTitle>{title}</ArticleTitle>
            <Abstract><AbstractText>{abstract}</AbstractText></Abstract>
            <Journal><JournalIssue><PubDate><Year>{year}</Year></PubDate></JournalIssue></Journal>
          </Article>
        </MedlineCitation>
        <PubmedData><ArticleIdList>{doi_xml}{pmc_xml}</ArticleIdList></PubmedData>
      </PubmedArticle>
    """


def efetch_xml(*articles: str) -> str:
    return "<PubmedArticleSet>" + "".join(articles) + "</PubmedArticleSet>"


def request_params(request):
    if getattr(request, "data", None) is not None:
        return parse_qs(request.data.decode("utf-8"))
    return parse_qs(urlparse(request.full_url).query)


class PubMedTests(unittest.TestCase):
    def call_pubmed(
        self,
        responses,
        *,
        query=QUERY,
        hard_limit=None,
        api_key="test-key",
        email="tests@example.org",
    ):
        requests = []

        def fake_urlopen(request, timeout=30):
            requests.append((request, timeout))
            value = responses.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value if isinstance(value, FakeResponse) else FakeResponse(value)

        env = {"NCBI_EMAIL": email, "NCBI_API_KEY": api_key}
        if hard_limit is not None:
            env["HARD_LIMIT"] = str(hard_limit)
        with patch.dict(search.os.environ, env, clear=False), \
                patch("urllib.request.urlopen", side_effect=fake_urlopen), \
                patch("time.sleep") as sleep:
            result = search._pubmed_search(query)
            sleeps = [call.args[0] for call in sleep.call_args_list]
        return result, requests, sleeps

    def test_query_contract_preserves_exact_term(self):
        term = ' ("Δ climate"[Title])  AND  adaptation[Abstract] '
        query = {"query_mode": "pubmed", "term": term}
        self.assertEqual(search.validate_pubmed_query(query), query)
        self.assertEqual(
            search.prepare_pubmed_query(query),
            {"query_mode": "pubmed", "params": {"term": term}},
        )
        self.assertEqual(
            search.serialize_pubmed_query_for_csv(query),
            '{"query_mode":"pubmed","term":" (\\"Δ climate\\"[Title])  AND  adaptation[Abstract] "}',
        )

    def test_invalid_query_shapes_are_rejected(self):
        invalid_queries = [
            "climate adaptation",
            {"query_mode": "search", "term": "climate"},
            {"query_mode": "pubmed", "term": ""},
            {"query_mode": "pubmed", "term": "   "},
            {"query_mode": "pubmed", "term": 42},
            {"term": "climate"},
            {"query_mode": "pubmed", "term": "climate", "extra": True},
            [],
            None,
            True,
        ]
        for invalid in invalid_queries:
            with self.subTest(invalid=invalid):
                with self.assertRaises(search.InvalidPubMedQuery):
                    search.validate_pubmed_query(invalid)

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
            invalid = {"query_mode": "pubmed", "term": "climate", "unknown": "x"}

            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(search.InvalidPubMedQuery):
                    search.main(rid, {"pubmed": invalid}, use_mock=False)

            urlopen.assert_not_called()
            self.assertFalse((review_dir / "candidates.csv").exists())
            self.assertEqual(
                (review_dir / "manifest.json").read_text(encoding="utf-8"),
                manifest_before,
            )

    def test_missing_email_fails_before_network(self):
        with patch.dict(search.os.environ, {"NCBI_EMAIL": "", "NCBI_API_KEY": ""}, clear=False), \
                patch("urllib.request.urlopen") as urlopen:
            result = search._pubmed_search(QUERY)
        self.assertEqual(result[:3], ([], None, "error"))
        self.assertIn("NCBI_EMAIL", result[3])
        urlopen.assert_not_called()

    def test_zero_results_are_complete_and_do_not_fetch(self):
        result, requests, sleeps = self.call_pubmed([esearch(0)], api_key="")
        self.assertEqual(result, ([], 0, "complete", "zero_results"))
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])
        request = requests[0][0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(
            request.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(urlparse(request.full_url).query, "")
        params = request_params(request)
        self.assertEqual(params["db"], ["pubmed"])
        self.assertEqual(params["term"], [QUERY["term"]])
        self.assertEqual(params["usehistory"], ["y"])
        self.assertEqual(params["sort"], ["relevance"])
        self.assertEqual(params["retmax"], ["0"])
        self.assertEqual(params["tool"], ["hermes_synthesis"])
        self.assertNotIn("api_key", params)

    def test_esearch_xml_counter_and_history_are_supported(self):
        esearch_xml = """
          <eSearchResult>
            <Count>1</Count><RetMax>0</RetMax>
            <WebEnv>NCID_XML</WebEnv><QueryKey>7</QueryKey>
          </eSearchResult>
        """
        result, requests, _ = self.call_pubmed(
            [esearch_xml, efetch_xml(article_xml(7))]
        )
        self.assertEqual(result[1:], (1, "complete", ""))
        fetch_params = parse_qs(urlparse(requests[1][0].full_url).query)
        self.assertEqual(fetch_params["WebEnv"], ["NCID_XML"])
        self.assertEqual(fetch_params["query_key"], ["7"])

    def test_requests_without_api_key_are_rate_limited_between_calls(self):
        result, requests, sleeps = self.call_pubmed(
            [esearch(1), efetch_xml(article_xml(1))], api_key=""
        )
        self.assertEqual(result[2], "complete")
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertGreaterEqual(sleeps[0], 0.3)
        self.assertLessEqual(sleeps[0], 1 / 3 + 0.05)

    def test_doi_missing_doi_and_pmcid_are_mapped_to_hermes_fields(self):
        payload = esearch(3)
        xml = efetch_xml(
            article_xml(1, doi="10.1234/with-doi"),
            article_xml(2, doi=None),
            article_xml(3, doi=None, pmcid="PMC123456"),
        )
        result, requests, _ = self.call_pubmed([payload, xml])
        self.assertEqual(len(requests), 2)
        self.assertEqual(result[1:], (3, "complete", ""))
        rows = result[0]
        self.assertEqual(rows[0]["doi"], "10.1234/with-doi")
        self.assertEqual(rows[1]["doi"], "")
        self.assertTrue(rows[1]["source_id"].endswith("/2/"))
        self.assertEqual(rows[2]["oa_url"], "https://pmc.ncbi.nlm.nih.gov/articles/PMC123456/")
        for row in rows:
            self.assertEqual(
                row["source_id"],
                f"https://pubmed.ncbi.nlm.nih.gov/{row['source_id'].rstrip('/').rsplit('/', 1)[-1]}/",
            )

    def test_complex_title_and_abstract_xml_is_flattened_in_order(self):
        complex_article = """
          <PubmedArticle>
            <MedlineCitation>
              <PMID>999</PMID>
              <Article>
                <ArticleTitle>Title <i>with</i> <sup>XML</sup> parts</ArticleTitle>
                <Abstract>
                  <AbstractText Label="BACKGROUND">First <b>bold</b> part.</AbstractText>
                  <AbstractText Label="METHODS">Second <i>rich</i> part.</AbstractText>
                </Abstract>
                <Journal><JournalIssue><PubDate><MedlineDate>2022 Jan-Feb</MedlineDate></PubDate></JournalIssue></Journal>
              </Article>
            </MedlineCitation>
            <PubmedData><ArticleIdList><ArticleId IdType="doi">https://doi.org/10.1000/xml</ArticleId></ArticleIdList></PubmedData>
          </PubmedArticle>
        """
        result, _, _ = self.call_pubmed([esearch(1), efetch_xml(complex_article)])
        self.assertEqual(result[0][0]["title"], "Title with XML parts")
        self.assertEqual(result[0][0]["abstract"], "First bold part. Second rich part.")
        self.assertEqual(result[0][0]["year"], "2022")
        self.assertEqual(result[0][0]["doi"], "10.1000/xml")

    def test_multiple_efetch_batches_are_at_most_200(self):
        responses = [
            esearch(401),
            efetch_xml(*(article_xml(i) for i in range(200))),
            efetch_xml(*(article_xml(i) for i in range(200, 400))),
            efetch_xml(article_xml(400)),
        ]
        result, requests, _ = self.call_pubmed(responses)
        self.assertEqual(len(result[0]), 401)
        self.assertEqual(result[1:], (401, "complete", ""))
        fetch_params = [
            parse_qs(urlparse(request.full_url).query)
            for request, _ in requests[1:]
        ]
        self.assertEqual([params["retstart"][0] for params in fetch_params], ["0", "200", "400"])
        self.assertEqual([params["retmax"][0] for params in fetch_params], ["200", "200", "1"])
        self.assertTrue(all(params["retmode"] == ["xml"] for params in fetch_params))
        self.assertTrue(all(params["query_key"] == ["1"] for params in fetch_params))

    def test_hard_limit_is_capped_without_fetching_beyond_limit(self):
        responses = [
            esearch(401),
            efetch_xml(*(article_xml(i) for i in range(200))),
            efetch_xml(*(article_xml(i) for i in range(200, 250))),
        ]
        result, requests, _ = self.call_pubmed(responses, hard_limit=250)
        self.assertEqual(len(result[0]), 250)
        self.assertEqual(result[1:3], (401, "capped"))
        fetch_params = [parse_qs(urlparse(request.full_url).query) for request, _ in requests[1:]]
        self.assertEqual([params["retmax"] for params in fetch_params], [["200"], ["50"]])

    def test_missing_or_invalid_count_is_incomplete_and_does_not_fetch(self):
        invalid_esearch = [
            {"esearchresult": {}},
            {"esearchresult": {"count": None}},
            {"esearchresult": {"count": "many"}},
            {"esearchresult": {"count": -1}},
            {"esearchresult": {"count": True}},
            {"esearchresult": {"count": 1.5}},
        ]
        for payload in invalid_esearch:
            with self.subTest(payload=payload):
                result, requests, _ = self.call_pubmed([payload])
                self.assertEqual(result, ([], None, "incomplete", "missing_or_invalid_expected_count"))
                self.assertEqual(len(requests), 1)

    def test_malformed_esearch_response_is_missing_invalid_count(self):
        result, requests, _ = self.call_pubmed([b"{not-json"])
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            result,
            ([], None, "incomplete", "missing_or_invalid_expected_count"),
        )

    def test_esearch_http_error_is_total_error(self):
        result, requests, sleeps = self.call_pubmed([http_error(400)])
        self.assertEqual(len(requests), 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(result[:3], ([], None, "error"))
        self.assertIn("ESearch", result[3])
        self.assertIn("400", result[3])

    def test_efetch_error_preserves_valid_count(self):
        result, requests, sleeps = self.call_pubmed([esearch(2), http_error(400, search.PUBMED_EFETCH_ENDPOINT)])
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleeps, [])
        self.assertEqual(result[0], [])
        self.assertEqual(result[1], 2)
        self.assertEqual(result[2], "incomplete")
        self.assertIn("EFetch", result[3])

    def test_retryable_http_errors_retry_and_do_not_sleep_after_final_attempt(self):
        success = esearch(0)
        for code in (429, 500, 502, 503, 504):
            with self.subTest(code=code):
                result, requests, sleeps = self.call_pubmed(
                    [http_error(code), http_error(code), http_error(code), success]
                )
                self.assertEqual(result, ([], 0, "complete", "zero_results"))
                self.assertEqual(len(requests), 4)
                self.assertEqual(sleeps, [1, 2, 4])

        result, requests, sleeps = self.call_pubmed([http_error(503)] * 4)
        self.assertEqual(len(requests), 4)
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(result[1], None)
        self.assertEqual(result[2], "error")

    def test_efetch_retry_exhaustion_is_incomplete_and_keeps_count(self):
        result, requests, sleeps = self.call_pubmed(
            [esearch(2)] + [http_error(503, search.PUBMED_EFETCH_ENDPOINT)] * 4
        )
        self.assertEqual(len(requests), 5)
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertEqual(result[0], [])
        self.assertEqual(result[1], 2)
        self.assertEqual(result[2], "incomplete")

    def test_invalid_efetch_xml_is_incomplete_and_keeps_count(self):
        result, requests, sleeps = self.call_pubmed([esearch(1), b"<broken>"])
        self.assertEqual(len(requests), 2)
        self.assertEqual(sleeps, [])
        self.assertEqual(result[0], [])
        self.assertEqual(result[1], 1)
        self.assertEqual(result[2], "incomplete")
        self.assertIn("invalid_efetch_xml", result[3])

    def test_missing_history_after_valid_count_is_incomplete(self):
        result, requests, _ = self.call_pubmed(
            [esearch(1, webenv=None, querykey=None)]
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(result, ([], 1, "incomplete", "missing_history_parameters"))

    def test_long_term_is_exactly_in_esearch_post_body(self):
        term = "(" + ("climate adaptation " * 2500) + ")[Title/Abstract]"
        query = {"query_mode": "pubmed", "term": term}
        result, requests, _ = self.call_pubmed(
            [esearch(0)], query=query, api_key="NCBI-API-SECRET"
        )
        self.assertEqual(result, ([], 0, "complete", "zero_results"))
        request = requests[0][0]
        params = request_params(request)
        self.assertEqual(params["term"], [term])
        self.assertEqual(request.full_url, search.PUBMED_ESEARCH_ENDPOINT)
        self.assertNotIn("tests@example.org", request.full_url)
        self.assertNotIn("NCBI-API-SECRET", request.full_url)

    def test_ncbi_credentials_never_reach_logs_or_status_reason(self):
        secret_email = "private-pubmed@example.org"
        secret_key = "NCBI-API-SECRET"
        with patch.dict(
            search.os.environ,
            {"NCBI_EMAIL": secret_email, "NCBI_API_KEY": secret_key},
            clear=False,
        ), redirect_stderr(io.StringIO()) as stderr:
            result, _, _ = self.call_pubmed(
                [http_error(503)] * 4,
                api_key=secret_key,
                email=secret_email,
            )
        logs = stderr.getvalue()
        self.assertEqual(result[2], "error")
        self.assertNotIn(secret_email, logs)
        self.assertNotIn(secret_key, logs)
        self.assertNotIn(secret_email, result[3])
        self.assertNotIn(secret_key, result[3])

    def test_efetch_retry_uses_same_batch(self):
        xml = efetch_xml(article_xml(1))
        result, requests, sleeps = self.call_pubmed([esearch(1), http_error(503), xml])
        self.assertEqual(result[1:], (1, "complete", ""))
        self.assertEqual(len(requests), 3)
        self.assertEqual(sleeps, [1])
        fetch_params = [parse_qs(urlparse(request.full_url).query) for request, _ in requests[1:]]
        self.assertEqual([params["retstart"][0] for params in fetch_params], ["0", "0"])

    def test_registry_routes_pubmed_and_manifest_merges_sources(self):
        self.assertIn("pubmed", search.CONNECTOR_REGISTRY)
        spec = search.CONNECTOR_REGISTRY["pubmed"]
        self.assertIs(spec["search"], search._pubmed_search)
        self.assertEqual(spec["endpoint"], search.PUBMED_ESEARCH_ENDPOINT)
        self.assertEqual(spec["fetch_endpoint"], search.PUBMED_EFETCH_ENDPOINT)
        self.assertEqual(spec["query_mode"], "pubmed")

        expected = ([{"title": "PubMed fixture"}], 1, "complete", "fixture")
        routed = Mock(return_value=expected)
        with patch.dict(search.CONNECTOR_REGISTRY["pubmed"], {"search": routed}):
            self.assertEqual(search.search_source("pubmed", QUERY), expected)
        routed.assert_called_once_with(QUERY)

        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            (review_dir / "prisma.json").write_text('{"identified":0}', encoding="utf-8")
            (review_dir / "manifest.json").write_text(
                '{"id":"fixture","stage":"protocol_done"}', encoding="utf-8"
            )
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")
            openalex_row = {
                "title": "OpenAlex fixture",
                "doi": "10.1234/openalex",
                "source_id": "https://openalex.org/W1",
                "year": "2024",
                "abstract": "OA abstract",
                "oa_url": "",
            }
            pubmed_row = {
                "title": "PubMed fixture",
                "doi": "",
                "source_id": "https://pubmed.ncbi.nlm.nih.gov/1/",
                "year": "2024",
                "abstract": "PM abstract",
                "oa_url": "",
            }

            def dispatch(source, query):
                return (
                    [openalex_row], 1, "complete", "fixture"
                ) if source == "openalex" else ([pubmed_row], 1, "complete", "fixture")

            with patch.object(search, "mcp_search", side_effect=dispatch):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(
                        rid,
                        {
                            "openalex": {"query_mode": "search", "search": "climate"},
                            "pubmed": QUERY,
                        },
                        use_mock=False,
                    )

            with (review_dir / "candidates.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([row["source"] for row in rows], ["openalex", "pubmed"])
            self.assertEqual(rows[1]["query"], search.serialize_pubmed_query_for_csv(QUERY))
            self.assertEqual(manifest["search_status"], "complete")
            self.assertEqual(manifest["search_meta"]["pubmed"]["query_mode"], "pubmed")
            self.assertEqual(
                manifest["search_meta"]["pubmed"]["endpoint"],
                search.PUBMED_ESEARCH_ENDPOINT,
            )
            self.assertEqual(
                manifest["search_meta"]["pubmed"]["fetch_endpoint"],
                search.PUBMED_EFETCH_ENDPOINT,
            )
            self.assertNotIn("tests@example.org", (review_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("test-key", (review_dir / "candidates.csv").read_text(encoding="utf-8"))

    def test_global_status_is_incomplete_when_pubmed_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "inputs" / "pdfs").mkdir(parents=True)
            reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
            rid = os.path.relpath(review_dir, reviews_root).replace(os.sep, "/")

            def dispatch(source, query):
                if source == "openalex":
                    return ([{"title": "OA", "source_id": "oa"}], 1, "complete", "ok")
                return ([{"title": "PM", "source_id": "pm"}], 3, "incomplete", "EFetch: 503")

            with patch.object(search, "mcp_search", side_effect=dispatch):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    search.main(
                        rid,
                        {
                            "openalex": {"query_mode": "search", "search": "climate"},
                            "pubmed": QUERY,
                        },
                        use_mock=False,
                    )

            manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["search_meta"]["pubmed"]["status"], "incomplete")
            self.assertEqual(manifest["search_status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
