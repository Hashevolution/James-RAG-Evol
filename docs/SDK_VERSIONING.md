# `james-pack-sdk` Versioning Policy

Per `PLATFORM_READINESS.md` §3 v0.3 gate ("12-month deprecation
window for any public-API removal") and v1.0 gate ("Public SDK +
plugin author guide"). This document is the single source of truth
for the SDK's compatibility contract.

## SemVer compliance

`james-pack-sdk` follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html):

> Given a version number `MAJOR.MINOR.PATCH`, increment the:
> - `MAJOR` when you make incompatible API changes,
> - `MINOR` when you add functionality in a backwards-compatible
>   manner,
> - `PATCH` when you make backwards-compatible bug fixes.

| Change kind | Bump | Example |
|---|---|---|
| Bug fix — same call signature, same return type | PATCH | `validate_pack_id("foo bar")` was raising `TypeError` instead of `ValueError` — fixed to match the docstring contract |
| New optional kwarg, new helper, new pure-function entry | MINOR | Adding `scaffold.render_changelog_md(pack_id)` |
| Required-kwarg added, signature changed, helper removed, semantics changed | MAJOR | `OntologyPack.__init__` gaining a new required field |

## Public API surface

The public surface as of `0.6.0a1` is:

- `james.__version__`
- `james.pack.OntologyPack`
- `james.pack.register_pack`
- `james.pack.unmount_pack`
- `james.pack.CapabilityNotGrantedError`
- `james.pack.NameCollisionError`
- `james.pack.SchemaError`
- `james.pack.scaffold.validate_pack_id`
- `james.pack.scaffold.render_pack_py`
- `james.pack.scaffold.render_test_pack_py`
- `james.pack.scaffold.render_license`
- `james.pack.scaffold.render_readme_md`
- `james.pack.scaffold.write_scaffold`
- `python -m james.pack init <pack_id> [--output-dir <path>] [--overwrite]`
- `james-pack init <pack_id> [--output-dir <path>] [--overwrite]`
  (entry-point alias)

Names that start with a single underscore (e.g.
`james.pack.scaffold._PACK_ID_RE`) are **private**. They may
change in any release.

## Deprecation window

The v0.3 platform gate sets the deprecation window at **12 months**:

> A public symbol marked deprecated stays present for at least one
> full year before the MAJOR-bump removal release.

Operational checklist for the maintainer who wants to remove a
public symbol:

1. In release `N.M.P`, decorate the symbol with
   `warnings.warn(DeprecationWarning(...))` on every call, and
   add a "Deprecated in `N.M`, removal in next major" note to
   the docstring. **Do not** change the signature in this
   release.
2. Add the symbol to a `DEPRECATIONS.md` table tracking
   removal target dates (one row per deprecated symbol).
3. Keep the symbol working for at least 12 months from the
   release date of step 1.
4. In the next MAJOR release (after the 12-month window) the
   symbol can be removed. The MAJOR's release notes must call
   out the removed symbols explicitly.

The MAJOR-bump grace window is non-negotiable even for symbols
that turn out to be misnamed or footguns — fix forward with an
additional well-named symbol in MINOR, deprecate the old one,
and respect the window.

## Pre-1.0 caveat (alpha-tier)

`0.6.0a1` is alpha. Per SemVer §4:

> Major version zero (0.y.z) is for initial development. Anything
> MAY change at any time.

We hold ourselves to the deprecation window above even during the
0.x line — operators relying on the SDK before v1.0 should still
expect the 12-month grace, with the caveat that the scope of the
"public API" itself is small (see the surface list above) and may
grow as v1.0 milestones land.

## Compatibility matrix

| SDK version | JAMES runtime version range | Notes |
|---|---|---|
| `0.6.x` | v0.5 — v0.6 cycle (current main) | Runtime API requires `core.ontology_packs` from this branch; pre-G8.a JAMES installs cannot import `OntologyPack` |
| `1.0.x` (planned) | v1.0+ (post-LOI) | First stable major; capability grant workflow (G8.d) available |

## Reporting incompatible-change regressions

A SemVer regression (a MINOR or PATCH that broke a public symbol)
is a release-blocker bug. File at
[github.com/Hashevolution/James-RAG-Evol/issues](https://github.com/Hashevolution/James-RAG-Evol/issues)
with the `sdk-semver-regression` label. The maintainer's reply
target is 7 days.
