# Phase 2 sample checklist — calibration Rule 3

Results directory: `results\20260715T161454171501Z`

Human verification is required for every sampled hard-fail below. A single REFUSÉ removes the criterion from the allowlist until v2.

Sampling rule: Règle 3 (vérification humaine échantillonnée) : pour chaque X encore qualifié, échantillon d'au plus 5 instances de hard-fail sur des records exclude avec assessment valide, hors les 7 DOI du micro-test (déjà vérifiés en phase 2) ; sélection déterministe par tri croissant de sha256(doi_minuscule + ":" + criterion_id). Exigence : 100 % de CONFIRMÉ sur l'échantillon — un seul REFUSÉ retire X de la allowlist jusqu'au v2.

## E4_APPLICATION_WITHOUT_PROMPT_DETAIL

**1. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_038`
- DOI: `10.48550/arxiv.2309.07864`
- Title: The Rise and Potential of Large Language Model Based Agents: A Survey
- Citation [S10] : « Subsequently, we explore the extensive applications of LLM-based agents in three aspects: single-agent scenarios, multi-agent scenarios, and human-agent cooperation. »
- Raison du modèle : The abstract reports domain applications but does not describe the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Survey multi-domain d’agents LLM, pas *une* application domaine d’un LLM. S10 = revue d’applications (single/multi/human-agent), pas un paper d’application sans détail de prompt. Le hard-fail correct ici est E5 (et E1) ; E4 est sur-appliqué. Aligné avec l’interprétation micro-test du même genre (survey d’applications → E4 non retenu).

**2. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_039`
- DOI: `10.1038/s41746-024-01083-y`
- Title: Evaluating large language models as agents in the clinic
- Citation [S1] : « Recent developments in large language models (LLMs) have unlocked opportunities for healthcare, from information synthesis to clinical decision support. »
- Citation [S2] : « These LLMs are not just capable of modeling language, but can also act as intelligent “agents” that interact with stakeholders in open-ended conversations and even influence clinical decision-making. »
- Raison du modèle : The article reports a domain application (healthcare) of LLM agents without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Contribution = cadres d’*évaluation* clinique (AI-SCE, S3–S4), pas le report d’une application LLM au domaine sans méthode de prompt. Le cadre healthcare est un contexte, pas une « domain application » au sens E4. E1 (pas de technique PE) / perspective d’évaluation sont les bons motifs d’exclude.

**3. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_040`
- DOI: `10.1109/tdsc.2024.3372777`
- Title: PrivacyAsst: Safeguarding User Privacy in Tool-Using Large Language Model Agents
- Citation [S4] : « we present PrivacyAsst, the first privacy-preserving framework tailored for tool-using LLM agents »
- Raison du modèle : The article reports a domain application (privacy-preserving LLM agents) without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Paper systèmes / privacy (chiffrement homomorphe, shuffling d’attributs — S5–S7), pas une application domaine d’un LLM. La contribution n’est pas « on a appliqué un LLM à X sans détailler le prompt », c’est un framework de protection des requêtes. E1 est le bon hard-fail (pas de technique PE actionnable). E4 incorrect.

**4. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_033`
- DOI: `10.48550/arxiv.2308.11432`
- Title: A Survey on Large Language Model based Autonomous Agents
- Citation [S7] : « Then, we present a comprehensive overview of the diverse applications of LLM-based autonomous agents in the fields of social science, natural science, and engineering. »
- Raison du modèle : The article reviews applications without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Même DOI que le micro-test `holdout_exclude_3`, où le reasoner avait correctement mis E4=`not_met` (« survey covering multiple applications, not a report of a single domain application »). Overview multi-domaines ≠ domain application E4. E5/E1 suffisent. Incohérence modèle entre runs ; hard-fail E4 refusé.

