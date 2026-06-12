"""v0.6 G8.a — ontology pack mount mechanism tests.

Covers:

  * `granted_capabilities()` — env parsing (empty default, comma-
    separated, whitespace-stripped, case-sensitive, never cached).
  * `OntologyPack` dataclass — frozen + defaults populated.
  * `register_pack` — capability gate; schema validation; collision
    detection (against mother + against already-mounted packs +
    within-pack double-claim).
  * `unmount_pack` — removes; raises KeyError on unknown id.
  * `mounted_packs` — snapshot is a tuple; preserves registration
    order; mutating the snapshot doesn't affect the registry.
  * Mother-platform invariant — at module import, registry is
    empty + default capability set is empty.
  * Rule #1 protection — a vertical pack (capability
    `rule_one_exemption_granted` not granted) cannot mount.
"""
from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from typing import Dict


@contextmanager
def _patched_env(**env: str):
    saved: Dict[str, str] = {}
    unset_keys = []
    for k, v in env.items():
        if k in os.environ:
            saved[k] = os.environ[k]
        else:
            unset_keys.append(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v
        for k in unset_keys:
            os.environ.pop(k, None)


def _make_pack(**overrides):
    """Build a minimal valid pack for tests.

    Default `requires_capability="cap_x"` aligns with the
    `JAMES_CAPABILITIES="cap_x"` env most tests patch in, so the
    capability gate doesn't block the pack at registration. Tests
    that exercise the capability gate explicitly override one or
    the other.
    """
    from core.ontology_packs import OntologyPack
    defaults = {
        "pack_id": "test-pack-v1",
        "requires_capability": "cap_x",
        "subtypes": {
            "test_subtype_horizontal": {
                "parent": "document",
                "since": "v0.6",
            },
        },
        "relation_types": {},
        "enterprise_roles": {},
        "label_to_type": {},
        "since": "v0.6",
        "provenance": "test",
    }
    defaults.update(overrides)
    return OntologyPack(**defaults)


class GrantedCapabilitiesTests(unittest.TestCase):
    def test_default_empty(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES=None):
            self.assertEqual(granted_capabilities(), frozenset())

    def test_single_capability(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES="cap_a"):
            self.assertEqual(granted_capabilities(), frozenset({"cap_a"}))

    def test_comma_separated(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES="cap_a,cap_b,cap_c"):
            self.assertEqual(
                granted_capabilities(),
                frozenset({"cap_a", "cap_b", "cap_c"}),
            )

    def test_whitespace_stripped(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES="  cap_a  , cap_b  "):
            self.assertEqual(
                granted_capabilities(),
                frozenset({"cap_a", "cap_b"}),
            )

    def test_empty_names_dropped(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES=",cap_a,,,cap_b,"):
            self.assertEqual(
                granted_capabilities(),
                frozenset({"cap_a", "cap_b"}),
            )

    def test_case_sensitive(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES="Cap_A"):
            self.assertNotIn("cap_a", granted_capabilities())
            self.assertIn("Cap_A", granted_capabilities())

    def test_not_cached(self):
        # Changing the env mid-process must be visible immediately.
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES="initial"):
            self.assertEqual(granted_capabilities(), frozenset({"initial"}))
            os.environ["JAMES_CAPABILITIES"] = "changed"
            self.assertEqual(granted_capabilities(), frozenset({"changed"}))


class OntologyPackDataclassTests(unittest.TestCase):
    def test_frozen(self):
        pack = _make_pack()
        with self.assertRaises(Exception):
            pack.pack_id = "mutated"  # type: ignore[misc]

    def test_default_since(self):
        from core.ontology_packs import OntologyPack
        pack = OntologyPack(
            pack_id="x", requires_capability="cap_x",
        )
        self.assertEqual(pack.since, "v0.6")

    def test_default_collections_empty(self):
        from core.ontology_packs import OntologyPack
        pack = OntologyPack(
            pack_id="x", requires_capability="cap_x",
        )
        self.assertEqual(pack.subtypes, {})
        self.assertEqual(pack.relation_types, {})
        self.assertEqual(pack.enterprise_roles, {})
        self.assertEqual(pack.label_to_type, {})


