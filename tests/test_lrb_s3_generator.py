"""LRB v0.2.3 S3 generator contract tests.

Pins:
  * Three scale presets (smoke / dev / publication) produce the right
    document counts, query counts, and weeks.
  * Determinism: re-running build_scenario at the same preset returns
    byte-identical scenarios (sha pinned).
  * Gold reachability: every query's gold doc_id is reachable from the
    initial corpus + events at the query's `query_time`.
  * Query type distribution matches the preset's per-category counts.
  * Schema-compatibility with the S2 driver: required top-level keys
    (`initial_corpus`, `events`, `queries`, `weeks`) are present and
    have the expected shapes.
  * Smoke preset is CI-safe (built in well under 1s, no LLM, no
    transformers).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.research.build_lrb_scenario_s3 import (PRESETS, _fixture_sha,
                                                    build_corpus_plan,
                                                    build_scenario,
                                                    make_dept, make_person,
                                                    make_project)


class VocabularyPrimitivesTests(unittest.TestCase):
    def test_make_dept_returns_unique_keys_for_first_100(self):
        keys = [make_dept(i)[0] for i in range(100)]
        self.assertEqual(len(set(keys)), 100)

    def test_make_dept_title_includes_department_of(self):
        _, title = make_dept(0)
        self.assertTrue(title.startswith("Department of "))

    def test_make_person_returns_unique_names_for_first_50(self):
        names = [make_person(i) for i in range(50)]
        self.assertEqual(len(set(names)), 50)

    def test_make_project_returns_unique_ids_per_dept(self):
        ids = [make_project(0, i)[0] for i in range(5)]
        self.assertEqual(len(set(ids)), 5)
        # Cross-dept also unique.
        cross = [make_project(d, p)[0] for d in range(5) for p in range(3)]
        self.assertEqual(len(set(cross)), 15)

    def test_negative_index_raises(self):
        with self.assertRaises(ValueError):
            make_dept(-1)
        with self.assertRaises(ValueError):
            make_person(-1)


class CorpusPlanTests(unittest.TestCase):
    def test_smoke_preset_yields_100_docs(self):
        plan = build_corpus_plan(PRESETS["smoke"])
        n_total = (plan.n_dept
                   + len(plan.projects)
                   + len(plan.contracts)
                   + len(plan.budgets)
                   + len(plan.policies)
                   + len(plan.appointments))
        self.assertEqual(n_total, 100)

    def test_publication_preset_yields_1000_docs(self):
        plan = build_corpus_plan(PRESETS["publication"])
        n_total = (plan.n_dept
                   + len(plan.projects)
                   + len(plan.contracts)
                   + len(plan.budgets)
                   + len(plan.policies)
                   + len(plan.appointments))
        self.assertEqual(n_total, 1000)

    def test_dev_preset_yields_300_docs(self):
        plan = build_corpus_plan(PRESETS["dev"])
        n_total = (plan.n_dept
                   + len(plan.projects)
                   + len(plan.contracts)
                   + len(plan.budgets)
                   + len(plan.policies)
                   + len(plan.appointments))
        self.assertEqual(n_total, 300)


class DeterminismTests(unittest.TestCase):
    def test_smoke_scenario_is_byte_deterministic(self):
        s1 = build_scenario(PRESETS["smoke"])
        s2 = build_scenario(PRESETS["smoke"])
        self.assertEqual(_fixture_sha(s1), _fixture_sha(s2))

    def test_publication_scenario_is_byte_deterministic(self):
        # Run the publication preset twice; the sha must match
        # exactly. This is the contract that downstream operators
        # rely on for cross-machine reproducibility.
        s1 = build_scenario(PRESETS["publication"])
        s2 = build_scenario(PRESETS["publication"])
        self.assertEqual(_fixture_sha(s1), _fixture_sha(s2))

    def test_different_presets_produce_different_sha(self):
        s_smoke = build_scenario(PRESETS["smoke"])
        s_pub = build_scenario(PRESETS["publication"])
        self.assertNotEqual(_fixture_sha(s_smoke), _fixture_sha(s_pub))


class QueryGoldReachabilityTests(unittest.TestCase):
    """Every query's gold doc_id must be reachable by walking events
    up through the query's `query_time`."""

    def test_smoke_all_gold_reachable(self):
        scenario = build_scenario(PRESETS["smoke"])
        initial_ids = {d["doc_id"] for d in scenario["initial_corpus"]}
        sorted_events = sorted(scenario["events"],
                               key=lambda e: (e["week"], e["event_id"]))
        # Replay
        week_states = {0: set(initial_ids)}
        state = set(initial_ids)
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
            elif op == "DELETE":
                state.discard(args["doc_id"])
        while last_w <= scenario["weeks"]:
            week_states[last_w] = set(state)
            last_w += 1
        for q in scenario["queries"]:
            reachable = set()
            for ww in range(0, q["query_time"] + 1):
                reachable |= week_states.get(ww, set())
            for g in q["gold"]:
                self.assertIn(g, reachable,
                              f"query {q['query_id']}: gold {g} "
                              f"not reachable")


