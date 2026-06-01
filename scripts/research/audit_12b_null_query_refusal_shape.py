"""4-step rule audit — refusal-shape vs hallucination across null queries.

Usage (defaults to 12b C_minus bench):
    python scripts/research/audit_12b_null_query_refusal_shape.py
    python scripts/research/audit_12b_null_query_refusal_shape.py <bench_json>

Output: counts of refusal-shaped vs hallucination answers + sample text.

Origin: α-6 Phase 3a, 2026-06-01 — 4-step rule check on the 12b C_minus
abst_f1=0.000 finding. Determined the 12b "dip" is 96% real (24/25 true
hallucinations) with 1 missed refusal pattern (`doesn't link`); the
"dip" framing is reshaped to "plateau" in the recovery curve doc.

Re-usable for any later cycle where pure-LLM abst_f1=0 at a scale we
expected to abstain — the audit catches bucket-(d) phrase-coverage gaps
before they pollute publishable framings.
"""
import json, sys, re

sys.stdout.reconfigure(encoding='utf-8')

bench_path = sys.argv[1] if len(sys.argv) > 1 else \
    'reports/bench_ac9670d_multihop_rag_20260601_115524.json'
with open(bench_path, 'rb') as fp:
    d = json.loads(fp.read().decode('utf-8'))

results = d['results']
nulls = [r for r in results if r.get('question_type') == 'null_query']

# Refusal indicators (rough — what an oracle SHOULD catch)
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

print(f'=== 12b (M_L) C_minus — 25 null query refusal-shape audit ===')
print(f'Oracle reported: TP=0 FP=0 FN=25 TN=75 → abst_f1 = 0.000')
print(f'4-step rule check: does any answer LOOK like refusal that oracle missed?')
print()

n_refusal_shape = 0
n_halluc = 0
refusal_samples = []
halluc_samples = []
for i, q in enumerate(nulls):
    ans = q.get('answer_preview', '')
    is_refusal, pat = classify(ans)
    if is_refusal:
        n_refusal_shape += 1
        refusal_samples.append((i, q.get('id'), pat, ans[:300]))
    else:
        n_halluc += 1
        halluc_samples.append((i, q.get('id'), ans[:200]))

print(f'refusal-shape answers: {n_refusal_shape}/25  ({n_refusal_shape*4}% — would be TP if oracle caught)')
print(f'hallucination answers: {n_halluc}/25  ({n_halluc*4}% — real FN)')
print()

if refusal_samples:
    print(f'=== Refusal-shape answers (oracle should have caught these) ===')
    for idx, qid, pat, ans in refusal_samples:
        print(f'  null[{idx}] id={qid}')
        print(f'    matched: {pat}')
        print(f'    answer:  {ans}')
        print()

print(f'=== First 3 true hallucinations (no refusal indicator) ===')
for idx, qid, ans in halluc_samples[:3]:
    print(f'  null[{idx}] id={qid}')
    print(f'    answer: {ans}')
    print()
