"""Build LRB-S3 'publication-scale-time-travel' scenario for LRB v0.2.3.

Pre-registered (`docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md`):
publication-tier extension of the S2 'lifecycle-yearly-with-time-travel'
benchmark. Same 4 query types, same schema, same gold reachability
invariants. Vocabulary scaled ~5x via programmatic templated naming so
the generator stays maintainable instead of hand-curating 1000 entries.

Default scale (`--scale publication`):
  * 100 departments
  * 300 projects (3 per dept)
  * 200 contracts (2 per dept)
  * 100 budgets (1 per dept)
  * 200 policies (2 per dept)
  * 100 appointments (1 per dept)
  ─────────────────────────────────
  * 1000 initial docs total
  * 52 weeks
  * ~10k events (proportional to S2 base rate)
  * 1000 queries x 4 categories (500 current + 200 historical-mid +
    100 historical-early + 200 never-stale)

Smaller presets:
  * `--scale smoke`  -> 100 docs / ~500 events / 100 queries (CI-safe)
  * `--scale dev`    -> 300 docs / ~2k events / 300 queries

Schema-identical to S2: existing `eval/external/lrb/driver.py` consumes
the output without changes. The fixture file is written separately so
it does NOT clobber the S2 fixture used by published artifacts.

Writes: eval/external/_fixtures/lrb/scenario_S3_publication.json
        (default; `--out` overrides for smoke / dev presets)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S3_publication.json"


# ──────────────────────────────────────────────────────────────────────
# Scale presets
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScalePreset:
    """All parameters needed to generate one scenario at a given scale.

    Hand-tuned so the four query buckets stay proportional to S2 and
    the event/dept ratio remains comparable to a real organisation's
    lifecycle. Operators may override individual fields via CLI for
    custom experiments.
    """
    name: str
    n_dept: int
    projects_per_dept: int
    contracts_per_dept: int
    policies_per_dept: int
    budgets_per_dept: int
    appointments_per_dept: int
    weeks: int
    # Supersede / update densities, expressed as a fraction of the
    # pool size; we use deterministic stride sampling, not random.
    director_supersede_frac: float
    project_supersede_frac: float
    contract_supersede_frac: float
    policy_supersede_frac: float
    project_delete_frac: float
    new_project_frac: float
    budget_update_frac: float
    # Query counts per category. The category total = (current +
    # historical-mid + historical-early + never-stale) caps the total
    # query count for that preset.
    queries_current: int
    queries_historical_mid: int
    queries_historical_early: int
    queries_never_stale: int


SMOKE = ScalePreset(
    name="smoke",
    n_dept=10, projects_per_dept=3, contracts_per_dept=2,
    policies_per_dept=2, budgets_per_dept=1, appointments_per_dept=1,
    weeks=24,
    director_supersede_frac=0.5, project_supersede_frac=0.3,
    contract_supersede_frac=0.3, policy_supersede_frac=0.3,
    project_delete_frac=0.2, new_project_frac=0.3,
    budget_update_frac=0.7,
    queries_current=50, queries_historical_mid=20,
    queries_historical_early=15, queries_never_stale=15,
)


DEV = ScalePreset(
    name="dev",
    n_dept=30, projects_per_dept=3, contracts_per_dept=2,
    policies_per_dept=2, budgets_per_dept=1, appointments_per_dept=1,
    weeks=36,
    director_supersede_frac=0.5, project_supersede_frac=0.3,
    contract_supersede_frac=0.3, policy_supersede_frac=0.3,
    project_delete_frac=0.2, new_project_frac=0.3,
    budget_update_frac=0.7,
    queries_current=150, queries_historical_mid=60,
    queries_historical_early=45, queries_never_stale=45,
)


PUBLICATION = ScalePreset(
    name="publication",
    n_dept=100, projects_per_dept=3, contracts_per_dept=2,
    policies_per_dept=2, budgets_per_dept=1, appointments_per_dept=1,
    weeks=52,
    director_supersede_frac=0.5, project_supersede_frac=0.3,
    contract_supersede_frac=0.3, policy_supersede_frac=0.3,
    project_delete_frac=0.2, new_project_frac=0.3,
    budget_update_frac=0.7,
    queries_current=500, queries_historical_mid=200,
    queries_historical_early=100, queries_never_stale=200,
)


PRESETS: Dict[str, ScalePreset] = {p.name: p for p in (
    SMOKE, DEV, PUBLICATION)}


# ──────────────────────────────────────────────────────────────────────
# Deterministic vocabulary primitives
# ──────────────────────────────────────────────────────────────────────


# 20 adjectives x 10 domains = 200 unique department titles (more than
# the publication preset's 100). Adjectives drawn from real municipal /
# civic terminology so the prompts read naturally.
DEPT_ADJECTIVES: Tuple[str, ...] = (
    "Public", "Municipal", "Civic", "Urban", "Metropolitan", "Regional",
    "City", "District", "County", "Borough", "Community", "Citywide",
    "Neighborhood", "Local", "Township", "Ward", "Precinct",
    "Riverfront", "Coastal", "Central",
)

DEPT_DOMAINS: Tuple[str, ...] = (
    "Works", "Health", "Safety", "Records", "Procurement",
    "Housing", "Education", "Transportation", "Environment",
    "Communications",
)

# 50 first names x 40 last names = 2000 unique persons (any reasonable
# scale fits without collision).
FIRST_NAMES: Tuple[str, ...] = (
    "Lena", "Marcus", "Priya", "Sofia", "Daniel", "Tomas", "Hana",
    "Idris", "Junko", "Karim", "Lucia", "Mehmet", "Nadia", "Oscar",
    "Pia", "Quentin", "Rosa", "Samir", "Tara", "Ulrich", "Vivian",
    "Wei", "Xochitl", "Yusuf", "Zara", "Aiko", "Bjorn", "Camila",
    "Devon", "Eitan", "Farah", "Gerald", "Helga", "Ian", "Jamila",
    "Kenji", "Leila", "Mateo", "Nora", "Olivier", "Petra", "Qadir",
    "Riya", "Sven", "Talia", "Uma", "Vasco", "Wren", "Yuki", "Zane",
)

LAST_NAMES: Tuple[str, ...] = (
    "Ortiz", "Chen", "Anand", "Reyes", "Okoye", "Eriksen", "Park",
    "Mwangi", "Watanabe", "El-Sayed", "Bianchi", "Aydin", "Hassan",
    "Lindgren", "Novak", "Aubert", "Delgado", "Khoury", "Joshi",
    "Bauer", "Cho", "Tan", "Mendez", "Demir", "Khan", "Tanaka",
    "Holm", "Souza", "Pratt", "Levy", "Adler", "Bahar", "Conti",
    "Diaz", "Esposito", "Fenton", "Garza", "Hoshino", "Ivanov",
    "Jensen",
)


# 20 verbs x 20 nouns = 400 unique project titles per dept.
PROJECT_VERBS: Tuple[str, ...] = (
    "Renewal", "Survey", "Inspection", "Expansion", "Refresh",
    "Modernisation", "Audit", "Tracker", "Mobile", "Backlog",
    "Outreach", "Census", "Dashboard", "Atlas", "Pilot",
    "Lifecycle", "Routing", "Monitor", "Network", "Portal",
)

PROJECT_NOUNS: Tuple[str, ...] = (
    "Riverwalk", "Pothole", "Bridge", "Greenway", "Playground",
    "Crosstown", "Signal", "Curb", "Permit", "Inspection",
    "Zoning", "Archive", "FOIA", "Vendor", "Bid",
    "Contract", "Patrol", "Emergency", "Camera", "Compliance",
)


VENDOR_PREFIXES: Tuple[str, ...] = (
    "Atlas", "Beacon", "Cobalt", "Delta", "Evergreen",
    "Frontier", "Granite", "Horizon", "Indigo", "Juniper",
    "Keystone", "Lyra", "Meridian", "Northwind", "Orchid",
    "Polaris", "Quartz", "Riverstone", "Summit", "Tidewater",
)

VENDOR_SUFFIXES: Tuple[str, ...] = (
    "Construction", "Industries", "Services", "Logistics", "Supply",
    "Tech", "Holdings", "Group", "Solutions", "Vendors",
    "Maintenance", "Equipment", "Partners", "Inc", "Supplies",
)


def make_dept(idx: int) -> Tuple[str, str]:
    """Returns (dept_key, dept_title) for the idx-th dept.

    Deterministic mapping idx -> (adj, domain). Title format mirrors
    real organisations: 'Department of {Adj} {Domain}'."""
    if idx < 0:
        raise ValueError(f"dept idx must be non-negative; got {idx!r}")
    adj_n = len(DEPT_ADJECTIVES)
    dom_n = len(DEPT_DOMAINS)
    adj = DEPT_ADJECTIVES[idx % adj_n]
    dom = DEPT_DOMAINS[(idx // adj_n) % dom_n]
    key = f"dept-{idx + 1:04d}"
    title = f"Department of {adj} {dom}"
    return key, title


def make_person(idx: int) -> str:
    """Returns the idx-th person name (cycled deterministically)."""
    if idx < 0:
        raise ValueError(f"person idx must be non-negative; got {idx!r}")
    fn_n = len(FIRST_NAMES)
    ln_n = len(LAST_NAMES)
    first = FIRST_NAMES[idx % fn_n]
    last = LAST_NAMES[(idx // fn_n) % ln_n]
    return f"{first} {last}"


def make_project(dept_idx: int, prj_idx: int) -> Tuple[str, str]:
    """Returns (prj_id, prj_title) for the prj_idx-th project in dept_idx.

    Project IDs use global index so the loader can dedup easily.
    """
    global_idx = dept_idx * 1000 + prj_idx + 1
    verb = PROJECT_VERBS[(dept_idx + prj_idx) % len(PROJECT_VERBS)]
    noun = PROJECT_NOUNS[(dept_idx * 7 + prj_idx * 3) % len(PROJECT_NOUNS)]
    return f"prj-{global_idx:06d}", f"Project {noun} {verb}"


# Contract title vocabulary — 30 domains × 7 types = 210 unique titles
# (more than the publication preset's 200 contracts so no collision).
# Single-template "{verb} Services Contract" naming (pre-S3.1) caused
# retrieval cluster collapse: all 200 contracts had "Services Contract"
# substring, so BM25 / embedding retrieval couldn't disambiguate among
# them, driving current-contract R@10 to 0.0 across all SUTs. Per-domain
# distinctive nouns + multiple agreement types restore retrieval
# distinguishability without touching the rest of the generator.
CONTRACT_DOMAINS: Tuple[str, ...] = (
    "Asphalt Resurfacing", "Bridge Maintenance", "Lawn Care",
    "Tree Pruning", "Bus Fleet", "Traffic Signal Repair",
    "Software Licensing", "Inspection Services", "Document Storage",
    "Scanning Services", "Office Supply", "IT Hardware",
    "Vehicle Lease", "Body Camera", "Mowing Operations",
    "Demolition", "Property Management", "Translation Services",
    "Medical Supply", "Clinic Staffing", "Snowplow Operations",
    "Tree Census", "Transit App Development", "Records Audit",
    "Vendor Performance Monitoring", "Mobile Inspection",
    "Classroom Devices", "Tax Portal", "Air Sensor Network",
    "Branch WiFi Provisioning",
)

CONTRACT_TYPES: Tuple[str, ...] = (
    "Contract", "Agreement", "Purchase Order",
    "Master Service Agreement", "Statement of Work",
    "Maintenance Agreement", "Service Order",
)


def make_contract(dept_idx: int, con_idx: int,
                  vendor: str,
                  contracts_per_dept: int = 2) -> Tuple[str, str]:
    """Returns (con_id, con_title) for the con_idx-th contract in dept_idx.

    Title format: ``{DOMAIN} {TYPE}`` where the global contract index
    ``(dept_idx * contracts_per_dept + con_idx)`` enumerates the unique
    (domain, type) pairs deterministically. With 30 domains × 7 types
    = 210 pairs, scenarios up to 210 contracts get unique titles.

    Replaces the pre-S3.1 single-template ``"{verb} Services Contract"``
    which caused retrieval cluster collapse on current-contract queries
    (R@10=0.0 across all 3 SUTs at S3 publication; see
    `docs/research/lrb-v023-s3-publication-scale-results-2026-06-12.md`
    §4).
    """
    global_idx_doc = dept_idx * 1000 + con_idx + 1
    global_idx_pair = dept_idx * contracts_per_dept + con_idx
    domain = CONTRACT_DOMAINS[global_idx_pair % len(CONTRACT_DOMAINS)]
    ctype = CONTRACT_TYPES[(global_idx_pair // len(CONTRACT_DOMAINS))
                           % len(CONTRACT_TYPES)]
    return (f"con-{global_idx_doc:06d}", f"{domain} {ctype}")


def make_vendor(idx: int) -> str:
    pn = len(VENDOR_PREFIXES)
    sn = len(VENDOR_SUFFIXES)
    return f"{VENDOR_PREFIXES[idx % pn]} {VENDOR_SUFFIXES[(idx // pn) % sn]}"


def make_budget(dept_idx: int, bud_idx: int) -> Tuple[str, str]:
    global_idx = dept_idx * 1000 + bud_idx + 1
    return f"bud-{global_idx:06d}", f"FY26 Operating Budget {global_idx}"


def make_policy(dept_idx: int, pol_idx: int) -> Tuple[str, str]:
    global_idx = dept_idx * 1000 + pol_idx + 1
    return f"pol-{global_idx:06d}", f"Policy {global_idx}: Operating Standard"


def make_appointment(dept_idx: int, app_idx: int) -> Tuple[str, str]:
    global_idx = dept_idx * 1000 + app_idx + 1
    return f"app-{global_idx:06d}", f"Appointment Record {global_idx}"


# ──────────────────────────────────────────────────────────────────────
# Doc body builders
# ──────────────────────────────────────────────────────────────────────


def _dept_body(dept_idx: int, dept_title: str,
               projects: List[Tuple[str, str]],
               policies: List[Tuple[str, str]]) -> str:
    director = make_person(dept_idx)
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    app_id = f"app-{dept_idx * 1000 + 1:06d}"
    bud_id = f"bud-{dept_idx * 1000 + 1:06d}"
    prj_ids = ", ".join(p[0] for p in projects)
    pol_ids = ", ".join(p[0] for p in policies)
    return (f"The {dept_title} (doc {dept_doc}) is led by {director} "
            f"per appointment {app_id}. Operating budget: {bud_id}. "
            f"Active projects: {prj_ids}. "
            f"Department policies: {pol_ids}.")


def _proj_body(prj_id: str, prj_title: str, dept_idx: int,
               lead_idx: int) -> str:
    lead = make_person(lead_idx)
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    return (f"{prj_title} (doc {prj_id}) is a project of department "
            f"{dept_doc}. Project lead: {lead}. "
            f"Parent department: {dept_doc}.")


def _con_body(con_id: str, con_title: str, dept_idx: int,
              vendor: str) -> str:
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    return (f"{con_title} (doc {con_id}). Vendor: {vendor}. "
            f"Awarding department: {dept_doc}.")


def _bud_body(bud_id: str, bud_title: str, dept_idx: int,
              amount_thousands: int) -> str:
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    return (f"{bud_title} (doc {bud_id}). Department: {dept_doc}. "
            f"Allocation: ${amount_thousands} thousand.")


def _pol_body(pol_id: str, pol_title: str, dept_idx: int) -> str:
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    return (f"{pol_title} (doc {pol_id}). Governing department: "
            f"{dept_doc}. Effective immediately upon promulgation.")


def _app_body(app_id: str, app_title: str, dept_idx: int,
              person_idx: int) -> str:
    dept_doc = f"co-dep-{dept_idx + 1:04d}"
    person = make_person(person_idx)
    return (f"{app_title} (doc {app_id}). Subject: {person}. "
            f"Appointed to lead {dept_doc}.")


# ──────────────────────────────────────────────────────────────────────
# Per-scale corpus enumeration
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CorpusPlan:
    """Frozen enumeration of every entity in the scenario.

    Built once per `build_scenario` call. Keeps the supersede / event /
    query generators trivially deterministic — they read indices off
    this plan rather than recomputing.
    """
    n_dept: int
    dept_keys: Tuple[str, ...]
    dept_titles: Tuple[str, ...]
    projects: Tuple[Tuple[str, str, int], ...]    # (prj_id, title, dept_idx)
    contracts: Tuple[Tuple[str, str, int, str], ...]   # +vendor
    budgets: Tuple[Tuple[str, str, int], ...]
    policies: Tuple[Tuple[str, str, int], ...]
    appointments: Tuple[Tuple[str, str, int], ...]


def build_corpus_plan(preset: ScalePreset) -> CorpusPlan:
    dept_keys: List[str] = []
    dept_titles: List[str] = []
    for i in range(preset.n_dept):
        k, t = make_dept(i)
        dept_keys.append(k)
        dept_titles.append(t)

    projects: List[Tuple[str, str, int]] = []
    for di in range(preset.n_dept):
        for pi in range(preset.projects_per_dept):
            pid, ptitle = make_project(di, pi)
            projects.append((pid, ptitle, di))

    contracts: List[Tuple[str, str, int, str]] = []
    for di in range(preset.n_dept):
        for ci in range(preset.contracts_per_dept):
            vendor = make_vendor(di * preset.contracts_per_dept + ci)
            cid, ctitle = make_contract(
                di, ci, vendor,
                contracts_per_dept=preset.contracts_per_dept)
            contracts.append((cid, ctitle, di, vendor))

    budgets: List[Tuple[str, str, int]] = []
    for di in range(preset.n_dept):
        for bi in range(preset.budgets_per_dept):
            bid, btitle = make_budget(di, bi)
            budgets.append((bid, btitle, di))

    policies: List[Tuple[str, str, int]] = []
    for di in range(preset.n_dept):
        for pi in range(preset.policies_per_dept):
            pid, ptitle = make_policy(di, pi)
            policies.append((pid, ptitle, di))

    appointments: List[Tuple[str, str, int]] = []
    for di in range(preset.n_dept):
        for ai in range(preset.appointments_per_dept):
            aid, atitle = make_appointment(di, ai)
            appointments.append((aid, atitle, di))

    return CorpusPlan(
        n_dept=preset.n_dept,
        dept_keys=tuple(dept_keys),
        dept_titles=tuple(dept_titles),
        projects=tuple(projects),
        contracts=tuple(contracts),
        budgets=tuple(budgets),
        policies=tuple(policies),
        appointments=tuple(appointments),
    )


def initial_corpus(plan: CorpusPlan) -> List[dict]:
    docs: List[dict] = []

    # Group projects + policies by dept for the dept body summary.
    by_dept_projects: Dict[int, List[Tuple[str, str]]] = {}
    for pid, ptitle, di in plan.projects:
        by_dept_projects.setdefault(di, []).append((pid, ptitle))
    by_dept_policies: Dict[int, List[Tuple[str, str]]] = {}
    for pid, ptitle, di in plan.policies:
        by_dept_policies.setdefault(di, []).append((pid, ptitle))

    for di in range(plan.n_dept):
        dept_doc_id = f"co-dep-{di + 1:04d}"
        title = plan.dept_titles[di]
        text = _dept_body(di, title,
                          by_dept_projects.get(di, []),
                          by_dept_policies.get(di, []))
        docs.append({"doc_id": dept_doc_id, "title": title, "text": text})

    for pid, ptitle, di in plan.projects:
        lead_idx = (plan.n_dept + di * 3 + int(pid[-3:]) % 7) \
            % (len(FIRST_NAMES) * len(LAST_NAMES))
        docs.append({"doc_id": pid, "title": ptitle,
                     "text": _proj_body(pid, ptitle, di, lead_idx)})

    for cid, ctitle, di, vendor in plan.contracts:
        docs.append({"doc_id": cid, "title": ctitle,
                     "text": _con_body(cid, ctitle, di, vendor)})

    for bid, btitle, di in plan.budgets:
        amount = (di + 1) * 250
        docs.append({"doc_id": bid, "title": btitle,
                     "text": _bud_body(bid, btitle, di, amount)})

    for pid, ptitle, di in plan.policies:
        docs.append({"doc_id": pid, "title": ptitle,
                     "text": _pol_body(pid, ptitle, di)})

    for aid, atitle, di in plan.appointments:
        docs.append({"doc_id": aid, "title": atitle,
                     "text": _app_body(aid, atitle, di, di)})

    return docs


# ──────────────────────────────────────────────────────────────────────
# Event generation
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SupersedePlan:
    """Frozen list of every supersede / update / delete / new ingest."""
    director_supersedes: Tuple[Tuple[int, int, int], ...]  # (dept_idx, week, new_dir_idx)
    project_supersedes: Tuple[Tuple[int, int, int], ...]   # (prj_global_idx, week, new_lead_idx)
    contract_supersedes: Tuple[Tuple[int, int, str], ...]  # (con_global_idx, week, new_vendor)
    policy_supersedes: Tuple[Tuple[int, int], ...]         # (pol_global_idx, week)
    budget_updates: Tuple[Tuple[int, int, int], ...]       # (bud_global_idx, week, new_amount)
    project_deletes: Tuple[Tuple[int, int], ...]           # (prj_global_idx, week)
    new_projects: Tuple[Tuple[str, str, int, int, int], ...]  # (id, title, dept_idx, week, lead_idx)


def _stride_indices(n_total: int, fraction: float) -> List[int]:
    """Returns the indices that pass the deterministic stride filter.

    A fraction of `0.5` returns every 2nd index; `0.3` returns every
    3rd-or-4th index (we round to keep the count predictable). Never
    random — pure function of (n_total, fraction).
    """
    if n_total <= 0 or fraction <= 0:
        return []
    if fraction >= 1.0:
        return list(range(n_total))
    k = max(1, int(round(n_total * fraction)))
    # Even spread: pick indices at uniform offsets.
    step = n_total / k
    return [int(round(step * i)) for i in range(k) if int(round(step * i)) < n_total]


def build_supersede_plan(plan: CorpusPlan,
                         preset: ScalePreset) -> SupersedePlan:
    weeks = preset.weeks

    # Director SUPERSEDE — evenly distributed weeks ∈ [2, weeks-2].
    director_idxs = _stride_indices(plan.n_dept,
                                    preset.director_supersede_frac)
    director_supersedes: List[Tuple[int, int, int]] = []
    person_pool = len(FIRST_NAMES) * len(LAST_NAMES)
    for i, di in enumerate(director_idxs):
        # Spread across [2, weeks-1] inclusive.
        week = 2 + (i * max(1, (weeks - 3))) // max(1, len(director_idxs))
        week = min(max(week, 2), weeks - 1)
        new_dir_idx = (plan.n_dept + i + 7) % person_pool
        director_supersedes.append((di, week, new_dir_idx))

    # Project SUPERSEDE.
    n_projects = len(plan.projects)
    prj_idxs = _stride_indices(n_projects, preset.project_supersede_frac)
    project_supersedes: List[Tuple[int, int, int]] = []
    for i, pi in enumerate(prj_idxs):
        week = 2 + (i * max(1, (weeks - 3))) // max(1, len(prj_idxs))
        week = min(max(week, 2), weeks - 1)
        new_lead_idx = (plan.n_dept + n_projects + i * 5) % person_pool
        project_supersedes.append((pi, week, new_lead_idx))

    # Contract SUPERSEDE.
    n_contracts = len(plan.contracts)
    con_idxs = _stride_indices(n_contracts, preset.contract_supersede_frac)
    contract_supersedes: List[Tuple[int, int, str]] = []
    for i, ci in enumerate(con_idxs):
        week = 2 + (i * max(1, (weeks - 3))) // max(1, len(con_idxs))
        week = min(max(week, 2), weeks - 1)
        new_vendor = make_vendor(n_contracts + i + 13)
        contract_supersedes.append((ci, week, new_vendor))

    # Policy SUPERSEDE.
    n_policies = len(plan.policies)
    pol_idxs = _stride_indices(n_policies, preset.policy_supersede_frac)
    policy_supersedes: List[Tuple[int, int]] = []
    for i, pi in enumerate(pol_idxs):
        week = 2 + (i * max(1, (weeks - 3))) // max(1, len(pol_idxs))
        week = min(max(week, 2), weeks - 1)
        policy_supersedes.append((pi, week))

    # Budget UPDATE.
    n_budgets = len(plan.budgets)
    bud_idxs = _stride_indices(n_budgets, preset.budget_update_frac)
    budget_updates: List[Tuple[int, int, int]] = []
    for i, bi in enumerate(bud_idxs):
        week = 2 + (i * max(1, (weeks - 3))) // max(1, len(bud_idxs))
        week = min(max(week, 2), weeks - 1)
        new_amount = 250 + ((i * 50) % 500)
        budget_updates.append((bi, week, new_amount))

    # Project DELETE.
    del_idxs = _stride_indices(n_projects, preset.project_delete_frac)
    project_deletes: List[Tuple[int, int]] = []
    for i, pi in enumerate(del_idxs):
        # Spread deletes later: weeks ∈ [weeks/2, weeks].
        floor = max(2, weeks // 2)
        week = floor + (i * max(1, (weeks - floor - 1))) \
            // max(1, len(del_idxs))
        week = min(max(week, floor), weeks)
        project_deletes.append((pi, week))

    # NEW project INGEST.
    n_new = int(round(plan.n_dept * preset.new_project_frac))
    new_projects: List[Tuple[str, str, int, int, int]] = []
    for i in range(n_new):
        di = i % plan.n_dept
        # Global idx well above the initial-corpus range to avoid collision.
        new_prj_global_idx = 800_000 + i + 1
        verb = PROJECT_VERBS[(i * 11) % len(PROJECT_VERBS)]
        noun = PROJECT_NOUNS[(i * 7) % len(PROJECT_NOUNS)]
        pid = f"prj-{new_prj_global_idx:06d}"
        ptitle = f"Project {noun} {verb}"
        week = 2 + (i * max(1, (weeks - 3))) // max(1, n_new)
        week = min(max(week, 2), weeks - 1)
        lead_idx = (i * 17) % (len(FIRST_NAMES) * len(LAST_NAMES))
        new_projects.append((pid, ptitle, di, week, lead_idx))

    return SupersedePlan(
        director_supersedes=tuple(director_supersedes),
        project_supersedes=tuple(project_supersedes),
        contract_supersedes=tuple(contract_supersedes),
        policy_supersedes=tuple(policy_supersedes),
        budget_updates=tuple(budget_updates),
        project_deletes=tuple(project_deletes),
        new_projects=tuple(new_projects),
    )


def evolution_events(plan: CorpusPlan,
                     sup: SupersedePlan) -> List[dict]:
    events: List[dict] = []
    counter = [0]

    def emit(week: int, op: str, args: Dict[str, Any]) -> None:
        counter[0] += 1
        events.append({
            "event_id": f"lrb-s3-{counter[0]:06d}",
            "week":     week,
            "op":       op,
            "args":     args,
        })

    # Director SUPERSEDE.
    for di, week, new_dir_idx in sup.director_supersedes:
        old_doc_id = f"co-dep-{di + 1:04d}"
        new_doc_id = f"{old_doc_id}.v2"
        new_director = make_person(new_dir_idx)
        title = plan.dept_titles[di]
        # Reuse _dept_body but with the new director by writing a thin
        # inline summary; we don't need the full project / policy index
        # again for the v2 — just enough that the LLM-grounded scorer
        # can recover the director name.
        text = (f"The {title} (doc {new_doc_id}) is led by {new_director}. "
                f"Supersedes {old_doc_id}.")
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id,
            "new_doc_id": new_doc_id,
            "title":      title,
            "text":       text,
        })

    # Project lead SUPERSEDE.
    for pi, week, new_lead_idx in sup.project_supersedes:
        pid, ptitle, di = plan.projects[pi]
        old_doc_id = pid
        new_doc_id = f"{pid}.v2"
        new_lead = make_person(new_lead_idx)
        text = (f"{ptitle} (doc {new_doc_id}) is led by {new_lead}. "
                f"Parent department: co-dep-{di + 1:04d}. "
                f"Supersedes {old_doc_id}.")
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id,
            "new_doc_id": new_doc_id,
            "title":      ptitle,
            "text":       text,
        })

    # Contract SUPERSEDE.
    for ci, week, new_vendor in sup.contract_supersedes:
        cid, ctitle, di, _ = plan.contracts[ci]
        old_doc_id = cid
        new_doc_id = f"{cid}.v2"
        text = (f"{ctitle} (doc {new_doc_id}). Vendor: {new_vendor}. "
                f"Awarding department: co-dep-{di + 1:04d}. "
                f"Supersedes {old_doc_id}.")
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id,
            "new_doc_id": new_doc_id,
            "title":      ctitle,
            "text":       text,
        })

    # Policy SUPERSEDE.
    for pi, week in sup.policy_supersedes:
        pid, ptitle, di = plan.policies[pi]
        old_doc_id = pid
        new_doc_id = f"{pid}.v2"
        text = (f"{ptitle} v2 (doc {new_doc_id}). Governing department: "
                f"co-dep-{di + 1:04d}. Revised policy supersedes "
                f"{old_doc_id}.")
        emit(week, "SUPERSEDE", {
            "old_doc_id": old_doc_id,
            "new_doc_id": new_doc_id,
            "title":      ptitle,
            "text":       text,
        })

    # Budget UPDATE (in-place; same doc_id).
    for bi, week, new_amount in sup.budget_updates:
        bid, btitle, di = plan.budgets[bi]
        text = _bud_body(bid, btitle, di, new_amount)
        emit(week, "UPDATE", {
            "doc_id": bid,
            "title":  btitle,
            "text":   text,
        })

    # Project DELETE.
    for pi, week in sup.project_deletes:
        pid, _, _ = plan.projects[pi]
        emit(week, "DELETE", {"doc_id": pid})

    # NEW project INGEST.
    for pid, ptitle, di, week, lead_idx in sup.new_projects:
        text = _proj_body(pid, ptitle, di, lead_idx)
        emit(week, "INGEST", {
            "doc_id": pid,
            "title":  ptitle,
            "text":   text,
        })

    return events


def evolution_events_with_routine(plan: CorpusPlan,
                                  sup: SupersedePlan,
                                  preset: ScalePreset) -> List[dict]:
    """Wraps `evolution_events` with the high-frequency appointment
    status updates. Separate function so the routine-update density is
    parameterized at the preset level rather than baked into the
    structural event generator."""
    events = evolution_events(plan, sup)
    counter = [len(events)]

    def emit(week: int, op: str, args: Dict[str, Any]) -> None:
        counter[0] += 1
        events.append({
            "event_id": f"lrb-s3-{counter[0]:06d}",
            "week":     week,
            "op":       op,
            "args":     args,
        })

    # Every week 1..weeks, every appointment gets a status update.
    # Appointments are NOT primary gold for any query, so this density
    # boost stresses event throughput without perturbing query gold.
    for week in range(1, preset.weeks + 1):
        for aid, atitle, di in plan.appointments:
            base = _app_body(aid, atitle, di, di)
            new_text = (base + f" Weekly review note: week {week}; "
                               f"status active.")
            emit(week, "UPDATE", {
                "doc_id": aid,
                "title":  atitle,
                "text":   new_text,
            })

    events.sort(key=lambda e: (e["week"], e["event_id"]))
    return events


# ──────────────────────────────────────────────────────────────────────
# State reconstruction (for query gold computation)
# ──────────────────────────────────────────────────────────────────────


def _director_at(plan: CorpusPlan, sup: SupersedePlan,
                 dept_idx: int, week: int) -> str:
    """Returns the doc_id of the dept's director record valid at `week`."""
    base = f"co-dep-{dept_idx + 1:04d}"
    # Find latest supersede with week <= query week.
    latest: Optional[Tuple[int, str]] = None
    for di, sweek, _ in sup.director_supersedes:
        if di == dept_idx and sweek <= week:
            new_doc = f"{base}.v2"
            if latest is None or sweek > latest[0]:
                latest = (sweek, new_doc)
    return latest[1] if latest else base


