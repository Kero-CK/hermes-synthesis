#!/usr/bin/env python3
"""
review.py — Formate les cas ambigus pour la review batch, et applique
les décisions humaines une fois rendues.

Mode affichage (sans "decisions") : lit to_review.jsonl et candidates.csv,
et affiche une liste lisible que le chercheur peut traiter en une seule fois.

Mode apply (avec "decisions") : enregistre les décisions humaines dans
decisions.jsonl, met à jour prisma.json / manifest.json, et vide
to_review.jsonl.

Usage:
  python3 review.py '<json>'

JSON attendu (affichage):
  {"id": "ma-revue"}

JSON attendu (apply) :
  {"id": "ma-revue", "decisions": {"<doi_ou_index>": "include|exclude", ...}}
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone


def resolve_screening_decisions(entries: list[dict]) -> dict[str, str]:
    """Résout l'éligibilité finale avec priorité aux décisions humaines."""
    machine: dict[str, str] = {}
    human: dict[str, str] = {}
    for entry in entries:
        doc = entry.get("doc", "")
        decision = entry.get("decision")
        stage = entry.get("stage")
        if not doc or decision not in ("include", "exclude"):
            continue
        if stage in ("human_review", "screen_manual"):
            human[doc] = decision
        elif stage == "screen_title_abstract":
            machine[doc] = decision
    return {doc: human.get(doc, decision) for doc, decision in machine.items()} | human


def apply_decisions(rid: str, decisions: dict):
    """Persiste les décisions humaines sur des cas ambigus."""
    base = f"/reviews/{rid}"
    review_path = f"{base}/to_review.jsonl"
    decisions_path = f"{base}/decisions.jsonl"
    prisma_path = f"{base}/prisma.json"
    manifest_path = f"{base}/manifest.json"

    if not os.path.exists(review_path):
        print("✅ Aucun cas ambigu — rien à appliquer.")
        return

    cases = []
    with open(review_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line.strip()))

    if not cases:
        print("✅ Aucun cas ambigu — rien à appliquer.")
        return

    cases_by_doi = {c.get("doi"): c for c in cases if c.get("doi")}

    existing_entries = []
    if os.path.exists(decisions_path):
        with open(decisions_path, encoding="utf-8") as f:
            existing_entries = [json.loads(line) for line in f if line.strip()]
    latest_human: dict[str, str] = {}
    for entry in existing_entries:
        if entry.get("stage") in ("human_review", "screen_manual"):
            if entry.get("doc") and entry.get("decision") in ("include", "exclude"):
                latest_human[entry["doc"]] = entry["decision"]

    now = datetime.now(timezone.utc).isoformat()
    entries = []
    included_manual = 0
    excluded_manual = 0
    handled = 0

    for key, decision in decisions.items():
        if decision not in ("include", "exclude"):
            print(f"⚠️  Décision invalide pour '{key}' : {decision!r} (ignorée)", file=sys.stderr)
            continue

        case = cases_by_doi.get(key)
        if case is None:
            try:
                idx = int(key) - 1
                if 0 <= idx < len(cases):
                    case = cases[idx]
            except ValueError:
                pass
        if case is None:
            print(f"⚠️  Cas introuvable pour la clé '{key}' (ignorée)", file=sys.stderr)
            continue

        doc = case.get("doi", "")
        handled += 1
        if doc and latest_human.get(doc) == decision:
            print(f"⚠️  Décision humaine déjà journalisée pour {doc} — rejeu ignoré")
            continue

        entries.append({
            "ts": now,
            "run": now,
            "doc": doc,
            "stage": "human_review",
            "decision": decision,
            "score": case.get("score", ""),
            "model": "human",
            "actor": "human",
            "reason": case.get("reason", "décision humaine via review apply"),
        })
        if decision == "include":
            included_manual += 1
        else:
            excluded_manual += 1
        if doc:
            latest_human[doc] = decision

    if not handled:
        print("⚠️  Aucune décision valide à appliquer.")
        return

    with open(decisions_path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    all_entries = existing_entries + entries
    final_decisions = resolve_screening_decisions(all_entries)
    remaining_cases = [
        case for case in cases
        if not case.get("doi") or case.get("doi") not in latest_human
    ]

    # Mise à jour prisma.json depuis l'état final du journal
    prisma = json.load(open(prisma_path, encoding="utf-8")) if os.path.exists(prisma_path) else {}
    prisma["included"] = sum(1 for decision in final_decisions.values() if decision == "include")
    prisma["needs_manual_pending"] = len(remaining_cases)
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest = json.load(open(manifest_path, encoding="utf-8")) if os.path.exists(manifest_path) else {"id": rid}
    manifest["stage"] = "review_done"
    manifest["manual_included"] = sum(1 for decision in latest_human.values() if decision == "include")
    manifest["manual_excluded"] = sum(1 for decision in latest_human.values() if decision == "exclude")
    manifest["updated"] = now
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Reconstruit la file avec les cas sans décision humaine finale
    with open(review_path, "w", encoding="utf-8") as f:
        for case in remaining_cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"✅ {len(entries)} nouvelle(s) décision(s) : {included_manual} inclus, {excluded_manual} exclus.")
    print(f"   to_review.jsonl reconstruit — {len(remaining_cases)} cas restant(s).")


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

    if "decisions" in payload:
        apply_decisions(rid, payload["decisions"])
    else:
        main(rid)
