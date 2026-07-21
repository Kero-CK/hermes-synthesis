#!/usr/bin/env python3
"""
fulltext.py — Récupère et parse les textes intégraux des articles inclus.

Identifie les articles avec decision=include dans decisions.jsonl,
récupère leur PDF (OA ou dropzone), et parse en Markdown.

Usage:
  python3 fulltext.py '<json>'

JSON attendu:
  {"id": "ma-revue", "mock": true}
"""

import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


KNOWN_JOURNAL_VOCABULARY = {
    "dedup": {"merge"},
    "screen_title_abstract": {"include", "exclude", "needs_manual"},
    "human_review": {"include", "exclude"},
    "screen_manual": {"include", "exclude"},  # alias historique
    "fulltext": {"retrieved", "retrieval_failed", "include", "needs_manual"},
    "screen_fulltext": {"include", "exclude", "needs_manual"},
    "human_review_fulltext": {"include", "exclude"},
    "extract": {"extracted", "not_found", "api_error", "rejected_citation", "citation_retry", "include", "needs_manual"},
}
HUMAN_SCREEN_STAGES = {"human_review", "screen_manual"}


def candidate_identity(candidate: dict) -> tuple[str, str] | None:
    """Retourne l'identité stable DOI → source_id → oa_url."""
    for kind in ("doi", "source_id", "oa_url"):
        raw_value = candidate.get(kind, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            return kind, value
    return None


def candidate_identity_values(candidate: dict) -> list[tuple[str, str]]:
    """Retourne tous les identifiants disponibles pour les anciens journaux."""
    values = []
    for kind in ("doi", "source_id", "oa_url"):
        raw_value = candidate.get(kind, "")
        if isinstance(raw_value, str) and raw_value.strip():
            values.append((kind, raw_value.strip()))
    return values


def safe_document_filename(value: str, identity_type: str = "") -> str:
    """Construit un nom de fichier Windows sûr et stable.

    Les DOI conservent exactement la convention historique ``/`` → ``_``.
    Les identifiants de repli sont nettoyés et suffixés d'un hash pour éviter
    les collisions entre URLs ou identifiants différents.
    """
    if identity_type == "doi":
        return value.replace("/", "_")
    safe = re.sub(r'[<>:"/\\|?*]', "_", value).strip().rstrip(". ")
    safe = safe or "document"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{identity_type or 'id'}_{safe[:100]}_{digest}"


def read_valid_markdown(path: str, minimum_characters: int = 500) -> str | None:
    """Retourne un Markdown déjà récupéré s'il est suffisamment substantiel.

    Le cache est vérifié par chemin d'identité du corpus courant. Un fichier
    étranger dans ``sources/`` n'est donc jamais compté ni réutilisé pour un
    autre article.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
    except (OSError, UnicodeError):
        return None
    return content if len(content) > minimum_characters else None


def _screening_documents(entries: list[dict]) -> tuple[list[dict], int]:
    """Résout les inclusions et conserve les métadonnées d'identité."""
    machine_decisions: dict[str, dict] = {}
    human_decisions: dict[str, dict] = {}
    order: list[str] = []
    unknown_entries = 0

    for line_number, entry in enumerate(entries, 1):
        stage = entry.get("stage")
        decision = entry.get("decision")
        if decision not in KNOWN_JOURNAL_VOCABULARY.get(stage, set()):
            unknown_entries += 1
            print(
                f"⚠️  Journal ligne {line_number} : tuple inconnu "
                f"(stage={stage!r}, decision={decision!r})",
                file=sys.stderr,
            )
            continue

        if stage != "screen_title_abstract" and stage not in HUMAN_SCREEN_STAGES:
            continue
        if decision not in ("include", "exclude"):
            continue

        raw_doc = entry.get("doc", "")
        doc = raw_doc.strip() if isinstance(raw_doc, str) else ""
        if not doc:
            print(
                f"⚠️  Journal ligne {line_number} : décision de screening sans identité",
                file=sys.stderr,
            )
            continue
        if doc not in machine_decisions and doc not in human_decisions:
            order.append(doc)

        if stage in HUMAN_SCREEN_STAGES:
            human_decisions[doc] = entry
        else:
            machine_decisions[doc] = entry

    selected = []
    for doc in order:
        entry = human_decisions.get(doc) or machine_decisions.get(doc)
        if entry and entry.get("decision") == "include":
            selected.append(entry)
    return [entry for entry in selected if entry], unknown_entries


def select_included_dois(entries: list[dict]) -> tuple[list[str], int]:
    """Sélectionne les inclusions avec priorité humaine et signale le vocabulaire inconnu."""
    documents, unknown_entries = _screening_documents(entries)
    return [entry["doc"] for entry in documents], unknown_entries


# ---------------------------------------------------------------------------
# PMC XML et téléchargement PDF non-PMC
# ---------------------------------------------------------------------------

PMC_EFETCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PMC_BATCH_SIZE = 200
PMC_REQUEST_INTERVAL_WITHOUT_KEY = 1 / 3
PMC_REQUEST_INTERVAL_WITH_KEY = 1 / 10
UNPAYWALL_ENDPOINT = "https://api.unpaywall.org/v2"
UNPAYWALL_MAX_ATTEMPTS = 4
UNPAYWALL_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_PMC_URL = re.compile(
    r"^https://pmc\.ncbi\.nlm\.nih\.gov/articles/(PMC[0-9]+)(?:/pdf)?/?$"
)


class PmcFetchError(RuntimeError):
    """Erreur globale d'EFetch PMC, avant toute écriture de revue."""


def extract_pmcid_from_url(url: str) -> str | None:
    """Extrait un PMCID d'une URL PMC canonique ou historique /pdf/."""
    if not isinstance(url, str):
        return None
    match = _PMC_URL.fullmatch(url.strip())
    return match.group(1) if match else None


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _xml_text(node: ET.Element) -> str:
    return " ".join("".join(node.itertext()).split())


def _pmc_article_meta(article: ET.Element) -> ET.Element | None:
    """Retourne les métadonnées de l'article principal, hors références."""
    return next(
        (node for node in article.iter() if _xml_local_name(node.tag) == "article-meta"),
        None,
    )


def _pmc_article_id(article: ET.Element, id_types: set[str]) -> str:
    metadata = _pmc_article_meta(article)
    if metadata is None:
        return ""
    for node in metadata.iter():
        if _xml_local_name(node.tag) not in {"article-id", "articleid"}:
            continue
        id_type = (
            node.attrib.get("pub-id-type", "")
            or node.attrib.get("IdType", "")
        ).lower()
        if id_type in id_types:
            value = _xml_text(node)
            if value:
                return value
    return ""


def extract_pmcid_from_article(article: ET.Element) -> str | None:
    """Extrait l'identifiant PMC d'un article JATS."""
    value = _pmc_article_id(article, {"pmc", "pmcid"})
    return value.upper() if value.upper().startswith("PMC") else None


def extract_pmc_doi_from_article(article: ET.Element) -> str:
    """Extrait le DOI de l'article principal, jamais ceux des références."""
    return _pmc_article_id(article, {"doi"})


def extract_pmc_title_from_article(article: ET.Element) -> str:
    """Extrait le titre de l'article principal, hors titres bibliographiques."""
    metadata = _pmc_article_meta(article)
    if metadata is None:
        return ""
    title = next(
        (node for node in metadata.iter() if _xml_local_name(node.tag) == "article-title"),
        None,
    )
    return _xml_text(title) if title is not None else ""


def _append_markdown_line(lines: list[str], line: str) -> None:
    line = line.strip()
    if line and (not lines or lines[-1] != line):
        lines.append(line)


def _render_jats_list(node: ET.Element, lines: list[str]) -> None:
    for child in node.iter():
        if _xml_local_name(child.tag) == "list-item":
            _append_markdown_line(lines, "- " + _xml_text(child))


def _render_jats_section(node: ET.Element, lines: list[str], level: int) -> None:
    title = next(
        (child for child in list(node) if _xml_local_name(child.tag) == "title"),
        None,
    )
    if title is not None:
        _append_markdown_line(
            lines, f"{'#' * min(level, 6)} {_xml_text(title)}"
        )
    _render_jats_children(node, lines, level + 1)


def _render_jats_children(node: ET.Element, lines: list[str], level: int) -> None:
    for child in list(node):
        name = _xml_local_name(child.tag)
        if name in {"title", "label"}:
            continue
        if name == "sec":
            _render_jats_section(child, lines, level)
        elif name == "p":
            _append_markdown_line(lines, _xml_text(child))
        elif name == "list":
            _render_jats_list(child, lines)
        elif name in {"disp-quote", "boxed-text"}:
            _render_jats_children(child, lines, level)
        else:
            _render_jats_children(child, lines, level)


def pmc_article_to_markdown(article: ET.Element) -> str | None:
    """Convertit un article JATS PMC avec un vrai body en Markdown."""
    body = next(
        (node for node in article.iter() if _xml_local_name(node.tag) == "body"),
        None,
    )
    if body is None or len(_xml_text(body)) <= 500:
        return None

    lines: list[str] = []
    metadata = _pmc_article_meta(article)
    title = next(
        (node for node in metadata.iter() if _xml_local_name(node.tag) == "article-title"),
        None,
    ) if metadata is not None else None
    if title is not None:
        _append_markdown_line(lines, "# " + _xml_text(title))

    abstracts = [
        node for node in metadata.iter() if _xml_local_name(node.tag) == "abstract"
    ] if metadata is not None else []
    for abstract in abstracts:
        _append_markdown_line(lines, "## Abstract")
        abstract_text = _xml_text(abstract)
        if abstract_text:
            _append_markdown_line(lines, abstract_text)

    _render_jats_children(body, lines, 2)
    markdown = "\n\n".join(lines).strip() + "\n"
    return markdown if len(markdown) > 500 else None


def normalize_identity_doi(value: str) -> str:
    """Normalise un DOI pour une comparaison d'identité, sans le réécrire en sortie."""
    if not isinstance(value, str):
        return ""
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].strip()
            break
    return normalized.rstrip(" .")


