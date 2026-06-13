"""v0.6 Phase 3 P3.2 — per-tenant workspace path resolver tests.

Validates `get_workspace_root_for_tenant` against:

  * Default-off behaviour (preserves byte-identical pre-Phase-3
    behaviour when `JAMES_WORKSPACE_PER_TENANT` is unset)
  * Per-tenant mode resolves `<workspace>/<tenant_id>/` paths
  * Path-safety validation — strict tenant id pattern rejects
    traversal and shell-metachar attempts
  * Integration with `current_tenant_id()` async stack — when no
    explicit tenant_id is passed, the resolver consults the
    per-request scope from
    `core.security.tenant_request.TenantHeaderMiddleware`
  * Directory auto-creation on first resolve

Run:
  python -m unittest tests.test_v06_workspace_per_tenant
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@contextmanager
def _patched_env(**env):
    saved = {}
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
        for k in env:
            if k not in saved and k not in unset_keys:
                os.environ.pop(k, None)


class DefaultOffBehaviourTests(unittest.TestCase):
    """Without the env flag the resolver MUST be byte-identical to
    the pre-Phase-3 ``get_workspace_root``."""

    def test_flag_unset_returns_base_root(self):
        from core.plugins.workspace import (
            get_workspace_root, get_workspace_root_for_tenant,
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            env = {"JAMES_WORKSPACE": str(base)}
            self.assertEqual(
                get_workspace_root_for_tenant("acme", env=env),
                get_workspace_root(env=env),
            )

    def test_flag_unset_with_no_tenant_returns_base_root(self):
        from core.plugins.workspace import (
            get_workspace_root, get_workspace_root_for_tenant,
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {"JAMES_WORKSPACE": str(Path(tmp).resolve())}
            self.assertEqual(
                get_workspace_root_for_tenant(None, env=env),
                get_workspace_root(env=env),
            )

    def test_explicit_falsy_flag_treated_as_off(self):
        from core.plugins.workspace import (
            get_workspace_root, get_workspace_root_for_tenant,
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "JAMES_WORKSPACE": str(Path(tmp).resolve()),
                "JAMES_WORKSPACE_PER_TENANT": "0",
            }
            self.assertEqual(
                get_workspace_root_for_tenant("acme", env=env),
                get_workspace_root(env=env),
            )


class PerTenantModeTests(unittest.TestCase):
    def test_returns_per_tenant_subdirectory(self):
        from core.plugins.workspace import get_workspace_root_for_tenant
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            env = {
                "JAMES_WORKSPACE": str(base),
                "JAMES_WORKSPACE_PER_TENANT": "1",
            }
            result = get_workspace_root_for_tenant("acme", env=env)
            self.assertEqual(result, base / "acme")
            self.assertTrue(result.exists())
            self.assertTrue(result.is_dir())

    def test_truthy_synonyms_for_flag(self):
        from core.plugins.workspace import get_workspace_root_for_tenant
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            for synonym in ("1", "true", "yes", "on", "enabled",
                            "TRUE", "Yes"):
                env = {
                    "JAMES_WORKSPACE": str(base),
                    "JAMES_WORKSPACE_PER_TENANT": synonym,
                }
                result = get_workspace_root_for_tenant("test-tenant",
                                                       env=env)
                self.assertEqual(
                    result, base / "test-tenant",
                    f"truthy synonym {synonym!r} not recognised",
                )

    def test_directory_auto_created_on_first_resolve(self):
        # The tenant subdir does not exist initially → resolver
        # creates it (so operators don't have to mkdir per tenant).
        from core.plugins.workspace import get_workspace_root_for_tenant
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            env = {
                "JAMES_WORKSPACE": str(base),
                "JAMES_WORKSPACE_PER_TENANT": "1",
            }
            target = base / "newtenant"
            self.assertFalse(target.exists())
            result = get_workspace_root_for_tenant("newtenant", env=env)
            self.assertEqual(result, target)
            self.assertTrue(target.exists())

    def test_multiple_tenants_isolated_paths(self):
        from core.plugins.workspace import get_workspace_root_for_tenant
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            env = {
                "JAMES_WORKSPACE": str(base),
                "JAMES_WORKSPACE_PER_TENANT": "1",
            }
            acme = get_workspace_root_for_tenant("acme", env=env)
            globex = get_workspace_root_for_tenant("globex", env=env)
            self.assertNotEqual(acme, globex)
            self.assertEqual(acme.parent, globex.parent)
            self.assertEqual(acme.parent, base)


class PathSafetyValidationTests(unittest.TestCase):
    """The strict tenant id pattern MUST reject traversal + shell
    metachar attempts."""

    def setUp(self):
        from core.plugins.workspace import PluginLoadError
        self._exc = PluginLoadError

    def _resolve(self, tenant_id):
        from core.plugins.workspace import get_workspace_root_for_tenant
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "JAMES_WORKSPACE": str(Path(tmp).resolve()),
                "JAMES_WORKSPACE_PER_TENANT": "1",
            }
            return get_workspace_root_for_tenant(tenant_id, env=env)

    def test_path_traversal_rejected(self):
        for evil in ("..", "../etc", "../../etc/passwd", "acme/../globex"):
            with self.assertRaises(self._exc, msg=f"accepted: {evil!r}"):
                self._resolve(evil)

    def test_absolute_path_rejected(self):
        for evil in ("/etc/passwd", "/home/attacker"):
            with self.assertRaises(self._exc):
                self._resolve(evil)

    def test_shell_metachar_rejected(self):
        for evil in ("acme;rm -rf /", "acme$(whoami)", "acme`id`",
                     "acme&disk", "acme|ls"):
            with self.assertRaises(self._exc):
                self._resolve(evil)

    def test_dot_in_tenant_id_rejected(self):
        # Dots COULD be safe but historically have been a CVE source
        # (Windows trailing-dot quirks; Unicode normalisation).
        # Pattern rejects them.
        for evil in ("acme.corp", "acme.", ".acme"):
            with self.assertRaises(self._exc):
                self._resolve(evil)

    def test_uppercase_rejected(self):
        # Case-folding ambiguity on Windows / macOS filesystems would
        # let two "different" tenants resolve to the same dir. Strict
        # lowercase pattern.
        for evil in ("Acme", "ACME"):
            with self.assertRaises(self._exc):
                self._resolve(evil)

    def test_empty_tenant_id_falls_back_to_base(self):
        # Empty / None tenant_id in per-tenant mode → resolver
        # asks current_tenant_id(). If that also returns None →
        # safe fallback to the base root.
        from core.plugins.workspace import (
            get_workspace_root, get_workspace_root_for_tenant,
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "JAMES_WORKSPACE": str(Path(tmp).resolve()),
                "JAMES_WORKSPACE_PER_TENANT": "1",
            }
            # No async/sync override; current_tenant_id() returns None.
            self.assertEqual(
                get_workspace_root_for_tenant(None, env=env),
                get_workspace_root(env=env),
            )


class IntegrationWithCurrentTenantTests(unittest.TestCase):
    """When tenant_id arg is None, the resolver consults
    ``current_tenant_id()`` from the async/sync tenant stack."""

    def test_picks_up_async_tenant_scope(self):
        from core.plugins.workspace import get_workspace_root_for_tenant
        from core.lifecycle.tenant import with_tenant_id_async

        async def case():
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve()
                env = {
                    "JAMES_WORKSPACE": str(base),
                    "JAMES_WORKSPACE_PER_TENANT": "1",
                }
                async with with_tenant_id_async("acme"):
                    # No explicit tenant_id arg — resolver should
                    # consult the async stack.
                    result = get_workspace_root_for_tenant(None, env=env)
                self.assertEqual(result, base / "acme")

        asyncio.run(case())

    def test_explicit_tenant_id_overrides_async_scope(self):
        from core.plugins.workspace import get_workspace_root_for_tenant
        from core.lifecycle.tenant import with_tenant_id_async

        async def case():
            with tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp).resolve()
                env = {
                    "JAMES_WORKSPACE": str(base),
                    "JAMES_WORKSPACE_PER_TENANT": "1",
                }
                async with with_tenant_id_async("acme"):
                    # Explicit arg overrides the async scope.
                    result = get_workspace_root_for_tenant("globex",
                                                           env=env)
                self.assertEqual(result, base / "globex")

        asyncio.run(case())


if __name__ == "__main__":
    unittest.main()
