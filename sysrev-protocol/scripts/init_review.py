#!/usr/bin/env python3
"""
init_review.py — Initialise le dossier de revue Hermes Synthesis.

Reçoit les champs du protocole en JSON (stdin ou argv[1]), crée le dossier
/reviews/<id>/ avec ses sous-dossiers, et écrit les fichiers d'état :
protocol.md, prisma.json, manifest.json.

Usage:
  python3 init_review.py '<json>'
  echo '<json>' | python3 init_review.py --stdin

Exemple:
  python3 init_review.py '{"id":"test-2026","question":"...","review_mode":"scoping","include":[...],"exclude":[...],"codebook":[...]}'

Aucune logique de jugement : pure mécanique de fichiers.
"""

import json
import os
import sys
from datetime import datetime, timezone


def main(payload: dict) -> str:
    """Crée le dossier de revue et retourne le chemin base."""
    rid = payload["id"]

    # Validation minimale du slug
    if not rid or " " in rid or "/" in rid:
        raise ValueError(f"Slug invalide : '{rid}'. Utilise des minuscules et des tirets.")

    base = f"/reviews/{rid}"

    # Création de l'arborescence
    os.makedirs(f"{base}/sources", exist_ok=True)
    os.makedirs(f"{base}/inputs/pdfs", exist_ok=True)

    # --- protocol.md (lisible par l'humain) ---
    lines = [
        f"# Protocole de revue — {rid}",
        "",
        f"**Type de revue :** {payload.get('review_mode', 'scoping')}",
        f"**Date de création :** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Question de recherche",
        "",
        payload.get("question", "(non renseignée)"),
        "",
        "## Critères d'inclusion",
        "",
    ]
    for c in payload.get("include", []):
        lines.append(f"- {c}")
    if not payload.get("include"):
        lines.append("*(aucun critère défini)*")

    lines.extend(["", "## Critères d'exclusion", ""])
    for c in payload.get("exclude", []):
        lines.append(f"- {c}")
    if not payload.get("exclude"):
        lines.append("*(aucun critère défini)*")

    lines.extend(["", "## Codebook d'extraction", ""])
    for v in payload.get("codebook", []):
        lines.append(f"- **{v['name']}** : {v.get('description', '')}")
    if not payload.get("codebook"):
        lines.append("*(aucune variable définie)*")

    lines.append("")

    with open(f"{base}/protocol.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # --- prisma.json (compteurs du flux) ---
    prisma = {
        "identified": 0,
        "after_dedup": 0,
        "screened": 0,
        "fulltext_assessed": 0,
        "excluded_fulltext": 0,
        "included": 0,
    }
    with open(f"{base}/prisma.json", "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # --- manifest.json (curseur d'état) ---
    manifest = {
        "id": rid,
        "stage": "protocol_done",
        "review_mode": payload.get("review_mode", "scoping"),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    with open(f"{base}/manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return base


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stdin":
        raw = sys.stdin.read()
    elif len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        print("Usage: init_review.py '<json>' | init_review.py --stdin", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}", file=sys.stderr)
        sys.exit(1)

    try:
        base = main(payload)
        print(f"✅ Revue initialisée : {base}")
    except ValueError as e:
        print(f"❌ Erreur : {e}", file=sys.stderr)
        sys.exit(1)
