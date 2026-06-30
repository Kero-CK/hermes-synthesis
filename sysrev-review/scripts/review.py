#!/usr/bin/env python3
"""
review.py — Formate les cas ambigus pour la review batch.

Lit to_review.jsonl et candidates.csv, et affiche une liste lisible
que le chercheur peut traiter en une seule fois.

Usage:
  python3 review.py '<json>'

JSON attendu:
  {"id": "ma-revue"}
"""

import csv
import json
import os
import sys


def main(rid: str):
    base = f"/reviews/{rid}"
    review_path = f"{base}/to_review.jsonl"
    csv_path = f"{base}/candidates.csv"

    if not os.path.exists(review_path):
        print("✅ Aucun cas ambigu — le screening est terminé.")
        return

    # Charge les cas ambigus
    cases = []
    with open(review_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line.strip()))

    if not cases:
        print("✅ Aucun cas ambigu — le screening est terminé.")
        return

    # Index des abstracts par DOI
    doi_to_abstract = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                doi = row.get("doi", "")
                if doi:
                    doi_to_abstract[doi] = row.get("abstract", "")

    print(f"🤔 {len(cases)} cas à trancher. Pour chacun, réponds include ou exclude :\n")

    for i, case in enumerate(cases, 1):
        title = case.get("title", "Article sans titre")
        score = case.get("score", "?")
        reason = case.get("reason", "")
        doi = case.get("doi", "")
        abstract = doi_to_abstract.get(doi, case.get("abstract", ""))[:250]

        print(f"{i}. {title}")
        print(f"   Score IA : {score}")
        if reason:
            print(f"   💬 {reason}")
        if abstract:
            print(f"   📄 {abstract}...")
        print(f"   🟢 include | 🔴 exclude")
        print()

    print("---")
    print("Réponds avec la liste de tes décisions (une par ligne) :")
    print()
    for i in range(1, len(cases) + 1):
        print(f"{i}. [include/exclude]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: review.py '<json>'", file=sys.stderr)
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

    main(rid)
