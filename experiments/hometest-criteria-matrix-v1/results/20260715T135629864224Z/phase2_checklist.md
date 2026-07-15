# Phase 2 — Vérification humaine des hard-fails (deepseek-reasoner, run 20260715T135629864224Z)

Pour chaque ligne : lis la citation, relis l'abstract si besoin, puis note CONFIRMÉ (le hard-fail est correct) ou REFUSÉ (le hard-fail est une erreur du modèle). Seuls les hard-fails d'assessments mécaniquement valides sont listés.

## fp_prompt_tuning — « Chain of Thought Prompt Tuning in Vision Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**1. I4_PRACTITIONER = not_met**
   - Citation [S5] : « chain of thought prompt tuning »
   - Raison du modèle : Prompt tuning involves training learned prompt parameters, not practitioner-accessible prompts; no statement indicates the prompts are discrete or manual.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Aligné avec la définition protocole (« prompt tuning » = paramètres appris, donc training). Aucune mention de prompts discrets/manuels/NL écrits par un humain. Hard-fail I4 correct.

**2. E2_MODEL_TRAINING_ONLY = met**
   - Citation [S5] : « chain of thought prompt tuning »
   - Raison du modèle : The article focuses on learned prompt parameters (prompt tuning) without a practitioner-usable prompting component.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Contribution centrale = prompt tuning (learned parameters). S7 évoque du CoT « prompting » multimodal, mais le cadre reste le tuning de paramètres, sans composante practitioner-only. Oracle primaire E2 validé.

## fp_agent_planning — « LLM-Planner: Few-Shot Grounded Planning for Embodied Agents with Large Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**3. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S1] : « using large language models (LLMs) as a planner for embodied agents that can follow natural language instructions to complete complex tasks in a visually-perceived environment. »
   - Citation [S3] : « propose a novel method, LLM-Planner, that harnesses the power of large language models to do few-shot planning for embodied agents. »
   - Raison du modèle : The article reports a domain application (embodied agents) of an LLM but does not describe the prompt method in actionable detail, as the prompt technique is not clearly specified.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Application domaine (agents embodied) claire ; aucun détail actionnable sur construction/structure de prompt. « Few-shot planning » = efficacité d’échantillon (données), pas few-shot prompting (Decision D). I2=not_reported → cohérent avec E4. (Oracle préférait I1/E1 ; E4 reste un hard-fail valide.)

## fp_ranking_evaluation — « Is ChatGPT Good at Search? Investigating Large Language Models as Re-Ranking Agents »
Label humain : exclude · Route phase 1 : needs_manual

**4. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « properly instructed LLMs can deliver competitive, even superior results »
   - Raison du modèle : The article discusses LLMs for ranking but does not describe an actionable prompt technique; 'properly instructed' is too vague.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : « properly instructed » ne décrit aucune opération PE concrète (structure, séquence, contrainte). I1=not_reported → cohérent avec E1.

**5. E3_BENCHMARK_ONLY = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « our experiments reveal that properly instructed LLMs can deliver competitive, even superior results »
   - Citation [S6] : « we collect a new test set called NovelEval »
   - Raison du modèle : The article presents a benchmark evaluation without a transferable prompt method or structure.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Abstract centré sur investigation expérimentale + NovelEval + benchmarks IR ; aucune méthode/structure de prompt transferable. Oracle primaire E3 validé. I2=not_reported → cohérent.

**6. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « properly instructed LLMs »
   - Raison du modèle : The article applies LLMs to the domain of IR re-ranking but does not describe the prompt method in actionable detail.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Application IR re-ranking sans détail actionnable de prompt. La distillation (S7) n’introduit pas non plus de technique PE. Cohérent avec I2=not_reported.

## state_title_only_prompt_tuning — « Chain of Thought Prompt Tuning in Vision Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**7. I4_PRACTITIONER = not_met**
   - Citation [T] : « Chain of Thought Prompt Tuning »
   - Raison du modèle : The phrase 'Prompt Tuning' indicates training of prompt parameters, which requires model training and is not applicable by a practitioner without training.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Title-only suffisant : « Prompt Tuning » = training de paramètres appris (glossaire protocole). Aucun abstract pour contredire. Hard-fail I4 correct.

