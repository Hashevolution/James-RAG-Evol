"""[PR plan-2, 2026-05-09] core.llm_catalog — central LLM model registry.

Before this module, model metadata was duplicated:
  - tools/system/hardware_inspector.LLM_CATALOG (10 entries)
  - core/model_catalog._model_catalog (mode → candidate list)
Adding a new model meant editing both. After this PR, both sites read
from core.llm_catalog.CATALOG. This file regression-guards the
contract.

Run:
    python -m unittest tests.test_llm_catalog
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CatalogShapeTests(unittest.TestCase):
    """Each entry in CATALOG must have the documented schema."""

    @classmethod
    def setUpClass(cls):
        from core.llm_catalog import CATALOG
        cls.CATALOG = CATALOG

    def test_catalog_non_empty(self):
        self.assertGreater(len(self.CATALOG), 5,
            "central catalog should carry at least the gemma3 family + qwen-coder")

    def test_required_fields_per_entry(self):
        required = {"tag", "weight", "purpose", "min_vram_gb",
                    "min_ram_gb", "size_gb", "description"}
        for e in self.CATALOG:
            missing = required - set(e.keys())
            self.assertFalse(missing,
                f"{e.get('tag','?')} missing required fields: {missing}")

    def test_weight_values_valid(self):
        valid = {"light", "medium", "heavy"}
        for e in self.CATALOG:
            self.assertIn(e["weight"], valid,
                f"{e['tag']} has invalid weight '{e['weight']}'")

    def test_purpose_values_valid(self):
        valid = {"chat", "retrieval", "coding", "multimodal", "general"}
        for e in self.CATALOG:
            for p in e["purpose"]:
                self.assertIn(p, valid,
                    f"{e['tag']} has unknown purpose '{p}'")

    def test_no_duplicate_tags(self):
        tags = [e["tag"] for e in self.CATALOG]
        self.assertEqual(len(tags), len(set(tags)),
            "CATALOG must not have duplicate tags — duplicates would "
            "break by_tag() lookup determinism")

    def test_min_specs_reasonable(self):
        for e in self.CATALOG:
            # No model should claim 0 RAM/VRAM — that's a schema bug.
            self.assertGreaterEqual(e["min_ram_gb"], 1)
            self.assertGreaterEqual(e["min_vram_gb"], 0)
            self.assertGreater(e["size_gb"], 0)


class LookupTests(unittest.TestCase):
    """by_tag / by_purpose / all_tags helpers."""

    def setUp(self):
        from core import llm_catalog as lc
        self.lc = lc

    def test_by_tag_hit(self):
        e = self.lc.by_tag("gemma3:4b")
        self.assertIsNotNone(e)
        self.assertEqual(e["tag"], "gemma3:4b")

    def test_by_tag_miss(self):
        self.assertIsNone(self.lc.by_tag("nonexistent:99b"))
        self.assertIsNone(self.lc.by_tag(""))
        self.assertIsNone(self.lc.by_tag(None))

    def test_by_purpose_chat(self):
        chat = self.lc.by_purpose("chat")
        self.assertGreater(len(chat), 3,
            "should have ≥4 chat-capable entries")
        for e in chat:
            self.assertIn("chat", e["purpose"])

    def test_by_purpose_coding(self):
        coding = self.lc.by_purpose("coding")
        self.assertGreater(len(coding), 1,
            "should have ≥2 coding entries (qwen-coder + deepseek)")
        for e in coding:
            self.assertIn("coding", e["purpose"])

    def test_by_purpose_unknown(self):
        self.assertEqual(self.lc.by_purpose("nonexistent"), [])
        self.assertEqual(self.lc.by_purpose(""), [])

    def test_all_tags_returns_list_of_strings(self):
        tags = self.lc.all_tags()
        self.assertIsInstance(tags, list)
        for t in tags:
            self.assertIsInstance(t, str)
            self.assertTrue(t)


class HardwareFeasibilityTests(unittest.TestCase):
    """feasible_for_hardware + recommend_for_hardware."""

    def setUp(self):
        from core import llm_catalog as lc
        self.lc = lc

    def test_feasible_low_spec(self):
        # 8GB RAM, no GPU — should still get the smallest models
        out = self.lc.feasible_for_hardware(vram_gb=0, ram_gb=8)
        tags = {e["tag"] for e in out}
        # gemma3:1b and gemma2:2b are designed for this tier
        self.assertIn("gemma3:1b", tags)
        # The 27B model should NOT fit
        self.assertNotIn("gemma3:27b", tags)

    def test_feasible_high_spec(self):
        # 32GB RAM + 16GB VRAM — everything fits
        out = self.lc.feasible_for_hardware(vram_gb=16, ram_gb=32)
        tags = {e["tag"] for e in out}
        self.assertIn("gemma3:27b", tags)
        self.assertIn("qwen2.5-coder:32b", tags)

    def test_recommend_returns_purpose_buckets(self):
        specs = {
            "gpu": {"found": True, "vram_gb": 8},
            "ram": {"total_gb": 16},
        }
        out = self.lc.recommend_for_hardware(specs, top_n=3)
        for purpose in ("chat", "coding", "multimodal"):
            self.assertIn(purpose, out)
            self.assertIsInstance(out[purpose], list)
            self.assertLessEqual(len(out[purpose]), 3,
                f"top_n=3 must cap each bucket at 3 entries (got {len(out[purpose])} for {purpose})")

    def test_recommend_chat_gives_largest_first(self):
        # On a 32GB+16GB machine, recommend should put a heavy chat
        # model first (gemma3:27b) since it's the most capable
        # feasible chat model.
        specs = {
            "gpu": {"found": True, "vram_gb": 16},
            "ram": {"total_gb": 32},
        }
        out = self.lc.recommend_for_hardware(specs, top_n=3)
        if out["chat"]:
            # First entry should be a heavy or medium chat model.
            self.assertIn(out["chat"][0]["weight"], ("medium", "heavy"))


class IntegrationWithModelCatalogTests(unittest.TestCase):
    """core.model_catalog.model_catalog() now derives from
    core.llm_catalog. Verify the picker still gets sensible candidates."""

    def setUp(self):
        from core import model_catalog as mc
        self.mc = mc

    def test_chat_mode_has_candidates(self):
        cat = self.mc.model_catalog()
        self.assertIn("chat", cat)
        self.assertGreater(len(cat["chat"]), 1,
            "chat mode must have ≥2 candidates so picker shows up")

    def test_coding_mode_has_candidates(self):
        cat = self.mc.model_catalog()
        self.assertIn("coding", cat)
        self.assertGreaterEqual(len(cat["coding"]), 2)

    def test_picker_entries_are_tag_weight_tuples(self):
        cat = self.mc.model_catalog()
        for tag, weight in cat["chat"]:
            self.assertIsInstance(tag, str)
            self.assertIn(weight, ("light", "medium", "heavy"))

    def test_operator_default_present_in_chat(self):
        from config import GEMMA_MODEL
        cat = self.mc.model_catalog()
        chat_tags = [t for t, _ in cat["chat"]]
        self.assertIn(GEMMA_MODEL, chat_tags,
            "operator's chat default must always appear in picker")


class IntegrationWithHardwareInspectorTests(unittest.TestCase):
    """LLM_CATALOG (legacy name) still works, derived from central."""

    @classmethod
    def setUpClass(cls):
        from tools.system import hardware_inspector as hw
        cls.hw = hw

    def test_local_catalog_non_empty(self):
        self.assertGreater(len(self.hw.LLM_CATALOG), 5,
            "LLM_CATALOG must still surface ≥5 entries (back-compat)")

    def test_local_catalog_has_legacy_keys(self):
        # Downstream UI consumers expect the legacy field names.
        for entry in self.hw.LLM_CATALOG:
            for legacy_key in ("name", "tag", "min_vram", "min_ram",
                               "desc", "purpose", "size_gb"):
                self.assertIn(legacy_key, entry,
                    f"LLM_CATALOG entry missing legacy key '{legacy_key}'")

    def test_get_llm_recommendations_returns_feasibility(self):
        specs = {
            "gpu": {"found": True, "vram_gb": 8, "name": "test"},
            "ram": {"total_gb": 16},
        }
        recs = self.hw.get_llm_recommendations(specs)
        self.assertIsInstance(recs, list)
        for r in recs:
            self.assertIn("feasible", r)


if __name__ == "__main__":
    unittest.main()
