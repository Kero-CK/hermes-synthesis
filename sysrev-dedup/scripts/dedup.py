#!/usr/bin/env python3
"""
dedup.py — Déduplique les articles candidats pour Hermes Synthesis.

Deux passes :
  1. DOI exact → fusion certaine
  2. Similarité de titre (ratio ≥ threshold) → fusion probabiliste

Sauvegarde le fichier original, journalise chaque fusion, met à jour
prisma.json et manifest.json. Stdlib uniquement — zéro dépendance.

Usage:
  python3 dedup.py '<json>'

JSON attendu:
  {"id": "ma-revue", "threshold": 0.85}
"""

import csv
import difflib
import json
import os
import shutil
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Normalisation des titres pour la comparaison fuzzy
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """Normalise un titre pour la comparaison : minuscules, sans ponctuation."""
    return "".join(c.lower() for c in title if c.isalnum() or c.isspace()).strip()


# ---------------------------------------------------------------------------
# Similarité entre deux titres
# ---------------------------------------------------------------------------

def title_similarity(a: str, b: str) -> float:
    """Ratio de similarité entre deux titres normalisés (0.0–1.0)."""
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


# ---------------------------------------------------------------------------
# Choix de la meilleure ligne à conserver lors d'une fusion
# ---------------------------------------------------------------------------

def score_row(row: dict) -> int:
    """Score heuristique : ligne la plus complète = la meilleure.
    Critères : abstract présent (3 pts), oa_url présent (2 pts), année récente."""
    score = 0
    if row.get("abstract", "").strip():
        score += 3
    if row.get("oa_url", "").strip():
        score += 2
    try:
        score += int(row.get("year", 0))
    except (ValueError, TypeError):
        pass
    return score


def pick_best(rows: list[dict]) -> dict:
    """Parmi un groupe de doublons, choisit la ligne la plus complète."""
    return max(rows, key=score_row)


# ---------------------------------------------------------------------------
# Log d'audit
# ---------------------------------------------------------------------------

def log_decision(base: str, kept_doi: str, merged_dois: list[str], reason: str):
    """Ajoute une ligne dans decisions.jsonl."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "doc": kept_doi,
        "stage": "dedup",
        "decision": "merge",
        "merged_dois": merged_dois,
        "reason": reason,
    }
    log_path = f"{base}/decisions.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str, threshold: float = 0.85):
    base = f"/reviews/{rid}"
    csv_path = f"{base}/candidates.csv"
    raw_path = f"{base}/candidates_raw.csv"

    if not os.path.exists(csv_path):
        print(f"❌ {csv_path} introuvable. Lance d'abord la skill search.", file=sys.stderr)
        sys.exit(1)

    # Chargement
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    original_count = len(rows)
    if original_count == 0:
        print("⚠️  candidates.csv est vide, rien à dédupliquer.")
        return

    # Backup
    shutil.copy2(csv_path, raw_path)
    print(f"📋 Backup : {raw_path} ({original_count} lignes)")

    # --- Passe 1 : DOI exact ---
    doi_groups: dict[str, list[dict]] = {}
    for r in rows:
        doi = r.get("doi", "").strip()
        if doi:
            doi_groups.setdefault(doi, []).append(r)

    pass1_removed = 0
    for doi, group in doi_groups.items():
        if len(group) > 1:
            best = pick_best(group)
            merged_dois = [doi]
            log_decision(base, doi, merged_dois, "DOI exact match")
            # Supprime les doublons de rows
            for dup in group:
                if dup is not best:
                    rows.remove(dup)
                    pass1_removed += 1

    # --- Passe 2 : similarité de titre ---
    pass2_removed = 0
    i = 0
    while i < len(rows):
        j = i + 1
        while j < len(rows):
            sim = title_similarity(rows[i]["title"], rows[j]["title"])
            if sim >= threshold:
                best = pick_best([rows[i], rows[j]])
                worst = rows[j] if best is rows[i] else rows[i]
                log_decision(
                    base,
                    best.get("doi", "sans-doi"),
                    [
                        rows[i].get("doi", "sans-doi"),
                        rows[j].get("doi", "sans-doi"),
                    ],
                    f"titre similaire (ratio={sim:.3f})",
                )
                if worst is rows[i]:
                    rows[i] = rows[j]  # garde la ligne j, supprime i
                rows.pop(j)
                pass2_removed += 1
                # Re-teste depuis le début car la liste a changé
                j = i + 1
            else:
                j += 1
        i += 1

    total_removed = pass1_removed + pass2_removed
    final_count = len(rows)

    # Réécriture de candidates.csv dédupliqué
    cols = [
        "title", "doi", "year", "abstract", "oa_url", "pdf_status",
        "source", "query", "date",
    ]
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
    prisma["after_dedup"] = final_count
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest_path = f"{base}/manifest.json"
    manifest = json.load(open(manifest_path, encoding="utf-8"))
    manifest["stage"] = "dedup_done"
    manifest["dedup_threshold"] = threshold
    manifest["dedup_removed"] = total_removed
    manifest["updated"] = datetime.now(timezone.utc).isoformat()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Rapport
    print(f"\n📊 Résultat déduplication :")
    print(f"   Avant          : {original_count}")
    print(f"   DOI exact      : -{pass1_removed}")
    print(f"   Titre similaire : -{pass2_removed}")
    print(f"   Après          : {final_count}")
    print(f"   Seuil titre    : {threshold}")
    print(f"\n✅ candidates.csv dédupliqué ({final_count} articles)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: dedup.py '<json>'", file=sys.stderr)
        print('  {"id": "ma-revue", "threshold": 0.85}', file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}", file=sys.stderr)
        sys.exit(1)

    rid = payload.get("id")
    threshold = float(payload.get("threshold", 0.85))

    if not rid:
        print("JSON invalide : 'id' requis.", file=sys.stderr)
        sys.exit(1)

    main(rid, threshold)
