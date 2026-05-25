# Authoring a JAMES Plugin Pack

> **Audience**: Engineers who want to ship a domain-specialized
> behavior pack against JAMES core. This guide assumes familiarity
> with Python protocols and YAML.
>
> **Status**: v0.3 author quickstart. Companion to
> [`docs/VERSIONING.md`](VERSIONING.md) (the SemVer contract) and the
> design memo [`docs/design/v0.3-plugin-api.md`](design/v0.3-plugin-api.md).
>
> **Last revised**: 2026-05-23 (PR-C7 of the v0.3 Plugin contract).

A **pack** is a Python package under `packs/<name>/` that contributes
**zero or more** of the four plugin slots JAMES exposes:

| Slot | Protocol type | What it does | Example |
|---|---|---|---|
| `ontology` | `OntologyPack` | New entity/relation types, hierarchies | Legal: `contract`, `clause`, `party` |
| `prompts` | `PromptPack` | Mode-specific system prompts + few-shot | Food: terse JSON-mode reply for recipe queries |
| `ui` | `UIPanel` | Server-rendered admin/user widgets | Retail: inventory dashboard panel |
| `scorers` | `Scorer` | Custom retrieval / answer scoring | Travel: prefer recency for itinerary queries |

The default JAMES behavior — generic ontology, mode prompts, no extra
panels, default reranker — ships as `packs/general/` (the dogfood
pack). Your pack overrides only the slots you register.

---

## 1. The 60-second quickstart

```bash
# 1. Skeleton
mkdir -p packs/mypack
touch packs/mypack/pack.yaml
touch packs/mypack/__init__.py
touch packs/mypack/ontology.py

# 2. Manifest — see §2
cat > packs/mypack/pack.yaml <<'EOF'
name: mypack
version: 0.1.0
james_api: ">=0.3,<0.4"
description: "My first JAMES pack"
author: "<your name or org>"
license: "MIT"
plugins:
  ontology: ontology:MyOntology
EOF

# 3. Minimum-viable ontology — see §4
cat > packs/mypack/ontology.py <<'EOF'
class MyOntology:
    pack_id = "mypack"
    entity_types = ("widget", "gadget")
    relation_types = ("contains",)
    hierarchies = {"widget": ("gadget",)}
EOF

# 4. Run JAMES with your pack
JAMES_PACKS=mypack python server_llmwiki.py
```

If the manifest is well-formed and the ontology class satisfies the
`OntologyPack` protocol, JAMES starts and your entity types are
registered.

---

## 2. Manifest authoring (`pack.yaml`)

The full schema is enforced by `core/plugins/manifest.py`. Every field
below is **required** except `plugins:`.

```yaml
# pack.yaml — schema v1
name: mypack                                    # MUST match the directory under packs/
version: 0.1.0                                  # SemVer 2.0.0 (your pack's version)
james_api: ">=0.3,<0.4"                         # SemVer range against JAMES core
description: "One-line human description"       # non-empty string
author: "Hashevolution"                         # author or org
license: "MIT"                                  # MIT | Apache-2.0 | AGPL-3.0 | proprietary

# plugins: is optional. Omit it and the pack contributes zero slots
# (legal but useless; loader warns once).
plugins:
  ontology: ontology:MyOntology                 # single import path
  prompts: prompts:MyPrompts
  ui:                                           # OR a list, for ui/scorers
    - ui.search:SearchPanel
    - ui.graph:GraphPanel
  scorers:
    - scoring.recency:RecencyScorer
```

### Field rules

| Field | Rule | Failure mode |
|---|---|---|
| `name:` | Must equal the directory name | `PluginLoadError("declares name='X' but the directory is named 'Y'")` |
| `version:` | Parseable by `packaging.version.Version` | `PluginLoadError("not a valid SemVer")` |
| `james_api:` | Parseable by `packaging.specifiers.SpecifierSet`; must contain the current core | `PluginVersionError("requires james_api 'X'; running core version is 'Y'")` |
| `description:` / `author:` | Non-empty string | `PluginLoadError("must be a non-empty string")` |
| `license:` | One of `MIT` / `Apache-2.0` / `AGPL-3.0` / `proprietary` | `PluginLoadError("must be one of [...]")`. `proprietary` warns at load but loads. |
| `plugins.<slot>:` | Known slot (`ontology` / `prompts` / `ui` / `scorers`) | `PluginLoadError("not a known slot")` |
| `plugins.<slot>: "x:Y"` | `module:Class` shape | `PluginLoadError("'module:Class' form")` |

### Tips

- Keep `version:` as a string in the YAML (`"0.1.0"`, not `0.1`). Bare
  `0.1` parses as a number in some YAML flavors.
