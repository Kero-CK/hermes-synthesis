#!/usr/bin/env python3
"""Interactive labeling helper for blocD.csv (include/exclude), non-dev friendly."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent / "blocD.csv"


def ask(prompt: str) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if answer in {"i", "include"}:
            return "include"
        if answer in {"e", "exclude"}:
            return "exclude"
        print("  Réponse invalide — tape 'i' (include) ou 'e' (exclude).")


def main() -> int:
    with PATH.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 5:
        raise SystemExit(f"blocD.csv doit contenir 5 lignes, trouvé {len(rows)}")

    print("Labellisation du bloc D — 5 articles. Réponds 'i' (include) ou 'e' (exclude).\n")
    for index, row in enumerate(rows, start=1):
        print("=" * 72)
        print(f"[{index}/5] {row['title']}")
        print(f"DOI: {row['doi']}\n")
        print(row["abstract"])
        print()
        row["label"] = ask("Ton verdict (i/e) : ")
        print()

    with PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doi", "title", "abstract", "label"])
        writer.writeheader()
        writer.writerows(rows)

    labeled = sum(1 for row in rows if row["label"] in {"include", "exclude"})
    print(f"Enregistré : {labeled}/5 labels dans {PATH.name}. Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