def normalize_identity_title(value: str) -> str:
    """Normalise un titre pour vérifier une identité sans modifier les données."""
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip()


def validate_pmc_identity(
    pmc_record: dict,
    candidate_doi: str,
    candidate_title: str,
) -> tuple[bool, str]:
    """Refuse un corps PMC dont l'identité XML contredit le candidat."""
    xml_doi = normalize_identity_doi(pmc_record.get("doi", ""))
    expected_doi = normalize_identity_doi(candidate_doi)
    if xml_doi and expected_doi:
        if xml_doi != expected_doi:
            return False, (
                f"DOI XML {xml_doi!r} différent du DOI candidat {expected_doi!r}"
            )
        return True, "DOI XML concordant"

    xml_title = normalize_identity_title(pmc_record.get("title", ""))
    expected_title = normalize_identity_title(candidate_title)
    if not xml_title or not expected_title:
        return False, "titre absent ou insuffisant pour vérifier l'identité"
    if xml_title != expected_title:
        return False, "titre XML différent du titre candidat après normalisation"
    return True, "titre XML concordant après normalisation"


def markdown_matches_candidate_title(markdown: str, candidate_title: str) -> bool:
    """Vérifie localement un cache Markdown PMC avant de le réutiliser."""
    markdown_title = next(
        (
            line[2:].strip()
            for line in markdown.splitlines()
            if line.startswith("# ")
        ),
        "",
    )
    return bool(markdown_title) and (
        normalize_identity_title(markdown_title)
        == normalize_identity_title(candidate_title)
    )


