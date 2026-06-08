"""Audit gemma4:e4b raw negrej answers for measurement artifacts (cycle γ Phase B Option A finding scrutiny, 2026-06-08)."""
import io, json, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

with open("reports/cycle_gamma/rgb-en-dual-axis-20260608.json", encoding="utf-8") as f:
    data = json.load(f)

negrej_rows = [r for r in data["rows"] if r["id"].endswith("-negrej")]
print(f"=== gemma4:e4b raw on negrej (n={len(negrej_rows)}) ===\n")

# 1. truncation indicators
truncated = [r for r in negrej_rows if len(r.get("answer", "")) >= 8000]
print(f"Truncation suspects (answer >=8000 chars): {len(truncated)}")

# 2. length distribution
lengths = [len(r.get("answer", "")) for r in negrej_rows]
print(f"Answer length: min={min(lengths)}, max={max(lengths)}, median={sorted(lengths)[len(lengths)//2]}")
print()

# 3. broad insufficient/dont-know check
print("=== Broad hedge / abstain patterns (lower-case substring search) ===")
broad_pats = [
    "insufficient", "unable", "cannot", "can't", "don't know",
    "do not know", "no information", "not mentioned", "not specified",
    "not provided", "no answer", "not enough", "no context",
    "no evidence", "unclear", "unspecified", "no mention",
    "does not mention", "doesn't mention", "not present",
    "no specific", "not clear", "no relevant", "based on the context",
    "according to the text", "the context does not", "the text does not",
    "context does not provide", "no specific information",
]
for p in broad_pats:
    hits = [r["id"] for r in negrej_rows if p in r.get("answer", "").lower()]
    if hits:
        print(f"  '{p}': {len(hits)} rows -> {hits[:5]}")
print()

# 4. all 25 answers, first 120 chars
print("=== ALL 25 gemma4 raw negrej answers ===")
for r in sorted(negrej_rows, key=lambda x: int(x["id"].split("-")[2])):
    ans_full = r.get("answer", "")
    ans = ans_full[:120].replace(chr(10), " ")
    print(f"  {r['id']:30s} ({len(ans_full):4d}c): {ans}")
