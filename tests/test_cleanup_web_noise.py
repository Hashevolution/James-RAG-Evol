"""scripts/cleanup_web_noise_entities.py contract (2026-05-13).

Pre-#252 `save_as_longterm` 가 만든 잘못된 단일 concept 노드 (질문문 =
name, relations=[]) 를 안전하게 제거하는 스크립트. dry-run 기본, --apply
시 zip 백업 후 .md 삭제 + vector_store.delete_by_source.

Contracts under test:
  1) heuristic precision — 노이즈 패턴 4종(공백 다수 / 명령어 어미 / 질문
     기호 / 정상 형태)을 분류
  2) heuristic recall — 정상 entity (단일 토큰, 합법 다어절) 는 false
     positive 없이 지나간다
  3) dry-run 은 파일 시스템을 절대 건드리지 않는다
  4) apply 는 백업 zip 을 만들고 .md 를 삭제한다
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_concept(
    concept_dir: Path,
    filename:    str,
    *,
    name:        str,
    learn_method: str = "web_search",
    relations:   list | None = None,
    entity_type: str = "concept",
    sources:     list | None = None,
) -> Path:
    concept_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "name":            name,
        "normalized_name": filename.replace(".md", "").lower(),
        "entity_id":       f"e_concept_{filename[:8]}",
        "entity_type":     entity_type,
        "aliases":         [name],
        "attributes":      {"learn_method": learn_method},
        "relations":       relations or [],
        "sources":         sources or [f"web_general_{filename}"],
    }
    body = "## 요약\n[Gemma 응답 없음]\n\n## 관계\n- (관계 없음)\n"
    path = concept_dir / filename
    path.write_text(
        "---\n"
        + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=True)
        + "---\n"
        + body,
        encoding="utf-8",
    )
    return path


class HeuristicTests(unittest.TestCase):
    """identify_noise_entities 가 노이즈/정상을 정확히 분류하는지."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.concept_dir = self.tmpdir / "entity" / "prod" / "concept"

    def _run(self):
        from scripts.cleanup_web_noise_entities import identify_noise_entities
        return identify_noise_entities(self.concept_dir)

    def test_question_form_with_multiple_spaces(self):
        _write_concept(self.concept_dir, "noise_spaces.md",
            name="엔비디아와 조비와 관계 조사해봐")
        names = {c.name for c in self._run()}
        self.assertIn("엔비디아와 조비와 관계 조사해봐", names)

    def test_question_form_with_marker(self):
        _write_concept(self.concept_dir, "noise_marker.md",
            name="엔비디아 대해 묻고 있데?")
        names = {c.name for c in self._run()}
        self.assertIn("엔비디아 대해 묻고 있데?", names)

    def test_question_mark_alone(self):
        _write_concept(self.concept_dir, "noise_qmark.md",
            name="GPU?")
        names = {c.name for c in self._run()}
        self.assertIn("GPU?", names)

    def test_normal_single_token_concept(self):
        # 정상 entity: 단일 토큰, web_search 학습이어도 이름이 entity-like 면
        # 청소 대상 아님.
        _write_concept(self.concept_dir, "btc.md", name="비트코인")
        self.assertEqual(self._run(), [])

    def test_normal_compact_multi_word(self):
        # 정상 다어절 (공백 1개, 명령어 어미 없음).
        _write_concept(self.concept_dir, "claude_sonnet.md",
                       name="Claude Sonnet")
        self.assertEqual(self._run(), [])

    def test_has_relations_means_already_extracted(self):
        # relations 가 비어있지 않으면 분해된 정상 노드 — 노이즈 아님.
        _write_concept(
            self.concept_dir, "with_rels.md",
            name="엔비디아와 조비와 관계 조사해봐",  # 같은 surface form
            relations=[{"target": "X", "target_id": "e_x", "label": "관련"}],
        )
        self.assertEqual(self._run(), [],
            "노이즈 surface 라도 relations 가 있으면 청소 안 함")

    def test_non_web_learn_method_skipped(self):
        # PDF ingestion 으로 생긴 entity (learn_method != web_search) 는
        # 청소 안 함.
        _write_concept(
            self.concept_dir, "from_pdf.md",
            name="긴 이름이 공백 셋 있는 정상 entity",
            learn_method="pdf_ingest",
        )
        self.assertEqual(self._run(), [])

    def test_missing_concept_dir_returns_empty(self):
        from scripts.cleanup_web_noise_entities import identify_noise_entities
        self.assertEqual(
            identify_noise_entities(self.tmpdir / "nonexistent"),
            [],
        )


