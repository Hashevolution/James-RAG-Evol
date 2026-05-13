# dev.to — Gemma 4 Challenge submission

> Published: 2026-05-12
> URL: https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk
> Challenge: [Gemma 4 Challenge: Build with Gemma 4](https://dev.to/challenges/google-gemma-2026-05-06)
> Track: Build with Gemma 4 (prize $500 × 5 winners)
> Submission deadline: 2026-05-24 11:59 PM PDT
> Winners announced: 2026-06-04
> Tags: `devchallenge`, `gemmachallenge`, `gemma`, `rag`
> Title: Building a Mini Palantir on gemma4:e4b — 128K Context Lets the Graph Actually Be Graph-RAG

## Why this submission was written

The first dev.to article ([Mini Palantir intro](https://dev.to/hashevolution/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-1914)) was a general project introduction. It did not foreground the **"intentional and effective use of Gemma 4"** criterion that the challenge weights first.

This second article is the actual challenge submission. It tackles the four challenge criteria head-on:

1. **Intentional and effective use of Gemma 4** — Section "How I Used Gemma 4" explains why E4B (over E2B / 31B Dense / 26B MoE), why 128K context is the deciding factor for Graph-RAG, and how native function calling + reasoning mode wire into `llm/router` and `core/security_layer`.
2. **Technical implementation and code quality** — Section "Code" links the OpenSSF passing badge, the ruff F-class CI gate, the 83-item security regression suite, and the 17-item password regression suite.
3. **Creativity and originality** — Mini Palantir framing + the design claim that *the graph traversal is the security boundary, not two pipelines glued together*.
4. **Usability and UX** — One-liner install, reasoning paths surfaced per response, 3D ontology visualizer.

## Submission body (preserved for archive)

````markdown
*This is a submission for the [Gemma 4 Challenge: Build with Gemma 4](https://dev.to/challenges/google-gemma-2026-05-06)*

## What I Built

**PROJECT JAMES** — a security-focused, locally-runnable **Graph-RAG knowledge engine** in Python, MIT-licensed. Think "Mini Palantir Foundry, but MIT, runs on a laptop, no cloud":

- **Graph-RAG with 12-type ontology** — relations carry semantic meaning, not just vector similarity
- **3-stage access control** — RBAC + ABAC + instruction isolation (vector → graph → output)
- **Self-evolution scaffold** — feedback → patch → 4-Gate validation → auto-rollback on bench regression, with `approver_username` audit
- **100% local** via Ollama — no cloud LLM dependency
- **Explicit reasoning paths** surfaced in every response

The problem it solves: most local RAG projects pick *one* of "ontology-aware retrieval", "role-based security", or "self-evolution audit logs". JAMES combines all three because for a 1-person knowledge engine, **security and reasoning have to be the same pipeline, not two pipelines glued together** — the graph traversal *is* the security boundary. A `confidential` entity is never visited for an `employee` role, so the model never sees it. No jailbreak prompt can leak content it never had in the context.

> Palantir® is a registered trademark of Palantir Technologies Inc. PROJECT JAMES is not affiliated. "Mini Palantir" is a descriptive comparison of the ontology-and-audit-log design pattern.

## Demo

Self-hosted, alpha v0.2.0. Quick-start (≈ 5 minutes on a laptop):

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol
cp .env.example .env   # set JAMES_API_KEY, JAMES_JWT_SECRET (32+ char)
pip install -r requirements.txt
ollama pull gemma4:e4b   # ~2.5 GB
python server_llmwiki.py
```

→ `http://localhost:8000` — chat UI + admin dashboard + 3D ontology graph visualizer.

**Key endpoints worth poking at:**

- `POST /query/` — natural-language query, returns answer + traversed `graph_paths` strings
- `GET /admin/graph` — 3D force-directed ontology visualizer (Three.js)
- `GET /admin/patch/audit` — operator-facing audit log over the patch lifecycle
- `GET /admin/trace/{trace_id}` — full pipeline replay for any query (auth → retrieve → graph → tool → answer → complete stages, with per-stage latency)

**Background article** with architecture diagram and limitations: [dev.to write-up](https://dev.to/hashevolution/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-1914).

## Code

**Repository**: [`Hashevolution/James-RAG-Evol`](https://github.com/Hashevolution/James-RAG-Evol) — MIT

Code-quality and security signals for reviewers:

- **[OpenSSF Best Practices passing badge](https://www.bestpractices.dev/projects/12806)** (Tiered 111%, awarded 2026-05-11)
- 7 published GitHub Releases through v0.2.0 (Foundation Hardening, 5/6 axes engineering-complete)
- `ruff.toml` enforces F821 / F541 / F401 / F841 on every PR via GitHub Actions
- 83-item security regression suite (`james_security_test.py`): injection, path traversal, prompt injection, unsafe deserialization
- 17-item password regression suite (`tests/test_password_bcrypt.py`)
- bcrypt password storage with transparent SHA-256 → bcrypt migration on first login (PR #173)
- GitHub Private Vulnerability Reporting enabled
- Module-size gate: no file under `core/` exceeds 20 KB

Where Gemma 4 lives in the codebase:

- `config.py:139` — `GEMMA_MODEL = os.environ.get("JAMES_LLM_MODEL", "gemma4:e4b")`
- `llm/router.py` — task-aware dispatch (`task_type=extract / classify / general / coding / vision`); every production call site declares its task
- `core/reasoning/pipeline.py` — RAG retrieval pipeline with explicit `graph_paths` argument carried to the model
- `core/security_layer.py::pre_check` — risky-coding hard-refuse, byte-identical to prompt-injection block

## How I Used Gemma 4

### Model choice: **E4B** (gemma4:e4b)

Three Gemma 4 variants were available. The choice was forced by single-user, laptop-class constraints:

| Variant | Considered for | Outcome |
|---|---|---|
| **31B Dense** | Server-grade reasoning depth | ❌ Doesn't fit 16 GB RAM; single-user means no throughput need |
| **26B MoE** | Long-context advanced reasoning | ❌ Expert-routing overhead helps batch workloads; single-user has batch size 1 |
| **E4B (4B effective)** ⭐ | Edge variant: 4B params, native multimodal, 128K context | ✅ Fits 8 GB GPU or CPU-only laptop, gives the 128K window I need, supports vision for v0.3 multimodal track |
| E2B (2B effective) | Smaller still | ⚠️ Tested as fallback; reasoning depth too low for graph synthesis at depth 3+ |

**The deciding factor was the 128K context window — not parameter count.** Here's why.

### Why 128K context matters for Graph-RAG specifically

A typical RAG pipeline retrieves top-k chunks and stuffs them into the prompt. Graph-RAG retrieves chunks *and* the relations between them — and the relations carry semantic meaning I want the model to reason over, not see as decoration.

A depth-3 query against my 161-entity wiki produces a context like:

```
[retrieved chunk 1]  (entity A, sensitivity=public)
[retrieved chunk 2]  (entity B, sensitivity=public)
...
[graph_path]  A --[CAUSES]--> X --[REQUIRES]--> Y --[BLOCKED_BY]--> B
[graph_path]  A --[KNOWN_AS]--> A' --[REFERENCES]--> C
[ontology]    relation 'CAUSES'      directed=true  weight=0.85
[ontology]    relation 'BLOCKED_BY'  directed=true  weight=0.92
[instruction] use graph_paths to constrain the answer
```

For real queries at depth 3 this routinely hits **~40K tokens**. With a 32K-window model (most older OSS LLMs), I'd be silently truncating the graph paths — meaning the model defaults to vector-only reasoning and the ontology becomes decoration. **With Gemma 4's 128K window the full retrieval result fits in one shot** and the model actually reasons over the relation labels.

This is the property I designed the rest of the system around. Without 128K, the "Graph-RAG with ontology" claim collapses into "RAG with extra metadata".

### Native function calling → router `task_type`

Gemma 4's native function calling underpins `llm/router.py::call_router`, which makes every call declare its purpose:

```python
call_router(prompt, task_type="extract",  **kwargs)   # entity extraction
call_router(prompt, task_type="classify", **kwargs)   # intent classification
call_router(prompt, task_type="general",  **kwargs)   # chat answer
call_router(prompt, task_type="coding",   **kwargs)   # code generation
```

The same router can route `task_type=coding` to a 32B Coder and `task_type=general` to Gemma 4 — but **default for general reasoning is `gemma4:e4b`** because the 128K window dominates everything else at this scale.

### Reasoning mode → security policy

Gemma 4's chain-of-thought reasoning is what makes the **risky-coding hard-refuse** policy actually usable. The block fires *before* the LLM is called for clear destructive patterns (regex match in `core/security_layer.py::RISKY_CODING_REGEX`), but borderline queries pass `pre_check` and the model itself classifies them:

- Query asks how to perform destructive command on a target → refuse, byte-identical block message
- Query asks about command syntax (documentation) → answer normally

Without a reasoning-capable model, this distinction collapses into "block everything" (false positives) or "answer everything" (security holes). Gemma 4's reasoning is what threads the needle.

### What I didn't use yet

- **Native multimodal retrieval** — Image OCR (Tesseract, EasyOCR) and video ASR (Whisper) are wired as *ingestion* paths, but treating images/audio as first-class graph citizens during retrieval is the v0.3 deliverable. Gemma 4's native vision is ready and waiting.
- **31B Dense or MoE for server deployment** — JAMES stays single-machine until v1.0 by design (`docs/PLATFORM_READINESS.md`). When multi-tenancy lands, swapping `JAMES_LLM_MODEL=gemma4:31b` is a one-env-var change — the router already abstracts it.

### One-line summary of the model fit

> 128K context is what lets Graph-RAG *be* graph-RAG instead of "RAG with extra metadata". gemma4:e4b is the smallest variant that ships it at a footprint a laptop can hold.

---

**Looking for**: adversarial review of the security model, a second user willing to run `scripts/bench.py --suite=step7` on their own corpus (that's the v0.2 → v0.3 gate), and critiques of the self-evolution 4-Gate.

GitHub: https://github.com/Hashevolution/James-RAG-Evol
OpenSSF: https://www.bestpractices.dev/projects/12806

🤖 Honest disclosure: this submission was drafted with AI assistance and edited by the author. The codebase, design decisions, model-choice rationale, and limitations described above are real and verifiable in the linked repository.
````

## Post-publication actions (planned)

- Add a first comment on the dev.to article to seed adversarial-review discussion (model-choice rationale, 128K context bet, alternative variants)
- Quote-tweet from the existing X/Twitter English thread with the Gemma 4 challenge URL
- Update `launch-tracker.md` social-posts table with this submission

## Monitoring

- **2026-05-24 (deadline)** — must be live by 11:59 PM PDT
- **2026-06-04** — winners announced
- During the next two weeks, response speed to comments matters for the judging-tie-break rule (reactions count when judge scores tie)
