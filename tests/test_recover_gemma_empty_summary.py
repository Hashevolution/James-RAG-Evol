"""Pin the recovery contract for `[Gemma 응답 없음]`-sentinel summaries.

Pre-PR-#447 the web-learn path checked only `len(knowledge.strip()) < 10`
before falling back, so the 13-char `[Gemma 응답 없음]` sentinel got
persisted to `attributes.summary` on 16 entity files. PR #447's
forward fix gates that branch; `scripts/recover_gemma_empty_summary.py`
patches the backlog using only metadata that's already on the file.

These tests verify the recovery helpers do what the operator expects:
detect the sentinel, synthesize a non-empty fallback, and rewrite all
three locations (top-level summary, attributes.summary, body section).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

# Path bootstrap (test runs from repo root via pytest, but the recovery
# script lives under scripts/ and imports `from core...`).
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.recover_gemma_empty_summary import (  # noqa: E402
    _fallback_summary,
    _is_error_sentinel,
    _node_needs_recovery,
    process_file,
)


class IsErrorSentinelTests(unittest.TestCase):
    def test_gemma_no_response_is_sentinel(self):
        self.assertTrue(_is_error_sentinel("[Gemma 응답 없음]"))

    def test_gemma_error_with_detail_is_sentinel(self):
        self.assertTrue(
            _is_error_sentinel("[Gemma 오류] 404 Client Error: Not Found"))

    def test_leading_whitespace_still_detected(self):
        self.assertTrue(_is_error_sentinel("   [Gemma 응답 없음]"))

    def test_real_summary_is_not_sentinel(self):
        self.assertFalse(
            _is_error_sentinel("AI 칩 시장의 주요 기업"))

    def test_empty_is_not_sentinel(self):
        self.assertFalse(_is_error_sentinel(""))
        self.assertFalse(_is_error_sentinel("   "))

    def test_non_string_is_not_sentinel(self):
        self.assertFalse(_is_error_sentinel(None))
        self.assertFalse(_is_error_sentinel(123))


class NodeNeedsRecoveryTests(unittest.TestCase):
    def test_top_level_sentinel_triggers(self):
        self.assertTrue(_node_needs_recovery({"summary": "[Gemma 응답 없음]"}))

    def test_attributes_sentinel_triggers(self):
        self.assertTrue(_node_needs_recovery(
            {"attributes": {"summary": "[Gemma 응답 없음]"}}))

    def test_both_clean_does_not_trigger(self):
        self.assertFalse(_node_needs_recovery({
            "summary": "GPU 제조 기업",
            "attributes": {"summary": "AI 칩 시장의 주요 기업"},
        }))

    def test_missing_summary_does_not_trigger(self):
        self.assertFalse(_node_needs_recovery({"name": "엔비디아"}))


class FallbackSummaryTests(unittest.TestCase):
    def test_prefers_original_query(self):
        fm = {
            "name": "web_business_MU_주식_1234567",
            "attributes": {
                "original_query": "MU 주식 투자 전략",
                "keywords": "MU 주식",
            },
        }
        self.assertEqual(_fallback_summary(fm), "MU 주식 투자 전략")

    def test_falls_back_to_keywords(self):
        fm = {
            "name": "web_business_foo_1234567",
            "attributes": {"keywords": "테스트 주제"},
        }
        self.assertEqual(_fallback_summary(fm), "테스트 주제")

    def test_falls_back_to_name_strips_prefix_and_suffix(self):
        """`web_business_` prefix and `_<timestamp>` suffix shouldn't
        leak into the recovered summary."""
        fm = {"name": "web_business_AMD_에_대해_설명_1778634167"}
        self.assertEqual(_fallback_summary(fm), "AMD 에 대해 설명")

    def test_caps_at_300_chars(self):
        long = "가" * 500
        fm = {"attributes": {"original_query": long}}
        self.assertEqual(len(_fallback_summary(fm)), 300)


class ProcessFileTests(unittest.TestCase):
    """End-to-end: write a stale .md → run process_file(apply=True) →
    verify frontmatter + body are all in sync."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.path = self.tmpdir / "stale.md"
        self.path.write_text(
            "---\n"
            "entity_id: e_document_test\n"
            "entity_type: document\n"
            "name: web_business_MU_주식_1234567\n"
            "summary: '[Gemma 응답 없음]'\n"
            "attributes:\n"
            "  original_query: MU 주식 투자 전략\n"
            "  keywords: MU 주식\n"
            "  summary: '[Gemma 응답 없음]'\n"
            "  learn_method: web_search\n"
            "---\n\n"
            "## 요약\n"
            "[Gemma 응답 없음]\n\n"
            "## 관계\n"
            "- (관계 없음)\n",
            encoding="utf-8",
        )

    def test_apply_rewrites_all_three_locations(self):
        changed, msg = process_file(self.path, apply=True, verbose=False)
        self.assertTrue(changed, msg)
        text = self.path.read_text(encoding="utf-8")
        # Body section
        self.assertIn("## 요약\nMU 주식 투자 전략\n", text)
        self.assertNotIn("[Gemma 응답 없음]", text,
            "sentinel must be gone from every location")
        # Frontmatter — both top-level and attributes mirror.
        self.assertIn("summary: MU 주식 투자 전략", text)

    def test_dry_run_does_not_write(self):
        original = self.path.read_text(encoding="utf-8")
        changed, _msg = process_file(self.path, apply=False, verbose=False)
        self.assertTrue(changed,
            "dry-run still reports a change is needed")
        self.assertEqual(self.path.read_text(encoding="utf-8"), original,
            "dry-run must not touch the file")

    def test_clean_file_is_skipped(self):
        clean = self.tmpdir / "clean.md"
        clean.write_text(
            "---\n"
            "entity_id: e_org_test\n"
            "entity_type: org\n"
            "name: 엔비디아\n"
            "summary: GPU 제조 기업\n"
            "attributes:\n"
            "  summary: GPU 제조 기업\n"
            "---\n\n"
            "## 요약\n"
            "GPU 제조 기업\n\n"
            "## 관계\n"
            "- (관계 없음)\n",
            encoding="utf-8",
        )
        original = clean.read_text(encoding="utf-8")
        changed, _msg = process_file(clean, apply=True, verbose=False)
        self.assertFalse(changed)
        self.assertEqual(clean.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