def _parse_pmc_xml(payload: bytes, requested: set[str]) -> dict[str, dict | None]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise PmcFetchError("EFetch PMC XML invalide") from exc

    results: dict[str, dict | None] = {}
    for article in root.iter():
        if _xml_local_name(article.tag) != "article":
            continue
        pmcid = extract_pmcid_from_article(article)
        if pmcid and pmcid in requested:
            results[pmcid] = {
                "markdown": pmc_article_to_markdown(article),
                "doi": extract_pmc_doi_from_article(article),
                "title": extract_pmc_title_from_article(article),
            }
    return results


def fetch_pmc_xml(pmcids: list[str], timeout: int = 60) -> dict[str, dict | None]:
    """Récupère les PMCID par EFetch XML groupé, sans écrire de fichier."""
    if not pmcids:
        return {}
    email = os.environ.get("NCBI_EMAIL", "")
    api_key = os.environ.get("NCBI_API_KEY", "")
    if not email:
        raise PmcFetchError("NCBI_EMAIL absent")

    requested = set(pmcids)
    results: dict[str, dict | None] = {}
    batches = [
        pmcids[start:start + PMC_BATCH_SIZE]
        for start in range(0, len(pmcids), PMC_BATCH_SIZE)
    ]
    for index, batch in enumerate(batches):
        if index:
            time.sleep(
                PMC_REQUEST_INTERVAL_WITH_KEY
                if api_key else PMC_REQUEST_INTERVAL_WITHOUT_KEY
            )
        params = {
            "db": "pmc",
            "id": ",".join(batch),
            "retmode": "xml",
            "tool": "hermes_synthesis",
            "email": email,
        }
        if api_key:
            params["api_key"] = api_key
        request = urllib.request.Request(
            PMC_EFETCH_ENDPOINT,
            data=urllib.parse.urlencode(params).encode("utf-8"),
            headers={
                "Accept": "application/xml",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            raise PmcFetchError(f"EFetch PMC HTTP {exc.code}") from exc
        except Exception as exc:
            raise PmcFetchError("EFetch PMC erreur réseau") from exc
        results.update(_parse_pmc_xml(payload, requested))
    return results


def download_pdf(url: str, timeout: int = 30) -> str | None:
    """
    Télécharge un PDF depuis une URL vers un fichier temporaire.
    Retourne le chemin du fichier temporaire, ou None en cas d'échec.
    """
    if extract_pmcid_from_url(url):
        print(
            "    ⚠️  Téléchargement PDF PMC désactivé : utiliser EFetch XML.",
            file=sys.stderr,
        )
        return None
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "HermesSynthesis/0.1 (mailto:hermes-synthesis@example.org)")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type and not url.endswith(".pdf"):
                # Tente quand même, certaines URLs n'ont pas le bon Content-Type
                pass
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.read())
                return tmp.name
    except Exception as e:
        print(f"    ⚠️  Download failed: {e}", file=sys.stderr)
        return None


