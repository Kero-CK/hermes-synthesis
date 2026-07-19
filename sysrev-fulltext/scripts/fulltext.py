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
import urllib.request
from datetime import datetime, timezone


KNOWN_JOURNAL_VOCABULARY = {
    "dedup": {"merge"},
    "screen_title_abstract": {"include", "exclude", "needs_manual"},
    "human_review": {"include", "exclude"},
    "screen_manual": {"include", "exclude"},  # alias historique
    "fulltext": {"retrieved", "retrieval_failed", "include", "needs_manual"},
    "screen_fulltext": {"include", "exclude", "needs_manual"},
    "human_review_fulltext": {"include", "exclude"},
    "extract": {"extracted", "not_found", "api_error", "rejected_citation", "include", "needs_manual"},
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
# Téléchargement de PDF
# ---------------------------------------------------------------------------

def download_pdf(url: str, timeout: int = 30) -> str | None:
    """
    Télécharge un PDF depuis une URL vers un fichier temporaire.
    Retourne le chemin du fichier temporaire, ou None en cas d'échec.
    """
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
    manifest["journal_unknown_entries"] = unknown_entries
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if not included_documents:
        print("⚠️  Aucun article inclus trouvé dans decisions.jsonl.")
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

    os.makedirs(sources_dir, exist_ok=True)

    success = 0
    failed = 0

    print(f"📄 Récupération des textes intégraux pour {len(included_documents)} articles...")
    if use_mock:
        print("   (mode mock — textes simulés)")
    print()

    for decision_entry in included_documents:
        doc = str(decision_entry.get("doc", "") or "").strip()
        candidate = candidates_by_identity.get(doc, {})
        identity = candidate_identity(candidate)
        identity_type = decision_entry.get("identity_type", "") or (identity[0] if identity else "")
        source_id = candidate.get("source_id", decision_entry.get("source_id", ""))
        oa_url = str(candidate.get("oa_url", "") or decision_entry.get("oa_url", "")).strip()
        actual_doi = candidate.get("doi", "") or decision_entry.get("doi", "")
        doi_safe = safe_document_filename(doc, identity_type)
        md_path = f"{sources_dir}/{doi_safe}.md"

        content = read_valid_markdown(md_path)
        reused_existing = content is not None
        reason = ""

        if content is not None:
            reason = "Markdown existant valide réutilisé sans nouveau téléchargement"
        elif use_mock:
            content = mock_fulltext(doc)
            reason = "mock — texte simulé pour test"
        elif oa_url:
            # Télécharger et parser le PDF OA
            print(f"    📥 Téléchargement {oa_url[:60]}...")
            pdf_path = download_pdf(oa_url)
            if pdf_path:
                try:
                    content = parse_pdf_real(pdf_path)
                    reason = f"PDF parsé avec pymupdf4llm (OA: {oa_url[:50]})"
                    os.unlink(pdf_path)  # Nettoie le fichier temporaire
                except Exception as e:
                    reason = f"Parsing échoué: {e}"
                    if os.path.exists(pdf_path):
                        os.unlink(pdf_path)
            else:
                reason = "Téléchargement PDF échoué"
        else:
            # Chercher dans la dropzone
            dropzone_dir = f"{base}/inputs/pdfs"
            pdf_path = None
            if os.path.isdir(dropzone_dir):
                doi_filename = safe_document_filename(doc, identity_type) + ".pdf"
                candidate = os.path.join(dropzone_dir, doi_filename)
                if os.path.exists(candidate):
                    pdf_path = candidate

            if pdf_path:
                try:
                    content = parse_pdf_real(pdf_path)
                    reason = "PDF parsé depuis dropzone"
                except Exception as e:
                    reason = f"Parsing dropzone échoué: {e}"
            else:
                reason = "PDF non disponible (ni OA téléchargeable, ni dropzone)"

        if content and len(content) <= 500:
            reason = f"Parsing quasi-vide ({len(content)} caractères — PDF scanné ou slides ?)"

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
