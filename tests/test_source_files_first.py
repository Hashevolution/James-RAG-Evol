"""Source-files-first answer format (item #5-A + #3, 2026-05-08).

User feedback: "내부 자료에 대해 구체적으로 분야별로 세부적인 것을
물으면, 우선적으로 관련된 파일이 뭐가 있고, 그 파일은 어떤 내용에
대한 것이다라고 명시하고, 그다음 추론과 제안이 나오도록 개선".

Two coordinated changes:

A. pipeline.py prepends a [관련 자료 목록] section to safe_context
   before calling _generate_answer. The list is built from
   loop_state["docs"] source/name fields, deduplicated, top 5,
   filename-only (path-stripped to 60 chars).

B. response_style.NATURAL_PRESET.rule_text_ko/_en instructs the
   model to OPEN its answer with "관련 자료: file1.md, file2.md"
   when the context contains a [관련 자료 목록] section. Skipped
   when no source list is present (no spurious mention).

Plus a report-format mode for analysis-style queries.

Coverage:
  - rule_text mentions the [관련 자료 목록] header pattern + the
    file-mention instruction.
  - rule_text covers the report-format trigger (분석/추론) + the
    section-header structure (## 핵심 결론 / ## 근거 / ## 추가 시각).
  - pipeline.py source-prepend logic builds [관련 자료 목록] from
    loop_state["docs"] when context is non-empty.

Run:
  python -m unittest tests.test_source_files_first
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RuleTextSourceMentionTests(unittest.TestCase):
    """response_style.NATURAL_PRESET rules instruct the model to
    cite source files first when available."""

    @classmethod
    def setUpClass(cls):
        from core.response_style import NATURAL_PRESET
        cls.ko = NATURAL_PRESET.rule_text_ko
        cls.en = NATURAL_PRESET.rule_text_en

    def test_ko_mentions_source_section_header(self):
        # Model must recognise the literal section header it sees in context.
        self.assertIn("[관련 자료 목록]", self.ko,
                      "rule_text_ko must reference the literal header so the "
                      "model knows when to surface source files in the answer")

    def test_ko_mentions_file_first_format(self):
        self.assertIn("관련 자료:", self.ko,
                      "rule_text_ko must show the answer-opening format "
                      "(관련 자료: file1.md, file2.md)")

    def test_ko_skips_when_no_source_list(self):
        # No spurious mention when context has no source list.
        # Korean adjacent-string concatenation can introduce extra
        # whitespace between words — use regex \s+ to be tolerant.
        self.assertRegex(
            self.ko,
            r"자료\s+목록이\s+없으면\s+이\s+단계\s+생략",
            "rule must explicitly skip the file-mention step when "
            "the context has no source list (no spurious citations)",
        )

    def test_en_mentions_source_files(self):
        self.assertIn("Source files:", self.en,
                      "rule_text_en must show the analogous English format")
        self.assertIn("Skip when no source list", self.en,
                      "EN rule must also skip when no source list provided")


class RuleTextReportFormatTests(unittest.TestCase):
    """Analysis / 추론 questions trigger a report-format response
    with section headers."""

    @classmethod
    def setUpClass(cls):
        from core.response_style import NATURAL_PRESET
        cls.ko = NATURAL_PRESET.rule_text_ko
        cls.en = NATURAL_PRESET.rule_text_en

    def test_ko_report_format_triggers(self):
        # Specific Korean trigger words listed.
        for w in ("분석", "비교", "평가", "전망", "왜", "어떻게"):
            self.assertIn(w, self.ko,
                          f"report-format trigger word {w!r} missing")

    def test_ko_report_format_section_headers(self):
        for h in ("## 핵심 결론", "## 근거", "## 추가 시각"):
            self.assertIn(h, self.ko,
                          f"report-format section header {h!r} missing")

    def test_ko_simple_fact_check_skips_report(self):
        # Simple facts like "X가 뭐야" must NOT trigger report format.
        self.assertIn("단순 사실 확인엔 보고서 형식 사용 X", self.ko,
                      "rule must explicitly say report format is for "
                      "analysis questions only — simple facts skip it")

    def test_en_report_format_present(self):
        self.assertIn("report format", self.en.lower())
        for w in ("analyze", "compare", "evaluate", "why", "how"):
            self.assertIn(w, self.en.lower(),
                          f"EN trigger word {w!r} missing")


class PipelineSourcePrependTests(unittest.TestCase):
    """pipeline.run_retrieval_pipeline must prepend the
    [관련 자료 목록] section to safe_context before calling
    _generate_answer."""

    @classmethod
    def setUpClass(cls):
        from tests._pipeline_src import pipeline_source
        cls.src = pipeline_source()

    def test_source_section_built_from_docs(self):
        # The pipeline must read from loop_state["docs"] to assemble
        # the source list.
        self.assertIn("loop_state.get(\"docs\")", self.src,
                      "source list must come from loop_state['docs']")
        # The literal section header must be inserted.
        self.assertIn("[관련 자료 목록]", self.src,
                      "pipeline must inject the literal header that "
                      "rule_text references")

    def test_source_dedup_and_cap(self):
        # Without dedup, the same file appears multiple times when
        # multiple chunks come from the same doc. Without cap, very
        # long lists overwhelm short answers.
        self.assertIn("seen_sources", self.src,
                      "source-prepend must dedupe — same file across "
                      "multiple chunks should appear once")
        # Look for the [:5] cap on the docs slice.
        self.assertIn("docs\") or [])[:5]", self.src,
                      "source-prepend must cap at top-5 source files")

    def test_skip_when_no_context(self):
        # If safe_context is empty (no retrieval result), prepending
        # the header would mislead the model. Source prepend is gated
        # on safe_context.strip().
        self.assertIn("if safe_context.strip() and source_names", self.src,
                      "source-prepend must be gated on non-empty context "
                      "AND non-empty source list")

    def test_filename_only_not_full_path(self):
        # Full paths (e.g. C:/Project/James-RAG-Evol-v010/wiki/...) leak
        # operator filesystem layout and clutter the answer.
        self.assertIn('split("/")[-1]', self.src,
                      "filename should be path-stripped (split on /)")
        self.assertIn('split("\\\\")[-1]', self.src,
                      "filename should be path-stripped (split on \\)")


if __name__ == "__main__":
    unittest.main()
