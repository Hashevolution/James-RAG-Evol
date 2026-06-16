"""RAB — Replayable-Audit Benchmark — interactive demo (Hugging Face Space).

A self-contained, deterministic demo of what RAB measures. It runs NO
model and makes NO network call — it reads pre-computed, re-verifiable
RAB artifacts bundled under ./data/ (a frozen scenario-S1 run for JAMES
plus the three other systems' scores). This mirrors JAMES's local-first
/ no-cloud-egress posture: the whole point of RAB is that the numbers
fall out of the exported audit log alone.

Four views:
  1. Gap structure  — AC / RF / PC across the 4 systems (the RAB headline)
  2. Audit log      — the JAMES JSONL log, filterable by canonical type
  3. Time-travel    — per-checkpoint Replay Fidelity (RF) from log-only replay
  4. Provenance     — trace an ANSWER's citations back to their origin event

RAB does NOT certify regulatory compliance; it operationalises EU AI Act
Art. 10/12/19 *concepts* into deterministic metrics.
"""

import json
import os

import gradio as gr

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

SUTS = ["baseline0", "baseline1", "james", "reference"]
SUT_LABEL = {
    "baseline0": "Baseline-0 (vanilla RAG, default logging)",
    "baseline1": "Baseline-1 (vanilla RAG + bolt-on tracing)",
    "james": "JAMES (audit-native reference)",
    "reference": "Reference (spec oracle)",
}


def _load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _load_log(name):
    out = []
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


RESULTS = {sut: _load_json(f"{sut}-S1.result.json") for sut in SUTS}
JAMES_LOG = _load_log("james-S1.log.jsonl")
LOG_BY_ID = {e["event_id"]: e for e in JAMES_LOG}


# ---------------------------------------------------------------- view 1
def gap_structure_table():
    rows = []
    for sut in SUTS:
        r = RESULTS[sut]
        rows.append(
            [
                SUT_LABEL[sut],
                round(r["AC"]["overall"], 3),
                round(r["RF"]["exact"], 3),
                round(r["RF"]["graded"], 3),
                round(r["PC"]["pc"], 3),
                r["RF"].get("cost_s_per_1k_events", "—"),
            ]
        )
    return rows


# ---------------------------------------------------------------- view 2
def audit_log_view(event_type):
    events = JAMES_LOG
    if event_type != "ALL":
        events = [e for e in events if e["event_type"] == event_type]
    rows = []
    for e in events:
        p = e.get("payload", {}) or {}
        summary = p.get("doc_id") or p.get("q") or p.get("answer", "")
        rows.append(
            [
                e["event_id"],
                e["event_type"],
                e.get("parent_id") or "—",
                str(summary)[:80],
                e.get("inputs_hash", "")[:12],
            ]
        )
    return rows


# ---------------------------------------------------------------- view 3
def time_travel_view(sut):
    r = RESULTS[sut]
    rf = r["RF"]
    per = rf.get("per_checkpoint", {})
    rows = []
    for k in sorted(per, key=lambda x: int(x)):
        c = per[k]
        rows.append([int(k), "✅ exact" if c["exact"] else "❌", round(c["jaccard"], 3)])
    summary = (
        f"**{SUT_LABEL[sut]}** — replay from the exported log ONLY "
        f"(no live-state access).\n\n"
        f"- RF-exact (byte-identical state @ checkpoint): **{rf['exact']:.3f}**\n"
        f"- RF-graded (Jaccard partial credit): **{rf['graded']:.3f}**\n"
        f"- RF-cost: **{rf.get('cost_s_per_1k_events', '—')}** s / 1k events "
        f"(scale axis — reported, never blended into the score)\n"
        f"- K = {rf.get('k', len(per))} checkpoints"
    )
    if not rows:
        summary += (
            "\n\n> This system produced no replayable state from its log "
            "(RF = 0). That gap *is* the finding."
        )
    return summary, rows


# ---------------------------------------------------------------- view 4
def _answer_events():
    return [e for e in JAMES_LOG if e["event_type"] == "ANSWER"]


def _origin_events_for(doc_id):
    """Events that introduced this content id: INGEST or SUPERSEDE."""
    return [
        e
        for e in JAMES_LOG
        if e["event_type"] in ("INGEST", "SUPERSEDE")
        and (e.get("payload") or {}).get("doc_id") == doc_id
    ]


def _parent_chain(event):
    """Walk parent_id upward (ANSWER -> SYNTH -> RETRIEVE -> ...)."""
    chain, cur, seen = [], event, set()
    while cur and cur["event_id"] not in seen:
        seen.add(cur["event_id"])
        chain.append(f"{cur['event_id']} [{cur['event_type']}]")
        pid = cur.get("parent_id")
        cur = LOG_BY_ID.get(pid) if pid else None
    return chain


