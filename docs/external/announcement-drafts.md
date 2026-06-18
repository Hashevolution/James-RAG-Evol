# External Announcement Drafts (Phase 5) — NOT POSTED

> **These are drafts for operator review. Nothing here has been or should be
> auto-posted.** External-facing claims are gated on measurement evidence
> (v0.5 entry rule) and the honest-framing rule. The framing below is
> deliberately *adversarial-invite*, not *gains-marketing* — we ask people to
> break the benchmarks, not to admire a leaderboard win.
>
> Why the framing differs from the original handover: the handover suggested
> "Can anyone reproduce these Graph-RAG gains?". The project has **not**
> established generic Graph-RAG reasoning gains (MuSiQue/MultiHop-RAG measured
> null/parity), and RAB's SPEC §6.5 disclaims a JAMES-wins reading. Posting a
> "gains" claim would resurrect an overclaim the project spent multiple cycles
> retracting. The honest ask is about **reproducible audit/lifecycle
> benchmarks**, not reasoning superiority.

---

## r/LocalLLaMA (draft)

**Title:** Two deterministic RAG benchmarks you can reproduce in ~2 minutes (no GPU): audit-replayability + temporal retrieval

**Body:**
We've been building a local-first Graph-RAG engine and got tired of
unreproducible benchmark claims, so we shipped two **deterministic-scorer**
benchmarks (no LLM in the scored path) with committed fixtures:

- **RAB** — scores whether a RAG/agent system's audit log can be *replayed*
  (3 metrics mapped to EU AI Act Art. 10/12/19).
- **LRB** — scores *temporal* retrieval (does the system retrieve what was
  valid at query-time?).

```
git clone … && cd James-RAG-Evol
pip install -r requirements.txt
bash benchmarks/run_all.sh        # ~2 min, no GPU, no Ollama
```

Honest scope: this is **not** a "we beat vector RAG on reasoning" post. On
open multi-hop our own measured result is null/parity, and we say so. The ask
is narrower and more useful: **can you reproduce the deterministic numbers, or
break the benchmarks?** Variant/failed reproductions welcome.

---

## r/MachineLearning (draft)

**Title:** [P] Pre-registered, deterministic-scorer RAG benchmarks (RAB: audit-replay; LRB: temporal retrieval) — reproduction + adversarial reports wanted

**Body:**
Two sibling benchmarks, both pre-registered before measurement, both scored by
deterministic functions over committed JSON (no LLM judge in the headline
path), both with baseline-vs-system gap tables. Preprints + SPEC + fixtures +
one-command runner all committed.

We're explicitly inviting **adversarial scrutiny**: a trivial system that
games either metric is a contribution to the benchmark. Honest-framing note:
the RAB headline is the *gap structure*, not a JAMES-wins leaderboard; LRB's
pattern/gap are scale-robust while absolute magnitudes are scenario-sensitive.
Repro path: `benchmarks/README.md`.

---

## Hacker News (draft)

**Title:** Show HN: Reproduce our RAG audit + temporal-retrieval benchmarks in 2 minutes (no GPU)

**Body:**
Deterministic-scorer benchmarks with committed fixtures and a one-command
runner. Not a reasoning-superiority claim — on open multi-hop we measured
null/parity and document it. We want reproductions and benchmark-breaking
attempts. `bash benchmarks/run_all.sh`.

---

## Pre-post checklist (operator)

- [ ] Core tier re-run green on a non-reference machine (Linux/macOS) before posting
- [ ] Repro labels created (`reproduction-confirmed` / `-variant` / `-failed`)
- [ ] Issue template enabled (`.github/ISSUE_TEMPLATE/reproduction-report.yml`)
- [ ] Links resolve (preprint PDFs, SPEC, `benchmarks/README.md`)
- [ ] No "gains"/"beats"/"SOTA" language re-introduced in the final post