def _unpaywall_urls(payload: dict) -> list[str]:
    """Retourne les URLs OA Unpaywall dans l'ordre de priorité documenté."""
    locations = []
    best_location = payload.get("best_oa_location")
    if isinstance(best_location, dict):
        locations.append(best_location)
    for location in payload.get("oa_locations", []) or []:
        if isinstance(location, dict):
            locations.append(location)

    urls = []
    seen = set()
    for location in locations:
        for field in ("url_for_pdf", "url"):
            url = location.get(field, "")
            if not isinstance(url, str):
                continue
            url = url.strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def fetch_unpaywall(doi: str, timeout: int = 30) -> dict:
    """Interroge Unpaywall sans jamais exposer l'adresse email dans les logs."""
    normalized_doi = normalize_identity_doi(doi)
    if not normalized_doi:
        return {"reason": "unpaywall_doi_absent"}

    email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
    if not email:
        return {"reason": "unpaywall_email_missing"}

    endpoint = (
        f"{UNPAYWALL_ENDPOINT}/"
        f"{urllib.parse.quote(normalized_doi, safe='')}"
    )
    request_url = endpoint + "?" + urllib.parse.urlencode({"email": email})

    for attempt in range(UNPAYWALL_MAX_ATTEMPTS):
        request = urllib.request.Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "HermesSynthesis/0.1",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if (
                exc.code in UNPAYWALL_RETRY_STATUS_CODES
                and attempt < UNPAYWALL_MAX_ATTEMPTS - 1
            ):
                time.sleep(2 ** attempt)
                continue
            if exc.code == 404:
                return {"reason": "unpaywall_doi_unknown"}
            return {"reason": f"unpaywall_api_http_{exc.code}"}
        except (urllib.error.URLError, TimeoutError, OSError):
            return {"reason": "unpaywall_api_error"}
        except (UnicodeError, json.JSONDecodeError):
            return {"reason": "unpaywall_api_invalid_response"}
    else:
        return {"reason": "unpaywall_api_error"}

    if not isinstance(payload, dict):
        return {"reason": "unpaywall_api_invalid_response"}

    returned_doi = normalize_identity_doi(payload.get("doi", ""))
    if not returned_doi or returned_doi != normalized_doi:
        return {"reason": "unpaywall_identity_mismatch"}

    urls = _unpaywall_urls(payload)
    if not urls:
        return {"reason": "unpaywall_no_open_copy"}

    return {
        "reason": "",
        "doi": returned_doi,
        "title": str(payload.get("title", "") or ""),
        "urls": urls,
    }


def validate_unpaywall_identity(
    lookup: dict,
    markdown: str,
    candidate_doi: str,
    candidate_title: str,
) -> tuple[bool, str]:
    """Valide le DOI API et une identité vérifiable dans le Markdown."""
    expected_doi = normalize_identity_doi(candidate_doi)
    returned_doi = normalize_identity_doi(lookup.get("doi", ""))
    expected_title = normalize_identity_title(candidate_title)

    if not expected_doi or not returned_doi or returned_doi != expected_doi:
        return False, "unpaywall_identity_mismatch"

    doi_pattern = r"\s*".join(re.escape(char) for char in expected_doi)
    doi_in_markdown = bool(
        re.search(
            rf"(?<![a-z0-9]){doi_pattern}(?![a-z0-9])",
            markdown.casefold(),
        )
    )
    title_in_markdown = bool(
        expected_title
        and expected_title in normalize_identity_title(markdown)
    )
    if not (doi_in_markdown or title_in_markdown):
        return False, "unpaywall_identity_mismatch"
    return True, ""