def provenance_view(answer_id):
    ev = LOG_BY_ID.get(answer_id)
    if ev is None:
        return "Select an ANSWER event."
    p = ev.get("payload", {}) or {}
    lines = [
        f"### {answer_id} — provenance trace",
        f"**Question:** {p.get('q', '—')}",
        f"**Answer:** {p.get('answer', '—')}",
        "",
        "**Parent chain (parent_id):** " + " → ".join(_parent_chain(ev)),
        "",
        "**Citations → origin event (INGEST | SUPERSEDE):**",
    ]
    cites = p.get("citations", []) or []
    traceable = 0
    for cid in cites:
        origins = _origin_events_for(cid)
        if origins:
            traceable += 1
            o = origins[-1]  # most recent origin
            lines.append(
                f"- `{cid}` ✅ traceable → {o['event_id']} "
                f"[{o['event_type']}] \"{(o.get('payload') or {}).get('title', '')}\""
            )
        else:
            lines.append(f"- `{cid}` ❌ no origin event in log (untraceable)")
    total = len(cites)
    pc = (traceable / total) if total else 1.0
    lines += ["", f"**PC for this answer:** {traceable}/{total} = {pc:.3f}"]
    return "\n".join(lines)


# ---------------------------------------------------------------- UI
DISCLAIMER = (
    "⚠️ **RAB does not certify regulatory compliance.** It operationalises "
    "EU AI Act Art. 10/12/19 *concepts* into deterministic, re-verifiable "
    "metrics. No LLM judge is used anywhere in scoring. This demo runs no "
    "model and makes no network call — it reads frozen, re-verifiable "
    "scenario-S1 artifacts."
)

with gr.Blocks(title="RAB — Replayable-Audit Benchmark") as demo:
    gr.Markdown(
        "# RAB — Replayable-Audit Benchmark\n"
        "**Can you tell what a RAG system did, replay its past state, and "
        "trace every cited answer — from its audit log alone?** "
        "RAB measures *auditability*, not answer quality.\n\n" + DISCLAIMER
    )

    with gr.Tab("1 · Gap structure"):
        gr.Markdown(
            "The RAB headline is the **gap across systems**, not any single "
            "score (SPEC §5). Scenario-S1, spec v0.1.1."
        )
        gr.Dataframe(
            value=gap_structure_table(),
            headers=["System", "AC", "RF-exact", "RF-graded", "PC", "RF-cost (s/1k)"],
            interactive=False,
        )

    with gr.Tab("2 · Audit log"):
        gr.Markdown(
            "JAMES's exported audit log (JSONL). Each decision-bearing action "
            "is a typed, parented event — this is what **AC** scores."
        )
        et = gr.Dropdown(
            ["ALL", "INGEST", "UPDATE", "SUPERSEDE", "DELETE", "RETRIEVE", "SYNTH", "ANSWER"],
            value="ALL",
            label="canonical event type",
        )
        log_df = gr.Dataframe(
            headers=["event_id", "type", "parent_id", "summary", "inputs_hash"],
            interactive=False,
        )
        et.change(audit_log_view, et, log_df)
        demo.load(audit_log_view, et, log_df)

    with gr.Tab("3 · Time-travel replay (RF)"):
        gr.Markdown(
            "Reconstruct state at each past checkpoint from the **log only**. "
            "JAMES uses `reconstruct_graph_at(t)`. Pick a system to see how "
            "much of its history is faithfully replayable."
        )
        sut_rf = gr.Dropdown(SUTS, value="james", label="system under test")
        rf_md = gr.Markdown()
        rf_df = gr.Dataframe(
            headers=["checkpoint k", "exact", "Jaccard"], interactive=False
        )
        sut_rf.change(time_travel_view, sut_rf, [rf_md, rf_df])
        demo.load(time_travel_view, sut_rf, [rf_md, rf_df])

    with gr.Tab("4 · Provenance"):
        gr.Markdown(
            "Trace an answer's citations back to the event that introduced the "
            "content (`ANSWER → SYNTH → RETRIEVE → INGEST|SUPERSEDE`). "
            "This is what **PC** scores."
        )
        ans = gr.Dropdown(
            [e["event_id"] for e in _answer_events()],
            value=_answer_events()[0]["event_id"] if _answer_events() else None,
            label="ANSWER event",
        )
        prov_md = gr.Markdown()
        ans.change(provenance_view, ans, prov_md)
        demo.load(provenance_view, ans, prov_md)

    gr.Markdown(
        "---\nSpec: `eval/rab/SPEC-v0.1.md` · Source: "
        "[Hashevolution/James-RAG-Evol](https://github.com/Hashevolution/James-RAG-Evol)"
        " · Archive DOI: [10.5281/zenodo.20625533](https://doi.org/10.5281/zenodo.20625533)"
    )

if __name__ == "__main__":
    demo.launch()
