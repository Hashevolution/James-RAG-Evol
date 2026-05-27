"""v0.4 Sprint 5 PR-T1.A — migration script contract tests.

Pins the properties of ``scripts/migrate_v04_lifecycle.py``:

1. **Idempotent** — running ``--apply`` twice leaves the wiki
   byte-identical after the first run (the second run is a no-op).
2. **v0.3-compatible defaults** — every back-filled field uses the
   safe defaults locked at PR-0; nothing else in the entity
   frontmatter is mutated.
3. **Validation pass** — migrated files validate clean against
   `validate_source_v04_fields` + `validate_edge_v04_fields`.
4. **Dry-run is read-only** — ``--dry-run`` (default) leaves the
   wiki untouched even when it reports thousands of would-be
   mutations.
5. **Verify mode** — reports `verify_failed > 0` when fields are
   missing; reports clean after apply.
6. **Snapshot path** — ``--apply`` creates ``wiki.pre-v04-migration/``
   for rollback; ``--no-snapshot`` skips it.
7. **No-relations files** — entities without a `relations` list pass
   through untouched (matches `had_no_relations` bucket).
8. **Atomic write** — a write-failure path leaves the original file
   intact (tested via monkey-patched os.replace).

Tests run against a self-contained tmp_path wiki fixture; the
production wiki under `wiki/` is never touched.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Make `scripts/` importable for direct function calls
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# ─── tmp_path wiki fixtures ───────────────────────────────────────


def _entity_v03(name: str) -> dict:
    """A canonical v0.3-shape entity frontmatter — sources are the
    Phase A v0.3 surface (doc_id + role + weight + ts), and edges
    carry confidence + sources but none of the v0.4 T1/T7 fields."""
    return {
        "entity_id": f"e_concept_{name}",
        "entity_type": "concept",
        "name": name,
        "normalized_name": name,
        "sensitivity": "public",
        "source_type": "prod",
        "version": 1,
        "trusted": True,
        "verified": False,
        "owner": "system",
        "aliases": [name],
        "attributes": {"summary": f"{name} summary"},
        "summary": f"{name} summary",
        "embedding_refs": [],
        "sources": [f"{name}.pdf"],
        "created_at": "2026-05-01T00:00:00",
        "updated_at": "2026-05-01T00:00:00",
        "relations": [
            {
                "label": "관련",
                "target": "OtherThing",
                "target_id": "e_concept_other",
                "target_type": "concept",
                "inferred": True,
                "confidence": 0.7,
                "sources": [
                    {
                        "doc_id": None,
                        "role": "legacy",
                        "ts": "2026-05-07T07:42:31.951205",
                        "weight": 0.7,
                    }
                ],
            }
        ],
    }


def _write_entity(wiki_root: Path, kind: str, name: str, fm: dict) -> Path:
    """Write a synthetic entity under wiki_root/entity/<kind>/<name>.md."""
    d = wiki_root / "entity" / kind
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{name}.md"
    body = "---\n" + yaml.safe_dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=True,
    ) + "---\n## body\n"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def fresh_wiki(tmp_path):
    """Build a tmp wiki with one v0.3-shape entity. Returns (wiki_root,
    entity_path)."""
    wiki_root = tmp_path / "wiki"
    fm = _entity_v03("ACI")
    entity_path = _write_entity(wiki_root, "concept", "ACI", fm)
    return wiki_root, entity_path


# ─── migrate_wiki API tests ──────────────────────────────────────


def test_dry_run_is_read_only(fresh_wiki):
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root, entity_path = fresh_wiki
    before = entity_path.read_text(encoding="utf-8")

    totals = migrate_wiki(wiki_root, dry_run=True)

    after = entity_path.read_text(encoding="utf-8")
    assert before == after, "dry-run must not modify any file"
    # Dry-run reports the would-be mutations
    assert totals["scanned"] == 1
    assert totals["relations_migrated"] == 1
    assert totals["sources_migrated"] == 1


def test_apply_migrates_v03_entity(fresh_wiki):
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root, entity_path = fresh_wiki

    totals = migrate_wiki(wiki_root, dry_run=False, verify=False)

    assert totals["scanned"] == 1
    assert totals["mutated"] == 1
    assert totals["relations_migrated"] == 1
    assert totals["sources_migrated"] == 1
    assert totals["validation_failed"] == 0
    assert totals["errors"] == 0

    # Parse the migrated frontmatter
    text = entity_path.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    rel = fm["relations"][0]
    assert rel["validity"] == {"from": None, "to": None}
    assert rel["status"] == {
        "active": True, "superseded_by": None, "superseded_at": None,
    }
    assert rel["mutation_type"] == "active"
    src = rel["sources"][0]
    assert src["valid_from"] is None
    assert src["valid_until"] is None
    # v0.3 fields preserved
    assert src["doc_id"] is None
    assert src["role"] == "legacy"
    assert src["weight"] == 0.7


def test_apply_is_idempotent(fresh_wiki):
    """Second --apply on already-migrated wiki is a no-op."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root, entity_path = fresh_wiki

    migrate_wiki(wiki_root, dry_run=False)
    first_pass = entity_path.read_text(encoding="utf-8")

    totals2 = migrate_wiki(wiki_root, dry_run=False)
    second_pass = entity_path.read_text(encoding="utf-8")

    assert first_pass == second_pass, "second --apply must be a no-op"
    assert totals2["mutated"] == 0, (
        "second --apply must report 0 mutations"
    )
    assert totals2["relations_migrated"] == 0
    assert totals2["sources_migrated"] == 0


