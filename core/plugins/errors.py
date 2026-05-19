"""Plugin loader exceptions — Cognitive Phase 3 / Track C PR-C2.

Two narrow error types so the loader (PR-C3) can raise something the
operator can grep for in startup logs without it being mistaken for a
generic Python exception:

  - ``PluginLoadError`` — the pack is missing, the manifest is
    malformed, the import fails. Operator-fixable: missing
    ``packs/<name>/``, typo in ``JAMES_PACKS``, broken plugin code.
  - ``PluginVersionError`` — the manifest's ``james_api:`` SemVer
    range does not intersect the running core's version. Operator
    needs a newer/older pack, or a newer/older JAMES.

Both inherit from ``RuntimeError`` (not ``Exception`` directly) so the
loader can keep using bare ``except RuntimeError`` at the startup
boundary without catching every stdlib exception.

Per ``docs/design/v0.3-plugin-api.md`` §"Loader semantics".
"""
from __future__ import annotations


class PluginLoadError(RuntimeError):
    """The pack cannot be loaded — missing directory, malformed
    ``pack.yaml``, import-time exception, missing slot class.

    The message MUST name the pack so operator log-grep is one-line:

        raise PluginLoadError(
            f"pack {name!r} not found at packs/{name}/"
        )
    """


class PluginVersionError(RuntimeError):
    """The pack's declared ``james_api:`` SemVer range does not
    intersect the running JAMES core version.

    The message MUST name the pack AND the version mismatch so the
    operator can decide whether to bump JAMES, bump the pack, or
    pin to a specific compatible pair:

        raise PluginVersionError(
            f"pack {name!r} requires james_api {required!r}; "
            f"running core version is {current_version}"
        )
    """


__all__ = ["PluginLoadError", "PluginVersionError"]
