# PROJECT JAMES

> **Security-focused, locally-runnable Graph-RAG knowledge engine**
> with explicit reasoning paths and self-evolution scaffolding.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.1.0--alpha-orange.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)

![PROJECT JAMES — 3D ontology graph visualizer](reports/promo-assets/screenshots/06-3d-graph.jpg)

[한국어 README](README.ko.md) · [🚀 처음 시작하시는 분 (10살도 따라할 수 있어요)](README.beginner.ko.md)

---

## Project Status: v0.1.0 (alpha / research stage)

This is an **early-stage, actively-researched project**.
The core engine works, but:

- Designed and tested with security-first principles
- **NOT production-ready** — see [SECURITY.md](SECURITY.md)
- Many features are scaffolded — real-data testing in progress
- Open to collaboration and feedback

---

## What's Different

JAMES combines five ideas that are rarely found together:

1. **Graph-RAG with ontology** — relations carry semantic meaning beyond embeddings
2. **Built-in security layer** — RBAC + ABAC + instruction isolation
3. **Self-evolution scaffold** — feedback signals → patch proposals
4. **Personality system** — 11 tunable traits influence responses
5. **100% local** — runs on a laptop with Ollama

> Honest disclosure: each feature is a *working prototype*, not a finished product. Real-data tuning is ongoing.

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

# Pull a small LLM
ollama pull gemma2:2b

# Start the server
python server_llmwiki.py
```

Open `http://localhost:8000`

---

## Architecture

```
[User Query]
     ↓
[Security Filter]      ← 31+ injection patterns
     ↓
[Query Router]         ← chat / coding / retrieval / web_search
     ↓
[Hybrid Search]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Graph Engine]         ← DFS + confidence + sensitivity gating
     ↓
[Reasoning Loop]       ← retrieve → expand → verify
     ↓
[Output Filter]        ← PII masking + role-based filter
     ↓
[Answer + Reasoning Path]
```

---

## Folder Structure

```
James-RAG-Evol/
├── core/             User interface layer + LLM clients
├── llm/              LLM abstraction (providers/)
├── tools/            Feature modules (8 subfolders)
├── frontend/         Web UI (HTML + JS)
├── processors/       File preprocessing
├── utils/            Utilities
├── wiki/             Knowledge graph (markdown-based)
├── memory/           Long-term memory DB
├── workspace/        Runtime data (backups, patches, proposals)
├── scripts/          Operational scripts
├── reports/          Test results
└── server_llmwiki.py Main server entry point
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
| Hybrid Search (Vector + BM25) | Working |
| Graph-RAG with ontology | Working |
| Security layer (RBAC/ABAC) | Working |
| Multimodal (image/video) | Scaffolded |
| Self-evolution | Scaffolded (needs data) |
| Web search integration | Working (Tavily/DDG) |
| Multi-LLM routing | Working |
| Real-data validation | Pending |

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

See [ROADMAP.md](ROADMAP.md). Summary:

- **v0.1** (current): Core engine + scaffolding
- **v0.2**: Real-data validation + polish
- **v0.3**: Multi-agent + Neo4j option
- **v1.0**: Production hardening

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

A full inventory of third-party dependency licenses is available in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

---

## Acknowledgements

Inspired by:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir-style ontology approaches

---

## Disclaimer

**Use at your own risk.** This is research code. No guarantees regarding sensitive-data handling or production security without further hardening.
