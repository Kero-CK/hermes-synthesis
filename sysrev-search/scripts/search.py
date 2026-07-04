#!/usr/bin/env python3
"""
search.py — Récupère des articles candidats multi-sources pour Hermes Synthesis.

Interroge les bases académiques (OpenAlex, + paper-search-mcp à venir),
fusionne les résultats, réconcilie avec la dropzone par DOI, et écrit
candidates.csv avec provenance complète.

Usage:
  python3 search.py '<json>'            # mode réel (OpenAlex câblé)
  python3 search.py '<json>' --mock     # mode test avec données fictives

JSON attendu:
  {"id": "ma-revue", "queries": {"openalex": "...", "crossref": "..."}}

  La requête openalex est passée telle quelle au paramètre `filter=` de
  l'API OpenAlex (PAS `search=`) : elle doit donc être en syntaxe filter
  structurée, pas du texte libre. Exemple valide :
    "title.search:self-improving,title_and_abstract.search:LLM agent,from_publication_date:2022-01-01"
  Voir https://docs.openalex.org/api-entities/works/filter-works pour la
  syntaxe complète (title.search, title_and_abstract.search,
  from_publication_date, etc., séparés par des virgules = ET logique).

Sources câblées :
  - openalex : ~250M articles (docs.openalex.org). Nécessite une clé API
    depuis février 2026 — lue depuis OPENALEX_API_KEY dans l'environnement.
  - crossref, pubmed : via paper-search-mcp (TODO)

Le script ne prend AUCUNE décision de recherche : les requêtes sont déjà
validées par l'humain en amont. Il fait l'exécution mécanique.
"""

import csv
import glob
import json
import os
import sys
from datetime import date, datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Recherche réelle — OpenAlex (clé API requise depuis février 2026)
# ---------------------------------------------------------------------------


def _looks_like_filter_syntax(query: str) -> bool:
    """
    Heuristique : une requête filter OpenAlex valide contient au moins un
    champ structuré du type `champ.search:...` ou `champ:...`
    (ex. title.search:, from_publication_date:). Du texte libre sans ':'
    n'est jamais une syntaxe filter valide et provoquerait un HTTP 400.
    """
    return ":" in query


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


def _openalex_search(query: str, max_results: int | None = None) -> tuple[list[dict], int, str, str]:
    """
    Interroge l'API OpenAlex et retourne (results, expected_count, status, status_reason).

    status ∈ {"complete", "incomplete", "capped", "error"}

    Clé API requise depuis février 2026 (lue depuis OPENALEX_API_KEY).
    Rate limit : 10 req/s (pool courtois), 100k/jour. Docs : https://docs.openalex.org/

    `query` est passée telle quelle au paramètre `filter=` de l'API — elle
    doit être en syntaxe filter structurée (ex. "title.search:X,from_publication_date:2023-01-01"),
    pas du texte libre. Une requête sans syntaxe filter reconnaissable est
    rejetée avant l'appel réseau plutôt que de provoquer un HTTP 400 opaque.

    Pagination par page (per_page=200) jusqu'à épuisement.
    Garde-fou : arrêt à 2000 résultats avec avertissement.
    Retry avec backoff exponentiel (1s, 2s, 4s, 4 tentatives max) sur HTTP 429.
    Utilise UNPAYWALL_EMAIL pour le pool courtois (fallback sur mailto générique).

    Returns:
        results: liste d'articles standardisés
        expected_count: meta.count annoncé par OpenAlex (0 si inconnu)
        status: "complete" | "incomplete" | "capped" | "error"
        status_reason: description humaine du statut
    """
    import urllib.request
    import urllib.parse
    import time

    if not _looks_like_filter_syntax(query):
        print(
            "  ❌ Requête OpenAlex invalide : ceci ressemble à du texte libre, "
            "pas à une syntaxe filter.\n"
            "     Le paramètre filter= d'OpenAlex exige une syntaxe structurée, "
            "ex. :\n"
            '     "title.search:self-improving,title_and_abstract.search:LLM agent,'
            'from_publication_date:2022-01-01"\n'
            "     Voir https://docs.openalex.org/api-entities/works/filter-works",
            file=sys.stderr,
        )
        return [], 0, "error", "requête invalide : pas de syntaxe filter (texte libre détecté)"

    courteous_email = os.environ.get("UNPAYWALL_EMAIL", "hermes-synthesis@example.org")
    api_key = os.environ.get("OPENALEX_API_KEY", "")

    all_results = []
    expected_count = 0
    page = 1
    per_page = 200
    hard_limit = int(os.environ.get("HARD_LIMIT", "2000"))
    fatal_error = False
    status = "complete"
    status_reason = ""
    last_error_code = None
    use_cursor = False
    cursor = None
    max_cursor_pages = 500
    count_checked = False

    while True:
        base_params = {"filter": query, "per_page": per_page}
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
                if e.code in (429, 502, 503, 504):
                    delay = 2 ** attempt  # 1s, 2s, 4s, 8s
                    print(f"  ⚠️  HTTP {e.code} — tentative {attempt + 1}/{max_retries}, "
                          f"retry dans {delay}s...", file=sys.stderr)
                    time.sleep(delay)
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

        meta = data.get("meta", {})
        if not count_checked:
            count_checked = True
            expected_count = meta.get("count", 0)
            if expected_count > 10000:
                use_cursor = True
                continue

        results = data.get("results", [])
        if not results:
            break

        for w in results:
            abstract = _reconstruct_abstract(w.get("abstract_inverted_index"))
            oa_info = w.get("open_access", {})

            all_results.append({
                "title": w.get("title", ""),
                "doi": _clean_doi(w.get("doi", "")),
                "year": str(w.get("publication_year", "")),
                "abstract": abstract,
                "oa_url": oa_info.get("oa_url", ""),
            })

        if len(all_results) >= hard_limit:
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
        elif expected_count > 0 and len(all_results) < expected_count:
            status = "incomplete"
            status_reason = (f"récupéré {len(all_results)}/{expected_count} "
                            f"(manque {expected_count - len(all_results)})")
        elif len(all_results) >= hard_limit:
            status = "capped"
            status_reason = f"plafond {hard_limit} atteint"

    return all_results[:hard_limit], expected_count, status, status_reason


