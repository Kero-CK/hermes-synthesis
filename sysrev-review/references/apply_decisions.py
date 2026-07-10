#!/usr/bin/env python3
"""Ancien exemple exécutable pour appliquer des décisions batch.

Référence de secours uniquement : le chemin supporté est désormais le mode
``decisions`` de ``scripts/review.py``, qui reconstruit aussi l'état résolu et
ses compteurs. Ne pas utiliser ce fichier comme procédure principale.
"""

import json, os
from datetime import datetime, timezone

base = "/reviews/<rid>"  # <- adapter

# Liste des décisions (ordre = ordre d'affichage de review.py)
decisions = [
    "include",  # 1.
    "exclude",  # 2.
    # ... compléter
]

# Charge les cas
cases = []
with open(f"{base}/to_review.jsonl", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            cases.append(json.loads(line.strip()))

assert len(decisions) == len(cases), f"{len(decisions)} décisions pour {len(cases)} cas"

# Journalise
ts = datetime.now(timezone.utc).isoformat()
counts = {"include": 0, "exclude": 0}
with open(f"{base}/decisions.jsonl", "a", encoding="utf-8") as f:
    for i, decision in enumerate(decisions):
        case = cases[i]
        entry = {
            "ts": ts,
            "doc": case.get("doi", ""),
            "stage": "human_review",
            "decision": decision,
            "score": case.get("score", 0),
            "model": "human (Cédric)",
            "actor": "human",
            "reason": "Décision batch du chercheur",
        }
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        counts[decision] += 1

# Vide to_review.jsonl
with open(f"{base}/to_review.jsonl", "w", encoding="utf-8") as f:
    pass

# Met à jour le compteur des cas restant à examiner
with open(f"{base}/prisma.json", encoding="utf-8") as f:
    prisma = json.load(f)
prisma["needs_manual_pending"] = max(
    0, prisma.get("needs_manual_pending", 0) - sum(counts.values())
)
with open(f"{base}/prisma.json", "w", encoding="utf-8") as f:
    json.dump(prisma, f, indent=2, ensure_ascii=False)

# Met à jour manifest.json
with open(f"{base}/manifest.json", encoding="utf-8") as f:
    manifest = json.load(f)
manifest["stage"] = "review_done"
manifest["human_reviewed"] = len(cases)
manifest["human_include"] = counts["include"]
manifest["human_exclude"] = counts["exclude"]
manifest["updated"] = datetime.now(timezone.utc).isoformat()
with open(f"{base}/manifest.json", "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

print(f"✅ {counts['include']} inclus, {counts['exclude']} exclus")
print(f"📋 to_review.jsonl vidé | manifest → review_done")
