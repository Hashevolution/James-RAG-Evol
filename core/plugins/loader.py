"""Pack loader — ``JAMES_PACKS`` env-driven (Track C PR-C3).

Reads ``JAMES_PACKS=<pack1>,<pack2>,…`` at startup, resolves each
to ``packs/<name>/``, parses ``pack.yaml`` via
:mod:`core.plugins.manifest`, imports the slot classes the manifest
declares, and registers each Protocol-validated instance in the
process-wide :class:`core.plugins.registry.PluginRegistry`.

**Failure is fatal.** A pack that silently fails to load would leave
the operator running a server that's missing the behavior they
configured — far worse than a loud refusal at startup. Every failure
path raises :class:`PluginLoadError` or :class:`PluginVersionError`
from :mod:`core.plugins.errors` so operator log-grep is one-line.

Per ``docs/design/v0.3-plugin-api.md`` §"Loader semantics".

Env-var separation
------------------
``JAMES_PLUGINS`` is **already used** by ``core/reasoning/backends``
(PR #326) for LLM-backend plugins as Python module paths. To avoid a
breaking rename of an env var that's already in the field, the
pack-level loader uses a **separate env name**: ``JAMES_PACKS``.

The two layers are independent — a deployment may set both, one, or
neither. ``JAMES_PACKS`` defaults to ``"general"`` (the dogfood pack,
PR-C5); ``JAMES_PLUGINS`` defaults to empty (no extra backend plugins).
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

from core.plugins.errors import PluginLoadError
from core.plugins.manifest import (
    KNOWN_SLOTS,
    Manifest,
    check_semver,
    read_manifest,
)
from core.plugins.registry import PluginRegistry, get_registry


# ─── Defaults + paths ───────────────────────────────────────────────

# The pack the dogfood gate (PR-C5) extracts. Used when ``JAMES_PACKS``
# is unset — empty string is *not* the same as unset (see ``_parse_env``).
DEFAULT_PACK = "general"

# JAMES core version. The single source of truth for the
# ``james_api:`` compatibility check; pack manifests state a SemVer
# range and this string must satisfy it. Kept here as a local constant
# (not imported from ``config.py``) so the plugin layer has no upward
# coupling to the rest of the project.
JAMES_CORE_VERSION = "0.3.0"

# Resolves to ``<repo_root>/packs`` regardless of CWD. The loader
# refuses paths outside this directory — a pack referenced as
# ``"../evil"`` will not find a matching subdirectory and raises.
_PACKS_ROOT = Path(__file__).resolve().parent.parent.parent / "packs"


# ─── Env parsing ────────────────────────────────────────────────────


def _parse_env(raw: str | None) -> List[str]:
    """Split ``JAMES_PACKS`` into pack names.

    Three semantics, matched 1:1 to design memo §"Loader semantics":

    - ``raw is None`` (unset) → load :data:`DEFAULT_PACK` only.
    - ``raw == ""`` (explicit empty) → raise ``PluginLoadError`` —
      operator asked for *no* packs, which would leave the server
      with no behavior.
    - non-empty string → comma-separated list, whitespace tolerated.
    """
    if raw is None:
        return [DEFAULT_PACK]
    stripped = raw.strip()
    if stripped == "":
        raise PluginLoadError(
            "JAMES_PACKS is set to the empty string; that explicitly "
            "asks for no packs, which would leave the server with no "
            "behavior. Either unset the env (defaults to "
            f"{DEFAULT_PACK!r}) or list at least one pack name."
        )
    names = [p.strip() for p in stripped.split(",") if p.strip()]
    if not names:
        # Pathological case: ``JAMES_PACKS=" , , "`` — same intent as
        # the empty string above.
        raise PluginLoadError(
            f"JAMES_PACKS={raw!r} contains only separators; treat as "
            f"unset (which defaults to {DEFAULT_PACK!r}) instead."
        )
    return names


def _pack_dir(name: str) -> Path:
    """Resolve ``packs/<name>/`` and verify it is inside :data:`_PACKS_ROOT`.

    Path-traversal probe: a pack name like ``"../tools"`` would resolve
    above the packs root; we reject any resolved directory that does
    not have :data:`_PACKS_ROOT` as a parent.
    """
    candidate = (_PACKS_ROOT / name).resolve()
    try:
        candidate.relative_to(_PACKS_ROOT.resolve())
    except ValueError as exc:
        raise PluginLoadError(
            f"pack {name!r}: resolved directory {candidate} escapes the "
            f"packs root {_PACKS_ROOT}; pack names cannot contain path "
            f"separators or '..'"
        ) from exc
    if not candidate.is_dir():
        raise PluginLoadError(
            f"pack {name!r} not found at {candidate}"
        )
    return candidate


# ─── Slot import ────────────────────────────────────────────────────


def _import_slot_class(
    pack_name: str, pack_dir: Path, import_path: str
):
    """Resolve ``"module:Class"`` against the pack directory.

    Adds the pack directory to ``sys.path`` *only for the duration of
    the import* so the pack's module namespace cannot collide with
    project-level imports. Removes the path entry on return.
    """
    if ":" not in import_path:
        raise PluginLoadError(
            f"pack {pack_name!r}: slot import path must be "
            f"'module:Class' form; got {import_path!r}"
        )
    module_path, class_name = import_path.split(":", 1)
    pack_dir_str = str(pack_dir)
    sys.path.insert(0, pack_dir_str)
    try:
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginLoadError(
                f"pack {pack_name!r}: cannot import module "
                f"{module_path!r} from {pack_dir} ({exc})"
            ) from exc
        if not hasattr(module, class_name):
            raise PluginLoadError(
                f"pack {pack_name!r}: module {module_path!r} has no "
                f"class {class_name!r}"
            )
        cls = getattr(module, class_name)
        try:
            return cls()
        except Exception as exc:  # noqa: BLE001 — wrap with context
            raise PluginLoadError(
                f"pack {pack_name!r}: instantiating "
                f"{module_path}:{class_name} raised "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    finally:
        try:
            sys.path.remove(pack_dir_str)
        except ValueError:
            # Pack code might have manipulated sys.path itself.
            # Don't crash startup over a best-effort cleanup.
            pass


def _iter_slot_imports(
    manifest: Manifest,
) -> Iterable[Tuple[str, str]]:
    """Yield ``(slot, import_path)`` tuples in :data:`KNOWN_SLOTS` order.

    Stable ordering matters because registration order is observable
    (registry returns slots in insertion order; consumer policy is
    last-registered-first for prompts, all-merged for ontology, etc.).
    """
    for slot in ("ontology", "prompts", "ui", "scorers"):
        if slot not in manifest.plugins:
            continue
        value = manifest.plugins[slot]
        if isinstance(value, str):
            yield slot, value
        else:
            # list[str] — validated by manifest parser
            for entry in value:
                yield slot, entry


def _register_slot(
    registry: PluginRegistry, slot: str, instance, pack_name: str
) -> None:
    """Dispatch to the slot-specific registry method.

    The Protocol check happens inside ``register_*`` so the error
    message is consistent; this function only routes.
    """
    if slot == "ontology":
        registry.register_ontology(instance)
    elif slot == "prompts":
        registry.register_prompts(instance)
    elif slot == "ui":
        registry.register_ui_panel(instance)
    elif slot == "scorers":
        registry.register_scorer(instance)
    else:
        # Manifest parser already rejects unknown slots, but be
        # defensive in case load_packs_from_env() is called with an
        # already-mutated manifest.
        raise PluginLoadError(
            f"pack {pack_name!r}: cannot register unknown slot "
            f"{slot!r}; valid: {sorted(KNOWN_SLOTS)}"
        )


# ─── Public entry point ─────────────────────────────────────────────


def load_packs_from_env(
    env: dict[str, str] | None = None,
    *,
    registry: PluginRegistry | None = None,
    core_version: str = JAMES_CORE_VERSION,
) -> List[Manifest]:
    """Read ``JAMES_PACKS`` from ``env`` (defaults to ``os.environ``),
    load each pack, populate the registry, and return the manifest
    list in load order.

    Arguments:
      env:           env-var dict; defaults to ``os.environ``. Tests
                     pass a literal dict to drive arbitrary inputs.
      registry:      target registry; defaults to
                     :func:`core.plugins.registry.get_registry`. Tests
                     pass a fresh registry instance per case.
      core_version:  JAMES core version for SemVer matching. Defaults
                     to :data:`JAMES_CORE_VERSION`. Tests drive
                     mismatch cases by passing a different version.

    Fatal failure modes (all raise from :mod:`core.plugins.errors`):
      - ``JAMES_PACKS=`` (empty) → ``PluginLoadError``
      - pack name resolves outside :data:`_PACKS_ROOT` → ``PluginLoadError``
      - ``packs/<name>/`` missing → ``PluginLoadError``
      - ``pack.yaml`` malformed → ``PluginLoadError``
      - ``pack.yaml`` declares incompatible ``james_api:`` →
        ``PluginVersionError``
      - slot import / instantiate / Protocol-check fails →
        ``PluginLoadError``
    """
    env_map = os.environ if env is None else env
    pack_names = _parse_env(env_map.get("JAMES_PACKS"))

    if registry is None:
        registry = get_registry()

    loaded: List[Manifest] = []
    for name in pack_names:
        pack_dir = _pack_dir(name)
        manifest = read_manifest(pack_dir / "pack.yaml", name)
        check_semver(name, manifest.james_api, core_version)

        if not manifest.plugins:
            # Empty plugins block — manifest parsed fine but no slots
            # to register. The design memo (§"Manifest") permits this
            # but says the loader warns once.
            print(
                f"[plugins] WARNING: pack {name!r} declares zero slots "
                f"in pack.yaml::plugins; loaded but contributes nothing",
                flush=True,
            )

        if manifest.warns_at_load:
            print(
                f"[plugins] WARNING: pack {name!r} declares "
                f"license={manifest.license!r}; loaded but operator "
                f"should record the commercial-license token "
                f"(see docs/LICENSE_PLAN.md §5.2)",
                flush=True,
            )

        for slot, import_path in _iter_slot_imports(manifest):
            instance = _import_slot_class(name, pack_dir, import_path)
            _register_slot(registry, slot, instance, name)

        loaded.append(manifest)

    return loaded


__all__ = [
    "DEFAULT_PACK",
    "JAMES_CORE_VERSION",
    "load_packs_from_env",
]
