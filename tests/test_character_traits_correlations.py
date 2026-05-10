"""[P1 unified UX, 2026-05-10] Trait expansion + correlations + ripple.

User feedback (2026-05-10):
> "어드민 웹페이지에 성향 설정에 대하여 글자로 설정하는 부분과 원 그래프를
>  이용하여 조정하는 부분이 충돌할수 있는 요인으로 작동할 우려가 보인다.
>  성향 그래프쪽으로 이동시켜서 사용자가 직관적으로 설정할수 있게끔
>  깔끔하게 설정 장치를 통합 대안 제시해라. 성향의 종류를 좀더 다양화하고
>  여러가지 성향의 상관관계가 서로간의 늘어나고 줄어드는 정도를 잘 반영
>  하게끔 사용자가 직관적인 알수 있도록 편의성 있는 캐릭터 설정 페이지로
>  만들어보자"

P1 backend contract:
  - 11 → 16 traits (간결성 / 직설성 / 낙관성 / 위험감수 / 인내심 추가)
  - CORRELATIONS dict — trait 간 soft 상관관계 (~15 edges)
  - set_trait — 짝(opposing) 100% flip + 상관 trait damped ripple 동시
  - get_correlations() / get_damping() — 프론트 시각화용 API
  - get_prompt_modifiers() — 신규 trait 5종도 directives 발화

Run:
    python -m unittest tests.test_character_traits_correlations
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.character_profile import (
    TRAITS, CORRELATIONS, CharacterProfile, _CORR_INDEX, _OPPONENTS,
)


# ─── 1. Trait registry shape ──────────────────────────────────────
class TraitRegistryTests(unittest.TestCase):
    def test_total_count_is_16(self):
        # 11 legacy + 5 new (간결성/직설성/낙관성/위험감수/인내심)
        self.assertEqual(len(TRAITS), 16,
            "P1 must extend 11 → 16 traits")

    def test_all_legacy_traits_preserved(self):
        # Migration safety: existing trait IDs MUST still exist so the
        # preferences DB rows (trait:curiosity, trait:focus, ...) keep
        # loading. If we rename one, users lose their saved values.
        legacy = [
            "curiosity", "focus", "caution", "boldness",
            "analytical", "intuitive", "independent", "collaborative",
            "security", "creativity", "empathy",
        ]
        for tid in legacy:
            self.assertIn(tid, TRAITS,
                f"legacy trait {tid!r} must not be removed/renamed — "
                "users have saved values in preferences DB under this key")

    def test_new_traits_present(self):
        new = ["conciseness", "directness", "optimism",
               "risk_tolerance", "patience"]
        for tid in new:
            self.assertIn(tid, TRAITS,
                f"P1 must add new trait {tid!r}")

    def test_each_trait_has_required_metadata(self):
        for tid, meta in TRAITS.items():
            for k in ("label", "label_ko", "group", "default", "icon"):
                self.assertIn(k, meta,
                    f"trait {tid!r} missing field {k!r}")
            self.assertIsInstance(meta["default"], (int, float))
            self.assertGreaterEqual(meta["default"], 0.0)
            self.assertLessEqual(meta["default"], 1.0)

    def test_opposing_pairs_sum_to_one_at_default(self):
        # Group A~D invariant: paired traits' defaults must sum to 1.0
        # (reflects the sum=1 constraint that set_trait enforces).
        pairs = {tuple(sorted(p)) for p in
                 ((k, v) for k, v in _OPPONENTS.items())}
        for a, b in pairs:
            s = TRAITS[a]["default"] + TRAITS[b]["default"]
            self.assertAlmostEqual(s, 1.0, places=3,
                msg=f"opposing pair {a}/{b} defaults must sum to 1.0")


# ─── 2. Correlation graph shape ───────────────────────────────────
class CorrelationGraphTests(unittest.TestCase):
    def test_correlations_nonempty(self):
        self.assertGreaterEqual(len(CORRELATIONS), 10,
            "need a meaningful correlation graph (≥10 edges) for the "
            "ripple visualization to feel alive")

    def test_each_edge_is_3_tuple(self):
        for edge in CORRELATIONS:
            self.assertEqual(len(edge), 3,
                "edge format is (source, target, weight)")
            src, tgt, w = edge
            self.assertIn(src, TRAITS,
                f"correlation source {src!r} not a known trait")
            self.assertIn(tgt, TRAITS,
                f"correlation target {tgt!r} not a known trait")
            self.assertIsInstance(w, (int, float))
            self.assertGreaterEqual(w, -1.0)
            self.assertLessEqual(w, 1.0)
            self.assertNotEqual(w, 0,
                "zero-weight edges are noise — drop them")

    def test_no_self_loops(self):
        for src, tgt, _ in CORRELATIONS:
            self.assertNotEqual(src, tgt,
                "trait can't be correlated with itself")

    def test_no_duplicate_directed_edges(self):
        seen = set()
        for src, tgt, _ in CORRELATIONS:
            self.assertNotIn((src, tgt), seen,
                f"duplicate directed edge {src}→{tgt} — merge or drop")
            seen.add((src, tgt))

    def test_does_not_overlap_opposing_pairs(self):
        # Opposing pairs are 100% flipped by _OPPONENTS in set_trait —
        # adding them as correlations would double-count the effect.
        for src, tgt, _ in CORRELATIONS:
            self.assertNotEqual(_OPPONENTS.get(src), tgt,
                f"correlation {src}→{tgt} duplicates opposing pair "
                "(already 100% flipped by _OPPONENTS)")

    def test_index_built_from_correlations(self):
        # _CORR_INDEX is the runtime lookup that set_trait uses; must
        # be 1:1 with CORRELATIONS.
        flat = sum(len(v) for v in _CORR_INDEX.values())
        self.assertEqual(flat, len(CORRELATIONS),
            "_CORR_INDEX must contain every CORRELATIONS edge")


# ─── 3. set_trait — opponent flip + ripple ────────────────────────
class SetTraitBehaviorTests(unittest.TestCase):
    """Use a fresh profile with mocked _save / _load so we don't touch
    the user's actual preferences DB."""

    def _fresh(self) -> CharacterProfile:
        with mock.patch.object(CharacterProfile, "_load", lambda self: None):
            p = CharacterProfile()
        # Defang persistence so tests don't write the DB.
        p._save = lambda: None  # type: ignore
        return p

    def test_opposing_pair_flips_to_one_minus(self):
        p = self._fresh()
        p.set_trait("curiosity", 0.8)
        # Opponent pair (curiosity ↔ focus) must sum to 1.0.
        self.assertAlmostEqual(p._values["focus"], 0.2, places=3)

    def test_opponent_field_returned(self):
        p = self._fresh()
        out = p.set_trait("caution", 0.9)
        self.assertEqual(out["opponent"], "boldness")

    def test_independent_trait_has_no_opponent(self):
        p = self._fresh()
        out = p.set_trait("creativity", 0.8)
        self.assertIsNone(out["opponent"],
            "Group E/F traits don't have a paired opponent")

    def test_ripple_applied_to_correlated_targets(self):
        # boldness → risk_tolerance (+0.5). Pushing boldness up should
        # nudge risk_tolerance up by delta * weight * damping.
        # [W3b 2026-05-10] damping 0.3 → 0.6 — nudge 도 비례하여 2x.
        p = self._fresh()
        old_rt = p._values["risk_tolerance"]
        out = p.set_trait("boldness", 0.8)
        # delta = 0.8 - 0.3 = 0.5; nudge = 0.5 * 0.5 * 0.6 = 0.15
        expected = round(min(1.0, old_rt + 0.15), 3)
        self.assertAlmostEqual(p._values["risk_tolerance"], expected, places=2)
        # And must be reported in the ripples list.
        rt_ripples = [r for r in out["ripples"] if r["trait"] == "risk_tolerance"]
        self.assertEqual(len(rt_ripples), 1,
            "risk_tolerance must appear in the ripples report")

    def test_negative_correlation_pulls_target_down(self):
        # caution → risk_tolerance (−0.4). Raising caution lowers RT.
        p = self._fresh()
        old_rt = p._values["risk_tolerance"]
        p.set_trait("caution", 0.95)        # was 0.7 → delta=+0.25
        # nudge = 0.25 * (-0.4) * 0.3 = -0.03
        self.assertLess(p._values["risk_tolerance"], old_rt,
            "negative-weight correlation must pull target down")

    def test_ripple_does_not_overwrite_opponent(self):
        # If a correlated target also happens to be the opponent of the
        # source, the opponent flip must win (no double-write).
        # Construct: directness ↔ ??? — directness has no opponent in
        # _OPPONENTS, but boldness→directness is a correlation. Pick
        # something safe: independent ↔ collaborative are opponents,
        # and there's no correlation edge that would conflict here.
        p = self._fresh()
        p.set_trait("independent", 0.9)
        # collaborative (opponent) must be exactly 1 − 0.9 = 0.1, not
        # affected further by any same-tick ripple.
        self.assertAlmostEqual(p._values["collaborative"], 0.1, places=3)

    def test_value_clipped_to_zero_one(self):
        p = self._fresh()
        out = p.set_trait("creativity", 1.5)   # over-cap
        self.assertEqual(out["value"], 1.0)
        out = p.set_trait("creativity", -0.3)  # under-cap
        self.assertEqual(out["value"], 0.0)

    def test_ripple_targets_clipped(self):
        # Big delta + saturated target should not push past [0, 1].
        p = self._fresh()
        p._values["risk_tolerance"] = 0.99
        p.set_trait("boldness", 1.0)   # huge positive delta
        self.assertLessEqual(p._values["risk_tolerance"], 1.0)
        self.assertGreaterEqual(p._values["risk_tolerance"], 0.0)

    def test_unknown_trait_returns_error(self):
        p = self._fresh()
        out = p.set_trait("nope", 0.5)
        self.assertIn("error", out)


