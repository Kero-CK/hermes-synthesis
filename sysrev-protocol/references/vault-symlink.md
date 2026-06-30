# Architecture vault — /reviews symlink

## Problème

Par défaut, les scripts Hermes Synthesis écrivent dans `/reviews/<slug>/`, un
dossier sur le filesystem WSL/Docker. L'utilisateur veut que les revues
apparaissent dans son vault Obsidian (`/vault/`), pas dans un coin invisible.

## Solution

Un lien symbolique :

```bash
rm -rf /reviews
ln -s /vault/Projets/Hermes\ Synthesis/Reviews /reviews
```

Ainsi :
- Les scripts continuent d'écrire dans `/reviews/<slug>/`
- Les fichiers atterrissent physiquement dans le vault
- Zéro duplication, zéro saturation disque
- Aucune modification de code nécessaire

## Conséquence pour `report.py`

Le script `sysrev-report/scripts/report.py` avait un bloc qui copiait les
livrables de `/reviews/<slug>/` vers `/vault/.../reviews/<slug>/`. Avec le
symlink, ces deux chemins pointent vers le même fichier → `SameFileError`.
Le bloc de copie a été supprimé (remplacé par un message informatif).

## Vérification

```bash
ls -la /reviews
# Doit afficher : /reviews -> /vault/Projets/Hermes Synthesis/Reviews
```
