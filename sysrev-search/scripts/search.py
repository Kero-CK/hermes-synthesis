#!/usr/bin/env python3
"""
search.py — Récupère des articles candidats multi-sources pour Hermes Synthesis.

Interroge les bases académiques (OpenAlex, puis connecteurs API directs),
fusionne les résultats, réconcilie avec la dropzone par DOI, et écrit
candidates.csv avec provenance complète.

Usage:
  python3 search.py '<json>'            # mode réel (OpenAlex + PubMed + ERIC câblés)
  python3 search.py '<json>' --mock     # mode test avec données fictives

JSON attendu:
  {"id": "ma-revue", "queries": {
      "openalex": {
          "query_mode": "search",
          "search": "climate adaptation",
          "filter": "from_publication_date:2020-01-01"
      },
      "pubmed": {
          "query_mode": "pubmed",
          "term": "(climate adaptation[Title/Abstract])"
      },
      "eric": {
          "query_mode": "eric",
          "search": "higher education AND generative AI",
          "sort": "publicationdateyear desc"
      }
  }}

  Le format OpenAlex est un objet avec `query_mode: "search"`, `search`
  et un `filter` facultatif ; il produit des paramètres `search=` et
  `filter=` séparés. Les anciennes chaînes OpenAlex sont refusées.
  Voir https://developers.openalex.org/guides/searching pour la syntaxe de
  recherche et https://developers.openalex.org/api-reference/works pour la
  référence des champs et filtres (séparés par des virgules = ET logique).

Sources câblées :
  - openalex : catalogue multidisciplinaire OpenAlex. Nécessite une clé API
    depuis février 2026 — lue depuis OPENALEX_API_KEY dans l'environnement.
    Authentification, quotas et coûts :
    https://developers.openalex.org/api-reference/authentication
  - pubmed : ESearch + EFetch XML via les E-utilities NCBI, avec NCBI_EMAIL
    obligatoire et NCBI_API_KEY facultative
  - eric : API JSON officielle de l'Institute of Education Sciences, sans clé
    obligatoire, avec pagination ``start``/``rows``

Le script ne prend AUCUNE décision de recherche : les requêtes sont déjà
validées par l'humain en amont. Il fait l'exécution mécanique.
"""

import csv
import glob
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Callable, Literal, NotRequired, TypeAlias, TypedDict


SearchStatus: TypeAlias = Literal["complete", "incomplete", "capped", "error"]
SearchResult: TypeAlias = tuple[list[dict], int | None, SearchStatus, str]
SourceQueryInput: TypeAlias = str | dict[str, object]


class OpenAlexSearchQuery(TypedDict):
    query_mode: Literal["search"]
    search: str
    filter: NotRequired[str]


OpenAlexQueryInput: TypeAlias = OpenAlexSearchQuery
SearchFunction: TypeAlias = Callable[[SourceQueryInput], SearchResult]


class PreparedOpenAlexQuery(TypedDict):
    query_mode: Literal["search"]
    params: dict[str, str]


class PubMedSearchQuery(TypedDict):
    query_mode: Literal["pubmed"]
    term: str


PubMedQueryInput: TypeAlias = PubMedSearchQuery


class PreparedPubMedQuery(TypedDict):
    query_mode: Literal["pubmed"]
    params: dict[str, str]


class EricSearchQuery(TypedDict):
    query_mode: Literal["eric"]
    search: str
    sort: NotRequired[str]


EricQueryInput: TypeAlias = EricSearchQuery


class PreparedEricQuery(TypedDict):
    query_mode: Literal["eric"]
    params: dict[str, str]


VALID_SEARCH_STATUSES = frozenset({"complete", "incomplete", "capped", "error"})


class ConnectorSpec(TypedDict):
    search: SearchFunction
    endpoint: str
    api_version: str
    query_mode: str
    fetch_endpoint: NotRequired[str]


class InvalidSearchContract(ValueError):
    """Raised when a connector does not return the common four-field tuple."""


class InvalidOpenAlexQuery(ValueError):
    """Raised when an OpenAlex query is not in a supported input format."""


class InvalidPubMedQuery(ValueError):
    """Raised when a PubMed query is not in the supported input format."""


class InvalidEricQuery(ValueError):
    """Raised when an ERIC query is not in the supported input format."""


_OPENALEX_QUERY_KEYS = frozenset({"query_mode", "search", "filter"})
_PUBMED_QUERY_KEYS = frozenset({"query_mode", "term"})
_ERIC_QUERY_KEYS = frozenset({"query_mode", "search", "sort"})

PUBMED_ESEARCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_TOOL = "hermes_synthesis"
PUBMED_BATCH_SIZE = 200
NCBI_MAX_RETRIES = 4
NCBI_RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})

ERIC_ENDPOINT = "https://api.ies.ed.gov/eric/"
ERIC_MIN_PAGE_SIZE = 20
ERIC_PAGE_SIZE = 200
ERIC_MAX_RETRIES = 4
ERIC_RETRYABLE_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
ERIC_FIELDS = (
    "id,title,author,source,publicationdateyear,description,subject,"
    "peerreviewed,audience,educationlevel,language,publicationtype,publisher,"
    "url,e_fulltextauth,ieslinkpublication"
)


def validate_openalex_query(query: object) -> OpenAlexQueryInput:
    """Validate the structured OpenAlex ``search=`` query object."""
    if isinstance(query, str):
        raise InvalidOpenAlexQuery(
            "Requête OpenAlex invalide : une chaîne historique est refusée ; "
            "un objet avec query_mode='search' et search= est requis. Voir "
            "https://developers.openalex.org/guides/searching"
        )

    prefix = "Requête OpenAlex invalide"
    if not isinstance(query, dict):
        raise InvalidOpenAlexQuery(
            f"{prefix} : un objet JSON avec query_mode='search' et search est requis"
        )

    unexpected = set(query) - _OPENALEX_QUERY_KEYS
    if unexpected:
        raise InvalidOpenAlexQuery(
            f"{prefix} : champs supplémentaires interdits : {sorted(unexpected, key=str)}"
        )

    if "query_mode" not in query:
        raise InvalidOpenAlexQuery(f"{prefix} : query_mode est obligatoire")
    if query.get("query_mode") != "search":
        raise InvalidOpenAlexQuery(
            f"{prefix} : query_mode doit être exactement 'search'"
        )

    if "search" not in query:
        raise InvalidOpenAlexQuery(f"{prefix} : search est obligatoire")
    search_value = query.get("search")
    if not isinstance(search_value, str):
        raise InvalidOpenAlexQuery(f"{prefix} : search doit être une chaîne")
    if not search_value.strip():
        raise InvalidOpenAlexQuery(f"{prefix} : search ne peut pas être vide")

    if "filter" in query:
        filter_value = query.get("filter")
        if not isinstance(filter_value, str):
            raise InvalidOpenAlexQuery(f"{prefix} : filter doit être une chaîne")
        if not filter_value.strip():
            raise InvalidOpenAlexQuery(f"{prefix} : filter ne peut pas être vide")

    return query