## holdout_exclude_1 — « Prompt Engineering for Healthcare: Methodologies and Applications »
Label humain : exclude · Route phase 1 : needs_manual

**8. I1_PROMPT_TECHNIQUE = not_met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The abstract states it is a review, not a description of a concrete prompt-engineering operation.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Genre review explicite ; l’article ne propose/décrit pas une opération PE concrète, il annonce une synthèse. S1 = définition générale de la PE, pas une opération isolable. not_met justifié.

**9. I2_REPRODUCIBLE = not_met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The abstract does not expose an identifiable prompt structure or transferable method.
   - Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Statut incorrect. L’absence de structure identifiable ⇒ `not_reported`, pas `not_met`. Le protocole exige pour `not_met` un span qui *contredit* le critère ; « this review will introduce… » est seulement topique, pas une contradiction. Hard-fail I2 non fondé (le statut aurait dû être not_reported, non hard-fail).

**10. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The article is a review and does not propose or describe an actionable prompt technique.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Survey sans technique PE actionnable proposée. Cohérent avec I1=not_met (et le resterait aussi avec I1=not_reported).

**11. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S5] : « First, we will provide the development of prompt engineering and emphasize its significant contributions to healthcare natural language processing applications such as question-answering systems, text summarization, and machine translation. »
   - Raison du modèle : The abstract mentions domain applications without describing the prompt method in actionable detail.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Applications santé (QA, summarization, MT) citées sans détail de méthode prompt. La cohérence E4 exige I2 ∈ {not_met, not_reported} : même si I2 aurait dû être not_reported (#9), E4 reste valide.

**12. E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE = met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The article is a survey that does not expose an isolable and actionable prompt technique.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Review/survey explicite ; l’abstract n’isole aucune technique PE actionnable (E5 autorise les surveys qui en isolent — ce n’est pas le cas ici).

## holdout_exclude_2 — « Training language models to follow instructions with human feedback »
Label humain : exclude · Route phase 1 : needs_manual

**13. I1_PROMPT_TECHNIQUE = not_met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article focuses on fine-tuning the model using human feedback, not on describing a concrete prompt-engineering operation.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Contribution = fine-tuning / RLHF (S4–S6), pas une opération PE. Preuve positive que la méthode n’est pas du prompt engineering. Hard-fail I1 correct.

**14. I2_REPRODUCIBLE = not_met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article does not expose an identifiable prompt structure or method; it describes model training.
   - Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : Même erreur de statut que #9. Décrire du fine-tuning montre l’absence de structure de prompt, mais n’est pas une contradiction explicite de I2 → devrait être `not_reported` (pas hard-fail inclusion). Les autres hard-fails de ce papier suffisent pour l’exclusion.

**15. I4_PRACTITIONER = not_met**
   - Citation [S5] : « fine-tune GPT-3 using supervised learning »
   - Raison du modèle : The technique requires fine-tuning model weights, not applicable by a practitioner through prompts or inference-time orchestration.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : S5–S6 = supervised fine-tuning + RLHF sur les poids. Inapplicable par prompts seuls. Hard-fail I4 clair.

**16. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article discusses LLMs but proposes a training technique, not an actionable prompt technique.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Technique proposée = training d’alignement, pas une technique de prompt actionnable. Cohérent avec I1=not_met.

**17. E2_MODEL_TRAINING_ONLY = met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Citation [S5] : « fine-tune GPT-3 using supervised learning »
   - Raison du modèle : The article is solely about training/fine-tuning without a practitioner-usable prompting component.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Article entièrement sur fine-tuning + RLHF (InstructGPT). Les « prompts » cités sont des données de labellisation, pas une technique practitioner. E2 solide ; I4≠met → cohérent.

**18. E3_BENCHMARK_ONLY = met**
   - Citation [S8] : « outputs from the 1.3B parameter InstructGPT model are preferred to outputs from the 175B GPT-3 »
   - Raison du modèle : The article includes model evaluation and lacks a transferable prompt method.
   - Verdict humain : [ ] CONFIRMÉ  [x] REFUSÉ — note : E3 exige que l’article *soit* un benchmark / une évaluation de modèle sans méthode. Ici la contribution primaire est le training RLHF ; S8 n’est qu’un résultat d’évaluation secondaire. Avoir des résultats d’éval ≠ être un paper « benchmark only ». Hard-fail E3 incorrect (E2/E1/I4 suffisent).

## holdout_exclude_3 — « A Survey on Large Language Model based Autonomous Agents »
Label humain : exclude · Route phase 1 : needs_manual

**19. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S5] : « we present a comprehensive survey of these studies »
   - Citation [S6] : « we first discuss the construction of LLM-based autonomous agents, for which we propose a unified framework »
   - Raison du modèle : The article is a survey that discusses LLM-based agents but does not propose or describe an actionable prompt technique.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Survey d’agents LLM ; le « unified framework » porte sur la construction d’agents, pas sur une technique de prompt isolable/actionnable. I1=not_reported → cohérent avec E1.

