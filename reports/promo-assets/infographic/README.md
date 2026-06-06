# PROJECT JAMES — Architecture Infographic

A single-poster, LinkedIn-style architecture infographic for PROJECT JAMES,
filled entirely from the project's real code / docs / roadmap (v0.4.1).

## Files

| File | What |
|---|---|
| `generate_infographic.py` | Reproducible generator (pure Python stdlib, no deps) |
| `james_architecture_en.svg` | English poster (1640×1993) |
| `james_architecture_ko.svg` | Korean poster (1640×1965) |
| `index.html` | Side-by-side viewer for both SVGs |

## Regenerate

```bash
python reports/promo-assets/infographic/generate_infographic.py
```

This rewrites both `*.svg` files. Edit the `content()` function in the
generator to change copy; edit the geometry/theme constants at the top to
restyle.

## Panels (and their source of truth)

- **Header / badges** — version, license, test count, DOI (`README.md`).
- **Why developers love JAMES** — local-first, Replayable RAG, append-only
  audit, deterministic 4-rule arbiter, Plugin API, default-OFF invariant.
- **Why JAMES ≠ flat / cloud RAG** — replay, deterministic arbitration,
  Trust Zones, on-prem moat, gated cloud egress.
- **Architecture overview** — Entry Points / JAMES Core / Execution Surfaces,
  mirroring `docs/ARCHITECTURE.md` §4 Component Layers + §5.7 Cognitive
  Middleware + §5.7.12/13 cloud egress & abstraction.
- **State & Knowledge** — Layer 4 Lifecycle (T1/T7/T2/T6), Knowledge Cascade
  (L3), ontology + typed filter, graph snapshot/replay, append-only audit.
- **How JAMES works** — route → retrieve → traverse → reason → arbitrate →
  mask → audit.
- **Platform capabilities / Why special** — mother-platform framing; v0.5
  enterprise-internal-knowledge candidate is shown as *gated* (no domain
  forking before v1.0, per `CLAUDE.md` rule 1).
- **What's verified** — numbers reproducible from current `main`
  (`README.md` "What's Verified" table).

## Rendering to PNG/PDF

The SVGs reference system fonts (Inter / Noto Sans KR with sans-serif
fallbacks). To rasterize where a converter is available:

```bash
rsvg-convert -w 3280 james_architecture_en.svg -o james_architecture_en.png
# or: inkscape james_architecture_en.svg --export-type=png -w 3280
# or open index.html in a browser and "Save as PDF"
```

> Note: Korean rendering needs a Hangul-capable font installed
> (e.g. `Noto Sans KR`). Browsers on most systems already have one.
