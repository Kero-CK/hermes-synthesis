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
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**2. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_039`
- DOI: `10.1038/s41746-024-01083-y`
- Title: Evaluating large language models as agents in the clinic
- Citation [S1] : « Recent developments in large language models (LLMs) have unlocked opportunities for healthcare, from information synthesis to clinical decision support. »
- Citation [S2] : « These LLMs are not just capable of modeling language, but can also act as intelligent “agents” that interact with stakeholders in open-ended conversations and even influence clinical decision-making. »
- Raison du modèle : The article reports a domain application (healthcare) of LLM agents without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**3. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_040`
- DOI: `10.1109/tdsc.2024.3372777`
- Title: PrivacyAsst: Safeguarding User Privacy in Tool-Using Large Language Model Agents
- Citation [S4] : « we present PrivacyAsst, the first privacy-preserving framework tailored for tool-using LLM agents »
- Raison du modèle : The article reports a domain application (privacy-preserving LLM agents) without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**4. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_033`
- DOI: `10.48550/arxiv.2308.11432`
- Title: A Survey on Large Language Model based Autonomous Agents
- Citation [S7] : « Then, we present a comprehensive overview of the diverse applications of LLM-based autonomous agents in the fields of social science, natural science, and engineering. »
- Raison du modèle : The article reviews applications without describing the prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**5. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
- Case: `gold_036`
- DOI: `10.1057/s41599-024-03611-3`
- Title: Large language models empowered agent-based modeling and simulation: a survey and perspectives
- Citation [S6] : « we provide a comprehensive overview of the recent works of large language model-empowered agent-based modeling and simulation in multiple scenarios, which can be divided into four domains: cyber, physical, social, and hybrid »
- Raison du modèle : The abstract reports on domain applications without describing any prompt method in actionable detail.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## I1_PROMPT_TECHNIQUE

**6. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_031`
- DOI: `10.1145/3641289`
- Title: A Survey on Evaluation of Large Language Models
- Citation [S4] : « this paper presents a comprehensive review of these evaluation methods for LLMs »
- Raison du modèle : The paper is a survey of evaluation methods, not a description of a concrete prompt-engineering operation.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**7. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_033`
- DOI: `10.48550/arxiv.2308.11432`
- Title: A Survey on Large Language Model based Autonomous Agents
- Citation [T] : « A Survey on Large Language Model based Autonomous Agents »
- Raison du modèle : The article is a survey and does not describe or propose any concrete prompt-engineering operation.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**8. I1_PROMPT_TECHNIQUE = not_met**
- Case: `gold_039`
- DOI: `10.1038/s41746-024-01083-y`
- Title: Evaluating large language models as agents in the clinic
- Citation [T] : « Evaluating large language models as agents in the clinic »
- Citation [S4] : « These evaluation frameworks, which we refer to as “Artificial Intelligence Structured Clinical Examinations” (“AI-SCE”), can draw from comparable technologies where machines operate with varying degrees of self-governance, such as self-driving cars, in dynamic environments with multiple stakeholders. »
- Raison du modèle : The title and abstract focus on evaluating LLM agents, not on describing or proposing a concrete prompt-engineering operation. The article discusses evaluation frameworks, not how to construct, structure, or constrain prompts.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## I4_PRACTITIONER

**9. I4_PRACTITIONER = not_met**
- Case: `gold_031`
- DOI: `10.1145/3641289`
- Title: A Survey on Evaluation of Large Language Models
- Citation [S4] : « this paper presents a comprehensive review of these evaluation methods for LLMs »
- Raison du modèle : The paper does not describe a technique applicable by a practitioner through prompts; it reviews evaluation methods.
- Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## Synthèse Phase 2

| # | Critère | DOI | Verdict |
|---|---|---|---|
| 1 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.48550/arxiv.2309.07864 | À remplir |
| 2 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1038/s41746-024-01083-y | À remplir |
| 3 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1109/tdsc.2024.3372777 | À remplir |
| 4 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.48550/arxiv.2308.11432 | À remplir |
| 5 | E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 10.1057/s41599-024-03611-3 | À remplir |
| 6 | I1_PROMPT_TECHNIQUE | 10.1145/3641289 | À remplir |
| 7 | I1_PROMPT_TECHNIQUE | 10.48550/arxiv.2308.11432 | À remplir |
| 8 | I1_PROMPT_TECHNIQUE | 10.1038/s41746-024-01083-y | À remplir |
| 9 | I4_PRACTITIONER | 10.1145/3641289 | À remplir |

### Résumé par critère

| Critère | Échantillon | Confirmés | Refusés | Allowlist après vérification |
|---|---:|---:|---:|---|
| E1_NO_ACTIONABLE_TECHNIQUE | 0 |  |  |  |
| E2_MODEL_TRAINING_ONLY | 0 |  |  |  |
| E4_APPLICATION_WITHOUT_PROMPT_DETAIL | 5 |  |  |  |
| E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE | 0 |  |  |  |
| I1_PROMPT_TECHNIQUE | 3 |  |  |  |
| I4_PRACTITIONER | 1 |  |  |  |
