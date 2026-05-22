"""PROJECT JAMES — server startup loads packs/general/ (PR-C5b).

Verifies the FastAPI startup hook in server_llmwiki actually wires
``load_packs_from_env()``. A regression here re-introduces the gap
that PR-C5b closed: the loader code exists but is never called, so
the dogfood pack never lights up.

Uses fastapi.testclient.TestClient which triggers startup events.
The test is read-only against the registry — it only confirms
packs/general/ landed in the slot counts.

A separate concern (byte-identical STEP 7) is operator-witnessed via
``scripts/step7_query_test.py`` against a running server; this file
covers only the lighter "startup hook fires" contract.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


class StartupHookLoadsPacksTests(unittest.TestCase):
    """The on_startup() hook must populate the plugin registry.

    Failure here means the loader is dead code from the server's
    perspective — the dogfood gate is broken.
    """

    def test_general_pack_is_registered_after_startup(self):
        # Importing the module triggers the FastAPI app creation; the
        # startup event fires on the first TestClient request (or its
        # context manager). We use the context manager form so any
        # PluginLoadError raised during startup is surfaced here.
        from fastapi.testclient import TestClient
        import server_llmwiki as srv
        from core.plugins.registry import get_registry

        # The shared registry may have been populated by other tests
        # before us. We capture the pre-startup state and check the
        # delta after, so this test is order-independent.
        before = get_registry().slot_counts()

        with TestClient(srv.app):
            # Context-manager entry fires startup; we don't actually
            # need to make a request — the registry mutation is what
            # we're checking.
            after = get_registry().slot_counts()

        # After startup, the registry should have at least one ontology
        # AND one prompts entry (general's two no-op overlays). The
        # "at least" wording covers the case where other tests already
        # registered packs before this one ran.
        self.assertGreaterEqual(
            after["ontology"], before["ontology"] + 1,
            f"server startup did not register general's OntologyPack; "
            f"before={before}, after={after}"
        )
        self.assertGreaterEqual(
            after["prompts"], before["prompts"] + 1,
            f"server startup did not register general's PromptPack; "
            f"before={before}, after={after}"
        )

    def test_startup_does_not_swallow_plugin_load_error(self):
        # Defensive: the hook's try/except clause must NOT catch
        # PluginLoadError. The design memo's "no silent fallback"
        # contract requires server startup to halt on a broken pack —
        # an operator with a typo'd JAMES_PACKS must see the failure
        # at startup, not 30 minutes later. The current implementation
        # only catches ImportError (the "package doesn't exist at all"
        # safety net), letting PluginLoadError / PluginVersionError
        # propagate. We assert that contract by grep on the source.
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "server_llmwiki.py").read_text(encoding="utf-8")
        # The startup hook block we added has a marker comment that's
        # easy to grep — verify it's still in place AND that it doesn't
        # catch PluginLoadError below it.
        marker = "[PR-C5b 2026-05-23] Plugin pack loader"
        self.assertIn(marker, src, "PR-C5b startup hook block was removed")
        # Find the block's slice (from the marker to the next ``# `` at
        # column 4 — the next subsystem's marker comment).
        idx = src.index(marker)
        # The block ends at the next "# #81 phase" comment (the
        # observability subsystem that follows). Defensive: 4000 chars
        # is more than enough headroom for the block.
        block = src[idx:idx + 4000]
        block_end = block.find("# #81 phase")
        if block_end > 0:
            block = block[:block_end]
        # The block must NOT mention PluginLoadError or
        # PluginVersionError in an except clause.
        self.assertNotIn(
            "except PluginLoadError", block,
            "PR-C5b block now swallows PluginLoadError — that violates "
            "the design memo's no-silent-fallback contract"
        )
        self.assertNotIn(
            "except PluginVersionError", block,
            "PR-C5b block now swallows PluginVersionError — that violates "
            "the design memo's no-silent-fallback contract"
        )


if __name__ == "__main__":
    unittest.main()
