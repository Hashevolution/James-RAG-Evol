# JAMES Pack SDK

Authoring SDK + CLI scaffolder for [PROJECT JAMES](https://github.com/Hashevolution/James-RAG-Evol)
ontology packs (v0.6 G8 plugin surface).

## What this package gives you

```bash
pip install james-pack-sdk

# Scaffold a new pack — `legal-demo-v1/` ends up in the cwd:
james-pack init legal-demo-v1

# Equivalent invocation as a module:
python -m james.pack init legal-demo-v1
```

The scaffolder writes:

- `pack.py` — minimal `OntologyPack` stub with commented examples
  for subtypes, relations, and roles
- `test_pack.py` — three contract tests (dataclass validity,
  capability gate, schema-error path) ready to run with `pytest`
- `LICENSE` — MIT default (replace with your customer-facing one)
- `README.md` — quickstart pointing at the author guide

## What's in this package

- `james.pack.OntologyPack` — frozen dataclass describing a pack.
  Re-exported from `core.ontology_packs` (requires the JAMES
  runtime on your `PYTHONPATH` for actual mounting).
- `james.pack.register_pack` / `unmount_pack` — runtime mount
  helpers. Same runtime-requirement note as `OntologyPack`.
- `james.pack.scaffold` — pure-function template generators
  (stdlib-only; usable as a library without the JAMES runtime).
- `python -m james.pack init` / `james-pack init` — CLI
  scaffolder.

## Important: rule #1 — vertical content is gated

`OntologyPack` requires `requires_capability="rule_one_exemption_granted"`
by default, and the JAMES runtime ships with `granted_capabilities()`
returning the empty frozenset. **A pack you write will not mount
until an operator explicitly grants the capability** — that
workflow (G8.d) is LOI-conditional and lands when the first
customer pilot scopes a vertical.

This is the mechanism that protects the mother-platform contract:
the SDK lets you author, scaffold, and test packs freely; mounting
in production stays gated.

## Versioning

[`docs/SDK_VERSIONING.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/SDK_VERSIONING.md)
documents the SemVer policy + 12-month deprecation window
(`PLATFORM_READINESS.md` §3 v0.3 gate).

## Documentation

- [`ONTOLOGY_PACK_AUTHORING.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/ONTOLOGY_PACK_AUTHORING.md)
  — the v0.6 G8 author guide
- [`PLATFORM_READINESS.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/PLATFORM_READINESS.md)
  — the readiness framework + gate definitions

## License

MIT — see `LICENSE`.
