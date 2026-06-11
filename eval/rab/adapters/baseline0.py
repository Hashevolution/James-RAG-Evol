"""RAB Baseline-0 adapter — vanilla RAG quickstart with default logging.

This adapter is the **floor** per SPEC §5: a system that does in-memory
RAG and emits the kind of log a vanilla quickstart would emit (Python
``logging`` records of human-readable strings), with no RAB canonical
event taxonomy.

The point is *not* to score well. The point is to honestly represent
what most "default logging" looks like — strings, not events — and let
the gap table show what bolt-on tracing would have to add.

Design choices (locked by pre-reg `docs/research/r1-4-preregistration-
2026-06-10.md`):

* Retrieval = title+body token overlap (deterministic, no embeddings).
* "Log" = a list of ``logging.LogRecord``-style dicts captured at the
  moment each op runs. Native event types are LangChain/LlamaIndex-style
  human strings ("doc_added", "query_run") with no parent_id or
  inputs_hash — those don't exist in a vanilla quickstart.
* Mapping table: only the obvious matches are mapped (``doc_added`` →
  INGEST). Updates and supersedes look like "doc_added" too because
  vanilla logging doesn't distinguish them — they correctly map to
  INGEST, which means UPDATE/SUPERSEDE/DELETE/ANSWER ops won't match
  in AC (that IS the floor).
* ``replay_at``: vanilla logs don't carry payloads to replay from, so
  replay returns the empty state. RF-exact / RF-graded will be 0
  whenever there is any ingest.
* ``snapshot``: returns the live state (driver uses it for AC ground
  truth; the SUT not being able to reproduce it from the log is the
  whole point).

This adapter has no LLM dependency and no JAMES dependency — it runs
in-process in milliseconds, so it can sit in CI alongside the
reference adapter as the "what bolt-on minimum looks like" data point.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Baseline0Adapter:
    """Vanilla RAG with Python-``logging``-style default logging."""

    # Mapping table (SPEC §1). Only obvious matches are mapped. Anything
    # else stays as OTHER — i.e. unmapped decision-bearing events count
    # against AC, which is the floor we want to surface.
    MAPPING_TABLE: Dict[str, str] = {
        "doc_added":   "INGEST",   # ingests + updates + supersedes
                                   # all look identical to a vanilla
                                   # logger ("doc added to index")
        "doc_removed": "OTHER",    # delete: many quickstarts don't
                                   # even log this canonically
        "query_run":   "OTHER",    # no ANSWER event in vanilla logs
    }

    def __init__(self):
        self._docs:  Dict[str, dict] = {}        # doc_id -> {"title", "text"}
        self._log:   List[dict]      = []
        self._seq:   int             = 0

    # ── internal ────────────────────────────────────────────────────

    def _log_record(self, native_type: str, msg: str) -> None:
        """Emit a vanilla-logger-style record. No parent_id, no
        inputs_hash, no structured payload — just a human string."""
        self._seq += 1
        self._log.append({
            "event_id":    f"bl0-{self._seq:05d}",
            "ts":          _now(),
            "event_type":  self.MAPPING_TABLE.get(native_type, "OTHER"),
            "parent_id":   None,
            "inputs_hash": "",
            "payload":     {"msg": msg, "native": native_type},
        })

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title, "text": text}
        self._log_record("doc_added", f"Indexed document {doc_id}")

    def update(self, doc_id: str, title: str, text: str) -> None:
        # Vanilla quickstart doesn't distinguish update from ingest —
        # it just re-indexes the document.
        self._docs[doc_id] = {"title": title, "text": text}
        self._log_record("doc_added", f"Re-indexed document {doc_id}")

    def supersede(self, old_doc_id: str, doc_id: str,
                  title: str, text: str) -> None:
        # No supersede concept; both docs end up in the index.
        self._docs[doc_id] = {"title": title, "text": text}
        # NB: vanilla quickstart wouldn't even know to keep the old doc;
        # we leave _docs[old_doc_id] alone (it's still there).
        self._log_record("doc_added", f"Indexed document {doc_id} "
                                      f"(replacing {old_doc_id})")

    def delete(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._log_record("doc_removed", f"Removed document {doc_id}")

    # ── query (no provenance chain in vanilla logs) ────────────────

    def query(self, q: str) -> dict:
        # Token-overlap retrieval over title + first 200 chars of text.
        terms = {w.lower().strip("?.,") for w in q.split() if len(w) > 3}
        hits: List[str] = []
        for doc_id, meta in sorted(self._docs.items()):
            haystack = (meta["title"] + " "
                        + meta["text"][:200]).lower().split()
            if terms & set(haystack):
                hits.append(doc_id)
            if len(hits) >= 3:
                break

        self._log_record("query_run", f"Query: {q!r}; hits={hits}")
        answer = (f"Best-effort answer based on {', '.join(hits)}."
                  if hits else "No documents matched.")
        # Vanilla quickstart often returns sources but they're not
        # threaded through a provenance chain.
        return {"answer": answer, "citations": list(hits)}

    # ── state + replay ──────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Live state — used by the driver as RF ground truth.

        Baseline-0 has no concept of supersede edges, so ``edges`` is
        always empty. Entities = the live document index.
        """
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(self._docs.items())],
            "edges": [],
        }

    def export_log(self) -> List[dict]:
        return [dict(e) for e in self._log]

    def replay_at(self, k: int, ts: str) -> dict:
        """Vanilla logs have no payload to replay from — return the
        empty state. This is the honest floor: a system whose log
        cannot reconstruct state.
        """
        return {"entities": [], "edges": []}


__all__ = ["Baseline0Adapter"]