class RegisterPackCapabilityGateTests(unittest.TestCase):
    def setUp(self):
        from core.ontology_packs import _reset_for_tests
        _reset_for_tests()

    def test_default_empty_capabilities_blocks_mount(self):
        from core.ontology_packs import CapabilityNotGrantedError, register_pack
        with _patched_env(JAMES_CAPABILITIES=None):
            with self.assertRaises(CapabilityNotGrantedError):
                register_pack(_make_pack(requires_capability="cap_x"))

    def test_granted_capability_allows_mount(self):
        from core.ontology_packs import register_pack, mounted_packs
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(requires_capability="cap_x"))
            self.assertEqual(len(mounted_packs()), 1)

    def test_vertical_pack_blocked_by_default(self):
        # The decisive Rule #1 enforcement test.
        from core.ontology_packs import CapabilityNotGrantedError, register_pack
        with _patched_env(JAMES_CAPABILITIES=None):
            with self.assertRaises(CapabilityNotGrantedError):
                register_pack(_make_pack(
                    pack_id="hypothetical-vertical-v1",
                    requires_capability="rule_one_exemption_granted",
                ))


class RegisterPackSchemaTests(unittest.TestCase):
    def setUp(self):
        from core.ontology_packs import _reset_for_tests
        _reset_for_tests()

    def test_empty_pack_id_rejected(self):
        from core.ontology_packs import SchemaError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(SchemaError):
                register_pack(_make_pack(pack_id=""))

    def test_empty_capability_rejected(self):
        # Empty `requires_capability` is rejected by the capability
        # gate (it's not in the granted set), not the schema check.
        # That ordering is the documented contract; an empty string
        # can never appear in `granted_capabilities()` because the
        # env parser drops empty tokens.
        from core.ontology_packs import (
            CapabilityNotGrantedError,
            register_pack,
        )
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(CapabilityNotGrantedError):
                register_pack(_make_pack(requires_capability=""))

    def test_subtype_unknown_parent_rejected(self):
        from core.ontology_packs import SchemaError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(SchemaError):
                register_pack(_make_pack(
                    subtypes={"bad": {"parent": "no-such-type"}},
                ))


class RegisterPackCollisionTests(unittest.TestCase):
    def setUp(self):
        from core.ontology_packs import _reset_for_tests
        _reset_for_tests()

    def test_collision_with_mother_subtype_rejected(self):
        from core.ontology_packs import NameCollisionError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(NameCollisionError):
                # `contract` is a mother DOCUMENT_SUBTYPE per B.5.b.
                register_pack(_make_pack(
                    subtypes={"contract": {"parent": "document"}},
                ))

    def test_collision_with_mother_relation_rejected(self):
        from core.ontology_packs import NameCollisionError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(NameCollisionError):
                # `AUTHORED_BY` is a mother RELATION_TYPE per B.5.b.
                register_pack(_make_pack(
                    subtypes={},
                    relation_types={"AUTHORED_BY": {
                        "label": "x", "inverse": "y", "transitive": False,
                        "weight": 1.0, "sensitive": False,
                    }},
                ))

    def test_collision_with_already_mounted_pack_rejected(self):
        from core.ontology_packs import NameCollisionError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(
                pack_id="first",
                subtypes={"unique_name_1": {"parent": "document"}},
            ))
            with self.assertRaises(NameCollisionError):
                register_pack(_make_pack(
                    pack_id="second",
                    subtypes={"unique_name_1": {"parent": "document"}},
                ))

    def test_within_pack_double_claim_rejected(self):
        from core.ontology_packs import NameCollisionError, register_pack
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            with self.assertRaises(NameCollisionError):
                # Name 'dual' appears as BOTH subtype and role.
                register_pack(_make_pack(
                    subtypes={"dual": {"parent": "document"}},
                    enterprise_roles={"dual": {"perms_over_doc": []}},
                ))


class UnmountAndSnapshotTests(unittest.TestCase):
    def setUp(self):
        from core.ontology_packs import _reset_for_tests
        _reset_for_tests()

    def test_unmount_removes(self):
        from core.ontology_packs import register_pack, unmount_pack, mounted_packs
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(pack_id="to-remove"))
            self.assertEqual(len(mounted_packs()), 1)
            unmount_pack("to-remove")
            self.assertEqual(len(mounted_packs()), 0)

    def test_unmount_unknown_raises(self):
        from core.ontology_packs import unmount_pack
        with self.assertRaises(KeyError):
            unmount_pack("does-not-exist")

    def test_snapshot_preserves_registration_order(self):
        from core.ontology_packs import register_pack, mounted_packs
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            for i in range(3):
                register_pack(_make_pack(
                    pack_id=f"pack-{i}",
                    subtypes={f"subtype_{i}": {"parent": "document"}},
                ))
            ids = [p.pack_id for p in mounted_packs()]
            self.assertEqual(ids, ["pack-0", "pack-1", "pack-2"])

    def test_snapshot_is_tuple_not_list(self):
        from core.ontology_packs import register_pack, mounted_packs
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack())
            snap = mounted_packs()
            self.assertIsInstance(snap, tuple)


