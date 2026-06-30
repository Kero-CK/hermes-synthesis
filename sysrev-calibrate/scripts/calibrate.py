#!/usr/bin/env python3
"""
calibrate.py — Calibre les seuils de screening contre un gold set.

Lit gold_set.csv (articles étiquetés manuellement), fait évaluer chaque
article par le LLM, et détermine les seuils optimaux (threshold_include,
threshold_exclude) qui maximisent le recall.

Usage:
  python3 calibrate.py '<json>'

JSON attendu:
  {"id": "ma-revue"}

Gold set attendu:
  /reviews/<id>/gold_set.csv  (title, abstract, doi, label)
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Appel LLM (dupliqué de screen.py — sera mutualisé plus tard)
# ---------------------------------------------------------------------------

SCREENING_PROMPT = """You are a systematic review screening assistant. Evaluate whether an article meets inclusion criteria.

## INCLUSION CRITERIA
{include_criteria}

## EXCLUSION CRITERIA
{exclude_criteria}

Return ONLY JSON: {{"score": <0.0-1.0>, "reason": "<1-2 sentences>"}}
Score >= 0.75 = include, <= 0.25 = exclude, between = needs_manual.

<DOCUMENT>
Title: {title}
Abstract: {abstract}
</DOCUMENT>"""


def call_llm(prompt: str) -> dict | None:
    """Appelle l'API LLM. Retourne {"score": ..., "reason": ...} ou None."""
    import urllib.request
    import urllib.error

    endpoint = os.environ.get("LLM_API_ENDPOINT", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_SCREENING_MODEL", "deepseek-chat")

    if not endpoint or not api_key:
        return None

    url = f"{endpoint.rstrip('/')}/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Evaluate."}
        ],
        "temperature": 0.0,
        "max_tokens": 200,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        print(f"  ⚠️  LLM error: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Métriques
# ---------------------------------------------------------------------------

def compute_metrics(y_true: list[str], y_pred: list[str]) -> dict:
    """
    Calcule recall, précision, F1.
    y_true/y_pred : listes de "include" ou "exclude"
    """
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "include" and p == "include")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == "exclude" and p == "include")
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "include" and p == "exclude")
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == "exclude" and p == "exclude")

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # κ de Cohen
    n = len(y_true)
    p_o = (tp + tn) / n if n > 0 else 0  # accord observé
    p_include = ((tp + fp) / n) * ((tp + fn) / n) if n > 0 else 0
    p_exclude = ((fn + tn) / n) * ((fp + tn) / n) if n > 0 else 0
    p_e = p_include + p_exclude  # accord aléatoire
    kappa = (p_o - p_e) / (1 - p_e) if (1 - p_e) > 0 else 0.0

    return {
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "cohens_kappa": round(kappa, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def compute_threshold_menu(scores: list[float], y_true: list[str]) -> list[dict]:
    """
    Calcule recall, précision, F1 et % d'ambigus pour une gamme de seuils.
    Retourne une liste utilisable pour un menu de choix.
    """
    results = []
    for ti in [0.85, 0.80, 0.75, 0.70, 0.65]:
        te = ti - 0.50  # garder un écart fixe include/exclude
        preds = []
        ambiguous = 0
        for s in scores:
            if s >= ti:
                preds.append("include")
            elif s <= te:
                preds.append("exclude")
            else:
                preds.append("needs_manual")
                ambiguous += 1
        m = compute_metrics(y_true, [p if p != "needs_manual" else "exclude" for p in preds])
        results.append({
            "threshold_include": ti,
            "threshold_exclude": te,
            "recall": m["recall"],
            "precision": m["precision"],
            "f1": m["f1"],
            "ambiguous_pct": round(ambiguous / len(scores) * 100, 1),
        })
    return results


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str):
    base = f"/reviews/{rid}"
    gold_path = f"{base}/gold_set.csv"
    protocol_path = f"{base}/protocol.md"

    if not os.path.exists(gold_path):
        print(f"❌ {gold_path} introuvable.", file=sys.stderr)
        print("   Crée un fichier gold_set.csv avec colonnes: title,abstract,doi,label", file=sys.stderr)
        print("   label = 'include' ou 'exclude' (décision humaine)", file=sys.stderr)
        sys.exit(1)

    # Charge le gold set
    with open(gold_path, newline="", encoding="utf-8") as f:
        gold = list(csv.DictReader(f))

    if len(gold) < 10:
        print(f"⚠️  Seulement {len(gold)} articles dans le gold set. 50+ recommandés.", file=sys.stderr)

    # Charge les critères
    criteria_include: list[str] = []
    criteria_exclude: list[str] = []
    current_section = None
    if os.path.exists(protocol_path):
        with open(protocol_path, encoding="utf-8") as f:
            for line in f:
                if "Critères d'inclusion" in line:
                    current_section = "include"
                elif "Critères d'exclusion" in line:
                    current_section = "exclude"
                elif line.startswith("##") and current_section:
                    current_section = None
                elif current_section == "include" and line.startswith("- "):
                    criteria_include.append(line[2:].strip())
                elif current_section == "exclude" and line.startswith("- "):
                    criteria_exclude.append(line[2:].strip())

    inc_text = "\n".join(f"- {c}" for c in criteria_include) if criteria_include else "- (aucun)"
    exc_text = "\n".join(f"- {c}" for c in criteria_exclude) if criteria_exclude else "- (aucun)"

    # Évalue chaque article
    print(f"🧪 Calibration sur {len(gold)} articles du gold set...")
    print()

    scores: list[float] = []
    y_true: list[str] = []
    y_pred_hard: list[str] = []  # décision binaire avec seuils par défaut
    errors = 0

    for i, row in enumerate(gold, 1):
        title = row.get("title", "")
        abstract = row.get("abstract", "")
        label = row.get("label", "").strip().lower()

        if label not in ("include", "exclude"):
            print(f"  ⚠️  Ligne {i}: label invalide '{label}' — ignorée")
            continue

        prompt = SCREENING_PROMPT.format(
            include_criteria=inc_text,
            exclude_criteria=exc_text,
            title=title,
            abstract=abstract or "(pas d'abstract)",
        )

        result = call_llm(prompt)

        if result and "score" in result:
            score = float(result["score"])
            scores.append(score)
            y_true.append(label)
            # Décision binaire avec seuils par défaut
            if score >= 0.75:
                y_pred_hard.append("include")
            elif score <= 0.25:
                y_pred_hard.append("exclude")
            else:
                y_pred_hard.append("needs_manual")
            print(f"  [{i}/{len(gold)}] label={label:8s} score={score:.2f}  {title[:60]}...")
        else:
            errors += 1
            print(f"  [{i}/{len(gold)}] ❌ erreur LLM — article ignoré")

    if len(scores) < 5:
        print(f"\n❌ Pas assez d'évaluations réussies ({len(scores)}). Vérifie la config LLM.", file=sys.stderr)
        sys.exit(1)

    # Métriques avec seuils par défaut
    metrics = compute_metrics(y_true, y_pred_hard)

    # Menu de compromis
    menu = compute_threshold_menu(scores, y_true)

    # Calibration
    calibration = {
        "n_samples": len(scores),
        "n_errors": errors,
        "default_thresholds": {"include": 0.75, "exclude": 0.25},
        "default_metrics": metrics,
        "threshold_menu": menu,
    }

    cal_path = f"{base}/calibration.json"
    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, ensure_ascii=False)

    # Rapport — menu de compromis
    print(f"""
📊 Calibration sur {len(scores)} articles du gold set :

   Par défaut (0.75/0.25) :
     Recall : {metrics['recall']:.1%}  |  Précision : {metrics['precision']:.1%}
     F1 : {metrics['f1']:.1%}  |  κ Cohen : {metrics['cohens_kappa']:.2f}
""")

    print("   Menu de compromis :\n")
    print(f"   {'Seuil':>8} | {'Recall':>8} | {'Précision':>10} | {'Ambigus':>8}")
    print(f"   {'-'*8}-+-{'-'*8}-+-{'-'*10}-+-{'-'*8}")
    for row in menu:
        bar = "█" * int(row["ambiguous_pct"] / 3)
        print(f"   {row['threshold_include']:.2f}/{row['threshold_exclude']:.2f}  | {row['recall']:>7.0%}  | {row['precision']:>9.0%}  | {row['ambiguous_pct']:>5.0f}% {bar}")

    print(f"""
   💡 Recommandations par discipline :

     🔬 Médical (zéro risque)          → seuil 0.65  (recall max, quitte à avoir plus d'ambigus)
     📊 Sciences sociales (équilibré)  → seuil 0.75  (bon compromis recall/précision)
     📈 Veille business (peu d'ambigus) → seuil 0.85  (moins de bruit, assume d'en rater)

   ⚠️  Ces seuils ne sont PAS appliqués automatiquement.
      C'est toi qui choisis en fonction de ta discipline et de ta tolérance au risque.

   📁 {cal_path}
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: calibrate.py '<json>'", file=sys.stderr)
        print('  {"id": "ma-revue"}', file=sys.stderr)
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

    main(rid=rid)
