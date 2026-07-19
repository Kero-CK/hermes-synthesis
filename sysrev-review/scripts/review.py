#!/usr/bin/env python3
"""
review.py — Formate les cas ambigus pour la review batch, et applique
les décisions humaines une fois rendues.

Deux files HITL sont supportées via le champ "queue" :
  - "screening" (défaut) : cas ambigus du screening titre/abstract
    (to_review.jsonl, stage humain "human_review")
  - "fulltext" : cas ambigus du screening texte intégral
    (to_review_fulltext.jsonl, stage humain "human_review_fulltext")

Mode affichage (sans "decisions") : lit la file et candidates.csv,
et affiche une liste lisible que le chercheur peut traiter en une seule fois.

Mode apply (avec "decisions") : enregistre les décisions humaines dans
decisions.jsonl, met à jour prisma.json / manifest.json, et vide la file.

Usage:
  python3 review.py '<json>'

JSON attendu (affichage):
  {"id": "ma-revue"}
  {"id": "ma-revue", "queue": "fulltext"}

JSON attendu (apply) :
  {"id": "ma-revue", "decisions": {"<doi_ou_index>": "include|exclude", ...}}
  {"id": "ma-revue", "queue": "fulltext", "decisions": {...}}
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone


# Configuration des files HITL. "screening" conserve exactement le
# comportement historique ; "fulltext" applique la même mécanique au
# stage d'éligibilité texte intégral.
QUEUES = {
    "screening": {
        "review_file": "to_review.jsonl",
        "machine_stage": "screen_title_abstract",
        "human_stage": "human_review",
        "human_stages": ("human_review", "screen_manual"),  # alias historique
        "done_stage": "review_done",
        "manifest_included": "manual_included",
        "manifest_excluded": "manual_excluded",
    },
    "fulltext": {
        "review_file": "to_review_fulltext.jsonl",
        "machine_stage": "screen_fulltext",
        "human_stage": "human_review_fulltext",
        "human_stages": ("human_review_fulltext",),
        "done_stage": "review_fulltext_done",
        "manifest_included": "fulltext_manual_included",
        "manifest_excluded": "fulltext_manual_excluded",
    },
}


def case_identity(case: dict) -> tuple[str, str] | None:
    """Retourne l'identité stable d'un cas, sans jamais accepter une valeur vide."""
    if case.get("doc"):
        kind = case.get("identity_type", "") or "doc"
        if isinstance(case["doc"], str) and case["doc"].strip():
            return kind, case["doc"].strip()
        return None
    for kind in ("doi", "source_id", "oa_url"):
        raw_value = case.get(kind, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            return kind, value
    return None


def resolve_stage_decisions(entries: list[dict], machine_stage: str,
                            human_stages: tuple[str, ...]) -> dict[str, str]:
    """Résout la décision finale d'un stage avec priorité aux décisions humaines."""
    machine: dict[str, str] = {}
    human: dict[str, str] = {}
    for entry in entries:
        doc = entry.get("doc", "")
        decision = entry.get("decision")
        stage = entry.get("stage")
        if not doc or decision not in ("include", "exclude"):
            continue
        if stage in human_stages:
            human[doc] = decision
        elif stage == machine_stage:
            machine[doc] = decision
    return {doc: human.get(doc, decision) for doc, decision in machine.items()} | human


def resolve_screening_decisions(entries: list[dict]) -> dict[str, str]:
    """Résout l'éligibilité finale titre/abstract (compat historique)."""
    queue = QUEUES["screening"]
    return resolve_stage_decisions(entries, queue["machine_stage"], queue["human_stages"])