def retrieve_unpaywall_pdf(
    doi: str,
    candidate_title: str,
) -> tuple[str | None, str]:
    """Récupère et valide le dernier recours PDF fourni par Unpaywall."""
    lookup = fetch_unpaywall(doi)
    lookup_reason = lookup.get("reason", "")
    if lookup_reason:
        return None, lookup_reason

    saw_refused = False
    saw_invalid = False
    saw_identity_mismatch = False
    for url in lookup.get("urls", []):
        pdf_path = download_pdf(url)
        if not pdf_path:
            saw_refused = True
            continue
        try:
            content, _ = _parse_pdf_file(
                pdf_path, "PDF parsé avec pymupdf4llm (Unpaywall)"
            )
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
        if not content:
            saw_invalid = True
            continue
        identity_ok, identity_reason = validate_unpaywall_identity(
            lookup, content, doi, candidate_title
        )
        if not identity_ok:
            saw_identity_mismatch = True
            continue
        return content, "PDF parsé avec pymupdf4llm (Unpaywall)"

    if saw_identity_mismatch:
        return None, "unpaywall_identity_mismatch"
    if saw_invalid:
        return None, "unpaywall_invalid_document"
    if saw_refused:
        return None, "unpaywall_url_refused"
    return None, "unpaywall_invalid_document"


# ---------------------------------------------------------------------------
# Parsing réel (pymupdf4llm)
# ---------------------------------------------------------------------------

def parse_pdf_real(pdf_path: str) -> str:
    """
    Convertit un PDF en Markdown via pymupdf4llm.
    Nécessite : pip install pymupdf4llm (installé dans le venv hermes-synthesis)
    """
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(pdf_path)
    except ImportError:
        raise NotImplementedError(
            "pymupdf4llm n'est pas installé. "
            "pip install pymupdf4llm ou utilise --mock."
        )


# ---------------------------------------------------------------------------
# Mode mock — faux textes intégraux
# ---------------------------------------------------------------------------

