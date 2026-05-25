# PROJECT JAMES

> **Local-first, auditable knowledge reasoning system** with explicit
> reasoning paths, a sources-aware knowledge graph, and self-evolution
> behind a human approval gate.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.4.0--alpha.2-blue.svg)](https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.4.0-alpha.2)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20372649.svg)](https://doi.org/10.5281/zenodo.20372649)

![PROJECT JAMES — 3D ontology graph visualizer](reports/promo-assets/screenshots/06-3d-graph.jpg)

[한국어 README](README.ko.md) · [🚀 처음 시작하시는 분 (10살도 따라할 수 있어요)](README.beginner.ko.md)

---

## Project Status: v0.3.0 — Platform Skeleton

Released **2026-05-17** after 190 PRs since v0.2.0 (1800+ tests).
The v0.2 → v0.3 gate is clear: all six Foundation Hardening axes
(architecture, eval, observability, security, controlled evolution,
real-data validation) passed; second-user validation closed
2026-05-13.

- **NOT production-ready** — operational maturity (HTTPS / SSO /
  multi-tenancy / backup CLI) is a v1.0 deliverable; see
  [SECURITY.md](SECURITY.md)
- Designed with security-first principles end to end
- Open to collaboration — external contributors sign a one-click CLA
  on their first PR (see [License](#license))

---

## Strategic frame: Mother Platform, not a single product

JAMES is **not building one vertical**. It is being hardened as a
"mother platform" from which domain packs (legal, food, retail,
travel, etc.) can branch off **only at v1.0**. Until then:

- No domain-specific features land in `core/`
- Every change is graded against the same six-dimension readiness
  framework (architecture / extension API / eval contract /
  operational maturity / security boundary / production proof)
- The plugin contract that future packs will be built against is
  being designed and stress-tested

See [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) for
the 6 dimensions, 4 gates (v0.2 / v0.3 / v0.4 / v1.0), and 3
branching forms (Domain Pack / Distribution / Vertical Product).

---

## What's Different

JAMES combines ideas that are rarely found together:

1. **Sources-aware Graph-RAG** — 12 typed relations carry semantic
   meaning beyond embeddings, and every relation carries
   `sources: [{doc_id, weight, role, ts}]` so deleting or modifying
   a document surgically updates only the affected derived knowledge
   (Knowledge Cascade A→E, v0.3.0)
2. **Cognitive Layer** — cross-encoder reranker (default ON), LLM
   query rewriter, reflection loop (draft → critique → revise),
   verification engine (security + fact check), and tool router.
   One `trace_id` reconstructs the full 8-stage reasoning sequence
   via `scripts/replay_trace.py`
3. **PolicyEngine as a layer, not a sprinkle** — single point of
   role / sensitivity decisions wired into retrieval, graph, output,
   and tools; removing it breaks 6+ modules (v0.2 Axis 4)
4. **Change Request primitive** — every write (wiki edits, workspace
   jobs, self-evolution patches) routes through propose → review →
   admin approval → atomic apply → audit row. No silent writes.
5. **Self-evolution behind a human gate** — feedback → candidate →
   bench eval → human approval → deploy → auto-rollback on
   regression. Every deployed patch has an `approver_username`
   audit row (v0.2 Axis 5).
6. **100% local** — runs on a laptop with Ollama

> Each feature is regression-tested against the STEP 7 13-query
> baseline + RAGAS metrics. PRs touching `core/{retrieval,graph,reasoning}`
> cannot land without bench numbers.

---

## Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) installed and running
- Min 16GB RAM (32GB+ recommended)
- (Optional) NVIDIA GPU for faster inference
- (Optional) Tavily API key for web search ([free 1k/month](https://tavily.com))

### Installation

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# Configure environment
cp .env.example .env
# Edit .env — set JAMES_API_KEY, JAMES_JWT_SECRET

# Install dependencies
pip install -r requirements.txt

# Start the server (admin wizard auto-recommends a model on first login)
python server_llmwiki.py
```

Open `http://localhost:8000/admin` — the admin wizard measures your
hardware and offers a one-click install of an appropriate Ollama
model. Then open `http://localhost:8000` for the chat UI.

---

## Architecture

```
[User Query]
     ↓
[Security Filter]      ← injection patterns + PolicyEngine pre-check
     ↓
[Query Router]         ← chat / coding / retrieval / web_search
     ↓
[Query Rewriter]       ← LLM rewrite (opt-in, JAMES_ENABLE_QUERY_REWRITE)
     ↓
[Hybrid Search]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Cross-Encoder Rerank] ← MiniLM-L-6-v2 (default ON; JAMES_DISABLE_RERANK=1 to disable)
     ↓
[Graph Engine]         ← DFS + sources-aware + sensitivity gating
     ↓
[Reasoning Loop]       ← retrieve → expand → reflect (opt-in) → verify (opt-in)
     ↓
[Tool Router]          ← read tools direct; write tools → Change Request
     ↓
[Output Filter]        ← PII masking + role-based filter
     ↓
[Answer + Reasoning Path + trace_id]
```

Every stage emits a row tied to one `trace_id`.
`scripts/replay_trace.py <trace_id>` reconstructs the full sequence
from `audit_log`. See [`docs/ARCHITECTURE.md §5.7`](docs/ARCHITECTURE.md)
for the Cognitive Layer design.

---

## Folder Structure

```
James-RAG-Evol/
├── core/
│   ├── reasoning/        retrieval/reflection/verification/tool router
│   ├── retrieval/        hybrid search + cross-encoder reranker + query rewriter
│   ├── memory/           long-term memory (db / conversation / summaries)
│   ├── plugins/          plugin contract surface (Provider Protocol)
│   ├── policy_engine.py  single point of role/sensitivity decisions
│   ├── change_request.py propose/review/approve write primitive
│   ├── cascade.py        file delete/modify → graph surgical update
│   ├── graph_editor.py   edge edit (replace/append/delete) + bidirectional sync
│   └── ...
├── eval/                 STEP 7 regression baseline + RAGAS suite
├── llm/                  LLM provider abstraction
├── tools/                Capability-token gated tool modules
├── frontend/             Web UI (HTML + JS)
├── processors/           File preprocessing
├── wiki/                 Knowledge graph (markdown + sources)
├── memory/               Long-term memory DB
├── workspace/            Change requests, patches, proposals
├── scripts/              bench.py / replay_trace.py / ops scripts
├── reports/              Eval results + promo assets
├── docs/                 ARCHITECTURE / PLATFORM_READINESS / ROADMAP / handovers
└── server_llmwiki.py     Main server entry point
```

---

## Security Approach

JAMES treats security as a **design principle, not a feature**:

- **3-stage access control**: Vector → Graph → Output
- **RBAC** (4 roles) + **ABAC** (4 sensitivity levels)
- **Instruction isolation**: separates commands from data
- **JWT auth** + rate limiting + full audit log
- **Sandboxed execution** (for tool calls)

> Realistic note: synthetic-data testing differs from adversarial production testing. See [SECURITY.md](SECURITY.md).

---

## Current Features

| Feature | Status |
|---------|--------|
| Hybrid Search (Vector + BM25 + keyword + name) | Working |
| Cross-encoder reranker (MiniLM-L-6-v2) | Working — default ON (v0.3) |
| LLM query rewriter | Opt-in (v0.3) |
| Sources-aware Graph-RAG (Knowledge Cascade A→E) | Working (v0.3) |
| PolicyEngine (RBAC + ABAC + capability tokens) | Working (v0.2 Axis 4) |
| Reflection loop (draft → critique → revise) | Opt-in (v0.3) |
| Verification engine (security + fact check) | Opt-in (v0.3) |
| Tool router (read direct, write → Change Request) | Working (v0.3) |
| Change Request primitive (wiki + jobs + patches) | Working (v0.2.x + v0.3) |
| Self-evolution (human approval + auto-rollback) | Working (v0.2 Axis 5) |
| Trace replay (one `trace_id` → full reasoning seq) | Working (v0.3) |
| Multimodal (image/video/audio + OCR-poison quarantine) | Working (v0.2 Axis 4) |
| Web search (Tavily / DuckDuckGo fallback) | Working |
| Multi-LLM routing (Ollama + Claude CLI backends) | Working |
| STEP 7 regression baseline + RAGAS | Working (v0.2 Axis 2) |
| Real-data validation (second-user gate) | Passed 2026-05-13 |

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **LLM**: Ollama (Gemma, DeepSeek-Coder, LLaVA)
- **Vector DB**: ChromaDB
- **Embedding**: Sentence-Transformers (MiniLM)
- **Search**: BM25 + Vector hybrid
- **Web search**: Tavily (primary) + DuckDuckGo (fallback)
- **Auth**: JWT (python-jose)
- **Storage**: SQLite + markdown wiki

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) and [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md).
Summary:

- **v0.1**: Core engine + scaffolding (released)
- **v0.2**: Foundation Hardening — 6 axes (closed 2026-05-13)
- **v0.3**: Platform Skeleton — Cognitive Layer + Knowledge Cascade
  + Change Request primitive (current; released 2026-05-17)
- **v0.4**: First Domain Pilot — one pack + one external customer,
  6-month no-regression
- **v1.0**: Production-Grade Mother — HTTPS / SSO / multi-tenancy /
  SOC2 readiness; external developers can publish their own packs

Multi-agent specialists, optional Neo4j backend, OpenAI-compatible
API, streaming responses, and federation are speculative Beyond
v1.0 work — see [`ROADMAP.md` §Beyond v1.0](ROADMAP.md).

---

## Contributing

Welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Priority areas:
- Documentation, examples, translations
- Bug fixes, test coverage
- New tool integrations and LLM provider support

---

## License

**Licensed under the MIT License.** Use freely. See [LICENSE](LICENSE).

External contributors sign a one-click
[Contributor License Agreement](docs/legal/CLA.md) on their first pull
request (CLA Assistant). One signature covers all future contributions
to the project. See [CONTRIBUTING.md](CONTRIBUTING.md#license--contributor-license-agreement-cla)
for the full §License & CLA section, and
[docs/legal/non-cla-contributions.md](docs/legal/non-cla-contributions.md)
for contribution paths that don't require signing.

A full inventory of third-party dependency licenses is available in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Acknowledgements

Inspired by:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir-style ontology approaches
- Architectural direction, Platform Readiness gates, and roadmap framing are discussed with LEO, continuing collaborator on this work, and that's how we intend to keep it.

---

## Disclaimer

**Use at your own risk.** This is research code. No guarantees regarding sensitive-data handling or production security without further hardening.
