"""Build LRB-S1 'lifecycle-quarterly' scenario for LRB v0.1.0 draft.

Pre-registered (PR #783): 100 docs initial / 12 weeks evolution / ~200
lifecycle events / 60 queries x 3 timestamps (T=0 / T=6w / T=12w) = 180
evaluations. Deterministic; no randomness; no time-dependent inputs.

Vocabulary reused from RAB scenario-S2 (city-operations) per prereg
S1 design memo - license friction 0.

Write: eval/external/_fixtures/lrb/scenario_S1_quarterly.json

This script is the reproducibility witness; the JSON output sha gets
hash-pinned in every result.json file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "external" / "_fixtures" / "lrb" / "scenario_S1_quarterly.json"

# ──────────────────────────────────────────────────────────────────────
# Deterministic vocabulary (reused from RAB scenario-S2 city-operations)
# ──────────────────────────────────────────────────────────────────────

DEPARTMENTS: List[Tuple[str, str]] = [
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

# 30 projects, 3 per department
PROJECTS = [
    ("co-prj-001", "Project Riverwalk Renewal",         "public-works"),
    ("co-prj-002", "Project Pothole Survey",            "public-works"),
    ("co-prj-003", "Project Bridge Inspection",         "public-works"),
    ("co-prj-004", "Project Greenway Expansion",        "parks"),
    ("co-prj-005", "Project Playground Refresh",        "parks"),
    ("co-prj-006", "Project Urban Forest",              "parks"),
    ("co-prj-007", "Project Crosstown Bus",             "transport"),
    ("co-prj-008", "Project Signal Modernisation",      "transport"),
    ("co-prj-009", "Project Curb Cut Audit",            "transport"),
    ("co-prj-010", "Project Permit Portal",             "permits"),
    ("co-prj-011", "Project Inspection Backlog",        "permits"),
    ("co-prj-012", "Project Zoning Atlas",              "permits"),
    ("co-prj-013", "Project Archive Digitisation",      "records"),
    ("co-prj-014", "Project Vital Records Index",       "records"),
    ("co-prj-015", "Project FOIA Workflow",             "records"),
    ("co-prj-016", "Project Vendor Consolidation",      "procurement"),
    ("co-prj-017", "Project Bid Tracker",               "procurement"),
    ("co-prj-018", "Project Contract Lifecycle",        "procurement"),
    ("co-prj-019", "Project Patrol Modernisation",      "safety"),
    ("co-prj-020", "Project Emergency Dispatch",        "safety"),
    ("co-prj-021", "Project Camera Audit",              "safety"),
    ("co-prj-022", "Project Vacant Lot Survey",         "code"),
    ("co-prj-023", "Project Violation Tracker",         "code"),
    ("co-prj-024", "Project Compliance Dashboard",      "code"),
    ("co-prj-025", "Project Affordable Housing Map",    "housing"),
    ("co-prj-026", "Project Tenant Rights Outreach",    "housing"),
    ("co-prj-027", "Project Inclusionary Zoning Audit", "housing"),
    ("co-prj-028", "Project Clinic Hours Expansion",    "health"),
    ("co-prj-029", "Project Vaccination Outreach",      "health"),
    ("co-prj-030", "Project Mental Health Pilot",       "health"),
]

# 20 contracts (vendor + scope) - 2 per department deterministic
CONTRACTS = [
    ("co-con-001", "Asphalt Resurfacing Contract",     "public-works"),
    ("co-con-002", "Bridge Maintenance Contract",      "public-works"),
    ("co-con-003", "Lawn Maintenance Contract",        "parks"),
    ("co-con-004", "Tree Care Contract",               "parks"),
    ("co-con-005", "Bus Fleet Maintenance Contract",   "transport"),
    ("co-con-006", "Traffic Signal Repair Contract",   "transport"),
    ("co-con-007", "Software Licensing Contract",      "permits"),
    ("co-con-008", "Inspection Services Contract",     "permits"),
    ("co-con-009", "Document Storage Contract",        "records"),
    ("co-con-010", "Scanning Services Contract",       "records"),
    ("co-con-011", "Office Supply Contract",           "procurement"),
    ("co-con-012", "IT Hardware Contract",             "procurement"),
    ("co-con-013", "Vehicle Lease Contract",           "safety"),
    ("co-con-014", "Body Camera Contract",             "safety"),
    ("co-con-015", "Mowing Services Contract",         "code"),
    ("co-con-016", "Demolition Contract",              "code"),
    ("co-con-017", "Property Management Contract",     "housing"),
    ("co-con-018", "Translation Services Contract",    "housing"),
    ("co-con-019", "Medical Supply Contract",          "health"),
    ("co-con-020", "Clinic Staffing Contract",         "health"),
]

# 10 budgets, 20 policies, 10 appointments - deterministic
BUDGETS = [(f"co-bud-{i:03d}", f"FY26 Operating Budget {i}", dep)
           for i, (dep, _) in enumerate(DEPARTMENTS, start=1)]
POLICIES = [(f"co-pol-{i:03d}", f"Policy {i}: Operating Standard",
             DEPARTMENTS[(i - 1) % 10][0]) for i in range(1, 21)]
APPOINTMENTS = [(f"co-app-{i:03d}", f"Appointment Record {i}",
                 DEPARTMENTS[i - 1][0]) for i in range(1, 11)]


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _dept_body(dep_key: str, dep_title: str, director_idx: int) -> str:
    director = PERSONS[director_idx]
    appt = f"co-app-{DEPT_INDEX[dep_key] + 1:03d}"
    bud  = f"co-bud-{DEPT_INDEX[dep_key] + 1:03d}"
    projs = [p[0] for p in PROJECTS if p[2] == dep_key]
    return (f"The {dep_title} (doc co-dep-{DEPT_INDEX[dep_key] + 1:03d}) "
            f"is led by {director} per appointment {appt}. "
            f"Operating budget: {bud}. "
            f"Active projects: {', '.join(projs)}. "
            f"Department policies: co-pol-{2 * DEPT_INDEX[dep_key] + 1:03d}, "
            f"co-pol-{2 * DEPT_INDEX[dep_key] + 2:03d}.")


def _proj_body(prj_id: str, prj_title: str, dep_key: str,
               lead_idx: int) -> str:
    lead = PERSONS[lead_idx]
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    return (f"{prj_title} (doc {prj_id}) is a project of the "
            f"{dict(DEPARTMENTS)[dep_key]}. Project lead: {lead}. "
            f"Parent department: {dep_doc}.")


def _con_body(con_id: str, con_title: str, dep_key: str,
              vendor: str) -> str:
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    return (f"{con_title} (doc {con_id}). Vendor: {vendor}. "
            f"Awarding department: {dep_doc}.")


def _bud_body(bud_id: str, bud_title: str, dep_key: str,
              amount_thousands: int) -> str:
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    return (f"{bud_title} (doc {bud_id}). Department: {dep_doc}. "
            f"Allocation: ${amount_thousands} thousand.")


def _pol_body(pol_id: str, pol_title: str, dep_key: str) -> str:
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    return (f"{pol_title} (doc {pol_id}). Governing department: {dep_doc}. "
            f"Effective immediately upon promulgation.")


def _app_body(app_id: str, app_title: str, dep_key: str,
              person_idx: int) -> str:
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    person = PERSONS[person_idx]
    return (f"{app_title} (doc {app_id}). Subject: {person}. "
            f"Appointed to lead {dep_doc}.")


# Index of dep_key -> position (0..9)
DEPT_INDEX = {dep[0]: i for i, dep in enumerate(DEPARTMENTS)}

VENDORS = [
    "Atlas Construction", "Beacon Industries", "Cobalt Services",
    "Delta Logistics", "Evergreen Supply", "Frontier Tech",
    "Granite Holdings", "Horizon Group", "Indigo Solutions",
    "Juniper Vendors", "Keystone Maintenance", "Lyra Equipment",
    "Meridian Partners", "Northwind Inc", "Orchid Supplies",
    "Polaris Logistics", "Quartz Industrial", "Riverstone Inc",
    "Summit Vendors", "Tidewater Group",
]


# ──────────────────────────────────────────────────────────────────────
# Initial corpus (T=0, 100 docs)
# ──────────────────────────────────────────────────────────────────────

def initial_corpus() -> List[dict]:
    docs: List[dict] = []
    # 10 departments (director = persons[i])
    for i, (dep_key, dep_title) in enumerate(DEPARTMENTS):
        doc_id = f"co-dep-{i + 1:03d}"
        docs.append({"doc_id": doc_id, "title": dep_title,
                     "text": _dept_body(dep_key, dep_title, i)})

    # 30 projects (lead = persons[10 + i])
    for i, (prj_id, prj_title, dep_key) in enumerate(PROJECTS):
        docs.append({"doc_id": prj_id, "title": prj_title,
                     "text": _proj_body(prj_id, prj_title, dep_key,
                                        (10 + i) % 30)})

    # 20 contracts (vendor[i])
    for i, (con_id, con_title, dep_key) in enumerate(CONTRACTS):
        docs.append({"doc_id": con_id, "title": con_title,
                     "text": _con_body(con_id, con_title, dep_key,
                                       VENDORS[i])})

    # 10 budgets
    for i, (bud_id, bud_title, dep_key) in enumerate(BUDGETS):
        docs.append({"doc_id": bud_id, "title": bud_title,
                     "text": _bud_body(bud_id, bud_title, dep_key,
                                       (i + 1) * 250)})

    # 20 policies
    for i, (pol_id, pol_title, dep_key) in enumerate(POLICIES):
        docs.append({"doc_id": pol_id, "title": pol_title,
                     "text": _pol_body(pol_id, pol_title, dep_key)})

    # 10 appointments (person = persons[i])
    for i, (app_id, app_title, dep_key) in enumerate(APPOINTMENTS):
        docs.append({"doc_id": app_id, "title": app_title,
                     "text": _app_body(app_id, app_title, dep_key, i)})

    return docs


# ──────────────────────────────────────────────────────────────────────
# Evolution events over 12 weeks
# ──────────────────────────────────────────────────────────────────────

# Director change schedule: who, when (week), new-director-index
# 4 director SUPERSEDE in weeks 1-6, 4 more in weeks 7-12 — covers
# "T=6w shift" and "T=12w shift" query partitioning
DIRECTOR_SUPERSEDE = [
    # (dep_key, week, new_director_idx, new_doc_suffix)
    ("public-works", 2,  1,  "a"),   # Lena (0) -> Marcus (1)
    ("parks",        3,  2,  "a"),   # Marcus (1) -> Priya (2)
    ("transport",    5,  3,  "a"),   # Priya (2) -> Sofia (3)
    ("permits",      6,  4,  "a"),   # Sofia (3) -> Daniel (4)
    ("records",      8,  5,  "a"),
    ("procurement",  9,  6,  "a"),
    ("safety",       10, 7,  "a"),
    ("code",         12, 8,  "a"),
]

# Project lead SUPERSEDE - select 6 projects, spread weeks
PROJECT_LEAD_SUPERSEDE = [
    ("co-prj-001", 1,  20),
    ("co-prj-005", 4,  21),
    ("co-prj-010", 4,  22),
    ("co-prj-015", 7,  23),
    ("co-prj-020", 8,  24),
    ("co-prj-025", 11, 25),
]

# Policy SUPERSEDE - 4 policies revised
POLICY_SUPERSEDE = [
    ("co-pol-001", 2),
    ("co-pol-005", 5),
    ("co-pol-010", 8),
    ("co-pol-015", 11),
]

# Contract SUPERSEDE - 4 contracts renegotiated (new vendor)
CONTRACT_SUPERSEDE = [
    ("co-con-001", 3,  "Aurora Construction"),
    ("co-con-007", 6,  "Beryllium Software"),
    ("co-con-013", 9,  "Cascade Fleet"),
    ("co-con-019", 12, "Daybreak Medical"),
]

# Budget UPDATE schedule - 8 budget revisions (UPDATE, not SUPERSEDE)
BUDGET_UPDATES = [
    ("co-bud-001", 4,  300),
    ("co-bud-002", 4,  280),
    ("co-bud-003", 5,  320),
    ("co-bud-004", 7,  260),
    ("co-bud-005", 8,  340),
    ("co-bud-006", 9,  360),
    ("co-bud-007", 10, 290),
    ("co-bud-008", 11, 310),
]

# Project DELETE schedule - 4 projects cancelled (incl. some
# previously-superseded leads to test cascade semantics)
PROJECT_DELETE = [
    ("co-prj-002", 3),
    ("co-prj-013", 6),
    ("co-prj-022", 9),
    ("co-prj-027", 12),
]

# New project INGEST schedule - 6 new projects added
NEW_PROJECTS = [
    ("co-prj-101", "Project Snowplow Routing",       "public-works", 1,  26),
    ("co-prj-102", "Project Tree Census",            "parks",        4,  27),
    ("co-prj-103", "Project Transit App",            "transport",    6,  28),
    ("co-prj-104", "Project Records Audit Trail",    "records",      8,  29),
    ("co-prj-105", "Project Vendor Performance",     "procurement",  10, 0),
    ("co-prj-106", "Project Code Mobile Inspector",  "code",         12, 1),
]


def evolution_events() -> List[dict]:
    """Return ~200 events deterministically ordered by (week, op_idx)."""
    events: List[dict] = []
    counter = [0]

    def emit(week: int, op: str, args: Dict[str, Any]) -> None:
        counter[0] += 1
        events.append({
            "event_id": f"lrb-s1-{counter[0]:04d}",
            "week":     week,
            "op":       op,
            "args":     args,
        })

    # Director SUPERSEDE: emit new dep doc with same doc_id semantics —
    # for LRB Phase A we mark old doc with valid_to=week-1 and new with
    # valid_from=week. We emit SUPERSEDE with old/new payload.
    for dep_key, week, new_dir, _suffix in DIRECTOR_SUPERSEDE:
        i = DEPT_INDEX[dep_key]
        old_doc_id = f"co-dep-{i + 1:03d}"
        new_doc_id = f"co-dep-{i + 1:03d}.v2"
        new_title = dict(DEPARTMENTS)[dep_key]
        new_text = _dept_body(dep_key, new_title, new_dir)
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id,
            "new_doc_id": new_doc_id,
            "title": new_title,
            "text":  new_text,
        })

    # Project lead SUPERSEDE
    for prj_id, week, new_lead in PROJECT_LEAD_SUPERSEDE:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        new_doc_id = f"{prj_id}.v2"
        new_text = _proj_body(prj_id, prj_meta[1], prj_meta[2], new_lead)
        emit(week, "SUPERSEDE", {
            "old_doc_id": prj_id,
            "new_doc_id": new_doc_id,
            "title": prj_meta[1],
            "text":  new_text,
        })

    # Policy SUPERSEDE
    for pol_id, week in POLICY_SUPERSEDE:
        pol_meta = next(p for p in POLICIES if p[0] == pol_id)
        new_doc_id = f"{pol_id}.v2"
        new_title = pol_meta[1] + " (Amended)"
        new_text = _pol_body(pol_id, new_title, pol_meta[2])
        emit(week, "SUPERSEDE", {
            "old_doc_id": pol_id,
            "new_doc_id": new_doc_id,
            "title": new_title,
            "text":  new_text,
        })

    # Contract SUPERSEDE (new vendor)
    for con_id, week, new_vendor in CONTRACT_SUPERSEDE:
        con_meta = next(c for c in CONTRACTS if c[0] == con_id)
        new_doc_id = f"{con_id}.v2"
        new_text = _con_body(con_id, con_meta[1], con_meta[2], new_vendor)
        emit(week, "SUPERSEDE", {
            "old_doc_id": con_id,
            "new_doc_id": new_doc_id,
            "title": con_meta[1],
            "text":  new_text,
        })

    # Budget UPDATE (in-place; same doc_id, new text, no valid_to)
    for bud_id, week, new_amt in BUDGET_UPDATES:
        bud_meta = next(b for b in BUDGETS if b[0] == bud_id)
        new_text = _bud_body(bud_id, bud_meta[1], bud_meta[2], new_amt)
        emit(week, "UPDATE", {
            "doc_id": bud_id,
            "title":  bud_meta[1],
            "text":   new_text,
        })

    # New project INGEST
    for prj_id, prj_title, dep_key, week, lead_idx in NEW_PROJECTS:
        emit(week, "INGEST", {
            "doc_id": prj_id,
            "title":  prj_title,
            "text":   _proj_body(prj_id, prj_title, dep_key, lead_idx),
        })

    # Project DELETE
    for prj_id, week in PROJECT_DELETE:
        emit(week, "DELETE", {"doc_id": prj_id})

    # Routine UPDATEs to bulk event count to prereg range (~200).
    # These do NOT change answer-bearing facts (director/lead/vendor/
    # amount). They append a "Weekly review note: week N" sentence to
    # appointment docs (10 appt docs * 12 weeks = 120 routine UPDATEs).
    # Appointment docs are NOT primary gold for any query, so routine
    # updates don't perturb temporal-accuracy gold.
    for week in range(1, 13):
        for i, (app_id, app_title, dep_key) in enumerate(APPOINTMENTS):
            base = _app_body(app_id, app_title, dep_key, i)
            new_text = base + f" Weekly review note: week {week}; status active."
            emit(week, "UPDATE", {
                "doc_id": app_id,
                "title":  app_title,
                "text":   new_text,
            })

    # Sort by (week, event_id) so the timeline is deterministic
    events.sort(key=lambda e: (e["week"], e["event_id"]))
    # Re-assign event_id post-sort to maintain monotone order
    for idx, ev in enumerate(events, start=1):
        ev["event_id"] = f"lrb-s1-{idx:04d}"
    return events


# ──────────────────────────────────────────────────────────────────────
# Queries x 3 timestamps with per-T gold
# ──────────────────────────────────────────────────────────────────────

# Helper: who directs department X at week W (looking at DIRECTOR_SUPERSEDE)
def director_at(dep_key: str, week: int) -> Tuple[int, str]:
    """Return (person_idx, doc_id) of the director doc valid at `week`."""
    i = DEPT_INDEX[dep_key]
    original_doc_id = f"co-dep-{i + 1:03d}"
    # Initial director is persons[i]
    current_idx = i
    current_doc = original_doc_id
    for dk, w, new_dir, _ in DIRECTOR_SUPERSEDE:
        if dk == dep_key and w <= week:
            current_idx = new_dir
            current_doc = f"co-dep-{i + 1:03d}.v2"
    return current_idx, current_doc


def project_lead_at(prj_id: str, week: int) -> Tuple[int, str]:
    prj = next(p for p in PROJECTS if p[0] == prj_id)
    initial_idx = (10 + PROJECTS.index(prj)) % 30
    current_idx = initial_idx
    current_doc = prj_id
    for pid, w, new_lead in PROJECT_LEAD_SUPERSEDE:
        if pid == prj_id and w <= week:
            current_idx = new_lead
            current_doc = f"{prj_id}.v2"
    return current_idx, current_doc


def project_deleted_at(prj_id: str, week: int) -> bool:
    for pid, w in PROJECT_DELETE:
        if pid == prj_id and w <= week:
            return True
    return False


def project_exists_at(prj_id: str, week: int) -> bool:
    # All initial projects exist from week 0; new ones from week-of-ingest
    if prj_id.startswith("co-prj-1"):  # new projects 101-106
        for pid, _t, _d, w, _l in NEW_PROJECTS:
            if pid == prj_id:
                return w <= week
        return False
    if project_deleted_at(prj_id, week):
        return False
    return True


def policy_doc_at(pol_id: str, week: int) -> str:
    """Return policy doc_id valid at week (v2 if revised, original
    otherwise)."""
    for pid, w in POLICY_SUPERSEDE:
        if pid == pol_id and w <= week:
            return f"{pol_id}.v2"
    return pol_id


def contract_doc_at(con_id: str, week: int) -> Tuple[str, str]:
    """Return (doc_id, vendor) valid at week."""
    initial_vendor = VENDORS[CONTRACTS.index(
        next(c for c in CONTRACTS if c[0] == con_id))]
    for cid, w, new_vendor in CONTRACT_SUPERSEDE:
        if cid == con_id and w <= week:
            return f"{con_id}.v2", new_vendor
    return con_id, initial_vendor


# Build 60 deterministic queries:
# Q1-Q10: department director by name ("Who directs X?") - 8/10 shift
# Q11-Q16: project lead ("Who leads project Y?") - all 6 shift
# Q17-Q20: policy ("What does policy P stipulate?") - all 4 shift
# Q21-Q24: contract vendor ("Who is the vendor for contract C?") - all 4 shift
# Q25-Q32: budget ("What is the allocation for budget B?") - mix UPDATE
# Q33-Q42: stable - "What department oversees project X?" (10 queries, never shift)
# Q43-Q52: stable - "What is the parent department of contract X?" (10 queries)
# Q53-Q60: new projects ("What is the lead of project co-prj-10X?")
#          - existence shifts (don't exist at T=0)


def build_queries() -> List[dict]:
    qs: List[dict] = []
    counter = [0]

    def add_q(q_text: str, gold_t0: List[str], gold_t6: List[str],
              gold_t12: List[str], category: str) -> None:
        counter[0] += 1
        qs.append({
            "query_id": f"lrb-s1-q{counter[0]:03d}",
            "category": category,
            "q":        q_text,
            "gold": {
                "T=0":   sorted(set(gold_t0)),
                "T=6w":  sorted(set(gold_t6)),
                "T=12w": sorted(set(gold_t12)),
            },
        })

    # Q1-Q10: department director queries
    for dep_key, dep_title in DEPARTMENTS:
        _, doc_t0 = director_at(dep_key, 0)
        _, doc_t6 = director_at(dep_key, 6)
        _, doc_t12 = director_at(dep_key, 12)
        add_q(
            f"Who is the director of the {dep_title}?",
            [doc_t0], [doc_t6], [doc_t12],
            "director-shift",
        )

    # Q11-Q16: project lead (6 projects with superseded lead)
    for prj_id, _w, _new in PROJECT_LEAD_SUPERSEDE:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        _, doc_t0 = project_lead_at(prj_id, 0)
        _, doc_t6 = project_lead_at(prj_id, 6)
        _, doc_t12 = project_lead_at(prj_id, 12)
        add_q(
            f"Who leads {prj_meta[1]}?",
            [doc_t0], [doc_t6], [doc_t12],
            "project-lead-shift",
        )

    # Q17-Q20: policy (4 superseded)
    for pol_id, _w in POLICY_SUPERSEDE:
        pol_meta = next(p for p in POLICIES if p[0] == pol_id)
        add_q(
            f"What is the current text of {pol_meta[1]}?",
            [policy_doc_at(pol_id, 0)],
            [policy_doc_at(pol_id, 6)],
            [policy_doc_at(pol_id, 12)],
            "policy-amend",
        )

    # Q21-Q24: contract vendor (4 superseded)
    for con_id, _w, _v in CONTRACT_SUPERSEDE:
        con_meta = next(c for c in CONTRACTS if c[0] == con_id)
        doc_t0, _v0 = contract_doc_at(con_id, 0)
        doc_t6, _v6 = contract_doc_at(con_id, 6)
        doc_t12, _v12 = contract_doc_at(con_id, 12)
        add_q(
            f"Who is the current vendor for {con_meta[1]}?",
            [doc_t0], [doc_t6], [doc_t12],
            "contract-vendor-shift",
        )

    # Q25-Q32: budget allocation queries (8 UPDATEs)
    # UPDATE = same doc_id, but content changed; gold is single doc_id
    # at all timestamps (validity = always-current after UPDATE)
    for bud_id, _w, _amt in BUDGET_UPDATES:
        bud_meta = next(b for b in BUDGETS if b[0] == bud_id)
        add_q(
            f"What is the current allocation for the {bud_meta[1]}?",
            [bud_id], [bud_id], [bud_id],
            "budget-update",
        )

    # Q33-Q42: stable - parent department of project (10 queries)
    # Not affected by SUPERSEDE because the original dep doc is in the
    # answer doc set even after director change.
    for prj_id, prj_title, dep_key in PROJECTS[:10]:
        # Gold = the dep doc current at that time (may shift if director
        # superseded). For stability we ask about the project doc.
        # Gold = project doc valid at T (or empty if deleted).
        gold_t0 = [prj_id] if project_exists_at(prj_id, 0) else []
        # If prj_id is in PROJECT_LEAD_SUPERSEDE then doc shifts to .v2
        if any(pid == prj_id for pid, w, _n in PROJECT_LEAD_SUPERSEDE):
            _, doc_t6 = project_lead_at(prj_id, 6)
            _, doc_t12 = project_lead_at(prj_id, 12)
            gold_t6 = [doc_t6] if project_exists_at(prj_id, 6) else []
            gold_t12 = [doc_t12] if project_exists_at(prj_id, 12) else []
        else:
            gold_t6 = [prj_id] if project_exists_at(prj_id, 6) else []
            gold_t12 = [prj_id] if project_exists_at(prj_id, 12) else []
        add_q(
            f"What is the project record for {prj_title}?",
            gold_t0, gold_t6, gold_t12,
            "project-record-lookup",
        )

    # Q43-Q52: contract record (stable for un-superseded; shifts for
    # superseded)
    for con_id, con_title, dep_key in CONTRACTS[:10]:
        doc_t0, _ = contract_doc_at(con_id, 0)
        doc_t6, _ = contract_doc_at(con_id, 6)
        doc_t12, _ = contract_doc_at(con_id, 12)
        add_q(
            f"What is the current contract record for {con_title}?",
            [doc_t0], [doc_t6], [doc_t12],
            "contract-record-lookup",
        )

    # Q53-Q58: new project existence (existence axis: empty at T=0)
    for prj_id, prj_title, dep_key, ingest_w, _l in NEW_PROJECTS:
        gold_t0 = [prj_id] if ingest_w <= 0 else []
        gold_t6 = [prj_id] if ingest_w <= 6 else []
        gold_t12 = [prj_id] if ingest_w <= 12 else []
        add_q(
            f"What is the project record for {prj_title}?",
            gold_t0, gold_t6, gold_t12,
            "new-project-existence",
        )

    # Q59-Q60: deleted-project negative existence (gold empty at later T)
    # Tests that SUT correctly returns empty/abstains for deleted docs
    for prj_id, del_week in PROJECT_DELETE[:2]:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        gold_t0 = [prj_id]
        gold_t6 = [prj_id] if del_week > 6 else []
        gold_t12 = [prj_id] if del_week > 12 else []
        add_q(
            f"What is the current project record for {prj_meta[1]}?",
            gold_t0, gold_t6, gold_t12,
            "deleted-project-negative",
        )

    return qs[:60]


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def build_scenario() -> dict:
    initial = initial_corpus()
    events = evolution_events()
    queries = build_queries()

    # Validation
    assert len(initial) == 100, f"initial corpus must be 100 docs, got {len(initial)}"
    assert 150 <= len(events) <= 250, f"events out of expected range: {len(events)}"
    assert len(queries) == 60, f"queries must be 60, got {len(queries)}"

    # Per-query gold must list only doc_ids that are reachable
    all_initial_ids = {d["doc_id"] for d in initial}
    new_ids = {ev["args"]["new_doc_id"] for ev in events if ev["op"] == "SUPERSEDE"}
    new_ingest_ids = {ev["args"]["doc_id"] for ev in events if ev["op"] == "INGEST"}
    all_reachable = all_initial_ids | new_ids | new_ingest_ids
    for q in queries:
        for ts, gold in q["gold"].items():
            for gid in gold:
                assert gid in all_reachable, (
                    f"query {q['query_id']} gold {gid} at {ts} not reachable")

    return {
        "scenario":      "LRB-S1",
        "name":          "lifecycle-quarterly",
        "spec":          "v0.1.0-draft",
        "description":   (
            "Deterministic 100-doc city-operations corpus with 12-week "
            "lifecycle evolution and 60 queries * 3 timestamps (T=0 / "
            "T=6w / T=12w) = 180 evaluations. SUPERSEDE events shift "
            "the valid-at-T document for 8 of 10 departments, 6 of 30 "
            "projects, 4 of 20 policies, 4 of 20 contracts. UPDATE "
            "events revise 8 of 10 budgets in-place. DELETE removes 4 "
            "projects. INGEST adds 6 new projects. The temporal-accuracy "
            "axis tests whether a SUT correctly retrieves the doc valid "
            "at T rather than a stale/superseded one."
        ),
        "vocabulary_source": "RAB scenario-S2 city-operations (license friction 0)",
        "weeks":         12,
        "timestamps":    ["T=0", "T=6w", "T=12w"],
        "initial_corpus": initial,
        "events":        events,
        "queries":       queries,
    }


def main() -> None:
    scenario = build_scenario()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(scenario, ensure_ascii=False, sort_keys=False, indent=2)
    OUT.write_text(text, encoding="utf-8")

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"wrote: {OUT.relative_to(ROOT)}")
    print(f"sha256: {sha}")
    print(f"docs: {len(scenario['initial_corpus'])}")
    print(f"events: {len(scenario['events'])}")
    print(f"queries: {len(scenario['queries'])}")
    print(f"timestamps: {scenario['timestamps']}")


if __name__ == "__main__":
    main()
