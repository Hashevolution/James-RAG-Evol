"""Plugin manifest — ``pack.yaml`` schema + validation (Track C PR-C3).

Every pack under ``packs/<name>/`` ships a top-level ``pack.yaml``.
The loader (``core/plugins/loader.py``) reads it via :func:`read_manifest`
and refuses startup if anything is malformed — there is no silent
fallback path.

Per ``docs/design/v0.3-plugin-api.md`` §"Manifest — pack.yaml".

Required fields
---------------
- ``name``         — slug; MUST match the directory under ``packs/``
- ``version``      — SemVer (e.g. ``1.0.0``)
- ``james_api``    — SemVer range against the JAMES core (e.g. ``">=0.3,<0.4"``)
- ``description``  — short human-readable string
- ``author``       — string (pack author / org)
- ``license``      — closed enum (v0.3): ``MIT`` / ``Apache-2.0`` /
                     ``AGPL-3.0`` / ``proprietary``. ``proprietary``
                     loads with a warning (see LICENSE_PLAN.md §5.2).

Optional fields
---------------
- ``plugins``      — slot → import path mapping. Missing or empty means
                     the pack contributes zero slots; the loader warns
                     once but the pack is still considered loaded.

Versioning
----------
Only **schema v1** is defined here. A future schema v2 would land as
``schema_version`` field on the manifest itself with an explicit
migration step in this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from core.plugins.errors import PluginLoadError, PluginVersionError


# ─── License enum (closed during v0.3) ──────────────────────────────
#
# Widened to "any SPDX identifier with an allowlist" at v1.0 once the
# marketplace lands. See docs/LICENSE_PLAN.md §5.2.
ALLOWED_LICENSES = frozenset({
    "MIT",
    "Apache-2.0",
    "AGPL-3.0",
    "proprietary",
})

# License values that emit a startup warning but still load. The
# operator may have intentionally licensed a private pack as
# proprietary — that's fine, but the audit log should surface it.
LICENSES_WITH_WARNING = frozenset({"proprietary"})


# ─── Slot names ─────────────────────────────────────────────────────
#
# The four slots correspond 1:1 to the Protocol types in
# ``core/plugins/base.py``. A manifest declaring an unknown slot is a
# PluginLoadError — fail loud, fail early.
KNOWN_SLOTS = frozenset({"ontology", "prompts", "ui", "scorers"})


@dataclass(frozen=True)
class Manifest:
    """Parsed pack manifest. Frozen so a loaded pack's contract cannot
    drift at runtime.

    The ``plugins`` field maps slot name to one of:
      - a single ``"module:Class"`` string (``ontology`` / ``prompts``),
      - a list of ``"module:Class"`` strings (``ui`` / ``scorers``).

    The loader (``core/plugins/loader.py``) normalises both shapes
    when it constructs the slot registry.
    """

    name: str
    version: str
    james_api: str
    description: str
    author: str
    license: str
    plugins: Dict[str, Union[str, List[str]]] = field(default_factory=dict)

    @property
    def warns_at_load(self) -> bool:
        """True when the license value is in :data:`LICENSES_WITH_WARNING`.

        The loader prints one warning line per warning pack at startup.
        """
        return self.license in LICENSES_WITH_WARNING


def _require_str(blob: Dict[str, Any], key: str, pack_name: str) -> str:
    """Read a required string field. Raises PluginLoadError if missing
    or not a string — operator gets the exact key in the error message.
    """
    if key not in blob:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml missing required field {key!r}"
        )
    val = blob[key]
    if not isinstance(val, str) or not val.strip():
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml field {key!r} must be a "
            f"non-empty string; got {val!r}"
        )
    return val.strip()


def _validate_plugins(
    plugins: Any, pack_name: str
) -> Dict[str, Union[str, List[str]]]:
    """Validate the optional ``plugins`` block.

    Accepts:
      - missing / None → empty dict (pack contributes zero slots)
      - dict with keys in :data:`KNOWN_SLOTS`

    Each value is either a ``"module:Class"`` string or a list of such
    strings. The loader (PR-C3) does the import; this function only
    checks structural shape so an obvious typo (``Ontology:`` ↔
    ``ontology:``) fails at manifest parse, not at import time.
    """
    if plugins is None:
        return {}
    if not isinstance(plugins, dict):
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml field 'plugins' must be a "
            f"mapping; got {type(plugins).__name__}"
        )
    out: Dict[str, Union[str, List[str]]] = {}
    for slot, value in plugins.items():
        if slot not in KNOWN_SLOTS:
            raise PluginLoadError(
                f"pack {pack_name!r}: pack.yaml plugins.{slot} is not a "
                f"known slot. Valid: {sorted(KNOWN_SLOTS)}"
            )
        # Single string OR list of strings. Reject anything else.
        if isinstance(value, str):
            if ":" not in value:
                raise PluginLoadError(
                    f"pack {pack_name!r}: plugins.{slot} import path "
                    f"must be 'module:Class' form; got {value!r}"
                )
            out[slot] = value.strip()
        elif isinstance(value, list):
            for entry in value:
                if not isinstance(entry, str) or ":" not in entry:
                    raise PluginLoadError(
                        f"pack {pack_name!r}: plugins.{slot} list entries "
                        f"must be 'module:Class' strings; got {entry!r}"
                    )
            out[slot] = [e.strip() for e in value]
        else:
            raise PluginLoadError(
                f"pack {pack_name!r}: plugins.{slot} must be a string or "
                f"list of strings; got {type(value).__name__}"
            )
    return out


def parse_manifest(blob: Dict[str, Any], pack_name: str) -> Manifest:
    """Convert a YAML-loaded dict into a validated :class:`Manifest`.

    ``pack_name`` is the directory name; if the manifest's ``name``
    field disagrees, that is a loud error.
    """
    name = _require_str(blob, "name", pack_name)
    if name != pack_name:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml declares name={name!r} but "
            f"the directory is named {pack_name!r}. The two must match."
        )

    version_str = _require_str(blob, "version", pack_name)
    # Validate version parses as a Version. We store the string form
    # (PyPA Version normalises in ways that surprise pack authors) but
    # the parse check catches obvious typos.
    try:
        Version(version_str)
    except InvalidVersion as exc:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml field 'version' is not a "
            f"valid SemVer; got {version_str!r} ({exc})"
        ) from exc

    james_api = _require_str(blob, "james_api", pack_name)
    # Validate the SemVer specifier parses. The actual range-vs-core
    # check happens in :func:`check_semver`.
    try:
        SpecifierSet(james_api)
    except InvalidSpecifier as exc:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml field 'james_api' is not a "
            f"valid SemVer specifier; got {james_api!r} ({exc})"
        ) from exc

    description = _require_str(blob, "description", pack_name)
    author = _require_str(blob, "author", pack_name)

    license_value = _require_str(blob, "license", pack_name)
    if license_value not in ALLOWED_LICENSES:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml field 'license' must be one "
            f"of {sorted(ALLOWED_LICENSES)}; got {license_value!r}"
        )

    plugins = _validate_plugins(blob.get("plugins"), pack_name)

    return Manifest(
        name=name,
        version=version_str,
        james_api=james_api,
        description=description,
        author=author,
        license=license_value,
        plugins=plugins,
    )


def read_manifest(pack_yaml_path: Path, pack_name: str) -> Manifest:
    """Read + parse + validate ``packs/<name>/pack.yaml``.

    Raises :class:`PluginLoadError` for any structural problem;
    the message names ``pack_name`` so operator log-grep is one-line.
    """
    if not pack_yaml_path.is_file():
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml not found at {pack_yaml_path}"
        )
    try:
        raw = pack_yaml_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PluginLoadError(
            f"pack {pack_name!r}: cannot read pack.yaml at "
            f"{pack_yaml_path}: {exc}"
        ) from exc
    try:
        blob = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml is not valid YAML "
            f"({exc})"
        ) from exc
    if not isinstance(blob, dict):
        raise PluginLoadError(
            f"pack {pack_name!r}: pack.yaml top-level must be a mapping; "
            f"got {type(blob).__name__}"
        )
    return parse_manifest(blob, pack_name)


def check_semver(
    pack_name: str,
    pack_james_api: str,
    current_core_version: str,
) -> None:
    """Verify the pack's ``james_api:`` range contains the core version.

    Raises :class:`PluginVersionError` with the exact mismatch the
    operator needs to either bump JAMES or bump the pack.

    The current core version is passed in (not read here) so tests can
    drive arbitrary version pairs without monkey-patching.
    """
    try:
        spec = SpecifierSet(pack_james_api)
    except InvalidSpecifier as exc:
        # parse_manifest() already validated the spec, but be defensive
        # in case this function is called with raw input.
        raise PluginLoadError(
            f"pack {pack_name!r}: james_api spec {pack_james_api!r} is "
            f"not parseable ({exc})"
        ) from exc
    try:
        version_obj = Version(current_core_version)
    except InvalidVersion as exc:
        raise PluginLoadError(
            f"current core version {current_core_version!r} is not a "
            f"valid SemVer ({exc})"
        ) from exc
    if version_obj not in spec:
        raise PluginVersionError(
            f"pack {pack_name!r} requires james_api {pack_james_api!r}; "
            f"running core version is {current_core_version!r}"
        )


__all__ = [
    "ALLOWED_LICENSES",
    "KNOWN_SLOTS",
    "LICENSES_WITH_WARNING",
    "Manifest",
    "check_semver",
    "parse_manifest",
    "read_manifest",
]
