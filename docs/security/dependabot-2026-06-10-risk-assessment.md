# Dependabot risk assessment — 2026-06-10

Open alerts on `main` at the time of this assessment:

| # | Package | Severity | CVE | Manifest | Disposition |
|---|---|---|---|---|---|
| 16 | starlette | medium | CVE-2026-48710 | `requirements.txt` | **Fix** (floor pin → 1.0.1) |
| 15 | starlette | medium | CVE-2026-48710 | `requirements_pinned.txt` | **Fix** (pin 1.0.0 → 1.0.1) |
| 14 | chromadb | critical | CVE-2026-45829 | `requirements.txt` | **Risk-accept** (not exploitable; awaiting upstream patch) |
| 13 | chromadb | critical | CVE-2026-45829 | `requirements_pinned.txt` | **Risk-accept** (same) |

Two distinct advisories; each fires once per manifest.

---

## 1. starlette — CVE-2026-48710 (badhost)

**GHSA-86qp-5c8j-p5mr.** Affected versions (≤ 1.0.0) did not validate
the HTTP `Host` header before reconstructing `request.url`. A
malformed `Host` such as `example.com/abc?bar=` shifts the
path/query boundary during URL re-parsing, so
`request.url.path` becomes `/abc` even when routing dispatched to
the real path `/foo`. Middleware that gates path prefixes on
`request.url.path` (rather than the raw ASGI scope path) can be
bypassed.

### JAMES exposure

Direct dependency surface — FastAPI / Uvicorn ASGI app
(`server_llmwiki.py`). The repository does not use the affected
attribute in security-critical decisions today (a quick grep finds
no middleware that gates on `request.url.path`), but the
deployment runs an ASGI app behind no consistently-configured
reverse-proxy normalisation, so the latent risk warrants the
mechanical fix even at the medium-severity level.

### Disposition

**Fix.** Patched in starlette 1.0.1. Pulled in transitively by
FastAPI; explicit floor pin added in `requirements.txt` mirroring
the existing pattern for urllib3 / idna / python-multipart so a
fresh install with a stale wheel cache cannot regress us.
`requirements_pinned.txt` bumped to 1.0.1.

---

## 2. chromadb — CVE-2026-45829 (chromatoast)

**GHSA-f4j7-r4q5-qw2c.** Pre-authentication remote code execution
in the ChromaDB HTTP server. An unauthenticated attacker POSTs a
collection-creation request to
`/api/v2/tenants/{tenant}/databases/{db}/collections` whose body
points at a malicious model repository with `trust_remote_code=true`
set; the server then executes attacker-controlled Python during
model loading. Vulnerable range: chromadb 1.0.0 – 1.5.9. **No
patched version is published as of 2026-06-10.** Upstream tracker:
`chroma-core/chroma#6717`.

### JAMES exposure — risk-accept rationale

The CVE attack surface is **not reachable** in this deployment:

1. **No HTTP server.** `core/vector_store.py` constructs the client
   as `chromadb.PersistentClient(path=self.db_path)` (line 75) —
   the embedded local mode. The chromadb HTTP server module
   (which exposes the vulnerable `/api/v2/.../collections`
   endpoint) is not started by any JAMES code path. A repo-wide
   grep for `chromadb.HttpClient` / `chromadb.AsyncHttpClient` /
   `chroma_server` returns zero matches.
2. **No trust_remote_code call sites.** Grep for
   `trust_remote_code` across the codebase returns zero matches.
   No JAMES module passes user-controlled values into a chromadb
   collection-construction payload that could enable the gadget.
3. **Local-first architecture.** CLAUDE.md headline ("A local-first,
   auditable knowledge reasoning system") and `docs/ARCHITECTURE.md`
   non-goals exclude multi-tenant network surface as a v0.4 target.
   v0.5 enterprise-internal-knowledge pilot (the candidate
   v0.5 domain, gated) does not change this — the chromadb client
   stays embedded; ingestion / retrieval flow through the JAMES
   API surface (`routes/`), not chromadb's own HTTP layer.

The vulnerable code path exists in the installed library but is
unreferenced from JAMES call sites. An attacker would need to
either (a) compromise the JAMES Python process directly (a higher
bar than the CVE describes), or (b) get JAMES code to import and
start chromadb's HTTP server with a user-controlled payload (no
such code path exists, and adding one would be a separate review).

### Disposition

**Risk-accept until upstream patch ships.** Concrete action:

- Floor in `requirements.txt` stays at `chromadb>=0.4.22`. No
  meaningful upper bound to add (no patched version exists; the
  pre-1.0 versions are missing features the project needs).
- `requirements_pinned.txt` stays at `chromadb==1.5.7`.
- Track `chroma-core/chroma#6717`; bump on first patched release.
- **Re-evaluation trigger**: any PR that introduces
  `chromadb.HttpClient`, `chromadb.AsyncHttpClient`, a
  `chroma_server` import, or anything that lets external input
  influence collection-creation payloads MUST revisit this
  assessment in the same PR. The chromadb advisory becomes live
  exposure the moment any of those land.
- Dependabot alerts #13 and #14 will be dismissed as
  `not_used` with this document URL as the comment, following the
  review's guidance to keep the alerts queue actionable.

---

## 3. Auditability note

This assessment lives in the repository at
`docs/security/dependabot-2026-06-10-risk-assessment.md` and is
referenced from the relevant requirements.txt comment block. The
goal is the property described in
`docs/research/project-direction-review-2026-06-09.md` R1 — that
JAMES's moat axis is **replayable audit**, and risk-acceptance
decisions on dependencies are exactly the kind of thing that has
to be reproducible from the repo, not from operator memory.
