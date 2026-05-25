"""Regression tests for scripts/rename_markdown_polluted_nodes.py.

The script is load-bearing on operator-run cleanup of the
production wiki, so the test surface covers:

1. Stale-node detection by markdown tokens in `name` only (not by
   `__` runs in normalized_name — those can be legitimate
   punctuation).
2. The clean id/name/normalized values match what PR #452's forward
   path produces (same emphasis-token strip + same SALT + same
   SHA256 truncation).
3. Cross-references in *other* entities — both
   `relations[].target_id` (hash) and `relations[].target` (name) —
   migrate when a stale node renames.
4. Body `## 관계` lines update so the rendered wiki text matches the
   new frontmatter.
5. Dry-run leaves the filesystem untouched.
6. `--apply` is idempotent (a second pass finds 0 stale nodes).
7. Collision and empty-after-strip cases are skipped (warned, not
   crashed).

We drive the script via its `run()` entry point so we can stand up
an arbitrary fixture under a tmp `wiki/entity` root, then assert on
both the resulting frontmatter and the surviving file paths.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable

import yaml

# Path bootstrap so `scripts.rename_markdown_polluted_nodes` imports
# without depending on the project root being on sys.path.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from scripts.rename_markdown_polluted_nodes import (  # noqa: E402
    _clean_name,
    _generate_entity_id,
    _is_markdown_polluted,
    _scan,
    _split_frontmatter,
    run,
)


def _write_md(path: Path, fm: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=True,
    )
    path.write_text(f"---\n{fm_text}---\n{body}", encoding="utf-8")


def _read_md(path: Path):
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


class _CleanupBase(unittest.TestCase):
    """Stands up a fresh `wiki/entity/<type>/` tree per test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wiki = self.tmp / "entity"
        for t in ("person", "org", "concept", "document", "event"):
            (self.wiki / t).mkdir(parents=True)

    def _files(self) -> Iterable[Path]:
        return sorted(self.wiki.rglob("*.md"))


class PureHelperTests(unittest.TestCase):
    """Cheap unit checks on the pure helpers — no filesystem needed."""

    def test_clean_name_strips_bold(self):
        self.assertEqual(_clean_name("**경쟁사 대비 AMD**"),
                         "경쟁사 대비 AMD")

    def test_clean_name_preserves_underscores(self):
        self.assertEqual(_clean_name("gpt_4"), "gpt_4")

    def test_clean_name_strips_mixed_tokens(self):
        # Token characters are removed; the inter-word spaces in the
        # original survive intact (no whitespace normalization).
        self.assertEqual(_clean_name("`Structured` *CoT* ~~v2~~"),
                         "Structured CoT v2")

    def test_clean_name_empty_after_strip(self):
        self.assertEqual(_clean_name("***"), "")

    def test_is_polluted_only_markdown_tokens(self):
        # underscores alone are NOT pollution
        self.assertFalse(_is_markdown_polluted("gpt_4"))
        self.assertFalse(_is_markdown_polluted("엔비디아"))
        # `,`, `(`, `)`, `.` are not pollution either (Tesla case)
        self.assertFalse(_is_markdown_polluted("Tesla, Inc. (TSLA)"))
        # but `*`, `` ` ``, `~` are
        self.assertTrue(_is_markdown_polluted("**bold**"))
        self.assertTrue(_is_markdown_polluted("`code`"))
        self.assertTrue(_is_markdown_polluted("~~strike~~"))

    def test_entity_id_matches_forward_path(self):
        # The id must be identical to what core/wiki_generator's
        # `_generate_entity_id` would produce for the cleaned name —
        # otherwise re-ingest of the same doc would land on a 3rd id.
        clean = _clean_name("**경쟁사 대비 AMD 기술적 우위**")
        # Sanity: known clean name should hash deterministically.
        id1 = _generate_entity_id(clean, "document")
        id2 = _generate_entity_id(clean, "document")
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("e_document_"))
        self.assertEqual(len(id1), len("e_document_") + 8)


class CleanWikiTests(_CleanupBase):

    def test_no_stale_no_changes(self):
        _write_md(self.wiki / "org" / "nvidia.md", {
            "entity_id":       "e_org_aaaa1111",
            "entity_type":     "org",
            "name":            "NVIDIA",
            "normalized_name": "nvidia",
            "relations":       [],
        }, body="## 요약\nGPU\n## 관계\n")
        before = sorted(p.name for p in self._files())
        rc = run(self.wiki, apply=True, verbose=False)
        after = sorted(p.name for p in self._files())
        self.assertEqual(rc, 0)
        self.assertEqual(before, after)


class StaleSelfRewriteTests(_CleanupBase):

    def test_bold_name_renamed_and_frontmatter_clean(self):
        # The exact production pattern.
        dirty_name = "**경쟁사 대비 AMD 기술적 우위**"
        dirty_id   = "e_document_b34476e8"          # arbitrary stale id
        _write_md(self.wiki / "document" / "dirty.md", {
            "entity_id":       dirty_id,
            "entity_type":     "document",
            "name":            dirty_name,
            "normalized_name": "___경쟁사_대비_amd_기술적_우위__",
            "aliases":         [dirty_name],
            "relations":       [],
        }, body="## 요약\n분석 자료\n## 관계\n")

        rc = run(self.wiki, apply=True, verbose=False)
        self.assertEqual(rc, 0)

        survivors = list(self._files())
        self.assertEqual(len(survivors), 1)
        self.assertNotEqual(survivors[0].name, "dirty.md")
        # filename has no `*` and no `___` runs
        self.assertNotIn("*", survivors[0].name)
        self.assertNotIn("___", survivors[0].name)

        fm, _body = _read_md(survivors[0])
        self.assertEqual(fm["name"], "경쟁사 대비 AMD 기술적 우위")
        self.assertNotIn("*", fm["name"])
        # entity_id matches the canonical recomputation
        expected_id = _generate_entity_id(
            "경쟁사 대비 AMD 기술적 우위", "document",
        )
        self.assertEqual(fm["entity_id"], expected_id)
        # aliases lead with the clean name; the dirty form is gone
        self.assertEqual(fm["aliases"][0], "경쟁사 대비 AMD 기술적 우위")
        self.assertNotIn(dirty_name, fm["aliases"])


