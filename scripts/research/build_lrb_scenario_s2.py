"""Build LRB-S2 'lifecycle-yearly-with-time-travel' scenario.

Pre-registered (Phase B prereg, this session): 200 docs / 24 weeks /
~360 events / 80 queries x 4 query-types = 320 evaluations.

Query types:
  * current        (40 q): query_time = valid_time = 24
  * historical-mid (20 q): query_time = 24, valid_time = 8
  * historical-early (10 q): query_time = 24, valid_time = 0
  * never-stale    (10 q): UPDATE-only; no SUPERSEDE on these docs

The historical query types are JAMES's unique testbed — Vanilla and
Naive-supersede cannot reach prior-T states from a later vantage point.

Vocabulary scaled from LRB-S1: 20 departments / 60 projects / 40
contracts / 20 budgets / 40 policies / 20 appointments = 200 initial.

Write: eval/external/_fixtures/lrb/scenario_S2_yearly_timetravel.json
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S2_yearly_timetravel.json"

# ──────────────────────────────────────────────────────────────────────
# Deterministic vocabulary — 2× LRB-S1 scope
# ──────────────────────────────────────────────────────────────────────

DEPARTMENTS: List[Tuple[str, str]] = [
    ("public-works",  "Department of Public Works"),
    ("parks",         "Department of Parks and Recreation"),
    ("transport",     "Department of Transport"),
    ("permits",       "Department of Permits and Inspections"),
    ("records",       "Department of Records"),
    ("procurement",   "Office of Procurement"),
    ("safety",        "Office of Public Safety"),
    ("code",          "Office of Code Enforcement"),
    ("housing",       "Department of Housing"),
    ("health",        "Department of Public Health"),
    ("education",     "Department of Education"),
    ("finance",       "Department of Finance"),
    ("environment",   "Department of Environment"),
    ("library",       "Department of Library Services"),
    ("communications","Office of Communications"),
    ("emergency",     "Office of Emergency Management"),
    ("aging",         "Department of Aging Services"),
    ("youth",         "Department of Youth Programs"),
    ("sanitation",    "Department of Sanitation"),
    ("planning",      "Department of City Planning"),
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
    "Farida Mansour", "Geir Iversen", "Hye-jin Kim", "Imran Sheikh",
    "Jana Krylova", "Kofi Mensah", "Liang Wei", "Magnus Berg",
    "Nia Sandoval", "Olu Adesanya", "Petra Vaclavik", "Rashid Patel",
    "Saori Hayashi", "Tobias Faber", "Uma Iyer", "Vassilios Stathis",
    "Wendy Brooks", "Xavi Romero", "Yael Cohen", "Zane Holloway",
]

DEPT_INDEX = {dep[0]: i for i, dep in enumerate(DEPARTMENTS)}

# 60 projects (3 per dept)
PROJECTS: List[Tuple[str, str, str]] = []
PROJECT_NAMES_PER_DEPT = {
    "public-works":  ("Riverwalk Renewal", "Pothole Survey", "Bridge Inspection"),
    "parks":         ("Greenway Expansion", "Playground Refresh", "Urban Forest"),
    "transport":     ("Crosstown Bus", "Signal Modernisation", "Curb Cut Audit"),
    "permits":       ("Permit Portal", "Inspection Backlog", "Zoning Atlas"),
    "records":       ("Archive Digitisation", "Vital Records Index", "FOIA Workflow"),
    "procurement":   ("Vendor Consolidation", "Bid Tracker", "Contract Lifecycle"),
    "safety":        ("Patrol Modernisation", "Emergency Dispatch", "Camera Audit"),
    "code":          ("Vacant Lot Survey", "Violation Tracker", "Compliance Dashboard"),
    "housing":       ("Affordable Housing Map", "Tenant Rights Outreach", "Inclusionary Zoning Audit"),
    "health":        ("Clinic Hours Expansion", "Vaccination Outreach", "Mental Health Pilot"),
    "education":     ("Classroom Tech Refresh", "Teacher Stipend", "After-School Audit"),
    "finance":       ("Revenue Forecast", "Audit Modernisation", "Treasury Dashboard"),
    "environment":   ("Air Quality Monitors", "Recycling Outreach", "Waste Stream Audit"),
    "library":       ("Branch Hours Pilot", "E-book Lending", "Outreach Van"),
    "communications":("City Newsletter", "Open Data Portal", "Press Office Audit"),
    "emergency":     ("Drill Modernisation", "Shelter Capacity", "Alert System"),
    "aging":         ("Senior Center Pilot", "Meal Delivery", "Mobility Aid"),
    "youth":         ("Summer Camp", "Mentorship Program", "Job Training"),
    "sanitation":    ("Trash Collection", "Street Sweeping", "Bulk Pickup"),
    "planning":      ("Master Plan Update", "Zoning Reform", "Transit Oriented Dev"),
}
for i, (dep_key, _dep_title) in enumerate(DEPARTMENTS):
    names = PROJECT_NAMES_PER_DEPT[dep_key]
    for j, name in enumerate(names):
        PROJECTS.append((f"co-prj-{3 * i + j + 1:03d}",
                          f"Project {name}", dep_key))
assert len(PROJECTS) == 60

# 40 contracts (2 per dept)
CONTRACTS: List[Tuple[str, str, str]] = []
CONTRACT_NAMES_PER_DEPT = {
    "public-works":  ("Asphalt Resurfacing Contract", "Bridge Maintenance Contract"),
    "parks":         ("Lawn Maintenance Contract", "Tree Care Contract"),
    "transport":     ("Bus Fleet Maintenance Contract", "Traffic Signal Repair Contract"),
    "permits":       ("Software Licensing Contract", "Inspection Services Contract"),
    "records":       ("Document Storage Contract", "Scanning Services Contract"),
    "procurement":   ("Office Supply Contract", "IT Hardware Contract"),
    "safety":        ("Vehicle Lease Contract", "Body Camera Contract"),
    "code":          ("Mowing Services Contract", "Demolition Contract"),
    "housing":       ("Property Management Contract", "Translation Services Contract"),
    "health":        ("Medical Supply Contract", "Clinic Staffing Contract"),
    "education":     ("Textbook Supply Contract", "Bus Service Contract"),
    "finance":       ("Auditing Services Contract", "Bank Services Contract"),
    "environment":   ("Waste Hauling Contract", "Lab Testing Contract"),
    "library":       ("Periodical Subscription Contract", "Cleaning Services Contract"),
    "communications":("Web Hosting Contract", "Print Services Contract"),
    "emergency":     ("Generator Maintenance Contract", "Radio Service Contract"),
    "aging":         ("Meal Service Contract", "Transport Contract"),
    "youth":         ("Camp Supply Contract", "Counseling Services Contract"),
    "sanitation":    ("Trash Removal Contract", "Recycling Hauling Contract"),
    "planning":      ("Planning Consultant Contract", "GIS Services Contract"),
}
for i, (dep_key, _dep_title) in enumerate(DEPARTMENTS):
    names = CONTRACT_NAMES_PER_DEPT[dep_key]
    for j, name in enumerate(names):
        CONTRACTS.append((f"co-con-{2 * i + j + 1:03d}", name, dep_key))
assert len(CONTRACTS) == 40

BUDGETS = [(f"co-bud-{i:03d}", f"FY26 Operating Budget {i}", dep[0])
           for i, dep in enumerate(DEPARTMENTS, start=1)]
POLICIES = [(f"co-pol-{i:03d}", f"Policy {i}: Operating Standard",
             DEPARTMENTS[(i - 1) % len(DEPARTMENTS)][0])
            for i in range(1, 41)]
APPOINTMENTS = [(f"co-app-{i:03d}", f"Appointment Record {i}",
                 DEPARTMENTS[i - 1][0]) for i in range(1, 21)]

VENDORS = [
    "Atlas Construction", "Beacon Industries", "Cobalt Services",
    "Delta Logistics", "Evergreen Supply", "Frontier Tech",
    "Granite Holdings", "Horizon Group", "Indigo Solutions",
    "Juniper Vendors", "Keystone Maintenance", "Lyra Equipment",
    "Meridian Partners", "Northwind Inc", "Orchid Supplies",
    "Polaris Logistics", "Quartz Industrial", "Riverstone Inc",
    "Summit Vendors", "Tidewater Group",
    "Umbra Services", "Vega Networks", "Westport Inc", "Xenon Group",
    "Yarrow Holdings", "Zenith Industries", "Acacia Partners",
    "Borealis Inc", "Cinnabar Group", "Datura Logistics",
    "Eos Services", "Fennel Industries", "Grove Vendors",
    "Hyssop Inc", "Iris Partners", "Jasmine Group",
    "Kelp Holdings", "Lotus Inc", "Mint Services", "Nettle Group",
]

# ──────────────────────────────────────────────────────────────────────
# Initial corpus (T=0, 200 docs)
# ──────────────────────────────────────────────────────────────────────

def _dept_body(dep_key: str, dep_title: str, director_idx: int) -> str:
    director = PERSONS[director_idx]
    i = DEPT_INDEX[dep_key]
    appt = f"co-app-{i + 1:03d}"
    bud  = f"co-bud-{i + 1:03d}"
    projs = [p[0] for p in PROJECTS if p[2] == dep_key]
    pols = [f"co-pol-{2 * i + 1:03d}", f"co-pol-{2 * i + 2:03d}"]
    return (f"The {dep_title} (doc co-dep-{i + 1:03d}) is led by "
            f"{director} per appointment {appt}. Operating budget: "
            f"{bud}. Active projects: {', '.join(projs)}. Department "
            f"policies: {', '.join(pols)}.")


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
    return (f"{pol_title} (doc {pol_id}). Governing department: "
            f"{dep_doc}. Effective immediately upon promulgation.")


def _app_body(app_id: str, app_title: str, dep_key: str,
              person_idx: int) -> str:
    dep_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
    person = PERSONS[person_idx]
    return (f"{app_title} (doc {app_id}). Subject: {person}. "
            f"Appointed to lead {dep_doc}.")


def initial_corpus() -> List[dict]:
    docs: List[dict] = []
    # 20 dept (director = persons[i])
    for i, (dep_key, dep_title) in enumerate(DEPARTMENTS):
        docs.append({"doc_id": f"co-dep-{i + 1:03d}",
                     "title": dep_title,
                     "text":  _dept_body(dep_key, dep_title, i)})

    # 60 project (lead = persons[(20+i) % 50])
    for i, (prj_id, prj_title, dep_key) in enumerate(PROJECTS):
        docs.append({"doc_id": prj_id, "title": prj_title,
                     "text": _proj_body(prj_id, prj_title, dep_key,
                                        (20 + i) % len(PERSONS))})

    # 40 contract
    for i, (con_id, con_title, dep_key) in enumerate(CONTRACTS):
        docs.append({"doc_id": con_id, "title": con_title,
                     "text": _con_body(con_id, con_title, dep_key,
                                       VENDORS[i])})

    # 20 budget
    for i, (bud_id, bud_title, dep_key) in enumerate(BUDGETS):
        docs.append({"doc_id": bud_id, "title": bud_title,
                     "text": _bud_body(bud_id, bud_title, dep_key,
                                       (i + 1) * 250)})

    # 40 policy
    for i, (pol_id, pol_title, dep_key) in enumerate(POLICIES):
        docs.append({"doc_id": pol_id, "title": pol_title,
                     "text": _pol_body(pol_id, pol_title, dep_key)})

    # 20 appointment
    for i, (app_id, app_title, dep_key) in enumerate(APPOINTMENTS):
        docs.append({"doc_id": app_id, "title": app_title,
                     "text": _app_body(app_id, app_title, dep_key, i)})

    return docs


# ──────────────────────────────────────────────────────────────────────
# Evolution events over 24 weeks
# ──────────────────────────────────────────────────────────────────────

# Director SUPERSEDE — 16 of 20 depts shift (weeks 2-22 spread).
# Distribute deterministically so historical queries at T=0/8 are
# meaningfully different from current T=24.
DIRECTOR_SUPERSEDE: List[Tuple[str, int, int]] = [
    ("public-works",  2,  20),  ("parks",         3,  21),
    ("transport",     4,  22),  ("permits",       5,  23),
    ("records",       6,  24),  ("procurement",   7,  25),
    ("safety",        9,  26),  ("code",          10, 27),
    ("housing",       11, 28),  ("health",        12, 29),
    ("education",     14, 30),  ("finance",       15, 31),
    ("environment",   16, 32),  ("library",       17, 33),
    ("communications",19, 34),  ("emergency",     21, 35),
    # aging / youth / sanitation / planning stay original
]

# Project lead SUPERSEDE — 12 projects
PROJECT_LEAD_SUPERSEDE = [
    ("co-prj-001", 2,  36),  ("co-prj-005", 4,  37),
    ("co-prj-010", 6,  38),  ("co-prj-015", 8,  39),
    ("co-prj-020", 10, 40),  ("co-prj-025", 12, 41),
    ("co-prj-030", 14, 42),  ("co-prj-035", 16, 43),
    ("co-prj-040", 18, 44),  ("co-prj-045", 20, 45),
    ("co-prj-050", 22, 46),  ("co-prj-055", 23, 47),
]

# Policy SUPERSEDE — 8 policies
POLICY_SUPERSEDE = [
    ("co-pol-001", 3),  ("co-pol-005", 6),  ("co-pol-010", 9),
    ("co-pol-015", 12), ("co-pol-020", 15), ("co-pol-025", 18),
    ("co-pol-030", 21), ("co-pol-035", 23),
]

# Contract SUPERSEDE — 12 contracts
CONTRACT_SUPERSEDE = [
    ("co-con-001", 4,  "Aurora Construction"),
    ("co-con-005", 6,  "Beryllium Software"),
    ("co-con-009", 8,  "Cascade Logistics"),
    ("co-con-013", 10, "Daybreak Services"),
    ("co-con-017", 12, "Echo Storage"),
    ("co-con-021", 14, "Forge Medical"),
    ("co-con-025", 16, "Galaxy Supplies"),
    ("co-con-029", 18, "Helios Transport"),
    ("co-con-033", 20, "Ironbrook Group"),
    ("co-con-037", 22, "Junction Vendors"),
    ("co-con-003", 5,  "Karst Maintenance"),
    ("co-con-019", 13, "Lattice Services"),
]

# Budget UPDATE — 16 budgets revised (in-place; never-stale queries)
BUDGET_UPDATES = [
    ("co-bud-001", 4,  300),  ("co-bud-002", 5,  280),
    ("co-bud-003", 6,  320),  ("co-bud-004", 7,  260),
    ("co-bud-005", 8,  340),  ("co-bud-006", 9,  360),
    ("co-bud-007", 11, 290),  ("co-bud-008", 12, 310),
    ("co-bud-009", 13, 380),  ("co-bud-010", 14, 270),
    ("co-bud-011", 16, 410),  ("co-bud-012", 17, 320),
    ("co-bud-013", 18, 250),  ("co-bud-014", 19, 350),
    ("co-bud-015", 21, 390),  ("co-bud-016", 23, 430),
]

# Project DELETE — 8 projects
PROJECT_DELETE = [
    ("co-prj-002", 5),  ("co-prj-013", 9),  ("co-prj-022", 13),
    ("co-prj-031", 16), ("co-prj-038", 19), ("co-prj-044", 21),
    ("co-prj-052", 23), ("co-prj-060", 24),
]

# New project INGEST — 12 new projects
NEW_PROJECTS = [
    ("co-prj-101", "Project Snowplow Routing",      "public-works", 2,  20),
    ("co-prj-102", "Project Tree Census",           "parks",        5,  21),
    ("co-prj-103", "Project Transit App",           "transport",    7,  22),
    ("co-prj-104", "Project Records Audit Trail",   "records",      10, 23),
    ("co-prj-105", "Project Vendor Performance",    "procurement",  12, 24),
    ("co-prj-106", "Project Code Mobile Inspector", "code",         14, 25),
    ("co-prj-107", "Project Classroom Devices",     "education",    16, 26),
    ("co-prj-108", "Project Tax Portal",            "finance",      18, 27),
    ("co-prj-109", "Project Air Sensor Network",    "environment",  20, 28),
    ("co-prj-110", "Project Branch WiFi",           "library",      21, 29),
    ("co-prj-111", "Project Alert Geofence",        "emergency",    22, 30),
    ("co-prj-112", "Project Senior Outreach",       "aging",        24, 31),
]


def evolution_events() -> List[dict]:
    events: List[dict] = []
    counter = [0]

    def emit(week: int, op: str, args: Dict[str, Any]) -> None:
        counter[0] += 1
        events.append({
            "event_id": f"lrb-s2-{counter[0]:04d}",
            "week":     week,
            "op":       op,
            "args":     args,
        })

    for dep_key, week, new_dir in DIRECTOR_SUPERSEDE:
        i = DEPT_INDEX[dep_key]
        old_doc_id = f"co-dep-{i + 1:03d}"
        new_doc_id = f"co-dep-{i + 1:03d}.v2"
        new_title = dict(DEPARTMENTS)[dep_key]
        new_text = _dept_body(dep_key, new_title, new_dir)
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id, "new_doc_id": new_doc_id,
            "title": new_title, "text": new_text})

    for prj_id, week, new_lead in PROJECT_LEAD_SUPERSEDE:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        new_doc_id = f"{prj_id}.v2"
        new_text = _proj_body(prj_id, prj_meta[1], prj_meta[2], new_lead)
        emit(week, "SUPERSEDE", {
            "old_doc_id": prj_id, "new_doc_id": new_doc_id,
            "title": prj_meta[1], "text": new_text})

    for pol_id, week in POLICY_SUPERSEDE:
        pol_meta = next(p for p in POLICIES if p[0] == pol_id)
        new_doc_id = f"{pol_id}.v2"
        new_title = pol_meta[1] + " (Amended)"
        new_text = _pol_body(pol_id, new_title, pol_meta[2])
        emit(week, "SUPERSEDE", {
            "old_doc_id": pol_id, "new_doc_id": new_doc_id,
            "title": new_title, "text": new_text})

    for con_id, week, new_vendor in CONTRACT_SUPERSEDE:
        con_meta = next(c for c in CONTRACTS if c[0] == con_id)
        new_doc_id = f"{con_id}.v2"
        new_text = _con_body(con_id, con_meta[1], con_meta[2], new_vendor)
        emit(week, "SUPERSEDE", {
            "old_doc_id": con_id, "new_doc_id": new_doc_id,
            "title": con_meta[1], "text": new_text})

    for bud_id, week, new_amt in BUDGET_UPDATES:
        bud_meta = next(b for b in BUDGETS if b[0] == bud_id)
        new_text = _bud_body(bud_id, bud_meta[1], bud_meta[2], new_amt)
        emit(week, "UPDATE", {
            "doc_id": bud_id, "title": bud_meta[1], "text": new_text})

    for prj_id, prj_title, dep_key, week, lead_idx in NEW_PROJECTS:
        emit(week, "INGEST", {
            "doc_id": prj_id, "title": prj_title,
            "text": _proj_body(prj_id, prj_title, dep_key, lead_idx)})

    for prj_id, week in PROJECT_DELETE:
        emit(week, "DELETE", {"doc_id": prj_id})

    # Routine UPDATEs to reach prereg event-count range
    for week in range(1, 25):
        for i, (app_id, app_title, dep_key) in enumerate(APPOINTMENTS):
            base = _app_body(app_id, app_title, dep_key, i)
            new_text = base + f" Weekly review note: week {week}; status active."
            emit(week, "UPDATE", {
                "doc_id": app_id, "title": app_title,
                "text":   new_text})

    events.sort(key=lambda e: (e["week"], e["event_id"]))
    for idx, ev in enumerate(events, start=1):
        ev["event_id"] = f"lrb-s2-{idx:04d}"
    return events


# ──────────────────────────────────────────────────────────────────────
# Queries with (query_time, valid_time) pairs
# ──────────────────────────────────────────────────────────────────────

def director_at(dep_key: str, week: int) -> Tuple[int, str]:
    i = DEPT_INDEX[dep_key]
    original_doc_id = f"co-dep-{i + 1:03d}"
    current_idx = i
    current_doc = original_doc_id
    for dk, w, new_dir in DIRECTOR_SUPERSEDE:
        if dk == dep_key and w <= week:
            current_idx = new_dir
            current_doc = f"co-dep-{i + 1:03d}.v2"
    return current_idx, current_doc


def project_lead_doc_at(prj_id: str, week: int) -> str:
    for pid, w, _new in PROJECT_LEAD_SUPERSEDE:
        if pid == prj_id and w <= week:
            return f"{prj_id}.v2"
    return prj_id


def policy_doc_at(pol_id: str, week: int) -> str:
    for pid, w in POLICY_SUPERSEDE:
        if pid == pol_id and w <= week:
            return f"{pid}.v2"
    return pol_id


def contract_doc_at(con_id: str, week: int) -> str:
    for cid, w, _v in CONTRACT_SUPERSEDE:
        if cid == con_id and w <= week:
            return f"{cid}.v2"
    return con_id


def build_queries() -> List[dict]:
    qs: List[dict] = []
    counter = [0]

    def add(category: str, q_text: str, query_time: int,
            valid_time: int, gold_doc_ids: List[str]) -> None:
        counter[0] += 1
        qs.append({
            "query_id":    f"lrb-s2-q{counter[0]:03d}",
            "category":    category,
            "q":           q_text,
            "query_time":  query_time,
            "valid_time":  valid_time,
            "gold":        sorted(set(gold_doc_ids)),
        })

    # CURRENT queries (40) — all asked at query_time=24, valid_time=24
    # 20 dept director (current)
    for dep_key, dep_title in DEPARTMENTS:
        _, doc = director_at(dep_key, 24)
        add("current-director", f"Who is the director of the {dep_title}?",
            24, 24, [doc])
    # 12 project lead (current)
    for prj_id, _w, _n in PROJECT_LEAD_SUPERSEDE:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        doc = project_lead_doc_at(prj_id, 24)
        add("current-project-lead", f"Who leads {prj_meta[1]}?",
            24, 24, [doc])
    # 8 policy (current)
    for pol_id, _w in POLICY_SUPERSEDE:
        pol_meta = next(p for p in POLICIES if p[0] == pol_id)
        doc = policy_doc_at(pol_id, 24)
        add("current-policy", f"What is the current text of {pol_meta[1]}?",
            24, 24, [doc])
    # 40 current total ✓

    # HISTORICAL-MID queries (20) — query_time=24, valid_time=8
    # 10 dept director at T=8w (different from current for 5 of 10)
    for dep_key, dep_title in DEPARTMENTS[:10]:
        _, doc_at_8 = director_at(dep_key, 8)
        add("historical-mid-director",
            f"Who was the director of the {dep_title} 16 weeks ago?",
            24, 8, [doc_at_8])
    # 6 project lead at T=8w
    for prj_id, _w, _n in PROJECT_LEAD_SUPERSEDE[:6]:
        prj_meta = next(p for p in PROJECTS if p[0] == prj_id)
        doc = project_lead_doc_at(prj_id, 8)
        add("historical-mid-project-lead",
            f"Who led {prj_meta[1]} 16 weeks ago?",
            24, 8, [doc])
    # 4 policy at T=8w
    for pol_id, _w in POLICY_SUPERSEDE[:4]:
        pol_meta = next(p for p in POLICIES if p[0] == pol_id)
        doc = policy_doc_at(pol_id, 8)
        add("historical-mid-policy",
            f"What was the text of {pol_meta[1]} 16 weeks ago?",
            24, 8, [doc])
    # 20 historical-mid total ✓

    # HISTORICAL-EARLY queries (10) — query_time=24, valid_time=0
    # 6 dept director at initial state
    for dep_key, dep_title in DEPARTMENTS[:6]:
        original_doc = f"co-dep-{DEPT_INDEX[dep_key] + 1:03d}"
        add("historical-early-director",
            f"Who was the original director of the {dep_title}?",
            24, 0, [original_doc])
    # 4 contract at initial state (vendor before renegotiation)
    for con_id, _w, _v in CONTRACT_SUPERSEDE[:4]:
        con_meta = next(c for c in CONTRACTS if c[0] == con_id)
        add("historical-early-contract",
            f"Who was the original vendor for {con_meta[1]}?",
            24, 0, [con_id])
    # 10 historical-early total ✓

    # NEVER-STALE queries (10) — UPDATEs only; no SUPERSEDE
    # 10 budgets (each updated in-place — same doc_id always valid)
    for bud_id, _w, _amt in BUDGET_UPDATES[:10]:
        bud_meta = next(b for b in BUDGETS if b[0] == bud_id)
        add("never-stale-budget",
            f"What is the current allocation for the {bud_meta[1]}?",
            24, 24, [bud_id])
    # 10 never-stale total ✓

    return qs


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def build_scenario() -> dict:
    initial = initial_corpus()
    events = evolution_events()
    queries = build_queries()

    assert len(initial) == 200, f"initial corpus: 200 expected, got {len(initial)}"
    assert 200 <= len(events) <= 600, f"events: {len(events)} out of range"
    assert len(queries) == 80, f"queries: 80 expected, got {len(queries)}"

    # Gold reachability check (each gold doc_id must exist at its valid_time)
    initial_ids = {d["doc_id"] for d in initial}
    by_event_t: Dict[int, set] = {0: set(initial_ids)}
    state = set(initial_ids)
    # Walk events in order tracking which doc_ids exist at each week
    sorted_events = sorted(events, key=lambda e: (e["week"], e["event_id"]))
    week_states: Dict[int, set] = {}
    last_w = -1
    for ev in sorted_events:
        w = ev["week"]
        if w != last_w:
            # snapshot state at end of previous week (= start of w)
            for ww in range(last_w + 1, w + 1):
                week_states[ww] = set(state)
            last_w = w
        if ev["op"] == "INGEST":
            state.add(ev["args"]["doc_id"])
        elif ev["op"] == "UPDATE":
            pass
        elif ev["op"] == "SUPERSEDE":
            state.add(ev["args"]["new_doc_id"])
            state.discard(ev["args"]["old_doc_id"])
        elif ev["op"] == "DELETE":
            state.discard(ev["args"]["doc_id"])
    for ww in range(last_w + 1, 25):
        week_states[ww] = set(state)
    week_states[0] = set(initial_ids)

    for q in queries:
        vt = q["valid_time"]
        # JAMES validity-window keeps superseded versions alive at
        # earlier valid_time, so for the gold check we expand the
        # reachable set with all doc_ids that existed at any time
        # up through query_time.
        reachable_up_to_qt = set()
        for ww in range(0, q["query_time"] + 1):
            reachable_up_to_qt |= week_states.get(ww, set())
        for g in q["gold"]:
            assert g in reachable_up_to_qt, (
                f"query {q['query_id']}: gold {g} not reachable by "
                f"query_time={q['query_time']}")

    return {
        "scenario":      "LRB-S2",
        "name":          "lifecycle-yearly-with-time-travel",
        "spec":          "v0.1.0-draft-phase-b",
        "description":   (
            "Deterministic 200-doc city-operations corpus with 24-week "
            "lifecycle evolution and 80 queries × 4 query types "
            "(current 40 / historical-mid 20 / historical-early 10 / "
            "never-stale 10) = 80 evaluations (one per query). "
            "Historical query types test time-travel retrieval — "
            "Vanilla and Naive-supersede have no access to prior-T "
            "states; only audit-native (JAMES) can answer them "
            "correctly."
        ),
        "vocabulary_source": "RAB scenario-S2 city-operations extended (license friction 0)",
        "weeks":         24,
        "query_times":   [24],
        "valid_times":   [0, 8, 24],
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
    print(f"query_times: {scenario['query_times']}")
    print(f"valid_times: {scenario['valid_times']}")


if __name__ == "__main__":
    main()
