#!/usr/bin/env python3
"""
search.py — Récupère des articles candidats multi-sources pour Hermes Synthesis.

Interroge les bases académiques (OpenAlex, puis connecteurs API directs),
fusionne les résultats, réconcilie avec la dropzone par DOI, et écrit
candidates.csv avec provenance complète.

Usage:
  python3 search.py '<json>'            # mode réel (OpenAlex câblé)
  python3 search.py '<json>' --mock     # mode test avec données fictives

JSON attendu:
  {"id": "ma-revue", "queries": {"openalex": {
      "query_mode": "search",
      "search": "climate adaptation",
      "filter": "from_publication_date:2020-01-01"
  }, "crossref": "..."}}

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
  - autres sources : via connecteurs API directs, ajoutés et validés une par une

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


VALID_SEARCH_STATUSES = frozenset({"complete", "incomplete", "capped", "error"})


class ConnectorSpec(TypedDict):
    search: SearchFunction
    endpoint: str
    api_version: str
    query_mode: str


class InvalidSearchContract(ValueError):
    """Raised when a connector does not return the common four-field tuple."""


class InvalidOpenAlexQuery(ValueError):
    """Raised when an OpenAlex query is not in a supported input format."""


_OPENALEX_QUERY_KEYS = frozenset({"query_mode", "search", "filter"})


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


def serialize_query_for_csv(query: OpenAlexQueryInput) -> str:
    """Serialize a validated structured query for candidates.csv provenance."""
    validated = validate_openalex_query(query)
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
}


def search_source(source: str, query: SourceQueryInput) -> SearchResult:
    """Interroge une seule source via le registre et valide son résultat."""
    spec = CONNECTOR_REGISTRY.get(source)
    if spec is None:
        raise NotImplementedError(
            f"Source '{source}' pas encore câblée. Sources disponibles : openalex.\n"
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

    # Refuse les anciennes chaînes OpenAlex avant tout appel de connecteur ou
    # écriture de sortie. Les futurs connecteurs gardent leur entrée générique;
    # les objets OpenAlex invalides suivent le chemin d'erreur du connecteur.
    for source, query in queries.items():
        if source == "openalex" and isinstance(query, str):
            try:
                validate_openalex_query(query)
            except InvalidOpenAlexQuery as exc:
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
        print(f"🔍 Recherche {source} : {query}")
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
