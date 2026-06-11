"""LRB (Lifecycle Retrieval Benchmark) v0.1.0 — Phase A smoke.

Pre-registered by `docs/research/lrb-phase-a-smoke-preregistration-
2026-06-11.md`. Design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-
benchmark-design.md`.

Phase A scope (LOCK):
  * SUTs:  Vanilla in-memory RAG + JAMES (audit-native validity window)
  * Axes:  R@5, R@10, P@5, P@10, Latency, Token cost, Temporal accuracy
           (all deterministic; no LLM judge anywhere — RAB H1 strict).
  * Fixture: eval/external/_fixtures/lrb/scenario_S1_quarterly.json
  * Honest tier: 2-SUT smoke (Phase B/v0.2 adds GraphRAG / ActiveGraph).

This package mirrors `eval/rab/` in shape (driver / scorer / adapters)
to keep operator muscle memory consistent.
"""