**5. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_036`
- DOI: `10.1057/s41599-024-03611-3`
- Title: Large language models empowered agent-based modeling and simulation: a survey and perspectives
- Citation [S6] : « we provide a comprehensive overview of the recent works of large language model-empowered agent-based modeling and simulation in multiple scenarios, which can be divided into four domains: cyber, physical, social, and hybrid »
- Raison du modèle : The abstract reports on domain applications without describing any prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Survey multi-scénarios (cyber/physical/social/hybrid), pas une application domaine unique sans détail de prompt. Même pattern que #1 et #4. Hard-fail correct = E5 (+ E1), pas E4.

## I1_PROMPT_TECHNIQUE

**6. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_031`
- DOI: `10.1145/3641289`
- Title: A Survey on Evaluation of Large Language Models
- Citation [S4] : « this paper presents a comprehensive review of these evaluation methods for LLMs »
- Raison du modèle : The paper is a survey of evaluation methods, not a description of a concrete prompt-engineering operation.
- Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Preuve positive de genre + objet : review de méthodes d’*évaluation*, pas d’opération PE concrète (construire/structurer/contraindre des prompts). Aligné phase 2 micro-test (#8, surveys/reviews hors PE). Hard-fail I1 correct.

**7. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_033`
- DOI: `10.48550/arxiv.2308.11432`
- Title: A Survey on Large Language Model based Autonomous Agents
- Citation [T] : « A Survey on Large Language Model based Autonomous Agents »
- Raison du modèle : The article is a survey and does not describe or propose any concrete prompt-engineering operation.
- Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Titre + abstract (S5 « comprehensive survey ») établissent un survey d’agents LLM, sans aucune opération PE isolée. Genre survey = évidence positive que l’article ne propose pas une opération PE concrète au sens I1. Cohérent avec phase 2 sur les reviews/surveys exclude. (Note : le micro-test avait I1=`not_reported` sur ce DOI — `not_met` reste défendable ici via le signal de genre.)

**8. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_039`
- DOI: `10.1038/s41746-024-01083-y`
- Title: Evaluating large language models as agents in the clinic
- Citation [T] : « Evaluating large language models as agents in the clinic »
- Citation [S4] : « These evaluation frameworks, which we refer to as “Artificial Intelligence Structured Clinical Examinations” (“AI-SCE”), can draw from comparable technologies where machines operate with varying degrees of self-governance, such as self-driving cars, in dynamic environments with multiple stakeholders. »
- Raison du modèle : The title and abstract focus on evaluating LLM agents, not on describing or proposing a concrete prompt-engineering operation. The article discusses evaluation frameworks, not how to construct, structure, or constrain prompts.
- Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Contribution explicite = frameworks d’évaluation (AI-SCE), pas une opération PE. Le titre + S4 contredisent I1 (évaluation ≠ construct/structure/constrain de prompts). Hard-fail I1 correct.

## I4_PRACTITIONER

**9. I4_PRACTITIONER = not_met**
- Case: `gold_031`
- DOI: `10.1145/3641289`
- Title: A Survey on Evaluation of Large Language Models
- Citation [S4] : « this paper presents a comprehensive review of these evaluation methods for LLMs »
- Raison du modèle : The paper does not describe a technique applicable by a practitioner through prompts; it reviews evaluation methods.
- Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Absence de technique PE ⇒ I4 doit être **`not_reported`**, pas `not_met`. `not_met` exige une preuve positive que *la technique* n’est pas applicable sans training (ex. fine-tuning, prompt tuning). Ici il n’y a pas de technique à qualifier — le modèle confond « pas de technique practitioner » avec « technique non practitioner ». Mauvais hard-fail I4 (I1/E1/E5 suffisent pour ce paper).

---

## Synthèse Phase 2

| # | Critère | DOI | Verdict |
|---|---|---|---|
| 1 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.48550/arxiv.2309.07864 | **REFUSÉ** |
| 2 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1038/s41746-024-01083-y | **REFUSÉ** |
| 3 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1109/tdsc.2024.3372777 | **REFUSÉ** |
| 4 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.48550/arxiv.2308.11432 | **REFUSÉ** |
| 5 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1057/s41599-024-03611-3 | **REFUSÉ** |
| 6 | I1_PROMPT_TECHNIQUE | 10.1145/3641289 | **CONFIRMÉ** |
| 7 | I1_PROMPT_TECHNIQUE | 10.48550/arxiv.2308.11432 | **CONFIRMÉ** |
| 8 | I1_PROMPT_TECHNIQUE | 10.1038/s41746-024-01083-y | **CONFIRMÉ** |
| 9 | I4_PRACTITIONER | 10.1145/3641289 | **REFUSÉ** |

### Résumé par critère

| Critère | Échantillon | Confirmés | Refusés | Allowlist après vérification |
|---|---:|---:|---:|---|
| E1_NO_ACTIONABLE_TECHNIQUE | 0 | — | — | déjà disqualifié (R1) |
| E2_MODEL_TRAINING_ONLY | 0 | — | — | déjà not_qualified (R2) |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 5 | 0 | **5** | **retiré** (R3 : un REFUSÉ suffit ; ici 5/5) |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | 0 | — | — | déjà disqualifié (R1) |
| I1_PROMPT_TECHNIQUE | 3 | **3** | 0 | **conservé** (100 % CONFIRMÉ) |
| I4_PRACTITIONER | 1 | 0 | **1** | **retiré** (R3) |

### Allowlist finale (après Règle 3)

**`auto_excludable` retenu : `I1_PROMPT_TECHNIQUE` uniquement.**

Retirés par R3 :
- `E4_APPLICATION_WITHOUT_PROMPT_DETAIL` — sur-application aux surveys multi-domaines, aux papers d’évaluation, et aux frameworks non-PE (privacy/crypto).
- `I4_PRACTITIONER` — `not_met` abusif quand aucune technique n’est identifiée (devrait être `not_reported`).

### Implications

1. **E4** reste utile en micro-test sur de vraies applications domaine (IR ranking, embodied agents, PE healthcare) mais **n’est pas prêt pour l’auto-exclude** tant que le modèle le tire sur des surveys d’applications / systèmes privacy.
2. **I4** reste valide sur prompt-tuning / RLHF (phase 2 micro-test) mais l’unique instance calibration est un faux hard-fail → allowlist retirée jusqu’au v2.
3. **I1** passe R3 à 100 % sur l’échantillon (surveys/reviews d’éval hors PE).
4. Cible v2 : (a) resserrer E4 aux applications primaires d’un LLM à un domaine, exclure surveys multi-apps ; (b) I4=`not_reported` si I1 ∈ {not_met, not_reported} et aucune technique n’est citable ; (c) réduire le sur-usage de `not_met` pour simple absence.