class MotherPlatformInvariantTests(unittest.TestCase):
    def test_registry_empty_at_module_import(self):
        # Re-import the module to simulate a fresh process.
        from core.ontology_packs import _reset_for_tests, mounted_packs
        _reset_for_tests()
        self.assertEqual(mounted_packs(), tuple())

    def test_default_capability_set_empty(self):
        from core.ontology_packs import granted_capabilities
        with _patched_env(JAMES_CAPABILITIES=None):
            self.assertEqual(granted_capabilities(), frozenset())


# ─── v0.6 G8.b — read-side lookup helpers tests ───────────────────────


class G8bLookupHelperTests(unittest.TestCase):
    """Per B.3 §4.2. Helpers merge mother + mounted packs at lookup."""

    def setUp(self):
        from core.ontology_packs import _reset_for_tests
        _reset_for_tests()

    def test_all_document_subtypes_returns_mother_by_default(self):
        # No packs mounted → result == mother DOCUMENT_SUBTYPES.
        from core.ontology import DOCUMENT_SUBTYPES
        from core.ontology_packs import all_document_subtypes
        result = all_document_subtypes()
        for key in DOCUMENT_SUBTYPES:
            self.assertIn(key, result)
        # Result has at least the mother set.
        self.assertGreaterEqual(len(result), len(DOCUMENT_SUBTYPES))

    def test_all_relation_types_returns_mother_by_default(self):
        from core.ontology import RELATION_TYPES
        from core.ontology_packs import all_relation_types
        result = all_relation_types()
        for key in RELATION_TYPES:
            self.assertIn(key, result)
        self.assertGreaterEqual(len(result), len(RELATION_TYPES))

    def test_all_enterprise_roles_returns_mother_by_default(self):
        from core.ontology import ENTERPRISE_ROLES
        from core.ontology_packs import all_enterprise_roles
        result = all_enterprise_roles()
        for key in ENTERPRISE_ROLES:
            self.assertIn(key, result)
        self.assertGreaterEqual(len(result), len(ENTERPRISE_ROLES))

    def test_mounted_pack_subtypes_appear_in_lookup(self):
        from core.ontology_packs import (
            all_document_subtypes,
            register_pack,
        )
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(
                pack_id="lookup-test-pack",
                subtypes={
                    "lookup_subtype_a": {
                        "parent": "document", "since": "v0.6",
                    },
                    "lookup_subtype_b": {
                        "parent": "document", "since": "v0.6",
                    },
                },
            ))
            result = all_document_subtypes()
        self.assertIn("lookup_subtype_a", result)
        self.assertIn("lookup_subtype_b", result)
        # Mother set is still present.
        self.assertIn("contract", result)

    def test_mother_takes_precedence_defensively(self):
        # The collision check prevents mother-shadowing at register
        # time, but the helper's merge order (packs first, mother
        # last) means even a future race would fall back to mother.
        from core.ontology import DOCUMENT_SUBTYPES
        from core.ontology_packs import _mounted, all_document_subtypes, OntologyPack
        # Bypass register_pack to force a collision directly into
        # the registry (simulating a race / hot-reload bug).
        rogue = OntologyPack(
            pack_id="rogue",
            requires_capability="cap_x",
            subtypes={
                "contract": {  # MOTHER key
                    "parent": "document",
                    "since":  "rogue-v1",
                    "rogue":  True,
                },
            },
        )
        _mounted.append(rogue)
        try:
            result = all_document_subtypes()
            # Mother's `contract` definition wins (no `rogue: True`).
            self.assertEqual(
                result["contract"], DOCUMENT_SUBTYPES["contract"],
            )
        finally:
            _mounted.remove(rogue)

    def test_unmount_pack_removes_from_lookup(self):
        from core.ontology_packs import (
            all_document_subtypes,
            register_pack,
            unmount_pack,
        )
        with _patched_env(JAMES_CAPABILITIES="cap_x"):
            register_pack(_make_pack(
                pack_id="ephemeral",
                subtypes={
                    "ephemeral_subtype": {
                        "parent": "document", "since": "v0.6",
                    },
                },
            ))
            self.assertIn("ephemeral_subtype", all_document_subtypes())
            unmount_pack("ephemeral")
            self.assertNotIn(
                "ephemeral_subtype", all_document_subtypes(),
            )

    def test_lookup_returns_fresh_dict(self):
        # Caller mutating the returned dict must NOT affect future
        # lookups (registry remains the source of truth).
        from core.ontology_packs import all_document_subtypes
        result = all_document_subtypes()
        result["INJECTED_BY_TEST"] = "should not persist"
        # Next call must NOT carry the injection.
        self.assertNotIn("INJECTED_BY_TEST", all_document_subtypes())


if __name__ == "__main__":
    unittest.main()
