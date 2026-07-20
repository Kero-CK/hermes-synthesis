"""La déclaration IA du rapport doit afficher le modèle servi quand il est
connu (journal ou réponse de synthèse), et rien sinon.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report.py"
SPEC = importlib.util.spec_from_file_location("sysrev_report_served", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ServedSuffixTests(unittest.TestCase):
    def _render(self, served_models):
        return report.generate_report(
            "rid-test", "# Protocole", {"included": 0}, [], [],
            "scoping", served_models=served_models,
        )

    def test_declaration_shows_served_models_when_known(self):
        text = self._render({
            "screening": "deepseek-v4-flash",
            "extraction": "deepseek-v4-flash",
            "synthesis": "deepseek-v4-flash",
        })
        self.assertEqual(text.count("servi : deepseek-v4-flash"), 3)

    def test_declaration_omits_suffix_when_unknown(self):
        text = self._render(None)
        self.assertNotIn("servi :", text)

    def test_multiple_served_models_are_all_listed(self):
        text = self._render({"screening": "model-a, model-b",
                             "extraction": "", "synthesis": ""})
        self.assertIn("servi : model-a, model-b", text)


if __name__ == "__main__":
    unittest.main()
