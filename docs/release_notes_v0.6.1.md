# v0.6.1 — product hardening: the platform becomes something an operator uses daily

**Released**: 2026-09-10 (PR sequence #831 → #1112, 2026-06-12 → 2026-09-09).

**DOI**: not issued. See *Scope and naming* below — DOI issuance is an
operator decision tied to the Fork A/B strategy gate, per the v0.6 entry
contract.
**Predecessor**: [`v0.4.4`](release_notes_v0.4.4.md) — DOI
[`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679).

**Theme**: v0.4.4 closed a *measurement* cycle. v0.6.1 closes a **product**
one. Nothing here changes what JAMES concludes — the retrieval layer is
untouched to the line — but almost everything changes what it is like to
run. An agent track, unified LLM routing chosen by paired measurement, a
rebuilt chat UX, eight pages consolidated into five, a CSP `style-src`
that no longer needs `'unsafe-inline'`, and one **measurement-gated
correctness fix** to live graph traversal that the cascade work turned up.

---

## Scope and naming — read this first

The tag is named `v0.6.1` because that is the cycle the bulk of the work
belongs to. **What it contains is wider than that name suggests.**

`v0.4.4` was the last tag. Everything after it — the v0.5 cycle close,
the v0.6 deployment-hardening stream, the v0.6.1 product work, and the
2026-09 restart that brought CI back to green — shipped to `main` without
a tag. This release is the first published artifact containing any of it.

| Window | PRs | Count |
|---|---|---:|
| v0.5 close + v0.6 entry skeleton | #831 – #911 | 81 |
| v0.6 / v0.6.1 product hardening | #912 – #1076 | 165 |
| Idle-period maintenance | #1077 – #1082 | 6 |
| v0.6.2 restart (CI green, CSP) | #1083 – #1112 | 30 |
| **Total** | **#831 – #1112** | **282** |

522 files changed, +90,289 / −5,838.

**`v0.5` has no tag of its own.** Whether to add one retroactively is an
operator decision: it changes the DOI lineage, which this project has had
to correct once already (#1077). The `CHANGELOG.md` sections
`[0.5.0-close]` and `[0.6.0]` remain the per-cycle record; this release
is the artifact that publishes them.

**This is not a v0.6 cycle entry.** The v0.5 → v0.6 gate (Dim F — a
six-month external customer pilot) is still open, and the 2-fork contract
from 2026-06-13 stands, with a decision point around 2026-12-13. A
product release is not a strategy decision.

---

## What's new

### Agent track — JAMES can work in a folder

| PR | Summary |
|---|---|
| #918 – #921 | Operator-allowed paths, `core/agent_tools` + an LLM tool-use loop, agent chat endpoint, admin panel |
| #1039 | `run_shell` tool — **default-OFF**, admin-only, behind `JAMES_AGENT_ENABLE_SHELL` |
| #1040 – #1047 | Folder picker, model select, merged agent page, DB-persisted sessions, cloud Claude via the Max-plan CLI (no API key) behind a `JAMES_AGENT_ALLOW_CLOUD` UI toggle |

The shell tool ships disabled and admin-only. Cloud egress from the agent
is a separate, explicit toggle — it does not inherit any other cloud
permission.

### LLM routing unification, decided by measurement

`DEFAULT_PREFERENCE` is now per-mode (chat / retrieval / meta / wiki_edit
/ vision), and **each mode's backend was chosen by a 3-cell paired
measurement**, not by assumption (#961 – #990).

Two findings worth carrying forward:

- **Interpolated is not the same as measured.** `gemma3:4b` was the
  hypothesised chat winner and came out **worst** (3/3 abstentions on
  "안녕하세요"); `gemma3:12b` leads. Promotion rejected (#971).
- **A judge can be wrong in a consistent direction.** Re-scoring the
  same runs against deterministic `gold_signals` showed the Claude judge
  over-crediting local models by +0.11 – +0.19 (#968). Conclusions drawn
  from judge-only scores in the prior cycle were re-derived.

Supporting hardening: a measurement-environment isolation contract
(lock-test + pre-flight, #963), a thinking-mode contract with a 4-layer
guard (#965), and privacy-gate + monthly-cost-cap primitives wired into
the cloud-egress site with defence-in-depth (#980 – #988).

### Chat UX rebuild + the SEKOS / JAMES naming split

#927 – #960 rebuild the chat surface: sidebar-first layout, session
popover with favourites synced across devices, answer typography, Korean
mobile readability (eojeol wrapping), and an answer-truncation guardrail
driven by a **real server truncation signal** rather than a client
heuristic (#1060).

**#934 fixes the brand contract**: *SEKOS* is the product name in UI,
README and outward-facing material; *JAMES* stays the engine codename in
source, `JAMES_*` environment variables, `--sut james`, the RAB/LRB
benchmarks and every Zenodo DOI. Reproducibility keeps the old name on
purpose.

One fix worth naming: the sidebar's "+ 새 대화" pill was wired to
`clear-history`, a server-side DELETE — an operator lost a session by
pressing what looked like "new chat". The default is now
non-destructive (#949).

### UI consolidation, 8 → 5 pages

#998 – #1017: decorative emoji out of every non-chat surface, `/` becomes
a public intro front door with chat at `/chat` (old routes 301),
reasoning-flow and knowledge-rollback fold into `/admin/graph` as tabs,
and the workspace gains a real find → view → edit surface for source
material. The answer → trace → graph deep-link loop is closed.

**#1013 adds a visual-regression harness** — 7 pages rendered headless,
console errors and pixel diff against committed baselines. The preceding
UI PRs had been verified only at source level.

### 🔴 Lifecycle live-consistency — a correctness fix found by measuring

The entity-edit cascade (#1018, #1019) prompted a deterministic probe
(#1020), which proved that **live graph traversal filtered relations by
confidence only** and ignored `status.active` / `mutation_type`.
Invalidated, superseded and expired relations were reaching LLM context
(3/3 in the fixture), while `status` was honoured *only* on the
time-travel path. The cascade was effectively cosmetic at the live layer.

`relation_is_live()` (`core/graph_engine/constants.py`, kill-switch
`JAMES_DISABLE_STATUS_FILTER`) now gates traversal output (#1021), graph
score (#1023), the T1 validity window (#1024) and the current-state 3D
snapshot (#1026). Time-travel isolation is pinned (#1025). Path-Recall
analog 1.0 — **no active-relation loss**.

Backlog re-measurement (#1028 – #1032) confirms no regression on the
supersede-sensitive LRB SUTs: HR N=100 reproduces **byte-identically**,
v0.2.3b reproduces its J − N gap.

This is **the single sanctioned break** of the `core/graph` traversal
zero-line streak — probe-first, measurement-gated, kill-switch-equipped.
Report:
`reports/research-runs/lifecycle-live-consistency-arc-20260622.md`.

### Image ingest and vision chain

#1062 – #1075 repair a four-stage bottleneck: vision extraction was using
the text model (#1067), harmful binarisation was dropped and OCR routing
fixed (#1068), EasyOCR became the fallback (#1069), the default vision
model moved to `qwen2.5vl:7b` on a measured OCR win (#1070), and the
vision context window was raised because 12MP images overflowed 4096
tokens (#1072). `/query/` and `/upload/` now heartbeat-stream so a mobile
tunnel drop does not kill a long request (#1073, #1075).

A later fix (#1091) found the related `cv2.imread` failure was **the
filename, not the megapixels** — the same photo read fine as
`photo_12mp.jpg` and returned `None` as `사진_12메가.jpg`, and an
`except` swallowed it, so Korean-named uploads passed silently without
OCR.

### CSP `style-src` graduation

The directive no longer carries `'unsafe-inline'`:

```
- style-src 'self' 'unsafe-inline' https://fonts.googleapis.com
+ style-src 'self' https://fonts.googleapis.com
```

596 inline `style="..."` attributes left the served pages (#1062) and the
JS-injected surface went 479 → 0 (#1095 – #1109). Where a value was
enumerable it became a class; where it is genuinely computed it moved to
`data-*` plus a CSSOM write, which CSP does not govern.

**`JAMES_CSP_MODE` still defaults to `report-only`.** Flipping to
`enforce` is blocked on something else the new
`scripts/csp_enforce_probe.py` found: `graph.html` loads three libraries
from `unpkg.com`, and `script-src 'self'` blocks all three.

### CI

The `--ignore` list is gone. It had carried an iteration plan — un-ignore
each file as its dependency arrives — and that plan had been overtaken:
the files were passing and nobody had checked. Measured in a detached
worktree with no `.env`, Ollama pointed at a dead port and 73 environment
variables stripped, all 51 passed; the CI run on #1111 confirmed it.

**CI now runs 5,309 tests instead of 4,469 — +840, 0 failed.**

---

## Invariants at close

| Invariant | Status |
|---|---|
| `core/retrieval` + `core/retrieval_engine.py` | **0 lines changed** across all 282 PRs |
| `core/graph` traversal | **Broken, deliberately** — the lifecycle arc above, measurement-gated |
| `core/reasoning` | Changed: rule #5 splits, `modes/vision.py`, per-mode routing wire (each preceded by a paired measurement) |
| rule #5 (20 KB module cap) | **0 exceptions** — `GRANDFATHERED` is empty |
| rule #1 (no vertical domain code) | **0 violations** — 13 token hits, all boundary-asserting comments or ordinary English |
| CI | tests / lint / security-scan all success at `5307ab3` |

---

## Known discrepancy — published LRB numbers

`docs/release_notes_v0.4.4.md`, the preprint README and `.zenodo.json`
carry LRB S2 as **V/N/J = 0.225 / 0.5375 / 0.7125**. Since #1089 repaired
a fixture collision, the repository reproduces **0.2500 / 0.5875 /
0.7625**. The headline relation is unchanged — V < N < J holds, and
**J − N is 0.175 in both**, identical to four decimals.

**This release does not rebase the published figures.** Whether to
restate them or footnote them is an operator decision (LRB decision #2,
open since 2026-09-08). The green test suite means *the repository
reproduces itself*, not that it reproduces the paper.

---

## Upgrade notes

- No migration. The lifecycle traversal filter changes what live
  traversal returns; if you need the old behaviour while auditing,
  `JAMES_DISABLE_STATUS_FILTER=1` restores it.
- `run_shell` and agent cloud egress are both **off** unless explicitly
  enabled (`JAMES_AGENT_ENABLE_SHELL`, `JAMES_AGENT_ALLOW_CLOUD`).
- `JAMES_CSP_MODE` defaults to `report-only`; `enforce` is not yet safe
  (see the `unpkg.com` note above).
- Old page routes (`/onboarding`, `/glossary`, `/reasoning-flow`,
  `/knowledge-rollback`) 301 to their new homes.

---

## Full record

- Cycle close handover: `docs/handovers/v0.6.1-close-2026-09-10.md`
- Per-cycle detail: `CHANGELOG.md` — `[0.6.1]`, `[0.6.0]`,
  `[0.5.0-close]`
- Session handovers: `docs/handovers/v0.5-close-2026-06-12.md`,
  `v0.6-entry-skeleton-2026-06-13.md`,
  `v0.6-template-engine-close-2026-06-13.md`,
  `v0.6.1-session-close-2026-06-{23,26}.md`,
  `v0.6.2-restart-roadmap-2026-09-03.md`,
  `v0.6.2-session-close-2026-09-{08,09}.md`