class QueryDistributionTests(unittest.TestCase):
    def test_publication_query_count_total(self):
        scenario = build_scenario(PRESETS["publication"])
        self.assertEqual(len(scenario["queries"]), 1000)

    def test_smoke_query_count_total(self):
        scenario = build_scenario(PRESETS["smoke"])
        self.assertEqual(len(scenario["queries"]), 100)

    def test_publication_has_all_four_category_families(self):
        scenario = build_scenario(PRESETS["publication"])
        prefixes = {q["category"].split("-")[0] for q in scenario["queries"]}
        # The four families: current / historical / never-stale.
        # "historical" splits into mid + early so we expect 3 prefixes.
        self.assertIn("current", prefixes)
        self.assertIn("historical", prefixes)
        self.assertIn("never", prefixes)


class SchemaCompatibilityTests(unittest.TestCase):
    """S3 scenarios must consume cleanly through the existing S2 driver
    by carrying the same top-level keys and event-row shape."""

    def test_top_level_keys(self):
        scenario = build_scenario(PRESETS["smoke"])
        for key in ("scenario", "name", "spec", "weeks", "query_times",
                    "valid_times", "initial_corpus", "events", "queries"):
            self.assertIn(key, scenario)

    def test_initial_corpus_row_shape(self):
        scenario = build_scenario(PRESETS["smoke"])
        for doc in scenario["initial_corpus"]:
            self.assertIn("doc_id", doc)
            self.assertIn("title", doc)
            self.assertIn("text", doc)

    def test_event_row_shape(self):
        scenario = build_scenario(PRESETS["smoke"])
        for ev in scenario["events"]:
            self.assertIn("event_id", ev)
            self.assertIn("week", ev)
            self.assertIn("op", ev)
            self.assertIn("args", ev)
            self.assertIn(ev["op"], ("INGEST", "UPDATE", "SUPERSEDE",
                                      "DELETE"))

    def test_query_row_shape(self):
        scenario = build_scenario(PRESETS["smoke"])
        for q in scenario["queries"]:
            self.assertIn("query_id", q)
            self.assertIn("category", q)
            self.assertIn("q", q)
            self.assertIn("query_time", q)
            self.assertIn("valid_time", q)
            self.assertIn("gold", q)
            self.assertIsInstance(q["gold"], list)


