# PROJECT JAMES — Architecture Infographic

A single-poster, LinkedIn-style architecture infographic for PROJECT JAMES,
filled entirely from the project's real code / docs / roadmap (v0.4.1).

## Files

| File | What |
|---|---|
| `generate_infographic.py` | Reproducible generator (stdlib for SVG; `cairosvg` optional for PNG/PDF) |
| `james_architecture_en.{svg,png,pdf}` | English poster (1640×1993; PNG @ 3280px) |
| `james_architecture_ko.{svg,png,pdf}` | Korean poster (1640×1965; PNG @ 3280px) |
| `index.html` | Side-by-side viewer for both SVGs |

## Regenerate

```bash
pip install cairosvg            # optional — only for PNG/PDF
python reports/promo-assets/infographic/generate_infographic.py
```

This rewrites the `*.svg` files (always) and the `*.png` / `*.pdf` files
(when `cairosvg` is importable). Edit the `content()` function in the
generator to change copy; edit the geometry/theme constants at the top to
restyle.

> Korean PNG/PDF rasterization needs a Hangul font visible to fontconfig
> (e.g. `apt-get install fonts-noto-cjk`); the generator's Korean font
> stack leads with `Noto Sans CJK KR`. Browsers do per-glyph fallback, so
> the committed SVG renders Korean wherever any Hangul font is installed.

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