class ApplyTests(unittest.TestCase):
    """cleanup_entities dry-run vs apply 동작."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.concept_dir = self.tmpdir / "entity" / "prod" / "concept"
        self.backup_root = self.tmpdir / "backups_root"

        self.noise_path = _write_concept(
            self.concept_dir, "엔비디아와_조비_조사해봐.md",
            name="엔비디아와 조비와 관계 조사해봐",
        )
        self.normal_path = _write_concept(
            self.concept_dir, "btc.md", name="비트코인",
        )

    def test_dry_run_preserves_files(self):
        from scripts.cleanup_web_noise_entities import (
            cleanup_entities, identify_noise_entities,
        )
        candidates = identify_noise_entities(self.concept_dir)
        plan = cleanup_entities(
            candidates,
            apply       = False,
            backup_root = self.backup_root,
            source_type = "prod",
            concept_dir = self.concept_dir,
        )
        self.assertFalse(plan["applied"])
        self.assertEqual(plan["candidate_count"], 1)
        # 파일 둘 다 살아있음
        self.assertTrue(self.noise_path.exists())
        self.assertTrue(self.normal_path.exists())
        # 백업도 안 만들어짐
        self.assertFalse(self.backup_root.exists())

    def test_apply_deletes_noise_and_backups(self):
        from scripts.cleanup_web_noise_entities import (
            cleanup_entities, identify_noise_entities,
        )
        candidates = identify_noise_entities(self.concept_dir)
        plan = cleanup_entities(
            candidates,
            apply       = True,
            backup_root = self.backup_root,
            source_type = "prod",
            concept_dir = self.concept_dir,
        )
        self.assertTrue(plan["applied"])
        self.assertEqual(len(plan["deleted_files"]), 1)
        # 노이즈 삭제됨
        self.assertFalse(self.noise_path.exists())
        # 정상 파일 살아있음
        self.assertTrue(self.normal_path.exists())
        # 백업 zip 생성됨
        self.assertIsNotNone(plan["backup_zip"])
        self.assertTrue(Path(plan["backup_zip"]).exists())

    def test_apply_no_backup_skips_zip(self):
        from scripts.cleanup_web_noise_entities import (
            cleanup_entities, identify_noise_entities,
        )
        candidates = identify_noise_entities(self.concept_dir)
        plan = cleanup_entities(
            candidates,
            apply       = True,
            backup_root = None,           # ← --no-backup 효과
            source_type = "prod",
            concept_dir = self.concept_dir,
        )
        self.assertTrue(plan["applied"])
        self.assertIsNone(plan["backup_zip"])
        self.assertFalse(self.noise_path.exists())


class CLITests(unittest.TestCase):
    """argparse / 종료코드 sanity."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        (self.tmpdir / "entity" / "prod" / "concept").mkdir(parents=True)
        _write_concept(
            self.tmpdir / "entity" / "prod" / "concept",
            "noise.md", name="x y z 조사해봐",
        )

    def test_main_dry_run_exits_zero(self):
        from scripts.cleanup_web_noise_entities import main
        rc = main(["--wiki-dir", str(self.tmpdir)])
        self.assertEqual(rc, 0)
        # 파일 보존
        files = list((self.tmpdir / "entity" / "prod" / "concept").glob("*.md"))
        self.assertEqual(len(files), 1)


if __name__ == "__main__":
    unittest.main()
