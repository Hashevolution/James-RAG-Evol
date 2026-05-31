# α-5 Cell Rescore Audit Summary

- Generated: 2026-05-31T06:50:11.079560+00:00
- Expected suite: `multihop_rag`
- Mode: live
- Tool: `scripts/qvt_rescore_all_cells.py`

## Per-cell classification

| Cell | Status | Detail |
|---|---|---|
| `qvt-ablation-cell-L1-M_M-thinkON.json` | **needs** | bench suite=step7 (expected multihop_rag) |
| `qvt-ablation-cell-L1-M_M.json` | **needs** | bench suite=step7 (expected multihop_rag) |
| `qvt-ablation-cell-L5-M_M.json` | **ok** | bench suite=multihop_rag |

## Totals

- ok: 1
- needs: 2
- empty: 0
- unparsable: 0

## Action required

2 cell(s) carry the QQ bug fingerprint (bench_output suite mismatches the cycle's expected suite). Re-running this wrapper without `--dry-run` rewrites their `runs[*].scores` + `aggregate` blocks against the correct bench file, with `.before-rescore.json` side-copies for the diagnostic trail.

## Wrong-fix avoided

α-5 cycle now stands at 4 wrong-fix-averted corrections (#618 / #619 / #623 / #638), 0 cumulative JAMES code-side changes. The 4-step verification rule generalises to bucket-(d) phrase coverage AND bucket-(a) wiring; this rescore is the last stop before publishable matrix numbers.
