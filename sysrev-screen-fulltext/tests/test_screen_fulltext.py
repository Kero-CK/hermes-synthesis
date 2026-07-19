from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "screen_fulltext.py"
SPEC = importlib.util.spec_from_file_location("sysrev_screen_fulltext", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
screen_fulltext = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen_fulltext)


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
- **gain_productivite** : gain de productivité mesuré
"""


def make_rid(root: Path) -> str:
    reviews_root = Path(os.path.abspath(os.sep)) / "reviews"
    return os.path.relpath(root, reviews_root).replace(os.sep, "/")


def make_review(root: Path, *, with_sources: bool = True) -> str:
    (root / "sources").mkdir(parents=True)
    (root / "protocol.md").write_text(PROTOCOL, encoding="utf-8")
    entries = [
        {"doc": "10.1234/mock001", "stage": "screen_title_abstract", "decision": "include"},
        {"doc": "10.1234/mock001", "stage": "fulltext", "decision": "retrieved",
         "reason": "mock"},
        {"doc": "10.1234/mock005", "stage": "screen_title_abstract", "decision": "include"},
        {"doc": "10.1234/mock005", "stage": "fulltext", "decision": "retrieved",
         "reason": "mock"},
    ]
    (root / "decisions.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8"
    )
    (root / "manifest.json").write_text(
        json.dumps({"id": "test", "stage": "fulltext_done"}), encoding="utf-8"
    )
    (root / "prisma.json").write_text(
        json.dumps({"included": 2, "fulltext_retrieved": 2, "fulltext_not_retrieved": 0}),
        encoding="utf-8",
    )
    if with_sources:
        for doi in ("10.1234/mock001", "10.1234/mock005"):
            (root / "sources" / f"{doi.replace('/', '_')}.md").write_text(
                "# Article\n\n" + "contenu " * 100, encoding="utf-8"
            )
    return make_rid(root)


class DecideTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(screen_fulltext.decide(0.75, 0.75, 0.25), "include")
        self.assertEqual(screen_fulltext.decide(0.25, 0.75, 0.25), "exclude")
        self.assertEqual(screen_fulltext.decide(0.5, 0.75, 0.25), "needs_manual")


class ScreenFulltextTests(unittest.TestCase):
    def test_missing_markdown_blocks_before_any_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root, with_sources=False)
            journal_before = (root / "decisions.jsonl").read_text(encoding="utf-8")
            with self.assertRaises(SystemExit):
                screen_fulltext.main(rid, use_mock=True)
            # Aucune décision screen_fulltext ne doit avoir été journalisée.
            self.assertEqual(
                (root / "decisions.jsonl").read_text(encoding="utf-8"), journal_before
            )

    def test_mock_run_journals_decisions_and_counters(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            screen_fulltext.main(rid, use_mock=True)

            entries = [
                json.loads(line)
                for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ft_entries = [e for e in entries if e.get("stage") == "screen_fulltext"]
            by_doc = {e["doc"]: e for e in ft_entries}
            self.assertEqual(by_doc["10.1234/mock001"]["decision"], "include")
            self.assertEqual(by_doc["10.1234/mock005"]["decision"], "exclude")
            # Une exclusion porte un critère nommé.
            self.assertTrue(by_doc["10.1234/mock005"].get("criterion"))
            self.assertTrue(all(e.get("actor") == "ai" for e in ft_entries))

            prisma = json.loads((root / "prisma.json").read_text(encoding="utf-8"))
            self.assertEqual(prisma["fulltext_screened"], 2)
            self.assertEqual(prisma["included_final"], 1)
            self.assertEqual(prisma["excluded_fulltext_eligibility"], 1)
            self.assertEqual(prisma["fulltext_review_pending"], 0)
            # Les compteurs d'accès restent intacts et distincts.
            self.assertEqual(prisma["fulltext_retrieved"], 2)
            self.assertEqual(prisma["fulltext_not_retrieved"], 0)

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "screen_fulltext_done")

    def test_refuses_wrong_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            (root / "manifest.json").write_text(
                json.dumps({"id": "test", "stage": "screen_done"}), encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                screen_fulltext.main(rid, use_mock=True)

    def test_downstream_stage_requires_force(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rid = make_review(root)
            (root / "manifest.json").write_text(
                json.dumps({"id": "test", "stage": "extract_done"}), encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                screen_fulltext.main(rid, use_mock=True)
            screen_fulltext.main(rid, use_mock=True, force=True)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["stage"], "screen_fulltext_done")


if __name__ == "__main__":
    unittest.main()
