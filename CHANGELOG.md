# Changelog

All notable changes to PROJECT JAMES will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0-close] — 2026-06-12 → 2026-06-13 — v0.5 cycle close + post-close mother-platform consolidation (UNRELEASED)

**Status**: `main`-branch cycle close + post-close consolidation. **No Zenodo DOI mint** — the v0.5 → v0.6 gate (Dim F: ≥6 month external customer pilot) is not yet cleared, and the 2-fork v0.6 entry contract (LOI signed → Track D / 6-month no-LOI → reassess; see [v0.6 entry skeleton](docs/handovers/v0.6-entry-skeleton-2026-06-13.md)) is the canonical state pointer. This entry documents the cumulative `main`-branch state at the close + post-close interval boundary.

**Theme**: enterprise document ontology mount (B.5 series) + SaaS-readiness primitives (G1 + G2) + Time-Travel Dashboard surface (F.1) + Change Review Workspace surface (F.2) + Pack SDK trio (G8.a-c + SDK.a-c) + CSP nonce middleware (Track C). **Streak preserved across 44 PRs**: zero vertical content, zero `core/retrieval` / `core/graph` traversal / `core/reasoning` lines changed, 4-layer rule #1 protection contract held throughout.

### v0.5 cycle (21 PRs, #841 – #861) — see [`docs/handovers/v0.5-close-2026-06-12.md`](docs/handovers/v0.5-close-2026-06-12.md) for the full PR table

