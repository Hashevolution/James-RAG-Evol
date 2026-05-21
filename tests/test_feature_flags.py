"""PROJECT JAMES — Cognitive feature-flag registry tests.

Pins the contract of `core/feature_flags.py` — the substrate the
admin Configure → Cognitive sub-page (PR-2) relies on.

The tests mutate `os.environ` in setUp/tearDown to keep the process
state clean for the next test. The registry covers six flags across
two polarity classes — both are exercised here.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.feature_flags import (  # noqa: E402
    COGNITIVE_FEATURE_FLAGS,
    COGNITIVE_FLAG_ORDER,
    _flag_is_on,
    apply_cognitive_flag,
    apply_cognitive_flags,
    read_cognitive_flags,
)


ALL_ENV_NAMES = {spec["env"] for spec in COGNITIVE_FEATURE_FLAGS.values()}


class _CleanEnvMixin:
    """Snapshot the relevant env vars at setUp, restore at tearDown.
    Other tests share `os.environ`, so leaking state here would be a
    cross-suite bug."""

    def setUp(self):
        self._snapshot = {n: os.environ.get(n) for n in ALL_ENV_NAMES}
        for n in ALL_ENV_NAMES:
            os.environ.pop(n, None)

    def tearDown(self):
        for n, v in self._snapshot.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v


# ─── Registry shape ─────────────────────────────────────────────


class RegistryShapeTests(_CleanEnvMixin, unittest.TestCase):
    # Inherit the env-clean mixin so test_default_matches_polarity_
    # with_empty_env actually sees an empty env when other tests in
    # the same run (test_planner / test_reflection_loop / etc.) have
    # left cognitive env vars set without cleanup.

    def test_six_flags_documented(self):
        self.assertEqual(len(COGNITIVE_FEATURE_FLAGS), 6)
        self.assertEqual(len(COGNITIVE_FLAG_ORDER), 6)

    def test_order_covers_every_flag_exactly_once(self):
        self.assertEqual(set(COGNITIVE_FLAG_ORDER),
                         set(COGNITIVE_FEATURE_FLAGS))

    def test_every_entry_has_required_fields(self):
        required = {"env", "polarity", "label", "default", "module"}
        for key, spec in COGNITIVE_FEATURE_FLAGS.items():
            with self.subTest(key=key):
                self.assertTrue(required.issubset(spec.keys()),
                    f"flag {key} missing fields: "
                    f"{required - set(spec.keys())}")
                self.assertIn(spec["polarity"], ("enable", "disable"))
                self.assertIsInstance(spec["default"], bool)

    def test_env_names_are_unique(self):
        envs = [s["env"] for s in COGNITIVE_FEATURE_FLAGS.values()]
        self.assertEqual(len(envs), len(set(envs)),
            "env vars must not be reused across flags")

    def test_default_matches_polarity_with_empty_env(self):
        # Default state with no env set must match the spec's
        # `default` field — otherwise an admin who never touches
        # any flag sees a different state than the contract
        # advertises.
        for key in COGNITIVE_FLAG_ORDER:
            spec = COGNITIVE_FEATURE_FLAGS[key]
            on = _flag_is_on(spec["env"], spec["polarity"])
            with self.subTest(key=key):
                self.assertEqual(on, spec["default"],
                    f"{key} default {spec['default']} does not match "
                    f"polarity {spec['polarity']} with env unset")


# ─── Read ───────────────────────────────────────────────────────


class ReadCognitiveFlagsTests(_CleanEnvMixin, unittest.TestCase):

    def test_returns_six_entries_in_canonical_order(self):
        out = read_cognitive_flags()
        self.assertEqual([e["key"] for e in out], COGNITIVE_FLAG_ORDER)

    def test_each_entry_carries_the_documented_fields(self):
        out = read_cognitive_flags()
        for entry in out:
            for f in ("key", "label", "env", "polarity",
                      "default", "on", "module"):
                self.assertIn(f, entry)

    def test_default_state_with_no_env_matches_specs(self):
        # All env popped in setUp → flags should resolve to their
        # documented defaults.
        out = read_cognitive_flags()
        for entry in out:
            with self.subTest(key=entry["key"]):
                self.assertEqual(entry["on"], entry["default"])

    def test_enable_polarity_env_one_flips_on(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"
        out = {e["key"]: e["on"] for e in read_cognitive_flags()}
        self.assertTrue(out["reflect"])
        # Others stay at their default.
        self.assertFalse(out["query_rewrite"])

    def test_disable_polarity_env_one_flips_off(self):
        os.environ["JAMES_DISABLE_VERIFY"] = "1"
        out = {e["key"]: e["on"] for e in read_cognitive_flags()}
        self.assertFalse(out["verify"])
        self.assertTrue(out["rerank"], "rerank default ON should stay ON")

    def test_non_one_value_treated_as_unset(self):
        # The polarity check is strict equality with "1" — any other
        # value (including "true", "yes", "0") is unset.
        os.environ["JAMES_ENABLE_REFLECT"] = "true"
        out = {e["key"]: e["on"] for e in read_cognitive_flags()}
        self.assertFalse(out["reflect"],
            "polarity gate is strict '1' — other truthy strings must "
            "not flip the flag")


# ─── Write ──────────────────────────────────────────────────────


class ApplyCognitiveFlagTests(_CleanEnvMixin, unittest.TestCase):

    def test_enable_polarity_on_sets_env_to_one(self):
        d = apply_cognitive_flag("reflect", True)
        self.assertEqual(d, {
            "key":    "reflect",
            "env":    "JAMES_ENABLE_REFLECT",
            "before": False,
            "after":  True,
        })
        self.assertEqual(os.environ.get("JAMES_ENABLE_REFLECT"), "1")

    def test_enable_polarity_off_pops_env(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"
        d = apply_cognitive_flag("reflect", False)
        self.assertFalse(d["after"])
        self.assertIsNone(os.environ.get("JAMES_ENABLE_REFLECT"),
            "OFF must pop the env var (not set to '0')")

    def test_disable_polarity_off_sets_env_to_one(self):
        d = apply_cognitive_flag("verify", False)
        self.assertEqual(d["before"], True)
        self.assertEqual(d["after"], False)
        self.assertEqual(os.environ.get("JAMES_DISABLE_VERIFY"), "1")

    def test_disable_polarity_on_pops_env(self):
        os.environ["JAMES_DISABLE_VERIFY"] = "1"
        d = apply_cognitive_flag("verify", True)
        self.assertTrue(d["after"])
        self.assertIsNone(os.environ.get("JAMES_DISABLE_VERIFY"),
            "ON (default) for disable-polarity must pop the env var")

    def test_idempotent_repeated_on_off_cycles(self):
        # Toggling repeatedly should never leave the env table in a
        # surprising state — pop / set / pop / set never accumulates.
        for _ in range(3):
            apply_cognitive_flag("planner", True)
            self.assertEqual(os.environ.get("JAMES_ENABLE_PLANNER"), "1")
            apply_cognitive_flag("planner", False)
            self.assertIsNone(os.environ.get("JAMES_ENABLE_PLANNER"))

    def test_unknown_key_raises(self):
        with self.assertRaisesRegex(ValueError, "unknown cognitive flag"):
            apply_cognitive_flag("does_not_exist", True)


class ApplyCognitiveFlagsBulkTests(_CleanEnvMixin, unittest.TestCase):

    def test_bulk_apply_returns_per_key_delta(self):
        out = apply_cognitive_flags({
            "reflect":      True,
            "planner":      True,
            "verify":       False,
        })
        self.assertEqual(len(out), 3)
        keys = {d["key"] for d in out}
        self.assertEqual(keys, {"reflect", "planner", "verify"})
        # All three transitioned from their default.
        self.assertEqual(os.environ.get("JAMES_ENABLE_REFLECT"), "1")
        self.assertEqual(os.environ.get("JAMES_ENABLE_PLANNER"), "1")
        self.assertEqual(os.environ.get("JAMES_DISABLE_VERIFY"), "1")

    def test_bulk_rejects_non_bool_value(self):
        with self.assertRaisesRegex(ValueError, "must be bool"):
            apply_cognitive_flags({"reflect": "yes"})  # type: ignore[arg-type]

    def test_bulk_raises_on_unknown_key(self):
        # Behaviour note: prior writes already landed. The exception
        # message should make it clear which key failed.
        with self.assertRaisesRegex(ValueError, "unknown cognitive flag"):
            apply_cognitive_flags({
                "reflect":         True,    # this lands
                "does_not_exist":  True,    # this raises
            })
        # Validate the prior write landed (documented semantics).
        self.assertEqual(os.environ.get("JAMES_ENABLE_REFLECT"), "1")


if __name__ == "__main__":
    unittest.main()
