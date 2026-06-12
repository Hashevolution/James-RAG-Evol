# Ontology Pack Authoring Guide — v0.6 G8 mount mechanism

**Status**: Mother-platform spec for third-party ontology pack
authors using the **v0.6 G8 in-process mount mechanism**
(`core/ontology_packs.py`). Companion to but distinct from the
older `docs/PLUGIN_AUTHORING.md` (v0.3 4-slot `packs/` contract
with `pack.yaml` manifests). Listed as a v1.0 gate requirement
in [`docs/PLATFORM_READINESS.md`](PLATFORM_READINESS.md) §3
"Gate v1.0" — Public SDK + plugin author guide.

**Date**: 2026-06-12 (v0.6 prep)

**Audience**: external developers building ontology packs for
JAMES SaaS / on-prem deployments — vertical domain integrators
(legal / medical / finance / etc.), customer-specific knowledge
layer authors, internal teams extending the mother schema.

**Pre-requisites**: this guide assumes familiarity with
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §5 (mother / pack
separation) + [`docs/PLATFORM_READINESS.md`](PLATFORM_READINESS.md)
§3 (v0.6 / v1.0 gates) + [`CLAUDE.md`](../CLAUDE.md) rule #1
(no domain features until v1.0).

---

## 0. v0.3 packs/ vs v0.6 G8 — which contract?

Both surfaces exist. Pick the right one for your use case:

