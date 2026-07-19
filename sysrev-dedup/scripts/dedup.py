#!/usr/bin/env python3
"""
dedup.py — Déduplique les articles candidats pour Hermes Synthesis.

Trois passes :
  1. identité exacte → fusion certaine
  2. titre normalisé identique avec années compatibles
  3. similarité de titre (ratio ≥ threshold) sous garde-fous

Sauvegarde le fichier original, journalise chaque fusion, met à jour
prisma.json et manifest.json. Stdlib uniquement — zéro dépendance.

Usage:
  python3 dedup.py '<json>'

JSON attendu:
  {"id": "ma-revue", "threshold": 0.90}
"""

import csv
import difflib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone


def row_identity(row: dict) -> tuple[str, str] | None:
    """Retourne l'identité stable d'une ligne, sans jamais accepter vide."""
    for kind in ("doi", "source_id", "oa_url"):
        raw_value = row.get(kind, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            return kind, value
    return None


def row_identity_values(row: dict) -> list[tuple[str, str]]:
    """Retourne toutes les identités renseignées d'une ligne, sans les vides."""
    values = []
    for kind in ("doi", "source_id", "oa_url"):
        raw_value = row.get(kind, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            values.append((kind, value))
    return values


# ---------------------------------------------------------------------------
# Normalisation des titres pour la comparaison fuzzy
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """Normalise un titre en conservant les séparations entre les mots."""
    if not isinstance(title, str):
        return ""
    normalized = unicodedata.normalize("NFKC", title).casefold()
    normalized = "".join(c if c.isalnum() else " " for c in normalized)
    return " ".join(normalized.split())


# ---------------------------------------------------------------------------
# Similarité entre deux titres
# ---------------------------------------------------------------------------

def title_similarity(a: str, b: str) -> float:
    """Ratio de similarité entre deux titres normalisés (0.0–1.0)."""
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def parse_year(value: object) -> int | None:
    """Extrait une année exploitable ; une valeur absente reste inconnue."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(?:19|20)\d{2}", text)
    return int(text) if match else None


def years_compatible(a: dict, b: dict) -> bool:
    """Autorise une même année, une année voisine ou une année manquante."""
    year_a = parse_year(a.get("year", ""))
    year_b = parse_year(b.get("year", ""))
    return year_a is None or year_b is None or abs(year_a - year_b) <= 1


# ---------------------------------------------------------------------------
# Choix de la meilleure ligne à conserver lors d'une fusion
# ---------------------------------------------------------------------------

def score_row(row: dict) -> tuple[int, int, int]:
    """Classe les lignes par complétude, puis par récence.

    La priorité est volontairement lexicographique : abstract présent, puis
    URL OA présente, puis année la plus récente.
    """
    has_abstract = bool(str(row.get("abstract", "") or "").strip())
    has_oa_url = bool(str(row.get("oa_url", "") or "").strip())
    year = parse_year(row.get("year", "")) or 0
    return (int(has_abstract), int(has_oa_url), year)


def pick_best(rows: list[dict]) -> dict:
    """Parmi un groupe de doublons, choisit la ligne la plus complète."""
    return max(rows, key=score_row)


# ---------------------------------------------------------------------------
# Log d'audit
# ---------------------------------------------------------------------------

def audit_identity_values(rows: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    """Construit les identités et sources d'un groupe fusionné sans vides."""
    merged_ids: list[str] = []
    merged_dois: list[str] = []
    records: list[dict] = []
    seen_ids: set[tuple[str, str]] = set()
    for row in rows:
        source = str(row.get("source", "") or "").strip()
        for kind, value in row_identity_values(row):
            if (kind, value) in seen_ids:
                continue
            seen_ids.add((kind, value))
            merged_ids.append(value)
            records.append({"type": kind, "value": value, "source": source})
            if kind == "doi" and value not in merged_dois:
                merged_dois.append(value)
    return merged_ids, merged_dois, records


def log_decision(base: str, kept_row: dict, merged_rows: list[dict], reason: str,
                 run_id: str, score: float | None = None):
    """Ajoute une ligne d'audit générique dans decisions.jsonl."""
    kept_identity = row_identity(kept_row)
    if kept_identity is None:
        raise ValueError("Impossible d'auditer une fusion sans identité conservée.")
    merged_ids, merged_dois, merged_id_records = audit_identity_values(merged_rows)
    merged_sources = sorted({
        str(row.get("source", "") or "").strip()
        for row in merged_rows
        if str(row.get("source", "") or "").strip()
    })
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run": run_id,
        "doc": kept_identity[1],
        "identity_type": kept_identity[0],
        "stage": "dedup",
        "decision": "merge",
        "merged_ids": merged_ids,
        "merged_id_records": merged_id_records,
        "merged_sources": merged_sources,
        "merged_dois": merged_dois,
        "reason": reason,
    }
    if score is not None:
        entry["score"] = round(score, 3)
    log_path = f"{base}/decisions.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _find(parent: list[int], value: int) -> int:
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _union(parent: list[int], left: int, right: int) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[right_root] = left_root


def exact_identity_groups(rows: list[dict]) -> list[list[int]]:
    """Retourne les composantes reliées par DOI/source_id/oa_url identique."""
    parent = list(range(len(rows)))
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        for identity in row_identity_values(row):
            buckets.setdefault(identity, []).append(index)
    for indexes in buckets.values():
        for index in indexes[1:]:
            _union(parent, indexes[0], index)
    groups: dict[int, list[int]] = {}
    for index in range(len(rows)):
        groups.setdefault(_find(parent, index), []).append(index)
    return [group for group in groups.values() if len(group) > 1]


def exact_title_groups(rows: list[dict]) -> list[list[int]]:
    """Regroupe les titres normalisés identiques aux années compatibles."""
    buckets: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        title = normalize_title(row.get("title", ""))
        if title:
            buckets.setdefault(title, []).append(index)

    groups: list[list[int]] = []
    for indexes in buckets.values():
        compatible_groups: list[list[int]] = []
        for index in indexes:
            row = rows[index]
            target = next(
                (
                    group for group in compatible_groups
                    if all(years_compatible(row, rows[member]) for member in group)
                ),
                None,
            )
            if target is None:
                compatible_groups.append([index])
            else:
                target.append(index)
        groups.extend(group for group in compatible_groups if len(group) > 1)
    return groups


def approximate_title_groups(rows: list[dict], threshold: float) -> list[list[int]]:
    """Regroupe prudemment les titres similaires, sans fusionner deux DOI."""
    groups: list[list[int]] = []
    for index, row in enumerate(rows):
        target = None
        for group in groups:
            members = [rows[member] for member in group]
            nonempty_dois = {
                str(member.get("doi", "") or "").strip()
                for member in members + [row]
                if str(member.get("doi", "") or "").strip()
            }
            if len(nonempty_dois) > 1:
                continue
            if not any(not str(member.get("doi", "") or "").strip() for member in members + [row]):
                continue
            if not all(years_compatible(row, member) for member in members):
                continue
            if not all(title_similarity(row.get("title", ""), member.get("title", "")) >= threshold
                       for member in members):
                continue
            target = group
            break
        if target is None:
            groups.append([index])
        else:
            target.append(index)
    return [group for group in groups if len(group) > 1]


def apply_merge_groups(rows: list[dict], groups: list[list[int]], base: str,
                       run_id: str, reason_factory, score_factory=None) -> tuple[list[dict], int]:
    """Applique des groupes disjoints et conserve la ligne la plus complète."""
    group_by_index: dict[int, list[int]] = {}
    for group in groups:
        for index in group:
            group_by_index[index] = group

    result: list[dict] = []
    removed = 0
    for index, row in enumerate(rows):
        group = group_by_index.get(index)
        if group is None:
            result.append(row)
            continue
        if index != group[0]:
            removed += 1
            continue
        members = [rows[member] for member in group]
        best = pick_best(members)
        score = score_factory(members) if score_factory else None
        log_decision(base, best, members, reason_factory(members, score), run_id, score)
        result.append(best)
    return result, removed


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main(rid: str, threshold: float = 0.90):
    base = f"/reviews/{rid}"
    csv_path = f"{base}/candidates.csv"
    raw_path = f"{base}/candidates_raw.csv"
    manifest_path = f"{base}/manifest.json"
    run_id = datetime.now(timezone.utc).isoformat()

    if not os.path.exists(csv_path):
        print(f"❌ {csv_path} introuvable. Lance d'abord la skill search.", file=sys.stderr)
        sys.exit(1)

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    if manifest.get("stage") == "search_done":
        shutil.copy2(csv_path, raw_path)
        print(f"📋 Backup rafraîchi depuis la nouvelle recherche : {raw_path}")
    elif not os.path.exists(raw_path):
        shutil.copy2(csv_path, raw_path)
        print(f"📋 Backup créé : {raw_path}")
    else:
        print(f"📋 Backup existant conservé : {raw_path}")

    # Chargement — toujours depuis le backup, pour que dedup soit rejouable
    with open(raw_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    original_count = len(rows)
    if original_count == 0:
        print("⚠️  candidates_raw.csv est vide, rien à dédupliquer.")
        return

    source_totals: dict[str, int] = {}
    for r in rows:
        source_totals[r.get("source", "?")] = source_totals.get(r.get("source", "?"), 0) + 1

    invalid_rows = [index + 1 for index, row in enumerate(rows) if row_identity(row) is None]
    if invalid_rows:
        raise ValueError(
            "Identité absente pour les lignes candidates "
            f"{invalid_rows[:10]} : DOI, source_id ou oa_url requis."
        )

    def exact_identity_reason(members: list[dict], _score: float | None) -> str:
        kinds = sorted({kind for member in members for kind, _ in row_identity_values(member)})
        sources = sorted({str(member.get("source", "") or "?") for member in members})
        return (
            f"identité exacte ({', '.join(kinds)}) — {len(members)} copies fusionnées "
            f"(sources: {', '.join(sources)})"
        )

    def exact_title_reason(members: list[dict], _score: float | None) -> str:
        sources = sorted({str(member.get("source", "") or "?") for member in members})
        return (
            f"titre normalisé identique — {len(members)} versions fusionnées "
            f"(années compatibles; sources: {', '.join(sources)})"
        )

    def approximate_reason(members: list[dict], score: float | None) -> str:
        score_text = f"{score:.3f}" if score is not None else "?"
        sources = sorted({str(member.get("source", "") or "?") for member in members})
        return (
            f"titre similaire (ratio={score_text}, seuil={threshold:.3f}; "
            f"années compatibles; au moins un DOI absent) — sources: {', '.join(sources)}"
        )

    def group_similarity(members: list[dict]) -> float:
        similarities = [
            title_similarity(left.get("title", ""), right.get("title", ""))
            for position, left in enumerate(members)
            for right in members[position + 1:]
        ]
        return min(similarities) if similarities else 1.0

    # --- Passe 1 : identité exacte ---
    rows, pass1_removed = apply_merge_groups(
        rows, exact_identity_groups(rows), base, run_id,
        exact_identity_reason, lambda _members: 1.0,
    )

    # --- Passe 2 : titre normalisé identique ---
    title_exact_groups = exact_title_groups(rows)
    pass2_source_removed: dict[str, int] = {}
    for group in title_exact_groups:
        members = [rows[index] for index in group]
        best = pick_best(members)
        for member in members:
            if member is best:
                continue
            source = str(member.get("source", "") or "?")
            pass2_source_removed[source] = pass2_source_removed.get(source, 0) + 1
    rows, title_exact_removed = apply_merge_groups(
        rows, title_exact_groups, base, run_id,
        exact_title_reason, lambda _members: 1.0,
    )

    # --- Passe 3 : similarité de titre sous garde-fous ---
    approximate_groups = approximate_title_groups(rows, threshold)
    for group in approximate_groups:
        members = [rows[index] for index in group]
        best = pick_best(members)
        for member in members:
            if member is best:
                continue
            source = str(member.get("source", "") or "?")
            pass2_source_removed[source] = pass2_source_removed.get(source, 0) + 1
    rows, title_approx_removed = apply_merge_groups(
        rows, approximate_groups, base, run_id,
        approximate_reason, group_similarity,
    )
    pass2_removed = title_exact_removed + title_approx_removed

    for src, removed in pass2_source_removed.items():
        total = source_totals.get(src, 0)
        if total and removed / total > 0.10:
            print(
                f"⚠️  Passe titre : {removed}/{total} ({removed / total:.0%}) fusionnés "
                f"pour la source '{src}' — taux élevé, vérifie les résultats.",
                file=sys.stderr,
            )

    total_removed = pass1_removed + pass2_removed
    final_count = len(rows)

    # Réécriture de candidates.csv dédupliqué
    cols = [
        "title", "doi", "source_id", "year", "abstract", "oa_url", "pdf_status",
        "source", "query", "date",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Mise à jour prisma.json
    prisma_path = f"{base}/prisma.json"
    if os.path.exists(prisma_path):
        prisma = json.load(open(prisma_path, encoding="utf-8"))
    else:
        prisma = {}
    prisma["after_dedup"] = final_count
    with open(prisma_path, "w", encoding="utf-8") as f:
        json.dump(prisma, f, indent=2, ensure_ascii=False)

    # Mise à jour manifest.json
    manifest["stage"] = "dedup_done"
    manifest["dedup_threshold"] = threshold
    manifest["dedup_removed"] = total_removed
    manifest["updated"] = datetime.now(timezone.utc).isoformat()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Rapport
    print(f"\n📊 Résultat déduplication :")
    print(f"   Avant          : {original_count}")
    print(f"   DOI exact      : -{pass1_removed}")
    print(f"   Titre identique : -{title_exact_removed}")
    print(f"   Titre similaire : -{title_approx_removed}")
    print(f"   Après          : {final_count}")
    print(f"   Seuil titre    : {threshold}")
    print(f"\n✅ candidates.csv dédupliqué ({final_count} articles)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: dedup.py '<json>'", file=sys.stderr)
        print('  {"id": "ma-revue", "threshold": 0.90}', file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Erreur JSON : {e}", file=sys.stderr)
        sys.exit(1)

    rid = payload.get("id")
    threshold = float(payload.get("threshold", 0.90))

    if not rid:
        print("JSON invalide : 'id' requis.", file=sys.stderr)
        sys.exit(1)

    main(rid, threshold)
