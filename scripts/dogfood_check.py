"""Dogfood gate check — Track C PR-C10.

Verifies the four end-to-end contract invariants of the dogfood pack
(``packs/general/``). Each invariant matches a line in the v0.3 design
memo's loader semantics (`docs/design/v0.3-plugin-api.md`):

  1. Default startup loads ``packs/general/`` and registers its slots
  2. ``JAMES_PACKS=`` (empty string) is refused with ``PluginLoadError``
  3. A typo'd pack name is refused with ``PluginLoadError``
  4. A path-traversal pack name (``../something``) is refused

This complements ``scripts/eval_pack.py`` (PR-C9): the eval script
covers static manifest + slot-import + ruff checks for an arbitrary
pack; this script covers the **runtime contract** of the dogfood
gate specifically. Both run in CI on relevant PRs.

The check is intentionally **non-destructive** — it never deletes
``packs/general/`` to verify the "missing pack" branch. Instead it
uses a known-non-existent pack name, which exercises the same code
path with no filesystem mutation.

Usage::

    python scripts/dogfood_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass

from core.plugins.errors import (  # noqa: E402
    PluginLoadError,
    PluginVersionError,
)
from core.plugins.loader import (  # noqa: E402
    DEFAULT_PACK,
    load_packs_from_env,
)
from core.plugins.registry import PluginRegistry  # noqa: E402


_FAILURES: list[str] = []


def _check(condition: bool, name: str, detail: str = "") -> None:
    if condition:
        print(f"  OK    {name}")
    else:
        msg = f"{name}" + (f" -- {detail}" if detail else "")
        print(f"  FAIL  {msg}", file=sys.stderr)
        _FAILURES.append(msg)


def _expect_raises(
    expected_exc: type[BaseException],
    *,
    env: dict,
    name: str,
) -> None:
    """Call load_packs_from_env(env=env) and assert it raises expected_exc."""
    registry = PluginRegistry()
    try:
        load_packs_from_env(env=env, registry=registry)
    except expected_exc as exc:
        print(f"  OK    {name} -- raised {type(exc).__name__}: {exc!s}")
        return
    except Exception as exc:  # noqa: BLE001 — diagnostic
        _check(
            False, name,
            f"raised wrong exception type: {type(exc).__name__}: {exc!s} "
            f"(expected {expected_exc.__name__})",
        )
        return
    _check(False, name, f"did not raise (expected {expected_exc.__name__})")


def invariant_1_default_loads() -> None:
    """The default startup path (no env) loads packs/general/ and the
    registry has at least the ontology + prompts slots populated.
    """
    name = "invariant 1 — default startup loads packs/general/"
    registry = PluginRegistry()
    try:
        loaded = load_packs_from_env(env={}, registry=registry)
    except (PluginLoadError, PluginVersionError) as exc:
        _check(
            False, name,
            f"default load raised {type(exc).__name__}: {exc!s} "
            f"(packs/general/ may be missing or its manifest broken)",
        )
        return
    pack_names = [m.name for m in loaded]
    if DEFAULT_PACK not in pack_names:
        _check(
            False, name,
            f"default load returned {pack_names!r} which does not "
            f"include {DEFAULT_PACK!r}",
        )
        return
    counts = registry.slot_counts()
    if counts["ontology"] < 1 or counts["prompts"] < 1:
        _check(
            False, name,
            f"registry has insufficient slot counts after default load: "
            f"{counts!r}",
        )
        return
    print(
        f"  OK    {name} -- loaded {pack_names!r}, "
        f"slots={counts!r}"
    )


def invariant_2_empty_env_refused() -> None:
    """``JAMES_PACKS=`` (explicit empty) is refused. The design memo's
    'no silent fallback' contract requires the server to halt, not
    quietly proceed with no behavior.
    """
    _expect_raises(
        PluginLoadError,
        env={"JAMES_PACKS": ""},
        name="invariant 2 -- JAMES_PACKS='' is refused",
    )


def invariant_3_missing_pack_refused() -> None:
    """A pack name that doesn't resolve to a directory is refused.

    Non-destructive equivalent of "delete packs/general/ to verify the
    server breaks cleanly" — same loader codepath, no FS mutation.
    """
    _expect_raises(
        PluginLoadError,
        env={"JAMES_PACKS": "definitely-not-a-pack-xyz-pr-c10-sentinel"},
        name="invariant 3 -- missing pack is refused",
    )


def invariant_4_path_traversal_refused() -> None:
    """Path-traversal pack name is refused with a clear error.

    The loader rejects any pack name that resolves outside _PACKS_ROOT.
    Defense in depth — a future change to the env-parsing logic that
    accidentally allows '/' or '..' would be caught here.
    """
    _expect_raises(
        PluginLoadError,
        env={"JAMES_PACKS": "../core"},
        name="invariant 4 -- path traversal is refused",
    )


def main() -> int:
    print("[dogfood-check] running v0.3 dogfood gate invariants")
    print("-" * 60)
    invariant_1_default_loads()
    invariant_2_empty_env_refused()
    invariant_3_missing_pack_refused()
    invariant_4_path_traversal_refused()
    print("-" * 60)
    if _FAILURES:
        print(f"[dogfood-check] FAILED ({len(_FAILURES)} invariant(s)):")
        for f in _FAILURES:
            print(f"  - {f}")
        return 1
    print("[dogfood-check] PASS — all 4 invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
