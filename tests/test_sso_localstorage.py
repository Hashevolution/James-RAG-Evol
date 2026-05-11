"""Chat ↔ Admin SSO via shared localStorage (item #A8-4, 2026-05-09).

User feedback: "챗 페이지 어드민 페이지 중 어느 하나에 로그인 하면
둘다 자동 로그인 처리되도록 로그인 시스템 통합".

Before:
  - chat.js mixed sessionStorage (token) + localStorage (role)
  - admin.js used sessionStorage for both token + role
  → sessionStorage is per-tab so opening admin.html in a new tab
    after chat login lost the session.

After:
  - Both pages use localStorage for james_token + james_role.
  - Initial load migrates any leftover sessionStorage values.
  - Both pages add a 'storage' event listener to react to cross-tab
    auth changes (login in one tab → other tab updates badge or
    closes modal).

Run:
  python -m unittest tests.test_sso_localstorage
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
CHAT_JS  = ROOT / "frontend" / "static" / "chat.js"
ADMIN_JS = ROOT / "frontend" / "static" / "admin.js"


class StorageBackendTests(unittest.TestCase):
    """All james_token / james_role accesses must go through localStorage."""

    @classmethod
    def setUpClass(cls):
        cls.chat = CHAT_JS.read_text(encoding="utf-8")
        cls.admin = ADMIN_JS.read_text(encoding="utf-8")

    def _count_session_token_role(self, src):
        """Count remaining sessionStorage references to james_token /
        james_role (both get/set/removeItem)."""
        pattern = r"sessionStorage\.(get|set|remove)Item\(['\"]james_(token|role)"
        return len(re.findall(pattern, src))

    def test_chat_no_session_token_role(self):
        # The migration block at the top is allowed to read sessionStorage
        # ONCE — but only inside the migration IIFE. Outside the migration,
        # all references must be localStorage.
        # Count the total references and subtract the migration ones (2:
        # one getItem for james_token, one for james_role).
        total = self._count_session_token_role(self.chat)
        # Migration block reads each key with getItem once.
        migration_idx = self.chat.index("_migrateSessionToLocal")
        migration_end = self.chat.index("})()", migration_idx)
        migration_block = self.chat[migration_idx:migration_end]
        migration_refs = self._count_session_token_role(migration_block)
        non_migration = total - migration_refs
        self.assertEqual(non_migration, 0,
            f"chat.js still has {non_migration} non-migration sessionStorage "
            f"references to james_token/role — should all be localStorage")

    def test_admin_no_session_token_role(self):
        total = self._count_session_token_role(self.admin)
        migration_idx = self.admin.index("_migrateAdminSessionToLocal")
        migration_end = self.admin.index("})()", migration_idx)
        migration_block = self.admin[migration_idx:migration_end]
        migration_refs = self._count_session_token_role(migration_block)
        non_migration = total - migration_refs
        self.assertEqual(non_migration, 0,
            f"admin.js still has {non_migration} non-migration sessionStorage "
            f"references to james_token/role — should all be localStorage")

    def test_chat_initial_token_read_from_localstorage(self):
        self.assertIn("localStorage.getItem('james_token')", self.chat,
            "chat.js must read initial token from localStorage")
        self.assertIn("localStorage.getItem('james_role')", self.chat,
            "chat.js must read initial role from localStorage")

    def test_admin_initial_token_read_from_localstorage(self):
        self.assertIn("localStorage.getItem('james_token')", self.admin,
            "admin.js must read initial token from localStorage")
        self.assertIn("localStorage.getItem('james_role')", self.admin,
            "admin.js must check role from localStorage on init")


class MigrationTests(unittest.TestCase):
    """One-shot migration from sessionStorage → localStorage on first load."""

    @classmethod
    def setUpClass(cls):
        cls.chat = CHAT_JS.read_text(encoding="utf-8")
        cls.admin = ADMIN_JS.read_text(encoding="utf-8")

    def test_chat_has_migration_iife(self):
        self.assertIn("_migrateSessionToLocal", self.chat,
            "chat.js must have a migration IIFE at top")
        idx = self.chat.index("_migrateSessionToLocal")
        body = self.chat[idx:idx + 800]
        self.assertIn("james_token", body)
        self.assertIn("james_role", body)
        self.assertIn("sessionStorage.getItem", body,
            "migration must read from sessionStorage")
        self.assertIn("localStorage.setItem", body,
            "migration must write to localStorage")

    def test_admin_has_migration_iife(self):
        self.assertIn("_migrateAdminSessionToLocal", self.admin,
            "admin.js must have a migration IIFE")


class CrossTabSyncTests(unittest.TestCase):
    """Both pages add a 'storage' event listener for cross-tab sync."""

    @classmethod
    def setUpClass(cls):
        cls.chat = CHAT_JS.read_text(encoding="utf-8")
        cls.admin = ADMIN_JS.read_text(encoding="utf-8")

    def test_chat_listens_for_storage_event(self):
        self.assertIn("addEventListener('storage'", self.chat,
            "chat.js must add 'storage' event listener for cross-tab SSO")
        idx = self.chat.index("addEventListener('storage'")
        body = self.chat[idx:idx + 800]
        self.assertIn("james_token", body,
            "listener must filter on james_token / james_role")
        self.assertIn("updateRoleBadge", body,
            "listener must call updateRoleBadge to refresh UI")

    def test_admin_listens_for_storage_event(self):
        self.assertIn("addEventListener('storage'", self.admin,
            "admin.js must add 'storage' event listener for cross-tab SSO")
        idx = self.admin.index("addEventListener('storage'")
        body = self.admin[idx:idx + 1200]
        self.assertIn("james_token", body)
        self.assertIn("showAdminLoginModal", body,
            "listener must show login modal when admin role is lost")

    def test_admin_listener_only_admin_role_keeps_dashboard(self):
        # If a different (non-admin) role gets set in localStorage from
        # the chat page, the admin tab should NOT silently auto-allow.
        # Verify the role check is present.
        idx = self.admin.index("addEventListener('storage'")
        body = self.admin[idx:idx + 1200]
        self.assertIn("'admin'", body,
            "must specifically check role === 'admin' before re-entering dashboard")


class LoginPersistenceTests(unittest.TestCase):
    """doLogin / doAdminLogin write to localStorage so other tabs see it."""

    @classmethod
    def setUpClass(cls):
        cls.chat = CHAT_JS.read_text(encoding="utf-8")
        cls.admin = ADMIN_JS.read_text(encoding="utf-8")

    def test_chat_doLogin_writes_localstorage(self):
        idx = self.chat.index("async function doLogin")
        end = self.chat.index("function logout", idx)
        body = self.chat[idx:end]
        self.assertIn("localStorage.setItem('james_token'", body,
            "doLogin must persist token to localStorage")
        self.assertIn("localStorage.setItem('james_role'", body,
            "doLogin must persist role to localStorage")

    def test_admin_doAdminLogin_writes_localstorage(self):
        idx = self.admin.index("async function doAdminLogin")
        # Bound at next async function or function decl.
        m = re.search(r"\n(async )?function\s+\w+\s*\(", self.admin[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 3000
        body = self.admin[idx:end]
        self.assertIn("localStorage.setItem('james_token'", body,
            "doAdminLogin must persist token to localStorage for SSO")
        self.assertIn("localStorage.setItem('james_role'", body,
            "doAdminLogin must persist role to localStorage")


class LogoutClearsBothTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chat = CHAT_JS.read_text(encoding="utf-8")
        cls.admin = ADMIN_JS.read_text(encoding="utf-8")

    def test_chat_logout_removes_localstorage(self):
        idx = self.chat.index("function logout")
        body = self.chat[idx:idx + 600]
        self.assertIn("localStorage.removeItem('james_token')", body)
        self.assertIn("localStorage.removeItem('james_role')", body)

    def test_admin_401_removes_localstorage(self):
        # Admin api() helper handles 401 — must clear localStorage so
        # chat tab role-badge updates too.
        idx = self.admin.index("if (r.status === 401)")
        body = self.admin[idx:idx + 600]
        self.assertIn("localStorage.removeItem('james_token')", body,
            "admin 401 path must clear localStorage james_token")


if __name__ == "__main__":
    unittest.main()
