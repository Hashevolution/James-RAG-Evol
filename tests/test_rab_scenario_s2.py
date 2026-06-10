"""RAB scenario-S2 fixture sanity + reference-SUT pin.

Pre-registration (`docs/research/r1-phase-3-scenario-s2-preregistration-
2026-06-10.md`) commits S2's shape before measurement. These tests are
the sentinel: any change to the generator or fixture that violates the
locked shape fails CI.

Pinned obligations:
- 400 ops total
- 110 INGEST / 40 UPDATE / 30 SUPERSEDE / 20 DELETE / 200 QUERY
- 40 checkpoints
- supersede chains: avg length >= 3, longest >= 5
- cross-reference density (doc_id mentions per content-bearing text) >= 2.5
- Reference adapter scores 1.000 / 1.000 / 1.000 on S2 — driver/scorer
  gate.
"""
import json
import re
from pathlib import Path
from typing import Dict, List

from eval.rab.adapters.reference import ReferenceAdapter
from eval.rab.driver import load_scenario, run_scenario, score_run

ROOT = Path(__file__).resolve().parent.parent
S2 = ROOT / "eval" / "rab" / "scenarios" / "s2_lifecycle_large.json"
_DOC_ID_RE = re.compile(r"co-[a-z]+-\d{3}(?:-r\d+)?")


# ─── fixture sanity ────────────────────────────────────────────────


def _load():
    return json.loads(S2.read_text(encoding="utf-8"))


def test_s2_header():
    data = _load()
    assert data["scenario"] == "S2"
    assert data["name"] == "lifecycle-large"
    assert data["spec"] == "v0.1.1"


def test_s2_distribution_matches_prereg():
    data = _load()
    ops = data["ops"]
    assert len(ops) == 400
    counts: Dict[str, int] = {}
    for o in ops:
        counts[o["op"]] = counts.get(o["op"], 0) + 1
    assert counts == {
        "INGEST": 110, "UPDATE": 40, "SUPERSEDE": 30,
        "DELETE": 20, "QUERY": 200,
    }


def test_s2_checkpoints_count_and_spacing():
    data = _load()
    ops = data["ops"]
    cps = [i for i, o in enumerate(ops, start=1) if o.get("checkpoint")]
    assert len(cps) == 40
    # every 10th op is a checkpoint per the generator schedule
    assert cps == list(range(10, 401, 10))


def test_s2_op_ids_unique_and_sorted():
    data = _load()
    ids = [o["op_id"] for o in data["ops"]]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)
    # deterministic prefix
    assert ids[0] == "s2-001"
    assert ids[-1] == "s2-400"


def test_s2_supersede_chains_shape():
    """Chains are grouped by lineage seed (the original old_doc_id at
    the chain head). Sentinel: avg length >= 3, longest >= 5."""
    data = _load()
    new_to_seed: Dict[str, str] = {}
    chain_len: Dict[str, int] = {}
    for op in data["ops"]:
        if op["op"] != "SUPERSEDE":
            continue
        old = op["args"]["old_doc_id"]
        new = op["args"]["doc_id"]
        seed = new_to_seed.get(old, old)
        chain_len[seed] = chain_len.get(seed, 0) + 1
        new_to_seed[new] = seed
    lengths: List[int] = list(chain_len.values())
    assert sum(lengths) == 30
    assert max(lengths) >= 5
    assert sum(lengths) / len(lengths) >= 3.0


def test_s2_cross_reference_density_meets_threshold():
    """Average count of *other* doc_id mentions per content-bearing text
    must be >= 2.5 (pre-registration §2 obligation)."""
    data = _load()
    mentions = 0
    texts = 0
    for op in data["ops"]:
        if op["op"] not in ("INGEST", "UPDATE", "SUPERSEDE"):
            continue
        self_id = op["args"].get("doc_id", "")
        text = op["args"].get("text", "") or ""
        found = {m for m in _DOC_ID_RE.findall(text)} - {self_id}
        mentions += len(found)
        texts += 1
    density = mentions / texts
    assert density >= 2.5, f"cross-ref density {density:.2f} < 2.5"


def test_s2_doc_id_prefix_convention():
    """Every doc_id introduced or referenced uses the co-XXX-NNN[-rN]
    prefix family (pre-registration §2)."""
    data = _load()
    expected_prefixes = {
        "co-dep", "co-app", "co-bud", "co-pol",
        "co-prj", "co-ctr", "co-inc",
    }
    for op in data["ops"]:
        for key in ("doc_id", "old_doc_id"):
            v = op["args"].get(key)
            if v is None:
                continue
            head = "-".join(v.split("-")[:2])
            assert head in expected_prefixes, (key, v)


def test_s2_supersede_targets_exist_at_time_of_op():
    """Every SUPERSEDE's old_doc_id must have been introduced (INGEST or
    a previous SUPERSEDE's new doc) BEFORE the op. Catches generator
    regressions where the chain head is missing."""
    data = _load()
    alive: set = set()
    for op in data["ops"]:
        a = op["args"]
        if op["op"] == "INGEST":
            alive.add(a["doc_id"])
        elif op["op"] == "SUPERSEDE":
            assert a["old_doc_id"] in alive, (op["op_id"], a["old_doc_id"])
            alive.add(a["doc_id"])
        elif op["op"] == "DELETE":
            # delete may target a doc not currently alive (e.g. an already
            # superseded intermediate revision); skip strict check here.
            pass


# ─── reference SUT pin: 1.000 / 1.000 / 1.000 on S2 ────────────────


def test_reference_adapter_pins_metrics_on_s2():
    """Same contract S1 enforces: a perfectly-audited event-sourced SUT
    MUST score AC=1.0 / RF-exact=1.0 / PC=1.0 on S2. This is the
    driver+scorer correctness gate (and the §6 invalidity rule of the
    pre-registration: if Reference < 1.000x3, the measurement is invalid
    and we fix the scenario, not interpret SUT numbers)."""
    scenario = load_scenario(S2)
    adapter = ReferenceAdapter()
    artifacts = run_scenario(scenario, adapter)
    scored = score_run(artifacts)
    assert scored["AC"]["overall"] == 1.0, scored["AC"]
    assert scored["RF"]["exact"] == 1.0, scored["RF"]
    assert scored["PC"]["pc"] == 1.0, scored["PC"]
