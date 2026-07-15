# Phase 2 — Vérification humaine des hard-fails (deepseek-reasoner, run 20260715T135629864224Z)

Pour chaque ligne : lis la citation, relis l'abstract si besoin, puis note CONFIRMÉ (le hard-fail est correct) ou REFUSÉ (le hard-fail est une erreur du modèle). Seuls les hard-fails d'assessments mécaniquement valides sont listés.

## fp_prompt_tuning — « Chain of Thought Prompt Tuning in Vision Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**1. I4_PRACTITIONER = not_met**
   - Citation [S5] : « chain of thought prompt tuning »
   - Raison du modèle : Prompt tuning involves training learned prompt parameters, not practitioner-accessible prompts; no statement indicates the prompts are discrete or manual.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**2. E2_MODEL_TRAINING_ONLY = met**
   - Citation [S5] : « chain of thought prompt tuning »
   - Raison du modèle : The article focuses on learned prompt parameters (prompt tuning) without a practitioner-usable prompting component.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## fp_agent_planning — « LLM-Planner: Few-Shot Grounded Planning for Embodied Agents with Large Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**3. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S1] : « using large language models (LLMs) as a planner for embodied agents that can follow natural language instructions to complete complex tasks in a visually-perceived environment. »
   - Citation [S3] : « propose a novel method, LLM-Planner, that harnesses the power of large language models to do few-shot planning for embodied agents. »
   - Raison du modèle : The article reports a domain application (embodied agents) of an LLM but does not describe the prompt method in actionable detail, as the prompt technique is not clearly specified.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## fp_ranking_evaluation — « Is ChatGPT Good at Search? Investigating Large Language Models as Re-Ranking Agents »
Label humain : exclude · Route phase 1 : needs_manual

**4. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « properly instructed LLMs can deliver competitive, even superior results »
   - Raison du modèle : The article discusses LLMs for ranking but does not describe an actionable prompt technique; 'properly instructed' is too vague.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**5. E3_BENCHMARK_ONLY = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « our experiments reveal that properly instructed LLMs can deliver competitive, even superior results »
   - Citation [S6] : « we collect a new test set called NovelEval »
   - Raison du modèle : The article presents a benchmark evaluation without a transferable prompt method or structure.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**6. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S4] : « we first investigate generative LLMs such as ChatGPT and GPT-4 for relevance ranking in IR »
   - Citation [S5] : « properly instructed LLMs »
   - Raison du modèle : The article applies LLMs to the domain of IR re-ranking but does not describe the prompt method in actionable detail.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## state_title_only_prompt_tuning — « Chain of Thought Prompt Tuning in Vision Language Models »
Label humain : exclude · Route phase 1 : needs_manual

**7. I4_PRACTITIONER = not_met**
   - Citation [T] : « Chain of Thought Prompt Tuning »
   - Raison du modèle : The phrase 'Prompt Tuning' indicates training of prompt parameters, which requires model training and is not applicable by a practitioner without training.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## holdout_exclude_1 — « Prompt Engineering for Healthcare: Methodologies and Applications »
Label humain : exclude · Route phase 1 : needs_manual

**8. I1_PROMPT_TECHNIQUE = not_met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The abstract states it is a review, not a description of a concrete prompt-engineering operation.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**9. I2_REPRODUCIBLE = not_met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The abstract does not expose an identifiable prompt structure or transferable method.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**10. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The article is a review and does not propose or describe an actionable prompt technique.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**11. E4_APPLICATION_WITHOUT_PROMPT_DETAIL = met**
   - Citation [S5] : « First, we will provide the development of prompt engineering and emphasize its significant contributions to healthcare natural language processing applications such as question-answering systems, text summarization, and machine translation. »
   - Raison du modèle : The abstract mentions domain applications without describing the prompt method in actionable detail.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**12. E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE = met**
   - Citation [S4] : « This review will introduce the latest advances in prompt engineering in the field of natural language processing for the medical field. »
   - Raison du modèle : The article is a survey that does not expose an isolable and actionable prompt technique.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## holdout_exclude_2 — « Training language models to follow instructions with human feedback »
Label humain : exclude · Route phase 1 : needs_manual

**13. I1_PROMPT_TECHNIQUE = not_met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article focuses on fine-tuning the model using human feedback, not on describing a concrete prompt-engineering operation.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**14. I2_REPRODUCIBLE = not_met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article does not expose an identifiable prompt structure or method; it describes model training.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**15. I4_PRACTITIONER = not_met**
   - Citation [S5] : « fine-tune GPT-3 using supervised learning »
   - Raison du modèle : The technique requires fine-tuning model weights, not applicable by a practitioner through prompts or inference-time orchestration.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**16. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Raison du modèle : The article discusses LLMs but proposes a training technique, not an actionable prompt technique.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**17. E2_MODEL_TRAINING_ONLY = met**
   - Citation [S4] : « fine-tuning with human feedback »
   - Citation [S5] : « fine-tune GPT-3 using supervised learning »
   - Raison du modèle : The article is solely about training/fine-tuning without a practitioner-usable prompting component.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**18. E3_BENCHMARK_ONLY = met**
   - Citation [S8] : « outputs from the 1.3B parameter InstructGPT model are preferred to outputs from the 175B GPT-3 »
   - Raison du modèle : The article includes model evaluation and lacks a transferable prompt method.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

## holdout_exclude_3 — « A Survey on Large Language Model based Autonomous Agents »
Label humain : exclude · Route phase 1 : needs_manual

**19. E1_NO_ACTIONABLE_TECHNIQUE = met**
   - Citation [S5] : « we present a comprehensive survey of these studies »
   - Citation [S6] : « we first discuss the construction of LLM-based autonomous agents, for which we propose a unified framework »
   - Raison du modèle : The article is a survey that discusses LLM-based agents but does not propose or describe an actionable prompt technique.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

**20. E5_NON_PRIMARY_WITHOUT_ISOLABLE_TECHNIQUE = met**
   - Citation [S5] : « we present a comprehensive survey of these studies »
   - Raison du modèle : The article is a survey that does not expose at least one isolable and actionable prompt technique.
   - Verdict humain : [ ] CONFIRMÉ  [ ] REFUSÉ — note :