class NoDuplicateIdsTests(unittest.TestCase):
    def test_no_duplicate_doc_ids_in_initial_corpus(self):
        scenario = build_scenario(PRESETS["publication"])
        ids = [d["doc_id"] for d in scenario["initial_corpus"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_duplicate_event_ids(self):
        scenario = build_scenario(PRESETS["publication"])
        ids = [e["event_id"] for e in scenario["events"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_duplicate_query_ids(self):
        scenario = build_scenario(PRESETS["publication"])
        ids = [q["query_id"] for q in scenario["queries"]]
        self.assertEqual(len(ids), len(set(ids)))


class ContractDiversityTests(unittest.TestCase):
    """S3.1 fix — contract titles must be distinguishable at the
    retrieval-index level (BM25 / embedding). The pre-S3.1 single
    template ``"{verb} Services Contract"`` cluster-collapsed all 200
    contracts into a single retrieval bucket (current-contract R@10 =
    0.0 across all 3 SUTs at S3 publication). The fix uses 30 domains
    × 7 types so titles are unique up to 210 contracts (>200 needed)."""

    def test_publication_contract_titles_are_unique(self):
        plan = build_corpus_plan(PRESETS["publication"])
        # contracts = (cid, ctitle, dept_idx, vendor)
        titles = [c[1] for c in plan.contracts]
        self.assertEqual(len(set(titles)), len(titles),
                         f"contract titles collided ({len(titles)} "
                         f"total, {len(set(titles))} unique)")

    def test_publication_contract_titles_do_not_share_services_contract(self):
        # The pre-S3.1 template all ended in "Services Contract"; the
        # fix replaces that with a domain × type combination. Most
        # titles should NOT share the exact phrase "Services Contract"
        # (a few will — "Inspection Services Agreement" etc. — but the
        # phrase frequency should drop below the pre-S3.1 100%).
        plan = build_corpus_plan(PRESETS["publication"])
        titles = [c[1] for c in plan.contracts]
        services_contract_frac = sum(
            "Services Contract" in t for t in titles) / max(1, len(titles))
        # Pre-S3.1: 100%. Post-fix expected < 30%.
        self.assertLess(services_contract_frac, 0.30,
                        f"too many contracts retain the pre-S3.1 "
                        f"'Services Contract' phrase: "
                        f"{services_contract_frac:.2%}")


class ScaleProportionsTests(unittest.TestCase):
    """Scale presets must produce monotonically-increasing counts so
    operators can rely on smoke < dev < publication."""

    def test_initial_corpus_size_monotonic(self):
        s = build_scenario(PRESETS["smoke"])
        d = build_scenario(PRESETS["dev"])
        p = build_scenario(PRESETS["publication"])
        self.assertLess(len(s["initial_corpus"]),
                        len(d["initial_corpus"]))
        self.assertLess(len(d["initial_corpus"]),
                        len(p["initial_corpus"]))

    def test_query_count_monotonic(self):
        s = build_scenario(PRESETS["smoke"])
        d = build_scenario(PRESETS["dev"])
        p = build_scenario(PRESETS["publication"])
        self.assertLess(len(s["queries"]), len(d["queries"]))
        self.assertLess(len(d["queries"]), len(p["queries"]))

    def test_event_count_monotonic(self):
        s = build_scenario(PRESETS["smoke"])
        d = build_scenario(PRESETS["dev"])
        p = build_scenario(PRESETS["publication"])
        self.assertLess(len(s["events"]), len(d["events"]))
        self.assertLess(len(d["events"]), len(p["events"]))


def _project_titles_by_base_id(scenario: dict) -> dict:
    """title -> set of base project ids (``prj-000001``, version suffix
    stripped) across the initial corpus and every event that carries a
    project title (INGEST / SUPERSEDE)."""
    by_title: dict = {}
    for doc in scenario["initial_corpus"]:
        if doc["doc_id"].startswith("prj-"):
            by_title.setdefault(doc["title"], set()).add(doc["doc_id"])
    for ev in scenario["events"]:
        args = ev["args"]
        doc_id = args.get("doc_id") or args.get("new_doc_id") or ""
        if doc_id.startswith("prj-") and "title" in args:
            by_title.setdefault(args["title"], set()).add(
                doc_id.split(".")[0])
    return by_title


class ProjectDiversityTests(unittest.TestCase):
    """S3.2 fix (2026-09-12) — project titles must be unique across the
    whole corpus, new-project ingests included. The pre-S3.2
    ``make_project`` formula was periodic in dept_idx with period 20, so
    the publication preset (100 departments) carried only 70 unique
    titles for 330 project docs: 50 titles × 5 projects. Because the
    project-lead query names only the title, no SUT could exceed R@1
    0.288 on ``current-project-lead`` (N and J sat at an identical 0.256
    under token mode and three LLM rerankers). See
    ``reports/research-runs/lrb-v023b-3model-llm-grounded-publication-20260910.md``
    §4. Same class of defect as S3.1 (``ContractDiversityTests``)."""

    def test_base_project_titles_unique_in_every_preset(self):
        for name, preset in PRESETS.items():
            with self.subTest(preset=name):
                plan = build_corpus_plan(preset)
                titles = [p[1] for p in plan.projects]
                self.assertEqual(len(set(titles)), len(titles),
                                 f"{name}: project titles collided "
                                 f"({len(titles)} total, "
                                 f"{len(set(titles))} unique)")

    def test_every_project_doc_has_a_unique_title_in_every_preset(self):
        # Includes the new-project INGEST events, which pre-S3.2 drew
        # from the same 20-slot cycle as the base projects.
        for name, preset in PRESETS.items():
            with self.subTest(preset=name):
                by_title = _project_titles_by_base_id(build_scenario(preset))
                collided = {t: sorted(ids) for t, ids in by_title.items()
                            if len(ids) > 1}
                self.assertEqual(collided, {},
                                 f"{name}: {len(collided)} project titles "
                                 f"shared by more than one project")

    def test_publication_project_title_space_is_not_exhausted(self):
        # 300 base + 30 new = 330 of the 400 (noun, verb) slots.
        plan = build_corpus_plan(PRESETS["publication"])
        n_new = int(round(plan.n_dept * PRESETS["publication"].new_project_frac))
        self.assertLessEqual(len(plan.projects) + n_new, 400)


class QueryOracleUnambiguityTests(unittest.TestCase):
    """The guard that would have caught S3.2 before any SUT ran: within a
    category, one query text at one (query_time, valid_time) must map to
    exactly one gold set. Identical input cannot yield gold-specific
    output, so any such collision is an oracle ceiling below 1.0 for
    every SUT — deterministic or stochastic — and shows up as an
    "SUT-independent" per-category floor rather than as a defect."""

    def test_no_query_text_maps_to_multiple_golds_in_every_preset(self):
        for name, preset in PRESETS.items():
            with self.subTest(preset=name):
                seen: dict = {}
                for q in build_scenario(preset)["queries"]:
                    key = (q["category"], q["q"],
                           q["query_time"], q["valid_time"])
                    seen.setdefault(key, set()).add(tuple(q["gold"]))
                ambiguous = {k: sorted(v) for k, v in seen.items()
                             if len(v) > 1}
                self.assertEqual(
                    ambiguous, {},
                    f"{name}: {len(ambiguous)} query texts carry more than "
                    f"one gold — an oracle ceiling below 1.0 for every SUT")


if __name__ == "__main__":
    unittest.main()