MOCK_FULLTEXTS = {
    "10.1234/mock001": """# L'impact de l'intelligence artificielle sur la productivité des PME manufacturières

## Résumé
Cette étude examine l'effet de l'adoption de l'IA sur la productivité de 150 PME
du secteur manufacturier français sur une période de 2 ans (2022-2024).

## Méthodologie
Étude quantitative longitudinale. 150 PME (10-249 salariés) du secteur manufacturier
dans 3 régions françaises. Groupe traitement (82 PME ayant adopté au moins un outil
d'IA) vs groupe contrôle (68 PME sans IA).

## Résultats
- Gain de productivité moyen : **12%** sur 2 ans (p < 0.01)
- Les PME de 50-249 salariés bénéficient davantage (+15%) que les TPE (+8%)
- Les outils de computer vision montrent les gains les plus élevés (+18%)
- L'effet est plus marqué la 2e année, suggérant une courbe d'apprentissage

## Discussion
L'adoption de l'IA dans les PME manufacturières est associée à des gains de
productivité significatifs, mais hétérogènes selon la taille et le secteur.
Les politiques de soutien devraient cibler les TPE qui bénéficient moins
spontanément de ces technologies.

## Secteur
Manufacturier

## Type d'IA déployée
Computer vision, maintenance prédictive, optimisation de production

## Gain de productivité mesuré
12% sur 2 ans
""",

    "10.1234/mock003": """# Machine Learning et performance des TPE françaises : une étude empirique

## Résumé
Analyse quantitative de 200 TPE françaises (1-19 salariés) ayant déployé des
solutions de machine learning entre 2020 et 2024. L'étude mesure l'impact sur
le chiffre d'affaires et la rentabilité.

## Méthodologie
Étude par différence-de-différences. Données fiscales (FARE/ESANE) appariées
à une enquête ad-hoc sur l'adoption technologique. Période : 2019-2024.

## Résultats
- Augmentation du CA de **7%** en moyenne après adoption du ML
- Rentabilité : +2.3 points de marge nette
- Effet plus fort dans les services (+10%) que dans le commerce (+4%)
- 60% des TPE rapportent que le ML a amélioré leur prise de décision

## Discussion
Même à petite échelle, le ML génère des gains mesurables. Le frein principal
reste l'accès aux compétences : 70% des TPE ont externalisé le déploiement.

## Secteur
Services, commerce

## Type d'IA déployée
Machine learning (classification, recommandation, prédiction de demande)

## Gain de productivité mesuré
7% de CA, +2.3 points de marge nette
""",

    "10.1234/mock005": """# Les déterminants de l'adoption de l'IA dans les PME européennes

## Résumé
Enquête auprès de 800 PME dans 5 pays européens (France, Allemagne, Italie,
Espagne, Pays-Bas) sur les facteurs favorisant ou freinant l'adoption de l'IA.

## Méthodologie
Enquête par questionnaire (taux de réponse : 32%). Analyse par régression
logistique des déterminants d'adoption.

## Résultats
- **Freins principaux** : manque de compétences (68%), coût perçu (54%),
  incertitude sur le ROI (47%)
- **Facteurs favorisants** : présence d'un responsable numérique (OR=2.4),
  participation à un cluster/incubateur (OR=1.9), accompagnement public (OR=1.7)
- L'adoption varie fortement par pays : Pays-Bas (38%) > Allemagne (31%) >
  France (24%) > Espagne (22%) > Italie (18%)
- **Note** : étude descriptive, pas d'impact productivité mesuré directement

## Discussion
Les politiques publiques de soutien à l'adoption de l'IA dans les PME doivent
cibler prioritairement la formation et l'accompagnement de proximité.

## Secteur
Multi-sectoriel

## Type d'IA déployée
Tous types confondus

## Gain de productivité mesuré
Non mesuré (étude des déterminants, pas d'impact)
""",

    "10.1234/mock008": """# ChatGPT in the Workplace: Early Evidence from SMEs

## Abstract
Mixed-methods study of ChatGPT adoption in 50 UK SMEs across sectors,
assessing productivity impacts in knowledge work tasks.

## Methodology
50 SMEs (10-249 employees). Mixed methods: time diaries (n=200 employees),
semi-structured interviews (n=30 managers). Period: June-December 2023.

## Results
- **Time savings**: 27% reduction in time spent on writing tasks (emails, reports)
- **Quality**: self-reported improvement in output quality (72% of users)
- **Heterogeneity**: gains concentrated in marketing, HR, and admin functions
- **Risks**: 15% of users reported occasional factual errors in AI outputs
- Productivity gain in knowledge work: **estimated 14% overall**

## Discussion
ChatGPT adoption in SMEs shows promising productivity gains in knowledge work,
but requires human oversight for accuracy. The 14% gain should be interpreted
as upper bound given the early-adopter bias in the sample.

## Sector
Multi-sector (services, tech, professional services)

## AI Type
Generative AI (LLM — ChatGPT)

## Productivity Gain
14% in knowledge work tasks
""",
}


def mock_fulltext(doi: str) -> str | None:
    """Retourne un faux texte intégral pour un DOI connu."""
    return MOCK_FULLTEXTS.get(doi)


# ---------------------------------------------------------------------------
# Journalisation
# ---------------------------------------------------------------------------

