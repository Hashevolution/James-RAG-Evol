"""Phase A sources-schema helpers — unit tests.

docs/design/v0.3-knowledge-cascade.md §3 + §6 — Knowledge Cascade Phase A.

Phase A 시점에서 본 helper 들은 production 호출 site 가 없지만
(reads still use ``relation['confidence']`` directly), 마이그레이션
스크립트와 Phase B / E 의 미래 코드가 의존할 contract 를 여기서 잠근다.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.relations_schema import (
    CONFIDENCE_CAP,
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    LEGACY_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
    VALID_SOURCE_ROLES,
    build_legacy_source,
    compute_confidence_from_sources,
    read_relation_sources,
)


class RoleConstantsTests(unittest.TestCase):
    """4-role taxonomy from §2 design doc — cascade 분기 매칭에 사용."""

    def test_four_roles_defined(self):
        self.assertEqual(LEGACY_SOURCE_ROLE,  "legacy")
        self.assertEqual(EXTRACT_SOURCE_ROLE, "extract")
        self.assertEqual(INVERSE_SOURCE_ROLE, "inverse")
        self.assertEqual(MANUAL_SOURCE_ROLE,  "manual")

    def test_valid_set_covers_all_four(self):
        self.assertEqual(
            VALID_SOURCE_ROLES,
            frozenset({"legacy", "extract", "inverse", "manual"}),
            "Phase C/D cascade gates on role membership; if a new role "
            "is added without updating VALID_SOURCE_ROLES the gates "
            "silently treat it as unknown",
        )


class ComputeConfidenceTests(unittest.TestCase):
    """Noisy-OR (probabilistic OR) per design memo §3.

    Formula: ``P = 1 - Π(1 - w_i)``. Chosen for monotone cascade
    semantics — adding a source strictly increases P, removing one
    strictly decreases P, no early saturation.
    """

    def test_empty_sources_returns_zero(self):
        self.assertEqual(compute_confidence_from_sources([]), 0.0)
        self.assertEqual(compute_confidence_from_sources(None), 0.0)

    def test_single_source_returns_weight(self):
        # 단일 source 는 noisy-OR / clamped sum 동일.
        # 이 identity 가 Phase A 마이그레이션의 byte-identical 게이트.
        sources = [{"weight": 0.7, "role": "extract"}]
        self.assertAlmostEqual(
            compute_confidence_from_sources(sources), 0.7,
        )

    def test_two_sources_diverge_from_clamped_sum(self):
        # 2-source 분기 invariant — 디자인 메모 §3 의 핵심 락인.
        # clamped sum 이면 0.7, noisy-OR 이면 1 - (0.6 * 0.7) = 0.58.
        # 이 값이 0.58 이 아니라면 clamped sum 으로 회귀한 것.
        sources = [
            {"weight": 0.4, "role": "extract"},
            {"weight": 0.3, "role": "extract"},
        ]
        self.assertAlmostEqual(
            compute_confidence_from_sources(sources), 0.58,
            places=4,
            msg="clamped sum 이 돌아왔다면 0.7 이 나옴. noisy-OR 회귀.",
        )

    def test_many_sources_asymptotic_not_saturated(self):
        # 디자인 메모 §3: "many sources → asymptotic to 1, but never
        # exceeds 1". quarterly report cascade 시 5+ 출처가 모여도
        # confidence 가 1.0 으로 평탄화되지 않아야 함.
        sources = [{"weight": 0.7, "role": "extract"} for _ in range(5)]
        # 1 - 0.3**5 = 1 - 0.00243 = 0.99757
        result = compute_confidence_from_sources(sources)
        self.assertAlmostEqual(result, 0.9976, places=4)
        self.assertLess(
            result, CONFIDENCE_CAP,
            msg="noisy-OR 은 [0, 1) — 정확히 1.0 에 도달하면 saturate 회귀.",
        )

    def test_strong_corroboration_3_sources(self):
        # 디자인 메모 §3 의 예시: 3 doc 강한 강화. clamped sum 으로는
        # 0.7+0.6+0.3 = 1.6 → cap 1.0. noisy-OR 로는:
        # 1 - (0.3 * 0.4 * 0.7) = 1 - 0.084 = 0.916.
        sources = [
            {"weight": 0.7, "role": "extract"},
            {"weight": 0.6, "role": "extract"},
            {"weight": 0.3, "role": "manual"},
        ]
        self.assertAlmostEqual(
            compute_confidence_from_sources(sources), 0.916,
            places=3,
        )
        # 핵심: cap 에 도달하지 않아 신호 보존.
        self.assertLess(
            compute_confidence_from_sources(sources), CONFIDENCE_CAP,
        )

    def test_monotone_adding_source_strictly_increases(self):
        # 디자인 메모 §3: "adding a new source — always increases".
        # 이 monotonicity 가 cascade 단조성의 근거.
        before = [{"weight": 0.5, "role": "extract"}]
        after  = [{"weight": 0.5, "role": "extract"},
                  {"weight": 0.2, "role": "extract"}]
        self.assertGreater(
            compute_confidence_from_sources(after),
            compute_confidence_from_sources(before),
        )

    def test_monotone_removing_source_strictly_decreases(self):
        # 디자인 메모 §3: "removing a source — always decreases".
        # clamped sum 의 saturate 동작은 이를 깬다 (이미 cap 이면
        # source 가 빠져도 안 떨어짐).
        before = [{"weight": 0.7, "role": "extract"},
                  {"weight": 0.6, "role": "extract"},
                  {"weight": 0.3, "role": "manual"}]
        after  = [{"weight": 0.7, "role": "extract"},
                  {"weight": 0.6, "role": "extract"}]
        self.assertGreater(
            compute_confidence_from_sources(before),
            compute_confidence_from_sources(after),
        )

    def test_weight_clamped_to_unit_interval(self):
        # 노이즈 robustness — out-of-range weight 가 product 를 음수나
        # 1 초과로 튕기지 못 하게 per-element clamp.
        sources = [
            {"weight":  1.5, "role": "extract"},  # 1.0 으로 clamp
            {"weight": -0.3, "role": "extract"},  # 0.0 으로 clamp
        ]
        # weight 1.0 한 개만 살아남는 효과 → 1 - 0 = 1.0 정확.
        # weight 0.0 는 (1 - 0) = 1 곱이라 product 에 영향 없음.
        self.assertAlmostEqual(
            compute_confidence_from_sources(sources), 1.0,
        )

    def test_skips_malformed_entries(self):
        # 손편집 / 외부 plugin 이 weight 누락하거나 dict 아닌 값을 넣은
        # source 가 들어오면 무시 — 다른 잘 정의된 source 는 살린다.
        sources = [
            {"weight": 0.5},          # OK → contributes (1 - 0.5)
            {"role": "extract"},      # weight 누락 — 무시
            "not-a-dict",              # 자체가 무효
            {"weight": "0.3"},         # str — 무시 (Phase B/E 가 float 로 검증)
        ]
        # 유효한 source 는 weight=0.5 한 개 → noisy-OR = 0.5.
        self.assertAlmostEqual(
            compute_confidence_from_sources(sources), 0.5,
        )


class ReadRelationSourcesTests(unittest.TestCase):
    """sources 누락 시 confidence 에서 synthetic legacy 복원. Phase A
    마이그레이션 이후 거의 안 타지만, 외부 손편집 .md 방어선."""

    def test_returns_sources_when_present(self):
        rel = {
            "target_id": "e_org_x",
            "confidence": 0.9,
            "sources": [
                {"doc_id": "d1", "weight": 0.7, "role": "extract"},
            ],
        }
        # 새 형식: sources 가 우선. confidence 는 무시 (Phase B 부터 derived).
        out = read_relation_sources(rel)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["doc_id"], "d1")

    def test_synthesizes_from_confidence_when_sources_missing(self):
        rel = {"target_id": "e_org_x", "confidence": 0.85}
        out = read_relation_sources(rel)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["weight"], 0.85)
        self.assertEqual(out[0]["role"], LEGACY_SOURCE_ROLE)
        self.assertIsNone(out[0]["doc_id"],
            "legacy back-fill must have doc_id=None — design §2 "
            "explicitly says pre-migration backref provenance is not "
            "recoverable")

    def test_no_confidence_no_sources_returns_empty(self):
        # Defensive — 정상적으로 ingest 된 relation 은 confidence 가
        # 항상 있다. 사용자가 직접 손편집한 비정상 frontmatter 도
        # 우아하게 처리한다.
        rel = {"target_id": "e_org_x"}
        self.assertEqual(read_relation_sources(rel), [])

    def test_none_input_returns_empty(self):
        self.assertEqual(read_relation_sources(None), [])

    def test_non_dict_input_returns_empty(self):
        self.assertEqual(read_relation_sources("not a dict"), [])
        self.assertEqual(read_relation_sources(["wrong shape"]), [])

    def test_sources_with_wrong_type_falls_through_to_confidence(self):
        # sources 키가 list 가 아닌 경우 — synthetic 복원으로 fallback.
        rel = {"target_id": "e_org_x", "confidence": 0.6, "sources": "oops"}
        out = read_relation_sources(rel)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["weight"], 0.6)
        self.assertEqual(out[0]["role"], LEGACY_SOURCE_ROLE)


class BuildLegacySourceTests(unittest.TestCase):
    """마이그레이션 스크립트가 채워 넣는 1-source back-fill row 의
    정확한 shape — Phase C cascade 가 ``role == legacy`` 를 보고
    file-delete 처리에서 제외한다."""

    def test_shape_exact(self):
        row = build_legacy_source(0.9, "2026-05-08T20:34:44.636574")
        self.assertEqual(row, {
            "doc_id": None,
            "weight": 0.9,
            "role":   "legacy",
            "ts":     "2026-05-08T20:34:44.636574",
        })

    def test_weight_is_float(self):
        # YAML / JSON round-trip 시 int 가 들어와도 float 으로 정규화.
        row = build_legacy_source(1, "2026-05-08")
        self.assertEqual(row["weight"], 1.0)
        self.assertIsInstance(row["weight"], float)

    def test_none_ts_allowed(self):
        # mtime 못 읽는 환경 (drive 손상 / 권한) 도 우아하게 처리.
        row = build_legacy_source(0.5, None)
        self.assertIsNone(row["ts"])
        self.assertEqual(row["weight"], 0.5)


if __name__ == "__main__":
    unittest.main()
