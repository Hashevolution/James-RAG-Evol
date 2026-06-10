"""RAB JAMES adapter — wires JAMES's audit-native plumbing to the RAB
driver contract (SPEC v0.1.1).

Design (locked by `docs/research/r1-4-preregistration-2026-06-10.md`):

* **Workspace-isolated**. The adapter is constructed with a dedicated
  workspace directory (default = a fresh tmp). Every artifact (audit
  log JSONL, lifecycle-event sqlite, optional vector store) lives
  under that directory. Production audit.db is never touched. This
  satisfies the pre-reg's "격리 `JAMES_WORKSPACE` 의무".

* **RAB canonical log = JSONL** written *by the adapter* at the moment
  each op runs. This IS the SPEC §1 audit log — JSONL is the canonical
  interchange the scorer reads. The mapping table is trivial (native
  type == canonical type) because the adapter chooses RAB-canonical
  type names up front; that is what "audit-native" means.

* **JAMES real-path bridge**: every SUPERSEDE op also calls
  ``core.lifecycle.replay_audit.emit_lifecycle_event(
  EVT_SUPERSEDE_EDGE_CREATED, ...)`` with a workspace-scoped
  ``JAMES_AUDIT_DB``. This exercises the actual JAMES production code
  path that operators ship today (T5.A). A test cross-verifies that
  the JSONL SUPERSEDE rows are 1:1 with the lifecycle-event sqlite
  rows, and that ``reconstruct_graph_at(t)`` reproduces the same
  supersede-chain subset our JSONL replay reproduces.

* **Replay** (``replay_at``) is a pure fold over the **exported JSONL
  log only** (SPEC §6.2 — no live-state reads). It is independent of
  ``reconstruct_graph_at``; we additionally verify the two agree on
  supersede-chain shape in the test suite.

* **Snapshot** returns the full live state in SPEC §2.4 shape:
  ``entities`` = sorted live docs, ``edges`` = supersede edges.

* **Query** has two modes (selected at construction):
    - ``use_engine=False`` (default for CI / determinism): token-overlap
      retrieval over titles + first 200 chars of body. No LLM call.
      Citations = retrieved doc_ids.
    - ``use_engine=True``: routes through ``core.reasoning.engine.
      ReasoningEngine`` and ``core.vector_store.VectorStore`` (LLM +
      embedding model required). Citations parsed from the engine
      response's ``sources``.

  Both modes emit the same RAB-canonical RETRIEVE → SYNTH → ANSWER
  provenance chain.

Honesty notes (the SPEC §6.5 clause applies):

* JAMES will score AC/RF/PC high because the adapter IS audit-native by
  design — that's the demonstration, not a discovery.
* The headline is the gap table across all SUTs, not JAMES's score
  alone (pre-reg §2.1).
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JamesAdapter:

    # JAMES adapter chooses RAB-canonical type names directly — the
    # mapping table is the identity map. That IS what audit-native
    # means: the system speaks the canonical taxonomy natively.
    MAPPING_TABLE: Dict[str, str] = {
        "INGEST":    "INGEST",
        "UPDATE":    "UPDATE",
        "SUPERSEDE": "SUPERSEDE",
        "DELETE":    "DELETE",
        "RETRIEVE":  "RETRIEVE",
        "SYNTH":     "SYNTH",
        "ANSWER":    "ANSWER",
    }

    def __init__(
        self,
        *,
        workspace: Optional[Path] = None,
        use_engine: bool = False,
    ):
        if workspace is None:
            workspace = Path(tempfile.mkdtemp(prefix="rab_james_"))
        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        self._workspace = workspace
        self._log_path = workspace / "rab_audit_log.jsonl"
        self._lifecycle_db = workspace / "lifecycle.db"
        self._use_engine = use_engine

        # Workspace-scoped lifecycle DB. Setting the env var BEFORE the
        # first emit_lifecycle_event call routes lifecycle events into
        # the workspace SQLite (pre-reg "production 무접촉").
        os.environ["JAMES_AUDIT_DB"] = str(self._lifecycle_db)
        self._init_lifecycle_db()

        # In-memory state model — drives snapshot() and is also used by
        # the deterministic retrieval mode. (For use_engine mode the
        # VectorStore is the source of truth for retrieval, but the
        # state model still drives snapshot() so the canonical shape
        # is consistent.)
        self._docs:  Dict[str, dict] = {}
        self._edges: List[dict]      = []
        self._seq:   int             = 0

        # Engine-mode lazy init.
        self._engine = None
        self._vector_store = None

        # Truncate any stale log under this workspace.
        if self._log_path.exists():
            self._log_path.unlink()

    # ── workspace lifecycle DB bootstrap ─────────────────────────

    def _init_lifecycle_db(self) -> None:
        """Create the minimum audit_log schema T5 emit_lifecycle_event
        expects, in the workspace SQLite."""
        import sqlite3
        conn = sqlite3.connect(self._lifecycle_db)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT,
                    user_role       TEXT,
                    endpoint        TEXT,
                    query           TEXT,
                    answer          TEXT,
                    graph_paths     TEXT,
                    blocked         INTEGER,
                    security_event  TEXT,
                    elapsed_sec     REAL,
                    ip_address      TEXT,
                    event_type      TEXT,
                    event_payload   TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ── internal: audit emission ────────────────────────────────

    def _emit(
        self,
        canonical_type: str,
        payload: Dict[str, Any],
        parent_id: Optional[str] = None,
    ) -> str:
        """Write one RAB-canonical row to the JSONL audit log."""
        self._seq += 1
        eid = f"jms-{self._seq:05d}"
        row = {
            "event_id":    eid,
            "ts":          _now_iso(),
            "event_type":  canonical_type,
            "parent_id":   parent_id,
            "inputs_hash": self._stable_hash(payload),
            "payload":     payload,
        }
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")
        return eid

    @staticmethod
    def _stable_hash(obj: Dict[str, Any]) -> str:
        """SUT-chosen stable hash per SPEC §1. Deterministic over the
        same payload."""
        import hashlib
        canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # ── engine mode lazy init ────────────────────────────────────

    def _ensure_engine(self):
        if self._engine is None:
            os.environ["JAMES_WORKSPACE"] = str(self._workspace)
            from core.reasoning.engine import ReasoningEngine
            from core.vector_store import VectorStore
            self._vector_store = VectorStore()
            self._engine = ReasoningEngine()
        return self._engine

    # ── mutating ops ────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title, "text": text}
        if self._use_engine:
            self._ensure_engine()
            self._vector_store.add_documents_with_meta(
                [f"{title}\n{text}" if title else text],
                source=doc_id,
                metadata={"category": "rab", "source_type": "prod"},
            )
        self._emit("INGEST", {"doc_id": doc_id, "title": title,
                              "text": text})

    def update(self, doc_id: str, title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title, "text": text}
        if self._use_engine:
            self._ensure_engine()
            self._vector_store.add_documents_with_meta(
                [f"{title}\n{text}" if title else text],
                source=doc_id,
                metadata={"category": "rab", "source_type": "prod"},
            )
        self._emit("UPDATE", {"doc_id": doc_id, "title": title,
                              "text": text})

    def supersede(self, old_doc_id: str, doc_id: str,
                  title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title, "text": text}
        edge = {"src": doc_id, "dst": old_doc_id, "type": "SUPERSEDE"}
        self._edges.append(edge)
        if self._use_engine:
            self._ensure_engine()
            self._vector_store.add_documents_with_meta(
                [f"{title}\n{text}" if title else text],
                source=doc_id,
                metadata={"category": "rab", "source_type": "prod"},
            )

        # Real JAMES code path: emit a lifecycle event into the
        # workspace-scoped audit.db. reconstruct_graph_at(t) will fold
        # this. The RAB scorer reads the JSONL we write below; the
        # lifecycle event is for the cross-verification test.
        try:
            from core.lifecycle.replay_audit import (
                EVT_SUPERSEDE_EDGE_CREATED,
                emit_lifecycle_event,
            )
            emit_lifecycle_event(
                EVT_SUPERSEDE_EDGE_CREATED,
                {
                    "new_edge_id": f"rab-edge-{self._seq + 1:05d}",
                    "head_id":     old_doc_id,
                    "src":         doc_id,
                    "dst":         old_doc_id,
                    "validity":    {"from": _now_iso(), "to": None},
                },
            )
        except Exception:
            # Lifecycle bridge is informational here — the RAB log is
            # the JSONL the scorer reads. Don't fail the op if the
            # lifecycle DB write hiccups.
            pass

        self._emit("SUPERSEDE", {"doc_id": doc_id,
                                 "old_doc_id": old_doc_id,
                                 "title": title, "text": text})

    def delete(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        # Edges referencing the deleted doc remain — history is data,
        # same convention as reference adapter. The supersede-chain
        # graph is append-only.
        if self._use_engine and self._vector_store is not None:
            try:
                self._vector_store.delete_by_source(doc_id)
            except Exception:
                pass
        self._emit("DELETE", {"doc_id": doc_id})

    # ── query (RETRIEVE → SYNTH → ANSWER provenance chain) ──────

    def query(self, q: str) -> dict:
        if self._use_engine:
            return self._query_engine(q)
        return self._query_deterministic(q)

    def _query_deterministic(self, q: str) -> dict:
        """Token-overlap retrieval over title + first 200 chars body."""
        terms = {w.lower().strip("?.,") for w in q.split() if len(w) > 3}
        hits: List[str] = []
        for doc_id, meta in sorted(self._docs.items()):
            haystack = (meta["title"] + " "
                        + meta["text"][:200]).lower().split()
            if terms & set(haystack):
                hits.append(doc_id)
            if len(hits) >= 3:
                break

        rid = self._emit("RETRIEVE", {"q": q, "doc_ids": hits})
        sid = self._emit("SYNTH", {"q": q, "n_docs": len(hits)},
                         parent_id=rid)
        answer = (f"Based on {', '.join(hits)}: deterministic stub."
                  if hits else "Insufficient information.")
        self._emit("ANSWER", {"q": q, "answer": answer,
                              "citations": list(hits)},
                   parent_id=sid)
        return {"answer": answer, "citations": list(hits)}

    def _query_engine(self, q: str) -> dict:
        """Real ReasoningEngine path. Citations parsed from sources."""
        engine = self._ensure_engine()
        result = engine.query(q, source_type="prod",
                              session_id=f"rab-{uuid.uuid4().hex[:8]}")
        sources = result.get("sources") or []
        citations = []
        for s in sources:
            if isinstance(s, dict):
                sid = s.get("source") or s.get("doc_id") or s.get("id")
                if sid:
                    citations.append(str(sid))
            elif isinstance(s, str):
                citations.append(s)

        rid = self._emit("RETRIEVE", {"q": q, "doc_ids": list(citations)})
        sid = self._emit("SYNTH", {"q": q, "n_docs": len(citations)},
                         parent_id=rid)
        answer = str(result.get("answer", ""))
        self._emit("ANSWER", {"q": q, "answer": answer,
                              "citations": list(citations)},
                   parent_id=sid)
        return {"answer": answer, "citations": list(citations)}

    # ── state + replay ──────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(self._docs.items())],
            "edges": [dict(e) for e in self._edges],
        }

    def export_log(self) -> List[dict]:
        if not self._log_path.exists():
            return []
        rows: List[dict] = []
        with self._log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def replay_at(self, k: int, ts: str) -> dict:
        """Pure fold over the exported JSONL log. Events with ts > the
        checkpoint's ts are skipped (SPEC §2.2 reconstruct_graph_at(t_k)).
        """
        docs: Dict[str, dict]   = {}
        edges: List[dict]       = []
        for ev in self.export_log():
            if str(ev.get("ts", "")) > ts:
                continue
            et = ev.get("event_type")
            p = ev.get("payload") or {}
            if et in ("INGEST", "UPDATE"):
                docs[p["doc_id"]] = {"title": p.get("title", "")}
            elif et == "SUPERSEDE":
                docs[p["doc_id"]] = {"title": p.get("title", "")}
                edges.append({"src": p["doc_id"],
                              "dst": p["old_doc_id"],
                              "type": "SUPERSEDE"})
            elif et == "DELETE":
                docs.pop(p["doc_id"], None)
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(docs.items())],
            "edges": edges,
        }

    # ── introspection (tests use these) ────────────────────────

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def lifecycle_db(self) -> Path:
        return self._lifecycle_db


__all__ = ["JamesAdapter"]