- Use `">=0.3,<0.4"` (locked to a minor) as your default `james_api:`
  range. See [`VERSIONING.md`](VERSIONING.md) §3 for when to widen.
- `license: "proprietary"` is valid for private packs but prints a
  warning at every JAMES startup — that's intentional, and operators
  can grep their logs for it.

---

## 3. Directory layout

A pack is a Python package, so it can structure its modules however it
likes. The convention used by `packs/general/` (the dogfood pack):

```
packs/mypack/
├── __init__.py                # may be empty
├── pack.yaml                  # required
├── ontology.py                # OntologyPack implementation
├── prompts.py                 # PromptPack implementation
├── ui/                        # multiple UI panels split into a subpackage
│   ├── __init__.py
│   ├── search.py
│   └── graph.py
├── scoring/
│   ├── __init__.py
│   └── recency.py
└── data/                      # static data the pack ships with
    ├── prompts/
    └── ontology.json
```

Import paths in `pack.yaml::plugins` are resolved relative to the pack
package. So `ontology: ontology:MyOntology` loads
`packs.mypack.ontology.MyOntology`.

If the import fails (typo'd class name, syntax error), the loader
raises `PluginLoadError` naming the pack and the failing import path.

---

## 4. Four-type examples

The four `@runtime_checkable` Protocol types live in
[`core/plugins/base.py`](../core/plugins/base.py). Each example below
is a minimum-viable implementation that the loader will accept.

### 4.1 `OntologyPack` — entity types, relation types, hierarchies

```python
# packs/mypack/ontology.py
from typing import Dict, Tuple


class MyOntology:
    """Domain-specific entity / relation types and hierarchies.

    The four required attributes are checked at load time via
    isinstance(obj, OntologyPack) — they must be present as instance
    attributes (or class attributes — Python doesn't distinguish).
    """

    pack_id: str = "mypack"
    entity_types: Tuple[str, ...] = ("widget", "gadget")
    relation_types: Tuple[str, ...] = ("contains", "extends")
    hierarchies: Dict[str, Tuple[str, ...]] = {
        "widget": ("gadget",),
    }
```

The loader registers `entity_types` and `relation_types` with the
existing ontology in `core/relations_schema.py`. Hierarchies are added
to the cascade-resolution graph.

### 4.2 `PromptPack` — system prompts + few-shot

```python
# packs/mypack/prompts.py
from typing import Any, Dict, List


class MyPrompts:
    """Mode-specific prompt overrides.

    Returning the empty string ``""`` for a mode means "let JAMES use
    its default prompt." A pack that only customises the ``meta`` mode
    returns ``""`` from system_prompt() for the other four modes.
    """

    pack_id: str = "mypack"

    def system_prompt(self, mode: str) -> str:
        if mode == "wiki_edit":
            return (
                "You are editing the MyPack knowledge base. Prefer "
                "terse factual entries. Always cite the source URL."
            )
        return ""  # other modes use JAMES defaults

    def few_shot(self, task: str) -> List[Dict[str, Any]]:
        if task == "extract_widget":
            return [
                {"role": "user", "content": "The 4-port USB hub is a widget."},
                {"role": "assistant", "content": "widget(name='4-port USB hub')"},
            ]
        return []
```

The five built-in modes are listed in
`core.plugins.base.KNOWN_MODES`:
`"chat"`, `"meta"`, `"wiki_edit"`, `"self_evolve"`, `"coding"`.

**Returning the empty string** is the graceful fall-through path —
don't raise on unknown modes; future JAMES versions may add modes and
your pack should let them use the default prompt unchanged.

### 4.3 `UIPanel` — server-rendered widget

```python
# packs/mypack/ui/search.py
from core.plugins.base import PanelContext


class SearchPanel:
    """Server-rendered search results widget.

    The path /panels/mypack/search is wired by the loader at startup.
    The HTML returned here is filtered by core/security_layer before
    reaching the client — your pack cannot bypass the response filter.
    """

    pack_id: str = "mypack"
    panel_id: str = "search"

    def render(self, ctx: PanelContext) -> str:
        # Respect the ABAC role — admins see more than externals.
        if ctx.user_role not in ("admin", "employee", "external"):
            return ""  # unknown role: render nothing

        # Locale-aware text. ctx.locale is "ko" / "en" / "ko-KR" etc.
        if ctx.locale.startswith("ko"):
            return "<div class='mypack-search'>검색 결과</div>"
        return "<div class='mypack-search'>Search results</div>"
```

`PanelContext` has three fields:
- `user_role`: ABAC role from `core/policy_engine.PolicyEngine`
- `session_id`: current chat session
- `locale`: ISO 639-1 + optional region

**A panel that ignores `ctx.user_role` and leaks admin-only content
to an external user is a contract violation.** The conformance suite
in PR-C9 will catch the obvious cases, but the responsibility lives
with the pack author.

### 4.4 `Scorer` — custom retrieval scoring

```python
# packs/mypack/scoring/recency.py
import time
from typing import Any, Dict


class RecencyScorer:
    """Prefer recent candidates over older ones.

    Plugged into the existing reranker slot in core/retrieval/. The
    returned score MUST be in [0.0, 1.0]; values outside that range
    are treated as a bug by the reranker.
    """

    pack_id: str = "mypack"

    def score(self, query: str, candidate: Dict[str, Any]) -> float:
        # Candidate dicts carry a 'timestamp' field in epoch seconds.
        ts = candidate.get("timestamp", 0)
        age_days = (time.time() - ts) / 86400.0
        # 1.0 for "today", drops linearly to 0.0 over 90 days.
        score = max(0.0, 1.0 - (age_days / 90.0))
        return min(1.0, score)
```

**Slot conflict**: if two packs both register a `Scorer` against the
same retrieval slot, the loader raises `PluginLoadError` — there is no
silent precedence rule, the operator must resolve the conflict by
removing one of the packs.

---

## 5. Loading the pack

JAMES reads two env vars at startup:

| Env var | Purpose | Default |
|---|---|---|
| `JAMES_PACKS=` | Comma-separated pack names to load | `general` (when unset) |
| `JAMES_WORKSPACE=` | Workspace data root (per-tenant isolation) | current directory |

```bash
# Load just the default pack (same as setting nothing)
python server_llmwiki.py

# Load your pack alongside the default
JAMES_PACKS=general,mypack python server_llmwiki.py

# Load your pack alone (NOT recommended — many JAMES features expect
# `general`'s ontology to be present)
JAMES_PACKS=mypack python server_llmwiki.py

# Multi-instance hosting: one process per workspace
JAMES_PACKS=general,mypack \
JAMES_WORKSPACE=/srv/james/tenant-acme \
python server_llmwiki.py
```

### A note on the two env vars: `JAMES_PACKS` vs `JAMES_PLUGINS`

JAMES has **two** plugin loaders, by historical accident:

- `JAMES_PLUGINS=` — **reasoning backend** loader (PR #326 in v0.2.x).
  Takes dotted module paths. Used to register new reasoning-loop
  backends (e.g. a custom planner).
- `JAMES_PACKS=` — **pack** loader (PR-C3 in v0.3, this contract). Takes
  pack names. Used to register the four slots described above.

They are **independent** — set both if you want to ship a pack
*and* a reasoning backend. The two-env surface is documented here so
pack authors don't accidentally collide with the older loader.

### Three startup failure modes (all fatal, no silent fallback)

1. `JAMES_PACKS=` (empty string): `PluginLoadError("no pack loaded;
    set JAMES_PACKS=general (or another pack name)")`.
2. `JAMES_PACKS=mypack` but `packs/mypack/` is missing:
    `PluginLoadError("pack 'mypack' not found at packs/mypack/")`.
3. `pack.yaml::james_api` doesn't contain the current core version:
    `PluginVersionError`.

---

## 6. Local testing

Until PR-C9 ships the CI eval contract, here's the minimum local
verification a pack author should run:

```bash
# 1. Verify the manifest parses
python -c "
from pathlib import Path
from core.plugins.manifest import read_manifest
m = read_manifest(Path('packs/mypack/pack.yaml'), 'mypack')
print(f'OK: {m.name} v{m.version}, license={m.license}')
"

# 2. Verify the loader accepts it
JAMES_PACKS=mypack python -c "
import os
from core.plugins.loader import load_packs_from_env
loaded = load_packs_from_env()
for m in loaded:
    print(f'Loaded: {m.name} v{m.version}')
"

# 3. Verify each Protocol implementation satisfies isinstance check
python -c "
from core.plugins.base import OntologyPack
from packs.mypack.ontology import MyOntology
o = MyOntology()
assert isinstance(o, OntologyPack), 'MyOntology fails OntologyPack protocol'
print('OK: OntologyPack satisfied')
"

# 4. Full JAMES startup
JAMES_PACKS=general,mypack python server_llmwiki.py
# (then drive the actual JAMES UI to exercise your slots)
```

If you have STEP 7 regression queries that touch your pack's
ontology, run them against the dogfood baseline:

```bash
python scripts/step7_query_test.py
```

The pack-author CI eval contract (PR-C9, not yet landed) will codify
which scores a pack must clear before merging into the main JAMES repo
or being listed in the future marketplace.

---

## 7. Common gotchas

### "My class isn't being recognised as an `OntologyPack`"

Protocol satisfaction in Python is structural. The most common cause
of a class failing `isinstance(obj, OntologyPack)` is a missing or
mistyped attribute. Check that:

- All four attributes (`pack_id`, `entity_types`, `relation_types`,
  `hierarchies`) are present as instance attributes
- `entity_types` and `relation_types` are tuples, not lists or sets
- `hierarchies` is a dict, not a tuple-of-tuples

Use `isinstance()` locally to find the gap before the loader does.

### "The loader can't find my class"

The `module:Class` shape in `pack.yaml::plugins` is resolved by
importing `packs.<pack_name>.<module>` and looking up `<Class>` as
an attribute. So:

```yaml
plugins:
  ontology: ontology:MyOntology
```

means `from packs.mypack.ontology import MyOntology`. If your class
lives in `packs/mypack/ontologies/v2.py`, use:

```yaml
plugins:
  ontology: ontologies.v2:MyOntology
```

### "My pack version 0.5.0 won't load against JAMES 0.3"

That's by design — the `james_api:` range you declared doesn't contain
the running JAMES core version. Either:

- Update `pack.yaml::james_api` to include the JAMES version you're
  running (e.g. `">=0.3,<0.4"`)
- Bump your JAMES install to a version your pack accepts

The loader prints the exact mismatch in the `PluginVersionError`
message.

### "I added a method to my Protocol implementation and now the loader
warns about deprecation"

You can't add to JAMES's Protocols from a pack — only JAMES core
can extend its own contracts. Extra methods on your concrete class
are fine and ignored by JAMES; the warning is likely about something
else (e.g. you imported a deprecated helper from `core.plugins`).
See [`VERSIONING.md`](VERSIONING.md) §4 for the deprecation policy.

### "Two packs declare the same slot and JAMES refuses to start"

Slot conflicts are intentional. The loader does not pick a winner
silently because the choice has security and behavior consequences
(e.g. two `Scorer`s biasing retrieval in opposite directions).
Remove one pack from `JAMES_PACKS=` or have the conflicting packs
collaborate upstream.

---

## 8. License options

The closed enum in v0.3 is `MIT` / `Apache-2.0` / `AGPL-3.0` /
`proprietary`. Choose per:

| License | Use case |
|---|---|
| `MIT` | Open-source pack, permissive. Matches JAMES core. |
| `Apache-2.0` | Open-source pack, patent grant. |
| `AGPL-3.0` | Open-source pack, copyleft including network services. |
| `proprietary` | Private pack. Logs a startup warning so operators are aware. |

Widening past this enum is planned for v1.0 when the marketplace
ships and SPDX-allowlisted identifiers become valid. Until then, a
pack that needs a license outside the enum cannot ship in this repo
— it can ship in a private repo loaded via `JAMES_PACKS=` to a path
your install resolves, but it cannot be PR'd to `Hashevolution/James-RAG-Evol`.

See [`docs/LICENSE_PLAN.md`](LICENSE_PLAN.md) §5.2 for the rationale.

---

## 9. What comes next

- [`docs/VERSIONING.md`](VERSIONING.md) — the SemVer contract, what
  counts as breaking, the 12-month deprecation window.
- `docs/design/v0.3-plugin-api.md` — the design memo for the contract
  itself (the "why" behind the four types and the loader semantics).
- `packs/general/pack.yaml` — once PR-C5 lands, the dogfood pack will
  be the most up-to-date example of every slot type in use.
- PR-C9 — CI eval contract for `packs/*/`. Until that lands, run
  STEP 7 manually as in §6.

---

## 10. 한국어 한 줄 결론

팩은 `packs/<name>/pack.yaml` + 4 가지 Protocol slot (`ontology`,
`prompts`, `ui`, `scorers`) 중 일부를 구현하는 Python 패키지다.
`JAMES_PACKS=<name>` 환경변수로 시작 시 로드되며, 매니페스트의 모든
요구 필드 (`name`, `version`, `james_api`, `description`, `author`,
`license`) 와 SemVer 정합성은 시작 시점에 엄격히 검증된다. 침묵하는
fallback 은 없다 — 실패는 즉시 명시적 에러로 드러난다. v0.3 의 라이선스
enum 은 `MIT` / `Apache-2.0` / `AGPL-3.0` / `proprietary` 의 4 종에
한정되며, v1.0 마켓플레이스 진입 시 SPDX allowlist 로 확장 예정.
