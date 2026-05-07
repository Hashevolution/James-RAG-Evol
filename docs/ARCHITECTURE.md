# JAMES — Architecture & Design Principles

> Engineering reference for contributors. Describes what JAMES is,
> what it deliberately is not, and the trust boundaries that govern
> all design decisions.
>
> Status: living document. Last updated: v0.2.0-dev.

---

## 1. Mission

A **local-first, auditable knowledge reasoning system** that answers
questions over a private knowledge base with:

- explicit reasoning paths (sources + graph trace)
- role-based access at every stage
- human-supervised improvement loop

JAMES sits **alongside** systems of record (ERP, DMS, CMS) — never
replaces them.

---

## 2. Non-goals

JAMES is deliberately **not**:

- a general-purpose AGI or fully autonomous agent
- a replacement for ERP, accounting, inventory, or booking systems
- a cloud-only SaaS (cloud is opt-in, not default)
- a self-modifying system without human approval
- a real-time transactional database
- a legal advisor (analytical assistance only; final review by qualified professionals)

If a feature request implies any of the above, it belongs in a
**downstream product** built on top of JAMES, not in JAMES itself.

---

## 3. Design Principles

| # | Principle | Operational meaning |
|---|---|---|
| 1 | **Local-first** | Default deployment is single-machine, no external network calls required for core path. |
| 2 | **Evidence-based reasoning** | Every answer must cite source documents and graph paths; ungrounded answers are flagged. |
| 3 | **Policy-aware retrieval** | RBAC + ABAC checks fire at retrieval, graph, and output stages — not just at the API edge. |
| 4 | **Auditability over performance** | When in doubt, log more. Audit log is append-only and never silently dropped. |
| 5 | **Human-supervised evolution** | Self-evolution **proposes**; humans **approve**. Deploy without approval is a bug. |
| 6 | **Sandboxed multimodality** | Image, audio, web content are untrusted inputs by default; extraction does not bypass policy. |
| 7 | **Composable boundaries** | Components communicate over typed interfaces, not shared globals. |

---

## 4. Component Layers

```
                ┌──────────────────────────────────────────┐
                │              Frontend / API              │
                └────────────────────┬─────────────────────┘
                                     │
                ┌────────────────────▼─────────────────────┐
                │         Auth + Policy Engine             │  ← RBAC/ABAC
                └────────────────────┬─────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
   ┌────▼─────┐               ┌──────▼────┐              ┌────────▼─────┐
   │  Query   │               │ Retrieval │              │     Tool     │
   │  Router  │               │ (Hybrid)  │              │    Router    │
   └────┬─────┘               └──────┬────┘              └────────┬─────┘
        │                            │                            │
        │                      ┌─────▼─────┐               ┌──────▼─────┐
        │                      │   Graph   │               │  Sandbox   │
        │                      │   Engine  │               │  (FS/Web)  │
        │                      └─────┬─────┘               └──────┬─────┘
        │                            │                            │
        └────────────┬───────────────┴────────────────────────────┘
                     │
              ┌──────▼──────┐                  ┌──────────────┐
              │  Reasoning  │                  │    Memory    │
              │    Loop     │ ◀──────────────▶ │ (Trust-gated)│
              └──────┬──────┘                  └──────────────┘
                     │
              ┌──────▼──────┐
              │   Output    │  ← PII + role mask
              │   Filter    │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Audit Log  │  (append-only, every decision)
              └─────────────┘
```

Each box is a **module with a typed interface**. No box reaches into
another's internals.

---

## 5. Trust Zones

| Zone | Source | Default trust | Hardening |
|---|---|---|---|
| User input (authenticated) | UI / API | **low** | sanitize, instruction-isolate |
| Internal documents | uploaded files, wiki | medium | content scan on ingest |
| Memory (system-tagged) | reasoning loop, system events | medium | role-locked writes |
| Memory (user-tagged) | feedback, comments | **low** until validated | trust score gate |
| Multimodal extraction | OCR, ASR, vision | **low** | content scan + isolate |
| Web search results | Tavily, DDG | **low** | content scan + isolate |
| Tool output | sandbox | medium | path/command allowlist |

Anything labeled **low** must pass `extract_data_only()` before
joining the LLM context.

---

## 6. Evolution Boundaries

Self-evolution is **disabled by default**. To enable:

1. Set `JAMES_ENABLE_EVOLUTION=1` (explicit opt-in)
2. Configure `JAMES_EVOLUTION_APPROVER_ROLE` (default: `admin`)
3. Patches flow: `feedback → candidate → 4-gate eval → approval → deploy → rollback-ready`

A patch reaches `deploy` only after a human with the approver role
explicitly approves it. Auto-approval is a bug, not a feature.

---

## 7. What JAMES is good at (and what it's not)

### Strong fits

- Q&A over private document corpora with role-restricted access
- Auditable reasoning over ontology-rich domains (legal, compliance, internal knowledge)
- Local-only environments with no acceptable cloud egress
- Domains where "why this answer?" matters as much as the answer

### Poor fits

- Real-time transactional systems (booking, POS, ledger)
- Workflow / approval engines (use a BPM; JAMES can be a node inside one)
- Pure summarization at scale (a smaller specialized pipeline is cheaper)
- General-purpose chat (the policy + audit overhead is wasted)

---

## 8. Versioning of this document

Architectural changes (new layer, trust-zone change, removal of
non-goal) require a PR to this file with an `architecture` label.
Module-internal changes do not.

---

## 9. 한국어 요약 (간단)

JAMES는 **로컬에서 실행되며, 추론 근거를 추적하고, 정책에 따라
권한을 검사하며, 사람이 승인한 변경만 적용되는** 지식 추론
시스템입니다. ERP·회계·예약 같은 **시스템 오브 레코드를 대체하지
않으며**, 그 위에 얹는 분석·검색·정책 레이어로 동작합니다.
자세한 영문 본문 참조.