def apply_decisions(rid: str, decisions: dict, queue: str = "screening"):
    """Persiste les décisions humaines sur des cas ambigus."""
    if queue not in QUEUES:
        print(f"❌ Queue inconnue : {queue!r} (attendu : screening | fulltext)", file=sys.stderr)
        sys.exit(1)
    config = QUEUES[queue]

    base = f"/reviews/{rid}"
    review_path = f"{base}/{config['review_file']}"
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

    cases_by_identity = {
        identity[1]: case
        for case in cases
        if (identity := case_identity(case)) is not None
    }

    existing_entries = []
    if os.path.exists(decisions_path):
        with open(decisions_path, encoding="utf-8") as f:
            existing_entries = [json.loads(line) for line in f if line.strip()]
    latest_human: dict[str, str] = {}
    for entry in existing_entries:
        if entry.get("stage") in config["human_stages"]:
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

        case = cases_by_identity.get(key)
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

        identity = case_identity(case)
        if identity is None:
            print(
                f"❌ Cas sans identité pour la clé '{key}' : décision refusée.",
                file=sys.stderr,
            )
            continue
        identity_type, doc = identity
        handled += 1
        if doc and latest_human.get(doc) == decision:
            print(f"⚠️  Décision humaine déjà journalisée pour {doc} — rejeu ignoré")
            continue

        entry = {
            "ts": now,
            "run": now,
            "doc": doc,
            "stage": config["human_stage"],
            "decision": decision,
            "score": case.get("score", ""),
            "model": "human",
            "actor": "human",
            "reason": case.get("reason", "décision humaine via review apply"),
        }
        if identity_type != "doi":
            entry.update({
                "identity_type": identity_type,
                "doi": "",
                "source_id": case.get("source_id", ""),
                "oa_url": case.get("oa_url", ""),
            })
        entries.append(entry)
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
    final_decisions = resolve_stage_decisions(
        all_entries, config["machine_stage"], config["human_stages"]
    )
    remaining_cases = []
    for case in cases:
        identity = case_identity(case)
        if identity is None or identity[1] not in latest_human:
            remaining_cases.append(case)

    # Mise à jour prisma.json depuis l'état final du journal
    prisma = json.load(open(prisma_path, encoding="utf-8")) if os.path.exists(prisma_path) else {}
    final_included = sum(1 for decision in final_decisions.values() if decision == "include")
    if queue == "screening":
        prisma["included"] = final_included
        prisma["needs_manual_pending"] = len(remaining_cases)
    else:
        prisma["included_final"] = final_included
        prisma["excluded_fulltext_eligibility"] = sum(
            1 for decision in final_decisions.values() if decision == "exclude"
        )
        prisma["fulltext_review_pending"] = len(remaining_cases)
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest = json.load(open(manifest_path, encoding="utf-8")) if os.path.exists(manifest_path) else {"id": rid}
    manifest["stage"] = config["done_stage"]
    manifest[config["manifest_included"]] = sum(
        1 for decision in latest_human.values() if decision == "include"
    )
    manifest[config["manifest_excluded"]] = sum(
        1 for decision in latest_human.values() if decision == "exclude"
    )
    manifest["updated"] = now
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Reconstruit la file avec les cas sans décision humaine finale
    with open(review_path, "w", encoding="utf-8") as f:
        for case in remaining_cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"✅ {len(entries)} nouvelle(s) décision(s) : {included_manual} inclus, {excluded_manual} exclus.")
    print(f"   {config['review_file']} reconstruit — {len(remaining_cases)} cas restant(s).")


def main(rid: str, queue: str = "screening"):
    if queue not in QUEUES:
        print(f"❌ Queue inconnue : {queue!r} (attendu : screening | fulltext)", file=sys.stderr)
        sys.exit(1)
    config = QUEUES[queue]
    base = f"/reviews/{rid}"
    review_path = f"{base}/{config['review_file']}"
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

    # Index des abstracts par identité
    identity_to_abstract = {}
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for key in ("doi", "source_id", "oa_url"):
                    value = row.get(key, "")
                    if value:
                        identity_to_abstract[value] = row.get("abstract", "")

    label = "texte intégral" if queue == "fulltext" else "screening"
    print(f"🤔 {len(cases)} cas à trancher ({label}). Pour chacun, réponds include ou exclude :\n")

    for i, case in enumerate(cases, 1):
        title = case.get("title", "Article sans titre")
        score = case.get("score", "?")
        reason = case.get("reason", "")
        identity = case_identity(case)
        doc = identity[1] if identity is not None else ""
        abstract = identity_to_abstract.get(doc, case.get("abstract", ""))[:250]

        print(f"{i}. {title}")
        print(f"   Score IA : {score}")
        if reason:
            print(f"   💬 {reason}")
        if abstract:
            print(f"   📄 {abstract}...")
        if queue == "fulltext":
            print(f"   📖 Texte intégral : sources/ — relire avant de trancher")
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

    queue = payload.get("queue", "screening")
    if "decisions" in payload:
        apply_decisions(rid, payload["decisions"], queue=queue)
    else:
        main(rid, queue=queue)
