# α-5 Cycle PR Index (2026-05-30 → 2026-05-31)

> 45 PRs across one multi-day session. This index gives a
> by-category view of what each PR did so a future operator
> can navigate the cycle without re-reading every PR description.
>
> **Cycle span**: PR #608 → PR #654 (sequentially landed)
> **Cycle PRs in flight at write time**: none (T1 mid-flight is
> matrix re-run, not a new PR)
> **Cumulative JAMES code change attributable to α-5
> measurement debt**: **0 lines**

---

## Quick stats

| Category | Count |
|---|---|
| Total cycle PRs | **45** |
| α-5 inheritor (think-mode preludes) | 4 (#608/#609/#610/#611) |
| α-5 cycle proper (#612 onward) | 41 |
| Measurement-side fixes (bucket-d / bucket-a) | 5 |
| Design / methodology docs | 17 |
| Tooling scripts | 9 |
| Tests | 1 (4-step rule contract) |
| Operator-facing handovers / runbooks | 5 |
| Closure docs | 4 |
| Post-closure self-audit | 5 (CCC / DDD / EEE / FFF / RRR + more) |
| Cycle-side wrong-fix-averted | 6 (with 1 RRR-candidate pending T1 close) |

---

## A. Think-mode preludes (α-5 inheritor, #608-#611)

| PR | Title | Topic |
|---|---|---|
| #608 | A3 — think-mode quality boundary | 5 stages × hard fixtures |
| #609 | A2 — gemma4:e4b per-stage think-mode policy | opt-in plumbing |
| #610 | backlog reconciliation A3 #608 + A2 #609 closure sync | handover |
| #611 | A3 v2 — LLM-judge confirmation | 3 surprising cells |

Used in α-5 as workspace `.env` `JAMES_GEMMA4_E4B_THINK_OFF=1` policy.

---

## B. α-5 entry (#612-#615)

| PR | Title | Topic |
|---|---|---|
| #612 | α-5 prep — driver + design memo | operator-ready matrix |
| #613 | α-5 prereq plan | 4-risk addressal + oracle negation + T0 smoke gate |
| #614 | step7 v6 → v7 — path annotation | internal canary (later) |
| #615 | α-5 reset — MultiHop-RAG external benchmark | 5-axis × question-type matrix |

PR #615 is the reset point — post-#614 fixture v7 risks moved the cycle to MultiHop-RAG.

---

## C. α-5 execution + bucket-(d) corrections (#616-#623)

| PR | Title | Bucket | Wrong-fix avoided |
|---|---|---|---|
| #616 | α-5 execute — ingest wrapper + bench timeout fix | exec | — |
| #617 | handover §7.4 first per-question-type signal | docs | — |
| #618 | source-recall — bench dropped `sources` field | **(d)** | path=0 → real 0.42 (Correction 1) |
| #619 | abstention phrases — gemma4:e4b English refusal | **(d)** | hallucination 76% → 36% (Correction 2a) |
| #620 | rescore tool + §7.4 hallucination rate correction | tool | — |
| #621 | 4-bucket diagnostic taxonomy + dual purpose | docs | — |
| #622 | render_report defensive path + bucket retroactive | fix | — |
| #623 | abstention phrases round-2 + session_id suite-aware | **(d)** | F1 → 0.70 (Correction 2b) |

The 3 bucket-(d) PRs are the cycle's first three wrong-fix-averted.

---

## D. α-5 cycle entry to ROADMAP + matrix runner fix (#624-#625)

| PR | Title | Bucket |
|---|---|---|
| #624 | ROADMAP §v0.4.x α-5 cycle (in flight) | docs |
| #625 | matrix runner subprocess suite-arg (was hardcoded step7) | **(a)** — Correction 3 |

PR #625 is the cycle's 4th wrong-fix-averted (bucket-(a) sibling to #618/#619/#623 measurement-side family).

---

## E. T0 prep infrastructure (#626-#633)

| PR | Title | Type |
|---|---|---|
| #626 | T0 smoke result analysis TEMPLATE | docs |
| #627 | Pareto verdict walk-through + CLAUDE.md `fix` exempt + post-mortem | docs |
| #628 | T0 analysis fill script | tool |
| #629 | oracle.py → package split design (deferred) | docs |
| #630 | α-5 cycle summary outline | docs |
| #631 | publishable narrative draft — "Don't Build a Layer for the Bug" | docs |
| #632 | bucket-(c) LLM-judge abstention detector design memo | docs |
| #633 | `qvt_promote_findings.py` — auto-draft memory entries | tool |

8 PRs of T0 prep infrastructure during the smoke run.

---

## F. Mid-cycle sync + 2 operational fixes (#634-#637)

| PR | Title | Type |
|---|---|---|
| #634 | mid-cycle sync — ROADMAP PR table to 24 + backlog §7.5/7.6/7.7/7.8 | docs |
| #635 | `core/observability.py::_trace_root()` workspace-aware (D11) | fix (code) |
| #636 | A2 default-flip Quality Delta Card pre-template (D12) | docs |
| #637 | 4-step rule contract test | test |

PR #635 is the only code-side change — but it's a code hygiene fix, not a measurement-debt fix (D11 was queued before T0 started).

---

## G. Correction 4 (matrix glob bug) (#638-#640)

| PR | Title | Bucket |
|---|---|---|
| #638 | matrix bench-output glob suite-aware (sibling to #625) + cell rescore tool | **(a)** — Correction 4 |
| #639 | Correction 4 post-mortem + narrative + backlog §7.9 | docs |
| #640 | `qvt_rescore_all_cells.py` — matrix-end audit + bulk rescore wrapper | tool |

PR #638 is the 5th wrong-fix-averted (bucket-(a) wiring sibling to #625).

---

## H. T0 closure (#641-#645)

| PR | Title | Type |
|---|---|---|
| #641 | matrix closure runbook (operator sequence) | docs |
| #642 | cycle summary draft — Correction 4 absorption + 32-PR ledger | docs |
| #643 | publishable narrative §1 + §4 — Correction 4 absorbed | docs |
| #644 | publishable narrative §6 split — baseline + routing verdict | docs |
| #645 | T0 CLOSURE — Branch B verdict, routing inert at production tier | docs (closure) |

PR #645 is the formal T0 closure PR.

---

## I. Post-closure self-audit + α-6 design (#646-#648)

| PR | Title | Type |
|---|---|---|
| #646 | α-6 sector × LLM ablation matrix — successor to α-5 | docs (design) |
| #647 | α-6 local-first phasing — 9 local Ollama models inventoried | docs (design) |
| #648 | α-5 post-closure verdict correction — AUTO_ROUTER no-op + ADAPTIVE_BUDGET wrong-axes | docs (correction) |

PR #648 carries Correction 5 (AUTO_ROUTER no-op, **bucket-(a) wiring**) AND Correction 6 (ADAPTIVE_BUDGET wrong-axes, **bucket-(a) layer-intent-axis-mismatch** — new sub-category). Cycle's 6 wrong-fix-averted total.

---

## J. T1-wait window (#649-#654)

| PR | Title | Type |
|---|---|---|
| #649 | README mother-platform framing primary (GGG) | docs |
| #650 | α-6 engineering pre — 5 sector flag PR sequence plan (FFF) | docs (design) |
| #651 | MultiHop-RAG paper baseline comparison plan (EEE) | docs (research) |
| #652 | CLAUDE.md rule 2 layer-intent extension + verdict_per_layer schema (NNN+OOO) | docs (policy) |
| #653 | `qvt_recover_cell_json.py` — manual cell JSON recovery (QQQ) | tool |
| #654 | T1 L3 silent-failure hypothesis memo (RRR) | docs (investigation) |

6 PRs during the T1 background run while the matrix re-tested L3 / L4 cells.

---

## K. Memory entries (user dir, not in repo)

| Slug | Topic |
|---|---|
| `alpha_5_multihop_rag_reset` | α-5 reset rationale + 5-axis Pareto + question-type cross-tab |
| `feedback_oracle_phrase_artifacts` | 4-step rule (확장 1+2+3) — bucket-(d) phrase coverage + bucket-(a) wiring + bucket-(a) layer-intent mismatch |
| `mechanism_layer_intent_axis_alignment` | RAG-general mechanism for per-layer per-axis matching |
| `feedback_jameses_positioning_replayable_rag` (correction) | Replayable RAG = one differentiator, not whole identity |

4 memory entries written / updated. JJJ promoted the layer-intent mechanism to a standalone entry.

---

## L. Operator artifacts (matrix outputs)

| Path | Content |
|---|---|
| `reports/promo-assets/v0.4-qvt-ablation-matrix-20260531T065209.md` | T0 matrix report (3 cells + sanity) |
| `reports/research-runs/qvt-ablation-T0-smoke-result-20260531-1552.md` | T0 analysis (filled) |
| `reports/research-runs/qvt-ablation-rescore-summary.md` | T0 cell-rescore audit |
| `reports/research-runs/alpha-5-cycle-summary-DRAFT.md` | cycle summary (filled per closure) |
| `reports/research-runs/alpha-5-publishable-narrative-DRAFT.md` | publishable narrative (5 sections filled) |
| `reports/research-runs/alpha-5-diagnostic-chain-post-mortem.md` | post-mortem (4 corrections) |
| `reports/research-runs/multihop-rag-paper-baseline-comparison.md` | external baseline comparison plan (EEE) |
| `reports/research-runs/t1-l3-silent-failure-hypothesis-2026-05-31.md` | T1 silent-failure investigation memo (RRR) |
| `workspaces/hotpot_eval/eval/qvt/baseline_3a961a3_rescored.json` | corrected α-5 baseline (path 0.404 / graded 0.343 / abst_f1 0.704) |

---

## M. Status of follow-up tracks

| Track | Trigger | Status |
|---|---|---|
| α-5 T1 (L3+L4 measurement) | post-T0 | **in flight** (cell L4 active, L3 silent-failure under investigation) |
| α-5 T2 (M_S + M_L tiers) | T1 verdict | deferred |
| A2 default-flip | G1+G2+G3 gates | template ready (#636), gate unchanged |
| Oracle package split | post-closure clean | design ready (#629), deferred |
| Bucket-(c) LLM-judge | post split | design ready (#632), deferred |
| α-6 Engineering pre (5 sector flags) | operator decision | plan ready (#650), unstarted |
| α-6 Phase 1 (sector ablation × gemma4) | post Engineering pre | gated |
| α-6 Phase 3 (local LLM family) | post Phase 1 | gated |
| MultiHop-RAG paper baseline reproduction | independent | plan ready (#651), unstarted |
| AUTO_ROUTER multi-tier engineering | α-6 Phase 5+ blocker | sketched (#646 §5.5), unstarted |
| DOI bump | post mid-June joint piece framing | **explicitly deferred** (see `docs/handovers/v0.4-doi-bump-defer-2026-05-31.md`) |
| Joint piece negotiation | 6/6+ Ali resume | Lane C, on hold |

---

## N. References

- ROADMAP §v0.4.x α-5 cycle — section anchor
- Backlog handover §7.10 — closure run log
- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`
- Layer-intent mechanism: `memory/mechanism_layer_intent_axis_alignment.md`
- DOI defer decision: `docs/handovers/v0.4-doi-bump-defer-2026-05-31.md`
