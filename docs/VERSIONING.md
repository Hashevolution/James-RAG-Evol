# Plugin Contract Versioning

> **Status**: v0.3 draft. The Plugin API is **pre-stable** until JAMES
> v1.0 lands the marketplace; the policy below is what authors can
> rely on starting v0.3.0.
>
> **Last revised**: 2026-05-23 (PR-C8 of the v0.3 Plugin contract
> sequence).

This document is the public contract between **JAMES core** and any
**pack** that ships against it. It defines:

1. What is versioned, on three independent axes
2. What changes in the Plugin API are breaking vs additive
3. How JAMES gives notice before removing something (the 12-month
   deprecation policy)
4. How a pack declares the range of JAMES core it supports

For the schema and Protocol shapes themselves, see
[`docs/design/v0.3-plugin-api.md`](design/v0.3-plugin-api.md). For
how to *author* a pack against this contract, see
[`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md).

---

## 1. Three version axes

A live JAMES install has three independent versions in play. Authors
need to track all three:

| Axis | Where it lives | Owner |
|---|---|---|
| **JAMES core version** | `core/plugins/loader.py::JAMES_CORE_VERSION` | JAMES maintainers (Hashevolution) |
| **Pack version** | `packs/<name>/pack.yaml::version` | Pack author |
| **Manifest schema version** | implicit v1 in `core/plugins/manifest.py` | JAMES maintainers |

The three axes are **independent** — a pack at version 2.3.1 can
declare it works against JAMES core `>=0.3,<0.4`, both on schema v1.

Pack authors only have to manage axis 2 themselves. Axes 1 and 3 are
declared as a range / version in `pack.yaml` and verified at load.

---

## 2. JAMES core SemVer

JAMES core follows [Semantic Versioning 2.0.0](https://semver.org/).
For the Plugin API surface specifically:

### What counts as a MAJOR bump (breaking)

A change to anything below requires a major version bump on JAMES core:

- **Protocol shape changes** in `core/plugins/base.py`:
  - Renaming a Protocol type (`OntologyPack` → something else)
  - Renaming or removing a method on a Protocol
  - Changing the signature of an existing method (positional → keyword,
    parameter rename, type narrowing on input, type widening on output)
- **Manifest schema changes** in `core/plugins/manifest.py`:
  - Renaming a required field (`name:` → `slug:`)
  - Adding a new required field (existing manifests would no longer
    parse)
  - Removing a known slot from `KNOWN_SLOTS` (e.g. removing the
    `ui:` slot would orphan every pack that ships UI panels)
- **License enum narrowing**: removing an entry from
  `ALLOWED_LICENSES` makes previously-valid packs refuse to load
- **Loader semantics**: changing the meaning of `JAMES_PACKS=` (e.g.
  treating empty as "load default" instead of "refused start")

### What counts as MINOR (additive, non-breaking)

These changes can ship in a minor release without breaking existing
packs:

- **New Protocol method with a default implementation** in the base
  Protocol body (callers default to the new behavior; existing packs
  that don't override see no behavior change)
- **New optional manifest field** (omitted in older packs is still
  legal)
- **New slot** added to `KNOWN_SLOTS` (existing packs simply don't
  declare the new slot)
- **New entry** added to `ALLOWED_LICENSES`
- **New `PluginRegistry` method** that doesn't replace an existing one
- **Wider input type / narrower output type** on a Protocol method
  (Liskov-safe expansion)

### What counts as PATCH

- Bug fixes in loader / registry / manifest validation
- Docstring updates
- Error-message phrasing improvements
- Test-only changes

---

## 3. The `james_api:` range in `pack.yaml`

Every pack declares the range of JAMES core it claims compatibility
with:

```yaml
james_api: ">=0.3,<0.4"
```

Verified at load by
`core/plugins/manifest.py::check_semver(pack.james_api, current_core)`
using [`packaging.specifiers.SpecifierSet`](https://packaging.pypa.io/en/stable/specifiers.html).
Mismatch raises `PluginVersionError` and is **fatal at startup** —
there is no silent fallback.

### Recommended ranges for pack authors

| Range | Meaning | When to use |
|---|---|---|
| `">=0.3,<0.4"` | Locked to a single minor | The conservative default. Pack is re-verified each JAMES minor bump. |
| `">=0.3"` | Forward-open | Pack author commits to tracking JAMES MINOR releases. Risks breaking on the next minor. |
| `"==0.3.5"` | Exact pin | For pack authors who run their own JAMES build. Not recommended for distribution. |

The default in `packs/general/` (the dogfood pack) is `">=0.3,<0.4"`
— same-repo dogfooding pins a single minor.

---

## 4. 12-month deprecation policy

When JAMES needs to remove or rename a Plugin API surface, the path is:

| Phase | Duration | What the operator sees | What the pack author sees |
|---|---|---|---|
| **Phase 1 — Soft warn** | Months 0–6 | `WARNING: pack {name} uses deprecated X; will be removed in v{Y}` printed at load | `DeprecationWarning` emitted when the API is touched; both old and new APIs work |
| **Phase 2 — Loud warn** | Months 6–12 | Same warning at startup AND every invocation site; both APIs still work | Same `DeprecationWarning`, plus a startup-time line in the pack-author CI eval |
| **Phase 3 — Removal** | Month 12+ | Pack refuses to load with `PluginLoadError` naming the new API | Migration is no longer optional |

**12-month minimum from first warn to removal.** A minor bump
introduces the warn; the removal cannot land before 12 months have
elapsed AND not before the next MAJOR bump of JAMES core. The two
gates are AND, not OR — a v0.4 minor that introduces a Phase-1 warning
does not earn the right to remove the old API in v0.5; the removal
waits for v1.0.

### What this commits JAMES core to

- A deprecation calendar lives in `docs/handovers/` per cycle. Each
  warn → removal cycle is one row.
- Pack authors can `grep DeprecationWarning core/plugins/` to find
  every public API on a removal track.
- The `pack-author CI eval contract` (PR-C9, not yet landed) will fail
  on Phase 2 warnings, giving authors a hard signal during the second
  six-month window.

### What this does NOT commit JAMES core to

- **Pre-v1.0 stability** of the entire surface. Until v1.0, an
  individual deprecation can be compressed if (a) the API is
  documented as unstable in this file or in the Protocol's docstring,
  AND (b) the operator-visible cost is bounded (e.g. an internal
  helper that no shipped pack uses).
- **Re-deprecating an already-deprecated API**. Once Phase 3 lands,
  the API name is retired.

---

## 5. Manifest schema versioning

Currently only **schema v1** exists; there is no `schema_version:`
field on `pack.yaml`. The implicit version is v1.

If a future schema v2 lands:

- The field `schema_version: 2` becomes required for any pack that
  uses v2-only features.
- v1 manifests continue to parse (read by the v1 codepath) for at
  least one JAMES MINOR cycle.
- After that, omitted `schema_version:` defaults to v1 for a deprecation
  window aligned with §4.

The intent is that schema v2 only ships when there is a concrete
need that cannot be solved additively within v1. So far, no such need
has surfaced.

---

## 6. Pre-v1.0 disclaimer

> **The Plugin API is pre-stable until JAMES v1.0.**

The contract above applies *starting* v0.3.0. During the v0.3 →
v1.0 cycle the maintainers commit to the deprecation policy in §4
*for surfaces documented as stable*. A Protocol method or manifest
field documented with `# unstable` in its docstring is exempt from
the 12-month window and can be reshaped in a minor.

A non-exhaustive list of surfaces that are currently **stable** in
v0.3:

- The four Protocol types in `core/plugins/base.py` (`OntologyPack`,
  `PromptPack`, `UIPanel`, `Scorer`) and their declared methods
- The `pack.yaml` required fields: `name`, `version`, `james_api`,
  `description`, `author`, `license`
- The `ALLOWED_LICENSES` enum (closed during v0.3 — widening at v1.0
  is additive)
- The four entries in `KNOWN_SLOTS`
- `JAMES_PACKS=` and `JAMES_WORKSPACE=` env semantics
- The `PluginLoadError` / `PluginVersionError` exception types and the
  fact that both are fatal at startup

Surfaces currently **explicitly unstable** in v0.3:

- The `PanelContext` shape (UI panel parameter) — may grow new fields
  in a minor without deprecation; existing fields will not be removed
  without §4 notice
- The exact wording of error messages — operator log-grep should
  match on the exception type, not the message text

---

## 7. SemVer normalization

The loader uses [`packaging.version.Version`](https://packaging.pypa.io/en/stable/version.html)
which normalises some shapes (`1.0` → `1.0`, `1.0.0a1` →
`1.0.0a1`). Pack authors who pin against a JAMES build should use
the canonical form (`0.3.0`, not `0.3`) to avoid surprise.

The `version:` field in `pack.yaml` is **stored as the string the
author wrote**, but validated by a `Version()` parse. The string is
preserved verbatim in the loaded `Manifest` dataclass — JAMES does
not normalise it back at you.

---

## 8. References

- Design memo: [`docs/design/v0.3-plugin-api.md`](design/v0.3-plugin-api.md)
- Manifest schema: `core/plugins/manifest.py`
- License policy: [`docs/LICENSE_PLAN.md`](LICENSE_PLAN.md) §5.2
- Loader semantics: `core/plugins/loader.py`
- Pack authoring guide: [`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md)
  *(PR-C7, lands alongside this file)*

---

## 9. 한국어 요약

플러그인 계약은 **세 축의 버전**을 분리해서 관리한다 — JAMES 코어
SemVer, 팩 자체 SemVer, manifest 스키마 버전. 팩 작성자는 `pack.yaml`
의 `james_api:` 범위로 코어 버전 제약을 선언하고, 코어 측은
**12개월 deprecation 정책**을 이 문서로 약속한다. v1.0 이전에는
Plugin API 가 사전 안정 단계라는 점을 명시하되, §4 의 deprecation
대응 약속은 v0.3.0 부터 즉시 발효한다.
