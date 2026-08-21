# Run-identity contamination — scope, fix, and what only the operator can settle

**Date**: 2026-08-19
**Trigger**: Ali Afana's fourth engineering finding (2026-08-19) —
*"Salt your run identities. Ours were keyed by a human-readable name,
and the stack silently find-or-created the same conversations across
four sweeps — turning what were labelled before and after columns into
turns 2 to 5 of a single conversation."*
**Status**: mechanism confirmed and demonstrated in tests; the
adversarial sweep is fixed; **three other measurement paths are exposed
and deliberately left unchanged** pending an operator decision.

---

## 1. The mechanism, in JAMES

Three lines make a shared conversation key harmful:

| Where | What |
|---|---|
| `routes/query.py:178` | `session_id = data.session_id or "default"` |
| `core/reasoning/engine_memory.py:83` | that session's **last 5 turns** are injected into the prompt |
| `routes/query.py:231` | every answered turn is written back |

And `core/reasoning/engine.py:233` calls `build_memory_context` **before**
the mode dispatch, so this applies to the retrieval path too, not only
chat. The engine's own comment at `engine.py:271` describes the failure
in as many words: *"memory_context (prior turns including the last
inference-only answer) is mixed back into the prompt → new answer looks
identical to the previous"*.

`tests/test_sweep_run_identity.py::TestHistoryBleedMechanism` pins this
against a temp DB: turns saved under one key come back in the next
call's context; a salted per-case key starts empty.

## 2. What was exposed

Only four things POST to `/query/`. `eval/qvt/oracle.py` makes no HTTP
call at all (it consumes bench output) and `scripts/bench_lc_scope_arms.py`
only polls `/healthz` before shelling out to `bench.py`; neither is
exposed directly.

| Poster | Session key | Within one run | Across runs |
|---|---|---|---|
| `scripts/adversarial_sweep.py` | **none** → server default `"default"` | ❌ all 18 cases shared one conversation | ❌ |
| `scripts/bench.py` | `bench_<suite>_<qid>` | ✅ partitioned per query | ❌ **re-joins every previous run of the same query** |
| `eval/ragas/run_ragas.py` | `ragas_live_<i>` | ✅ | ❌ |
| `scripts/research/q15_repeat_audit.py` | `q15_audit_<run_idx>` | ✅ | ❌ |

The sweep was the worst case — no key at all, so case *N* was answered
with cases *1..N-1* in its prompt. The other three are exactly the shape
Ali described: a stable, human-readable name that silently re-joins.

**Not exposed:** the V3′ / Direction 1 measurement drivers
(`scripts/research/v3prime_*.py`, `lrb_run_*.py`) call Ollama's
`/api/generate` directly — one process, no session, no history. The
seven-tier gradient in the joint deposit is unaffected, which is why the
first reply to Ali could say so.

## 3. What was fixed

`scripts/adversarial_sweep.py` now mints a per-case, per-run key:

```
advsweep-<8 hex run salt>-<case_id>
```

The salt is `uuid4` at process start, so a re-run can never rejoin a
previous sweep. The key is recorded on `CaseResult` so it lands in the
run JSON and can be grepped against `audit_log`. Eleven tests in
`tests/test_sweep_run_identity.py` cover key uniqueness, run-stability,
the salt's shape (random hex, not a readable name), and the store-level
bleed it prevents — plus a guard that the runner still posts the fixture
text byte-for-byte, since the bidi cases test the server-side gate.

## 4. What was **not** fixed, and why

`bench.py`, `run_ragas.py` and `q15_repeat_audit.py` keep their stable
keys. Changing them is an operator call, not a mechanical fix:

- `bench.py` is the **STEP 7 gate for every PR touching
  `core/{retrieval,graph,reasoning}`** (CLAUDE.md rule 2). Salting it
  changes the conditions under which future numbers are produced, so
  post-fix results are not directly comparable to the baselines in
  `eval/qvt/baseline_<sha>.json` — it likely implies a re-baseline.
- The current key was chosen deliberately: the comment at
  `bench.py:323` records that it was widened from a hardcoded
  `bench_step7_*` precisely so suites stay distinguishable in
  `reports/trace/*.jsonl` and `audit_log`. A salt has to preserve that
  correlation, e.g. `bench_<suite>_<qid>_<runsalt>`.

## 5. What only the operator can settle

Whether any *published* number was actually affected depends on whether
the machine that produced it carried prior turns in
`memory/james_memory.db`. A fresh container or a wiped DB accumulates
nothing. That database is not in the repository and cannot be inspected
from a session container.

One command answers it:

```bash
sqlite3 memory/james_memory.db \
  "SELECT session_id, COUNT(*) AS turns
     FROM conversation_history
    GROUP BY session_id
    HAVING turns > 2
    ORDER BY turns DESC
    LIMIT 40;"
```

- Rows like `bench_step7_q07` with a large count → that query's bench
  runs have been answered with earlier answers in context, and the
  affected suites need a re-run against wiped history before their
  numbers are quoted again.
- `default` with a large count → the Track 2c sweep (and anything else
  that omitted a key) accumulated there.
- No rows above 2 turns → nothing accumulated; the exposure was
  latent and the sweep fix is purely preventive.

## 6. Consequence for the Track 2c table sent to Ali

`eval/adversarial/ar_ecommerce-cross-stack-comparison.md` reports N=1
per case with a note reading *"bidi_02 — one JAMES verdict slipped
resisted → partial between the two runs. With N=1 this is most likely
single-run noise"*. Order contamination is now a live alternative
explanation for that slip, since every case in that sweep shared one
conversation.

The re-measurement needs a live JAMES server plus Ollama and is
therefore operator-gated. Until it runs, **no figure from that table is
re-confirmed to Ali** — the first reply already committed to sending
what each finding did or did not reproduce, in its own message, once
measured.

Runbook:

```bash
# 1. start from clean history
sqlite3 memory/james_memory.db "DELETE FROM conversation_history;"
# 2. re-run the suite (now salted per case)
python scripts/adversarial_sweep.py --fixture eval/adversarial/ar_ecommerce-v1.1-james.yaml
# 3. diff the per-case verdicts against the table in
#    eval/adversarial/ar_ecommerce-cross-stack-comparison.md §2
```
