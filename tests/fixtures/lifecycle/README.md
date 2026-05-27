# Lifecycle fixture — Sprint 5 PR-T7.B

Curated wiki entities for the **release-gating invariant** tests
in `tests/test_t7_release_gating_invariants.py`. Tests load these
files into a `tmp_path` copy (so the originals are never mutated)
and exercise the CASCADE / EVENT separation against actual
frontmatter rather than mocks.

## Entities

| file | purpose |
|---|---|
| `entity_a.md` | Has a 2-link supersede chain (V1 → V2_active). `cascade_remove` of an unrelated doc_id must leave the chain pointers intact. |
| `entity_b.md` | Has one relation sourced from `doc_cascade_target` — the doc that gets CASCADE-removed in the test. |
| `entity_c.md` | Has the active head of `entity_a`'s chain (target side). Verifies the lookup-across-files path. |

## Why a fixture instead of mocks

Mocking the wiki layer hides the production CASCADE/EVENT
separation — a regression in `cascade_remove_doc_from_sources`
(e.g., accidentally walking through `superseded_by` links) would
not surface against a mock that returns a fixed dict. Running
against real frontmatter means the test catches the wiki-write
path as well as the in-memory mutation.

The fixture is intentionally minimal — 3 small files — so a
breaking change to the `core.lifecycle.schema` vocabulary is a
quick fix here, not a churn of fixture rebuilds.
