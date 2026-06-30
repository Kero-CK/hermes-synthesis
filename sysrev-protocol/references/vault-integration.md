# Intégration Vault Obsidian

## Architecture

```
/reviews → /vault/Projets/Hermes Synthesis/Reviews/   (symlink)
```

Toutes les skills du pipeline écrivent dans `/reviews/<id>/`. Grâce au symlink,
les fichiers atterrissent directement dans le vault Obsidian de Cédric.

## Pourquoi un symlink ?

- **Zéro duplication** : un seul emplacement physique
- **Zéro modif de code** : les scripts continuent d'écrire dans `/reviews/`
- **Visible dans Obsidian** : les rapports apparaissent automatiquement
- **Survit aux mises à jour** : les skills n'ont pas à connaître le chemin du vault

## Mise en place (one-time)

```bash
# Si /reviews existe déjà en dossier physique :
rm -rf /reviews

# Créer le symlink :
ln -s /vault/Projets/Hermes\ Synthesis/Reviews /reviews
```

## Vérification

```bash
ls -la /reviews
# Doit afficher : /reviews -> /vault/Projets/Hermes Synthesis/Reviews
```

## Impact sur les skills

| Skill | Comportement avec symlink |
|---|---|
| protocol | Écrit dans `/reviews/<id>/` → vault |
| search | Idem |
| dedup | Idem |
| screen | Idem |
| fulltext | Idem |
| extract | Idem |
| report | **Attention** : le bloc de copie vault explicite a été supprimé de `report.py` (causait `SameFileError`). Le script signale juste `(via symlink)`. |
| review | Idem (pas d'écriture de fichier) |

## Piège : SameFileError

Si un script tente de copier un fichier de `/reviews/<id>/x.md` vers
`/vault/.../Reviews/<id>/x.md`, Python lève `shutil.SameFileError` car
c'est le même fichier via le symlink.

→ Ne jamais faire de `shutil.copy2` entre `/reviews/` et le vault.