def prepare_openalex_query(query: object) -> PreparedOpenAlexQuery:
    """Return exact OpenAlex ``search=`` and optional ``filter=`` parameters."""
    validated = validate_openalex_query(query)
    params = {"search": validated["search"]}
    if "filter" in validated:
        params["filter"] = validated["filter"]
    return {"query_mode": "search", "params": params}


def validate_pubmed_query(query: object) -> PubMedQueryInput:
    """Validate the only supported PubMed input contract."""
    prefix = "Requête PubMed invalide"
    if isinstance(query, str):
        raise InvalidPubMedQuery(
            f"{prefix} : une chaîne simple est refusée ; un objet avec "
            "query_mode='pubmed' et term= est requis"
        )
    if not isinstance(query, dict):
        raise InvalidPubMedQuery(
            f"{prefix} : un objet JSON avec query_mode='pubmed' et term est requis"
        )

    unexpected = set(query) - _PUBMED_QUERY_KEYS
    if unexpected:
        raise InvalidPubMedQuery(
            f"{prefix} : champs supplémentaires interdits : {sorted(unexpected, key=str)}"
        )

    if "query_mode" not in query:
        raise InvalidPubMedQuery(f"{prefix} : query_mode est obligatoire")
    if query.get("query_mode") != "pubmed":
        raise InvalidPubMedQuery(
            f"{prefix} : query_mode doit être exactement 'pubmed'"
        )

    if "term" not in query:
        raise InvalidPubMedQuery(f"{prefix} : term est obligatoire")
    term_value = query.get("term")
    if not isinstance(term_value, str):
        raise InvalidPubMedQuery(f"{prefix} : term doit être une chaîne")
    if not term_value.strip():
        raise InvalidPubMedQuery(f"{prefix} : term ne peut pas être vide")

    return query


def prepare_pubmed_query(query: object) -> PreparedPubMedQuery:
    """Return the exact PubMed term without rewriting its syntax."""
    validated = validate_pubmed_query(query)
    return {"query_mode": "pubmed", "params": {"term": validated["term"]}}


def validate_eric_query(query: object) -> EricQueryInput:
    """Validate the structured ERIC query without changing its text."""
    prefix = "Requête ERIC invalide"
    if isinstance(query, str):
        raise InvalidEricQuery(
            f"{prefix} : une chaîne simple est refusée ; un objet avec "
            "query_mode='eric' et search= est requis"
        )
    if not isinstance(query, dict):
        raise InvalidEricQuery(
            f"{prefix} : un objet JSON avec query_mode='eric' et search est requis"
        )

    unexpected = set(query) - _ERIC_QUERY_KEYS
    if unexpected:
        raise InvalidEricQuery(
            f"{prefix} : champs supplémentaires interdits : "
            f"{sorted(unexpected, key=str)}"
        )
    if query.get("query_mode") != "eric":
        raise InvalidEricQuery(
            f"{prefix} : query_mode doit être exactement 'eric'"
        )

    search_value = query.get("search")
    if not isinstance(search_value, str):
        raise InvalidEricQuery(f"{prefix} : search doit être une chaîne")
    if not search_value.strip():
        raise InvalidEricQuery(f"{prefix} : search ne peut pas être vide")

    if "sort" in query:
        sort_value = query.get("sort")
        if not isinstance(sort_value, str):
            raise InvalidEricQuery(f"{prefix} : sort doit être une chaîne")
        if not sort_value.strip():
            raise InvalidEricQuery(f"{prefix} : sort ne peut pas être vide")

    return query


def prepare_eric_query(query: object) -> PreparedEricQuery:
    """Return exact ERIC search and optional sort parameters."""
    validated = validate_eric_query(query)
    params = {"search": validated["search"]}
    if "sort" in validated:
        params["sort"] = validated["sort"]
    return {"query_mode": "eric", "params": params}


