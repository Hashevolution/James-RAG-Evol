# Axis-4 — Recovery / Graceful Degradation (reachability proxy, LLM-free)

> **Status**: EXECUTED result (2026-06-04). Deterministic, no LLM, no core/
> edits. Parallel-safe. **Branch**: `claude/graph-rag-abac-benchmark-qRBnr`
> **Artifact**: `eval/abac_bench/probe_recovery.py` +
> `eval/abac_bench/fixtures/axis4_recovery.py`
> **Run**: `python -m eval.abac_bench.probe_recovery`

---

## Definition (new — VAULT/SNU leave this as future work)
For a role and question:
- **candidate** = answer is legitimately reachable (all evidence endpoints
  accessible) **and** the default/primary path is gated → a *routing
  failure*, not a legitimate denial.
- **recovered** = some alternative path is fully permitted.
- **recovery_rate = recovered / candidate** (per role).

## Result
| role | reachable | primary-gated | candidate | recovered | recovery_rate |
|---|---|---|---|---|---|
| external | 0 | 6 | 0 | 0 | n/a |
| employee | 6 | 6 | **6** | **3** | **50%** |
| manager | 6 | 0 | 0 | 0 | n/a |
| admin | 6 | 0 | 0 | 0 | n/a |

@ employee: recovered `R1,R2,R4` (internal bypass permitted); unrecovered
`R3,R5` (no alternative), `R6` (alternative also gated).

## What this establishes
- Recovery is **only meaningful in the "answer-reachable but default-path-
  gated" regime** — i.e. exactly the graph-specific failure Axis-2 found.
  external (answers not reachable → legitimate denial) and manager/admin
  (hub visible → no gating) have zero candidates. This scoping is itself the
  honest framing: recovery measures *routing*, not policy.
- At the regime where it matters (employee), **half the lost answers are
  recoverable** by re-routing through a permitted alternative path. The other
  half fail for a structural reason flat retrieval never has (no permitted
  route, or the only alternative is also gated).
- Gives JAMES a concrete graceful-degradation target: a Tier-2 retrieval
  policy could *prefer permitted alternative paths* before declaring "no
  info", recovering the recoverable fraction without weakening access control.

## Honest caveats
- Reachability proxy, not measured answer quality (LLM probe pending).
- recovery_rate magnitude is fixture-dependent (here 50% by construction);
  the contribution is the *metric + the regime scoping*, not the number.

## Tier-1 deterministic set — COMPLETE
| | artifact | headline |
|---|---|---|
| Measurement 0 | enforcement audit | gate is post-filter, not "by construction"; paths/relations unfiltered |
| Axis 3 | `probe_path_survival` | node-list enforced 4/4, **output LEAK 4/4** (2 channels) |
| Axis 2 | `probe_differential` | graph 3/7 vs flat 6/7 @ employee; hub removal breaks 4 (flat 0) |
| Axis 4 | `probe_recovery` | **50%** of path-gated-but-reachable answers recoverable |

## Next (NOT parallel-safe — hold until test run finishes)
- LLM-echo probe + parametric-baseline subtraction (validates the proxies;
  confirms whether JAMES's *actual answers* track the reachability verdicts).
- Tier-2 must-fixes (close Axis-3 channels A/B; add Axis-4 re-routing).
