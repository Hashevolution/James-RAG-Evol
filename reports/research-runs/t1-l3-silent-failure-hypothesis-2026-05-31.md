# T1 L3 Silent Failure — Hypothesis Memo (RRR)

> **Status**: post-mortem hypothesis space, not a verdict.
> Investigation queued for post-T1-completion (after cell L4 finishes
> ~19:45 KST). The matrix is still running; do not modify
> `core/` / `scripts/qvt_ablation_matrix.py` / `scripts/bench.py`
> until L4 completes.
>
> **Symptom**: T1 cell L3 (ADAPTIVE_BUDGET only) ran 100 queries
> against MultiHop-RAG balanced-100 (workspace trace evidence shows
> sessions `bench_multihop_rag_1` through `bench_multihop_rag_100`),
> but neither the bench JSON nor the cell JSON was written. The
> matrix runner moved on to cell 2 (L4) without surfacing an error.
> The background task's captured stdout file is 0 bytes.
>
> **작성일**: 2026-05-31 PM (T1 cell L4 mid-flight)

---

## 0. TL;DR

Four hypotheses ranked by prior likelihood. None of them can be
confirmed while the matrix is still running. The investigation
plan is deferred to post-T1; the recovery tool
(`scripts/qvt_recover_cell_json.py` PR #653) is the operator
fallback when this turns out to be a recurring issue. **This is a
candidate 7th wrong-fix-averted entry for the cycle's discipline
log** — applying the 4-step rule before the matrix re-runs anything
is now mandatory.

---

## 1. The 4-step rule applied (verification trail)

| Step | Observation |
|---|---|
| 1. axis NaN / saturated / missing | L3 cell JSON missing, L3 bench JSON missing |
| 2. read what's there | workspace traces show 100 sessions completed; no `reports/bench_*_multihop_rag_*.json` written between 17:28 (T1 launch) and 18:02 (cell 2 start) |
| 3. check JAMES response keys | bench.py output: `reports/bench_<sha>_<suite>_<ts>.json` at `scripts/bench.py:526` |
| 4. design vs matcher | bench.py write at line 545; matrix runner glob at `qvt_ablation_matrix.py:355` + `:380` (post #638). Both target the same pattern. The bench file simply does not exist on disk. |

So the failure is upstream of detection — bench.py did not produce
its output file even though all 100 queries completed.

---

## 2. Hypotheses (ranked by prior likelihood)

### H1 (most likely) — JSON serialisation error in results list

**Mechanism**: at `bench.py:545`, `json.dumps(...)` serialises
the `results` list. If any query's response contains a
non-serialisable type (e.g., raw bytes from a binary-content
answer, a NaN float, an unparseable unicode codepoint),
`json.dumps` raises `TypeError` / `ValueError` and the file is
never written.

**Evidence for**: the python 3.14 + Windows + cp949 environment
saw earlier issues with em-dash in stdout. JSON dump could plausibly
trip on a similar character class from a model output.

**Evidence against**: `ensure_ascii=False` is set, which means
escape-encoding is more permissive. Most JSON failure modes would
also leave a traceback in stderr → matrix runner's `capture_output=False`
means it would pass through to the task output file. But task
output is 0 bytes (stdout buffering separate issue, H2).

**Diagnostic**: add `try/except json.dumps` with explicit error
print + per-row binary search to find the offending result.

### H2 (highly likely, co-cause) — Python 3.14 + Windows stdout buffering

**Mechanism**: `python` invoked from subprocess with default
buffering means stdout flushes only on process exit. If bench.py
crashed mid-run (per H1), the in-buffer error message never
reaches the task output file. The matrix runner sees a
"completed" subprocess but with no captured output.

**Evidence for**: task output file `b82bipgbh.output` is 0 bytes
despite ~30 min of matrix activity. Cell 1 (L3) clearly ran (traces
exist) but the runner's own stdout (cell-start banner, etc.) is
also absent.

**Evidence against**: this alone wouldn't cause the bench JSON to
go unwritten. Combined with H1 it's the masking layer.

**Diagnostic**: invoke bench.py with `python -u` (unbuffered) from
the matrix runner. This is a one-line fix at `qvt_ablation_matrix.py:363-364`.

### H3 — bench.py exits cleanly without writing (silent skip)

**Mechanism**: bench.py has `args.dry_run` early return at line
486-498 that exits before writing. If `--dry-run` somehow ended
up in the matrix runner's subprocess invocation, no write happens
and the exit code is 0 (clean).

**Evidence for**: explains both the silent failure AND the
clean-looking subprocess exit.

**Evidence against**: matrix runner at `qvt_ablation_matrix.py:363-365`
invokes `bench.py --suite=multihop_rag --mode=retrieval` — no
`--dry-run`. Checked the runner code; flag is not present. Argv
contamination from environment would be unusual.

**Diagnostic**: print `sys.argv` in bench.py main as a first action.

### H4 — Disk / filesystem write failure

**Mechanism**: `out_path.write_text(...)` raises `OSError`
(disk full, permissions, antivirus quarantine). bench.py exits
non-zero; matrix runner's subprocess.run captures exit code but
doesn't surface it because `check=False`.

**Evidence for**: Windows + antivirus environments do occasionally
quarantine new JSON files briefly.

**Evidence against**: `reports/` directory has been written to
moments before (T0 sanity bench `bench_6e73197_*_154937.json` at
15:49). Same path, same process pattern.

**Diagnostic**: shell out `touch reports/test.txt` from the matrix
runner before invoking bench.py.

### H5 (low) — `out_path.relative_to(ROOT)` ValueError at line 558

**Mechanism**: if `out_path` is somehow not under `ROOT`,
`relative_to(ROOT)` raises ValueError. This raises AFTER
`write_text` already succeeded.

**Evidence for**: would cause non-zero exit despite written file.

**Evidence against**: if the write happened, the file would be on
disk. We searched — it isn't.

**Diagnostic**: not applicable (file would exist).

---

## 3. Investigation procedure (post-T1)

When T1 cell L4 completes (~19:45 KST):

### Step 1 — Inspect cell L4 outcome

- If L4 bench + cell JSON both present → L3 was an isolated failure
  (transient cause). Continue to Step 2 with rerun.
- If L4 also missing → systematic matrix runner / bench.py bug.
  Continue to Step 3 with full diagnosis.

### Step 2 — Rerun L3 standalone with diagnostics

```bash
JAMES_WORKSPACE=./workspaces/hotpot_eval \
PYTHONIOENCODING=utf-8 \
PYTHONUNBUFFERED=1 \
  python -u scripts/qvt_ablation_matrix.py \
    --tiers M_M --rows L3 --suite multihop_rag --n-runs 1 \
    2>&1 | tee t1-l3-diagnostic-rerun.log
```

`PYTHONUNBUFFERED=1` + `-u` + `tee` ensures full diagnostic capture.
Compare resulting bench JSON with the trace evidence to validate.

### Step 3 — Run bench.py standalone with H1/H2/H3 diagnostics

```bash
# 1. Confirm bench.py basic write works
python -u scripts/bench.py --suite=multihop_rag --mode=retrieval --dry-run

# 2. Run a small smoke (smaller fixture if exists)
JAMES_WORKSPACE=./workspaces/hotpot_eval \
  python -u scripts/bench.py --suite=multihop_rag --mode=retrieval 2>&1 \
    | tee bench-py-smoke.log
```

If smoke produces bench JSON → bug is in matrix runner subprocess
invocation. If smoke also fails → bug is in bench.py output write.

### Step 4 — Patch matrix runner with `python -u` (H2 mitigation)

One-line fix at `scripts/qvt_ablation_matrix.py:363-364`:

```python
subprocess.run(
    [sys.executable, "-u", str(ROOT / "scripts" / "bench.py"),  # add -u
     f"--suite={suite}", "--mode=retrieval"],
    ...
)
```

This is harmless on success paths and surfaces stdout on failure
paths. Land regardless of H1/H3 outcome.

---

## 4. Recovery options

Once root cause is known:

| Outcome | Action |
|---|---|
| H1 confirmed | Patch bench.py to wrap json.dumps in try/except + write a `.error` sidecar with the offending result. Re-run T1. |
| H2 confirmed (alone) | Apply `-u` patch (Step 4). T1 cell L4's silent-failure if any, may still recur until H1 root-fix also lands. |
| H3 confirmed | Trace argv pollution source (probably .env or env-var). Patch + re-run. |
| H4 confirmed | OS-level diagnostic; not a code fix. |
| All ruled out | Add explicit error capture in matrix runner (subprocess.run + capture_output=True + log stderr) and re-run to gather data. |

For the immediate L3 attribution gap:

- **Preferred recovery**: full L3 rerun standalone after root cause
  identified + matrix runner patched (Step 4).
- **Fallback**: `scripts/qvt_recover_cell_json.py` Mode B with
  proper mtime window (post-T1 trace dir is stable; mtime
  isolation works cleanly). Cost axes only — quality axes "not in
  evidence."

---

## 5. Discipline note — 7th wrong-fix-averted candidate

Per the cycle's running count, this matters:
- #618 (path), #619+#623 (hallucination), #625 (suite arg),
  #638 (glob), Correction 5 (AUTO_ROUTER no-op), Correction 6
  (ADAPTIVE_BUDGET wrong-axes) — **6 averted so far**

If this turns out to be a real systemic matrix-runner bug, the
7th wrong-fix-averted would have been: *"the L3 cell verdict was
missing, so the operator might have assumed ADAPTIVE_BUDGET
behaves wildly different than expected at production tier. The
4-step rule applied to the empty cell location surfaced the silent
failure before any conclusion was drawn."* Same generalisation
(bucket-(a) wiring, layer-intent mismatch family).

Even if it's a one-off (H4 disk hiccup), the discipline of
**looking for the cell JSON within minutes of expected write** is
the bug-catcher. Update `feedback_oracle_phrase_artifacts.md`
"확장 3" to add this as a worked example after T1 closes.

---

## 6. Out of scope

- Patching the matrix runner mid-run (would kill T1's cell L4)
- Speculating on H1/H2/H3 root cause beyond the diagnostic list
- Rerunning L3 immediately (waiting for T1 cell L4 completion to
  preserve compute investment)

---

## 7. References

- bench.py write surface: `scripts/bench.py:545-558`
- Matrix runner subprocess invocation: `scripts/qvt_ablation_matrix.py:363-365`
- Matrix runner post-bench glob: `scripts/qvt_ablation_matrix.py:380` (post #638 fix)
- Recovery tool: `scripts/qvt_recover_cell_json.py` (PR #653)
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Cycle PR ledger (44 PRs in α-5 + post-closure self-audit + α-6 design):
  ROADMAP §v0.4.x + handover §7.10