| Surface | v0.3 `packs/<name>/` | v0.6 G8 `core/ontology_packs.py` |
|---|---|---|
| File layout | `packs/<name>/{pack.yaml,*.py}` | Pure-Python module; no directory contract |
| Manifest | `pack.yaml` (name, version, james_api) | `OntologyPack` dataclass fields |
| Slots | 4 (ontology / prompts / ui / scorers) | 1 (ontology only) |
| Mount mechanism | `JAMES_PACKS=<name>` env at boot | `register_pack(pack)` at any time |
| Unmount | restart with different `JAMES_PACKS` | `unmount_pack(pack_id)` at runtime |
| Audit-replay | not designed for it | first-class — emits lifecycle events |
| Capability gate | none | `requires_capability` + `JAMES_CAPABILITIES` env |
| Rule #1 enforcement | doc-level only | code-level (capability default empty) |
| Reference guide | [`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md) | **this document** |

**Use v0.6 G8** when:
- You need ontology extensions only (no prompts / UI / scorer)
- You want runtime mount/unmount (e.g. customer-specific schema
  loaded on per-tenant boot)
- You need audit-replay determinism (every mount/unmount is a
  lifecycle event)
- You want code-level Rule #1 enforcement

**Use v0.3 `packs/`** when:
- You need prompts / UI panels / custom scorers (slots G8 doesn't
  cover)
- You're shipping a fully-integrated vertical product (the
  reference packs/general/ is the dogfood for this)
- You need pack-author-controlled metadata (license / SemVer
  api constraint / etc.)

The two surfaces can coexist: a v0.3 pack can ship ontology
content via its own `OntologyPack` protocol class, while a
v0.6 G8 pack ships only the ontology dataclass. They are
distinct registries; a name registered in one does NOT prevent
registration in the other (potential v1.0 cleanup item).

The rest of this document is about **v0.6 G8 only**.

---

## 1. What is a v0.6 G8 pack?

A **pack** is a pure-data extension that adds horizontal
primitives to the mother ontology. Concretely, a pack carries:

  * Document **subtypes** (e.g. `contract`, `procedure`,
    `case_brief` — see §6 for vertical-content gating)
  * **Relation types** (e.g. `AUTHORED_BY`, `APPROVED_BY`,
    `CITES`, `DERIVED_FROM`)
  * **Enterprise roles** (e.g. `AUTHOR`, `REVIEWER`,
    `APPROVER`)
  * **Label-to-type** localisation map

A v0.6 G8 pack is NOT:

  * Code (no Python / JS files inside the pack itself —
    `core/` extensions are a separate v1.0 plugin-code surface)
  * Prompts (use the v0.3 `packs/<name>/prompts/` slot for
    that)
  * UI (use the v0.3 `packs/<name>/ui/` slot for that)

The single-responsibility shape is intentional: G8 packs are
**ontology data only**, which keeps the audit-replay contract
simple and the mount/unmount lifecycle cheap.

---

## 2. The mount lifecycle

Every G8 pack moves through 4 states:

```
              ┌──────────────┐    register_pack    ┌──────────────┐
              │ unregistered │ ───────────────────▶ │   mounted    │
              └──────────────┘                      └──────┬───────┘
                       ▲                                   │
                       │ unmount_pack                      │
                       │                                   ▼
                       └───────────────────────────  archive
```

* **Unregistered**: the `OntologyPack` dataclass exists in code
  but `register_pack()` has not been called. The mother
  ontology behaves as if the pack doesn't exist.
* **Mounted**: `register_pack()` succeeded. The pack's subtypes /
  relations / roles appear in `all_document_subtypes()` /
  `all_relation_types()` / `all_enterprise_roles()` (the read-
  side helpers from G8.b).
* **Unmounted (archive)**: `unmount_pack()` succeeded. Pack
  data no longer appears in the lookup helpers, but existing
  audit rows referencing pack-defined names remain replayable
  via the G8.c event stream — `reconstruct_graph_at(t)` at any
  prior time T returns a snapshot whose `mounted_pack_ids`
  field reflects the registry as it was at T.

The lifecycle is **deterministic and audit-replayable** by
construction.

---

## 3. Capability gate (Rule #1 enforcement)

Every pack must declare `requires_capability`, a string naming
a capability the operator has explicitly granted via the
`JAMES_CAPABILITIES` env var (comma-separated list).

**Mother default is empty** → no pack can mount.

The mother-platform code uses this to enforce CLAUDE.md rule #1
(no domain features until v1.0 / LOI). Vertical packs declare
`requires_capability="rule_one_exemption_granted"`, which the
operator only grants in environments where:

1. A signed customer LOI scopes the vertical, OR
2. v1.0 has shipped and the gate is broadly opened.

Without the grant, `register_pack()` raises
`CapabilityNotGrantedError` at mount time. The pack's
`OntologyPack` dataclass can exist in code, can be imported,
can be inspected — but cannot influence runtime behaviour.

### 3.1 Granting capabilities (operator-side)

```bash
# Production SaaS (post-LOI scoping):
export JAMES_CAPABILITIES="rule_one_exemption_granted,custom_pack_owner"

# Local-dev (no packs mounted, mother only):
unset JAMES_CAPABILITIES
```

Capability names are case-sensitive. Whitespace around each
name is stripped. Empty names (trailing comma) are dropped.
The env is **never cached** — operator can toggle mid-process
by setting/unsetting it and triggering a re-mount.

### 3.2 What if a pack needs multiple capabilities?

It doesn't. Each pack declares **exactly one**
`requires_capability` per the B.3 §4.1 contract. If you have
two distinct concerns (e.g. "this pack contains sensitive
schema" + "this pack contains PII-tagged columns"), ship two
packs that each gate on its respective capability.

---

## 4. Authoring a pack — minimal example

```python
# my_pack/pack.py
from core.ontology_packs import OntologyPack

LEGAL_DEMO_PACK = OntologyPack(
    pack_id="legal-demo-v1",
    requires_capability="rule_one_exemption_granted",
    subtypes={
        "case_brief": {
            "parent": "document",   # must be a mother entity type
            "since":  "v1.0",
        },
        "memorandum_of_understanding": {
            "parent": "document",
            "since":  "v1.0",
        },
    },
    relation_types={
        "CITES": {
            "label":     "cites",
            "inverse":   "CITED_BY",
            "transitive": True,
            "weight":     1.0,
            "sensitive":  False,
            "allowed_head": {"document"},
            "allowed_tail": {"document"},
        },
    },
    enterprise_roles={
        "OUTSIDE_COUNSEL": {
            "perms_over_doc": {"read", "comment"},
        },
    },
    label_to_type={
        # i18n labels → canonical type names
        "인용함": "CITES",
        "cites":  "CITES",
    },
    since="v1.0",
    provenance=(
        "Hashevolution legal pack, customer-LOI #12345, "
        "signed 2027-Q1. Renewed annually."
    ),
)
```

### 4.1 Mounting

```python
# server_llmwiki.py or operator-supplied bootstrap script
from core.ontology_packs import register_pack
from my_pack.pack import LEGAL_DEMO_PACK

register_pack(LEGAL_DEMO_PACK)
```

If the operator has not granted `rule_one_exemption_granted`,
this raises `CapabilityNotGrantedError` immediately. The pack
is unmounted; the mother ontology behaves as if the import
never happened.

### 4.2 Unmounting

```python
from core.ontology_packs import unmount_pack
unmount_pack("legal-demo-v1")
```

`unmount_pack` raises `KeyError` if the pack id is not
currently mounted (defensive — silent unmount on unknown is
an operator-error mask).

---

## 5. The 4-vertical test (mandatory)

**Every pack must pass the 4-vertical test before shipping.**

The test is a self-audit: name 4 verticals (legal, food,
retail, finance — or 4 in your domain), and check that your
pack's subtype + relation + role names would work in all 4.
A "vertical" name like `contract` passes; a "vertical" name
like `nda` does not (it's legal-specific).

| Pack content | Passes 4-vertical? | Why |
|---|---|---|
| `subtypes: {"contract": ...}` | ✓ | Used in legal AND finance AND retail AND food |
| `subtypes: {"nda": ...}` | ✗ | Legal-only (does not generalise to food / retail / finance) |
| `relation_types: {"AUTHORED_BY": ...}` | ✓ | Authoring is universal |
| `relation_types: {"PATIENT_CONSENTED_TO": ...}` | ✗ | Medical-only |
| `enterprise_roles: {"APPROVER": ...}` | ✓ | Every vertical has approvers |
| `enterprise_roles: {"COMPLIANCE_OFFICER": ...}` | ✓ | Every regulated vertical has one |
| `enterprise_roles: {"SOMMELIER": ...}` | ✗ | Food-only |

A pack that fails the 4-vertical test **must** declare
`requires_capability="rule_one_exemption_granted"`, since by
construction it is a vertical pack — its names will collide
with the next customer's pack and the mother contract.

A pack that **passes** the 4-vertical test can theoretically
ship with a more permissive capability (e.g.
`horizontal_pack_owner` instead of `rule_one_exemption_granted`).
However, horizontal packs are extremely rare — almost everything
worth shipping outside the mother is at least somewhat
domain-specific.

---

## 6. Schema validation (mother-platform invariants)

`register_pack()` enforces three invariants:

### 6.1 Subtype `parent` must be a mother entity type

```python
# OK — mother has `document` as an entity type
subtypes={"my_subtype": {"parent": "document"}}

# ERROR — `not_a_type` is not in core.ontology.ENTITY_TYPES
subtypes={"my_subtype": {"parent": "not_a_type"}}
# → SchemaError: subtype 'my_subtype' parent 'not_a_type'
#                is not a known mother entity type
```

The mother entity types (in `core/ontology.py::ENTITY_TYPES`)
include: `document`, `person`, `org`, `concept`, `event`,
`location`, `date`, `quantity`, `project`. Your pack's
subtypes attach to one of these.

### 6.2 No name collision

A pack cannot register a name (subtype / relation / role) that
is already used by:

  * The **mother** ontology (`DOCUMENT_SUBTYPES` /
    `RELATION_TYPES` / `ENTERPRISE_ROLES` from
    `core/ontology.py`)
  * Any **already-mounted** pack

```python
# ERROR — `contract` is a mother subtype
subtypes={"contract": {"parent": "document"}}
# → NameCollisionError: pack 'my-pack' tried to register
#                       'contract' as subtype; already
#                       claimed by 'mother'
```

The operator must rename the conflicting name in your pack
before mounting. This is enforcement, not friction: silent
override of mother semantics would break the audit-replay
contract.

### 6.3 Within-pack double-claim

A pack cannot declare the same name as both a subtype AND a
relation, or any other combination of two fields:

```python
# ERROR — `dual` appears as both subtype and role
OntologyPack(
    pack_id="bad-pack",
    requires_capability="cap_x",
    subtypes={"dual": {"parent": "document"}},
    enterprise_roles={"dual": {"perms_over_doc": []}},
)
# → NameCollisionError: pack 'bad-pack' declared 'dual'
#                       as both 'subtype' and 'role'
```

---

## 7. Read-side lookup (G8.b helpers)

When your pack-aware code needs to traverse the merged
ontology, use the G8.b helpers (not the raw mother dicts):

```python
from core.ontology_packs import (
    all_document_subtypes,
    all_relation_types,
    all_enterprise_roles,
)

# Returns: mother + every currently-mounted pack, merged
subtypes = all_document_subtypes()
relations = all_relation_types()
roles = all_enterprise_roles()

# Pack-unaware code can continue to use the direct imports
# from core.ontology — those return only the mother set.
```

**Mother takes precedence** on duplicate names (defensive —
`register_pack` already blocks collisions at mount time, but
a future race would still fall back to mother behaviour).

---

## 8. Replay-side semantics (G8.c)

Every `register_pack()` / `unmount_pack()` call emits a
lifecycle event row into the audit_log via
`emit_lifecycle_event`. The event types are:

| Event type | Payload fields |
|---|---|
| `lifecycle.ontology.pack_mounted` | `pack_id`, `requires_capability`, `since`, `provenance` |
| `lifecycle.ontology.pack_unmounted` | `pack_id` |

`reconstruct_graph_at(t)` (in `core/lifecycle/replay_graph.py`)
reads the event stream up to `t` and returns a `GraphSnapshot`
whose `mounted_pack_ids` field is a tuple of pack ids that
were mounted at exactly that moment. This is the audit-replay
contract — an external auditor can reconstruct "which packs
were active at audit cutoff T?" deterministically from the
audit log alone.

Example:

```python
from datetime import datetime, timezone
from core.lifecycle.replay_graph import reconstruct_graph_at

# What ontology packs were active on 2026-12-25?
snap = reconstruct_graph_at(
    datetime(2026, 12, 25, tzinfo=timezone.utc),
)
print(snap.mounted_pack_ids)
# → ('legal-demo-v1', 'finance-baseline-v2')
```

---

## 9. Pack versioning

A pack's `since` field is purely informational — it identifies
the version of the pack that the operator chose to mount. To
roll out a v2 pack:

1. Author `pack_v2.py` with `pack_id="legal-demo-v2"`
   (different id; same `requires_capability`)
2. `register_pack(LEGAL_DEMO_PACK_V2)`
3. `unmount_pack("legal-demo-v1")` (or keep both mounted if
   they don't collide on names)

The audit-replay layer captures both transitions:
`reconstruct_graph_at(t_before)` returns `("legal-demo-v1",)`,
`reconstruct_graph_at(t_after)` returns `("legal-demo-v2",)`.

There is **no versioning resolution in the runtime** — the pack
author chooses unique ids and the operator chooses which to
mount. SemVer-style version negotiation is explicitly out of
scope (would conflict with the audit-replay determinism).

---

## 10. Distribution

How your pack module gets imported into the JAMES process is
an **operator concern**, not a runtime API concern. Common
patterns:

  * **PyPI**: `pip install james-pack-legal-demo` →
    `from james_pack_legal_demo import LEGAL_DEMO_PACK`
  * **Git submodule**: customer clones the pack repo as a
    submodule under `packs/`
  * **Customer-supplied zip**: operator extracts to a known
    location and imports
  * **Inline**: small pack lives in the same repo as the
    JAMES deployment

All four work — the runtime only cares that you can
`from somewhere import YOUR_PACK` and call
`register_pack(YOUR_PACK)`.

The Pack SDK CLI (`python -m james.pack init <pack_id>`,
shipping in SDK.a separate PR) generates a PyPI-ready
scaffold — the recommended distribution path for production
packs.

---

## 11. What this guide does NOT cover

- **Code-side pack content** (custom cascade rules, custom
  scorer plugins) — use the v0.3 `packs/<name>/` 4-slot
  contract for that (see [`docs/PLUGIN_AUTHORING.md`](PLUGIN_AUTHORING.md)).
- **Prompt template plugins** — same. The v0.3 `prompts/` slot
  is the right surface.
- **UI panel plugins** — same. v0.3 `ui/` slot.
- **Multi-tenant pack isolation** — currently every pack is
  process-wide. Per-tenant pack mounting (so tenant_A sees
  pack_X while tenant_B does not) lands in v0.6 G1.c +
  pack-tenant filter, separate PR.
- **Pack signing / verification** — operator-side concern
  (PyPI signature, supply-chain check) not a runtime contract.

---

## 12. References

- v0.6 G8.a (mount mechanism): PR #868
- v0.6 G8.b (read-side helpers): PR #871
- v0.6 G8.c (replay events): PR #872
- B.3 design memo:
  `docs/reviews/v0.5-b3-plugin-api-stability.md`
- v0.5 close handover (Track B SDK series queue):
  `docs/handovers/v0.5-close-2026-06-12.md` §5.2
- v0.3 4-slot plugin contract (companion surface):
  `docs/PLUGIN_AUTHORING.md`
- Mother ontology:
  `core/ontology.py` (ENTITY_TYPES, DOCUMENT_SUBTYPES,
  RELATION_TYPES, ENTERPRISE_ROLES)
- Runtime API:
  `core/ontology_packs.py`
- Replay layer:
  `core/lifecycle/replay_graph.py` +
  `core/lifecycle/replay_packs.py`
- CLAUDE.md rule #1:
  `CLAUDE.md` (no domain features until v1.0 / LOI)
- PLATFORM_READINESS gate v1.0 (Public SDK requirement):
  `docs/PLATFORM_READINESS.md` §3

---

## 13. Korean summary (한국어 요약)

**JAMES v0.6 G8 온톨로지 팩 작성 가이드** (v0.3 4-slot 컨트랙트와
별도, `core/ontology_packs.py` 의 in-process mount mechanism 용):

- **팩 = 순수 데이터** (subtypes / relations / roles / labels).
  코드 / 프롬프트 / UI 는 v0.3 packs/ 컨트랙트 사용.
- **마운트 lifecycle**: unregistered → mounted → unmounted.
  모든 transition 이 audit-replay 가능.
- **Capability gate**: 모든 팩이 `requires_capability` 선언
  필수. mother default 빈 set → 팩 마운트 불가. vertical 팩 =
  `rule_one_exemption_granted` 필요 (LOI scoping 후 operator
  명시 grant).
- **4-vertical test**: 팩의 모든 이름 (subtype / relation /
  role) 이 4개 vertical (legal / food / retail / finance) 에
  모두 통하는가? Yes → horizontal OK. No → vertical, capability
  필수.
- **Schema invariants**: subtype.parent 는 mother entity type;
  no collision with mother / already-mounted pack; no
  within-pack double-claim.
- **Read-side**: `all_document_subtypes()` / `all_relation_types()`
  / `all_enterprise_roles()` 헬퍼가 mother + mounted packs 머지.
- **Replay**: `reconstruct_graph_at(t).mounted_pack_ids` 가
  시점 T 의 팩 구성 결정적 재현.
- **Distribution**: PyPI / git submodule / zip / inline — operator
  선택. CLI 스캐폴더 (`python -m james.pack init`) 는 SDK.a 별도 PR.
- **이 doc 가 다루지 않는 것**: 코드 plugin (v0.3 packs/), 프롬프트
  plugin (v0.3 prompts/), UI panel (v0.3 ui/), multi-tenant 팩 격리
  (G1.c 별도 PR), 팩 서명 / 검증 (operator-side concern).