- **B.5 enterprise document ontology** (#841 – #844) — design memo LOCK + 10 horizontal `DOCUMENT_SUBTYPES` + 4 enterprise `RELATION_TYPES` (`AUTHORED_BY` / `APPROVED_BY` sensitive / `REFERENCES` / `DERIVED_FROM`) + 4 `ENTERPRISE_ROLES` + 7-state `DocumentLifecycleState` enum + typed-filter R1-R5 at subtype level + 11-doc generic test fixture. **B.5 series total ~83 tests**.
- **B.1 ontology surface audit + 4 gap closures** (#845 – #849) — audit doc with 8 gaps triaged (3 must-address / 3 strongly-recommended / 2 v1.0-deferred); G7 etag optimistic concurrency, G5 batched contradiction classifier, G4 retention-class metadata, G3 corpus-wide `reconstruct_corpus_view_at` streaming generator. **G3-G7 total ~88 tests**.
- **B.2 / B.3 design memos** (#850 / #851) — multi-tenant isolation contract (G1 tenant-scoped audit + G2 verified approver) + plugin API stability (G8 ontology-pack mount surface for v1.0 plugin-API-freeze gate input).
- **UI improvement stream** (#852 – #856 / #858) — WCAG 2.4.1 skip-link + global `:focus-visible` ring + `<main id="main">` landmark + i18n; `aria-live` regions on `#messages` / `#toast` / `#dash-cards` / `#dash-logs`; mobile responsive (7 newly-covered modals + 44×44 touch target); inline `<script>` extraction → `static/index-init.js` (CSP `script-src 'self'` ready); sensitivity badge + reasoning-panel ARIA + 3-phase landmark; inline `<style>` audit + 3 utility classes (`.is-hidden` / `.field-label` / `.muted-12`) + CSP path-forward doc.
- **External evaluation disclosure** (#857) — `docs/evaluation/v0.5-evaluation-coverage-mapping.md` 13-row standard-metric × JAMES-surface mapping + procurement-readiness checklist (corrects 1 reviewer miss: MRR / NDCG present at `scripts/research/retrieval_quality.py` — research-tier, not headline).
- **Server-side hardening** (#859 – #861) — security headers middleware (`core/security/headers.py`: CSP report-only default + X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy / HSTS opt-in) + G1.a tenant-id primitive (`core/lifecycle/tenant.py`) + G2.a approval-evidence primitive (`core/security/approval_evidence.py`).

### v0.5 close handover (#862) — single source of truth for the cycle deliverables

[`docs/handovers/v0.5-close-2026-06-12.md`](docs/handovers/v0.5-close-2026-06-12.md) — 21 PR enumeration + B.1 gap status sweep (4 LANDED + 2 primitive LANDED + 2 contract-locked + 1 v1.0-deferred) + v0.5 → v0.6 gate definition (Dim F not yet cleared) + 6-track v0.6 work queue (A SaaS-readiness / B SDK + G8 / C CSP / D Dim F LOI-required / E operator-pending / F mother-level UI).

### Post-close consolidation (23 PRs, #863 – #886)

Between v0.5 close (2026-06-12 PM) and 2026-06-13, 23 additional PRs landed implementing most of the close handover §5 work queue:

- **Track F.1 — Time-Travel Dashboard quartet** (#865 / #878 / #879 / #880): TT.a timestamp picker UI shell + `:set` / `:clear` event dispatch; TT.b `GET /admin/graph/reconstruct-at` audit-replay summary overlay (10 tests); TT.c `GET /admin/graph/trace-replay` 3-phase reasoning trail panel matching chat.js `STAGE_META` (8 tests); TT.d `GET /admin/graph/diff-vs-now` side-by-side modal with `chain_extended` projection + audit-evidence deep links (10 tests).
- **Track F.2 — Change Review Workspace quartet** (#866 / #867 / #873 / #874): CR.a list page UI shell + CR.b detail modal with side-by-side diff renderer + CR.c contradiction-arbiter visualisation + CR.d approve/reject buttons + G2.a evidence capture wire.
- **Track A — v0.5 G1 + G2 SaaS-readiness follow-ups** (#869 / #870 / #882 / #883): G1.b `reconstruct_graph_at(t, *, tenant_id=None)` strict-exclusion filter + G2.b `apply_change_request(..., approval_evidence=None)` CR merge wire-in + G1.c [`docs/deployment/v0.6-saas-tenant-isolation.md`](docs/deployment/v0.6-saas-tenant-isolation.md) operator deployment guide + G2.c OIDC resolver hook surface (`register_oidc_validator` + `JAMES_OIDC_ISSUER` / `_TOKEN` / `_AUDIENCE`) + `with_tenant_id_async` contextvars variant (18 tests).
- **Track B — v0.6 Pack SDK trio + G8 mount mechanism** (#868 / #871 / #872 / #875 / #876 / #881): G8.a `core/ontology_packs.py` mount skeleton + `rule_one_exemption_granted` capability gate; G8.b read-side lookup helpers (`all_document_subtypes()` / `all_relation_types()` merging mother + mounted packs); G8.c `EVT_ONTOLOGY_PACK_{MOUNTED,UNMOUNTED}` + `reconstruct_graph_at` dispatch; SDK.a `python -m james.pack init <pack_id>` CLI scaffolder; SDK.b [`docs/ONTOLOGY_PACK_AUTHORING.md`](docs/ONTOLOGY_PACK_AUTHORING.md); SDK.c `pyproject.toml` for `james-pack-sdk` PyPI distribution + [`docs/SDK_VERSIONING.md`](docs/SDK_VERSIONING.md) SemVer 12-month deprecation policy (15 tests).
- **Track C — CSP nonce middleware** (#884): `core/security/csp_nonce.py` per-request `new_nonce()` (16 bytes urlsafe → 22-char base64url) + `JAMES_CSP_USE_NONCE_SCRIPT` (safe to set today — `script-src` already strict-mode-clean per UI #4 PR #855) + `JAMES_CSP_USE_NONCE_STYLE` (reserved for the inline-style migration; sets BREAK the UI without it under CSP3 §6.6.2.4); `build_security_headers(*, script_nonce=None, style_nonce=None)` composition seam + `request.state.csp_nonce` middleware wire-in (20 tests).
- **Graph-RAG synthesis** (#864 / #877 / #885): pre-measurement skeleton ([`docs/evaluation/v0.5-graph-rag-contribution.md`](docs/evaluation/v0.5-graph-rag-contribution.md)) + Step 1 n=3 paired result (**Graph-RAG contributes +0.41 path_coverage** on `multihop_rag` × M_M = gemma4:e4b 4B, noise band 0.02 ⭐⭐⭐ load-bearing; cross-time agreement with α-6 cycle 0.408 → 0.4056 stable across 12 days of oracle revisions) + Step 2 cross-model driver scaffold (`scripts/research/graph_rag_synth_step2_cross_model.py`; pre-agreed interpretation rules in synthesis-doc §3.2; ~14 h wall operator-launchable).
- **v0.6 entry skeleton** (#886): [`docs/handovers/v0.6-entry-skeleton-2026-06-13.md`](docs/handovers/v0.6-entry-skeleton-2026-06-13.md) — bridges v0.5 close → v0.6 entry with: 23-PR post-close enumeration + close handover §5 work-queue status sweep (20 LANDED + 4 LOI-blocked + 6 operator-pending + 2 prerequisite-gated) + 2-fork v0.6 entry contract restated + 4 NEW solo-doable items (TT.b `paintLinks` auto-activation after T5.A.b mutation-site wiring / UI #6 partial Option B / CSP script-flag deploy doc / entry-doc staleness meta-test) + updated mechanical entry checklist + CLAUDE.md "Where to look next" first row pointer updated.

### Default-off invariant preserved across every new flag

| Flag | Default | Verification |
|---|---|---|
| `JAMES_TENANT_ID` (G1.a, PR #860) | unset | `current_tenant_id()` returns `None`; `emit_lifecycle_event` does not stamp `tenant_id` |
| `JAMES_REQUIRE_TENANT_ID` (G1.a, PR #860) | unset | `is_tenant_isolation_enforced()` returns `False`; pre-G1.a emit behaviour preserved |
| `JAMES_REQUIRE_APPROVAL_EVIDENCE` (G2.a, PR #861) | unset | `require_approval_evidence()` returns `False`; `apply_change_request` does not gate on evidence |
| `JAMES_OIDC_ISSUER` / `_TOKEN` / `_AUDIENCE` (G2.c, PR #883) | unset | `_resolve_oidc()` returns `None` without env vars; without a registered validator, `_resolve_oidc()` still returns `None` even if env vars set |
| `JAMES_CSP_USE_NONCE_SCRIPT` / `_STYLE` (Track C, PR #884) | unset | `build_security_headers()` no-kwargs path byte-identical to pre-v0.6 output |
| Time-Travel `paintLinks` link decoration (TT.b, PR #878) | inert | auto-call NOT wired; the helper is exported but waits on T5.A.b mutation-site wiring to populate `link.edge_id` |
| `JAMES_CSP_MODE=enforce` graduate flip (handover §5.3) | NOT shipped | gated on inline-style migration completion (UI #6 audit Option A / B) |

### What this cycle close does NOT do

- **No new Zenodo DOI**. v0.4.4 DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679) remains the most recent published release. v0.5 close is documented on `main` only; DOI mint waits on either Fork A entry (vertical pack release point) or Fork B reassess (strategy-pivot release point).
- **No JAMES production runtime change in the retrieval / graph traversal / reasoning paths.** All 44 cycle PRs touch UI / lifecycle primitives / security / SDK packaging / docs only. The pre-v0.5 routing and inference behaviour is byte-identical when no new env flag is set.
- **Dim F gate (≥6 month external customer pilot) NOT cleared.** The v0.5 → v0.6 gate stays open; the 2-fork entry contract (LOI signed OR 6-month no-LOI reassess) governs the next session's posture.
- **No vertical pack content.** G8.d capability grant workflow is LOI-gated; F.2 CR.e customer-specific theming is LOI-gated; Track D (vertical pack build) is LOI-gated. CLAUDE.md rule #1 4-layer protection contract preserved across all 44 PRs.

### Verification

- **4632 tests** collected across `tests/` (308 test files) — up from ~3290 at v0.4.4. **~420 new tests** added across v0.5 cycle (~290) + post-close (~130).
- B.5 (83) + G3-G7 (88) + UI (0) + security headers (33) + tenant (23) + approval (18) + F.1 TT.b/c/d (28) + F.2 CR.d (verified) + SDK.c (15) + G2.c (18) + Track C (20) + Step 2 scaffold (11) tests all pass on `main`.
- `core/retrieval` / `core/graph` traversal / `core/reasoning` lines changed: **0**.

---

## [0.4.4] — 2026-06-12 — LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure

**Theme**: v0.4.4 extends v0.4.3 with **LRB v0.2.3** — the *Lifecycle Retrieval Benchmark*'s cross-scale reproducibility extension and a sibling axis to RAB v0.1.1. The v0.2.1 cross-model leg-clear (gemma4:e4b 4B / gemma3:12b 12B / mixtral:8x7b 47B / claude-haiku-4-5 cloud) established that **R@1 V<N<J on Phase B (S2 time-travel)** is not a single-model artefact; **v0.2.3 adds the scale axis**: a 4-point ladder spanning a **12.5× scale jump** (S2 N=80 → S3 publication N=1000) preserves the V<N<J inequality at every cell with JAMES − Naive gap above +0.10 throughout. **Pattern + gap are scale-robust ⭐⭐⭐; absolute magnitudes are scenario-sensitive ⭐⭐** (honest framing locked in preprint §5).

Same cycle ships the **cycle γ 4-bench measurement infrastructure closure**: D-alce research-tier NLI adapter + D-2wiki supporting-fact-aware producer promote ALCE and 2Wiki cells from ⭐ infra-only (v0.4.3) to research-tier-ready infrastructure for 4-of-4 cycle γ benches.

**No JAMES production runtime change** — v0.4.4 ships generators, scorers, runners, NLI adapters, 8 pre-registration LOCK documents, and 2 arXiv preprints (papers/rab-preprint, papers/lrb-preprint). The arXiv preprints cite Zenodo DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679) for data availability.

### LRB v0.2.3 — cross-scale reproducibility extension

- **#823 S3 publication-scale generator** — programmatic vocabulary; three presets (smoke 100 docs / 282 events / 100 queries; dev 300 / 1.2k / 300; publication 1000 / 5.6k / 1000); SHA-deterministic; 25 unit tests.
- **#824 S3 token-mode 4-point ladder measurement** — initial verdict.
- **#825 S3.1 contract-vocabulary fix + honest-framing self-correction** — broken `current-contract` category caught via per-category audit; generator fix → honest J magnitude 0.845 (delta +0.132 vs S2 token); re-graded verdict ⭐⭐⭐ pattern + gap / ⭐⭐ magnitude. **First self-catch in the JAMES cycle history's 12 wrong-fix-averted instances**.
- **#826 preprint integration** — papers/lrb-preprint/main.tex §4.6 + §5 + §6.1 + §7.4.
- **#827 v0.2.3b cross-model LLM-grounded runner** — pure-reuse wrapper; operator-gated; pre-reg LOCKED.
- **#829 preprint typo + abstract S3 integration** — 4 fixes.

### Cycle γ 4-bench infrastructure closure

- **#819 audit-trail closure** — canonical claude S2 vanilla R@1=0.6125 committed + ⭐ reproducibility band finding (~10pp claude API non-determinism between ~1.5min-apart runs).
- **#820 D-alce research-tier NLI adapter** — RoBERTa-MNLI + DeBERTa-v3-large-mnli-fever-anli-ling-wanli; T5-XXL deferred; 19 tests.
- **#821 D-2wiki supporting-fact-aware producer** — `[Title #sent_id]` citation prompt + tolerant parser; 24 tests.

### Repository health + papers pre-flight

- **#822 ruff F-class CI hygiene** — 39 → 0 violations; 178 tests green.
- **#828 next-session entry handover**.
- **#830 Zenodo v0.4.4 mint prep** → DOI `10.5281/zenodo.20652679` minted via GitHub Release webhook.
- **#831 preprint Data Availability + Acknowledgements** — DOI inserted.
- **#832 refs.bib citation corrections + LRB \thanks{} commit-hash insertion** — 6 LLM-fabricated citation patterns caught (4 wrong-author + 2 fabricated URLs).
- **#833 Stage-2 deep audit cleanup** — EU AI Act precision, "JAMES T5" → "JAMES", attribution fix.

### Self-correction narrative (12th wrong-fix-averted, first self-catch)

PR #824 originally claimed ⭐⭐⭐ "JAMES R@1 within ±0.05 of S2 token reference". A per-category audit revealed `current-contract R@10 = 0.0` across all 3 SUTs from single-template title cluster collapse. PR #825 fixed the generator, revealed the honest J magnitude (0.845, delta +0.132), and re-graded the verdict. **Strongest applied evidence of the `feedback_oracle_phrase_artifacts` measurement-side-artefact rule**. The prior 11 wrong-fix-averted instances were all user-catches; this is the first self-catch.

### What v0.4.4 does NOT include (separate cycles)

- LLM-grounded S3 publication run (v0.2.3b operator-gated)
- D-alce / D-2wiki research-tier measurement (operator-gated)
- T5-XXL TRUE NLI Mixture integration (GPU-attended)
- HR full sweep n=100 (operator-attended)
- TimeQA / TempReason / GraphRAG SUT (operator data-download gated)
- arXiv preprint submission (pre-flight complete; endorsement = operator-gated last step)

### Verification

After v0.4.4: **~200+ tests pass**. New: `test_alce_nli_adapter.py` (19), `test_wikimulti_cited_producer.py` (24), `test_lrb_s3_generator.py` (27). Existing: 0 regressions.

---

## [0.4.3] — 2026-06-10 — RAB v0.1.1 (Replayable-Audit Benchmark) + Cycle γ multi-hop arc closure

**Theme**: v0.4.3 ships **RAB v0.1.1** — the first replayable-audit benchmark for RAG / agent systems whose 3 metrics (AC / RF / PC) are operationalisations of EU AI Act Articles 10, 12, 19 (in force 2026-08-02). Same cycle closes the cycle γ multi-hop arc (7 probes, 6 honest nulls, 2 self-corrections — `multi-hop improvement` reframed out of the JAMES roadmap; **graph build O(N²) finding** lifted into RAB as the RF-cost axis). No JAMES production runtime change — RAB measures the existing audit / lifecycle / graph paths via a workspace-scoped adapter; production `audit.db` is untouched.

**Default-off invariant preserved**. The cycle γ measurement gates (`JAMES_RETRIEVE_TOP_K`, `JAMES_RERANK_TOP_K`) default to the existing values (8 / 5) and are byte-identical when unset.

### RAB v0.1.1 — R1.0 → R1.5 sequence

- **R1.0 prior-art + EU AI Act anchors (#758 / #760 / #761)** — vacancy confirmed (no replayable-audit benchmark exists); arXiv 2606.04990 (Mathkar et al.) names "realistic execution-trace benchmarks" as an open challenge → RAB responds to a published gap. ActiveGraph (arXiv 2605.21997, 2026-05-21) is independent co-invention of the event-sourced log + replay architecture → **contribution is the benchmark, not the architecture**. EU AI Act Art. 12(1) + 12(2)(b) + 10(2)(b) + 19 verbatim verified; Art. 113 fixes effective date 2026-08-02.
- **R1.1 SPEC v0.1.1 FROZEN (#762)** — `eval/rab/SPEC-v0.1.md`. Abstract log interface (§1, JSONL + canonical event types), three deterministic metrics (§2: AC / RF / PC), scenario contract (§3), reporting format (§4 incl. log_sha + mapping_table_sha for re-verification), 5 baselines (§5: reference / Baseline-0 / Baseline-1 / JAMES / invited audit-native runtimes), 6 honesty clauses (§6). v0.1.1 = v0.1.0 + PC's origin-bearing event rule widened from `INGEST` only to `INGEST | SUPERSEDE` (defect caught by the reference adapter implementation before any measurement was taken; changelog in the SPEC itself).
- **R1.2 scenario-S1 fixture (#763)** — `eval/rab/scenarios/s1_lifecycle_small.json`. 40 ops (11 INGEST / 4 UPDATE / 3 SUPERSEDE / 2 DELETE / 20 QUERY) + 10 checkpoints over a synthetic Northbridge Labs lifecycle. Public-domain content, deterministic ids.
- **R1.3 driver + scorer + reference adapter (#764)** — `eval/rab/{driver,scorer}.py` + `eval/rab/adapters/reference.py` + `tests/test_rab_benchmark.py` (14 tests pinning reference 1.0×3 self-verification + 3 fault-injection variants that drop exactly the targeted metric).
- **R1.4 pre-registration + JAMES adapter + Baseline-0 adapter + measurement (#766 / #767)** — pre-registration `docs/research/r1-4-preregistration-2026-06-10.md` LOCKED before any adapter code or measurement ran (R5 rule). `eval/rab/adapters/baseline0.py` (vanilla in-memory RAG + Python-logging-style records — the floor). `eval/rab/adapters/james.py` (workspace-isolated; SUPERSEDE calls real `core.lifecycle.replay_audit.emit_lifecycle_event` and is cross-verified against `core.lifecycle.replay_graph.reconstruct_graph_at` — JAMES's production code path is actually exercised). `scripts/research/rab_run.py` CLI writes the SPEC §4 re-verification triple (`result.json` + `log.jsonl` + `mapping.json`) per SUT. **31 tests green** across all three test files. Gap-table handover: `docs/handovers/v0.4-r1-4-gap-table-2026-06-10.md`.
- **R1.5 = this release** — packaged for external review (CHANGELOG, `.zenodo.json` v0.4.3, README RAB section, release notes).

### Gap table (RAB SPEC v0.1.1 / scenario-S1)

| SUT | AC | AC INGEST | AC UPDATE | AC SUPERSEDE | AC DELETE | AC ANSWER | RF-exact | RF-graded | PC | events |
|---|---|---|---|---|---|---|---|---|---|---|
| reference (self-verify gate) | **1.000** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **1.000** | 1.000 | **1.000** | 80 |
| **JAMES** | **1.000** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | **1.000** | 1.000 | **1.000** | 80 |
| **Baseline-0** (floor) | **0.275** | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.000** | 0.000 | **0.000** | 40 |

Honest tier: **⭐⭐ scenario-S1 audit-native vs floor gap confirmed** (deterministic, re-runnable from artifacts under `reports/rab/`). ⭐⭐⭐ cross-scenario remains ungated until a future cycle ships additional scenarios. JAMES = reference on S1 is **expected** per SPEC §6.5 — the headline is the gap structure across SUTs, not any single system's score.

### Cycle γ multi-hop arc closure (companion track)

PRs #752 → #757. Cycle γ's MuSiQue probes concluded that "multi-hop improvement" is not a JAMES roadmap item: the wall is unsupervised supporting-paragraph selection, not retrieval breadth and not model ceiling. Top-8 retrieval recall is 0.76 (both R0 and ablated); oracle-grounded performance jumps 8% → 72% (9×) when supporting paragraphs are given directly. The cycle's secondary finding — **graph build O(N²)** — has been lifted out of MuSiQue scope (where it had no leverage) into RAB as the RF-cost axis (SPEC §2.2 `cost_s_per_1k_events`). Memory: `project_cycle_gamma_phase_c2_retrieval_bottleneck`. ★ selector-tuning rabbit hole closed.

Env-gate hooks added: `JAMES_RETRIEVE_TOP_K`, `JAMES_RERANK_TOP_K` (defaults 8 / 5; byte-identical when unset).

### R0 P0 (cycle-pre disciplinary + security)

- **#750** — R5 pre-registration rules + R2 measurement-discipline rules checked into `docs/rules/` as repo-side audit trail (previously memory-only — bus-factor + auditability fix from 2026-06-09 external review action R2).
- **#751** — `starlette` 1.0.1 (CVE) + `chromadb` risk-accept note (`docs/security/`).

### Verification

- `tests/test_rab_benchmark.py` — 14/14 PASS (reference 1.0×3 + 3 fault-injection variants)
- `tests/test_rab_baseline0.py` — 8/8 PASS (floor pinned: AC 0.275 / RF 0 / PC 0)
- `tests/test_rab_james_adapter.py` — 9/9 PASS (audit-native 1.0×3 + workspace isolation + real `emit_lifecycle_event` bridge + `reconstruct_graph_at` agreement + log-only replay invariant)
- **RAB test suite: 31/31 PASS**
- No JAMES core test regression — no `core/` change.
- RAB measurement artifacts committed under `reports/rab/`:
  - `reference-S1-*.{result.json,log.jsonl,mapping.json}`
  - `james-S1-*.{result.json,log.jsonl,mapping.json}`
  - `baseline0-S1-*.{result.json,log.jsonl,mapping.json}`

### What v0.4.3 does NOT do

- No production runtime change in JAMES core.
- No cross-scenario RAB result (S1 only).
- No Baseline-1 (LangSmith/OTel adapter) — separate SUT, future cycle.
- No mutation-site wiring follow-up to v0.4.2 (T1/T2/T2.D/T6/T7 → `emit_lifecycle_event` still deferred).
- No multi-hop retrieval improvement (cycle γ closure re-framed it as not a JAMES roadmap item).
- No regulatory compliance certification claim (SPEC §6.3).

---

## [0.4.2] — 2026-06-06 — T5 Replayable Audit Graph (full event-sourced reconstruction)

**Theme**: v0.4.0 shipped `reconstruct_view_at` — a single-supersede-chain replay primitive. v0.4.2 extends that to **graph-wide event-sourced reconstruction**: a pure-function `reconstruct_graph_at(t)` that rebuilds the full graph snapshot at any past time using only `audit_log` event rows, with no wiki / knowledge_tracker / graph-engine read. That is the **audit-only invariant** — the foundation that makes the "ABAC + replay" claim (corpus retrieval analysis, PR #712 §6) externally demonstrable: ship the `audit_log` JSON → third party reproduces the graph state at any past `t` and the answer's decision tree on top, with no other artifact.

**Default-off invariant preserved**. No new env flag in this cycle. The two new `audit_log` columns (`event_type` / `event_payload`) default NULL on existing rows; mutation-site wiring (T1/T2/T2.D/T6/T7 call sites → `emit_lifecycle_event`) is intentionally a follow-up cycle (cross-cutting change kept out of v0.4.2 so the read-side primitive can land independently). Production `audit_log` keeps emitting only reasoning trace rows until wiring lands.

### T5 — 5-PR sequence (#719 → #720 → #721 → #722 → PR-T5.D)

Per `docs/design/v0.4.2-t5-replayable-audit-graph.md`:

- **#719 T5 design memo** — 15 sections covering partial-vs-full scope, audit-only invariant, event-type taxonomy, API design, cross-chain integration, 5-PR phase plan, 5 Decision LOCKs, cross-cutting impact analysis, closure conditions.
- **#720 PR-T5.A — event taxonomy + emit helper + audit_log migration**. `core/lifecycle/replay_audit.py` (`LIFECYCLE_EVENT_TYPES` with 7 entries: T7 supersede ×2, T6 cascade, T1 expiration, T2 dispatch, T2.D ingest dispatch, migration backfill; `EVT_*` constants; `is_lifecycle_event` exact-match predicate; `emit_lifecycle_event` synchronous in-transaction insert — never raises). LOCK 1 (event_payload = JSON string column) + LOCK 2 (synchronous in-transaction emit). `scripts/migrate_v042_replay_audit.py` (idempotent ALTER TABLE adding `event_type` + `event_payload` columns; `--dry-run` / `--apply` / `--verify` / `--no-snapshot`; pre-write snapshot at `<db>.pre-v042-migration`). 19 contract tests.
- **#721 PR-T5.B — `reconstruct_graph_at` audit-only primitive**. `core/lifecycle/replay_graph.py` (frozen `GraphSnapshot` dataclass: edges / supersede_chains / invalidated_ids / replayed_at / event_count; `reconstruct_graph_at(t, *, audit_log_path=None, include_event_types=None)`). Per-event-type handlers for every `LIFECYCLE_EVENT_TYPES` entry; import-time assert `set(_HANDLERS) == set(LIFECYCLE_EVENT_TYPES)` makes any drift a load-time error. LOCK 4 (pure function — only side-channel is the audit_log SELECT). Defence-in-depth (malformed JSON / unknown event_type / pre-migration DB / non-existent file all return the empty snapshot). 20 contract tests + 4 invariants (I1 audit-only / I2 supersede-preserved / I3 cascade-respected / I4 replay-equality weak form).
- **#722 PR-T5.C — cross-chain integration + ARCHITECTURE §5.7.2 extension**. `view_from_snapshot(snap, head_id, t)` snapshot-side equivalent of `reconstruct_view_at`. Same iterate-forward + last-match + validity-window + invalidated-edge-skip semantics as the live primitive; `_validity_contains` private helper mirrors the live primitive byte-for-byte on edge selection. Cross-chain consistency contract: `view_from_snapshot(snap, head, t) ∈ snap.edges.values() ∪ {None}`. `ARCHITECTURE.md` §5.7.2 gets a "Graph replay invariant" subsection alongside the trace replay invariant. 11 contract tests.
- **PR-T5.D — release-gating invariants + closure**. `tests/test_t5_release_gating_invariants.py` (5 release-gating tests against in-memory SQLite fixtures with real emit/reconstruct code: `test_graph_replay_at_t_matches_event_log`, `test_replay_audit_only_no_db_scan`, `test_replay_preserves_supersede_chain`, `test_replay_respects_cascade_invalidate`, `test_reasoning_trace_replay_invariant`). CHANGELOG `[0.4.2]` (this entry), `.zenodo.json` v0.4.2, `docs/release_notes_v0.4.2.md`.

### Verification

- `tests/test_t5_event_taxonomy`:           19/19 PASS
- `tests/test_t5_reconstruct_graph_at`:     20/20 PASS
- `tests/test_t5_cross_chain_consistency`:  11/11 PASS
- `tests/test_t5_release_gating_invariants`: 5/5 PASS
- `tests/test_replay_trace` (§5.7.2):       16/16 PASS — no regression on the v0.4.1 reasoning trace invariant.
- **T5 lifecycle suite + replay regression: 71/71 PASS.**

### What v0.4.2 does NOT do

- No mutation-site wiring (T1/T2/T2.D/T6/T7 → `emit_lifecycle_event`). Production `audit_log` keeps emitting only reasoning trace rows; `reconstruct_graph_at(now)` returns the empty snapshot until wiring lands. The wiring is a cross-cutting cycle (lifecycle / graph / audit_log all touched) kept out of v0.4.2.
- No I4 against the live wiki (strong form requires wiring + live-state fixture). The round-trip form (every emit becomes exactly one fold step) is what PR-T5.D pins.
- No T3 Evidence Aging, no T4 Reviewer Authority Hierarchy. Both stay deferred to v0.4.3+.

---

## [0.4.1] — 2026-05-28 — T6 Causality Chain (CASCADE extension) — derived-fact propagation

**Theme**: v0.4.1 closes the CASCADE pillar that v0.4.0 only half-finished. When `cascade_remove_doc_from_sources` empties a base fact's sources, edges whose `derived_from` references that base now auto-invalidate via `invalidate_derived_facts` — the derivation chain stays internally consistent without manual operator intervention. Per-derivation-type semantics (T6.C.b refinement): `transitive` / `inferred` are hard deps (any base empty → invalidate); `operator` is corroborative (only invalidates when no hard deps AND all operator bases empty). Plus the v0.4.0 carry-over `dispatch_contradiction` wiring (T2.D-1/2/2.b/3) lands as flag-gated default-OFF, the QVT α track ships end-to-end (oracle + canonical baseline JSON + PR-gate template), and `tests/test_t6_release_gating_invariants.py` provides 4 release-gating invariants against real wiki fixtures.

**Default-off invariant preserved**. `JAMES_T2D_INGEST_DISPATCH` (T2.D wiring) + `JAMES_T6_LLM_DERIVATION` (T6.B LLM path) both default OFF. T6.D cascade integration is on by default but the wiki gains `derived_from: []` (empty) via T6.A migration so byte-identical retrieval behaviour relative to v0.4.0 holds until operators (or v0.4.2+ LLM path) start populating `derived_from`.

### T6 Causality Chain — 5-PR sequence (#562 ~ #566)

Per `docs/handovers/v0.4.1-t6-causality-chain-entry.md` plan:

- **#562 PR-T6.A — schema + cycle validator + migration**. `core/lifecycle/schema.py` gains `T6_EDGE_FIELD_DERIVED_FROM` + `VALID_DERIVATION_TYPES` (`transitive` / `operator` / `inferred`) + `validate_edge_t6_derived_from(edge, *, edges_by_id)` (Decision 3 LOCK — cycle rejection at write time) + idempotent `apply_t6_edge_defaults`. `scripts/migrate_v041_lifecycle.py` adds `derived_from: []` to every existing relation atomically (`--dry-run` / `--apply` / `--verify` / pre-write snapshot to `wiki.pre-v041-migration/`). 23 contract tests.
- **#563 PR-T6.B — derivation extraction (operator-tagged + flag-gated LLM)**. `core/lifecycle/derivation.py` (~10 KB). `extract_derivation_chain(new_rel, *, context_edges_by_id, llm_provider, enable_llm)` — operator-tagged path validates + cycle-checks; LLM-inferred path (default OFF via `JAMES_T6_LLM_DERIVATION`) delegates to caller-supplied `LLMDerivationProvider` callable. Module never imports an LLM client directly. 14 contract tests.
- **#564 PR-T6.C — `invalidate_derived_facts` cascade**. `core/lifecycle/causality.py` (~10 KB). `should_invalidate_edge` (pure decision) + `invalidate_derived_facts(base_fact_id, entity_root, *, additional_empty_bases, audit_emit)`. Soft-invalidate: `status.active=False` + `mutation_type=invalidated`, `sources` preserved → edge survives for T7 replay. Atomic per-file writes. 19 contract tests.
- **#565 PR-T6.C.b — foundational vs corroborative refinement**. T6.C had collapsed the 1-transitive + 1-operator case (operator gone → invalidate trivially); user clarified intent during review. C.b refines: `transitive` / `inferred` are structural chain links (**hard deps**); `operator` is corroborative (**soft** — strengthens but doesn't single-handedly support when hard deps are alive). Invalidation rules: any hard dep base empty → invalidate (structural break); OR no hard deps AND operator entries exist AND all operator bases empty → invalidate (lone-corroborator collapse). 22 tests (19 original + 3 new C.b).
- **#566 PR-T6.D — cascade integration + 4 release-gating invariants**. `cascade_remove_doc_from_sources` extended (kwargs `audit_emit` + `propagate_t6=True` opt-out). After the primary loop, single call to `invalidate_derived_facts` with all dropped relation ids batched via `additional_empty_bases`. `tests/test_t6_release_gating_invariants.py` (5 tests against tmpdir wiki fixtures + real `cascade_remove_doc_from_sources`): `test_derived_invalidated_when_base_removed`, `test_partial_base_loss_preserves_derived` (T6.C.b refinement), `test_self_reference_rejected_at_write` + `test_two_hop_cycle_rejected_at_write` (Decision 3), `test_cascade_invalidate_emits_audit_row`. 69 existing cascade tests (`test_phase_c_cascade.py` + `test_phase_e_graph_editor.py` + `test_t7_release_gating_invariants.py`) all still pass — no regression.

T6 lifecycle suite total: **83+ contract tests** pass.

### v0.4.0 carry-over — `dispatch_contradiction` ingestion wiring (T2.D, 4 PRs, #558 ~ #561)

v0.4.0 release notes called out the ingestion-path caller for `dispatch_contradiction` as a v0.4.1 deliverable. Shipped in 4 sub-PRs:

- **#558 PR-T2.D-1 — contradiction ingest detector + tests**. `core/lifecycle/contradiction_ingest_detector.py` (~8 KB). `find_contradiction_candidates(new_rel, existing_rels)` returns (existing_rel, pattern) pairs — pattern P1 "different_tail" (CEO-change scenario: same predicate, different target), P2 "divergent_validity" (same target with v0.4 lifecycle metadata). `to_classifier_edge_shape` adapter for the ingestion → classifier shape bridge. 19 contract tests.
- **#559 PR-T2.D-2 — flag-gated dispatch in merge**. `core/lifecycle/ingest_contradiction.py` (~9 KB) + `core/wiki_generator/_merge.py` pre-merge hook. `dispatch_contradictions_for_merge(new_rels, existing_rels, *, ingest_doc_id, ingest_ts, audit_emit)`. B_supersede + ignore in-line; `JAMES_T2D_INGEST_DISPATCH=1` default OFF → production byte-identical until opt-in. 10 contract tests.
- **#561 PR-T2.D-2.b — A_invalidate cascade race fix via pending_cascades**. T2.D-2 logged-only A_invalidate (cascade would race with the in-memory `_merge.py` write-after-read). T2.D-2.b introduces `PendingCascade` dataclass + `apply_pending_cascades(pending, entity_root, *, audit_emit)`; dispatcher captures cascade requests; `_merge.py` calls the apply helper AFTER writing back its entity (no race). Bad-doc-id heuristic: lowest-weight non-manual source. Manual sources never targeted (`cascade_remove` preserves them by design). 15 tests including 3 `ApplyPendingCascadesTests` + 2 `PickCascadeTargetTests`.
- **#560 PR-T2.D-3 — step7 v6 q17 CEO + acceptance integration**. `eval/regression/step7_queries.json` bumped to v6 with q17 *"Anthropic의 CEO는 누구야?"* (category `ceo-change`, `abstention_truth: "absent"` today, dual-purpose `gold_signals` matching both abstention phrases AND the actual answer post-seed). `tests/test_t2d3_dispatch_acceptance.py` (6 tests) — end-to-end CEO-change scenario via synthetic seed edge + dispatch + `walk_supersede_chain` returns ordered chain.

### QVT α track closure (6 PRs, #550 ~ #553 + #555 + #556)

QVT formalised in v0.4.0 (handover memo #537) ships its full **α-track implementation** in v0.4.1:

- **#550 PR-α-1 — design memo**. `docs/design/v0.4-qvt-alpha-non-saturating-oracle.md` (~14 KB). 3-axis non-saturating oracle (Path Coverage / Graded Answer Accuracy / Calibrated Abstention F1) + fixture schema v5 + per-PR Quality Delta Card pattern + 5 exemption labels (`external-contributor` / `joint-collab-prep` / `docs` / `chore` / `ci` / `code`) + 18-cell ablation-matrix shape for v0.4-end.
- **#551 PR-α-2 — step7 fixture v4 → v5**. 16-query fixture extended with `gold_signals` (3 atomic claims per query, deterministic substring + alias matcher) + `abstention_truth` (12 present / 4 absent) + `min_recall: 1.0` on 5 path-annotated queries. `tests/test_step7_v5_schema.py` (11 invariant tests). `expected_path.edges` deferred (current graph schema uses generic `RELATED_TO` only).
- **#552 PR-α-3 — oracle module + capture wrapper**. `eval/qvt/oracle.py` (~14 KB) — `detect_abstention` (Korean + English phrase matcher), `score_path_coverage`, `score_graded_answer`, `score_abstention_f1` (positive class = abstained), `score_three_axis` top-level + `ThreeAxisResult` dataclass. `scripts/qvt_capture_baseline.py` (~13 KB) — operator wrapper spawning its own server with v0.4.0 production env fixed (ENTITY_ANCHOR=1 + bge-m3 + REWRITE=1, routing layers OFF), N=3 paired reruns, atomic median / min / max / noise_band aggregation. 20 oracle contract tests + `eval/qvt/__init__.py` public API.
- **#553 PR-α-4 — PR-gate template + CLAUDE.md rule 2 + ARCHITECTURE.md §5.7.10**. `.github/PULL_REQUEST_TEMPLATE.md` introduces the Quality Delta Card section with the exemption-label one-liner. CLAUDE.md rule 2 extended (bench + delta card with `core/`-touch trigger). `docs/ARCHITECTURE.md` §5.7.10 names the QVT subsystem alongside §5.7.4 (Bench gate): cost vs marginal quality contribution.
- **#555 PR-α-3 baseline capture — `baseline_2a31b20.json`**. Canonical reference (~25 KB) for every future Quality Delta Card comparison. N=3 paired reruns, ~64-minute operator run. Aggregate (raw): `path_coverage` 1.00 / 0.00 noise; `graded_answer` 0.58 / 0.10 noise; `abstention_f1` 0.29 / 0.40 noise. 3 raw bench JSONs under `reports/research-runs/` for audit replay.
- **#556 PR-α-3 oracle phrase calibration**. Baseline capture surfaced two oracle misses (Korean security-block `"자료에 없"` / `"차단"` missing + `blocked=True` flag unused). Fix: add phrases + `blocked=True` short-circuit. Re-scored baseline (same 3 bench JSONs, deterministic). `abstention_f1` lifted **0.29 → 0.67** median (+0.38); noise band tightened 0.40 → 0.29. 2 new oracle tests pin the regression.

QVT α track total: **22+ oracle contract tests** + canonical `baseline_2a31b20.json`.

### v0.4.1 also ships

- **Replayable RAG positioning** (#548). README + ARCHITECTURE adopt "Replayable RAG" as the JAMES category framing. Two contrast lines (vs Agentic RAG / vs Mem0) + `core/lifecycle/contradiction_arbiter.py:classify_contradiction` named as the Mem0 differentiator. Repo rename deferred past mid-June joint piece milestone.
- **F9 cycle full closure** (#549). q15 *"David Soria Parra가 누구야?"* zero-recall 8-cycle diagnostic ended with `path_recall = 1.0` after `JAMES_ENABLE_ENTITY_ANCHOR=1` + `JAMES_EMBEDDING_MODEL=BAAI/bge-m3` + `JAMES_ENABLE_QUERY_REWRITE=1`. Closure result doc + audit-trail bench JSON under `reports/research-runs/`.
- **v0.4.0 post-mint DOI badge** (#554). README DOI shields bumped `10.5281/zenodo.20391100` → `10.5281/zenodo.20411354` (v0.4.0 Zenodo mint).
- **v0.4.1 entry memo** (#557). `docs/handovers/v0.4.1-t6-causality-chain-entry.md` — 4-decision LOCK section (eager trigger / operator-tagged + LLM flag / strict cycle reject / **C.b foundational-vs-corroborative semantics** — Decision 4 clarified during this release vs the original memo text).

### Verification

- **T6 lifecycle suite**: 83+ contract tests pass.
- **T2.D ingest suite**: 50 contract tests.
- **QVT α**: 22+ oracle contract tests + 11 step7 v5 schema tests + canonical `baseline_2a31b20.json`.
- **No regression**: 69 pre-T6 cascade tests still green; CASCADE/EVENT separation invariants from v0.4.0 hold unchanged.

### What v0.4.1 does NOT do

- No production flip of `JAMES_T2D_INGEST_DISPATCH` default to ON (operator opts in until fixtures exercise dispatch broadly).
- No production population of `derived_from` (migration adds `[]`; operator-tagged + v0.4.2+ LLM-inferred path fill them in).
- No T3 (Aging) / T4 (Reviewer) / T5 (Snapshot replay) — those land at v0.4.2 / v0.4.3.
- No v0.4-end QVT ablation matrix capture (18 cells, ~20-hour operator run, deferred to late June+).

---

## [0.4.0] — 2026-05-27 — Layer 4 Lifecycle Semantics (T1 + T7 + T2 first bundle) — CASCADE/EVENT separation provable

**Theme**: v0.4.0 final. Ships the Layer 4 Lifecycle Semantics first bundle (T1 Temporal Validity + T7 Supersede Chain + T2 Contradiction Arbitration) as a release-gated 8-PR sequence per the Sprint 5 entry memo. The CASCADE vs EVENT separation invariant the v0.4 cycle was retargeted around is now **provable end-to-end** via `tests/test_t7_release_gating_invariants.py` (run against the actual `tests/fixtures/lifecycle/` wiki, not mocks). Plus the L.D measurement-substrate sprint (10 cycles, PR #526~#536) that hardened the bench substrate against the LEO Evidence-Scope routing track shipped in alpha.3, and the Quality Verification Track (QVT) handover (#537) that formalises the measurement loop the L.D cycles built.

**Default-off invariant preserved** across every opt-in flag added in this cycle (`JAMES_SCOPE_ROUTING` / `JAMES_AUTO_ROUTER` / `JAMES_ADAPTIVE_BUDGET` / `JAMES_EMBEDDING_MODEL` / `JAMES_ENABLE_CLAUDE_BACKEND`). Production fleets pulling v0.4.0 see byte-identical retrieval behaviour relative to v0.4.0-alpha.3 unless they opt into one of the flags.

### Sprint 5 — Layer 4 first bundle (8 PRs)

Per `docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md` 7-PR plan + the closure docs PR-T7.C:

- **#524 PR-0 — schema validators + clock helper**. `core/lifecycle/schema.py` (~9 KB) + `core/lifecycle/clock.py` (~2 KB) + `core/relations_schema.py` re-export. Field vocabulary: source-level `valid_from` / `valid_until`, edge-level `validity` / `status` / `mutation_type`. Validators raise on malformed shapes; defaults helpers are idempotent. `clock.now()` is the single monkeypatch point for the entire EVENT/TEMPORAL track. 51 contract tests.
- **#525 PR-T1.A — schema migration script**. `scripts/migrate_v04_lifecycle.py`. `--dry-run` default + `--apply` writes back via tempfile + `os.replace` (no half-written frontmatter). Pre-write snapshot to `wiki.pre-v04-migration/`. `--verify` mode confirms full migration. Idempotent at the byte level after the first apply. 18 contract tests.
- **#538 PR-T1.B — expiration cascade + runner**. `core/lifecycle/expiration_cascade.py` (~15.5 KB) + `scripts/run_expiration_cascade.py`. Marks `mutation_type=expired` + `status.active=False` on every edge whose ALL non-malformed sources have reached `valid_until`. Does NOT delete (CASCADE concern, separated by design). Manual immunity via `edge.manual_immune` opt-out. Idempotent + already-inactive guard. 16 contract tests including the 4 entry-memo invariants (`test_source_expires_at_valid_until`, `test_relation_dropped_when_all_active_sources_expire`, `test_valid_until_null_means_indefinite`, `test_temporal_cascade_preserves_manual_immunity`).
- **#539 PR-T7.A — supersede chain ops (T7 EVENT primitive)**. `core/lifecycle/supersede_chain.py` (~13.8 KB) — 3 pure functions: `supersede_edge(old, new_fact, ts)` (DOES NOT call cascade_remove), `walk_supersede_chain(edge, lookup)` (cycle-safe, max-length-capped, dangling-pointer-tolerant), `reconstruct_view_at(head, lookup, t)` (replay primitive, skips `mutation_type=invalidated`). 15 contract tests including 3 entry-memo invariants (`test_supersede_preserves_old_sources`, `test_supersede_chain_walks_to_active`, `test_supersede_chain_acyclic`).
- **#540 PR-T7.B — release-gating invariants suite**. `tests/test_t7_release_gating_invariants.py` (5 tests) + `tests/fixtures/lifecycle/` (curated 3-entity wiki). Three release-gating invariants the entry memo §3 marked as "must hold before v0.4.0 release": `test_supersede_does_not_trigger_cascade` (patches both `core.cascade.cascade_remove_doc_from_sources` + the underlying `_delete.*` entry point — defense-in-depth), `test_cascade_preserves_supersede_chain` (real CASCADE against the fixture; chain links on unrelated edges byte-identical post-CASCADE), `test_historical_replay_via_chain` (end-to-end: CASCADE → supersede_edge → reconstruct_view_at at 3 times → correct chain link returned). **Run against the actual wiki fixture, not mocks** so regressions in the production CASCADE/EVENT separation surface here on every PR thereafter.
- **#541 PR-T2.A — A/B contradiction classifier**. `core/lifecycle/contradiction_arbiter.py` (~10.2 KB). Single deterministic function `classify_contradiction(old_edge, new_fact, *, now) → Literal["A_invalidate", "B_supersede", "ignore"]`. 4-rule decision tree (first match wins): rule 1 B_supersede when world changed, rule 2 A_invalidate when higher-confidence retroactive correction, rule 3 ignore when duplicate inside window with no confidence delta, rule 4 B_supersede default for edge cases (safer than CASCADE). **LLM-free by design** — the Mem0 differentiator (Mem0 routes via LLM-judge; JAMES routes via this deterministic rule tree). 17 contract tests including 12 parametrized branch cases + literal-return-type reachability smoke.
- **#542 PR-T2.B — A-path contradiction routing wire**. `core/lifecycle/contradiction_router.py` (~8.5 KB initial). `route_a_invalidate(bad_doc_id, entity_root, *, audit_emit)` runs the existing `cascade_remove_doc_from_sources` unchanged + emits a `mutation_type=invalidated` audit row. `dispatch_contradiction(old_edge, new_fact, ...)` is the full A/B dispatcher (B-path raised `NotImplementedError` at this PR — wired in PR-T2.C). 13 contract tests.
- **#543 PR-T2.C — B-path supersede wiring + final A/B dispatch**. Extends `contradiction_router.py` (~11.3 KB) with `route_b_supersede(old_edge, new_fact, supersede_ts, *, audit_emit)` calling `supersede_edge` from PR-T7.A. Audit row carries `old_edge_id` + `new_edge_id` + `superseded_by` + `superseded_at` so the T7 replay primitive sees the chain. `dispatch_contradiction` B-branch wired (replaces the PR-T2.B `NotImplementedError`). 19 router tests total (T2.B's 13 + T2.C's 6) including end-to-end `test_supersede_chain_replayable_after_dispatch`.
- **#544 PR-T7.C — Sprint 5 closure docs + v0.4.0 release prep (this PR)**. ROADMAP.md v0.4.0 marked closed with the "Done when" checklist all green. `.zenodo.json` + this CHANGELOG entry + `README.md` Status badge bumped to v0.4.0. Release notes draft at `docs/release_notes_v0.4.0.md`. GitHub release publish + Zenodo auto-mint DOI is operator action (separate from this PR's merge).

Sprint 5 lifecycle total: **123+ tests pass** when run together (PR-0 51 + PR-T1.A 18 + PR-T1.B 16 + PR-T7.A 15 + PR-T7.B 5 + PR-T2.A 17 + PR-T2.B+C 19).

### LEO L.D measurement-substrate (10 cycles, PR #526~#536 + #537 QVT handover)

L.D wrapper end-to-end validation surfaced two latent issues during the operator-execution phase that L.D F1~F7 + Idea 1 + F2 + F6 + F7 collectively isolated to the right layer (each cycle ~30 minutes; "diagnose cost > fix cost" lesson captured in `feedback_intent_classifier_audit_clean` + `feedback_q15_chroma_embedding_root_pinned` memories). Highlights:

- **#526 L.D wrapper end-to-end fix + router latent backend-id bug**. Wrapper plumbing (env-not-propagated, wrong audit DB path, JSON-wrapped audit payload parser) + a D5.A-era latent router bug (`_legacy_backend_id` returned a model tag like "gemma4:e4b" instead of a registry key like "ollama_local"; AUTO_ROUTER=1 fallback paths all crashed). The D5 closure result doc had promised "fall back to legacy → just extra audit rows"; the code instead degraded to "every routing decision raises". First fixed end-to-end by an operator who actually flipped AUTO_ROUTER=1 server-side.
- **#527 F1 — retrieval-mode bench harness**. `bench.py --mode=retrieval` + `JAMES_BENCH_BEARER` JWT env (the `query.internal_rag` policy gate denies the `external` role that api_key-only requests resolve to; F1 elevates to `employee` via JWT). 4 / 5 step7 path-recall queries hit perfect 1.0 in the acceptance run; q15 (David Soria Parra) zero-recall surfaced as the residual.
- **#528 F4 — narrow-scope fixture + L.B threshold floor finding**. step7 v3 schema adds q14/q15/q16 narrow candidates. **Quantitative discovery**: lowest observed scope = 0.40 even with `effective_k=0` + `graph_reach=0`, because ChromaDB's always-return-top_k floods `score_entropy` (~0.999) + `doc_spread` (~1.0). The L.B narrow threshold (0.30) was below this structural floor.
- **#529 F5 — k=0 floor fix**. `core/reasoning/evidence_scope.py:compute_scope` drops `score_entropy` + `doc_spread` from the aggregate when `effective_k == 0`. Distribution shift: F4's 0/9/5 narrow/mid/wide → **2/5/7**. Narrow rule now fires in production audit. Existing tests + 3 new pinning tests; back-compat (additive change, no test regressions).
- **#530 Idea 1 — Path Recall ground truth** (user-proposed). step7 v4 schema adds `expected_path.nodes` on 5 queries. `bench.py` gains `_parse_path_nodes` + `_path_metrics` + per-query `path_metrics` block + aggregate `path_recall_aggregate`. Mean recall 0.80 on the acceptance run (4/5 at 1.0). q15 zero-recall surfaced the entity-extraction stochasticity hypothesis.
- **#531 F2 — IntentClassifier audit + chat-mode passthrough reattribution**. `scripts/research/intent_classifier_audit.py`. **14 / 14 classifier accuracy** (100%) — the L.D F1 closure note had attributed the step7 chat-mode passthrough pattern to the classifier; this audit refuted that. The actual chain: bench api_key → `external` role → policy gate blocks `query.internal_rag` → engine returns `handle_chat` regardless of classifier output. F1's JWT-bearer pattern remains the right fix; the attribution was wrong.
- **#532 F6 — q15 repeat-run audit**. Entered with the LLM-extraction stochasticity hypothesis; refuted it: 5 / 5 identical zero-recall on q15 (paths=12, nodes=13 byte-identical across runs). Top extracted entities all in finance + Korean-AI domain (FOMC / 정명수 / Powell / Warsh / 비트코인 / etc.), none related to David Soria Parra. Pinned the cluster to a downstream layer.
- **#533 F7 — chroma top-k probe**. Direct chroma query for the MCP PDF (David Soria Parra's source document). Smoking gun: rank 1 (score 0.846) when queried with `"MCP Model Context Protocol"`, NOT in top-20 for any person-name variation (KO, EN, bare). **Proper-noun-mediated retrieval is the MiniLM weakness**; the F7 4-variation probe became the BL-9 acceptance gate.
- **#534 BL-9 prep — embedding swap runner + bge-m3 acceptance gate**. `scripts/migrate_embedding.py` re-encodes the legacy MiniLM chroma collection into a new `chroma_db_<short>/` collection via a fresh `SentenceTransformer`. `--dry-run` flag. Refuses no-op migration (target == legacy). Acceptance gate spec: F7 4-variation probe re-run with the new model, post-swap target = MCP PDF in top-10 on `name_only` variation, step7 v4 q15 path_recall ≥ 0.5.
- **#535 F3 prep — bench wrapper `--enable-claude` flag + capture-rate gate**. Module-level toggle `_ENABLE_CLAUDE_LARGE_TIER` propagated from the CLI flag to the per-arm server env (`JAMES_ENABLE_CLAUDE_BACKEND=1`). Operator opt-in only — back-compat with L.D F1/F4/F5 small-tier-only fleet runs. New "F3 large-tier capture rate" summary block (target ≥ 90%).
- **#536 BL-9 acceptance run — partial success, q15 root reattributed to query expansion**. Operator ran the BL-9 prep workflow (migration runner + `.env` toggle). Swap active confirmation: scores differ (concept_side 0.8462 → 0.7576, deterministic encoder). **q15 still fails** — post-swap 5-variation probe shows MCP PDF reaches rank 1 when the query carries a concept anchor (`"MCP 설계자 David Soria Parra"`) but NOT for the bare name. The MCP PDF chunk contains `"David Soria Parra와 Justin Spahr-Summers"` in ~80 chars of ~2 KB; chunk vector is dominated by concept tokens. F7's embedding-root attribution was half-right — bge-m3 swap is keep, but the q15 fix moves to the query expansion layer. F9 spawned (query_rewriter audit) as the next concrete step.
- **#537 QVT handover — Quality Verification Track**. `docs/handovers/v0.4-quality-verification-track.md` (12 §, ~240 lines) formalises the meta-frame the L.D 10-cycle work was building. Diagnosis: cost is rigorously measured (V3' protocol cross-validated through Robin's 26b matrix work) but quality is assumed; routing machines (D1 / D5 / LEO) all flag-OFF dormant. Plan: Sprint 1 non-saturated quality oracle (the α the cycle is missing) → Sprint 3~5 PR-gate ambient → v0.4 end ablation matrix → v0.5 Domain Pilot flag-ON. The Sprint 5 8-PR sequence in this changelog IS the QVT step-3 PR-gate first installment.

### Sprint 5 prep queue (4 PRs, queued during GitHub Actions outage, cleared 2026-05-27)

- **#522 live verify fixes #5 + #6** — `core/reasoning/engine_memory.py` query-language mirror (persona strip lands inside the memory-context block where the synth-stage language-detection sees it) + `core/reasoning/reflect.py` meta-narration detector + stripper (Gemma 4 occasionally produces a `[CRITIQUE: ...]` envelope on the revise pass; the stripper removes it before the answer reaches the user).
- **#523 Sprint 5 entry memo** — `docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md` (~543 lines). The 4-decision LOCK at §12: migration-timing (separate prep PR), `current_time` source (hybrid via `core/lifecycle/clock.py:now()`), `mutation_type` audit field (unconditional emit, absent = `"active"`), expiration cadence (on-demand only for v0.4.0).

### Verification

- **Lifecycle suite** (Sprint 5): 123+ tests, all green.
- **Router + scope suite** (L.D track): 187 tests (router + wiring + evidence-scope) + 77 stage-D1 wiring tests, all green.
- **Bench / harness contracts**: 31 tests (bench mode-flag + path-metrics + wrapper-enable-claude), all green.
- **Live wrapper runs** (operator + measurement substrate): 5 acceptance runs across this cycle's L.D / BL-9 work — all preserved as audit trail under `reports/research-runs/`.

### What v0.4.0 does NOT do

- **No ingestion-path caller** for `dispatch_contradiction` — the Sprint 5 PRs ship the primitive surface + the routing wire; the call site that detects "new fact arrived → look up old edge → invoke dispatch" is the next operator integration (carried into v0.4.1 with the canonical CEO-change STEP 7 bench).
- **No production BL-9 embedding swap default flip** — `JAMES_EMBEDDING_MODEL` stays at the legacy MiniLM tag; the swap is opt-in via `.env` + the operator-run migration runner. The default flip lands in a follow-up PR once the q15 query-expansion fix (F9) gives the swap a path-recall acceptance gate to pass.
- **No T3 / T4 / T5 / T6** — those land at v0.4.1 / v0.4.2 / v0.4.3 per the ROADMAP phase plan.

---

## [0.4.0-alpha.3] — 2026-05-26 — LEO Evidence-Scope routing track (L.0→L.D) + Sprint 4 embedding prep + CI / module hygiene

**Theme**: second alpha tag of the v0.4 cycle. Bundles the full LEO Evidence-Scope Routing track (4 phases, 5 PRs) — a measured input-side routing axis complementing the predicted output-side D5 budget axis — plus Sprint 4 BL-9 embedding-abstraction prep, CI infrastructure stabilisation (conftest pre-import that eliminates a recurring CI flake), and pipeline.py module-size hygiene. Supersedes the never-released v0.4.0-alpha.2 prep (PR #508, see [0.4.0-alpha.2] below for the historical entry). **Default-off invariant preserved** across all opt-in flags (`JAMES_SCOPE_ROUTING` / `JAMES_EMBEDDING_MODEL` / `JAMES_ADAPTIVE_BUDGET` / `JAMES_AUTO_ROUTER`): production fleets pulling alpha.3 see zero behaviour change relative to v0.3.3.

### LEO Evidence-Scope Routing Track (5 PRs, 4 phases — measured input-side axis)

Track originated by Jiwon's Gemma 4 generation-halt diagnostic question; Leo (Younghu, external contributor, GitHub `222315AIS`) proposed measuring data scope (input-side, post-retrieval) instead of predicting token count (output-side, pre-retrieval). Five PRs across the L.0 → L.D phase plan from `docs/handovers/v0.4-leo-evidence-scope-routing-track.md`.

- **#512 L.0 design memo (external — first external PR to the repo)** — `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` + README walk-back trimming the future-binding "and that's how we intend to keep it" phrase. JAMES-side merge resolved + path renamed `docs/James_leo_evidencescoperoutingtrack` → `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` to match the handovers/ convention. CLA workflow (shipped in #340) fired cleanly on this contribution.
- **#513 L.A extractor + flag** — `core/reasoning/evidence_scope.py` (~13 KB). `ScopeBreakdown` frozen dataclass + `compute_scope(docs, graph_context, graph_paths) → ScopeBreakdown` pure function reading `loop_state` retrieval / graph output. 4 components weighted: `effective_k` (0.35) + `graph_reach` (0.25) + `doc_spread` (0.20) + `score_entropy` (0.20). `JAMES_SCOPE_ROUTING` env flag (default OFF). 23 contract tests in `tests/test_evidence_scope.py` pin the API + empty-input safety net + flag parsing + audit payload schema + determinism + frozen-dataclass guard. Module-level weight constants so Direction 2 regression can swap them in one place. Drive-by F401 cleanup: `Optional` unused in evidence_scope.py + `CAP_SUBSTITUTION` / `TaskBudget` unused in `test_planner_d1_wiring.py` (PR #507 leftover) + `test_adaptive_budget::test_module_exports` `__all__` updated to include PR #507's `adaptive_budget_enabled` entry.
- **#514 L.B router signature + policy v1** — `Router.select_backend` + `resolve_backend` + `_route_policy` gain kwarg-only `evidence_scope`. Policy v1 thresholds: `_SCOPE_NARROW_THRESHOLD=0.30` / `_SCOPE_WIDE_THRESHOLD=0.70` (module constants, L.D tuning candidates). Decision rule order: verify-stage (rule 1, grounding-critical) > scope-override (rule 2, narrow → small / wide → large) > budget rules (3, 4, CAP_SUBSTITUTION / CAP_HEAVY) > legacy. mid-band (0.30 < scope < 0.70) falls through to budget — implements LEO open Q #4 "measurement can promote/demote one tier, not two" as a bounded correction rather than wholesale replacement. 23 contract tests in `tests/test_router_evidence_scope.py` (threshold ordering + narrow/wide overrides + fallback chain + mid-band fall-through + scope=None D5.C.1 regression + verify-wins-over-scope priority).
- **#515 CI flake permanent fix — conftest pre-import (root-cause repair surfaced during L.B)** — `tests/conftest.py` warms `sys.modules` for `core.vector_store` + `core.memory` + `core.wiki_generator` + `llm.router` at session start. Root cause: `patch("core.vector_store.VectorStore")` in legacy `_MarkdownStripBase.setUp` triggered a ~5s `sentence_transformers`+`torch` cold-import cascade inside setUp, crossed the per-test 30s pytest-timeout on slow CI runners, killed setUp mid-execution → `tearDown` never ran → `patch("llm.router.RouterWrapper")` started earlier in the same setUp **leaked**, surfacing downstream as `test_native_done_reason::test_router_wrapper_call_gemma_meta_dispatches_to_call_router_meta` failing with `Expected 'call_router_meta' to be called once. Called 0 times.`. Six legacy test fixtures benefit transparently with no test source changes. CI pytest stabilised: 4m34s (intermittent fail) → 3m1s (consistent green).
- **#516 L.C engine wiring + audit payload (ContextVar pattern)** — new `scope_context(...)` context manager + `get_current_scope()` reader in `evidence_scope.py`. `pipeline.py` computes scope after Loop 1 (graph_context + graph_paths populated) and wraps `generate_answer(...)` in `with scope_context(...)` so all five synth-path `trace_synth_call` invocations (rag / web_summary / web_fallback / retry_no_info, plus reflect / verify routed through trace_helpers) see the same scope. `trace_helpers.trace_synth_call` reads `get_current_scope()` (gated on `scope_routing_enabled()`) and passes `evidence_scope=breakdown.scope` to `resolve_backend`. `router.emit_route_event` audit payload extended: with a `ScopeBreakdown` it emits all 5 fields (`evidence_scope` + 4 components); with a bare float, the scalar only; with `None`, omits the scope fragment → flag-OFF audit-row shape preserved bit-for-bit. 12 contract tests in `tests/test_evidence_scope_wiring.py` pin ContextVar set / get / nested / cleanup-on-exception + audit payload shape for ScopeBreakdown vs float vs None vs invalid + flag-OFF byte-identical at three layers. Mode-gate (LEO open Q #3) auto-resolved: `engine._query_impl` dispatches `chat` / `meta` / `wiki_edit` / `self_evolve` / `coding` modes to `handle_*` helpers **before** `run_retrieval_pipeline` runs, so the scope context only ever wraps the retrieval pipeline.
- **#517 L.D operator bench wrapper** — `scripts/bench_lc_scope_arms.py`. Operator-runnable. Runs `scripts/bench.py --suite=step7` twice (flag-OFF baseline + flag-ON arm) against a live JAMES server, queries `audit_log` for `reason:route` rows from the flag-ON window, aggregates per-query elapsed delta + scope distribution (narrow / mid / wide bin counts) + backend selection counts into `reports/research-runs/lc-scope-bench-<timestamp>.json`. Acceptance criteria reported but not enforced (that is the L.D result doc's job). Deferred to operator's live-server execution window — L.D closure consumes the resulting aggregate JSON.

### Sprint 4 prep (1 PR — Sprint 4 swap PR deferred to operator compute window)

- **#509 BL-9 embedding model abstraction** — `JAMES_EMBEDDING_MODEL` env + `_embedding_short_name` slug helper + per-model `models/<short>` cache path + per-model `chroma_db_<short>` directory. Default-off byte-identical: legacy MiniLM tag maps to `models/miniLM` + `chroma_db`. Actual default flip (likely `bge-m3` or `multilingual-e5-large`) + re-embed migration runner is the Sprint 4 swap PR — operator compute window required.

### Documentation (1 PR)

- **#510 ARCHITECTURE §5.7.9 LLM model authority chain** — per-call > env > preference > any installed > none. D5 (per-backend) ↔ model_resolver (per-tag) two-axis disambiguation. `architecture` label PR (CLAUDE.md rule #4 compliance for the model-resolution surface documentation).

### Module-size hygiene (1 PR)

- **#518 pipeline.py post-loop context split** — extract `build_unified_context` (unified_score v3 + graph context assembly) + `apply_post_check_and_sources_header` (post_check + [관련 자료 목록] prepend) from `pipeline.py` to new `core/reasoning/pipeline_context.py`. Pure refactor, byte-identical behaviour. `pipeline.py` 19.0 KB → 16.0 KB, returns 3 KB headroom for Sprint 5 Layer 4 wiring without breaching the 20 KB CLAUDE.md rule #5 cap. `tests/_pipeline_src.py:pipeline_source()` helper updated to include the new split companion (preserves the structural-grep test pattern used by `test_source_files_first.py` and similar).

### Default-off invariant verified (every new opt-in)

| Flag | Default | Verification |
|---|---|---|
| `JAMES_SCOPE_ROUTING` (LEO L.C, new) | OFF | `test_flag_off_ignores_bound_scope` + `test_emit_route_event_no_scope_fragment_when_none` + pipeline.py `scope_context(None)` no-op path |
| `JAMES_EMBEDDING_MODEL` (Sprint 4 prep, new) | unset → MiniLM tag (= legacy `models/miniLM` + `chroma_db`) | retrieval-engine tests pin per-model path resolution; default flip is the Sprint 4 swap PR, not this alpha |
| `JAMES_ADAPTIVE_BUDGET` (D1, pre-existing) | OFF | unchanged |
| `JAMES_AUTO_ROUTER` (D5, pre-existing) | OFF | unchanged |

### Cross-stack collaboration boundary

Robin (V3'.e schema-adopted research runs) and Ali (Track 3 swap_eval) cross-stack comparisons MUST pin all opt-in routing flags OFF for apples-to-apples purity. Documented in memory `feedback_cross_stack_run_flag_off` and in the L.D bench-wrapper docstring. Joint piece (mid-June trigger) inclusion of evidence-scope deferred to L.D closure + at least one Ali Track 3 swap_eval result.

### Verified

- 9 PRs land green on `pytest` for the changed surface + broader regression. CI pytest run-time stable at 3m1s after #515 (was 4m34s with intermittent failures pre-fix).
- New tests added across the bundle: `test_evidence_scope.py` (23), `test_router_evidence_scope.py` (23), `test_evidence_scope_wiring.py` (12). Cumulative new tests for the LEO track: 58.
- No `core/` file exceeds 20 KB after the bundle. `pipeline.py` post-#518 split at 16.0 KB; `router.py` 17.7 KB; `evidence_scope.py` 13 KB; `trace_helpers.py` 10.7 KB. `verify.py` remains at 19.2 KB pending the next verify addition.
- ruff / hooks clean on every PR (including drive-by F401 cleanups bundled with #513).

### Operator action

GitHub release publish (`gh release create v0.4.0-alpha.3 --target main --title "v0.4.0-alpha.3 — LEO Evidence-Scope routing (L.0→L.D) + Sprint 4 prep + CI hygiene" --notes-file <changelog excerpt>`) triggers Zenodo automatic mint. The minted DOI for v0.3.3 (operator-supplied at this publish time) will be added as `isNewVersionOf` in the next deposit; the chain back to v0.3.2 / v0.3.1 (specific DOIs `10.5281/zenodo.20372649` / `10.5281/zenodo.20363998`) stays explicit in `related_identifiers` as `isDerivedFrom`. L.D closure operator path (separate from release publish): run `python scripts/bench_lc_scope_arms.py` against a live JAMES server, paste the aggregate JSON into `reports/promo-assets/v3prime-leo-evidence-scope-result.md`, tick the ROADMAP entry.

### Out of scope for v0.4.0-alpha.3 (Sprint 4 swap + Sprint 5 follow-up)

- **Sprint 4 swap PR** — default flip `JAMES_EMBEDDING_MODEL` → `bge-m3` (or `multilingual-e5-large`) + re-embed migration runner. Requires operator compute window for the full chroma re-embed pass.
- **Sprint 5 Layer 4 main theme** — T1 Lifecycle states + T2 Event-driven transitions + T7 Cross-workspace federation primitives. The architectural shift planned for v0.4.0 final.
- **LEO L.D closure docs** — `reports/promo-assets/v3prime-leo-evidence-scope-result.md` + ROADMAP entry + memory sync. Waits on operator STEP 7 live run (#517 wrapper is the input).
- **Constant consolidation** — `RELEVANCE_GATE` (now in `pipeline_context.py`) + `MAX_DEPTH` (in `graph_engine.py`) + `_RELEVANCE_THRESHOLD` / `_GRAPH_MAX_DEPTH` (in `evidence_scope.py`) are intentionally mirrored with comments; a single-source consolidation PR would touch all three modules atomically.
- `verify.py` module split (19.2 KB, approaching 20 KB cap; extract `_verify_security` / `_verify_fact_check` on next addition).

---

## [0.4.0-alpha.2] — 2026-05-25 — v0.4 alpha bundle (Sprint 2 UI consistency + Sprint 3 plumbing & 5-stage D1 surface) — **PREPPED, NOT RELEASED — superseded by [0.4.0-alpha.3]**

> **Note**: this entry documents the v0.4.0-alpha.2 release prep (PR #508 — `.zenodo.json` + CHANGELOG + README badge) that landed on `main` 2026-05-25. No GitHub release was published before nine additional PRs (LEO L.0→L.D + Sprint 4 prep + CI fix + module hygiene) merged on 2026-05-26. The alpha.2 scope is now part of [0.4.0-alpha.3]'s ancestry; the historical entry below is preserved so the alpha.2 prep work (Sprint 2 + Sprint 3) is still attributable to the right window.

**Theme**: first alpha tag of the v0.4 cycle — the deliverable between v0.3.x closure (v0.3.3, D6 retry wiring) and the v0.4.0 final Layer 4 main theme (Lifecycle Semantics, Sprint 5). Two sprints of stabilisation work bundled into one citable archive. **Default-off invariant preserved** across all D1 / D5 flags: production fleets pulling alpha.2 see zero behaviour change relative to v0.3.3.

### Sprint 2 — UI consistency bundle (5 PRs)

- **#496 admin character profile page i18n consistency** — 38 new `char.*` keys + `window.onLangChange` dynamic re-render hook + `data-i18n="char.card.{core,values,style}"` on the summary card frame. Closes the long-standing bug where `buildCharacterSummary` / `renderConnectionsPanel` rendered Korean strings in EN mode (root cause was one layer below the existing `label_key` contract). `tests/test_i18n_char_keys_parity.py` (3 tests) pins EN↔KO `char.*` key parity + no orphan `t('char.…')` calls.
- **#497 chat sidebar hover auto-expand** — CSS-only sibling + self `:hover` rule on `.sidebar-open-btn` / `.sidebar.collapsed`. Click-toggle UX preserved untouched.
- **#498 always-visible chat model indicator chip** — new `GET /llm/active` endpoint (api_key only, not admin-gated) returns `{tag, source, warning}` from `resolve_chat()`. Chip in `index.html` header populated via `loadActiveModelChip()`; `data-source` attribute drives edge colour for non-default resolution (`preference` / `any` / `none`).
- **#499 chat-side model picker popover** — chip click opens popover listing installed models (aggregated from `MODE_OPTIONS`). Selection writes to `selectedModel` (per-session override) + `localStorage`. Resolution priority unchanged: per-call (`selected_model` param) > env (`config.GEMMA_MODEL`) > preference list > any > none.
- **#500 sticky top navigation on scrolling pages** — admin / workspace headers get `position:sticky; top:0; z-index:50`; chat / graph keep their `overflow:hidden` viewport pattern. `tests/test_header_sticky_parity.py` (4 tests) pins the per-page policy with negative assertions so a future refactor that "fixes the inconsistency" by adding sticky to chat / graph fails CI.

### Sprint 3 — Plumbing closure (5 PRs + 2 follow-ups)

- **#501 BL-1 emit_trace_step stdout mirror** — single-line `[reason:<stage>] applied_rule · backend · latency [trace abc12345] [err=…]` mirror lives inside `emit_trace_step` itself, so every caller (synth + planner + reflect + verify + retrieve + rerank + tool) gets the same console signal. Convention matches `observability.emit_step`: `JAMES_TRACE_STDOUT` default ON; `"0"` / `"false"` / `"no"` / empty silences. Closes `feedback_stdout_vs_audit_log_trace_split`.
- **#502 BL-2 attributes.summary legacy field cleanup** — `_ingestion.py` stops mirroring `description` into `attributes.summary`; `_frontmatter.py` defensively strips any caller-passed `attributes.summary` before frontmatter dump. Read fallback kept for legacy disk files. New wiki writes converge on the canonical top-level `summary`.
- **#503 D1 stage expansion #7a planner** — `Planner.__init__` accepts `max_tokens: Optional[int]` + `budget: Optional[TaskBudget]`. Per-call cap resolution: explicit int / `adaptive_budget_enabled() + TaskBudget.assess("planner", query)` / fall-back default. `backend.complete` → `complete_with_retry(stage="planner")`.
- **#504 D1 stage expansion #7b reflect** — `ReflectionLoop` critique + revise sub-stages share `TaskBudget.assess("reflect", query)` when both `*_max_tokens` are `None` and D1 is on. `complete_with_retry(stage="reflect")` wired through `_call`.
- **#505 D1 stage expansion #7c verify** — `Verifier.__init__` accepts `fact_check_max_tokens: Optional[int]` + `budget`. `_fact_check` routes through `assess("verify", query)` when D1 is on. D5 grounding-critical escalation (D5.C.1 rule 1) composes with D1 cap signal — both fire independently into the router policy + retry helper.
- **#506 follow-up** — `test_verifier.py::ANSWER_KO` fixture rebalanced under PR #495 (Sprint 1 #2) dominant-script `is_korean` contract. The fixture had ~24 Hangul + ~34 English alpha chars — English-dominant under the new rule, so the verifier's `_format` took the EN branch and the `"검증:"` assertion broke. Rebalanced to ~50 Hangul + 3 ASCII (`RAG`).
- **#507 follow-up** — `query_rewriter` local `_adaptive_budget_enabled()` migrated to `core.reasoning.budget.adaptive_budget_enabled` so all 5 reasoning stages read the D1 opt-in flag through one function.

### After v0.4.0-alpha.2 — 5-stage D1 surface uniform

| Stage | D1 cap | D6 retry | Router signal |
|---|---|---|---|
| `query_rewriter` | ✅ (v0.3.1 / PR #461) | ✅ (v0.3.3 / PR #486) | budget signal under D1 on |
| `synth` | ✅ (v0.3.1) | ✅ (v0.3.3, via `trace_synth_call`) | budget signal under D1 on |
| `planner` | ✅ (v0.4.0-alpha.2 / PR #503) | ✅ (v0.4.0-alpha.2) | budget signal under D1 on |
| `reflect` | ✅ (v0.4.0-alpha.2 / PR #504) | ✅ (v0.4.0-alpha.2) | budget signal under D1 on |
| `verify` | ✅ (v0.4.0-alpha.2 / PR #505) | ✅ (v0.4.0-alpha.2) | budget signal + grounding-critical |

### Default-off invariant verified

Every wiring landed in v0.4.0-alpha.2 stays gated behind `JAMES_ADAPTIVE_BUDGET=1`. Without the env opt-in, every reasoning stage hits the pre-#7a cap (4096 / 1024) byte-identically. The router signal in budget-aware mode is also a no-op under flag-off — `_budget_for_router` is `None`, so policy rules 1 / 4 don't fire on a fake CAP_HEAVY value.

### Verified

- 12 PRs land green on `pytest` for the changed surface + broader regression (planner / reflect / verify / query_rewriter / router / budget / trace / chip wiring / sticky parity / i18n parity).
- New tests added across the bundle: `test_i18n_char_keys_parity.py` (3), `test_llm_active_endpoint.py` (8, including ChipPickerPopoverTests), `test_header_sticky_parity.py` (4), `test_emit_trace_step_stdout_mirror.py` (6), `test_attributes_summary_cleanup.py` (3), `test_planner_d1_wiring.py` (8), `test_reflect_d1_wiring.py` (6), `test_verify_d1_wiring.py` (6).
- No `core/` file exceeds 20 KB after the bundle. `verify.py` approached the cap at 21.4 KB during #7c development; trimmed docstrings landed it at 19.2 KB — split is the next-action for any further verify additions (extract `_verify_security` / `_verify_fact_check`).
- ruff / hooks clean on every PR.

### Operator action

GitHub release publish triggers Zenodo automatic mint. The minted DOI for v0.3.3 will be supplied by the operator at v0.4.0-alpha.2 publish time and added as `isNewVersionOf` in the next deposit; the chain back to v0.3.2 / v0.3.1 (specific DOIs `10.5281/zenodo.20372649` / `10.5281/zenodo.20363998`) stays explicit in `related_identifiers` as `isDerivedFrom`.

### Out of scope for v0.4.0-alpha.2 (Sprint 4-5 follow-up)

- **Sprint 4 retrieval quality** — BL-9 embedding model swap (`paraphrase-multilingual-MiniLM-L12-v2` → `bge-m3` / `multilingual-e5-large`). Re-embeds all chroma chunks. Cross-lingual diagnostic fixture (`feedback_rag_cross_lingual_diagnostic` memory) is the test bed.
- **Sprint 5 Layer 4 main theme** — T1 Lifecycle states + T2 Event-driven transitions + T7 Cross-workspace federation primitives. The architectural shift planned for v0.4.0 final.
- `verify.py` module split (19.2 KB, approaching 20 KB cap; extract `_verify_security` / `_verify_fact_check` on next addition).
- `docs/ARCHITECTURE.md` LLM-model authority chain documentation polish (Sprint 2 #3c).
- admin sidebar collapsed-state parity (Sprint 2 #5b) — bundled with sticky-nav follow-up when needed.

---

## [0.3.3] — 2026-05-25 — D6 retry-wiring follow-up cycle closure (D1 design/wiring gap closed)

**Theme**: close the design ↔ wiring gap surfaced by the 2026-05-25 user diagnostic question (*"does D1 7-tier cover all cases / what about exceptions?"*). The `retry_doubled` helper that existed since v0.3.1 (D1 closure) but was never invoked from any production call site is now wired through `complete_with_retry`. Truncation triggers single retry up to `CAP_HEAVY`. `audit_log reason:retry` row records every retry decision. Native Ollama `done_reason` replaces the heuristic when the provider exposes it (heuristic preserved as fallback for cache hits / Ollama < 0.1.30 / non-Ollama providers).

Three-PR sequence (#486 + #487 + #488) plus two operator-trail PRs (#489 launch-tracker rows + #490 README DOI badge bump to v0.3.2).

### Added — `complete_with_retry` helper (PR #486)

- `core/reasoning/budget.py:complete_with_retry(backend, prompt, *, cap, max_cap=CAP_HEAVY, timeout, stage="", **opts)` — single retry on `done_reason="length"`, bounded by `max_cap`. `opts` forwarded both calls. Added to `__all__`.
- `core/reasoning/backends/__init__.py` — `CompletionResult.done_reason: str = ""` field. Backward compat: backends without the attribute are tolerated (helper falls back to no-retry).
- `core/reasoning/backends/ollama_local.py` — length-+-terminator heuristic. Two signals must fire to mark `"length"`: response length ≥ 90% × `max_tokens` × 4 chars AND no sentence terminator (`.`, `?`, `!`, `다`, `요`, `음`, `}`, `]`, `"`, `'`, `)`). Conservative — biased to false negatives.
- `core/retrieval/query_rewriter.py` — `backend.complete(...)` → `complete_with_retry(...)` at the only call site where retry can actually fire (D1 wired stage with dynamic cap signal under `JAMES_ADAPTIVE_BUDGET=1`).
- 14 contract tests in `tests/test_complete_with_retry.py` covering retry trigger / no-retry conditions / cap saturation / custom max_cap / backend-without-`done_reason` / opts forwarding / ollama heuristic edge cases.

### Added — `audit_log reason:retry` emission (PR #487)

- `complete_with_retry` drops one `reason:retry` row to `audit_log` every time a retry actually fires.
- Schema: `endpoint="reason:retry"`, `target=stage` (or `backend_id` when stage empty), answer column auto-serialized JSON `{"cap_before": <int>, "cap_after": <int>, "backend": "<id>", "prompt_hash": "<8 hex>"}`.
- Operator monitoring channel: `SELECT endpoint='reason:retry' FROM audit_log` shows retry rate / stage distribution / backend distribution for new fail-case discovery + heuristic false-positive rate tracking.
- Audit emission is try/except-wrapped — never blocks production.
- 5 new tests pinning the emit / no-emit conditions + reason label correctness + audit-failure-survives-retry.

### Added — native Ollama `done_reason` exposure (PR #488, 4-layer additive)

- `core/gemma_client.py` — `GemmaClient._last_done_reason` instance attribute populated from `resp.json().get("done_reason", "")`. Reset at the top of `call_gemma` so a cache hit / early-return path doesn't leak the prior call's signal.
- `llm/base.py` — `BaseLLM.generate_meta(messages, **kwargs) → dict` default implementation wraps `generate(...)` into `{"text": str, "done_reason": ""}`. Providers that don't override get graceful fallback.
- `llm/providers/ollama_client.py` — OllamaClient holds a single GemmaClient instance (`_gemma_client` lazy-initialized via `_client()`). `generate_meta` returns `{"text": ..., "done_reason": client._last_done_reason}`.
- `llm/router.py` — `call_router_meta(prompt, task_type=None, **kwargs) → dict` mirrors `call_router`. `RouterWrapper.call_gemma_meta` is a thin shim. Hard fallback path reads `GemmaClient._last_done_reason` after the direct `call_gemma` call.
- `core/reasoning/backends/ollama_local.py` — `complete()` tries `router.call_gemma_meta` first (callable + dict-return check); on absent / non-dict / exception, falls through to legacy `call_gemma` + heuristic.
- 12 new tests in `tests/test_native_done_reason.py` covering BaseLLM default + OllamaClient stash read + RouterWrapper shim + `call_router_meta` + ollama_local preference order + heuristic fallback + GemmaClient reset.

### Added — operator trail (PRs #489 + #490)

- `reports/promo-assets/launch-tracker.md` — 3 new audit-trail rows (D5 cycle CLOSED catalog + v0.3.2 GitHub release published + D6 retry-wiring follow-up cycle).
- `README.md` / `README.ko.md` — Status badge v0.3.1 → v0.3.2 + DOI badge `10.5281/zenodo.20363998` → `10.5281/zenodo.20372649`.

### D1 safety net status — all backed

| # | Net | Pre-D6 | Post-D6 |
|---|---|---|---|
| 1 | `retry_doubled` fallback | Definition-only, no wiring | **Wired via `complete_with_retry` (query_rewriter) + audit `reason:retry` + native Ollama `done_reason` precision** |
| 2 | Falsification cycle | Measurement-driven heuristic evolution | + `audit_log reason:retry` row pile-up is now the monitoring channel for new fail-case discovery |
| 3 | flag-off default | Pre-D6 byte-identical | Pre-D6 byte-identical (`JAMES_AUTO_ROUTER` / `JAMES_ADAPTIVE_BUDGET` both default OFF) |
| 4 | Heuristic asymmetry | Half-effective (escalate but no retry) | Fully backed — escalate path retries on truncation, native signal where available |

### Verified

- Final state: **587 backend/router/budget/rewriter/graph/reflect/verify/alias/retry/gemma/done regression tests pass**.
- 31 new D6 contract tests across 2 files (`test_complete_with_retry.py` 19 + `test_native_done_reason.py` 12).
- ruff clean on all touched files.
- Module sizes all under the 20 KB gate.

### Out of scope for v0.3.3

- **Native `done_reason` for other providers** (Claude / DeepSeek) — 3-condition gated (operator opts into `JAMES_ENABLE_CLAUDE_BACKEND=1` + `JAMES_AUTO_ROUTER=1` + observed `reason:retry` rows with that backend > 0). Memory: `feedback_d1_d5_retry_doubled_wiring_gap.md`.
- **planner / reflect / verify wiring through `complete_with_retry`** — these stages currently use a fixed `self._max_tokens = 4096` which is already at the `CAP_HEAVY` ceiling, so retry would be no-op. Wiring lands together with the D1 budget signal expansion (v0.4 follow-up).
- **D2 task-weight metric in measured form** — absorbed into D5 as the policy's heuristic classifier; revisit as a measured metric if the heuristic plateaus on production bench.
- **Cost-based scoring v2** / **per-pack policy** / **per-stage explicit override under D5 ON** / **embedding swap (BL-9 bge-m3 / multilingual-e5-large)** — v0.4 follow-ups.
- **D3 / D6(I)** — cross-family generalization + joint paper consolidation remain queued for the mid-June Robin / Ali Gemini collaboration window.

### Acknowledgements

- The 2026-05-25 user diagnostic question (*"7단계 사다리로 나누는 것이 전부 커버가 되나? 예외가 발생할 가능성이 제로는 아닐 것 같은데"*) directly motivated this cycle. The honest engineering response — admit the gap, ship the wiring, add the monitoring channel, swap the heuristic for native signal when available — followed in three small PRs over the same session.
- D1 (`core/reasoning/budget.py`, v0.3.1) defined the `retry_doubled` helper that v0.3.3 finally activates. The 7-tier natural-stop gradient remains the measurement baseline.
- D5 (Auto-routing, v0.3.2) shares the `audit_log` infrastructure: `reason:route` (D5.C.2.a, PR #478) + `reason:retry` (this cycle, PR #487) together give operators a complete picture of every routing decision plus every truncation retry.

---

## [0.3.2] — 2026-05-25 — Direction 5 (Auto-routing on Provider Contract) cycle closure

**Theme**: ship a per-call backend-selection layer above the Provider Contract. Every production LLM call path now consults a router that picks backend by task weight + stage type. Default OFF; opt-in via `JAMES_AUTO_ROUTER=1`. Byte-identical to pre-v0.3.2 at the production call path when the flag is unset. 10-PR sequence (#474–#484) merged in a single 2026-05-25 session.

### Added — `core/reasoning/router.py` (Router + policy + helpers)

- New `core/reasoning/router.py` (~12 KB) providing:
  - `Router(*, enabled=None)` — env-flag-gated (`JAMES_AUTO_ROUTER`). Default OFF.
  - `Router.select_backend(stage, prompt, *, context, budget_signal) → str` — dispatches to `_route_policy` when flag-on, returns `_legacy_backend_id()` when flag-off.
  - `_route_policy` — 4-rule decision tree: (1) `stage == "verify"` (grounding-critical) → prefer `large` → `medium` → legacy; (2) `budget_signal == CAP_SUBSTITUTION` → prefer `small` → legacy; (3) `budget_signal == CAP_HEAVY` → prefer `large` → `medium` → legacy; (4) otherwise (CAP_LIGHT / None / unknown) → legacy.
  - High-level stage-call-site helpers: `resolve_backend`, `emit_route_event`, `_budget_to_tier_label`. `resolve_backend` returns `fallback_backend_id` when flag-off (byte-identical); under flag-on, the router is the authority — stage-level `self._backend_id` is intentionally overridden.

### Added — `BackendCapability(tier, provider)` metadata

- `core/reasoning/backends/__init__.py` extended with `BackendCapability` frozen dataclass, `UNKNOWN_CAPABILITY` sentinel, `get_backend_capability(name)`, and `list_backends_by_tier(tier)`.
- `tier` ∈ `{small, medium, large}` (model-size class); `provider` ∈ `{local, sovereign, cloud}` (deployment surface). Free-form strings — plugin backends can declare niche tiers without modifying core.
- Two builtin backends declared: `ollama_local` = `BackendCapability(tier="small", provider="local")`; `claude_code_cli` = `BackendCapability(tier="large", provider="cloud")`.
- Backward compat: backends without `capability` → `UNKNOWN_CAPABILITY`, treated as fallback only (not preferred by policy).

### Added — 5-stage wiring (every production LLM call path)

- `core/retrieval/query_rewriter.py` (D5.C.2.a) — first stage wired. cap computed first → fed to router as `budget_signal` only when D1 `JAMES_ADAPTIVE_BUDGET=1` is also on. Audit row every successful resolve.
- `core/reasoning/planner.py` (D5.C.2.b) — same pattern, `budget_signal=None` (planner not D1-wired).
- `core/reasoning/reflect.py` (D5.C.2.c) — single backend resolve serves both critique + revise passes.
- `core/reasoning/verify.py` (D5.C.2.d) — grounding-critical stage, `reason="grounding-critical"` audit label. The stage where a small-tier-only fleet sees routing actually take effect when operator opts into a larger backend.
- `core/reasoning/trace_helpers.py:trace_synth_call` (D5.C.2.e) — L1 unified entry point. `resolve_backend_for_stage(stage)` result becomes `fallback_backend_id` for `resolve_backend(...)`. Closes the 5-stage surface.

### Added — `audit_log` `reason:route` rows

- Per successful resolve, one row recording `(stage, prompt_hash[:8], selected_backend, budget_tier_label, reason)`. `reason` values: `auto` (D1+D5 both on), `fallback` (D5 on, D1 off), `grounding-critical` (verify stage escalation), `policy` (helper default).
- Audit emission is try/except-wrapped — failure never blocks production.

### Added — `core/entity_alias_pack.py` (cross-lingual entity resolution, D5.D)

- New `core/entity_alias_pack.py` (~3.6 KB) — `_ENTITY_ALIAS_PACK` list of ~30 high-traffic entities with bidirectional KO↔EN surface forms (Palantir, Tesla, Nvidia, Apple, Microsoft, Google, Meta, Amazon, Anthropic, OpenAI, AMD, BYD, BlackRock, Citi, Archer, Bouygues, Cursor, Claude, FOMC, Federal Reserve, White House, Pentagon, …).
- `core/graph_engine.py:build_entity_map_snapshot` augmented — after the wiki-frontmatter pass, iterate the alias pack and augment the snapshot with KO↔EN surface forms (silent skip when the canonical name has no matching wiki entity).
- Pairs with the v0.3.1 follow-up PR #472 `_SYNONYM_MAP` keyword expansion: two layers, same KO↔EN problem, different pipeline stages (query expansion vs graph entity resolution).
- Backward compat: wiki frontmatter `aliases:` takes precedence (first-write); removing the pack reverts to v0.3.1 alias-from-frontmatter-only behavior.

### Added — closure documentation

- `docs/handovers/v0.3.x-direction5-auto-routing-track.md` (PR #474, 213 lines) — design memo with scope / phase plan / STEP 7 bench plan / Build-don't-broadcast principle application.
- `docs/ARCHITECTURE.md` §5.7.8 (PR #484) — D5 routing layer + activation flag + decision tree + authority model + audit row schema + cross-lingual entity resolution.
- `reports/promo-assets/v3prime-direction5-router-result.md` (PR #484) — closure result doc: 10-PR catalog + acceptance (bench-neutral by design) + operator-run STEP 7 procedure for 3 scenarios + "what this closure does NOT claim" + cross-Direction map.
- `ROADMAP.md` Direction 5 `[ ]` → `[x]` with 10-PR sequence.

### Verified

- All wiring PRs land on test-level invariance (flag-off byte-identical). 526 backend / router / graph / entity / rewriter / reflect / verify regression tests pass on the full D5 surface.
- 74 new D5-specific contract tests across 5 files (`test_router_skeleton.py` 23 + `test_backend_capability.py` 14 + `test_router_policy.py` 14 + `test_query_rewriter_router_wiring.py` 11 + `test_entity_alias_pack.py` 12).
- Module sizes all under the 20 KB gate: `router.py` ~12 KB, `entity_alias_pack.py` ~3.6 KB, `graph_engine.py` +29 lines.
- ruff clean on all touched files.

### Operator-run STEP 7 sweep (any time)

The result doc documents a 3-scenario procedure: (1) baseline with flag OFF; (2) treatment with flag ON, only `ollama_local` registered — expected match baseline (all routing falls back to legacy with `reason:route` audit row pile-up); (3) treatment with flag ON + `JAMES_ENABLE_CLAUDE_BACKEND=1` — verify stage routes to Claude on every call, expected latency ↑ + grounded=true rate ↑. Acceptance: no grounded=true rate regression at any tier in scenario (2).

The cross-lingual diagnostic ("팔란티어가 뭐야?" → wiki entity `palantir_technologies__pltr_` matching) was the 2026-05-25 root cause this release closes at the graph layer.

### Out of scope for v0.3.2

- **Cost-based routing scoring v2** — current 4-rule heuristic stays. Token price × latency × quality weighted score is a v0.4 follow-up.
- **Per-domain-pack policy** — v0.5 Domain Pilot scope.
- **Per-stage explicit override under D5 ON** — when the router flag is on, stage-level `self._backend_id` is intentionally overridden; a flag-aware per-stage override mechanism is a v0.4 follow-up.
- **Embedding model swap** (BL-9) — bge-m3 / multilingual-e5-large for global retrieval quality is v0.4 retrieval-rework cycle backlog.
- **Direction 2 (task-weight metric) as a paper** — absorbed into Direction 5 as the policy's heuristic classifier (Build-don't-broadcast principle).
- **D3 / D6(I)** — cross-family generalization + joint paper consolidation remain queued for mid-June Robin / Ali Gemini collaboration window.

### Acknowledgements

- Direction 1 (`core/reasoning/budget.py`, v0.3.1) provided the `budget_signal` input the router consumes — this release stands on the 7-tier natural-stop gradient ground truth.
- The Build-don't-broadcast principle (memory: `feedback_build_dont_broadcast`) was applied throughout: D5 is a product cycle, not a research cycle. No public broadcast, no Robin coupling. Single Ali design-preview DM at D5.0 merge.

---

## [0.3.1] — 2026-05-24 — Direction 1 (Adaptive Budgeting) cycle closure

**Theme**: ship the dynamic-token-budget mechanism as a **data-bearing experiment artifact**, not a runtime change. Default OFF; opt-in via `JAMES_ADAPTIVE_BUDGET=1`. Three publishable findings + one process finding on `gemma4:e4b` at T=0.2, validated by two A/B sweeps × N=20/cell × 7 task-weight tiers.

### Added — `core/reasoning/budget.py` (TaskBudget module)

- New `core/reasoning/budget.py` (~7.2 KB) providing `TaskBudget.assess(stage, prompt) → int` with a 3-tier heuristic: `CAP_SUBSTITUTION = 200`, `CAP_LIGHT = 1200` (v2; bumped from 800 on 2026-05-24 after the cognitive-stages sweep showed reflect/verify natural-stop ~926/~984), `CAP_HEAVY = 4096`. Fallback: `retry_doubled(prev_cap)` for `done_reason=length` retry, bounded by `CAP_HEAVY`.
- 40 unit tests in `tests/test_adaptive_budget.py` pin every tier value, every regex branch, and the retry helper contract.

### Added — `core/retrieval/query_rewriter.py` adaptive-budget wiring (default OFF)

- `QueryRewriter.__init__` accepts an optional `budget: TaskBudget` arg and `max_tokens=None` default. Cap resolution is three-way: (1) explicit `max_tokens=int` → fixed cap (experiment baseline), (2) `None` + `JAMES_ADAPTIVE_BUDGET=1` → dynamic via `TaskBudget.assess()`, (3) `None` + flag off → `DEFAULT_MAX_TOKENS=4096` (byte-identical legacy).
- `JAMES_ADAPTIVE_BUDGET` env flag, **default OFF**. 5 default-off invariant tests in `tests/test_query_rewriter.py` prove byte-identical pre-v0.3.1 behaviour for any operator who has not opted in.
- Stdout trace `[budget] query_rewriter cap=N reason=...` when both `JAMES_ADAPTIVE_BUDGET=1` and `JAMES_TRACE_STDOUT=1` (default ON via `core/observability.py` convention).

### Added — research drivers + result docs (experiment-grade artifacts)

- `scripts/research/v3prime_direction1_adaptive_budget.py` — 3-prompt A/B driver (substitution/light/heavy), 120 calls/N=20, same fixture as V3'.e (PR #440 / PR #453). V3' Protocol v1 schema with two additive fields (`adaptive_cap_requested`, `adaptive_decision_reason`).
- `scripts/research/v3prime_direction1_cognitive_stages.py` — 4-stage cognitive A/B driver (query_rewriter / planner / reflect / verify) using production prompt templates imported from the live modules. 160 calls/N=20.
- `reports/promo-assets/v3prime-direction1-adaptive-budget-result.md` — 3-prompt sweep result.
- `reports/promo-assets/v3prime-direction1-cognitive-stages-result.md` (NEW) — full v1 vs v2 comparison + per-cell detail + 2 sub-findings (verify clustering + 7-tier gradient) + Direction 1 final closure.
- `reports/research-runs/v3prime-direction1-adaptive-budget-20260524T050347.json` — 3-prompt raw data (120 calls, 0 failures).
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T054634.json` — cognitive v1 sweep (CAP_LIGHT=800; falsification data — exposed reflect/verify truncation).
- `reports/research-runs/v3prime-direction1-cognitive-stages-20260524T061858.json` — cognitive v2 sweep (CAP_LIGHT=1200; PASS data — 0/20 truncation on every cell, quality 20/20 restored).

### Findings — three publishable + one process

1. **Cap is a ceiling, not the floor**. `gemma4:e4b` naturally stops well below 4096 on every measured tier; cap reduction → 0% token change, but +7-17% latency win on substitution/light tiers (Ollama KV-cache buffer sizing) + ~20× per-call memory allocation reduction on substitution + bounded emergency-exit guard. PR #399's lifted cap was *permission to finish*, not waste.
2. **7-tier monotonic natural-stop gradient** spanning 62 → 1681 tokens on `gemma4:e4b` at T=0.2. 27× dynamic range, cross-sweep noise within 5% per tier. The quantitative form of the joint-paper sub-clause *"the workload gradient is multi-tier monotonic on a single model"*.
3. **`verify` is a high-clustering cognitive stage** (~12.5% unique baseline responses across 40 calls, stable across two independent sweeps). Direction 4 Mechanism 2 (answer convergence) now has **two axes**: workload weight + task type.
4. **Process finding** — heuristic v2 (CAP_LIGHT 800 → 1200) was data-driven by a falsification → revision → confirmation cycle.

### Joint paper sub-clauses now drafted

3-author headline holds verbatim: *"Substitution is free. Synthesis costs in proportion to what it has to invent."* Direction 1 closure adds three sub-clauses:

- *"…and inversely to parameter count."* (Robin axis-3 — 2 evidence layers)
- *"…and the gradient is multi-tier monotonic — 7 measured tiers spanning 27× dynamic range."* (JAMES Direction 1)
- *"…and answer convergence has a task-type axis: structured-JSON outputs cluster independent of workload."* (JAMES Direction 1, cross-sweep validated)

### Verified

- 71 unit tests pass (40 budget + 31 query_rewriter); ruff clean; `core/reasoning/budget.py` 7.2 KB / `core/retrieval/query_rewriter.py` 12 KB (CLAUDE.md rule #5 < 20 KB).
- Default-OFF invariant proven by 5 dedicated tests.
- Operator real-traffic signal: STEP 7 bench at intermediate commit `eccfc4d` passed within band [158.7, 413.7] @ 172.7 s — additional real-traffic robustness evidence beyond unit tests.

### PR references

- PR #461 — D1.A module + D1.B wiring (default OFF) + 3-prompt driver + cognitive-stages extension driver + first result doc.
- PR #463 — Heuristic v2 (CAP_LIGHT 800 → 1200) + v2 sweep PASS + closure result docs + 7-tier gradient documentation.

### Out of scope

- Flipping `JAMES_ADAPTIVE_BUDGET` default to ON — token-reduction hypothesis target unmet on `gemma4:e4b`; stays OFF.
- Production wiring of the 4 cognitive stages (planner / reflect / verify / synth) — cap-invariance removes urgency.
- Direction 2 (task-weight metric formalization), Direction 3 (cross-family generalization), Direction 5 (auto-routing) — separate cycles.

---

## [Unreleased] — v0.3.x patches

### Added

- **Working memory turn-end cleanup wired into `engine.query()`
  (Cognitive Phase 3 PR-10b)** — the public `query()` is now a
  thin try/finally wrapper that delegates to a new `_query_impl`;
  the finally block clears the turn's working-memory scratch and
  releases the session ContextVar on every return path, including
  exception unwinds and the early `_blocked_result` returns from
  `pre_check`. Before this PR, a crashed turn or a pre_check
  rejection could leave the session ContextVar bound at the thread
  level — the next request reusing that thread would have
  inherited a stale `(session_id, turn_id)` until
  `set_session_context` ran again. Working memory had no production
  call sites yet (PR-10a infra-only), but the same cleanup invariant
  now holds end-to-end before the wiring sites are added in a
  future PR. 3 new integration tests in `tests/test_working_memory.py`
  lock the contract (normal return, exception, early blocked
  return). `tests/test_chat_mode_picker.py::test_engine_query_validates_override`
  updated to scan both `query()` and `_query_impl` for the override
  whitelist since the validation logic now lives in `_query_impl`.

- **Working memory infrastructure (Cognitive Phase 3 PR-10a)** —
  `core/memory/working.py` ships a turn-scoped scratch store sibling
  to the episodic memory landed in PR-9. Where episodic captures the
  **final** plan/reflect/verify decisions across turns, working memory
  holds **intra-turn** intermediate state (reflection critique drafts,
  per-claim verifier intermediates, planner subtask scratch) that
  reasoning stages hand off to each other while the answer is being
  built and that the audit_log already keeps a forensic copy of.
  In-process dict with `threading.Lock` (no SQLite) keeps the
  "cleared at turn end" invariant safe against operator restart
  races. ContextVar reuse: the PR-9b `(session_id, turn_id)` binding
  is the only one needed — `working_event()` reads it directly so
  PR-10b call sites stay one-liners.
  15 new tests in `tests/test_working_memory.py` lock the contract
  (round-trip, turn isolation, session isolation, keys(), clear_turn,
  prune_idle_turns, thread-safety, helper no-op outside tracked turn,
  helper write under bound context, singleton stability). Wiring into
  the cognitive stages and the `engine.query()` finally-block
  cleanup lands in PR-10b. Design memo:
  [`docs/design/v0.3-working-memory.md`](docs/design/v0.3-working-memory.md).

### Changed

- **Verifier base scan (security_validator) is now default ON**
  (Cognitive Phase 2 PR-6 default flip). A fresh JAMES install now
  gets injection-echo detection on every answer without an operator
  having to discover the env flag. The base scan is ~5ms of
  pure-Python pattern matching against the final answer — well below
  the STEP 7 measurement noise floor (Run-A all-off: 159.6s vs
  Run-B verify-on attempt: 152.5s; the ~7s spread is LLM-call
  variance, not verifier cost) and independent of LLM availability.
  Fact-check (LLM-driven, +5-15s/query) remains opt-in via
  `JAMES_ENABLE_FACT_CHECK=1`. The legacy opt-in flag
  `JAMES_ENABLE_VERIFY=1` is still honoured as a no-op (truthy →
  True) so existing `.env` files keep working unchanged. A new hard
  opt-out `JAMES_DISABLE_VERIFY=1` silences both the base scan and
  any pending fact-check — consistent with operator intent for
  baseline-cost measurement or quiet-mode operation.

### Added

- **Episodic memory wiring across cognitive stages (Cognitive Phase 3
  PR-9b)** — a follow-up question in the same session can now see what
  the planner decomposed the prior question into, what reflection
  revised, and what verification flagged. PR-9a (`core/memory/episodic.py`)
  shipped the session-scoped SQLite store; this PR wires the
  `record_event()` calls into `planner.py`, `reflect.py`, `verify.py`,
  and the shared `trace_helpers.trace_synth_call` (covers every synth
  sub-stage). `engine.query()` binds `(session_id, turn_id)` to a
  ContextVar at turn start; `engine_memory.build_memory_context`
  reads the last 3 turns of plan / reflect / verify events and
  prepends a compact "[이전 추론 흔적 (이 세션)]" block to the system
  prompt. Same-session isolation enforced at the SQL layer
  (`WHERE session_id = ?`); the PR-O4 N-3 gate already prevents
  cross-session leak on a new session's first turn. Opt-out via
  `JAMES_EPISODIC_CONTEXT=0` for measuring baseline cost. New admin
  endpoint `GET /admin/episodic/{session_id}` returns the session's
  events for debugging (gated by the same `admin.metrics` permission
  as `/admin/trace/*`). 8 new tests in
  `tests/test_episodic_wiring.py` lock the contract (stage record,
  cross-turn read, new-session isolation, cross-session isolation,
  opt-out, ContextVar no-op when unbound, ContextVar happy path).

### Fixed

- **Cross-document evidence accumulation now works** — uploading two
  documents that both attest to the same `(subject, predicate, object)`
  triple now produces a relation with 2 sources (confidence ≈ 0.91
  with default LLM weights), rather than only the first doc's
  contribution. Previously `core/wiki_generator.py:640` returned
  `continue` when an entity already existed, silently dropping every
  subsequent doc's strengthening — Knowledge Cascade relations were
  permanently single-source, so the noisy-OR formula never had
  multi-source state to act on and `--dry-run` of the recompute
  migration found 0 affected relations across 278 production entity
  files. New helper `_merge_relations_into_existing_entity` matches
  on `(target_name, normalized_type)`, skips duplicate `doc_id` for
  idempotency (re-upload safe), recomputes confidence via noisy-OR,
  and writes the frontmatter back. Both forward and inverse
  directions aggregate symmetrically. 5 new tests in
  `tests/test_phase_b_ingestion_sources.py` lock the behaviour
  (cross-doc append, inverse aggregation, noisy-OR confidence after
  2 sources asserting 0.91, same-doc idempotency, distinct-target
  new-row). Design memo
  [`docs/design/v0.3-knowledge-cascade.md §4`](docs/design/v0.3-knowledge-cascade.md)
  describes the same behaviour as a historical reference.

- **Confidence from multiple sources no longer saturates at 2** —
  `compute_confidence_from_sources` now uses noisy-OR
  (`P = 1 - Π(1 - w_i)`) instead of clamped sum (`min(Σw, 1.0)`).
  With default LLM weights ~0.7, the clamped-sum implementation
  reached confidence = 1.0 from just 2 corroborating sources, losing
  all signal about *how strongly* a relation was supported (5 vs 20
  attestations collapsed to the same value). It also broke monotone
  cascade semantics: deleting one of multiple sources didn't reduce
  confidence when others kept it pinned at the ceiling. Noisy-OR
  preserves the signal asymptotically (5×0.7 → 0.998, < 1) and
  guarantees strict monotonicity on source add/remove — important
  for the graph DFS `confidence < 0.6` threshold gate in
  `core/graph_engine.py:335`. Single-source identity preserved
  (`min(w, 1) == 1 - (1-w) == w` for one source), so Phase A
  back-fills remain byte-identical and STEP 7 bench stayed within
  baseline tolerance. Production wiki audit: 0 multi-source
  relations existed at the time of the fix (because of the cross-doc
  bug above), so no historical confidence values changed. Includes
  `scripts/migrate_recompute_confidence.py` for any installation
  that may have accumulated multi-source relations under the wrong
  formula. 7 new tests in `tests/test_relations_schema.py` lock the
  behaviour (single-source identity, 2-source divergence from
  clamped sum asserting 0.58, asymptotic-not-saturated for 5+
  sources, strict monotonicity on add/remove, per-element weight
  clamping). Design memo
  [`docs/design/v0.3-knowledge-cascade.md §3`](docs/design/v0.3-knowledge-cascade.md)
  arrived at the same formula as a historical reference.

---

## [0.3.0] — Platform Skeleton (2026-05-17)

After 190 merged PRs since v0.2.0 (9 days, 129 test files), JAMES exits
the v0.2 Foundation Hardening cycle and enters **v0.3 Platform Skeleton**.
Axis 6's second-user gate cleared on 2026-05-13. The original v0.3 plan
(Plugin API as the single theme) was rebalanced after the 2026-05-14
user briefing: **Cognitive Layer** and **Knowledge Cascade** become the
two main tracks, **Plugin API** slips to v0.3.x or v0.4 pending external
contributor demand.

Full release notes: [`docs/release_notes_v0.3.0.md`](docs/release_notes_v0.3.0.md).

### Added

#### Change Request primitive (v0.2.x track)
- **`core/change_request.py`** generalises the `approver_username`
  pattern that v0.1 hard-coded for self-evolution alone. Every write
  becomes a proposal → review → admin approval → atomic apply →
  audit row. Two target types ship: `wiki_entity` (markdown edits with
  `base_hash` conflict detection) and `run_jobs` (workspace job gate).
  Trust zone documented in `docs/ARCHITECTURE.md §5.6`. PRs #237, #243,
  #239, #240, #247.
- Workspace UI panel for proposers / reviewers (`/workspace` Change
  Request tab). PR #239.
- CR-E (self-evolution wrap) deferred to Cognitive Layer Phase 2 PR-6
  per the 2026-05-14 user decision (verification engine fuses with CR-E
  end-to-end).

#### Knowledge Cascade (Phase A → E, sources-aware graph)
- **Phase A** — `sources: [{doc_id, weight, role, ts}]` schema replaces
  the v0.2 single `confidence` field on every relation. Production wiki
  migrated (213 entities / 656 relations back-filled; backup at
  `wiki.pre-v03-migration/`). PR #266.
- **Phase B** — `process_document_for_entities` writes sources directly
  (`role=extract` outgoing + `role=inverse` inverse + doc-entity
  self-source). Legacy callers unaffected. PR #269.
- **Phase C** — `DELETE /admin/files` cascade. New `core/cascade.py`
  with strengthened orphan-detection rules. PR #270.
- **Phase D** — `PUT /admin/files` (multipart replace) cascade. Extraction
  sidecar JSON + diff_triples. PR #274.
- **Phase E backend** — `core/graph_editor.py` (replace / append / delete
  + bidirectional sync + manual metadata). Behind `JAMES_GRAPH_EDIT=1`
  opt-in flag. PR #271.
- **Phase E UI** — `/admin/graph` edit-mode toggle + edge-click modal
  (sources display + manual append + delete relation). PR #273.

#### Cognitive Middleware Layer (architecture only, code in v0.3.x)
- **`docs/ARCHITECTURE.md §5.7`** introduces the Cognitive Middleware
  Layer between retrieval and LLM synthesis. 7 named components
  (Planner / Query Rewriter / Reflection / Verification / Tool Router /
  Memory Manager / Security Reasoner / Context Optimizer), trust zone,
  trace-replay invariant, **5-role multi-agent cap (anti-sprawl)**,
  memory scope layering (system / workspace / session), and deployment
  isolation deferred to v0.4. Code lands across v0.3.x phases. PR #275.
- Cycle plan: `docs/handovers/v0.3-cognitive-layer-track.md`.

#### Operational UX (cycle 12, live usability)
- **PR-O1** — `/admin/entities/<id>` 노드 클릭 요약 403 fix (Bearer
  header). PR #277.
- **PR-O2** — chat suggestion chips: 3 natural-language patterns added
  ("혹시 ~궁금하신가요?", "~에 대해 더 알고 싶으시면", "관련된
  질문으로는"), threshold relaxed `>=2 → >=1`. PR #279.
- **PR-O3** — long-term wiki save chip in-place spinner → ✓/✗ transition
  with mint accent ring, 1.4 s failure restore. PR #280.
- Remaining PR-O4 (N-3 long_ctx isolation) / PR-O5 (external matrix
  tightening) / PR-O6 (node editing + Korean labels) / PR-O7 (drag +
  click-to-connect) deferred to v0.3.0.x. Track:
  `docs/handovers/v0.3-operational-ux-track.md`.

#### Cyber UI — mono-cyber palette (6a → 6d)
- Mono-cyber palette migration: single `--accent` (mint) on dark
  background, replacing the v0.2 multi-hue gradient. PRs #222–#224.
- **6a** background texture (grid + corner radials). PR #223.
- **6b** single-accent glow on primary surfaces. PR #224.
- **6c** modal glassmorphism (`@supports (backdrop-filter)`). PR #225.
- **6d** live indicators (pulse dot + scan line, 4-page rollout). PRs
  #226 / #228.
- Token consolidation into `frontend/static/tokens.css`. PRs #214 / #221.
- WCAG dialog pattern on every modal (focus trap + ESC + ARIA roles).
  PR #216. `aria-label` on icon-only and JS-populated buttons. PR #217.
  `--muted-2` lifted above WCAG AA. PR #218.
- Inline-handler → `data-action` event delegation across all 4 pages.
  PRs #230, #232, #233, #241.

#### Audit pipeline — JSONL → SQLite mirror (Phase 1 → 4)
- **Phase 1** — tool JSONL events mirrored to SQLite `audit_log`. PR #206.
- **Phase 2** — attack + system JSONL events mirrored. PR #207.
- **Phase 3** — `/admin/audit/list` categories (`tools` / `attack` /
  `system`). PR #208.
- **Phase 4a** — legacy `/admin/audit` dropped; dashboard reads SQLite.
  PR #210.
- **Phase 4b-1** — `/code/surface/` reader migrated to SQLite. PR #211.
- **Phase 4b-2 (writer removal)** intentionally deferred 2–4 weeks of
  production mirror-reliability monitoring. ROADMAP "Deferred follow-ups".

#### Workspace + Scheduler (W7 / W8)
- **W7-A** — `data_artifacts` table + lifecycle (uploaded → extracted →
  indexed / failed). `wiki_links` records doc → entity derivation. PR #191.
- **W7-B** — standalone `/workspace` data-explorer page. PR #192.
- **W8-A** — generic job execution backbone + 3 handlers
  (`excel_build` / `doc_combine` / `entity_export`). PR #193.
- **W8-B** — chat-sidebar workspace tab. PR #194.
- **W8-C** — `wiki_links` populated on upload. PR #195.
- **W8-D** — scheduler with small cron DSL (`every:N` / `hourly` /
  `daily:HH:MM` / `weekly:DOW:HH:MM`) + 90-day result retention. PR #197.
- **W8-D follow-up** — `/admin/scheduler/status` + `/jobs/unschedule`. PR #204.

#### Auth + Policy matrix (W4 P3 / Q1-Q3)
- **W4 P3-2** — request authentication accepts `X-API-Key` header or
  `?api_key=` query parameter; system key resolves to `employee` role
  (no implicit admin authority). PRs #179 / #180.
- **W4 P5** — chat-page password-reset modal. PR #182.
- **W4 P6** — admin audit log page (category filter + search + paging).
  PR #183.
- **W4 Q1** — feature capability registry (`core/feature_registry.py`
  + `feature_overrides` table + `PolicyEngine.can_use_feature`). PR #184.
- **W4 Q2-a** — wire 17 admin endpoints onto `_require_feature`. PR #187.
- **W4 Q2-b** — catalog extension + remaining 38 endpoints. PR #188.
- **W4 Q2-c** — user-facing feature gates on `/query` / `/upload` /
  `/password` / `/api-keys`. Behaviour change: `/upload` denied for
  `employee` / `external` by default (previously any valid api_key).
  PR #189.
- **W4 Q3** — admin permission matrix UI (feature × role grid).
  PR #190.

#### License Track A + OpenSSF passing badge
- License Track A cleanup: `THIRD_PARTY_LICENSES.md` (one-shot via
  `pip-licenses`), README license-line unification, first-quarter
  trigger monitoring entry in `docs/LICENSE_PLAN.md §8`. PR #259.
- **OpenSSF Best Practices passing badge** achieved (2026-05-11,
  Tiered 111%). Badge displayed in `README.md` / `README.ko.md`.
  Project page: https://www.bestpractices.dev/projects/12806.

#### v0.2 axes 6 closure + Axis 6 user-feedback follow-ups
- **N-1** — `/admin/graph` snapshot now reflects entity files written
  by other engines (cache invalidation). PR #256.
- **N-3** — new-session greeting + cross-session leak (partial fix;
  full isolation in v0.3.0.x PR-O4). PR #257.
- **Web learn fix** — `/web learn` routes through proper LLM triple
  extraction (no more query-as-node). PR #252.
- **2-pass UNRESOLVED sweep** — every ingest resolves UNRESOLVED
  target_id references on a second pass. PR #253. Manual grand-sweep
  trigger: `POST /admin/wiki/resolve-relations`. PR #261.
- **One-shot cleanup script** for pre-#252 web-learn noise concepts.
  PR #254 (user runs `--apply` after dry-run review).
- **Workspace continuity** — `core/reasoning/modes.py` conversation
  continuity (Axis 6 item 1). PR #249.
- **Clean answer + dual web-search chip** (Axis 6 items 2-3). PR #248.
- **Reasoning panel** — retrieve → expand → verify phase grouping in
  `/admin/dashboard`. PR #235.
- **Citation chips** — `graph_paths` rendered as mint citation chips
  in chat answers. PR #229.

#### Chat UX (cycle 5)
- **N-4** — suggestion chip header with mint accent + uppercase. PR #263.
- **N-5** — mid-band web-search chip when retrieval below the
  configurable threshold. PR #263.
- **N-6** — in-page long-term save modal (`jamesConfirm()` replaces
  native `confirm()`, 6c glass + mint, WCAG dialog ARIA). PR #264.

#### Multimodal + extras
- **Video ASR** — ffmpeg + Whisper pipeline (`W1 §3-C Option A`). PR #198.
- **Chat file drag-drop + clipboard paste** with mini-thumbnails and
  sidebar auto-switch (W5 / W6). PRs #185 / #186.

### Changed

- **`core/memory/store.py` split** — 24 KB → 12 KB across natural
  boundaries (`db.py` / `conversation.py` / `summaries.py` +
  `store.py` facade). Public API preserved. CLAUDE.md rule #5 module
  size gate restored. PR #260.
- **Mono-cyber palette migration** — every page repainted; legacy CSS
  token aliases removed. PR #220.
- **`urllib3 >= 2.7.0` + `python-multipart >= 0.0.27`** floors
  raised to close 6 Dependabot high-severity alerts. PR #244.

### Security

- **`python-multipart >= 0.0.18`** floor raised earlier in the cycle
  for GHSA-59g5-xgcq-4qw3 (DoS via unbounded multipart part headers).
  PR #213.
- **`/upload/` feature gate** — `employee` / `external` denied by
  default (W4 Q2-c). A leaked `JAMES_API_KEY` alone (resolves to
  `employee`) no longer ingests documents.
- **Multimodal trust quarantine** continues from v0.2 Axis 4; web
  results pass `PolicyEngine.quarantine()` before joining the LLM
  context. Codified in `core/policy_engine.py` + `TrustedContent`.

### Fixed

- **F541 / F401 lint cleanup** — main CI green restored after Phase A
  migration residuals. PR #278.
- Several smaller live-usage fixes folded into the cycle 12 quick-fix
  bundle (PRs #277 / #279 / #280).

### Deprecated / Removed

- **Legacy `/admin/audit` endpoint** removed in Audit Phase 4a (#210).
  Operators migrate to `/admin/audit/list?category=…`.
- **Legacy CSS token aliases** removed. PR #220.

### Migration

```bash
git pull origin main
git checkout v0.3.0
pip install -r requirements.txt   # urllib3 >= 2.7.0, python-multipart >= 0.0.27

# new opt-in env knobs:
export JAMES_GRAPH_EDIT=1            # enable Phase E graph editor
export JAMES_ENABLE_EVOLUTION=0      # self-evolution opt-in (unchanged)
export JAMES_TRACE_STDOUT=0          # silence per-stage console mirror (unchanged)

# verify:
python -m unittest discover -s tests
python scripts/bench.py --suite=step7
```

If you ran v0.2.0 with a populated wiki, the Phase A migration ran
automatically on first boot under v0.3 — verify backup at
`wiki.pre-v03-migration/` before deleting it.

### Pending live validation (shipped, will follow up if regressions)

- Phase D file-modify cascade (#274) — end-to-end live verification
  with diverse formats
- Phase E graph editor UI (#273) — full edit-mode UX flow
- Cycle 12 PR-O1 / PR-O2 / PR-O3 — admin-UI / chat live spot-check
- Phase A migration (#266) `bench step7 --check` byte-identical
  verification on the user's production corpus

---

## [0.2.0] — Foundation Hardening (released 2026-05-08)

### Security

- **`python-multipart` spec floor raised to `>=0.0.18`** (GHSA-59g5-xgcq-4qw3
  — Denial of Service via unbounded multipart part headers). The pinned
  install (`requirements_pinned.txt`) was already on 0.0.26, so no
  upgrade-side risk; this change aligns `requirements.txt`'s spec with
  the safe minimum and closes Dependabot alerts #5 and #6 (both High).

### Added

#### OpenSSF Best Practices passing badge
- Achieved the **OpenSSF Best Practices passing badge** (2026-05-11,
  Tiered 111%). Badge is now displayed in `README.md` and
  `README.ko.md`. Project page:
  https://www.bestpractices.dev/projects/12806
- The submission documents the project's posture on bug-reporting,
  vulnerability disclosure (GitHub PVR + backup email), licensing
  (MIT), versioning (SemVer + 7 GitHub Releases), test suite
  (`james_*_test.py` and `tests/`), bcrypt password storage
  (PR #173, W4 P1-A), and static analysis baseline
  (PR #196 — ruff F821 enforcement with phased plan).

#### Reasoning Graph Visualizer (Axis 3 Observability/Explainability)
- **`/admin/graph`** — new admin-only 3D page that renders every wiki
  entity as a point in a soft-ball sphere and every ontology relation
  as a connecting line. Drag to rotate 360°, scroll to zoom, click to
  focus. Force-directed layout with link strength ∝ `min(deg(s), deg(t))`
  so densely-connected nodes drift together; a custom radial spring
  pulls the layout toward a sphere shell.
- **`/admin/graph/snapshot`** — new admin-gated read-only data endpoint
  (`source_type=prod|test`) that materializes the full entity + edge
  set as JSON. Cached by `(source_type, max_mtime)`; gzip-friendly
  short keys (`s`/`t`).
- **Pulse animation** — when a query is asked from the page's bottom
  query bar, the response's `graph_paths` strings are parsed
  client-side and a cyan additive sprite tweens along each traversed
  edge in chronological order, leaving a 4 s afterglow.
- **Sensitivity-aware**: nodes with `sensitivity == "sensitive"` and
  edges whose ontology entry is `sensitive=True` (HAS_SECRET,
  KNOWS_PASSWORD, HAS_CREDENTIAL, OWNS_PRIVATE) are filtered out
  server-side by default. `include_sensitive=1` is locked off until a
  dedicated elevated role lands.

### Implementation notes
- New module `core/graph_snapshot.py` (~8.4 KB) sits alongside
  `core/graph_engine.py` (15.8 KB) so the latter stays well under the
  20 KB module-size gate. No retrieval / pipeline / ontology code was
  modified — the visualizer is pure observability over data that
  already exists.
- 3D libs (Three.js 0.160, 3d-force-graph 1.73, d3-force-3d 3) are
  loaded from CDN; matches the project's no-bundler vanilla-JS
  posture. Vendoring for air-gapped deploys is tracked separately.
- Tests in `tests/test_graph_snapshot.py` cover the snapshot shape,
  sensitivity filter, mtime-based cache invalidation, server route
  registration, and frontend artifact contract.

---

## [0.1.1] — Path Auto-Detection (Patch)

### Fixed

#### Critical: Hardcoded Paths Removed
- **config.py**: `BASE_DIR` was hardcoded. Now auto-detected from `config.py`'s own location.
- **config.py**: Removed hardcoded user paths exposing the developer's Windows username.
- **vector_store.py**: `LOCAL_MODEL_PATH` was hardcoded. Now derives from `BASE_DIR`. Fixes the issue where renaming the project folder caused the embedding model to be re-downloaded externally.
- **patch_abac_fields.py / tools/admin/seed_data.py / tools/admin/wiki_reset.py**: Replaced hardcoded fallback paths with location-relative detection.

#### Cross-Platform Support
- Tesseract OCR path: auto-detected for Windows / macOS / Linux
- Poppler path: auto-detected for Windows; uses system PATH on macOS / Linux
- Ollama path: uses system PATH (no hardcoded location)

### Added
- Environment variable overrides for all binary paths:
  - `TESSERACT_PATH` — Tesseract binary
  - `JAMES_POPPLER_PATH` — Poppler bin directory
  - `OLLAMA_PATH` — Ollama binary
  - `JAMES_MODEL_PATH` — Sentence-Transformer model location
  - `JAMES_LLM_MODEL` — Default LLM model name (default: `gemma2:2b`)
  - `OLLAMA_API_URL` — Ollama API endpoint
  - `JAMES_MAX_UPLOAD_MB` — Upload size limit (default: 100)

### Security
- **CRITICAL**: Previous version (v0.1.0) included paths revealing the developer's local Windows username. Anyone cloning the repository could see this information. Now removed.
- Project folder can be renamed/moved freely without breaking functionality.
- Anyone cloning the repository can run `python server_llmwiki.py` immediately without editing paths.

### Migration from v0.1.0
No migration steps needed. The fix is backward compatible:
- Existing installations will continue to work
- Folder rename now safe
- No database / data changes required

---

## [0.1.0-alpha] — Initial Release

### Added

#### Core Engine
- Hybrid Search (Vector 60% + BM25 20% + keyword 20%)
- Graph-RAG with 12 ontology relation types
- DFS traversal with confidence-based pruning
- ChromaDB vector store with Sentence-Transformers embeddings
- Ollama-based local LLM execution

#### Security
- 3-stage access control (Vector / Graph / Output)
- RBAC with 4 roles
- ABAC with 4 sensitivity levels
- 31+ prompt injection pattern detection
- Instruction Isolation framework
- JWT authentication
- Rate limiting (30 req/60s)
- Full audit log in SQLite

#### Knowledge Management
- Markdown-based wiki as knowledge graph
- File ingestion (PDF, DOCX, images, video, audio)
- Automatic entity extraction and linking
- Relations stored in YAML frontmatter

#### Self-Evolution Scaffolding
- Patch Pipeline with 4-Gate validation
- 11-trait personality system
- Knowledge tracker (8 abilities + 6 domains)
- Feedback engine

#### Multimodal & Tools
- LLaVA, Whisper, ffmpeg, pytesseract, easyocr integrations
- Sandboxed Python execution
- File upload pipeline

#### Web Search
- Tavily (primary) + DuckDuckGo (fallback)

#### User Interface
- Web-based chat UI + Admin dashboard
- Session management
- Reasoning path visualization
- Confidence badges

#### Internationalization
- 286 i18n keys (English / Korean)
- Default language: English
- Live toggle (KO / EN)

#### Documentation
- README.md, README.ko.md
- SECURITY.md, ROADMAP.md, CONTRIBUTING.md, CHANGELOG.md
- .env.example

---

[0.3.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.3.0
[0.2.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.2.0
[0.1.1]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.1
[0.1.0-alpha]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.0-alpha
