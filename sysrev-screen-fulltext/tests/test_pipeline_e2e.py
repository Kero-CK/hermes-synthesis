"""Dry-run E2E mock : fulltext → screen_fulltext → review (queue fulltext)
→ extract → report.

Vérifie le contrat central du stage d'éligibilité full-text :
  - un article exclu à l'éligibilité (mock005) ne passe jamais en extraction ;
  - extract refuse de tourner tant qu'un cas d'éligibilité est en attente ;
  - le diagramme PRISMA sépare non-récupérés (accès) et exclus (éligibilité).
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SYSREV_ROOT = Path(__file__).resolve().parents[2]


def load_module(skill: str, script: str):
    path = SYSREV_ROOT / skill / "scripts" / script
    spec = importlib.util.spec_from_file_location(f"e2e_{skill.replace('-', '_')}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fulltext = load_module("sysrev-fulltext", "fulltext.py")
screen_fulltext = load_module("sysrev-screen-fulltext", "screen_fulltext.py")
review = load_module("sysrev-review", "review.py")
extract = load_module("sysrev-extract", "extract.py")
report = load_module("sysrev-report", "report.py")


FIELDS = ["title", "doi", "source_id", "year", "abstract", "oa_url",
          "pdf_status", "source", "query", "date"]
DOIS = ["10.1234/mock001", "10.1234/mock003", "10.1234/mock005", "10.1234/mock008"]

PROTOCOL = """# Protocole de test

## Question
Quel est l'impact de l'IA sur la productivité des PME ?

## Critères d'inclusion
- Étude empirique sur PME/TPE
- Mesure d'impact sur la productivité

## Critères d'exclusion
- Pas de mesure d'impact
- Grandes entreprises uniquement

## Codebook d'extraction
- **secteur** : secteur d'activité étudié
- **techno_ia** : type d'IA déployée
- **gain_productivite** : gain de productivité mesuré
"""


def make_review(root: Path) -> str:
    (root / "protocol.md").write_text(PROTOCOL, encoding="utf-8")
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for doi in DOIS:
            writer.writerow({
                "title": f"Article {doi}", "doi": doi, "source_id": "",
                "year": "2024", "abstract": "abstract", "oa_url": "",
                "pdf_status": "", "source": "openalex", "query": "q", "date": "",
            })
    entries = [
        {"doc": doi, "stage": "screen_title_abstract", "decision": "include",
         "score": 0.9, "actor": "ai", "reason": "test"}
        for doi in DOIS
    ]
    (root / "decisions.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text(json.dumps({
        "id": "e2e", "stage": "review_done", "search_status": "complete",
        "review_mode": "scoping",
    }), encoding="utf-8")
    (root / "prisma.json").write_text(json.dumps({
        "identified": 9, "after_dedup": 9, "screened": 4, "included": 4,
        "needs_manual_pending": 0,
    }), encoding="utf-8")
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


class PipelineE2ETests(unittest.TestCase):
    def test_fulltext_eligibility_gates_extraction_and_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)

            # 1. fulltext : les 4 mocks sont récupérés.
            fulltext.main(rid, use_mock=True)
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_retrieved"], 4)
            self.assertEqual(prisma["fulltext_not_retrieved"], 0)

            # 2. screen_fulltext : 2 include, 1 exclude (mock005), 1 needs_manual (mock008).
            screen_fulltext.main(rid, use_mock=True)
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_screened"], 4)
            self.assertEqual(prisma["included_final"], 2)
            self.assertEqual(prisma["excluded_fulltext_eligibility"], 1)
            self.assertEqual(prisma["fulltext_review_pending"], 1)
            queue = (root / "to_review_fulltext.jsonl").read_text(encoding="utf-8")
            self.assertIn("10.1234/mock008", queue)

            # 3. extract refuse tant que le cas ambigu n'est pas tranché.
            with self.assertRaises(SystemExit):
                extract.main(rid, use_mock=True)

            # 4. review (queue fulltext) : l'humain inclut mock008.
            review.apply_decisions(rid, {"10.1234/mock008": "include"}, queue="fulltext")
            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["included_final"], 3)
            self.assertEqual(prisma["fulltext_review_pending"], 0)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "review_fulltext_done")

            # 5. extract : uniquement les 3 inclusions finales, jamais mock005.
            extract.main(rid, use_mock=True)
            with (root / "extraction.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            extracted_docs = {row["doi"] for row in rows}
            self.assertEqual(
                extracted_docs,
                {"10.1234/mock001", "10.1234/mock003", "10.1234/mock008"},
            )
            self.assertNotIn("10.1234/mock005", extracted_docs)
            self.assertEqual(len(rows), 9)  # 3 articles × 3 variables

            # 6. report : cohérence sur les inclusions finales, sémantique séparée.
            report.main(rid, use_mock=True)
            prisma_md = (root / "prisma.md").read_text(encoding="utf-8")
            self.assertIn("Exclus à l'éligibilité", prisma_md)
            self.assertIn("Non récupérés", prisma_md)
            self.assertIn("**n = 3**", prisma_md)  # inclus final
            report_md = (root / "report.md").read_text(encoding="utf-8")
            self.assertIn("Articles exclus à l'éligibilité (texte intégral)", report_md)
            self.assertIn("10.1234/mock005", report_md)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "report_done")

    def test_report_refuses_pending_fulltext_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            fulltext.main(rid, use_mock=True)
            screen_fulltext.main(rid, use_mock=True)
            (root / "extraction.csv").write_text(
                "doi,variable,valeur,citation,section\n", encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                report.main(rid, use_mock=True)


if __name__ == "__main__":
    unittest.main()