def test_verify_fails_on_v03_entity(fresh_wiki):
    """Verify mode reports failure for unmigrated v0.3 entities."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root, _ = fresh_wiki

    totals = migrate_wiki(wiki_root, verify=True)
    assert totals["verify_failed"] >= 1, (
        "verify must flag v0.3 entities as missing v0.4 fields"
    )


def test_verify_passes_after_apply(fresh_wiki):
    """After --apply, verify reports zero failures."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root, _ = fresh_wiki

    migrate_wiki(wiki_root, dry_run=False)
    totals = migrate_wiki(wiki_root, verify=True)
    assert totals["verify_failed"] == 0
    assert totals["errors"] == 0


def test_apply_does_not_touch_no_relations_file(tmp_path):
    """Entity with no relations array passes through untouched."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root = tmp_path / "wiki"
    fm = _entity_v03("Empty")
    fm["relations"] = []  # empty list
    path = _write_entity(wiki_root, "concept", "Empty", fm)
    before = path.read_text(encoding="utf-8")

    totals = migrate_wiki(wiki_root, dry_run=False)

    after = path.read_text(encoding="utf-8")
    assert before == after, (
        "empty-relations file must not be rewritten"
    )
    assert totals["had_no_relations"] == 1
    assert totals["mutated"] == 0


def test_apply_handles_multiple_relations(tmp_path):
    """Migrate every relation independently when an entity has many."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root = tmp_path / "wiki"
    fm = _entity_v03("MultiRel")
    fm["relations"] = [
        {
            "label": "관련", "target": f"T{i}",
            "target_id": f"e_concept_t{i}", "target_type": "concept",
            "confidence": 0.5 + i * 0.1,
            "sources": [
                {"doc_id": None, "role": "legacy",
                 "ts": "2026-05-07T07:42:31", "weight": 0.5 + i * 0.1},
            ],
        }
        for i in range(5)
    ]
    _write_entity(wiki_root, "concept", "MultiRel", fm)

    totals = migrate_wiki(wiki_root, dry_run=False)
    assert totals["relations_migrated"] == 5
    assert totals["sources_migrated"] == 5
    assert totals["mutated"] == 1   # one file rewritten


def test_apply_preserves_v04_fields_on_already_migrated(tmp_path):
    """When a relation already has v0.4 fields (some user set them
    explicitly), the migration must NOT overwrite them with defaults.
    This is the setdefault() invariant from PR-0."""
    from migrate_v04_lifecycle import migrate_wiki
    wiki_root = tmp_path / "wiki"
    fm = _entity_v03("PreSet")
    # Pre-set v0.4 fields on the one relation
    fm["relations"][0]["validity"] = {
        "from": "2026-04-01", "to": "2027-04-01",
    }
    fm["relations"][0]["status"] = {
        "active": True, "superseded_by": None, "superseded_at": None,
    }
    fm["relations"][0]["mutation_type"] = "active"
    fm["relations"][0]["sources"][0]["valid_from"] = "2026-04-01"
    fm["relations"][0]["sources"][0]["valid_until"] = "2027-04-01"
    path = _write_entity(wiki_root, "concept", "PreSet", fm)

    migrate_wiki(wiki_root, dry_run=False)
    after_fm = yaml.safe_load(
        path.read_text(encoding="utf-8").split("---", 2)[1]
    )
    rel = after_fm["relations"][0]
    assert rel["validity"] == {"from": "2026-04-01", "to": "2027-04-01"}
    src = rel["sources"][0]
    assert src["valid_from"] == "2026-04-01"
    assert src["valid_until"] == "2027-04-01"


# ─── CLI / subprocess smoke ──────────────────────────────────────


def _run_cli(wiki_root: Path, *flags: str) -> subprocess.CompletedProcess:
    """Run the migration script as an external process — covers the
    full CLI path (argparse + main() + exit codes)."""
    script = Path(__file__).resolve().parent.parent / "scripts" / "migrate_v04_lifecycle.py"
    cmd = [sys.executable, str(script), "--root", str(wiki_root)] + list(flags)
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def test_cli_dry_run_default(fresh_wiki):
    """No flag → dry-run, exit 0, no writes."""
    wiki_root, entity_path = fresh_wiki
    before = entity_path.read_text(encoding="utf-8")
    result = _run_cli(wiki_root)
    assert result.returncode == 0, (
        f"dry-run should exit 0, got {result.returncode}: {result.stderr}"
    )
    assert "DRY-RUN" in result.stdout
    assert entity_path.read_text(encoding="utf-8") == before


