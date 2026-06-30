# Bugs connus — Hermes Synthesis

## Bug 1 : Signature mismatch mock/réel

**Date** : 2026-06-25
**Fichier** : `screen.py`
**Symptôme** : `TypeError: llm_screen() takes 4 positional arguments but 5 were given`
**Cause** : `mock_screen()` avait un paramètre `doi` (5 params) mais `llm_screen()` non (4 params). La boucle `main()` appelle avec 5 arguments.
**Correction** : Ajouter `doi` à `llm_screen()` (paramètre ignoré, pour compatibilité).
**Fichiers impactés** : `screen.py` ✅ corrigé, `extract.py` ✅ corrigé préventivement

## Bug 2 : Journalisation : modèle affiché "mock@test" au lieu du vrai modèle

**Date** : 2026-06-25
**Fichier** : `screen.py`
**Symptôme** : `decisions.jsonl` contient `"model": "mock@test"` même quand le LLM réel est utilisé
**Cause** : `log_decision()` avait `model="mock@test"` en paramètre par défaut, jamais surchargé dans la boucle principale
**Correction** : `llm_screen()` et `mock_screen()` retournent `"model"` dans leur dict ; la boucle le passe à `log_decision(model=result["model"])`

## Bug 3 : SyntaxError dans report.py après patchs

**Date** : 2026-06-25
**Fichier** : `report.py`
**Symptôme** : `SyntaxError: '[' was never closed` puis `IndentationError`
**Cause** : Patchs multiples sur `generate_report()` ont créé une liste `lines = [` non fermée et une indentation incohérente
**Correction** : Réécriture complète de `generate_report()` avec structure propre (liste fermée, `extend()` séparés, pas d'imbrication)

## Bug 5 : NameError sur `e` hors du bloc except (portée des variables d'exception)

**Date** : 2026-06-30
**Fichier** : `search.py`
**Symptôme** : `NameError: name 'e' is not defined` dans le `status_reason` après la boucle retry
**Cause** : En Python 3, la variable d'exception `e` est effacée (`del e`) à la sortie du bloc `except` pour éviter les références circulaires. Référencer `e` après le `except` lève un NameError.
**Correction** : Stocker `e.code` dans `last_error_code = e.code` À L'INTÉRIEUR du bloc except, initialiser `last_error_code = None` avant la boucle. Utiliser `last_error_code` (jamais `e`) après la boucle.

## Bug 6 : `--stdin` lit du vide dans WSL (subprocess.run évite le problème)

**Date** : 2026-06-30
**Fichier** : `search.py`, `screen.py`
**Symptôme** : `Erreur JSON : Expecting value: line 1 column 1 (char 0)` quand on passe `--stdin`
**Cause** : Dans l'environnement WSL, `python3 script.py --stdin < file.json` lit du vide depuis stdin. Probablement lié au terminal broker ou au buffering.
**Correction** : NE PAS utiliser `--stdin`. Passer le JSON via `sys.argv[1]` avec `subprocess.run([\"python3\", \"script.py\", json_str])` — cette approche contourne complètement stdin et le shell. **Ne pas** tenter de réparer `--stdin`, c'est un dead-end dans cet environnement.