def log_decision(base: str, doi: str, decision: str, reason: str, run_id: str, *,
                 identity_type: str = "doi", source_id: str = "", oa_url: str = "",
                 actual_doi: str = ""):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run": run_id,
        "doc": doi,
        "stage": "fulltext",
        "decision": decision,
        "reason": reason,
    }
    if identity_type != "doi":
        entry.update({
            "identity_type": identity_type,
            "doi": actual_doi,
            "source_id": source_id,
            "oa_url": oa_url,
        })
    with open(f"{base}/decisions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _dropzone_pdf_path(base: str, doc: str, identity_type: str) -> str | None:
    dropzone_dir = f"{base}/inputs/pdfs"
    if not os.path.isdir(dropzone_dir):
        return None
    path = os.path.join(
        dropzone_dir,
        safe_document_filename(doc, identity_type) + ".pdf",
    )
    return path if os.path.isfile(path) else None


def _parse_pdf_file(pdf_path: str, success_reason: str) -> tuple[str | None, str]:
    try:
        content = parse_pdf_real(pdf_path)
    except Exception as exc:
        return None, f"{success_reason} — parsing échoué"
    if content and len(content) > 500:
        return content, success_reason
    length = len(content or "")
    return None, f"{success_reason} — texte inférieur à 500 caractères ({length})"


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str, use_mock: bool = False):
    base = f"/reviews/{rid}"
    decisions_path = f"{base}/decisions.jsonl"
    csv_path = f"{base}/candidates.csv"
    sources_dir = f"{base}/sources"
    run_id = datetime.now(timezone.utc).isoformat()

    if not os.path.exists(decisions_path):
        print(f"❌ {decisions_path} introuvable.", file=sys.stderr)
        sys.exit(1)

    # Identifie les articles inclus ; l'humain prime toujours sur la machine.
    with open(decisions_path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    included_documents, unknown_entries = _screening_documents(entries)

    manifest_path = f"{base}/manifest.json"
    manifest = json.load(open(manifest_path, encoding="utf-8"))

    if not included_documents:
        print("⚠️  Aucun article inclus trouvé dans decisions.jsonl.")
        manifest["journal_unknown_entries"] = unknown_entries
        prisma_path = f"{base}/prisma.json"
        if os.path.exists(prisma_path):
            with open(prisma_path, encoding="utf-8") as f:
                prisma = json.load(f)
        else:
            prisma = {}
        prisma["fulltext_assessed"] = 0
        prisma["fulltext_retrieved"] = 0
        prisma["fulltext_not_retrieved"] = 0
        prisma.pop("excluded_fulltext", None)
        with open(prisma_path, "w", encoding="utf-8") as f:
            json.dump(prisma, f, indent=2, ensure_ascii=False)
        manifest["stage"] = "fulltext_done"
        manifest["fulltext_success"] = 0
        manifest["fulltext_failed"] = 0
        manifest["updated"] = datetime.now(timezone.utc).isoformat()
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return

    # Charge candidates.csv pour les URLs OA et les identités de repli.
    candidates_by_identity: dict[str, dict] = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for _, identity_value in candidate_identity_values(row):
                    candidates_by_identity[identity_value] = row

    article_contexts = []
    pmcids = []
    for decision_entry in included_documents:
        doc = str(decision_entry.get("doc", "") or "").strip()
        candidate = candidates_by_identity.get(doc, {})
        identity = candidate_identity(candidate)
        identity_type = decision_entry.get("identity_type", "") or (identity[0] if identity else "")
        source_id = candidate.get("source_id", decision_entry.get("source_id", ""))
        oa_url = str(candidate.get("oa_url", "") or decision_entry.get("oa_url", "")).strip()
        actual_doi = candidate.get("doi", "") or decision_entry.get("doi", "")
        candidate_title = str(candidate.get("title", "") or "").strip()
        doi_safe = safe_document_filename(doc, identity_type)
        md_path = f"{sources_dir}/{doi_safe}.md"
        content = read_valid_markdown(md_path)
        pmcid = extract_pmcid_from_url(oa_url)
        if (
            pmcid
            and content is not None
            and not markdown_matches_candidate_title(content, candidate_title)
        ):
            content = None
        if pmcid and not use_mock and pmcid not in pmcids:
            pmcids.append(pmcid)
        article_contexts.append({
            "decision_entry": decision_entry,
            "doc": doc,
            "identity_type": identity_type,
            "source_id": source_id,
            "oa_url": oa_url,
            "actual_doi": actual_doi,
            "candidate_title": candidate_title,
            "doi_safe": doi_safe,
            "md_path": md_path,
            "content": content,
            "reused_existing": content is not None,
            "pmcid": pmcid,
        })

    try:
        pmc_markdown = {} if use_mock else fetch_pmc_xml(pmcids)
    except PmcFetchError as exc:
        print(f"❌ EFetch PMC groupé échoué : {exc}", file=sys.stderr)
        raise SystemExit(1)

    os.makedirs(sources_dir, exist_ok=True)
    manifest["journal_unknown_entries"] = unknown_entries
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    success = 0
    failed = 0

    print(f"📄 Récupération des textes intégraux pour {len(included_documents)} articles...")
    if use_mock:
        print("   (mode mock — textes simulés)")
    print()

    for context in article_contexts:
        doc = context["doc"]
        identity_type = context["identity_type"]
        source_id = context["source_id"]
        oa_url = context["oa_url"]
        actual_doi = context["actual_doi"]
        doi_safe = context["doi_safe"]
        md_path = context["md_path"]
        pmcid = context["pmcid"]
        candidate_title = context["candidate_title"]
        content = context["content"]
        reused_existing = context["reused_existing"]
        reason = ""
        identity_conflict = False

        if content is not None:
            reason = "Markdown existant valide réutilisé sans nouveau téléchargement"
        elif use_mock:
            content = mock_fulltext(doc)
            reason = "mock — texte simulé pour test"

        if content is None and not use_mock:
            if pmcid:
                pmc_record = pmc_markdown.get(pmcid)
                if pmc_record is not None:
                    identity_ok, identity_reason = validate_pmc_identity(
                        pmc_record, actual_doi, candidate_title
                    )
                    if not identity_ok:
                        identity_conflict = True
                        reason = f"Identité PMC refusée : {identity_reason}"
                    elif pmc_record.get("markdown"):
                        content = pmc_record["markdown"]
                        reason = f"XML PMC JATS parsé via EFetch ({pmcid})"
                    else:
                        reason = f"Corps XML PMC inexploitable ({pmcid})"
                else:
                    reason = f"Notice PMC absente de la réponse EFetch ({pmcid})"

            if content is None and not pmcid and oa_url:
                print(f"    📥 Téléchargement {oa_url[:60]}...")
                pdf_path = download_pdf(oa_url)
                if pdf_path:
                    content, reason = _parse_pdf_file(
                        pdf_path,
                        f"PDF parsé avec pymupdf4llm (OA: {oa_url[:50]})",
                    )
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
                else:
                    reason = "Téléchargement PDF OA échoué"

            if content is None and not identity_conflict:
                pdf_path = _dropzone_pdf_path(base, doc, identity_type)
                if pdf_path:
                    drop_content, drop_reason = _parse_pdf_file(
                        pdf_path, "PDF parsé depuis dropzone"
                    )
                    if drop_content:
                        content = drop_content
                        reason = drop_reason
                    elif reason:
                        reason += "; " + drop_reason
                    else:
                        reason = drop_reason
                elif reason:
                    reason += "; PDF non disponible dans la dropzone"
                else:
                    reason = "PDF non disponible (ni OA non-PMC, ni dropzone)"

            if content is None and not identity_conflict:
                unpaywall_content, unpaywall_reason = retrieve_unpaywall_pdf(
                    actual_doi, candidate_title
                )
                if unpaywall_content:
                    content = unpaywall_content
                    reason = unpaywall_reason
                elif unpaywall_reason:
                    reason = f"{reason}; {unpaywall_reason}" if reason else unpaywall_reason

        if content and len(content) > 500:
            if not reused_existing:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(content)
            print(f"  ✅ {doi_safe}.md  ({len(content)} caractères)")
            log_decision(
                base, doc, "retrieved", reason, run_id,
                identity_type=identity_type, source_id=source_id,
                oa_url=oa_url, actual_doi=actual_doi,
            )
            success += 1
        else:
            print(f"  ❌ {doc}  — {reason}")
            log_decision(
                base, doc, "retrieval_failed", reason, run_id,
                identity_type=identity_type, source_id=source_id,
                oa_url=oa_url, actual_doi=actual_doi,
            )
            failed += 1

    # Mise à jour prisma.json
    prisma_path = f"{base}/prisma.json"
    if os.path.exists(prisma_path):
        prisma = json.load(open(prisma_path, encoding="utf-8"))
    else:
        prisma = {}
    prisma["fulltext_assessed"] = success + failed
    prisma["fulltext_not_retrieved"] = failed
    prisma.pop("excluded_fulltext", None)
    # Les compteurs portent uniquement sur les articles inclus dans ce run.
    # Les anciens ou étrangers fichiers présents dans sources/ sont ignorés.
    prisma["fulltext_retrieved"] = success
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest["stage"] = "fulltext_done"
    manifest["fulltext_success"] = success
    manifest["fulltext_failed"] = failed
    manifest["updated"] = datetime.now(timezone.utc).isoformat()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Résumé
    print(f"\n📊 Résultat fulltext :")
    print(f"   ✅ Récupérés : {success}")
    print(f"   ❌ Échecs    : {failed}")
    print(f"   📁 Dossier   : {sources_dir}/")
    print(f"\n✅ Fulltext terminé")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fulltext.py '<json>'", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}", file=sys.stderr)
        sys.exit(1)

    rid = payload.get("id")
    if not rid:
        print("JSON invalide : 'id' requis.", file=sys.stderr)
        sys.exit(1)

    main(rid=rid, use_mock=payload.get("mock", False))