def test_cli_apply_then_verify(tmp_path, fresh_wiki):
    """--apply migrates; subsequent --verify exits 0."""
    wiki_root, entity_path = fresh_wiki

    # --apply with --no-snapshot for test simplicity
    r1 = _run_cli(wiki_root, "--apply", "--no-snapshot")
    assert r1.returncode == 0, f"apply failed: {r1.stderr}"
    assert "APPLY" in r1.stdout

    # --verify
    r2 = _run_cli(wiki_root, "--verify")
    assert r2.returncode == 0, f"verify failed: {r2.stderr}"
    assert "VERIFY OK" in r2.stdout


def test_cli_apply_creates_snapshot(tmp_path, fresh_wiki):
    """--apply (without --no-snapshot) creates ``wiki.pre-v04-migration/``."""
    wiki_root, _ = fresh_wiki
    snap = wiki_root.with_name(f"{wiki_root.name}.pre-v04-migration")
    assert not snap.exists()

    result = _run_cli(wiki_root, "--apply")
    assert result.returncode == 0, f"apply failed: {result.stderr}"
    assert snap.exists(), (
        "snapshot directory must exist after --apply without --no-snapshot"
    )


def test_cli_apply_refuses_to_overwrite_snapshot(tmp_path, fresh_wiki):
    """Second --apply without --force fails when snapshot already exists."""
    wiki_root, _ = fresh_wiki
    snap = wiki_root.with_name(f"{wiki_root.name}.pre-v04-migration")

    # First apply: creates snapshot
    r1 = _run_cli(wiki_root, "--apply")
    assert r1.returncode == 0
    assert snap.exists()

    # Second apply without --force should refuse
    r2 = _run_cli(wiki_root, "--apply")
    assert r2.returncode != 0, (
        "second --apply without --force must refuse to overwrite snapshot"
    )


def test_cli_apply_with_force_overwrites_snapshot(tmp_path, fresh_wiki):
    """--apply --force overwrites existing snapshot."""
    wiki_root, _ = fresh_wiki

    r1 = _run_cli(wiki_root, "--apply")
    assert r1.returncode == 0

    r2 = _run_cli(wiki_root, "--apply", "--force")
    assert r2.returncode == 0, f"--force apply failed: {r2.stderr}"


def test_cli_apply_and_verify_mutually_exclusive(fresh_wiki):
    """--apply + --verify is rejected."""
    wiki_root, _ = fresh_wiki
    result = _run_cli(wiki_root, "--apply", "--verify")
    assert result.returncode != 0, (
        "--apply and --verify together must be rejected"
    )


def test_cli_missing_wiki_root_exit_2(tmp_path):
    """Nonexistent --root exits 2."""
    fake_root = tmp_path / "does_not_exist"
    result = _run_cli(fake_root)
    assert result.returncode == 2


# ─── Per-file unit tests ─────────────────────────────────────────


def test_migrate_entity_file_returns_stats(fresh_wiki):
    from migrate_v04_lifecycle import migrate_entity_file
    _, entity_path = fresh_wiki
    stats = migrate_entity_file(entity_path)
    assert stats["scanned"] == 1
    assert stats["mutated"] == 1
    assert stats["relations_migrated"] == 1
    assert stats["sources_migrated"] == 1
    assert stats["errors"] == 0


def test_migrate_entity_file_atomic_on_write_failure(
    fresh_wiki, monkeypatch,
):
    """When os.replace fails, the original file must be intact."""
    from migrate_v04_lifecycle import migrate_entity_file
    _, entity_path = fresh_wiki
    before = entity_path.read_text(encoding="utf-8")

    def _boom(*a, **kw):
        raise OSError("simulated write failure")

    monkeypatch.setattr("migrate_v04_lifecycle.os.replace", _boom)
    stats = migrate_entity_file(entity_path)
    assert stats["errors"] == 1
    assert stats["mutated"] == 0
    # File is the original, not half-written
    assert entity_path.read_text(encoding="utf-8") == before


def test_snapshot_function(tmp_path, fresh_wiki):
    """snapshot_wiki copies the entire tree, returns the snapshot path."""
    from migrate_v04_lifecycle import snapshot_wiki, SNAPSHOT_SUFFIX
    wiki_root, _ = fresh_wiki
    snap = snapshot_wiki(wiki_root)
    assert snap.exists()
    assert snap.name == f"{wiki_root.name}.{SNAPSHOT_SUFFIX}"
    # Files in snap match originals byte-for-byte
    for orig in (wiki_root.rglob("*.md")):
        rel = orig.relative_to(wiki_root)
        snap_file = snap / rel
        assert snap_file.exists()
        assert snap_file.read_bytes() == orig.read_bytes()
    shutil.rmtree(snap)