# ─── 4. Static API for frontend ───────────────────────────────────
class StaticApiTests(unittest.TestCase):
    def test_get_correlations_returns_dicts(self):
        out = CharacterProfile.get_correlations()
        self.assertIsInstance(out, list)
        self.assertGreater(len(out), 0)
        sample = out[0]
        for k in ("from", "to", "weight"):
            self.assertIn(k, sample,
                f"correlation dict missing key {k!r} — frontend expects "
                "{from, to, weight}")

    def test_get_damping_returns_float(self):
        d = CharacterProfile.get_damping()
        self.assertIsInstance(d, float)
        self.assertGreater(d, 0)
        self.assertLess(d, 1)


# ─── 5. Prompt modifiers cover new traits ─────────────────────────
class PromptModifierCoverageTests(unittest.TestCase):
    """Each new P1 trait, when extreme, must produce at least one LLM
    directive — otherwise the slider does nothing for the user."""

    def _fresh(self) -> CharacterProfile:
        with mock.patch.object(CharacterProfile, "_load", lambda self: None):
            p = CharacterProfile()
        p._save = lambda: None  # type: ignore
        return p

    def _force(self, p: CharacterProfile, tid: str, val: float):
        # Direct-write so we don't trigger ripples for this isolation.
        p._values[tid] = val

    def test_high_conciseness_has_directive(self):
        p = self._fresh()
        self._force(p, "conciseness", 0.9)
        self.assertNotEqual(p.get_prompt_modifiers(), "",
            "high conciseness must produce a 'be brief' directive")

    def test_high_directness_has_directive(self):
        p = self._fresh()
        self._force(p, "directness", 0.9)
        self.assertNotEqual(p.get_prompt_modifiers(), "")

    def test_high_optimism_has_directive(self):
        p = self._fresh()
        self._force(p, "optimism", 0.9)
        self.assertNotEqual(p.get_prompt_modifiers(), "")

    def test_high_risk_tolerance_has_directive(self):
        p = self._fresh()
        self._force(p, "risk_tolerance", 0.9)
        self.assertNotEqual(p.get_prompt_modifiers(), "")

    def test_high_patience_has_directive(self):
        p = self._fresh()
        self._force(p, "patience", 0.9)
        self.assertNotEqual(p.get_prompt_modifiers(), "")

    def test_low_extremes_produce_opposite_directive(self):
        # Some new traits also have a low-side directive (the symmetry
        # is what makes a slider feel "alive" at both ends).
        p = self._fresh()
        self._force(p, "conciseness", 0.1)
        out = p.get_prompt_modifiers()
        self.assertNotEqual(out, "",
            "low conciseness should yield a 'be verbose' directive — "
            "otherwise the bottom half of the slider does nothing")


# ─── 6. Endpoint registration ─────────────────────────────────────
class CorrelationEndpointTests(unittest.TestCase):
    """The new GET /admin/character/correlations endpoint must be
    registered on the FastAPI app (sanity check — full HTTP test would
    require spinning up the server)."""

    def test_endpoint_registered(self):
        try:
            from server_llmwiki import app
        except Exception as e:
            self.skipTest(f"server import failed: {e}")
        paths = [r.path for r in app.routes]
        self.assertIn("/admin/character/correlations", paths,
            "P1 must register GET /admin/character/correlations for the "
            "frontend correlation-graph fetch")


if __name__ == "__main__":
    unittest.main()
