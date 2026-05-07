# Session Handover — 2026-05-07

> Single-day session continuation note. After reading `CLAUDE.md` and
> `docs/handovers/v0.2.0-platform-track.md`, read this for the
> immediate state on 2026-05-07 PM. Treat as transient — once the
> open PR is resolved and Phase 2-C lands, this file can be deleted
> or rolled into `v0.2.0-platform-track.md`.

---

## 1. TL;DR — where we are right now

- **Open PR**: **#54** `refactor(policy): route graph ABAC through PolicyEngine.can_walk (#44 phase 2-B)`. CLEAN/MERGEABLE, bench `--check` already passed at PR open. Awaiting merge confirmation.
- **In flight**: Issue #44 (PolicyEngine extraction). Phases 1, 2-A complete and merged. Phase 2-B is PR #54. Phase 2-C is the immediate next task.
- **Just landed today**: 12 PRs merged (full list in §4 below). Most consequential: `core/reasoning_engine.py` split into `engine.py` + `modes.py` + `pipeline.py` (PRs #37/#38/#39 — all `core/` files now under 20 KB), STEP 7 locked as `scripts/bench.py --suite=step7 --check` with committed baseline (#52), RAGAS harness wired to local Ollama + miniLM (#51), PolicyEngine skeleton (#50), retrieval ABAC migrated to it (#53).
- **5 issues closed today**: #5, #6, #14, #29, #45 (auto-closed by their PRs). Plus 4 superseded older issues closed manually: #30, #31, #32, #33.

## 2. The open PR (#54)

```
gh pr view 54
gh pr merge 54 --squash --delete-branch
```

If you reach the same `[bench] OK — within step7 baseline tolerances` verdict on a re-run, merge directly. The PR body has the verification harness output and ABAC equivalence proof (3/3 cases). q11 byte-identical security block has now held across 7 cumulative bench runs.

## 3. Immediate next task — #44 phase 2-C

Migrate the remaining `check_access()` callsites in `core/security_layer.py` itself onto `PolicyEngine`. After this lands, only `core/policy_engine.py` and `core/security_layer.py::check_access` (the implementation backend) reference `check_access` directly — the "remove `core/policy_engine.py` should break ≥ 4 modules on import" criterion from #44 will be measurably closer.

### 2-C scope

Two functions, both in `core/security_layer.py`:

#### `cross_stage_abac_verify` (lines ~169-220)

Two callsites at lines 185 and 197 (current main; line numbers shift after PR #54 merges by +5 LOC). Both are `if check_access(user_role, meta):` — the rejection branch logs a violation. Migration: route through `_policy.can_retrieve` (line 185, vector docs) and `_policy.can_walk` (line 197, graph entities). The `Decision.applied_rule` field can replace the hand-written violation strings, but a strict pure-refactor PR keeps the violation strings unchanged.

```python
# Before
if check_access(user_role, meta):
    v_pass += 1
else:
    v_fail += 1
    violations.append(f"Vector 우회: role={user_role} sensitivity={meta.get('sensitivity')}")

# After (lazy import inside the function avoids module-load cycle)
from core.policy_engine import default_engine as _policy
...
if _policy.can_retrieve(user_role, meta).allowed:
    v_pass += 1
else:
    ...
```

#### `filter_answer_by_role` (lines ~277-318 of current main)

This one is more nuanced. It does not call `check_access` directly — it does keyword-based content masking by role. The `#44` issue lists it as `core/security_layer.py::filter_answer_by_role — output ABAC`, and the PolicyEngine method is `can_emit(role, content) -> Decision`. Today (#50 phase 1), `can_emit` always returns `allowed=True` because the existing function MUTATES content rather than gating it. Two reasonable interpretations:

(a) **Keep `filter_answer_by_role` as-is for now** — it's a content transform, not a binary decision. Mark the file as "wired to PolicyEngine in spirit" and defer to phase 3. Lighter PR but less progress on the done-when criterion.

(b) **Wrap `filter_answer_by_role` callers with `can_emit`** — call `_policy.can_emit(role, content)` first; if `.allowed`, then run the existing transform. Phase-1 `can_emit` always allows so behavior unchanged, but the call site is wired for future tightening (e.g., refusing to emit when `Decision.allowed=False`).

Recommendation: **(b)**. It moves the migration forward without changing behavior. Single callsite to update is in `core/reasoning/pipeline.py` around the `filter_answer_by_role` call (line ~279 of current pipeline.py).

### 2-C verification (per CLAUDE.md rule 2)

This PR touches `core/security_layer.py` (and possibly `core/reasoning/pipeline.py` for option b). The pipeline.py touch triggers the bench requirement. Standard contract:

```
$ python scripts/bench.py --suite=step7 --check
[ 1/12] retrieve  | RAG가 무엇인가?
      OK     ...   | graph_paths=15 | answer_len=...
... (10 rows) ...
[11/12] security  | BLOCK   0.0s | mode=                | graph_paths= 0 | answer_len=  26
[12/12] security  | X  TIMEOUT    (120.0s): timeout

총 소요: ...
[bench] OK — within step7 baseline tolerances
```

Paste this into the PR body. q11 byte-identical (26 bytes, blocked, gp=0) is the strongest invariant — should now be at 8/8 cumulative runs.

## 4. Today's merged PRs (chronological)

| PR | Topic | Commit |
|---|---|---|
| #35 | refactor(v0.2): consolidate `core/memory_*.py` → `core/memory/` package | `ad91155` |
| #36 | fix(server): UTF-8 console at server entry to prevent cp949 print crashes | `ba48433` |
| #37 | refactor(v0.2): create `core/reasoning/` package skeleton (#29 phase 1/3) | `2bcfeac` |
| #38 | refactor(v0.2): extract 4 mode handlers from `query()` (#29 phase 2/3) | `ee6a451` |
| #39 | refactor(v0.2): extract RAG pipeline from `query()` (#29 phase 3/3) | `bd12eb7` |
| #40 | fix(extract): tighten entity-extraction prompt for type accuracy + label diversity (#5, #6) | `9dc4944` |
| #41 | feat(upload): per-file progress bar + queue indicator + cancel via XHR (#14) | `1349f94` |
| #50 | feat(policy): introduce PolicyEngine skeleton (#44 phase 1/4) | `0aa416d` |
| #51 | feat(eval): RAGAS evaluation harness (#46 phase 1) | `40e4f34` |
| #52 | feat(eval): lock STEP 7 as bench.py + committed baseline (closes #45) | `77ba509` |
| #53 | refactor(policy): route retrieval ABAC through PolicyEngine (#44 phase 2-A) | `754e545` |

Plus three PRs landed by other devices on the same day (#42 CLAUDE.md primer, #43 platform-track / business-track handovers + ROADMAP align, #49 frontend UI refinement). All synced to local main.

## 5. Issue state summary

**Closed today**: #5, #6, #14, #29, #30, #31, #32, #33, #45 (9 closed in total this session, including the older duplicates #30~#33 which were superseded by #44~#48).

**Open issues** (`gh issue list --state open --label priority:high`):

| # | Topic | Notes |
|---|---|---|
| **#44** | PolicyEngine extraction | Phase 1 done (#50). Phase 2-A done (#53). **Phase 2-B is PR #54 (open)**. Phase 2-C next. Phases 3 (capability tokens) and 4 (multimodal TrustedContent) follow. |
| #46 | RAGAS integration | Phase 1 (harness shell) done in #51. **Phase 2** is committing a `baseline.json` from a representative-hardware run; live `/query/` integration depends on `bench.py` runner shape (now landed in #52). |
| #47 | Observability trace_id | Not started. |
| #48 | Self-evolution opt-in + approval gate | Not started. CLAUDE.md rule 3 applies. |
| #8 | Risky-coding-request policy | Not started. |

## 6. Operational reminders for the next session

- **CLAUDE.md rule 2** is enforced via `CONTRIBUTING.md` PR contract. PRs touching `core/retrieval_engine.py`, `core/graph_engine.py`, anything under `core/reasoning/` MUST paste the `bench.py --check` summary in the PR body. Other `core/` paths (e.g., `security_layer.py`) are not strictly required but pasting is good due diligence (PR #54 did this and was the right call).
- **`scripts/bench.py --update-baseline`** is destructive. Use only when an intentional scope change (data state migration, model swap) shifts the bands; never run on the same PR as the behavior change.
- **`scripts/step7_query_test.py` was deleted** in PR #52. The replacement is `scripts/bench.py --suite=step7`.
- **Server start**: `python server_llmwiki.py` (no env prefix needed — PR #36's `ensure_utf8_console()` handles cp949). Once `Application startup complete` appears, the bench runner is ready.
- **Issue closing**: GitHub auto-close from the PR body works for `Closes #N` lines. Multi-issue close in commit message via squash merge has occasionally missed entries — when the PR closes 2+ issues, double-check after merging.
- **Stale local branches**: 14 squash-merged branches were force-deleted earlier today. Repeat `git branch -vv` periodically; squash-merged branches show as `origin: gone` and `git branch -d` will refuse them — use `-D` when the corresponding PR is verified merged.
- **`wiki/prod/` is intentionally untracked** — it's user-uploaded entity data per `.gitignore`. Will always show as `??` in `git status`.

## 7. Where to look next (file map)

| Purpose | File |
|---|---|
| Active strategic frame | `docs/handovers/v0.2.0-platform-track.md`, `docs/PLATFORM_READINESS.md` |
| Architecture (PolicyEngine §5.5 just added) | `docs/ARCHITECTURE.md` |
| Engineering rules + module size gate + bench contract | `CLAUDE.md`, `CONTRIBUTING.md` |
| Bench runner | `scripts/bench.py`, `eval/regression/step7_{queries,baseline}.json` |
| RAGAS harness | `eval/ragas/run_ragas.py`, `eval/ragas/fixture_v0.2.json` |
| PolicyEngine | `core/policy_engine.py` (skeleton + 4 typed methods + Decision/TrustedContent) |
| Phase 2-C target functions | `core/security_layer.py::cross_stage_abac_verify`, `::filter_answer_by_role` |
| Reasoning pipeline (filter_answer_by_role caller) | `core/reasoning/pipeline.py` |

## 8. Things to deliberately NOT do

(Echo of `docs/handovers/v0.2.0-platform-track.md` §5, repeated for self-containment.)

- Do not propose a domain pack — v1.0 only.
- Do not run `bench.py --update-baseline` casually.
- Do not enable self-evolution by default.
- Do not couple `PolicyEngine` to a specific role taxonomy — it must accept pluggable schemas.
- Do not bypass the `bench --check` failure — fix in branch or land an explicit `chore(eval): rebaseline` PR first.