def serialize_query_for_csv(query: OpenAlexQueryInput) -> str:
    """Serialize a validated structured query for candidates.csv provenance."""
    validated = validate_openalex_query(query)
    return json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_pubmed_query_for_csv(query: PubMedQueryInput) -> str:
    """Serialize a validated PubMed query while preserving its exact term."""
    validated = validate_pubmed_query(query)
    return json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_eric_query_for_csv(query: EricQueryInput) -> str:
    """Serialize an ERIC query while preserving exact search and sort text."""
    validated = validate_eric_query(query)
    return json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_source_query_for_csv(source: str, query: SourceQueryInput) -> str:
    """Serialize provenance without coupling non-OpenAlex sources to OpenAlex."""
    if source == "openalex":
        return serialize_query_for_csv(query)
    if source == "pubmed":
        return serialize_pubmed_query_for_csv(query)
    if source == "eric":
        return serialize_eric_query_for_csv(query)
    if isinstance(query, str):
        return query
    if isinstance(query, dict):
        return json.dumps(
            query,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    raise TypeError("La requête source doit être une chaîne ou un objet JSON")


def _validate_search_result(source: str, result: object) -> SearchResult:
    """Validate and return the common connector result contract."""
    prefix = f"Source '{source}' : contrat de recherche invalide"
    if not isinstance(result, tuple):
        raise InvalidSearchContract(f"{prefix} : résultat attendu sous forme de tuple")
    if len(result) != 4:
        raise InvalidSearchContract(f"{prefix} : tuple à 4 éléments requis")

    results, expected_count, status, reason = result
    if not isinstance(results, list):
        raise InvalidSearchContract(f"{prefix} : results doit être une liste")
    if expected_count is not None and (
        isinstance(expected_count, bool)
        or not isinstance(expected_count, int)
        or expected_count < 0
    ):
        raise InvalidSearchContract(
            f"{prefix} : expected_count doit être None ou un entier supérieur ou égal à zéro"
        )
    if not isinstance(status, str) or status not in VALID_SEARCH_STATUSES:
        raise InvalidSearchContract(
            f"{prefix} : status doit appartenir à {sorted(VALID_SEARCH_STATUSES)}"
        )
    if not isinstance(reason, str):
        raise InvalidSearchContract(f"{prefix} : reason doit être une chaîne")

    return results, expected_count, status, reason


# ---------------------------------------------------------------------------
# Recherche réelle — OpenAlex (clé API requise depuis février 2026)
# ---------------------------------------------------------------------------


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """
    Reconstruit un abstract lisible depuis l'index inversé d'OpenAlex.

    OpenAlex stocke les abstracts sous forme {mot: [positions]}.
    Ex: {"Artificial": [0], "Intelligence": [1], "is": [2], "great": [3]}
    → "Artificial Intelligence is great"
    """
    if not inverted_index:
        return ""

    # Crée un dict position → mot
    positioned: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            positioned[pos] = word

    # Reconstruit dans l'ordre
    return " ".join(positioned[i] for i in sorted(positioned))


def _clean_doi(doi_url: str) -> str:
    """Nettoie un DOI OpenAlex (URL → identifiant court)."""
    if not doi_url:
        return ""
    return doi_url.replace("https://doi.org/", "")


def _resolve_hard_limit(max_results: int | None = None) -> int:
    """Read the shared safety cap without allowing a malformed env to crash search."""
    try:
        hard_limit = int(os.environ.get("HARD_LIMIT", "2000"))
    except (TypeError, ValueError):
        hard_limit = 2000
    hard_limit = max(0, hard_limit)
    if max_results is not None:
        hard_limit = min(hard_limit, max(0, max_results))
    return hard_limit


def _parse_nonnegative_count(value: object) -> int | None:
    """Parse the string or integer count returned by NCBI, rejecting ambiguity."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
    return None


def _xml_local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _xml_elements(root: object, name: str) -> list:
    """Return XML descendants by local name, including namespace-qualified tags."""
    if not hasattr(root, "iter"):
        return []
    return [node for node in root.iter() if _xml_local_name(node.tag) == name]


def _xml_first_element(root: object, name: str):
    elements = _xml_elements(root, name)
    return elements[0] if elements else None


def _xml_direct_elements(root: object, name: str) -> list:
    """Return only direct XML children by local name."""
    if root is None:
        return []
    try:
        children = list(root)
    except TypeError:
        return []
    return [node for node in children if _xml_local_name(node.tag) == name]


def _xml_first_direct_element(root: object, name: str):
    elements = _xml_direct_elements(root, name)
    return elements[0] if elements else None


def _xml_text(node: object) -> str:
    """Flatten nested XML markup into normalized human-readable text."""
    import re

    if node is None or not hasattr(node, "itertext"):
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def _pubmed_year(article: object) -> str:
    """Extract the best available publication year from a PubMed article."""
    import re

    for article_date in _xml_elements(article, "ArticleDate"):
        year = _xml_text(_xml_first_element(article_date, "Year"))
        if year:
            return year

    for pub_date in _xml_elements(article, "PubDate"):
        year = _xml_text(_xml_first_element(pub_date, "Year"))
        if year:
            return year
        medline_date = _xml_text(_xml_first_element(pub_date, "MedlineDate"))
        match = re.search(r"\b(?:18|19|20|21)\d{2}\b", medline_date)
        if match:
            return match.group(0)

    for pubmed_date in _xml_elements(article, "PubMedPubDate"):
        if (pubmed_date.attrib.get("PubStatus", "").lower()
                in {"epublish", "ppublish"}):
            year = _xml_text(_xml_first_element(pubmed_date, "Year"))
            if year:
                return year

    year = _xml_text(_xml_first_element(article, "Year"))
    if year:
        return year
    return ""


def _pubmed_article_to_result(article: object) -> dict | None:
    """Map one PubMed XML notice to Hermes' common article shape."""
    pmid = _xml_text(_xml_first_element(article, "PMID"))
    if not pmid:
        return None

    title = _xml_text(_xml_first_element(article, "ArticleTitle"))
    abstract_parts = [_xml_text(node) for node in _xml_elements(article, "AbstractText")]
    abstract_parts = [part for part in abstract_parts if part]
    if abstract_parts:
        abstract = " ".join(abstract_parts)
    else:
        abstract = _xml_text(_xml_first_element(article, "Abstract"))

    doi = ""
    pmcid = ""
    pubmed_data = _xml_first_direct_element(article, "PubmedData")
    article_id_list = _xml_first_direct_element(pubmed_data, "ArticleIdList")
    article_id_nodes = _xml_direct_elements(article_id_list, "ArticleId")
    for article_id in article_id_nodes:
        value = _xml_text(article_id)
        id_type = article_id.attrib.get("IdType", "").lower()
        if not value:
            continue
        if id_type == "doi" and not doi:
            doi = value
        elif id_type in {"pmc", "pmcid"} and not pmcid:
            pmcid = value
    if not doi:
        medline_citation = _xml_first_direct_element(article, "MedlineCitation")
        main_article = _xml_first_direct_element(medline_citation, "Article")
        for elocation in _xml_elements(main_article, "ELocationID"):
            if elocation.attrib.get("EIdType", "").lower() == "doi":
                doi = _xml_text(elocation)
                if doi:
                    break

    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    if pmcid and not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"

    return {
        "title": title,
        "doi": doi,
        "source_id": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "year": _pubmed_year(article),
        "abstract": abstract,
        "oa_url": (
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""
        ),
    }


def _parse_pubmed_efetch_xml(payload: bytes | str) -> list[dict]:
    """Parse PubMed EFetch XML, including namespaced and mixed-content notices."""
    import xml.etree.ElementTree as ET

    if isinstance(payload, bytes):
        root = ET.fromstring(payload)
    else:
        root = ET.fromstring(payload.encode("utf-8"))
    results = []
    for article in _xml_elements(root, "PubmedArticle"):
        result = _pubmed_article_to_result(article)
        if result is not None:
            results.append(result)
    return results


def _parse_pubmed_esearch_response(payload: bytes | str) -> tuple[int | None, str, str]:
    """Parse ESearch JSON or XML into ``(count, WebEnv, query_key)``."""
    import json as json_module
    import xml.etree.ElementTree as ET

    if isinstance(payload, bytes):
        text = payload.decode("utf-8-sig")
    else:
        text = payload
    if text.lstrip().startswith("<"):
        root = ET.fromstring(text.encode("utf-8"))
        count_value = _xml_text(_xml_first_element(root, "Count"))
        webenv = _xml_text(_xml_first_element(root, "WebEnv"))
        query_key = _xml_text(_xml_first_element(root, "QueryKey"))
    else:
        parsed = json_module.loads(text)
        esearch_result = parsed.get("esearchresult")
        if not isinstance(esearch_result, dict):
            raise ValueError("invalid ESearch response")
        count_value = esearch_result.get("count")
        if count_value is None:
            count_value = esearch_result.get("Count")
        webenv = esearch_result.get("webenv", esearch_result.get("WebEnv", ""))
        query_key = esearch_result.get(
            "querykey", esearch_result.get("QueryKey", esearch_result.get("query_key", ""))
        )
        if not isinstance(webenv, str):
            webenv = ""
        if not isinstance(query_key, str):
            query_key = str(query_key) if query_key is not None else ""

    return _parse_nonnegative_count(count_value), webenv, query_key


def _sanitize_ncbi_message(message: object, email: str, api_key: str) -> str:
    """Keep credentials out of error strings that can reach logs or manifests."""
    import urllib.parse

    safe_message = str(message)
    for secret in (email, api_key):
        if not secret:
            continue
        for candidate in (secret, urllib.parse.quote(secret, safe="")):
            safe_message = safe_message.replace(candidate, "[redacted]")
    return safe_message


def _ncbi_rate_limit(api_key: str, rate_state: dict[str, float | None]) -> None:
    """Keep unauthenticated E-utility traffic at or below three requests/second."""
    if api_key:
        return
    import time

    last_request_at = rate_state.get("last_request_at")
    if last_request_at is not None:
        remaining = (1 / 3) - (time.monotonic() - last_request_at)
        if remaining > 0:
            time.sleep(remaining)
    rate_state["last_request_at"] = time.monotonic()


def _ncbi_request(
    endpoint: str,
    params: dict[str, str],
    *,
    email: str,
    api_key: str,
    rate_state: dict[str, float | None],
    method: str = "GET",
) -> tuple[bytes | None, str, str]:
    """Call one E-utility endpoint with the Hermes retry contract."""
    import time
    import urllib.error
    import urllib.parse
    import urllib.request

    if method.upper() == "POST":
        request = urllib.request.Request(
            endpoint,
            data=urllib.parse.urlencode(params).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        request_url = f"{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(request_url, method="GET")
    request.add_header("User-Agent", "HermesSynthesis/0.1")
    last_error_code = None

    for attempt in range(NCBI_MAX_RETRIES):
        # Retries already wait at least one second; rate-limit the first attempt
        # of each E-utility call without adding a second delay to retries.
        if attempt == 0:
            _ncbi_rate_limit(api_key, rate_state)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read(), "ok", ""
        except urllib.error.HTTPError as exc:
            last_error_code = exc.code
            if exc.code not in NCBI_RETRYABLE_HTTP_CODES:
                return None, "error", f"HTTP {exc.code}"
            if attempt < NCBI_MAX_RETRIES - 1:
                delay = 2 ** attempt
                print(
                    f"  ⚠️  PubMed HTTP {exc.code} — tentative "
                    f"{attempt + 1}/{NCBI_MAX_RETRIES}, retry dans {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
            else:
                print(
                    f"  ⚠️  PubMed HTTP {exc.code} — tentative "
                    f"{attempt + 1}/{NCBI_MAX_RETRIES} (dernier essai).",
                    file=sys.stderr,
                )
        except Exception as exc:
            safe_message = _sanitize_ncbi_message(exc, email, api_key)
            return None, "error", f"exception: {safe_message}"

    code = str(last_error_code) if last_error_code is not None else "429/5xx"
    return (
        None,
        "incomplete",
        f"requête abandonnée après {NCBI_MAX_RETRIES} tentatives (HTTP {code})",
    )


def _pubmed_search(query: SourceQueryInput, max_results: int | None = None) -> SearchResult:
    """Search PubMed through ESearch history and fetch XML notices in batches."""
    try:
        prepared_query = prepare_pubmed_query(query)
    except InvalidPubMedQuery as exc:
        print(f"  ❌ {exc}", file=sys.stderr)
        return [], None, "error", str(exc)

    email = os.environ.get("NCBI_EMAIL", "").strip()
    if not email:
        reason = "NCBI_EMAIL est obligatoire pour une requête PubMed réelle"
        print(f"  ❌ {reason}", file=sys.stderr)
        return [], None, "error", reason
    api_key = os.environ.get("NCBI_API_KEY", "").strip()
    hard_limit = _resolve_hard_limit(max_results)
    rate_state: dict[str, float | None] = {"last_request_at": None}

    esearch_params = {
        "db": "pubmed",
        "term": prepared_query["params"]["term"],
        "retmax": "0",
        "usehistory": "y",
        "sort": "relevance",
        "retmode": "json",
        "tool": NCBI_TOOL,
        "email": email,
    }
    if api_key:
        esearch_params["api_key"] = api_key

    esearch_payload, http_status, http_reason = _ncbi_request(
        PUBMED_ESEARCH_ENDPOINT,
        esearch_params,
        email=email,
        api_key=api_key,
        rate_state=rate_state,
        method="POST",
    )
    if esearch_payload is None:
        return [], None, "error", f"ESearch: {http_reason}"

    try:
        expected_count, webenv, query_key = _parse_pubmed_esearch_response(esearch_payload)
    except Exception as exc:
        reason = _sanitize_ncbi_message(exc, email, api_key)
        print(f"  ❌ PubMed ESearch response invalide : {reason}", file=sys.stderr)
        return [], None, "incomplete", "missing_or_invalid_expected_count"

    if expected_count is None:
        return [], None, "incomplete", "missing_or_invalid_expected_count"
    if expected_count == 0:
        return [], 0, "complete", "zero_results"
    if not webenv or not query_key:
        return [], expected_count, "incomplete", "missing_history_parameters"
    if hard_limit == 0:
        return [], expected_count, "capped", "plafond 0 atteint"

    target_count = min(expected_count, hard_limit)
    all_results: list[dict] = []
    batch_number = 0
    for retstart in range(0, target_count, PUBMED_BATCH_SIZE):
        batch_number += 1
        retmax = min(PUBMED_BATCH_SIZE, target_count - retstart)
        efetch_params = {
            "db": "pubmed",
            "query_key": query_key,
            "WebEnv": webenv,
            "retstart": str(retstart),
            "retmax": str(retmax),
            "retmode": "xml",
            "tool": NCBI_TOOL,
            "email": email,
        }
        if api_key:
            efetch_params["api_key"] = api_key

        efetch_payload, http_status, http_reason = _ncbi_request(
            PUBMED_EFETCH_ENDPOINT,
            efetch_params,
            email=email,
            api_key=api_key,
            rate_state=rate_state,
        )
        if efetch_payload is None:
            return all_results, expected_count, "incomplete", f"EFetch: {http_reason}"

        try:
            batch_results = _parse_pubmed_efetch_xml(efetch_payload)
        except Exception as exc:
            reason = _sanitize_ncbi_message(exc, email, api_key)
            print(
                f"  ❌ PubMed EFetch XML invalide sur le lot {batch_number} : {reason}",
                file=sys.stderr,
            )
            return all_results, expected_count, "incomplete", (
                f"invalid_efetch_xml_batch_{batch_number}"
            )

        if not batch_results:
            return all_results, expected_count, "incomplete", (
                f"lot {batch_number} sans notice PubMed valide"
            )
        all_results.extend(batch_results)

    retrieved = len(all_results)
    if retrieved < target_count:
        return all_results[:hard_limit], expected_count, "incomplete", (
            f"récupéré {retrieved}/{expected_count}"
        )
    if expected_count > hard_limit:
        return all_results[:hard_limit], expected_count, "capped", (
            f"arrêt volontaire à {hard_limit} (requête trop large)"
        )
    return all_results[:hard_limit], expected_count, "complete", ""


def _eric_clean_text(value: object) -> str:
    """Flatten an ERIC scalar/list field without changing its meaning."""
    import html
    import re

    if isinstance(value, list):
        parts = [_eric_clean_text(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("name", "value", "text", "label"):
            if key in value:
                return _eric_clean_text(value[key])
        return ""
    if value is None or isinstance(value, bool):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _eric_field(doc: dict, *names: str) -> object:
    for name in names:
        if name in doc and doc[name] not in (None, "", []):
            return doc[name]
    return ""


def _eric_doi(doc: dict) -> str:
    """Extract and normalize an ERIC DOI from DOI or URL metadata."""
    import re

    direct = _eric_field(doc, "doi", "DOI", "identifierdoi", "identifiersdoi")
    candidates = []
    if direct:
        candidates.append(_eric_clean_text(direct))
    for key in (
        "url",
        "URL",
        "ieslinkpublication",
        "e_fulltext",
        "fulltexturl",
        "full_text_url",
    ):
        value = _eric_field(doc, key)
        if value:
            candidates.append(_eric_clean_text(value))

    pattern = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
    for candidate in candidates:
        match = pattern.search(candidate)
        if not match:
            continue
        doi = match.group(0).rstrip(".,;:)]}")
        if doi.lower().startswith(("https://doi.org/", "http://doi.org/")):
            doi = doi.split("/", 3)[-1]
        return doi
    return ""


def _eric_url(doc: dict) -> str:
    """Return the first usable ERIC URL supplied by the notice."""
    for key in (
        "url",
        "URL",
        "ieslinkpublication",
        "e_fulltext",
        "fulltexturl",
        "full_text_url",
    ):
        value = _eric_field(doc, key)
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for item in values:
            candidate = _eric_clean_text(item)
            if candidate.startswith(("https://", "http://")):
                return candidate
    return ""


def _eric_notice_to_result(doc: object) -> dict | None:
    """Map one official ERIC notice to the common Hermes result shape."""
    if not isinstance(doc, dict):
        return None
    eric_id = _eric_clean_text(
        _eric_field(doc, "id", "ERICID", "ericid", "eric_id")
    )
    if not eric_id:
        return None

    import urllib.parse

    return {
        "source": "eric",
        "title": _eric_clean_text(_eric_field(doc, "title", "Title")),
        "doi": _eric_doi(doc),
        "source_id": (
            "https://eric.ed.gov/?id="
            f"{urllib.parse.quote(eric_id, safe='')}"
        ),
        "year": _eric_clean_text(
            _eric_field(
                doc,
                "publicationdateyear",
                "publicationDateYear",
                "publication_year",
                "year",
            )
        ),
        "abstract": _eric_clean_text(
            _eric_field(doc, "description", "abstract", "Abstract")
        ),
        "oa_url": _eric_url(doc),
        "authors": _eric_clean_text(_eric_field(doc, "author", "authors")),
        "publication_type": _eric_clean_text(
            _eric_field(doc, "publicationtype", "publicationType", "publication_type")
        ),
        "subjects": _eric_clean_text(
            _eric_field(doc, "subject", "subjects", "descriptors")
        ),
    }


def _parse_eric_response(payload: bytes | str) -> tuple[int | None, list[dict]]:
    """Parse the official ERIC JSON envelope ``response.numFound/docs``."""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8-sig")
    else:
        text = payload
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("invalid ERIC response")
    response = parsed.get("response", parsed)
    if not isinstance(response, dict):
        raise ValueError("invalid ERIC response envelope")
    count_value = response.get("numFound")
    if count_value is None:
        count_value = response.get("numfound")
    docs = response.get("docs", [])
    if docs is None:
        docs = []
    if not isinstance(docs, list):
        raise ValueError("invalid ERIC docs")
    return _parse_nonnegative_count(count_value), docs


def _eric_request(params: dict[str, str]) -> tuple[bytes | None, str]:
    """GET one ERIC page with retries and no credential-bearing parameters."""
    import time
    import urllib.error
    import urllib.parse
    import urllib.request

    request_url = f"{ERIC_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        request_url,
        headers={"User-Agent": "HermesSynthesis/0.1"},
        method="GET",
    )
    last_error_code = None
    for attempt in range(ERIC_MAX_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read(), ""
        except urllib.error.HTTPError as exc:
            last_error_code = exc.code
            if exc.code not in ERIC_RETRYABLE_HTTP_CODES:
                return None, f"HTTP {exc.code}"
            if attempt < ERIC_MAX_RETRIES - 1:
                delay = 2 ** attempt
                print(
                    f"  ⚠️  ERIC HTTP {exc.code} — tentative "
                    f"{attempt + 1}/{ERIC_MAX_RETRIES}, retry dans {delay}s...",
                    file=sys.stderr,
                )
                time.sleep(delay)
            else:
                print(
                    f"  ⚠️  ERIC HTTP {exc.code} — tentative "
                    f"{attempt + 1}/{ERIC_MAX_RETRIES} (dernier essai).",
                    file=sys.stderr,
                )
        except Exception as exc:
            return None, f"exception: {exc}"

    code = str(last_error_code) if last_error_code is not None else "429/5xx"
    return (
        None,
        f"requête abandonnée après {ERIC_MAX_RETRIES} tentatives (HTTP {code})",
    )


def _eric_search(query: SourceQueryInput, max_results: int | None = None) -> SearchResult:
    """Search ERIC through its JSON API using explicit start/rows pagination."""
    try:
        prepared_query = prepare_eric_query(query)
    except InvalidEricQuery as exc:
        print(f"  ❌ {exc}", file=sys.stderr)
        return [], None, "error", str(exc)

    hard_limit = _resolve_hard_limit(max_results)
    exact_params = prepared_query["params"]
    all_results: list[dict] = []
    start = 0
    expected_count: int | None = None
    first_page = True

    while True:
        target_for_request = (
            hard_limit
            if expected_count is None
            else min(expected_count, hard_limit)
        )
        remaining = target_for_request - len(all_results)
        rows = min(ERIC_PAGE_SIZE, max(ERIC_MIN_PAGE_SIZE, remaining))
        params = {
            "search": exact_params["search"],
            "format": "json",
            "start": str(start),
            "rows": str(rows),
            "fields": ERIC_FIELDS,
        }
        if "sort" in exact_params:
            params["sort"] = exact_params["sort"]

        payload, request_reason = _eric_request(params)
        if payload is None:
            if first_page:
                return [], None, "error", f"ERIC: {request_reason}"
            return all_results, expected_count, "incomplete", f"ERIC: {request_reason}"

        try:
            page_count, docs = _parse_eric_response(payload)
        except Exception as exc:
            safe_reason = str(exc)
            if first_page:
                return [], None, "error", f"ERIC JSON invalide: {safe_reason}"
            return all_results, expected_count, "incomplete", (
                f"ERIC JSON invalide: {safe_reason}"
            )

        if page_count is None:
            return (
                all_results,
                None if first_page else expected_count,
                "incomplete",
                "missing_or_invalid_expected_count",
            )
        if first_page:
            expected_count = page_count
        elif page_count != expected_count:
            return all_results, expected_count, "incomplete", (
                "ERIC numFound incohérent entre les pages"
            )

        if expected_count == 0:
            return [], 0, "complete", "zero_results"
        if hard_limit == 0:
            return [], expected_count, "capped", "plafond 0 atteint"

        if not docs:
            return all_results, expected_count, "incomplete", (
                f"page ERIC vide à partir de start={start}"
            )

        for doc in docs:
            result = _eric_notice_to_result(doc)
            if result is None:
                return all_results, expected_count, "incomplete", (
                    "invalid_eric_notice"
                )
            all_results.append(result)
            if len(all_results) >= min(expected_count, hard_limit):
                break

        target_count = min(expected_count, hard_limit)
        if len(all_results) >= target_count:
            all_results = all_results[:target_count]
            if expected_count > hard_limit:
                return all_results, expected_count, "capped", (
                    f"arrêt volontaire à {hard_limit} (requête trop large)"
                )
            return all_results, expected_count, "complete", ""

        start += len(docs)
        first_page = False


def _openalex_search(query: SourceQueryInput, max_results: int | None = None) -> SearchResult:
    """
    Interroge l'API OpenAlex et retourne (results, expected_count, status, status_reason).

    status ∈ {"complete", "incomplete", "capped", "error"}

    Clé API requise depuis février 2026 (lue depuis OPENALEX_API_KEY).
    Clé API requise ; quotas et coûts consultables dans les en-têtes de réponse
    et la documentation officielle.
    Documentation : https://developers.openalex.org/api-reference/authentication

    Un objet structuré utilise `search=` et, s'il existe, `filter=` séparément.
    Toute chaîne historique et toute autre requête invalide sont rejetées avant
    le réseau.

    Pagination par page (per_page=100) jusqu'à épuisement.
    Garde-fou : arrêt à 2000 résultats avec avertissement.
    Retry avec backoff exponentiel (1s, 2s, 4s, 4 tentatives max) sur HTTP 429
    et les erreurs serveur temporaires (500, 502, 503, 504).
    Utilise UNPAYWALL_EMAIL comme adresse de contact dans le User-Agent
    (fallback sur mailto générique).

    Returns:
        results: liste d'articles standardisés
        expected_count: meta.count annoncé par OpenAlex (None si inconnu)
        status: "complete" | "incomplete" | "capped" | "error"
        status_reason: description humaine du statut
    """
    import urllib.request
    import urllib.parse
    import time

    try:
        prepared_query = prepare_openalex_query(query)
    except InvalidOpenAlexQuery as exc:
        print(f"  ❌ {exc}", file=sys.stderr)
        return [], None, "error", str(exc)

    courteous_email = os.environ.get("UNPAYWALL_EMAIL", "hermes-synthesis@example.org")
    api_key = os.environ.get("OPENALEX_API_KEY", "")

    all_results = []
    expected_count = None
    page = 1
    per_page = 100
    hard_limit = int(os.environ.get("HARD_LIMIT", "2000"))
    fatal_error = False
    status = "complete"
    status_reason = ""
    last_error_code = None
    use_cursor = False
    cursor = None
    max_cursor_pages = 500
    count_checked = False
    invalid_expected_count = False

    while True:
        base_params = {**prepared_query["params"], "per_page": per_page}
        if api_key:
            base_params["api_key"] = api_key
        if use_cursor:
            cur_val = cursor if cursor else "*"
            params = urllib.parse.urlencode({**base_params, "cursor": cur_val})
        else:
            params = urllib.parse.urlencode({**base_params, "page": page})
        url = f"https://api.openalex.org/works?{params}"

        # --- Retry avec backoff exponentiel sur 429 et 5xx ---
        data = None
        max_retries = 4
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url)
                req.add_header("User-Agent", f"HermesSynthesis/0.1 (mailto:{courteous_email})")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
                break  # succès → sort de la boucle retry
            except urllib.error.HTTPError as e:
                last_error_code = e.code
                if e.code in (429, 500, 502, 503, 504):
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt  # 1s, 2s, 4s
                        print(f"  ⚠️  HTTP {e.code} — tentative {attempt + 1}/{max_retries}, "
                              f"retry dans {delay}s...", file=sys.stderr)
                        time.sleep(delay)
                    else:
                        print(f"  ⚠️  HTTP {e.code} — tentative {attempt + 1}/{max_retries} "
                              "(dernier essai).", file=sys.stderr)
                else:
                    # 4xx = vraie erreur, pas de retry
                    print(f"  ❌ OpenAlex HTTP {e.code}: {e}", file=sys.stderr)
                    status = "error"
                    status_reason = f"HTTP {e.code} sur page {page}"
                    fatal_error = True
                    break
            except Exception as e:
                print(f"  ❌ OpenAlex API error: {e}", file=sys.stderr)
                status = "error"
                status_reason = f"exception sur page {page}: {e}"
                fatal_error = True
                break

        # Après la boucle retry : si data est None, toutes les tentatives 429/5xx ont échoué
        if data is None and not fatal_error:
            code_str = str(last_error_code) if last_error_code is not None else "429/5xx"
            status = "incomplete"
            status_reason = (f"page {page} abandonnée après {max_retries} tentatives "
                            f"(HTTP {code_str})")
            fatal_error = True

        if fatal_error:
            break

        raw_meta = data.get("meta", {}) if isinstance(data, dict) else {}
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        raw_count = meta.get("count") if isinstance(raw_meta, dict) else None
        count_is_valid = (
            not isinstance(raw_count, bool)
            and isinstance(raw_count, int)
            and raw_count >= 0
        )
        if not count_is_valid:
            if not count_checked:
                expected_count = None
            invalid_expected_count = True
            status = "incomplete"
            status_reason = "missing_or_invalid_expected_count"
        elif not count_checked:
            count_checked = True
            expected_count = raw_count
            if expected_count is not None and expected_count > 10000:
                use_cursor = True
                continue

        results = data.get("results", []) if isinstance(data, dict) else []
        if not results:
            if expected_count is not None and expected_count == 0 and status == "complete":
                status_reason = "zero_results"
            elif expected_count is None:
                status = "incomplete"
                status_reason = "missing_or_invalid_expected_count"
            break

        for w in results:
            abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
            oa_info = w.get("open_access", {})

            all_results.append({
                "title": w.get("title", ""),
                "doi": _clean_doi(w.get("doi", "")),
                "source_id": w.get("id", ""),
                "year": str(w.get("publication_year", "")),
                "abstract": abstract,
                "oa_url": oa_info.get("oa_url", ""),
            })

        if invalid_expected_count:
            break

        if len(all_results) >= hard_limit:
            if (
                expected_count is not None
                and expected_count == hard_limit
                and len(all_results) >= expected_count
            ):
                break
            print(f"  ⚠️  Plafond de sécurité {hard_limit} atteint.", file=sys.stderr)
            status = "capped"
            status_reason = f"arrêt volontaire à {hard_limit} (requête trop large)"
            break
        if use_cursor:
            cursor = meta.get("next_cursor")
            if not cursor:
                break
            page += 1
            if page > max_cursor_pages:
                status = "capped"
                status_reason = f"garde-fou cursor: {max_cursor_pages} pages"
                break
        else:
            if page * per_page >= meta.get("count", 0):
                break
            page += 1
        time.sleep(0.15)

    # Détermine le statut final (sauf si déjà fixé par erreur/capped/incomplete)
    if status == "complete":
        if fatal_error:
            status = "error"
            status_reason = status_reason or "erreur fatale non spécifiée"
        elif (
            expected_count is not None
            and expected_count > 0
            and len(all_results) < expected_count
        ):
            status = "incomplete"
            status_reason = (f"récupéré {len(all_results)}/{expected_count} "
                            f"(manque {expected_count - len(all_results)})")
        elif (
            len(all_results) >= hard_limit
            and not (expected_count is not None
                     and expected_count == hard_limit
                     and len(all_results) >= expected_count)
        ):
            status = "capped"
            status_reason = f"plafond {hard_limit} atteint"

    return all_results[:hard_limit], expected_count, status, status_reason


CONNECTOR_REGISTRY: dict[str, ConnectorSpec] = {
    "openalex": {
        "search": _openalex_search,
        "endpoint": "https://api.openalex.org/works",
        "api_version": "unversioned",
        "query_mode": "search",
    },
    "pubmed": {
        "search": _pubmed_search,
        "endpoint": PUBMED_ESEARCH_ENDPOINT,
        "fetch_endpoint": PUBMED_EFETCH_ENDPOINT,
        "api_version": "NCBI E-utilities",
        "query_mode": "pubmed",
    },
    "eric": {
        "search": _eric_search,
        "endpoint": ERIC_ENDPOINT,
        "api_version": "ERIC API",
        "query_mode": "eric",
    },
}


def search_source(source: str, query: SourceQueryInput) -> SearchResult:
    """Interroge une seule source via le registre et valide son résultat."""
    spec = CONNECTOR_REGISTRY.get(source)
    if spec is None:
        raise NotImplementedError(
            f"Source '{source}' pas encore câblée. Sources disponibles : "
            "openalex, pubmed, eric.\n"
            f"Utilise --mock pour tester le pipeline en attendant."
        )
    result = spec["search"](query)
    return _validate_search_result(source, result)


# Compatibilité rétroactive pour les appelants historiques.
mcp_search = search_source


# ---------------------------------------------------------------------------
# Mode mock (pour tests du pipeline sans MCP)
# ---------------------------------------------------------------------------

MOCK_DATA = {
    "openalex": [
        {
            "title": "L'impact de l'intelligence artificielle sur la productivité des PME manufacturières",
            "doi": "10.1234/mock001",
            "year": "2024",
            "abstract": "Cette étude examine l'effet de l'adoption de l'IA sur la productivité de 150 PME du secteur manufacturier. Les résultats montrent un gain moyen de 12% sur 2 ans.",
            "oa_url": "https://example.org/oa/mock001.pdf",
        },
        {
            "title": "Artificial Intelligence Adoption in Small Business: Barriers and Enablers",
            "doi": "10.1234/mock002",
            "year": "2023",
            "abstract": "A systematic review of AI adoption in SMEs identifying key barriers including skills gap and data readiness.",
            "oa_url": "",
        },
        {
            "title": "Machine Learning et performance des TPE françaises : une étude empirique",
            "doi": "10.1234/mock003",
            "year": "2025",
            "abstract": "Analyse quantitative de 200 TPE françaises ayant déployé des solutions de ML entre 2020 et 2024.",
            "oa_url": "https://example.org/oa/mock003.pdf",
        },
        {
            "title": "Digital Transformation and Firm Productivity: The Role of AI",
            "doi": "10.1234/mock004",
            "year": "2024",
            "abstract": "Panel study of 500 firms showing AI adoption increases productivity by 8-15% depending on sector.",
            "oa_url": "",
        },
        {
            "title": "Les déterminants de l'adoption de l'IA dans les PME européennes",
            "doi": "10.1234/mock005",
            "year": "2023",
            "abstract": "Enquête auprès de 800 PME dans 5 pays européens sur les facteurs d'adoption de l'IA.",
            "oa_url": "https://example.org/oa/mock005.pdf",
        },
    ],
    "crossref": [
        {
            "title": "AI and the Future of Small Business Productivity",
            "doi": "10.1234/mock006",
            "year": "2025",
            "abstract": "Forward-looking analysis of AI-driven productivity gains in SMEs across sectors.",
            "oa_url": "",
        },
        {
            "title": "Impact des technologies d'automatisation sur l'emploi et la productivité en PME",
            "doi": "10.1234/mock003",  # même DOI que mock003 → test dédup
            "year": "2025",
            "abstract": "Version Crossref du même article — doit être fusionné lors de la dédup.",
            "oa_url": "https://example.org/oa/mock003.pdf",
        },
        {
            "title": "Small Business AI Readiness Index 2024",
            "doi": "10.1234/mock007",
            "year": "2024",
            "abstract": "Survey-based index measuring AI readiness across 1000 small businesses globally.",
            "oa_url": "",
        },
        {
            "title": "ChatGPT in the Workplace: Early Evidence from SMEs",
            "doi": "10.1234/mock008",
            "year": "2024",
            "abstract": "Mixed-methods study of ChatGPT adoption in 50 SMEs, finding productivity gains in knowledge work.",
            "oa_url": "https://example.org/oa/mock008.pdf",
        },
        {
            "title": "ROI de l'IA générative pour les petites structures",
            "doi": "10.1234/mock009",
            "year": "2025",
            "abstract": "Calcul de retour sur investissement pour 30 PME ayant déployé des outils d'IA générative.",
            "oa_url": "",
        },
    ],
}


def mock_search(source: str, query: SourceQueryInput) -> SearchResult:
    """Retourne des données mock pour une source donnée (toujours complet)."""
    if source == "openalex":
        try:
            validate_openalex_query(query)
        except InvalidOpenAlexQuery as exc:
            return [], None, "error", str(exc)
    elif source == "pubmed":
        try:
            validate_pubmed_query(query)
        except InvalidPubMedQuery as exc:
            return [], None, "error", str(exc)
    elif source == "eric":
        try:
            validate_eric_query(query)
        except InvalidEricQuery as exc:
            return [], None, "error", str(exc)
    results = MOCK_DATA.get(source, [])
    return _validate_search_result(source, (results, len(results), "complete", "mock"))


# ---------------------------------------------------------------------------
# Réconciliation dropzone
# ---------------------------------------------------------------------------

def reconcile_dropzone(rows: list[dict], pdf_dir: str) -> list[dict]:
    """
    Associe un PDF local à une ligne si le DOI matche un nom de fichier.
    Le fichier doit être nommé <doi>.pdf (avec '/' remplacés par '_').
    Exemple : 10.1234_mock001.pdf pour le DOI 10.1234/mock001
    """
    if not os.path.isdir(pdf_dir):
        return rows

    local: dict[str, str] = {}
    for p in glob.glob(f"{pdf_dir}/*.pdf"):
        name = os.path.basename(p).rsplit(".pdf", 1)[0]
        # Convertit le nom de fichier en DOI : remplace _ par /
        doi_candidate = name.replace("_", "/")
        local[doi_candidate] = p

    for r in rows:
        doi = r.get("doi", "")
        if doi and doi in local:
            r["pdf_status"] = "dropzone"
            r["pdf_path"] = local[doi]
        elif not r.get("pdf_status"):
            r["pdf_status"] = "oa" if r.get("oa_url") else "none"

    return rows


STATUS_PRIORITY = {"error": 0, "incomplete": 1, "capped": 2, "complete": 3}
REVERSE_STATUS_PRIORITY = {value: key for key, value in STATUS_PRIORITY.items()}


def _query_mode_for_manifest(source: str, query: object) -> str:
    """Detect the per-request mode without changing connector metadata."""
    if source != "openalex":
        spec = CONNECTOR_REGISTRY.get(source)
        return spec["query_mode"] if spec is not None else "unknown"
    try:
        return prepare_openalex_query(query)["query_mode"]
    except InvalidOpenAlexQuery:
        return "unknown"


def _connector_metadata(source: str, query_mode: str | None = None) -> dict[str, str]:
    """Return manifest metadata for a source, with explicit unknown defaults."""
    spec = CONNECTOR_REGISTRY.get(source)
    if spec is None:
        return {"endpoint": "", "api_version": "unknown", "query_mode": "unknown"}
    metadata = {
        "endpoint": spec["endpoint"],
        "api_version": spec["api_version"],
        "query_mode": query_mode if query_mode is not None else spec["query_mode"],
    }
    if "fetch_endpoint" in spec:
        metadata["fetch_endpoint"] = spec["fetch_endpoint"]
    return metadata


def _global_search_status(search_meta: dict[str, dict]) -> str:
    """Return the worst status; unknown values fail closed as ``error``."""
    global_priority = min(
        (
            STATUS_PRIORITY.get(metadata.get("status"), STATUS_PRIORITY["error"])
            if isinstance(metadata.get("status"), str)
            else STATUS_PRIORITY["error"]
            for metadata in search_meta.values()
        ),
        default=STATUS_PRIORITY["complete"],
    )
    return REVERSE_STATUS_PRIORITY[global_priority]


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str, queries: dict[str, SourceQueryInput], use_mock: bool = False):
    base = f"/reviews/{rid}"
    today = date.today().isoformat()

    # Vérifie que le dossier de revue existe
    if not os.path.isdir(base):
        print(f"❌ Dossier de revue introuvable : {base}", file=sys.stderr)
        print("   Lance d'abord la skill protocol.", file=sys.stderr)
        sys.exit(1)

    # Refuse les requêtes structurées invalides avant tout appel de connecteur
    # ou écriture de sortie. PubMed ne conserve aucun chemin d'entrée générique.
    for source, query in queries.items():
        if source == "openalex" and isinstance(query, str):
            try:
                validate_openalex_query(query)
            except InvalidOpenAlexQuery as exc:
                print(f"❌ {exc}", file=sys.stderr)
                raise
        elif source == "pubmed":
            try:
                validate_pubmed_query(query)
            except InvalidPubMedQuery as exc:
                print(f"❌ {exc}", file=sys.stderr)
                raise
        elif source == "eric":
            try:
                validate_eric_query(query)
            except InvalidEricQuery as exc:
                print(f"❌ {exc}", file=sys.stderr)
                raise

    # TODO: read the year window from protocol.md and inject it into the
    # OpenAlex filter (from_publication_date) automatically, instead of
    # relying on a well-formed query passed in by hand. Skipped for now —
    # low priority, adds complexity/risk for a run that already works.
    search_fn = mock_search if use_mock else mcp_search
    rows: list[dict] = []
    search_meta: dict[str, dict] = {}  # source → connector metadata + counters/status

    for source, query in queries.items():
        query_mode = _query_mode_for_manifest(source, query)
        display_query = query
        if source == "pubmed":
            display_query = _sanitize_ncbi_message(
                query,
                os.environ.get("NCBI_EMAIL", ""),
                os.environ.get("NCBI_API_KEY", ""),
            )
        print(f"🔍 Recherche {source} : {display_query}")
        try:
            raw_result = search_fn(source, query)
            results, expected, status, reason = _validate_search_result(source, raw_result)
        except InvalidSearchContract as e:
            print(f"❌ {e}", file=sys.stderr)
            search_meta[source] = {
                **_connector_metadata(source, query_mode),
                "retrieved": 0,
                "expected": None,
                "status": "error",
                "reason": str(e),
            }
            continue
        except NotImplementedError as e:
            print(f"⚠️  {e}", file=sys.stderr)
            search_meta[source] = {
                **_connector_metadata(source, query_mode),
                "retrieved": 0,
                "expected": None,
                "status": "error",
                "reason": str(e),
            }
            continue

        search_meta[source] = {
            **_connector_metadata(source, query_mode),
            "retrieved": len(results),
            "expected": expected,
            "status": status,
            "reason": reason
        }

        if results:
            query_provenance = serialize_source_query_for_csv(source, query)
            for item in results:
                rows.append({
                    "title": item.get("title", ""),
                    "doi": item.get("doi", ""),
                    "source_id": item.get("source_id", ""),
                    "year": str(item.get("year", "")),
                    "abstract": item.get("abstract", ""),
                    "oa_url": item.get("oa_url", ""),
                    "pdf_status": "",  # rempli par reconcile_dropzone
                    "source": source,
                    "query": query_provenance,
                    "date": today,
                })

    # Réconciliation dropzone
    rows = reconcile_dropzone(rows, f"{base}/inputs/pdfs")

    # Écriture candidates.csv
    cols = [
        "title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status",
        "source", "query", "date",
    ]
    csv_path = f"{base}/candidates.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Mise à jour prisma.json
    prisma_path = f"{base}/prisma.json"
    if os.path.exists(prisma_path):
        prisma = json.load(open(prisma_path, encoding="utf-8"))
    else:
        prisma = {}
    prisma["identified"] = len(rows)
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest_path = f"{base}/manifest.json"
    if os.path.exists(manifest_path):
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    else:
        manifest = {"id": rid}
    # Statut global : le pire des statuts par source
    global_status = _global_search_status(search_meta)

    manifest["stage"] = "search_done"
    manifest["queries"] = queries
    manifest["search_status"] = global_status
    manifest["search_meta"] = search_meta
    manifest["updated"] = datetime.now(timezone.utc).isoformat()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if global_status == "complete":
        print(f"✅ {len(rows)} candidats (corpus COMPLET)")
    elif global_status == "capped":
        print(f"⚠️  {len(rows)} candidats (CORPUS TRONQUÉ — plafond sécurité)")
    elif global_status == "incomplete":
        print(f"⚠️  CORPUS INCOMPLET : {len(rows)} candidats")
        for src, m in search_meta.items():
            if m.get("status") == "incomplete":
                print(f"   {src}: {m['retrieved']}/{m['expected']} — {m['reason']}")
        print("   → NE PAS utiliser pour comparaison quantitative.")
    else:  # error
        print(f"❌ ERREUR : {len(rows)} candidats (run probablement corrompu)")
        for src, m in search_meta.items():
            if m.get("status") == "error":
                print(f"   {src}: {m['reason']}")
    if use_mock:
        print("   (mode mock — données fictives pour test du pipeline)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: search.py '<json>' [--mock]", file=sys.stderr)
        sys.exit(1)

    use_mock = "--mock" in sys.argv

    raw = sys.argv[1] if sys.argv[1] != "--mock" else (
        sys.argv[2] if len(sys.argv) > 2 else ""
    )
    if not raw:
        print("Usage: search.py '<json>' [--mock]", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}", file=sys.stderr)
        sys.exit(1)

    if "id" not in payload or "queries" not in payload:
        print("JSON invalide : 'id' et 'queries' requis.", file=sys.stderr)
        sys.exit(1)

    main(payload["id"], payload["queries"], use_mock=use_mock)
