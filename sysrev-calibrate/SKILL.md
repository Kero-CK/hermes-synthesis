---
name: sysrev-calibrate
description: >
  Calibre les seuils de screening en comparant les décisions du LLM à un
  gold set étiqueté manuellement. Calcule recall, précision, F1 et κ de Cohen.
  Suggère les thresholds optimaux pour le screening. À utiliser APRÈS avoir
  câblé le LLM dans screen, sur un échantillon de 50-100 articles étiquetés.
inputs:
  - /reviews/<id>/gold_set.csv (articles étiquetés manuellement)
  - /reviews/<id>/protocol.md (critères)
  - /reviews/<id>/manifest.json
outputs:
  - /reviews/<id>/calibration.json (métriques + seuils suggérés)
  - manifest.json mis à jour
requires:
  env: [LLM_API_ENDPOINT, LLM_API_KEY]
  tools: [terminal]
  scripts: [scripts/calibrate.py]
---

# Objectif

Mesurer la performance du screening LLM contre un gold set étiqueté par
l'humain, et déterminer les seuils optimaux (threshold_include,
threshold_exclude) qui maximisent le recall tout en gardant une précision
acceptable.

**Pourquoi c'est indispensable :** sans calibration, les seuils 0.75/0.25
sont arbitraires. Avec calibration, ils sont fondés sur des données réelles
et spécifiques à ta discipline.

# Pré-conditions

- Le LLM est câblé dans `sysrev-screen` (LLM_API_ENDPOINT + LLM_API_KEY)
- Un gold set existe : `gold_set.csv` avec colonnes `title,abstract,doi,label`
  où `label` = `include` ou `exclude` (décision humaine)
- 50-100 articles recommandés pour une calibration fiable

# Procédure

1. **Crée le gold set.** L'utilisateur étiquette manuellement 50-100 articles
   depuis `candidates.csv` (ou un export). Format :
   ```csv
   title,abstract,doi,label
   "Titre article","Abstract...","10.xxx","include"
   "Autre titre","Abstract...","10.yyy","exclude"
   ```

2. Exécute :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-calibrate/scripts/calibrate.py '<json>'
   ```
   avec :
   ```json
   {"id": "ma-revue"}
   ```

3. Le script :
   - Fait passer chaque article du gold set dans le LLM (comme screen)
   - Compare décision LLM vs label humain pour différents seuils
   - Calcule recall, précision, F1, κ de Cohen
   - Suggère les seuils optimaux

4. Présente les résultats et les seuils recommandés.

# Métriques calculées

| Métrique | Interprétation |
|---|---|
| **Recall** | Proportion d'articles pertinents correctement inclus. **Priorité n°1.** |
| **Précision** | Proportion d'articles inclus qui sont vraiment pertinents. |
| **F1** | Moyenne harmonique recall/précision. |
| **κ de Cohen** | Accord IA vs humain corrigé du hasard. >0.6 = bon, >0.8 = excellent. |

# Règles

- **Le script ne décide PAS.** Il présente un menu de compromis. C'est le
  chercheur qui choisit son seuil en fonction de sa discipline et de sa
  tolérance au risque.
- **Gold set représentatif.** Mélanger des cas clairs ET ambigus. Un gold set
  composé uniquement de cas évidents donne une fausse confiance.
- **Gold set externe.** Le gold set NE doit PAS être un sous-ensemble de
  `candidates.csv` déjà screené (risque de data leakage).

# Sortie — calibration.json + menu

```json
{
  "n_samples": 47,
  "default_metrics": {"recall": 0.91, "precision": 0.83, "f1": 0.87, "cohens_kappa": 0.71},
  "threshold_menu": [
    {"threshold_include": 0.85, "recall": 0.82, "precision": 0.91, "ambiguous_pct": 3.0},
    {"threshold_include": 0.80, "recall": 0.87, "precision": 0.88, "ambiguous_pct": 5.0},
    {"threshold_include": 0.75, "recall": 0.91, "precision": 0.83, "ambiguous_pct": 9.0},
    {"threshold_include": 0.70, "recall": 0.94, "precision": 0.78, "ambiguous_pct": 14.0},
    {"threshold_include": 0.65, "recall": 0.97, "precision": 0.71, "ambiguous_pct": 22.0}
  ]
}
```

Le menu affiché dans le terminal :

```
   Seuil  |  Recall  |  Précision  |  Ambigus
   -------+----------+-------------+---------
   0.85   |    82%   |      91%    |     3% █
   0.80   |    87%   |      88%    |     5% █
   0.75   |    91%   |      83%    |     9% ███
   0.70   |    94%   |      78%    |    14% ████
   0.65   |    97%   |      71%    |    22% ███████

   💡 Recommandations :
     🔬 Médical          → 0.65 (recall max)
     📊 Sciences sociales → 0.75 (équilibré)
     📈 Veille business   → 0.85 (peu d'ambigus)

   ⚠️  Ces seuils ne sont PAS appliqués automatiquement.
```

# Journalisation

- `manifest.json` : `calibration = {recall, precision, kappa, thresholds}`
- `manifest.json` : `stage = "calibrated"`

# Pièges connus

- **Gold set non représentatif** : un gold set composé uniquement de cas ambigus
  (ceux que le LLM a classés `needs_manual`) donne des scores plombés (recall ~0%)
  car le LLM les trouve toujours ambigus. Le gold set DOIT mélanger des cas clairs
  (include/exclude) ET des cas ambigus, idéalement 50-100 articles avec un ratio
  include/exclude représentatif de la vraie population.

- **Labels `needs_manual` ignorés** : le script n'accepte que `include` ou `exclude`
  comme labels dans `gold_set.csv`. Les articles encore en `needs_manual` doivent
  être tranchés par l'humain AVANT d'être ajoutés au gold set.

# Critère de fin (Definition of Done)

- `calibration.json` existe avec recall ≥ 0.85 (sinon, revoir le prompt ou le gold set)
- Les seuils optimaux sont documentés
- `manifest.json` indique `stage = "calibrated"`