def mcp_search(source: str, query: str) -> tuple[list[dict], int, str, str]:
    """
    Interroge une source de recherche académique.
    Retourne (results, expected_count, is_complete).

    Sources supportées :
      - openalex : ≈250M articles, clé API requise depuis février 2026 (OPENALEX_API_KEY)
      - crossref  : TODO (API gratuite, métadonnées DOI)
      - pubmed    : TODO (via paper-search-mcp)

    Pour les sources non encore câblées, bascule sur --mock.
    """
    if source == "openalex":
        return _openalex_search(query)
    else:
        raise NotImplementedError(
            f"Source '{source}' pas encore câblée. Sources disponibles : openalex.\n"
            f"Utilise --mock pour tester le pipeline en attendant."
        )


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


def mock_search(source: str, query: str) -> tuple[list[dict], int, str, str]:
    """Retourne des données mock pour une source donnée (toujours complet)."""
    results = MOCK_DATA.get(source, [])
    return results, len(results), "complete", "mock"


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


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str, queries: dict[str, str], use_mock: bool = False):
    base = f"/reviews/{rid}"
    today = date.today().isoformat()

    # Vérifie que le dossier de revue existe
    if not os.path.isdir(base):
        print(f"❌ Dossier de revue introuvable : {base}", file=sys.stderr)
        print("   Lance d'abord la skill protocol.", file=sys.stderr)
        sys.exit(1)

    # TODO: read the year window from protocol.md and inject it into the
    # OpenAlex filter (from_publication_date) automatically, instead of
    # relying on a well-formed query passed in by hand. Skipped for now —
    # low priority, adds complexity/risk for a run that already works.
    search_fn = mock_search if use_mock else mcp_search
    rows: list[dict] = []
    search_meta: dict[str, dict] = {}  # source → {retrieved, expected, status, reason}

    for source, query in queries.items():
        print(f"🔍 Recherche {source} : {query}")
        try:
            results, expected, status, reason = search_fn(source, query)
        except NotImplementedError as e:
            print(f"⚠️  {e}", file=sys.stderr)
            search_meta[source] = {"retrieved": 0, "expected": 0, "status": "error", "reason": str(e)}
            continue

        search_meta[source] = {
            "retrieved": len(results),
            "expected": expected,
            "status": status,
            "reason": reason
        }

        for item in results:
            rows.append({
                "title": item.get("title", ""),
                "doi": item.get("doi", ""),
                "year": str(item.get("year", "")),
                "abstract": item.get("abstract", ""),
                "oa_url": item.get("oa_url", ""),
                "pdf_status": "",  # rempli par reconcile_dropzone
                "source": source,
                "query": query,
                "date": today,
            })

    # Réconciliation dropzone
    rows = reconcile_dropzone(rows, f"{base}/inputs/pdfs")

    # Écriture candidates.csv
    cols = [
        "title", "doi", "year", "abstract", "oa_url", "pdf_status",
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
    status_priority = {"error": 0, "incomplete": 1, "capped": 2, "complete": 3}
    global_priority = min(
        (status_priority.get(m.get("status", "complete"), 3) for m in search_meta.values()),
        default=3
    )
    reverse_status = {v: k for k, v in status_priority.items()}
    global_status = reverse_status[global_priority]

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
