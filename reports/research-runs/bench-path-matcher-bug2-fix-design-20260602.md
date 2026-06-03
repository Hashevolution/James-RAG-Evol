# Bench path matcher slug-normalization fix (Bug 2 design)

> Drafted 2026-06-02 23:00 during α-8 Phase C n=3 confirm run.
> NOT applied this session — bench.py edits would corrupt the running
> n=3 measurement. Apply after n=3 completes (~03:35).

## Root cause

`scripts/bench.py:_path_metrics` L207-247 uses raw-string set
intersection between graph nodes and fixture `expected_path.nodes`:

```python
actual = _parse_path_nodes(actual_paths)   # raw entity names from graph_paths
expected = set(expected_nodes)              # raw titles from fixture
hits = actual & expected                    # ← exact string match
```

For multihop_rag, this fails systematically because:
- fixture `expected_path.nodes` = full article titles
  (e.g., `"The FTX trial is bigger than Sam Bankman-Fried"`)
- graph node names = wiki entity names which may be slugified, shortened,
  or differ in punctuation
- exact string match → empty intersection → `path_recall = 0.0`

Reference data: last 35+ multihop bench runs all report
`path_recall_aggregate.mean_path_recall = 0.0`.

Why oracle.py recovers some signal: `eval/qvt/oracle.py:score_path_coverage`
has its own slug normalizer (`_slug_for_match` L177-190) that handles
multihop sources well, so the per-cell aggregate (0.40 for multihop) is
higher than bench's self-report (0.0). The bench-side per-query
`path_metrics.hits` field is still zero, which biases the new oracle
fallback floor introduced by the bug 1 fix to NOT activate on multihop
(via_sources already covers the case).

## Why slug normalization is the right fix

oracle.py already proved slug normalization works on the same data:
- step7 source recall via slug matching: ✓ (we just verified mean=0.82)
- multihop source recall via slug matching: ✓ (cells show 0.40)

The bench-side `path_metrics.hits` should use the SAME normalizer so
bench's per-query report agrees with the cell aggregate.

## Proposed implementation

### Option A: duplicate the helper (recommended)

bench.py gains a 12-line helper modeled on oracle's:

```python
# scripts/bench.py — new private helper near _parse_path_nodes
import re as _re

_SLUG_PREFIX_RE = _re.compile(r"^multihop_\d+_")
_SLUG_BAD_RE = _re.compile(r"[^a-z0-9\-]+")

def _slug_for_path_match(s: str) -> str:
    """Normalize entity / title / filename to a comparable slug.

    Mirror of `eval/qvt/oracle.py:_slug_for_match` — keep in sync.
    Lowercase ASCII-alphanumeric-dash, capped at 80 chars. Drops
    `multihop_<id>_` prefix and `.txt`/`.pdf` suffix on source filenames.
    """
    if not s:
        return ""
    s = s.strip()
    s = _SLUG_PREFIX_RE.sub("", s)
    if s.lower().endswith((".txt", ".pdf")):
        s = s[:-4]
    s = s.lower()
    s = _SLUG_BAD_RE.sub("-", s).strip("-")
    return s[:80]
```

Then in `_path_metrics` (L234-236), slug-normalize both sides:

```python
actual = _parse_path_nodes(actual_paths)
actual_slugs = {_slug_for_path_match(n) for n in actual}
actual_slugs.discard("")
expected_slugs = {_slug_for_path_match(n) for n in expected_nodes}
expected_slugs.discard("")
hit_slugs = actual_slugs & expected_slugs
```

And track `missed` against the slug-normalized form (so the missed list
is still informative — reverse-map slugs back to original names via a
dict if needed, or just report slugs).

### Option B: shared module (cleaner long-term)

Extract `_slug_for_match` to a third location both bench.py and oracle.py
import:
- `core/utils/slug_match.py` or
- `eval/qvt/slug_match.py`

Defer to a separate cleanup PR if/when a third caller needs it.

## Implementation order

1. ✅ Root cause identified + design written (this memo, 2026-06-02)
2. ⏸️ Wait for n=3 confirm completion (~03:35 same night)
3. Apply Option A on the `fix/v0.4-path-coverage-oracle-fallback`
   branch (combines bug 1 + bug 2 fixes in one PR; same scope = QVT
   path measurement repair)
4. Add tests in `tests/test_qvt_oracle.py` or `tests/test_bench_path_metrics.py`
   exercising the multihop-style case (long article title vs slugified
   graph entity).
5. Verify by re-running a small bench against existing wiki + checking
   `path_recall_aggregate.mean_path_recall > 0` on multihop.
6. Bump PR title to "fix(qvt): path_coverage oracle + bench slug
   normalization" and update body.

## Expected impact post-fix

- Multihop bench's own `path_recall_aggregate.mean_path_recall` would
  go from 0.0 to roughly the cell aggregate (~0.40 at M_M baseline).
- Cell aggregates from existing JSONs unchanged (already report 0.40
  via oracle's source-side fix).
- Bench's per-query `path_metrics.hits` would become meaningful for
  multihop (currently always 0).
- Cascade benefit: any downstream tool that reads bench's per-query
  `path_metrics` (e.g., audit scripts) would get real numbers.

## Caveats

- Slug normalization is lossy — `"A vs A's"` collapse to same slug.
  Acceptable for path recall (already a fuzzy retrieval metric); the
  alternative (exact string) misses way more than it false-positives.
- bench.py and oracle.py must keep slug helpers in sync. Comment
  reminder in each helper. Cleanest fix is Option B but defer.
- The `missed` list in `_path_metrics` output may need to keep
  original names (for human-readable diagnostic) while matching on
  slugs. Cheap workaround: build a reverse dict `slug → original`.

## Verification plan post-implementation

1. Run a single multihop bench cell post-fix. Confirm:
   - `path_recall_aggregate.mean_path_recall > 0.0` (was always 0)
   - per-query `path_metrics.hits` > 0 for ~half the queries (the ones
     that genuinely matched a title)
2. Re-score the n=3 baseline bench JSONs through oracle and compare
   path_coverage cell aggregate — should be ~same as previously
   (oracle was already doing the right thing via source-side).
3. Run full `tests/test_qvt_oracle.py` + `tests/test_bench_path_metrics.py`
   — all pass.

## Links

- Bug discovery memory: `memory/feedback_path_coverage_measurement_bug.md`
- Bug 1 fix (already commit `b3c4562` on
  `fix/v0.4-path-coverage-oracle-fallback`)
- Reference slug normalizer: `eval/qvt/oracle.py:_slug_for_match` L177
- Affected production: `scripts/bench.py:_path_metrics` L207-247
