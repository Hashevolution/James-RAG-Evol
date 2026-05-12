---
title: "Building a Mini Palantir: A Local Graph-RAG Engine with Ontology, Security, and Self-Evolution (Alpha)"
published: false
description: "How I built PROJECT JAMES — a security-focused, locally-runnable Graph-RAG knowledge engine in Python, MIT-licensed. Inspired by Palantir's ontology approach, but 100% local and open source."
tags: rag, llm, python, opensource
cover_image:
canonical_url:
---

> **TL;DR**
> [PROJECT JAMES](https://github.com/Hashevolution/James-RAG-Evol) is a security-focused, locally-runnable Graph-RAG knowledge engine in Python. It combines an explicit 12-type ontology, 3-stage access control (RBAC + ABAC + instruction isolation), a self-evolution scaffold with audit log, and 100% local execution via Ollama. MIT-licensed, alpha v0.2.0, [OpenSSF Best Practices passing](https://www.bestpractices.dev/projects/12806).

## Why I built this

If you've ever wanted to point a local LLM at your own wiki, codebase, or document store, you've probably hit the same three walls I did:

1. **Cloud RAG services** want everything in their cloud — fine for prototypes, painful for anything sensitive.
2. **Self-hosted RAG frameworks** are usually one of: (a) too much infrastructure (Kubernetes-shaped), or (b) too few security primitives (no role separation, no audit trail).
3. **Most Graph-RAG implementations** treat the graph as a side feature on top of vectors. The graph rarely *participates* in the security boundary or the reasoning path.

I wanted something closer to **Palantir Foundry's mental model** — an explicit ontology, capability-token security, a full audit log — but compressed into something one person can run on a laptop, under MIT, without a cloud account.

That's what PROJECT JAMES is.

> Palantir® is a registered trademark of Palantir Technologies Inc. PROJECT JAMES is not affiliated with or endorsed by Palantir. "Mini Palantir" here is a descriptive comparison of the ontology-and-audit-log design pattern, not a product claim.

## What's in the box

Five things that rarely show up in the same Python repo:

| # | Capability | What it does |
|---|---|---|
| 1 | **Graph-RAG with ontology** | 12 relation types; relations carry semantic meaning beyond vector similarity |
| 2 | **3-stage security** | RBAC + ABAC + Instruction Isolation, applied at vector → graph → output |
| 3 | **Self-evolution scaffold** | feedback signals → patch proposals → 4-Gate validation → auto-rollback on bench regression, all with `approver_username` audit |
| 4 | **100% local** | Ollama-based, no cloud LLM dependency. Gemma `gemma2:2b` works on a laptop |
| 5 | **Explicit reasoning paths** | Every response surfaces the traversed graph paths so you can see *why* it answered that way |

## Architecture at a glance

```
[User query]
     ↓
[Security filter]      ← 31+ injection patterns + risky-coding hard-refuse
     ↓
[Query router]         ← chat / coding / retrieval / web_search
     ↓
[Hybrid search]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Graph engine]         ← DFS traversal + confidence pruning + sensitivity gating
     ↓
[Reasoning loop]       ← retrieve → expand → verify
     ↓
[Output filter]        ← PII masking + role-based content filter
     ↓
[Answer + reasoning path]
```

The graph is not a side index. Every retrieval that reaches the graph engine is gated by the user's role, the entity's sensitivity, and the ontology relation type. Removing the graph would break the security model — they're the same pipeline, not two pipelines glued together.

## A typical query lifecycle

```python
# Pseudocode for what happens behind /query/
def answer(query: str, user: User) -> Response:
    # 1. Pre-check: 31+ injection patterns, risky-coding hard-refuse
    if security_layer.pre_check(query) == BLOCK:
        return RESPONSE_BLOCKED  # byte-identical block message

    # 2. Hybrid retrieval — vector + BM25 + keyword + name match
    candidates = hybrid_search(query, top_k=10)

    # 3. Graph expansion — only visit entities the user can read
    paths = graph_engine.expand(
        seed_entities=candidates,
        role=user.role,                # RBAC
        sensitivity_ceiling=user.tier, # ABAC
        max_depth=3,
    )

    # 4. Reason over retrieved context (LLM call via router)
    answer, reasoning_trace = llm.reason(query, paths)

    # 5. Output filter — PII mask, role-based redact
    return output_filter.apply(answer, user.role)
```

The interesting part is step 3: **the graph traversal itself is access-controlled**, not just the final output. A `confidential` entity is never even *traversed* for an `employee` user, so the model never sees it. This means no jailbreak prompt can talk the LLM into leaking content it never had in the context.

## Security in depth

A few specific behaviors worth calling out:

### Hard-refuse for destructive commands

Queries that ask the model to produce filesystem-wide deletion, SQL `DROP DATABASE`, `git reset --hard`, etc. trigger a **byte-identical block message** *before* the LLM is ever called. The block message is the same string as the prompt-injection block, so an audit consumer cannot distinguish the two externally.

Patterns live in `core/security_layer.py::RISKY_CODING_REGEX`. Korean scope markers (`전체`, `모든`) are recognized too.

### Bcrypt password storage with transparent migration

Passwords are stored as `bcrypt$<hash>`. Pre-bcrypt SHA-256 hex digests from older deployments are accepted on input only and **rewritten to bcrypt on the next successful login** — no manual migration needed.

### Audit log everywhere

Every approved self-evolution patch is recorded with `approver_username`, `approver_role`, `approved_at`, and `approval_method` in the patch lifecycle JSONL. There is no auto-deploy path that bypasses this — if you bypass it, your fork stops being JAMES.

## Self-evolution scaffold

This is the part that scares people most when I describe it, so let me be precise about what it does and doesn't do:

**What it does:**

1. Collects feedback signals from `/query/` responses (thumbs-up/down, latency, hallucination flags)
2. Generates a candidate patch proposal (LLM-assisted)
3. Validates it through a 4-Gate pipeline:
   - **Gate 1**: Syntactic — parses, imports, no obvious explosions
   - **Gate 2**: Test suite — existing tests still pass
   - **Gate 3**: Bench eval — STEP 7 regression suite stays within tolerance
   - **Gate 4**: Human approval — `approver_username` required
4. Applies the patch with a known-good backup
5. **Auto-rollback** if Gate 3 detects a post-deploy regression

**What it does NOT do:**

- It does not auto-deploy without `approver_username`. If you set `JAMES_AUTO_APPROVE=1`, the server refuses to start unless `JAMES_DEV_MODE=1` is also set.
- It does not modify trust boundaries (auth, policy, sandbox) without an explicit `architecture` PR label.
- It does not touch security-critical files inside `core/security_layer.py` or `core/policy_engine.py` automatically.

The default deployment ships with `JAMES_ENABLE_EVOLUTION=0`. You have to opt in.

## What it's NOT — honest limitations

PROJECT JAMES is alpha. Here's what doesn't work yet:

- **Real-data validation is the v0.2 → v0.3 gate.** The internal STEP 7 suite passes (13 queries, security-block invariants, graph-paths bands), but the next gate is *a second user running the bench end-to-end on their own corpus*. That's a recruitment problem, not a coding problem, and I'm honest about it.
- **Multimodal retrieval is v0.3.** Video-ASR (Whisper) and image OCR (Tesseract, EasyOCR) are wired and work as ingestion paths, but multimodal retrieval as a first-class graph citizen is the next milestone.
- **Self-evolution is verified single-user.** It works on my machine. It has not been adversarially probed by a second user yet. Don't enable it in production.
- **Plugin API is v0.3.** Domain packs (legal, food, retail, travel) are deliberately blocked until v1.0 — see `docs/PLATFORM_READINESS.md` for the gate definitions.

## Trust signals

External validation that matters more than my self-assessment:

- **[OpenSSF Best Practices passing badge](https://www.bestpractices.dev/projects/12806)** (Tiered 111%, awarded 2026-05-11)
- **7 published GitHub Releases** through v0.2.0 (Foundation Hardening)
- **Static analysis** — ruff F-class rules (F821 + F541 + F401 + F841) enforced on every PR via GitHub Actions
- **Security tests** — 83-item adversarial regression suite (`james_security_test.py`) covering injection, path traversal, prompt injection, unsafe deserialization; 17-item password regression suite (`tests/test_password_bcrypt.py`)
- **Vulnerability disclosure** — GitHub Private Vulnerability Reporting enabled; backup channel documented in `SECURITY.md`
- **MIT-licensed**, with `CONTRIBUTING.md` test-policy gate

## Try it

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# Configure
cp .env.example .env
# Edit .env — set JAMES_API_KEY, JAMES_JWT_SECRET (32-char random)

# Install (Python 3.11+)
pip install -r requirements.txt

# Pull a model
ollama pull gemma2:2b   # 1.6 GB, runs on a laptop

# Start
python server_llmwiki.py
```

Then `http://localhost:8000`.

## Where this is going

Short-term roadmap:

- **v0.2.1**: Recruitment for the second-user real-data validation gate
- **v0.3.0**: Plugin API skeleton — `core/plugins/base.py` with 4 plugin interfaces, `JAMES_PLUGINS` loader, `packs/general/` dogfood, multi-instance `JAMES_WORKSPACE`
- **v1.0**: Production hardening + first domain packs (legal, retail, etc. only after this gate)

The bigger frame is in `docs/PLATFORM_READINESS.md`: PROJECT JAMES is a *mother platform* until v1.0. Domain forks happen after, not before. That's the discipline of the project.

## Feedback welcome

I'm specifically looking for:

1. **Adversarial review of the security model** — the boundary, the audit log, the hard-refuse policy. If you can break the role separation, please open a private advisory.
2. **A second-user corpus**. If you've got a wiki/document store you can point this at and run `scripts/bench.py --suite=step7 --check` on, I want to know what breaks.
3. **Critiques of the self-evolution scaffold** — particularly whether the 4-Gate is *enough* gating, or whether it needs another stage before Gate 4.

Repo: https://github.com/Hashevolution/James-RAG-Evol
Discussions: GitHub Issues
Security: GitHub Private Vulnerability Reporting (preferred), `karu-7@hanmail.net` (backup)

If you build something on top of it, I'd love to hear about it.

---

🤖 Honest disclosure: this article was drafted with AI assistance and edited by the author. The codebase, design decisions, and limitations described here are real and verifiable in the linked repository.
