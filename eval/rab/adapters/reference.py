"""RAB reference adapter — a minimal, perfectly-audited in-memory SUT.

Purpose (two-fold):
1. **Benchmark self-verification**: a system that logs every event and
   reconstructs state purely from its log MUST score AC=1.0,
   RF-exact=1.0, PC=1.0. The test suite pins this, which validates the
   driver + scorer end-to-end.
2. **Worked example** of the SPEC §1 interface for adapter authors.

Fault injection (for tests): the constructor flags let tests knock out
specific behaviours and assert the corresponding metric drops —
``drop_audit_types`` (AC), ``corrupt_replay`` (RF),
``break_provenance`` (PC).

State model (deliberately tiny): each live doc is an entity
``{"id": doc_id, "title": title}``; each supersede adds an edge
``{"src": new_doc, "dst": old_doc, "type": "SUPERSEDE"}``. DELETE
removes the entity (edges referencing it remain — history is data).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReferenceAdapter:

    def __init__(
        self,
        *,
        drop_audit_types: Optional[Set[str]] = None,
        corrupt_replay: bool = False,
        break_provenance: bool = False,
    ):
        self._drop = drop_audit_types or set()
        self._corrupt_replay = corrupt_replay
        self._break_provenance = break_provenance
        self._log: List[dict] = []
        self._docs: Dict[str, dict] = {}      # doc_id -> {"title": ...}
        self._edges: List[dict] = []
        self._seq = 0

    # ── internal ────────────────────────────────────────────────────

    def _emit(self, event_type: str, payload: dict,
              parent_id: Optional[str] = None) -> str:
        self._seq += 1
        eid = f"ref-{self._seq:05d}"
        if event_type not in self._drop:
            self._log.append({
                "event_id": eid,
                "ts": _now(),
                "event_type": event_type,
                "parent_id": parent_id,
                "inputs_hash": f"h{self._seq:05d}",
                "payload": payload,
            })
        return eid

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title}
        self._emit("INGEST", {"doc_id": doc_id, "title": title,
                              "text": text})

    def update(self, doc_id: str, title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title}
        self._emit("UPDATE", {"doc_id": doc_id, "title": title,
                              "text": text})

    def supersede(self, old_doc_id: str, doc_id: str,
                  title: str, text: str) -> None:
        self._docs[doc_id] = {"title": title}
        self._edges.append({"src": doc_id, "dst": old_doc_id,
                            "type": "SUPERSEDE"})
        self._emit("SUPERSEDE", {"doc_id": doc_id,
                                 "old_doc_id": old_doc_id,
                                 "title": title, "text": text})

    def delete(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)
        self._emit("DELETE", {"doc_id": doc_id})

    # ── query (RETRIEVE → SYNTH → ANSWER provenance chain) ─────────

    def query(self, q: str) -> dict:
        # naive lexical retrieval over titles — determinism is what
        # matters here, not quality.
        terms = {w.lower().strip("?.,") for w in q.split() if len(w) > 3}
        hits = [d for d, meta in sorted(self._docs.items())
                if terms & {w.lower() for w in meta["title"].split()}]
        hits = hits[:3]
        rid = self._emit("RETRIEVE", {"q": q, "doc_ids": hits})
        sid = self._emit("SYNTH", {"q": q, "n_docs": len(hits)},
                         parent_id=rid)
        citations = [] if self._break_provenance else list(hits)
        answer = (f"Based on {', '.join(hits)}: deterministic stub answer."
                  if hits else "Insufficient information.")
        self._emit("ANSWER", {"q": q, "answer": answer,
                              "citations": citations},
                   parent_id=sid)
        return {"answer": answer, "citations": citations}

    # ── state + replay ──────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(self._docs.items())],
            "edges": [dict(e) for e in self._edges],
        }

    def export_log(self) -> List[dict]:
        return [dict(e) for e in self._log]

    def replay_at(self, k: int, ts: str) -> dict:
        """Fold the EXPORTED LOG's mutating events with event ts <= ts.
        Pure function of the log — the event-sourcing invariant."""
        docs: Dict[str, dict] = {}
        edges: List[dict] = []
        for ev in self._log:
            if str(ev.get("ts", "")) > ts:
                continue
            et = ev.get("event_type")
            p = ev.get("payload") or {}
            if et in ("INGEST", "UPDATE"):
                docs[p["doc_id"]] = {"title": p.get("title", "")}
            elif et == "SUPERSEDE":
                docs[p["doc_id"]] = {"title": p.get("title", "")}
                edges.append({"src": p["doc_id"], "dst": p["old_doc_id"],
                              "type": "SUPERSEDE"})
            elif et == "DELETE":
                docs.pop(p["doc_id"], None)
        if self._corrupt_replay:
            docs["ghost-doc"] = {"title": "corruption artifact"}
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(docs.items())],
            "edges": edges,
        }


__all__ = ["ReferenceAdapter"]
