"""[W7-hotfix 2026-05-10, W1 진단 §2-C] .gitignore wiki 패턴 회귀.

W1 진단 결과: 기존 .gitignore 가 wiki/entity/prod/{concept,org,person,
document,system_internal}/*.md 5 카테고리만 ignore 했다.

문제:
  • 새 카테고리 (food/, event/, relation/ 등) 추가 시 자동으로 ignored
    안 됨 → 사용자 데이터 누수 가능.
  • wiki/prod/ (entity/ 없이 prod 직속) 도 .gitignore 등재 X.

W1 §2-C 권고:
  → wildcard 패턴 (wiki/entity/prod/**/*.md) + 메타 파일 unignore +
    wiki/prod/ defense.

이 테스트는 git check-ignore CLI 로 실제 git matcher 의 동작을 검증한다 —
정규식으로 .gitignore 텍스트를 파싱하지 않고 git 자신의 매칭 로직을
사용하므로 syntax edge case 까지 신뢰 가능.

Run:
    python -m unittest tests.test_gitignore_wiki
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


def _is_ignored(rel_path: str) -> bool:
    """git check-ignore 로 path 가 ignored 인지 확인.

    git check-ignore exit code:
      0 = ignored
      1 = NOT ignored
      128 = error (path 형식 오류 등)
    """
    # `--no-index` 없이 호출 — repo 의 실제 .gitignore 만 본다.
    # `-q` 로 stdout 억제, 종료 코드만 사용.
    proc = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 128:
        raise RuntimeError(
            f"git check-ignore error for {rel_path!r}: {proc.stderr}"
        )
    return proc.returncode == 0


class ExistingCategoriesStillIgnoredTests(unittest.TestCase):
    """기존 5 카테고리는 그대로 ignored — 회귀 가드."""

    def test_concept_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/concept/foo.md"))

    def test_org_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/org/foo.md"))

    def test_person_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/person/foo.md"))

    def test_document_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/document/foo.md"))

    def test_system_internal_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/system_internal/foo.md"))


class FutureCategoriesAlsoIgnoredTests(unittest.TestCase):
    """W1 §2-C 핵심 — 신규 카테고리도 자동 ignored."""

    def test_food_category_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/food/x.md"))

    def test_event_category_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/event/x.md"))

    def test_relation_category_ignored(self):
        self.assertTrue(_is_ignored("wiki/entity/prod/relation/x.md"))

    def test_deeply_nested_md_ignored(self):
        # wildcard ** 가 깊은 경로도 커버.
        self.assertTrue(
            _is_ignored("wiki/entity/prod/concept/sub/deep/x.md")
        )


class MetaFilesPreservedTests(unittest.TestCase):
    """index.md / .gitkeep 같은 메타 파일은 추적 대상."""

    def test_category_index_md_not_ignored(self):
        # 카테고리 인덱스 (예: 카테고리 요약 페이지) 는 추적되어야.
        self.assertFalse(
            _is_ignored("wiki/entity/prod/concept/index.md"),
            "카테고리 index.md 가 ignored 됨 — 추적 의도와 충돌",
        )

    def test_gitkeep_not_ignored(self):
        # 빈 카테고리 폴더를 git 에 보존하려면 .gitkeep 추적 필요.
        self.assertFalse(
            _is_ignored("wiki/entity/prod/person/.gitkeep"),
        )

    def test_top_level_wiki_index_not_ignored(self):
        # wiki/index.md 는 시스템 메타 — 항상 tracked.
        self.assertFalse(_is_ignored("wiki/index.md"))

    def test_wiki_synonyms_not_ignored(self):
        self.assertFalse(_is_ignored("wiki/synonyms.yaml"))


class DefenseAgainstWrongPathTests(unittest.TestCase):
    """wiki/prod/ (entity/ 없이) 도 누수 차단."""

    def test_wiki_prod_direct_md_ignored(self):
        self.assertTrue(_is_ignored("wiki/prod/foo.md"))

    def test_wiki_prod_subdir_ignored(self):
        self.assertTrue(_is_ignored("wiki/prod/concept/foo.md"))


if __name__ == "__main__":
    unittest.main()