def _project_lead_at(plan: CorpusPlan, sup: SupersedePlan,
                     prj_global_idx: int, week: int) -> str:
    pid, _, _ = plan.projects[prj_global_idx]
    latest: Optional[Tuple[int, str]] = None
    for pi, sweek, _ in sup.project_supersedes:
        if pi == prj_global_idx and sweek <= week:
            new_doc = f"{pid}.v2"
            if latest is None or sweek > latest[0]:
                latest = (sweek, new_doc)
    return latest[1] if latest else pid


def _policy_at(plan: CorpusPlan, sup: SupersedePlan,
               pol_global_idx: int, week: int) -> str:
    pid, _, _ = plan.policies[pol_global_idx]
    latest: Optional[Tuple[int, str]] = None
    for pi, sweek in sup.policy_supersedes:
        if pi == pol_global_idx and sweek <= week:
            new_doc = f"{pid}.v2"
            if latest is None or sweek > latest[0]:
                latest = (sweek, new_doc)
    return latest[1] if latest else pid


# ──────────────────────────────────────────────────────────────────────
# Query generation
# ──────────────────────────────────────────────────────────────────────


def build_queries(plan: CorpusPlan, sup: SupersedePlan,
                  preset: ScalePreset) -> List[dict]:
    qs: List[dict] = []
    counter = [0]
    weeks = preset.weeks
    mid_t = weeks // 3            # historical-mid valid_time
    early_t = 0                   # historical-early valid_time

    def add(category: str, q_text: str, query_time: int,
            valid_time: int, gold_doc_ids: List[str]) -> None:
        counter[0] += 1
        qs.append({
            "query_id":   f"lrb-s3-q{counter[0]:05d}",
            "category":   category,
            "q":          q_text,
            "query_time": query_time,
            "valid_time": valid_time,
            "gold":       sorted(set(gold_doc_ids)),
        })

    # CURRENT queries — director / project-lead / policy / contract,
    # split proportionally so the per-category n is balanced.
    n_current = preset.queries_current
    n_per_current_sub = max(1, n_current // 4)
    # Director: cycle dept indices.
    for i in range(n_per_current_sub):
        di = i % plan.n_dept
        doc = _director_at(plan, sup, di, weeks)
        add("current-director",
            f"Who is the director of the {plan.dept_titles[di]}?",
            weeks, weeks, [doc])
    # Project lead (current).
    for i in range(n_per_current_sub):
        if not sup.project_supersedes:
            break
        pi = sup.project_supersedes[i % len(sup.project_supersedes)][0]
        pid, ptitle, _ = plan.projects[pi]
        doc = _project_lead_at(plan, sup, pi, weeks)
        add("current-project-lead", f"Who leads {ptitle}?",
            weeks, weeks, [doc])
    # Policy (current).
    for i in range(n_per_current_sub):
        if not sup.policy_supersedes:
            break
        pi = sup.policy_supersedes[i % len(sup.policy_supersedes)][0]
        _, ptitle, _ = plan.policies[pi]
        doc = _policy_at(plan, sup, pi, weeks)
        add("current-policy", f"What is the current text of {ptitle}?",
            weeks, weeks, [doc])
    # Contract (current vendor).
    for i in range(n_current - 3 * n_per_current_sub):
        if not sup.contract_supersedes:
            break
        ci = sup.contract_supersedes[i % len(sup.contract_supersedes)][0]
        cid, ctitle, _, _ = plan.contracts[ci]
        # Latest = .v2 if supersede week <= weeks.
        latest_week = max((sw for c, sw, _ in sup.contract_supersedes
                           if c == ci and sw <= weeks), default=-1)
        doc = f"{cid}.v2" if latest_week >= 0 else cid
        add("current-contract",
            f"Who is the current vendor for {ctitle}?",
            weeks, weeks, [doc])

    # HISTORICAL-MID — valid_time = mid_t. Use first half of supersede
    # lists so the gold differs from current.
    n_mid = preset.queries_historical_mid
    n_per_mid_sub = max(1, n_mid // 3)
    for i in range(n_per_mid_sub):
        di = i % plan.n_dept
        doc = _director_at(plan, sup, di, mid_t)
        add("historical-mid-director",
            f"Who was the director of the {plan.dept_titles[di]} "
            f"{weeks - mid_t} weeks ago?",
            weeks, mid_t, [doc])
    for i in range(n_per_mid_sub):
        if not sup.project_supersedes:
            break
        pi = sup.project_supersedes[i % len(sup.project_supersedes)][0]
        _, ptitle, _ = plan.projects[pi]
        doc = _project_lead_at(plan, sup, pi, mid_t)
        add("historical-mid-project-lead",
            f"Who led {ptitle} {weeks - mid_t} weeks ago?",
            weeks, mid_t, [doc])
    for i in range(n_mid - 2 * n_per_mid_sub):
        if not sup.policy_supersedes:
            break
        pi = sup.policy_supersedes[i % len(sup.policy_supersedes)][0]
        _, ptitle, _ = plan.policies[pi]
        doc = _policy_at(plan, sup, pi, mid_t)
        add("historical-mid-policy",
            f"What was the text of {ptitle} {weeks - mid_t} weeks ago?",
            weeks, mid_t, [doc])

    # HISTORICAL-EARLY — valid_time = 0 (initial state).
    n_early = preset.queries_historical_early
    n_per_early_sub = max(1, n_early // 2)
    for i in range(n_per_early_sub):
        di = i % plan.n_dept
        original_doc = f"co-dep-{di + 1:04d}"
        add("historical-early-director",
            f"Who was the original director of the "
            f"{plan.dept_titles[di]}?",
            weeks, early_t, [original_doc])
    for i in range(n_early - n_per_early_sub):
        if not sup.contract_supersedes:
            break
        ci = sup.contract_supersedes[i % len(sup.contract_supersedes)][0]
        cid, ctitle, _, _ = plan.contracts[ci]
        add("historical-early-contract",
            f"Who was the original vendor for {ctitle}?",
            weeks, early_t, [cid])

    # NEVER-STALE — budget queries (UPDATE-only doc_ids).
    for i in range(preset.queries_never_stale):
        if not sup.budget_updates:
            break
        bi = sup.budget_updates[i % len(sup.budget_updates)][0]
        bid, btitle, _ = plan.budgets[bi]
        add("never-stale-budget",
            f"What is the current allocation for the {btitle}?",
            weeks, weeks, [bid])

    return qs


# ──────────────────────────────────────────────────────────────────────
# Scenario assembly + validation
# ──────────────────────────────────────────────────────────────────────


def build_scenario(preset: ScalePreset) -> dict:
    plan = build_corpus_plan(preset)
    initial = initial_corpus(plan)
    sup = build_supersede_plan(plan, preset)
    events = evolution_events_with_routine(plan, sup, preset)
    queries = build_queries(plan, sup, preset)

    n_initial_expected = (plan.n_dept
                          + len(plan.projects)
                          + len(plan.contracts)
                          + len(plan.budgets)
                          + len(plan.policies)
                          + len(plan.appointments))
    assert len(initial) == n_initial_expected, (
        f"initial corpus size mismatch: expected {n_initial_expected}, "
        f"got {len(initial)}")
    # No duplicate doc ids inside the initial corpus.
    seen_ids = set()
    for d in initial:
        assert d["doc_id"] not in seen_ids, (
            f"duplicate doc_id in initial corpus: {d['doc_id']}")
        seen_ids.add(d["doc_id"])

    # Gold reachability: every gold doc_id must exist at the query's
    # valid_time given the event timeline. Walk the events forward to
    # build a per-week reachable-set snapshot.
    initial_ids = {d["doc_id"] for d in initial}
    week_states: Dict[int, set] = {0: set(initial_ids)}
    state = set(initial_ids)
    sorted_events = sorted(events, key=lambda e: (e["week"], e["event_id"]))
    last_w = 0
    for ev in sorted_events:
        w = ev["week"]
        while last_w < w:
            week_states[last_w] = set(state)
            last_w += 1
        op = ev["op"]
        args = ev["args"]
        if op == "INGEST" or op == "UPDATE":
            state.add(args["doc_id"])
        elif op == "SUPERSEDE":
            state.add(args["new_doc_id"])
            # JAMES preserves old via validity window — we keep it in
            # state too so historical-* queries can resolve it.
        elif op == "DELETE":
            state.discard(args["doc_id"])
    while last_w <= preset.weeks:
        week_states[last_w] = set(state)
        last_w += 1

    for q in queries:
        # Historical queries should hit the union of states up through
        # query_time (JAMES validity-window semantics).
        reachable = set()
        for ww in range(0, q["query_time"] + 1):
            reachable |= week_states.get(ww, set())
        for g in q["gold"]:
            assert g in reachable, (
                f"query {q['query_id']}: gold {g} not reachable by "
                f"week {q['query_time']}")

    return {
        "scenario": "S3_publication_scale",
        "name": "lifecycle-publication-scale-time-travel",
        "spec": "v0.2.3-draft-publication",
        "scale_preset": preset.name,
        "vocabulary_source":
            "scripts/research/build_lrb_scenario_s3.py:vocab-primitives",
        "weeks": preset.weeks,
        "n_dept": preset.n_dept,
        "n_projects": len(plan.projects),
        "n_contracts": len(plan.contracts),
        "n_budgets": len(plan.budgets),
        "n_policies": len(plan.policies),
        "n_appointments": len(plan.appointments),
        "n_initial": len(initial),
        "n_events": len(events),
        "n_queries": len(queries),
        "query_times": [preset.weeks],
        "valid_times": [0, preset.weeks // 3, preset.weeks],
        "initial_corpus": initial,
        "events": events,
        "queries": queries,
    }


def _fixture_sha(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True).encode("utf-8")
    ).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="build_lrb_scenario_s3")
    p.add_argument(
        "--scale", default="publication", choices=list(PRESETS.keys()),
        help=("scale preset: smoke (CI-safe; ~100 docs / ~500 events / "
              "~100 queries), dev (~300 / ~2k / ~300), publication "
              "(default; ~1000 / ~10k / ~1000)"),
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help=("output path. Default = "
              "eval/external/_fixtures/lrb/scenario_S3_<preset>.json "
              "if --scale != publication; "
              "eval/external/_fixtures/lrb/scenario_S3_publication.json "
              "otherwise."),
    )
    args = p.parse_args(argv)

    preset = PRESETS[args.scale]
    scenario = build_scenario(preset)
    sha = _fixture_sha(scenario)

    out_path: Path
    if args.out is not None:
        out_path = args.out
    elif preset.name == "publication":
        out_path = DEFAULT_OUT
    else:
        out_path = DEFAULT_OUT.with_name(
            f"scenario_S3_{preset.name}.json")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scenario, f, ensure_ascii=False)

    print(f"[s3] preset       = {preset.name}")
    print(f"[s3] n_dept       = {preset.n_dept}")
    print(f"[s3] weeks        = {preset.weeks}")
    print(f"[s3] initial      = {scenario['n_initial']}")
    print(f"[s3] events       = {scenario['n_events']}")
    print(f"[s3] queries      = {scenario['n_queries']}")
    print(f"[s3] sha          = {sha[:16]}...")
    print(f"[s3] -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