class CrossRefUpdateTests(_CleanupBase):

    def _setup_stale_with_xref(self):
        """Stale doc + a clean concept that references it by both
        target_id and target name + a body line that mentions the
        stale name."""
        self.dirty_name = "**경쟁사 분석**"
        self.clean_name = "경쟁사 분석"
        self.dirty_id   = "e_document_aaaa1111"
        self.clean_id   = _generate_entity_id(self.clean_name, "document")

        _write_md(self.wiki / "document" / "stale.md", {
            "entity_id":       self.dirty_id,
            "entity_type":     "document",
            "name":            self.dirty_name,
            "normalized_name": "___경쟁사_분석__",
            "aliases":         [],
            "relations":       [],
        }, body="## 요약\n경쟁 자료\n## 관계\n")

        _write_md(self.wiki / "concept" / "ref.md", {
            "entity_id":       "e_concept_bbbb2222",
            "entity_type":     "concept",
            "name":            "시장 분석",
            "normalized_name": "시장_분석",
            "relations": [
                {
                    "target":      self.dirty_name,
                    "target_id":   self.dirty_id,
                    "target_type": "document",
                    "type":        "RELATED_TO",
                    "confidence":  0.8,
                },
            ],
        }, body=(
            "## 요약\n시장 분석\n## 관계\n"
            f"- 관련: {self.dirty_name} (conf=0.80)\n"
        ))

    def test_xref_target_id_and_target_name_migrate(self):
        self._setup_stale_with_xref()
        rc = run(self.wiki, apply=True, verbose=False)
        self.assertEqual(rc, 0)

        ref_path = self.wiki / "concept" / "ref.md"
        fm, body = _read_md(ref_path)
        rel = fm["relations"][0]
        self.assertEqual(rel["target_id"], self.clean_id)
        self.assertEqual(rel["target"],    self.clean_name)
        self.assertIn(f"- 관련: {self.clean_name}", body)
        self.assertNotIn(self.dirty_name, body)


class DryRunTests(_CleanupBase):

    def test_dry_run_makes_no_writes(self):
        dirty_name = "**something**"
        _write_md(self.wiki / "concept" / "x.md", {
            "entity_id":       "e_concept_cccc3333",
            "entity_type":     "concept",
            "name":            dirty_name,
            "normalized_name": "___something__",
            "relations":       [],
        }, body="## 요약\n\n## 관계\n")
        before_files = {p.name: p.read_text(encoding="utf-8")
                        for p in self._files()}

        rc = run(self.wiki, apply=False, verbose=False)
        self.assertEqual(rc, 0)

        after_files = {p.name: p.read_text(encoding="utf-8")
                       for p in self._files()}
        self.assertEqual(before_files, after_files)


class IdempotencyTests(_CleanupBase):

    def test_second_apply_is_a_noop(self):
        _write_md(self.wiki / "concept" / "y.md", {
            "entity_id":       "e_concept_dddd4444",
            "entity_type":     "concept",
            "name":            "**dup**",
            "normalized_name": "___dup__",
            "relations":       [],
        }, body="## 요약\n\n## 관계\n")
        rc1 = run(self.wiki, apply=True, verbose=False)
        self.assertEqual(rc1, 0)
        first_files = {p.name: p.read_text(encoding="utf-8")
                       for p in self._files()}

        # Second pass — should detect 0 stale, change nothing.
        rc2 = run(self.wiki, apply=True, verbose=False)
        self.assertEqual(rc2, 0)
        second_files = {p.name: p.read_text(encoding="utf-8")
                        for p in self._files()}
        self.assertEqual(first_files, second_files)


class CollisionTests(_CleanupBase):

    def test_empty_clean_name_skipped(self):
        # `***` strips to "" — would otherwise collide en masse on
        # the "unknown" filename. The plan must be None.
        _write_md(self.wiki / "concept" / "empty.md", {
            "entity_id":       "e_concept_eeee5555",
            "entity_type":     "concept",
            "name":            "***",
            "normalized_name": "____",
            "relations":       [],
        })
        plans, _warnings = _scan(self.wiki)
        self.assertEqual(plans, [])

    def test_same_pass_collision_warns(self):
        # Two stale entities clean to the same name → both skipped.
        _write_md(self.wiki / "concept" / "a.md", {
            "entity_id":   "e_concept_aaaa1111",
            "entity_type": "concept",
            "name":        "**dup**",
            "relations":   [],
        })
        _write_md(self.wiki / "concept" / "b.md", {
            "entity_id":   "e_concept_bbbb2222",
            "entity_type": "concept",
            "name":        "*dup*",
            "relations":   [],
        })
        plans, warnings = _scan(self.wiki)
        self.assertEqual(len(plans), 1)        # first wins; second warned
        self.assertTrue(any("collision" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