**20. E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE = met**
   - Citation [S5] : « we present a comprehensive survey of these studies »
   - Raison du modèle : The article is a survey that does not expose at least one isolable and actionable prompt technique.
   - Verdict humain : [x] CONFIRMÉ  [ ] REFUSÉ — note : Survey explicite (titre + S5) ; aucune technique PE isolable dans l’abstract. E5 correct.

---

## Synthèse Phase 2

| # | Critère | Article | Verdict |
|---|---------|---------|---------|
| 1 | I4 not_met | fp_prompt_tuning | CONFIRMÉ |
| 2 | E2 met | fp_prompt_tuning | CONFIRMÉ |
| 3 | E4 met | fp_agent_planning | CONFIRMÉ |
| 4 | E1 met | fp_ranking_evaluation | CONFIRMÉ |
| 5 | E3 met | fp_ranking_evaluation | CONFIRMÉ |
| 6 | E4 met | fp_ranking_evaluation | CONFIRMÉ |
| 7 | I4 not_met | state_title_only_prompt_tuning | CONFIRMÉ |
| 8 | I1 not_met | holdout_exclude_1 | CONFIRMÉ |
| 9 | I2 not_met | holdout_exclude_1 | **REFUSÉ** (devrait être not_reported) |
| 10 | E1 met | holdout_exclude_1 | CONFIRMÉ |
| 11 | E4 met | holdout_exclude_1 | CONFIRMÉ |
| 12 | E5 met | holdout_exclude_1 | CONFIRMÉ |
| 13 | I1 not_met | holdout_exclude_2 | CONFIRMÉ |
| 14 | I2 not_met | holdout_exclude_2 | **REFUSÉ** (devrait être not_reported) |
| 15 | I4 not_met | holdout_exclude_2 | CONFIRMÉ |
| 16 | E1 met | holdout_exclude_2 | CONFIRMÉ |
| 17 | E2 met | holdout_exclude_2 | CONFIRMÉ |
| 18 | E3 met | holdout_exclude_2 | **REFUSÉ** (pas un paper benchmark-only) |
| 19 | E1 met | holdout_exclude_3 | CONFIRMÉ |
| 20 | E5 met | holdout_exclude_3 | CONFIRMÉ |

**Score : 17 CONFIRMÉ / 3 REFUSÉ (85 %).**

### Impact sur la permission `auto_excludable`
- Aucun des 3 REFUSÉ n’est le seul hard-fail d’un article : chaque paper exclude conserve au moins un hard-fail confirmé.
- Les 3 FP originaux (prompt_tuning, agent_planning, ranking) ont tous leurs hard-fails confirmés → critère prereg (b) reste solide après review humaine.
- Pattern des REFUSÉS :
  1. **Sur-usage de `not_met` pour I2** quand l’info est absente → devrait être `not_reported` (tie-breaker protocole).
  2. **E3 trop large** : résultats d’éval ≠ article « benchmark only ».

### Recommandation
- Phase 2 **passe** pour valider les hard-fails qui porteront un futur `auto_excludable` (E1, E2, E4, E5, I1, I4 sur ces cas).
- Ne pas mettre I2=`not_met` ni E3 dans la allowlist auto sans re-prompt / v2 : trop de faux hard-fails de statut.
- Cible v2 déjà identifiée dans le report + ces 3 refus : distinguer `not_met` vs `not_reported`, et resserrer E3.
