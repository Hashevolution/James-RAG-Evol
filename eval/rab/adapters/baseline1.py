"""RAB Baseline-1 adapter — bolt-on OTel GenAI tracing on a vanilla RAG.

Baseline-1 (SPEC §5) is the bolt-on-tracing data point. It is the same
in-memory RAG quickstart that Baseline-0 runs, but instrumented with
OpenTelemetry GenAI semantic-conventions-shaped spans instead of
Python-``logging``-style records. The mapping table that converts
OTel span ``gen_ai.operation.name`` values onto RAB canonical event
types is published as ``eval/rab/mappings/otel_genai_to_rab.json``
and hash-pinned in every Baseline-1 result.json.

What this SUT is for (in the gap-table reading):

* It quantifies *which parts* of the gap between Baseline-0 (vanilla
  default logging) and the audit-native column close when an operator
  bolts on the industry-standard tracing format, and *which parts do
  not* — even after bolt-on instrumentation.
* The honest expected outcome on scenario-S1 is:
    AC RETRIEVE = 1.0, AC ANSWER = 1.0 (the OTel home turf),
    AC INGEST = AC UPDATE = AC SUPERSEDE = AC DELETE = AC SYNTH = 0
    (the OTel-vocabulary gap),
    RF = 0 (spans carry no doc payload),
    PC = 0 (no INGEST event means the parent-chain breaks at origin).
* The interesting comparison is NOT Baseline-1 vs Baseline-0 in the
  overall column — it is Baseline-1 vs audit-native column on a
  *per-AC-type* and *RF/PC* axis breakdown. That is what the
  release-handover gap table reports.

Implementation notes:

* This adapter does NOT depend on the OpenTelemetry SDK. Adding a
  runtime dependency on OTel just to emit a few spans into an
  in-memory list would obscure the comparison; instead we construct
  spans as plain dicts shaped per the OTel GenAI semconv. The mapping
  table assumes the publishing operator has used the OTel SDK on the
  way out — the dict shape and the attribute names are identical.
* Spans carry ``span_id`` and ``parent_span_id`` per OTel convention.
  We use these as RAB ``event_id`` / ``parent_id`` directly so PC
  scoring on the exported log behaves exactly as it would for a real
  OTel-instrumented system whose collector forwards the same fields.
* The ``replay_at`` returns the empty state honestly: an OTel-only
  log of a RAG system cannot reconstruct the doc set, because the
  retrieval span only carries doc IDs at query time and there are no
  ingest spans whose payload could be folded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_MAPPING_PATH = Path(__file__).resolve().parents[1] / "mappings" \
                / "otel_genai_to_rab.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Baseline1Adapter:
    """In-memory RAG + OTel GenAI semconv-shaped spans."""

    def __init__(self):
        self._docs:  Dict[str, dict] = {}        # doc_id -> {"title", "text"}
        self._spans: List[dict]      = []        # OTel-shaped span dicts
        self._span_seq: int          = 0
        # Load + cache the mapping table so export_log can produce
        # canonical event_type without re-reading the file every call.
        self._mapping = self._load_mapping()

    # ── mapping table -------------------------------------------------

    @staticmethod
    def _load_mapping() -> Dict[str, str]:
        with _MAPPING_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return dict(data.get("mapping") or {})

    @property
    def MAPPING_TABLE(self) -> Dict[str, str]:  # for the CLI
        return dict(self._mapping)

    # ── internal: emit an OTel-shaped span -------------------------

    def _emit_span(
        self,
        operation_name: str,
        attributes: dict,
        parent_span_id: Optional[str] = None,
    ) -> str:
        """Append one OTel GenAI-semconv-shaped span to the internal
        trace buffer. Returns the new span_id so callers can thread
        parent links."""
        self._span_seq += 1
        span_id = f"ot-{self._span_seq:05d}"
        span = {
            "span_id":        span_id,
            "parent_span_id": parent_span_id,
            "ts":             _now_iso(),
            "operation_name": operation_name,  # gen_ai.operation.name
            "attributes":     dict(attributes),
        }
        self._spans.append(span)
        return span_id

    # ── mutating ops ────────────────────────────────────────────────

    def ingest(self, doc_id: str, title: str, text: str) -> None:
        """A RAG quickstart instrumented purely with OTel GenAI has no
        canonical span for *adding a document to the corpus* — there is
        no ``corpus_ingest`` in the source spec. Operators sometimes
        emit a custom span; doing so would not change the AC INGEST
        result, because the mapping table that ships with v0.1.1 does
        not map custom span names. We mutate state but emit no span,
        which models the honest case where the operator did not
        instrument ingest at all."""
        self._docs[doc_id] = {"title": title, "text": text}

    def update(self, doc_id: str, title: str, text: str) -> None:
        # Same rationale as ingest — no canonical OTel GenAI span.
        self._docs[doc_id] = {"title": title, "text": text}

    def supersede(self, old_doc_id: str, doc_id: str,
                  title: str, text: str) -> None:
        # No supersede taxonomy in OTel GenAI. State mutates;
        # bookkeeping evidence in the log is none.
        self._docs[doc_id] = {"title": title, "text": text}

    def delete(self, doc_id: str) -> None:
        # No delete taxonomy either.
        self._docs.pop(doc_id, None)

    # ── query (retrieval → chat) ────────────────────────────────────

    def query(self, q: str) -> dict:
        # Token-overlap retrieval — same toy retriever Baseline-0 uses,
        # so the comparison isolates the instrumentation differential.
        terms = {w.lower().strip("?.,") for w in q.split() if len(w) > 3}
        hits: List[str] = []
        for doc_id, meta in sorted(self._docs.items()):
            haystack = (meta["title"] + " "
                        + meta["text"][:200]).lower().split()
            if terms & set(haystack):
                hits.append(doc_id)
            if len(hits) >= 3:
                break

        # Retrieval span: gen_ai.operation.name = "retrieval"
        rid = self._emit_span(
            "retrieval",
            {
                "gen_ai.operation.name":      "retrieval",
                "gen_ai.retrieval.query":     q,
                "gen_ai.retrieval.doc_ids":   list(hits),
            },
        )
        # Chat span: gen_ai.operation.name = "chat" — the LLM call +
        # its output. We treat the chat span's *output side* as the
        # ANSWER event (see mapping rationale in
        # mappings/otel_genai_to_rab.json).
        answer = (f"Bolt-on best-effort answer over {', '.join(hits)}."
                  if hits else "No documents matched.")
        self._emit_span(
            "chat",
            {
                "gen_ai.operation.name":          "chat",
                "gen_ai.request.model":           "vanilla-toy-llm",
                "gen_ai.input.messages":          [{"role": "user", "content": q}],
                "gen_ai.output.messages":         [{"role": "assistant", "content": answer}],
                "gen_ai.response.citations":      list(hits),
                "gen_ai.usage.input_tokens":      len(q.split()),
                "gen_ai.usage.output_tokens":     len(answer.split()),
                "gen_ai.response.finish_reasons": ["stop"],
            },
            parent_span_id=rid,
        )
        return {"answer": answer, "citations": list(hits)}

    # ── state + replay ──────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Live state — used by the driver as RF ground truth.

        Bolt-on OTel doesn't bother modelling supersede edges (the
        source spec has no concept), so the snapshot edges list is
        always empty."""
        return {
            "entities": [{"id": d, "title": m["title"]}
                         for d, m in sorted(self._docs.items())],
            "edges": [],
        }

    def export_log(self) -> List[dict]:
        """Apply the mapping table once at export time. The exported
        rows follow SPEC §1; ``event_type`` is the RAB canonical type
        the OTel span's operation_name maps to (OTHER when unmapped).

        The chat span's citations attribute carries forward into the
        RAB payload so PC can attempt the chain — even though, with no
        INGEST event in the log, the chain will fail at origin."""
        rows: List[dict] = []
        for sp in self._spans:
            op = sp.get("operation_name", "")
            attrs = sp.get("attributes", {}) or {}
            canonical = self._mapping.get(op, "OTHER")

            # Build a RAB-canonical payload from the OTel attributes
            # without inventing fields the source spec doesn't carry.
            payload: Dict[str, object] = dict(attrs)
            # For ANSWER rows the scorer expects a "citations" key in
            # the payload (Spec §2.3). The OTel chat span uses
            # gen_ai.response.citations; surface it under the SPEC
            # name as well so PC can walk the chain without the
            # mapping table needing to rename keys.
            if canonical == "ANSWER":
                cites = attrs.get("gen_ai.response.citations") or []
                payload.setdefault("citations", list(cites))
                payload.setdefault("q",
                                   attrs.get("gen_ai.input.messages") or "")
                payload.setdefault("answer",
                                   attrs.get("gen_ai.output.messages") or "")
            if canonical == "RETRIEVE":
                payload.setdefault("doc_ids",
                                   attrs.get("gen_ai.retrieval.doc_ids") or [])
                payload.setdefault("q",
                                   attrs.get("gen_ai.retrieval.query") or "")

            rows.append({
                "event_id":    sp["span_id"],
                "ts":          sp["ts"],
                "event_type":  canonical,
                "parent_id":   sp.get("parent_span_id"),
                "inputs_hash": "",
                "payload":     payload,
            })
        return rows

    def replay_at(self, k: int, ts: str) -> dict:
        """OTel GenAI semconv has no corpus-lifecycle spans, so the
        exported log carries no payload from which to reconstruct the
        document index. Replay therefore returns the empty state. This
        is not a defect of the adapter; it is a structural property of
        the source spec, and the headline finding for the bolt-on
        tier."""
        return {"entities": [], "edges": []}


__all__ = ["Baseline1Adapter"]
