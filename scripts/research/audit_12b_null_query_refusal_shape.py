"""4-step rule audit — null-query refusal-shape coverage gap finder.

Usage:
    python scripts/research/audit_12b_null_query_refusal_shape.py
    python scripts/research/audit_12b_null_query_refusal_shape.py <bench_json>

Output:
    - Loads the actual oracle `_ABSTENTION_PHRASES` set
    - Splits null queries into oracle-positive (detected refusal) vs
      oracle-negative (oracle did NOT detect refusal — these are the FNs)
    - Among the FN set, applies a wider refusal-shape regex panel to
      surface patterns the oracle would benefit from adding (narrow only —
      patterns appearing in unhedged refusal positions, not in
      partial-answer rows).

Origin: α-6 Phase 3a, 2026-06-01.
- Initial run on 12b C_minus found 1/25 missed refusal (`doesn't
  link`); 12b "dip" reframed to "plateau with 4b".
- Extension run on 27b C_minus + 4b C_minus to consolidate any
  multi-tier oracle phrase coverage gaps (= bucket-(d) sub-findings).
"""
import json, sys, re

sys.stdout.reconfigure(encoding='utf-8')

bench_path = sys.argv[1] if len(sys.argv) > 1 else \
    'reports/bench_ac9670d_multihop_rag_20260601_115524.json'
with open(bench_path, 'rb') as fp:
    d = json.loads(fp.read().decode('utf-8'))

results = d['results']
nulls = [r for r in results if r.get('question_type') == 'null_query']

# Load oracle's actual phrase list to compute oracle TP / FN per query.
sys.path.insert(0, '.')
try:
    from eval.qvt.oracle import _ABSTENTION_PHRASES, detect_abstention
    oracle_phrases = _ABSTENTION_PHRASES
except ImportError:
    oracle_phrases = ()
    detect_abstention = lambda a: bool(a) and any(p in a.lower() for p in [])

def oracle_decides(answer):
    """What the oracle would classify (True = refusal detected)."""
    return detect_abstention(answer)

# Refusal indicators (wider than oracle — for finding coverage gaps)
refusal_patterns = [
    r"\bdoesn'?t\s+(explicitly\s+)?link",
    r"\bdoes\s+not\s+(explicitly\s+)?link",
    r"\b(no\s+)?information\s+(is\s+)?(not\s+)?(provided|given|available)",
    r"\b(cannot|can'?t|impossible)\s+(determine|answer|verify|confirm)",
    r"\binsufficient\s+(information|data|evidence)",
    r"\bnot\s+possible\s+to",
    r"\b(no|don'?t\s+have)\s+(specific\s+)?(information|data|details)\s+(about|on)",
    r"\bunable\s+to\s+(provide|determine|answer)",
    r"\bdata\s+(provided\s+)?doesn'?t",
    r"\bnot\s+available",
    r"\bnot\s+in\s+(my|the)\s+(knowledge|data|provided)",
    r"\bdon'?t\s+know",
    r"\b(I|JAMES)\s+(am\s+)?not\s+(able|sure|certain)",
    # Korean
    r"답할\s*수\s*없",
    r"정보\s*가\s*없",
    r"확인\s*할\s*수\s*없",
    r"알\s*수\s*없",
    r"근거\s*가\s*없",
    r"제공된\s*문서에서\s*확인되지\s*않",
]
patterns = [re.compile(p, re.IGNORECASE) for p in refusal_patterns]

def classify(answer):
    """Return (is_refusal_shaped, matched_pattern_text)."""
    if not answer:
        return True, "<empty answer>"
    for i, p in enumerate(patterns):
        m = p.search(answer)
        if m:
            return True, f"pattern[{i}]={refusal_patterns[i]} → match='{m.group(0)}'"
    return False, None

print('=== Null-query refusal-shape audit ===')
print(f'bench file: {bench_path}')
print(f'null queries: {len(nulls)}')
print()

# Split by oracle decision
oracle_tp = []      # oracle classified as refusal
oracle_fn = []      # oracle classified as hallucination (= FN since truth=null=should refuse)
for i, q in enumerate(nulls):
    ans = q.get('answer_preview', '') or ''
    if oracle_decides(ans):
        oracle_tp.append((i, q.get('id'), ans))
    else:
        oracle_fn.append((i, q.get('id'), ans))

print(f'Oracle TP (refusal caught): {len(oracle_tp)}/25')
print(f'Oracle FN (refusal missed or true hallucination): {len(oracle_fn)}/25')
print()

# Among oracle-FN, find refusal-shape patterns (= missed by oracle)
print(f'=== Audit on Oracle-FN set ({len(oracle_fn)} answers) ===')
missed = []
true_halluc = []
for idx, qid, ans in oracle_fn:
    is_refusal, pat = classify(ans)
    if is_refusal:
        missed.append((idx, qid, pat, ans))
    else:
        true_halluc.append((idx, qid, ans))

print(f'  oracle-missed refusal-shape: {len(missed)}/{len(oracle_fn)} ({len(missed)*100//max(1,len(oracle_fn))}%)')
print(f'  true hallucinations:         {len(true_halluc)}/{len(oracle_fn)} ({len(true_halluc)*100//max(1,len(oracle_fn))}%)')
print()

if missed:
    print('=== Oracle-missed refusal patterns (candidates for bucket-(d) phrase add) ===')
    for idx, qid, pat, ans in missed:
        print(f'  null[{idx}] id={qid}')
        print(f'    matched: {pat}')
        print(f'    answer:  {ans[:300]}')
        print()

if oracle_tp:
    print('=== Oracle-caught refusals (for comparison) ===')
    for idx, qid, ans in oracle_tp[:3]:
        print(f'  null[{idx}] id={qid}: {ans[:200]}')
        print()

print('=== Top-3 true hallucinations (no refusal indicator) ===')
for idx, qid, ans in true_halluc[:3]:
    print(f'  null[{idx}] id={qid}: {ans[:200]}')
    print()
