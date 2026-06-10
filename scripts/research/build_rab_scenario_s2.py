"""Build scenario-S2 'lifecycle-large' fixture for RAB SPEC v0.1.1.

Pre-registered (PR #774):
- 400 ops: 110 INGEST + 40 UPDATE + 30 SUPERSEDE + 20 DELETE + 200 QUERY
- 40 checkpoints
- supersede chain: avg length >= 3, longest >= 5 hops
- cross-reference density >= 2.5 (each doc text mentions >= 2.5 other doc_ids)
- domain: synthetic City Operations (departments / projects / contracts /
  incidents / policies / appointments / budgets). English prose, no
  randomness, no time-dependent inputs.

Run: ``python scripts/research/build_rab_scenario_s2.py``
Writes: ``eval/rab/scenarios/s2_lifecycle_large.json``

This script is the reproducibility witness for the fixture; the JSON
output is the artifact that gets sha-pinned in result.json files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "rab" / "scenarios" / "s2_lifecycle_large.json"

# ──────────────────────────────────────────────────────────────────────
# Deterministic vocabulary (no random; everything indexed)
# ──────────────────────────────────────────────────────────────────────

DEPARTMENTS = [
    ("public-works", "Department of Public Works"),
    ("parks",        "Department of Parks and Recreation"),
    ("transport",    "Department of Transport"),
    ("permits",      "Department of Permits and Inspections"),
    ("records",      "Department of Records"),
    ("procurement",  "Office of Procurement"),
    ("safety",       "Office of Public Safety"),
    ("code",         "Office of Code Enforcement"),
    ("housing",      "Department of Housing"),
    ("health",       "Department of Public Health"),
]

# 30 named persons used as project leads / directors / contractors
PERSONS = [
    "Lena Ortiz", "Marcus Chen", "Priya Anand", "Sofia Reyes",
    "Daniel Okoye", "Tomas Eriksen", "Hana Park", "Idris Mwangi",
    "Junko Watanabe", "Karim El-Sayed", "Lucia Bianchi", "Mehmet Aydin",
    "Nadia Hassan", "Oscar Lindgren", "Pia Novak", "Quentin Aubert",
    "Rosa Delgado", "Samir Khoury", "Tara Joshi", "Ulrich Bauer",
    "Vivian Cho", "Wei Tan", "Xochitl Mendez", "Yusuf Demir",
    "Zara Khan", "Aiko Tanaka", "Bjorn Holm", "Camila Souza",
    "Devon Pratt", "Eitan Levy",
]

# 30 projects (3 per department, deterministic association)
PROJECTS = [
    ("co-prj-001", "Project Riverwalk Renewal",         "public-works"),
    ("co-prj-002", "Project Pothole Survey",            "public-works"),
    ("co-prj-003", "Project Storm Drain Mapping",       "public-works"),
    ("co-prj-004", "Project Arboretum Expansion",       "parks"),
    ("co-prj-005", "Project Playground Audit",          "parks"),
    ("co-prj-006", "Project Trail Wayfinding",          "parks"),
    ("co-prj-007", "Project Bus Lane Modernisation",    "transport"),
    ("co-prj-008", "Project Ferry Terminal Upgrade",    "transport"),
    ("co-prj-009", "Project Signal Retiming Phase 1",   "transport"),
    ("co-prj-010", "Project Permit Portal Rebuild",     "permits"),
    ("co-prj-011", "Project Inspection Backlog Clear",  "permits"),
    ("co-prj-012", "Project Historic Plaque Survey",    "permits"),
    ("co-prj-013", "Project Records Digitisation",      "records"),
    ("co-prj-014", "Project Archive Climate Control",   "records"),
    ("co-prj-015", "Project FOIA Workflow Reform",      "records"),
    ("co-prj-016", "Project Vendor Onboarding",         "procurement"),
    ("co-prj-017", "Project Contract Templates Refresh","procurement"),
    ("co-prj-018", "Project Spend Analytics Dashboard", "procurement"),
    ("co-prj-019", "Project Fire Station Siting",       "safety"),
    ("co-prj-020", "Project Emergency Comms Upgrade",   "safety"),
    ("co-prj-021", "Project Hydrant Inventory",         "safety"),
    ("co-prj-022", "Project Vacant Lot Registry",       "code"),
    ("co-prj-023", "Project Noise Complaint Triage",    "code"),
    ("co-prj-024", "Project Sign Code Modernisation",   "code"),
    ("co-prj-025", "Project Affordable Units Census",   "housing"),
    ("co-prj-026", "Project Voucher Programme Reform",  "housing"),
    ("co-prj-027", "Project Tenant Helpline Expansion", "housing"),
    ("co-prj-028", "Project Clinic Site Survey",        "health"),
    ("co-prj-029", "Project Vector Control Mapping",    "health"),
    ("co-prj-030", "Project Health Data Lake",          "health"),
]

# 20 contracts; each ties a vendor to one or more projects
CONTRACTS = [
    ("co-ctr-001", "Contract Helios Cells — battery storage pilot",   "public-works", ["co-prj-001"]),
    ("co-ctr-002", "Contract Vento Group — drainage equipment",        "public-works", ["co-prj-003"]),
    ("co-ctr-003", "Contract Arborwise — tree health survey",          "parks",        ["co-prj-004", "co-prj-006"]),
    ("co-ctr-004", "Contract PlayCheck Ltd — safety audit",            "parks",        ["co-prj-005"]),
    ("co-ctr-005", "Contract MetroSignal — signal hardware",           "transport",    ["co-prj-009"]),
    ("co-ctr-006", "Contract Marinex — ferry electrical refit",        "transport",    ["co-prj-008"]),
    ("co-ctr-007", "Contract CodeForge — portal development",          "permits",      ["co-prj-010"]),
    ("co-ctr-008", "Contract Heritage Studio — plaque fabrication",    "permits",      ["co-prj-012"]),
    ("co-ctr-009", "Contract DigiScan — archive digitisation",         "records",      ["co-prj-013"]),
    ("co-ctr-010", "Contract Climacore — HVAC for archives",           "records",      ["co-prj-014"]),
    ("co-ctr-011", "Contract Talenta — vendor onboarding tooling",     "procurement",  ["co-prj-016"]),
    ("co-ctr-012", "Contract DataLense — spend analytics platform",    "procurement",  ["co-prj-018"]),
    ("co-ctr-013", "Contract FireRadio — emergency comms hardware",    "safety",       ["co-prj-020"]),
    ("co-ctr-014", "Contract HydroMap — hydrant survey services",      "safety",       ["co-prj-021"]),
    ("co-ctr-015", "Contract LotTrack — vacant lot registry tooling",  "code",         ["co-prj-022"]),
    ("co-ctr-016", "Contract Quietworks — acoustic monitoring",        "code",         ["co-prj-023"]),
    ("co-ctr-017", "Contract HomeBridge — voucher case management",    "housing",      ["co-prj-026"]),
    ("co-ctr-018", "Contract LineTwo — tenant helpline staffing",      "housing",      ["co-prj-027"]),
    ("co-ctr-019", "Contract MapClinic — clinic siting analytics",     "health",       ["co-prj-028"]),
    ("co-ctr-020", "Contract VectorOps — mosquito surveillance",       "health",       ["co-prj-029"]),
]

# 10 incidents (operational events that cross-reference projects/depts)
INCIDENTS = [
    ("co-inc-001", "Incident Riverwalk segment closure",
        "public-works", ["co-prj-001", "co-ctr-001"]),
    ("co-inc-002", "Incident Bus lane signal conflict",
        "transport",    ["co-prj-007", "co-prj-009"]),
    ("co-inc-003", "Incident Ferry refit schedule slip",
        "transport",    ["co-prj-008", "co-ctr-006"]),
    ("co-inc-004", "Incident Permit portal outage",
        "permits",      ["co-prj-010", "co-ctr-007"]),
    ("co-inc-005", "Incident Archive HVAC alarm",
        "records",      ["co-prj-014", "co-ctr-010"]),
    ("co-inc-006", "Incident Emergency radio dead zone",
        "safety",       ["co-prj-020", "co-ctr-013"]),
    ("co-inc-007", "Incident Hydrant pressure failure",
        "safety",       ["co-prj-021", "co-ctr-014"]),
    ("co-inc-008", "Incident Voucher payment delay",
        "housing",      ["co-prj-026", "co-ctr-017"]),
    ("co-inc-009", "Incident Mosquito surveillance gap",
        "health",       ["co-prj-029", "co-ctr-020"]),
    ("co-inc-010", "Incident Clinic siting public comment",
        "health",       ["co-prj-028", "co-ctr-019"]),
]

# 20 policy docs (2 per dept; the first 10 also serve as SUPERSEDE seeds)
POLICIES = [
    ("co-pol-001", "Policy Procurement code v1",          "procurement"),
    ("co-pol-002", "Policy Records retention v1",         "records"),
    ("co-pol-003", "Policy Inspection escalation v1",     "permits"),
    ("co-pol-004", "Policy Tenant eviction guidance v1",  "housing"),
    ("co-pol-005", "Policy Vector control protocol v1",   "health"),
    ("co-pol-006", "Policy Bus lane enforcement v1",      "transport"),
    ("co-pol-007", "Policy Park ranger conduct v1",       "parks"),
    ("co-pol-008", "Policy Public hearing notice v1",     "code"),
    ("co-pol-009", "Policy Hydrant inspection v1",        "safety"),
    ("co-pol-010", "Policy Storm response v1",            "public-works"),
    ("co-pol-011", "Policy Vendor disqualification v1",   "procurement"),
    ("co-pol-012", "Policy Archive access v1",            "records"),
    ("co-pol-013", "Policy Permit appeals v1",            "permits"),
    ("co-pol-014", "Policy Voucher fraud reporting v1",   "housing"),
    ("co-pol-015", "Policy Clinic data sharing v1",       "health"),
    ("co-pol-016", "Policy Ferry safety drills v1",       "transport"),
    ("co-pol-017", "Policy Trail closure protocol v1",    "parks"),
    ("co-pol-018", "Policy Sign permit fee schedule v1",  "code"),
    ("co-pol-019", "Policy Mutual aid agreement v1",      "safety"),
    ("co-pol-020", "Policy Snow plough priority v1",      "public-works"),
]

# 10 budgets
BUDGETS = [
    ("co-bud-001", "Budget Public Works FY2024",  "public-works"),
    ("co-bud-002", "Budget Parks FY2024",         "parks"),
    ("co-bud-003", "Budget Transport FY2024",     "transport"),
    ("co-bud-004", "Budget Permits FY2024",       "permits"),
    ("co-bud-005", "Budget Records FY2024",       "records"),
    ("co-bud-006", "Budget Procurement FY2024",   "procurement"),
    ("co-bud-007", "Budget Safety FY2024",        "safety"),
    ("co-bud-008", "Budget Code FY2024",          "code"),
    ("co-bud-009", "Budget Housing FY2024",       "housing"),
    ("co-bud-010", "Budget Health FY2024",        "health"),
]

# 10 appointment / charter docs (one per department director)
APPOINTMENTS = [
    (f"co-app-{i+1:03d}",
     f"Appointment {dep[1]} — Director {PERSONS[i]}",
     dep[0])
    for i, dep in enumerate(DEPARTMENTS)
]


def _dep_title(slug: str) -> str:
    return next(t for s, t in DEPARTMENTS if s == slug)


# ──────────────────────────────────────────────────────────────────────
# INGEST text builders (each text mentions >= 2-3 other doc_ids)
# ──────────────────────────────────────────────────────────────────────

def _dept_id_of(slug: str) -> str:
    return f"co-dep-{next(i for i, d in enumerate(DEPARTMENTS) if d[0] == slug) + 1:03d}"


def _app_id_of(slug: str) -> str:
    return f"co-app-{next(i for i, d in enumerate(DEPARTMENTS) if d[0] == slug) + 1:03d}"


def _bud_id_of(slug: str) -> str:
    return f"co-bud-{next(i for i, d in enumerate(DEPARTMENTS) if d[0] == slug) + 1:03d}"


def _policies_of(slug: str) -> List[str]:
    return [p[0] for p in POLICIES if p[2] == slug]


def _ingest_dept_charter(idx: int) -> Tuple[str, str, str]:
    slug, dept_title = DEPARTMENTS[idx]
    director = PERSONS[idx]
    app_id = _app_id_of(slug)
    dept_id = _dept_id_of(slug)
    bud_id = _bud_id_of(slug)
    dept_projects = [p[0] for p in PROJECTS if p[2] == slug]
    dept_policies = _policies_of(slug)
    text = (
        f"The {dept_title} (doc {dept_id}) is led by {director} per "
        f"appointment {app_id}. Operating budget: {bud_id}. Active projects: "
        f"{', '.join(dept_projects)}. Department policies: "
        f"{', '.join(dept_policies)}."
    )
    return dept_id, dept_title, text


def _ingest_appointment(idx: int) -> Tuple[str, str, str]:
    app_id, title, slug = APPOINTMENTS[idx]
    director = PERSONS[idx]
    dept_id = _dept_id_of(slug)
    bud_id = _bud_id_of(slug)
    dept_projects = [p[0] for p in PROJECTS if p[2] == slug]
    dept_policies = _policies_of(slug)
    text = (
        f"Per record {app_id}, {director} is appointed director of the "
        f"{_dep_title(slug)} (doc {dept_id}). Budget authority: {bud_id}. "
        f"Oversees projects {', '.join(dept_projects)} and policies "
        f"{', '.join(dept_policies)}."
    )
    return app_id, title, text


def _ingest_budget(idx: int) -> Tuple[str, str, str]:
    bud_id, title, slug = BUDGETS[idx]
    dept_id = _dept_id_of(slug)
    app_id = _app_id_of(slug)
    director = PERSONS[idx]
    dept_projects = [p[0] for p in PROJECTS if p[2] == slug]
    dept_contracts = [c[0] for c in CONTRACTS if c[2] == slug]
    text = (
        f"Budget record {bud_id} allocates funds to the {_dep_title(slug)} "
        f"(doc {dept_id}, director {director} per {app_id}). Funded "
        f"projects: {', '.join(dept_projects)}. Active contracts: "
        f"{', '.join(dept_contracts)}."
    )
    return bud_id, title, text


def _ingest_policy(idx: int) -> Tuple[str, str, str]:
    pol_id, title, slug = POLICIES[idx]
    dept_idx = next(i for i, d in enumerate(DEPARTMENTS) if d[0] == slug)
    dept_id = _dept_id_of(slug)
    app_id = _app_id_of(slug)
    bud_id = _bud_id_of(slug)
    director = PERSONS[dept_idx]
    text = (
        f"Policy {pol_id} ({title}) is owned by the {_dep_title(slug)} "
        f"(doc {dept_id}, director {director} per {app_id}) and is funded "
        f"under budget {bud_id}. Applies to all department operations."
    )
    return pol_id, title, text


def _ingest_project(idx: int) -> Tuple[str, str, str]:
    prj_id, title, slug = PROJECTS[idx]
    dept_id = _dept_id_of(slug)
    app_id = _app_id_of(slug)
    bud_id = _bud_id_of(slug)
    # project leads cycle through PERSONS (deterministic)
    lead = PERSONS[idx % len(PERSONS)]
    siblings = [p[0] for p in PROJECTS if p[2] == slug and p[0] != prj_id]
    related_contracts = [c[0] for c in CONTRACTS if prj_id in c[3]]
    contract_str = (
        f" Active contract(s): {', '.join(related_contracts)}."
        if related_contracts else ""
    )
    sibling_str = (
        f" Coordinates with sibling projects "
        f"{', '.join(siblings[:2])}." if siblings else ""
    )
    text = (
        f"{title} (doc {prj_id}) is run by the {_dep_title(slug)} "
        f"(doc {dept_id}, director per {app_id}, budget {bud_id}). "
        f"Lead: {lead}.{sibling_str}{contract_str}"
    )
    return prj_id, title, text


def _ingest_contract(idx: int) -> Tuple[str, str, str]:
    ctr_id, title, slug, prj_refs = CONTRACTS[idx]
    dept_id = _dept_id_of(slug)
    app_id = _app_id_of(slug)
    bud_id = _bud_id_of(slug)
    text = (
        f"{title} (doc {ctr_id}) is administered by the {_dep_title(slug)} "
        f"(doc {dept_id}, director per {app_id}) under budget {bud_id}. "
        f"Covers project(s) {', '.join(prj_refs)}."
    )
    return ctr_id, title, text


def _ingest_incident(idx: int) -> Tuple[str, str, str]:
    inc_id, title, slug, refs = INCIDENTS[idx]
    dept_id = _dept_id_of(slug)
    app_id = _app_id_of(slug)
    text = (
        f"{title} (doc {inc_id}) was filed against the {_dep_title(slug)} "
        f"(doc {dept_id}, director per {app_id}). Related records: "
        f"{', '.join(refs)}."
    )
    return inc_id, title, text


# Build the deterministic INGEST sequence (110 docs).
def _ingest_seq() -> List[Tuple[str, str, str]]:
    seq: List[Tuple[str, str, str]] = []
    for i in range(len(DEPARTMENTS)):       # 10 dept
        seq.append(_ingest_dept_charter(i))
    for i in range(len(APPOINTMENTS)):      # 10 app
        seq.append(_ingest_appointment(i))
    for i in range(len(BUDGETS)):           # 10 bud
        seq.append(_ingest_budget(i))
    for i in range(len(POLICIES)):          # 10 pol
        seq.append(_ingest_policy(i))
    for i in range(len(PROJECTS)):          # 30 prj
        seq.append(_ingest_project(i))
    for i in range(len(CONTRACTS)):         # 20 ctr
        seq.append(_ingest_contract(i))
    for i in range(len(INCIDENTS)):         # 10 inc
        seq.append(_ingest_incident(i))
    assert len(seq) == 110, len(seq)
    return seq


# ──────────────────────────────────────────────────────────────────────
# UPDATE targets (40 docs — minor revisions of existing docs)
# ──────────────────────────────────────────────────────────────────────

def _update_seq() -> List[Tuple[str, str, str]]:
    """40 UPDATE ops on existing doc_ids; each retains the doc_id but
    revises the title (vN suffix) and the text. Targets are distributed:
    10 budgets (FY2024 -> FY2024 rev) + 10 policies (v1 -> v1.1) +
    10 projects + 10 contracts."""
    out: List[Tuple[str, str, str]] = []
    # 10 budget updates (FY2024 -> FY2024 mid-year revision)
    for i, (bud_id, title, slug) in enumerate(BUDGETS):
        dept_id = f"co-dep-{i+1:03d}"
        prjs = [p[0] for p in PROJECTS if p[2] == slug]
        new_title = title + " (mid-year revision)"
        text = (
            f"Mid-year revision of {bud_id}. Reallocates funds between "
            f"{_dep_title(slug)} (doc {dept_id}) projects: "
            f"{', '.join(prjs)}."
        )
        out.append((bud_id, new_title, text))
    # 10 policy revisions to v1.1 (first 10 only — second 10 are not updated)
    for i, (pol_id, title, slug) in enumerate(POLICIES[:10]):
        dept_idx = next(j for j, d in enumerate(DEPARTMENTS) if d[0] == slug)
        dept_id = f"co-dep-{dept_idx+1:03d}"
        new_title = title.replace(" v1", " v1.1")
        text = (
            f"Revision v1.1 of policy {pol_id}. Clarifies enforcement under "
            f"the {_dep_title(slug)} (doc {dept_id})."
        )
        out.append((pol_id, new_title, text))
    # 10 project status updates (first 10 projects)
    for i in range(10):
        prj_id, title, slug = PROJECTS[i]
        dept_idx = next(j for j, d in enumerate(DEPARTMENTS) if d[0] == slug)
        dept_id = f"co-dep-{dept_idx+1:03d}"
        ctrs = [c[0] for c in CONTRACTS if prj_id in c[3]]
        ctr_str = f" Active contract(s): {', '.join(ctrs)}." if ctrs else ""
        new_title = title + " (status update)"
        text = (
            f"Status update on {title} (doc {prj_id}) under the "
            f"{_dep_title(slug)} (doc {dept_id}).{ctr_str}"
        )
        out.append((prj_id, new_title, text))
    # 10 contract amendments (first 10 contracts)
    for i in range(10):
        ctr_id, title, slug, prj_refs = CONTRACTS[i]
        dept_idx = next(j for j, d in enumerate(DEPARTMENTS) if d[0] == slug)
        dept_id = f"co-dep-{dept_idx+1:03d}"
        new_title = title + " (amendment 1)"
        text = (
            f"Amendment 1 to {ctr_id}. Extends scope to additional work "
            f"under the {_dep_title(slug)} (doc {dept_id}). Affected "
            f"project(s): {', '.join(prj_refs)}."
        )
        out.append((ctr_id, new_title, text))
    assert len(out) == 40, len(out)
    return out


# ──────────────────────────────────────────────────────────────────────
# SUPERSEDE chain plan
#
# Pre-registered shape: 30 SUPERSEDE ops across 9 chains.
#   - 2 chains of length 5 (10 SUPERSEDE)
#   - 2 chains of length 4 ( 8 SUPERSEDE)
#   - 2 chains of length 3 ( 6 SUPERSEDE)
#   - 3 chains of length 2 ( 6 SUPERSEDE)
# avg chain length = 30 / 9 ≈ 3.33  (>= 3, sentinel OK)
# longest chain   = 5                (>= 5, sentinel OK)
# Chain seeds = existing INGEST doc_ids (the head of each chain).
# ──────────────────────────────────────────────────────────────────────

SUPERSEDE_PLAN: List[Tuple[str, int]] = [
    # (seed_doc_id, chain_length)
    ("co-pol-001", 5),  # procurement code lineage
    ("co-pol-002", 5),  # records retention lineage
    ("co-pol-003", 4),  # inspection escalation lineage
    ("co-pol-004", 4),  # tenant eviction guidance lineage
    ("co-pol-005", 3),  # vector control protocol lineage
    ("co-pol-006", 3),  # bus lane enforcement lineage
    ("co-ctr-011", 2),  # vendor onboarding contract turnover
    ("co-ctr-014", 2),  # hydrant survey vendor turnover
    ("co-ctr-019", 2),  # clinic siting vendor turnover
]

assert sum(L for _, L in SUPERSEDE_PLAN) == 30
assert max(L for _, L in SUPERSEDE_PLAN) >= 5
assert sum(L for _, L in SUPERSEDE_PLAN) / len(SUPERSEDE_PLAN) >= 3.0


def _supersede_seq() -> List[Tuple[str, str, str, str]]:
    """Yield (old_doc_id, new_doc_id, title, text) flattening every
    chain in SUPERSEDE_PLAN. The first hop's old_doc_id is the seed
    (existing INGEST id); subsequent hops chain from the previous hop's
    new_doc_id. New doc_ids are deterministic: ``<seed>-rN``."""
    out: List[Tuple[str, str, str, str]] = []
    for seed, length in SUPERSEDE_PLAN:
        prev_id = seed
        for hop in range(1, length + 1):
            new_id = f"{seed}-r{hop}"
            # Title carries the revision number; text cross-refs
            # the predecessor and the seed.
            title = f"Revision r{hop} of {seed}"
            text = (
                f"This revision (doc {new_id}) supersedes {prev_id}; the "
                f"lineage originates at {seed}. The revision adjusts the "
                f"underlying record while preserving the SUPERSEDE chain."
            )
            out.append((prev_id, new_id, title, text))
            prev_id = new_id
    assert len(out) == 30, len(out)
    return out


# ──────────────────────────────────────────────────────────────────────
# DELETE targets (20 doc_ids — operational retirements)
# ──────────────────────────────────────────────────────────────────────

def _delete_seq() -> List[str]:
    """20 deletes targeting incidents, the first r1 revision of every
    supersede chain (older intermediate revisions), and one budget
    retired at fiscal close. Deletes happen after the chain has been
    extended in Phase 4, so removing an intermediate revision does not
    break the chain history (history is data — the supersede edges
    remain in the log)."""
    deletes: List[str] = []
    # Retire all 10 incidents (operational close-out)
    for inc_id, _, _, _ in INCIDENTS:
        deletes.append(inc_id)
    # Retire the r1 revision of every supersede chain (9 chains)
    for seed, length in SUPERSEDE_PLAN:
        deletes.append(f"{seed}-r1")
    # Retire one fiscal budget at year close
    deletes.append("co-bud-010")
    assert len(deletes) == 20, len(deletes)
    return deletes


# ──────────────────────────────────────────────────────────────────────
# QUERY pool (200 queries — deterministic, drawn from corpus facts)
# ──────────────────────────────────────────────────────────────────────

def _query_pool() -> List[str]:
    out: List[str] = []
    # 10 per department: director, charter doc id, projects, budget
    for i, (slug, dept_title) in enumerate(DEPARTMENTS):
        director = PERSONS[i]
        out.append(f"Who is the director of the {dept_title}?")
        out.append(f"Which doc id holds the appointment of {director}?")
        out.append(f"How many active projects does the {dept_title} oversee?")
        out.append(f"What is the FY2024 budget doc id for the {dept_title}?")
        out.append(f"Which policy v1 belongs to the {dept_title}?")
    # 30 project lead queries
    for prj_id, title, slug in PROJECTS:
        out.append(f"Who leads {title}?")
    # 20 contract queries
    for ctr_id, title, slug, refs in CONTRACTS:
        out.append(f"Which project(s) does {ctr_id} cover?")
    # 10 incident queries
    for inc_id, title, slug, refs in INCIDENTS:
        out.append(f"Which department filed {inc_id}?")
    # 10 supersede chain queries (1 per chain — current head)
    for seed, length in SUPERSEDE_PLAN:
        out.append(f"What is the current revision in the {seed} lineage?")
    # 49 cross-reference queries on department-project relations
    for i in range(49):
        slug, dept_title = DEPARTMENTS[i % len(DEPARTMENTS)]
        out.append(f"Name one project run by the {dept_title}.")
    # 32 misc factual queries (persons cross-referenced to departments)
    for i in range(32):
        person = PERSONS[i % len(PERSONS)]
        out.append(f"What department does {person} direct or work for?")
    # Total so far: 50 + 30 + 20 + 10 + 9 + 49 + 32 = 200
    assert len(out) == 200, len(out)
    return out


# ──────────────────────────────────────────────────────────────────────
# Op-list assembly per the pre-registered phase distribution
# ──────────────────────────────────────────────────────────────────────

#   Phase  range       INGEST UPDATE SUPERSEDE DELETE QUERY  total
#     1    op  1..100    60     0      0         0      40    100
#     2    op 101..180   30    20      0         0      30     80
#     3    op 181..280   20    15     15         0      50    100
#     4    op 281..360    0     5     15        10      50     80
#     5    op 361..400    0     0      0        10      30     40
#                       ───   ───    ───       ───    ───   ─────
#                       110    40     30        20    200    400

PHASE_PLAN = [
    {"ingest": 60, "update":  0, "supersede":  0, "delete":  0, "query": 40},
    {"ingest": 30, "update": 20, "supersede":  0, "delete":  0, "query": 30},
    {"ingest": 20, "update": 15, "supersede": 15, "delete":  0, "query": 50},
    {"ingest":  0, "update":  5, "supersede": 15, "delete": 10, "query": 50},
    {"ingest":  0, "update":  0, "supersede":  0, "delete": 10, "query": 30},
]
assert sum(p["ingest"]    for p in PHASE_PLAN) == 110
assert sum(p["update"]    for p in PHASE_PLAN) ==  40
assert sum(p["supersede"] for p in PHASE_PLAN) ==  30
assert sum(p["delete"]    for p in PHASE_PLAN) ==  20
assert sum(p["query"]     for p in PHASE_PLAN) == 200


def _interleave_phase(
    counts: Dict[str, int],
    cursors: Dict[str, int],
    ingest_pool: List[Tuple[str, str, str]],
    update_pool: List[Tuple[str, str, str]],
    supersede_pool: List[Tuple[str, str, str, str]],
    delete_pool: List[str],
    query_pool: List[str],
) -> List[dict]:
    """Round-robin interleave one phase's ops. Determinism source: the
    pool ordering and the cursor state. The interleave order within a
    phase is a fixed schedule (INGEST/QUERY/UPDATE/SUPERSEDE/DELETE)."""
    queue: List[str] = []
    # Build a stable schedule by repeating the order until budget exhausted.
    remaining = dict(counts)
    order = ["ingest", "query", "update", "supersede", "delete"]
    while sum(remaining.values()) > 0:
        for kind in order:
            if remaining[kind] > 0:
                queue.append(kind)
                remaining[kind] -= 1
    ops: List[dict] = []
    for kind in queue:
        idx = cursors[kind]
        cursors[kind] += 1
        if kind == "ingest":
            doc_id, title, text = ingest_pool[idx]
            ops.append({"op": "INGEST",
                        "args": {"doc_id": doc_id, "title": title, "text": text}})
        elif kind == "update":
            doc_id, title, text = update_pool[idx]
            ops.append({"op": "UPDATE",
                        "args": {"doc_id": doc_id, "title": title, "text": text}})
        elif kind == "supersede":
            old, new, title, text = supersede_pool[idx]
            ops.append({"op": "SUPERSEDE",
                        "args": {"old_doc_id": old, "doc_id": new,
                                 "title": title, "text": text}})
        elif kind == "delete":
            ops.append({"op": "DELETE",
                        "args": {"doc_id": delete_pool[idx]}})
        elif kind == "query":
            ops.append({"op": "QUERY",
                        "args": {"q": query_pool[idx]}})
    return ops


def build_scenario() -> Dict[str, Any]:
    ingest_pool    = _ingest_seq()
    update_pool    = _update_seq()
    supersede_pool = _supersede_seq()
    delete_pool    = _delete_seq()
    query_pool     = _query_pool()

    cursors = {"ingest": 0, "update": 0, "supersede": 0,
               "delete": 0, "query": 0}
    flat_ops: List[dict] = []
    for phase in PHASE_PLAN:
        flat_ops.extend(_interleave_phase(
            phase, cursors,
            ingest_pool, update_pool, supersede_pool,
            delete_pool, query_pool,
        ))
    assert len(flat_ops) == 400

    # ── checkpoint distribution: 40 checkpoints, every 10th op (1-based)
    # so op_id s2-010, s2-020, ..., s2-400 are checkpoints.
    out_ops: List[dict] = []
    for i, op in enumerate(flat_ops, start=1):
        op_id = f"s2-{i:03d}"
        checkpoint = (i % 10 == 0)
        out_ops.append({
            "op_id": op_id,
            "op": op["op"],
            "checkpoint": checkpoint,
            "args": op["args"],
        })

    return {
        "scenario": "S2",
        "name": "lifecycle-large",
        "spec": "v0.1.1",
        "description": (
            "Deterministic 400-op lifecycle scenario with a larger graph "
            "for activating the RF-cost axis. 110 INGEST, 40 UPDATE, "
            "30 SUPERSEDE (9 chains; avg length 3.33, max 5), 20 DELETE, "
            "200 QUERY; K=40 checkpoints. Synthetic public-domain English "
            "prose about a fictional city's operations (departments, "
            "projects, contracts, incidents, policies). Doc texts mention "
            "other doc_ids explicitly to give graph builders a non-trivial "
            "cross-reference density."
        ),
        "ops": out_ops,
    }


# ──────────────────────────────────────────────────────────────────────
# Cross-reference density check (pre-registration §2 obligation)
# ──────────────────────────────────────────────────────────────────────

import re

_DOC_ID_RE = re.compile(r"co-[a-z]+-\d{3}(?:-r\d+)?")


def _cross_ref_density(scenario: Dict[str, Any]) -> float:
    """Average count of doc_id mentions per content-bearing text body
    (INGEST + UPDATE + SUPERSEDE). Self-references are excluded."""
    total_mentions = 0
    total_texts = 0
    for op in scenario["ops"]:
        if op["op"] not in ("INGEST", "UPDATE", "SUPERSEDE"):
            continue
        text = op["args"].get("text", "") or ""
        # Identify the "self" doc id for this op (INGEST/UPDATE: doc_id;
        # SUPERSEDE: doc_id is the new one).
        self_id = op["args"].get("doc_id", "")
        mentions = {m for m in _DOC_ID_RE.findall(text)} - {self_id}
        total_mentions += len(mentions)
        total_texts += 1
    return total_mentions / max(total_texts, 1)


def _supersede_chain_stats(scenario: Dict[str, Any]) -> Dict[str, float]:
    """Compute observed chain stats from the assembled scenario for the
    pre-registration sentinel checks. Walks SUPERSEDE ops in order,
    grouping by the lineage seed (chain head)."""
    chains: Dict[str, int] = {}     # seed_id -> length
    # Track which super-doc id belongs to which seed lineage.
    new_to_seed: Dict[str, str] = {}
    for op in scenario["ops"]:
        if op["op"] != "SUPERSEDE":
            continue
        old = op["args"]["old_doc_id"]
        new = op["args"]["doc_id"]
        seed = new_to_seed.get(old, old)  # if old already in a chain
        chains[seed] = chains.get(seed, 0) + 1
        new_to_seed[new] = seed
    lengths = list(chains.values())
    return {
        "n_chains": len(lengths),
        "avg_length": sum(lengths) / max(len(lengths), 1),
        "max_length": max(lengths) if lengths else 0,
    }


def main() -> int:
    scenario = build_scenario()
    body = json.dumps(scenario, ensure_ascii=False, indent=2,
                      separators=(",", ": "))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body + "\n", encoding="utf-8")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    stats = _supersede_chain_stats(scenario)
    density = _cross_ref_density(scenario)
    print(f"wrote {OUT}")
    print(f"  ops             : {len(scenario['ops'])}")
    counts: Dict[str, int] = {}
    for op in scenario["ops"]:
        counts[op["op"]] = counts.get(op["op"], 0) + 1
    print(f"  distribution    : {counts}")
    print(f"  checkpoints     : "
          f"{sum(1 for o in scenario['ops'] if o['checkpoint'])}")
    print(f"  supersede chains: n={stats['n_chains']} "
          f"avg={stats['avg_length']:.2f} max={int(stats['max_length'])}")
    print(f"  cross-ref dens  : {density:.2f} (target >= 2.5)")
    print(f"  sha256          : {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
