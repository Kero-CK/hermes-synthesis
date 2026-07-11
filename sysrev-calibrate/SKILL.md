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
- Un gold set existe : `gold_set.csv` avec colonnes
  `title,abstract,doi,label,stratum,abstract_source`, où `label` vaut
  `include` ou `exclude`, `stratum` identifie la strate d'échantillonnage
  (`A`/`B`) et `abstract_source=none` signale l'absence d'abstract.
- 50-100 articles recommandés pour une calibration fiable

# Procédure

1. **Crée le gold set.** L'utilisateur étiquette manuellement 50-100 articles
   depuis `candidates.csv` (ou un export). Format :
   ```csv
   title,abstract,doi,label,stratum,abstract_source
   "Titre article","Abstract...","10.xxx","include","A","manual"
   "Autre titre","Abstract...","10.yyy","exclude","B","openalex"
   ```

2. Exécute :
   ```
   python3 ~/.hermes/skills/sysrev/sysrev-calibrate/scripts/calibrate.py '<json>'
   ```
   avec :
   ```json
   {"id": "ma-revue", "N_A": 13, "N_B": 1226, "n_A": 13, "n_B": 75}
   ```

3. Le script :
   - Fait passer chaque article du gold set dans le LLM (comme screen)
   - Compare décision LLM vs label humain pour différents seuils
   - Calcule recall, précision et F1 bruts et pondérés par strate
   - Calcule κ de Cohen sur l'échantillon brut uniquement
   - Produit les métriques par strate et l'analyse de sensibilité sans abstract
   - Suggère les seuils optimaux

4. Présente les résultats et les seuils recommandés.

# Métriques calculées

| Métrique | Interprétation |
|---|---|
| **Recall** | Proportion d'articles pertinents correctement inclus. **Priorité n°1.** |
| **Précision** | Proportion d'articles inclus qui sont vraiment pertinents. |
| **F1** | Moyenne harmonique recall/précision. |
| **κ de Cohen** | Accord IA vs humain corrigé du hasard. >0.6 = bon, >0.8 = excellent. |

## Pondération du plan stratifié

Chaque ligne contribue à la matrice de confusion avec le poids de sa strate :

```text
w_A = N_A / n_A
w_B = N_B / n_B
recall_w    = ΣwTP / (ΣwTP + ΣwFN)
precision_w = ΣwTP / (ΣwTP + ΣwFP)
```

Les valeurs par défaut sont `N_A=13`, `n_A=13`, `N_B=1226`, `n_B=75`,
soit `w_A=1` et `w_B≈16.347`. Le nombre de lignes observé dans chaque strate
doit correspondre à `n_A`/`n_B`. Si le gold set change légitimement, ajuster
ces paramètres dans le payload ; ne pas modifier le script.

Le rapport conserve simultanément les métriques brutes et pondérées. κ de
Cohen reste **strictement non pondéré**, car un κ pondéré entre strates n'est
pas défini ici. Les métriques A et B sont aussi publiées séparément ; la strate
A (`n=13` par défaut) porte un avertissement de petit effectif.

## Sensibilité aux abstracts absents

Pour les lignes dont `abstract_source=none`, le rapport recalcule les métriques
pondérées en forçant toutes leurs prédictions à `include`, puis à `exclude`.
Le point estimé et la plage numérique min/max sont enregistrés. Dans tous les
scénarios, `needs_manual` reste compté comme `exclude` selon la convention
conservatrice.

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
  "sampling": {"parameters": {"N_A": 13, "N_B": 1226, "n_A": 13, "n_B": 75}, "weights": {"A": 1.0, "B": 16.346667}},
  "default_metrics": {
    "raw": {"recall": 0.91, "precision": 0.83, "f1": 0.87, "cohens_kappa": 0.71},
    "weighted": {"recall": 0.88, "precision": 0.52, "f1": 0.65}
  },
  "per_stratum": {"A": {"n": 13}, "B": {"n": 75}},
  "abstract_source_none_sensitivity": {"n_abstract_source_none": 3, "range": {"recall": {"min": 0.84, "max": 0.91}}},
  "threshold_menu": [
    {
      "threshold_include": 0.85,
      "threshold_exclude": 0.35,
      "metrics_raw": {"recall": 0.82, "precision": 0.91},
      "metrics_weighted": {"recall": 0.78, "precision": 0.62},
      "ambiguous_pct": 3.0
    }
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

- `manifest.json` : métriques headline pondérées, métriques brutes et κ brut
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

- **Strate absente ou effectif incohérent** : le script échoue avant tout appel
  LLM. Le message affiche les effectifs observés et rappelle que `n_A`/`n_B`
  sont des paramètres du payload pour gérer une modification légitime du corpus.

# Critère de fin (Definition of Done)

- `calibration.json` existe avec recall pondéré ≥ 0.85 (sinon, revoir le prompt ou le gold set)
- Les seuils optimaux sont documentés
- `manifest.json` indique `stage = "calibrated"`
