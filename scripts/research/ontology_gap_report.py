"""Ontology gap report — read-only advisor (α-8 cycle prototype).

Generates a markdown report scanning the wiki entity inventory for
ontology-evolution opportunities a human reviewer could act on:

  1. Empty type slots — types declared in `core/ontology.py:ENTITY_TYPES`
     but with zero entities on disk. Useful right after α-8 lands the
     5 new horizontal types (event/date/location/quantity/project).
  2. Candidates for re-typing — concepts whose name pattern smells like
     a date / location / quantity / event / project. Heuristic only;
     reviewer decides.
  3. UNRESOLVED relation targets — entities referenced by `target` but
     whose target_id is `UNRESOLVED` (target entity doesn't exist).
     Cluster by frequency = high-value entities to ingest.
  4. Relation usage distribution — which RELATION_TYPES are used a lot
     vs declared-but-unused.
  5. Type-relation usage mismatch — entities using a relation type
     not in ALLOWED_RELATIONS for their entity_type.

Scope:
  - READ-ONLY. No code writes, no change requests, no audit_log entries.
  - Output = stdout + optional markdown file.
  - Designed to seed v0.5+ semi-automatic ontology proposal mechanism
    with real data (gap pattern frequency).

Compliance:
  - CLAUDE.md rule #1: no domain features. This script proposes
    horizontal type re-classification only; reviewer enforces
    `event/date/location/quantity/project` slot only (per α-8
    §2.3 boundary test).
  - CLAUDE.md rule #3: opt-in self-evolution. This script is the
    advisor side — does not auto-apply, does not auto-PR.

Usage:
  python scripts/research/ontology_gap_report.py
  python scripts/research/ontology_gap_report.py --wiki wiki/entity/prod
  python scripts/research/ontology_gap_report.py --output reports/research-runs/ontology-gap-YYYYMMDD.md
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from core.ontology import (  # noqa: E402
    ALLOWED_RELATIONS,
    ENTITY_TYPES,
    RELATION_TYPES,
    list_active_entity_types,
)

sys.stdout.reconfigure(encoding="utf-8")


# ─── Heuristic patterns (intentional best-effort, reviewer-gated) ──────

_DATE_PATTERNS = [
    re.compile(r"\b\d{4}[-./]\d{1,2}[-./]\d{1,2}\b"),
    re.compile(r"\b\d{4}\s*년"),
    re.compile(r"\b\d{1,2}\s*월\s*\d{1,2}\s*일"),
    re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d", re.I),
    re.compile(r"\b\d{4}\b"),  # bare year, lowest signal
]

# Korean admin-division suffixes — match only at token boundaries with a
# ≥2-char Korean prefix attached, to filter common nouns sharing the same
# ending ("금리" interest rate / "처리" handling / "오류" error). Genuine
# place names like "서울시" / "강남구" / "성수동" carry ≥2-char prefixes;
# short common nouns ("금리") do not.
_KO_ADMIN_SUFFIX_RE = re.compile(
    r"[가-힣]{2,}(시|도|구|군|동|면|리|역)(?:\s|$|[\(\[\)])"
)
# Free-position keywords — these are unambiguous location markers; substring
# match is OK (rare to appear inside non-location words).
_LOCATION_FREE_KEYWORDS = (
    # Korean — building / facility / campus markers
    "공항", "대학교", "캠퍼스", "센터", "본사", "지사", "본부", "빌딩", "타워",
    # English — word-boundary checked separately below
)
# English location markers — match as whole words via regex word boundaries.
_EN_LOCATION_RE = re.compile(
    r"\b(city|state|country|province|valley|street|avenue|boulevard|"
    r"square|plaza|district|county|region|metro|airport|university|"
    r"campus|tower|stadium)\b",
    re.IGNORECASE,
)

_QUANTITY_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s*(%|퍼센트|percent)\b", re.I),
    re.compile(r"\b\d+(\.\d+)?\s*(억|만|천|백)\s*달러?\b"),
    re.compile(r"\b\d+(\.\d+)?\s*(million|billion|trillion|k|m|b)\b", re.I),
    re.compile(r"\b\$\s*\d"),
    re.compile(r"\b\d+\s*(개|명|건|회|차|t|kg|km|m\b|cm)\b"),
]

_EVENT_KEYWORDS = (
    "발표", "출시", "공개", "선언", "결정", "회의", "행사", "사건", "사고",
    "release", "launch", "announce", "decision", "meeting", "event",
    "incident", "summit",
)

_PROJECT_KEYWORDS = (
    "프로젝트", "개발", "구축", "추진", "이니셔티브",
    "project", "initiative", "program", "campaign",
)


# ─── Wiki scan ─────────────────────────────────────────────────────────


def _split_frontmatter(text: str) -> Dict:
    """Parse YAML frontmatter block. Returns {} if parse fails (read-only
    advisor — skip bad entities rather than abort)."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    try:
        loaded = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    loaded.setdefault("relations", [])
    if not isinstance(loaded["relations"], list):
        loaded["relations"] = []
    return loaded


def scan_wiki(wiki_root: Path) -> List[Dict]:
    """Walk wiki/entity/<type>/*.md, return list of parsed entity dicts.

    Skips files that fail to parse rather than aborting (read-only advisor)."""
    entities: List[Dict] = []
    if not wiki_root.exists():
        return entities
    for type_dir in sorted(p for p in wiki_root.iterdir() if p.is_dir()):
        type_name = type_dir.name
        for md in type_dir.glob("*.md"):
            try:
                fm = _split_frontmatter(md.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, OSError):
                continue
            if not fm:
                continue
            fm["_path"] = str(md.relative_to(ROOT))
            fm.setdefault("entity_type", type_name)
            entities.append(fm)
    return entities


# ─── Gap analyses ──────────────────────────────────────────────────────


def empty_type_slots(entities: List[Dict]) -> List[Tuple[str, str]]:
    """Return [(type, since)] for ENTITY_TYPES that have zero entities."""
    counts = Counter(e.get("entity_type", "") for e in entities)
    out = []
    for t in list_active_entity_types():
        if counts.get(t, 0) == 0:
            since = ENTITY_TYPES[t].get("since", "?")
            out.append((t, since))
    return out


def retype_candidates(entities: List[Dict]) -> Dict[str, List[Dict]]:
    """Heuristic re-typing candidates: concepts/documents whose name
    pattern matches a more specific α-8 horizontal type."""
    out: Dict[str, List[Dict]] = defaultdict(list)
    for e in entities:
        et = e.get("entity_type", "")
        if et not in ("concept", "document"):
            continue
        name = (e.get("name") or "")
        low = name.lower()
        # Order matters — more specific first.
        if any(p.search(name) for p in _DATE_PATTERNS):
            out["date"].append(e)
            continue
        if any(p.search(name) for p in _QUANTITY_PATTERNS):
            out["quantity"].append(e)
            continue
        # Location: token-boundary suffix match (KO admin) OR free-position
        # facility keyword OR English word-boundary match.
        if (
            _KO_ADMIN_SUFFIX_RE.search(name + " ")  # add trailing space so end-anchor catches name-final suffix
            or any(kw in name for kw in _LOCATION_FREE_KEYWORDS)
            or _EN_LOCATION_RE.search(name)
        ):
            out["location"].append(e)
            continue
        if any(kw in low for kw in _EVENT_KEYWORDS):
            out["event"].append(e)
            continue
        if any(kw in low for kw in _PROJECT_KEYWORDS):
            out["project"].append(e)
            continue
    return out


def unresolved_targets(entities: List[Dict]) -> List[Tuple[str, int, List[str]]]:
    """Find relation targets with target_id == 'UNRESOLVED'.
    Returns [(target_name, hit_count, [source entity names])] sorted desc."""
    target_hits: Dict[str, List[str]] = defaultdict(list)
    for e in entities:
        src = e.get("name") or e.get("_path", "?")
        for rel in e.get("relations", []):
            if (rel.get("target_id") or "").strip().upper() == "UNRESOLVED":
                target = (rel.get("target") or "").strip()
                if target:
                    target_hits[target].append(src)
    return sorted(
        ((t, len(srcs), srcs[:5]) for t, srcs in target_hits.items()),
        key=lambda x: -x[1],
    )


def relation_usage(entities: List[Dict]) -> Tuple[Counter, List[str]]:
    """Counter of relation types used + list of declared-but-unused types."""
    counter: Counter = Counter()
    for e in entities:
        for rel in e.get("relations", []):
            rtype = (rel.get("type") or rel.get("label") or "").strip()
            if rtype:
                counter[rtype] += 1
    declared = set(RELATION_TYPES.keys())
    used = set(counter.keys())
    unused = sorted(declared - used)
    return counter, unused


def type_relation_mismatch(entities: List[Dict]) -> List[Dict]:
    """Entities using a relation type not in ALLOWED_RELATIONS for their
    entity_type. Returns sample violations (capped at 50)."""
    violations = []
    for e in entities:
        et = e.get("entity_type", "")
        allowed = ALLOWED_RELATIONS.get(et, set())
        for rel in e.get("relations", []):
            rtype = (rel.get("type") or "").strip()
            if rtype and rtype not in allowed and rtype in RELATION_TYPES:
                violations.append({
                    "entity": e.get("name", "?"),
                    "entity_type": et,
                    "relation": rtype,
                    "target": rel.get("target", "?"),
                    "path": e.get("_path", "?"),
                })
                if len(violations) >= 50:
                    return violations
    return violations


# ─── Report formatter ──────────────────────────────────────────────────


def format_report(
    entities: List[Dict],
    wiki_root: Path,
) -> str:
    lines: List[str] = []
    add = lines.append

    add("# Ontology Gap Report")
    add("")
    add(f"> Generated: {datetime.now().isoformat(timespec='seconds')}  ")
    add(f"> Wiki scanned: `{wiki_root}`  ")
    add(f"> Total entities: **{len(entities)}**  ")
    add(f"> Active entity types: {len(list_active_entity_types())}  ")
    add(f"> Total relation types: {len(RELATION_TYPES)}  ")
    add("")
    add("**Status**: read-only advisor (CLAUDE.md rule #3 opt-in). ")
    add("No CR opened, no code changed. Reviewer decides per row.")
    add("")
    add("---")
    add("")

    # § 1 — entity count per type
    add("## 1. Entity inventory")
    add("")
    counts = Counter(e.get("entity_type", "?") for e in entities)
    add("| Type | Count | Declared since | Status |")
    add("|---|---:|---|---|")
    for t in list_active_entity_types():
        c = counts.get(t, 0)
        since = ENTITY_TYPES[t].get("since", "?")
        status = "🟢 populated" if c > 0 else "⚪ empty slot"
        add(f"| `{t}` | {c} | {since} | {status} |")
    other = sum(v for k, v in counts.items() if k not in ENTITY_TYPES)
    if other:
        add(f"| *(unknown/legacy)* | {other} | — | ⚠️ schema drift |")
    add("")

    # § 2 — empty slots
    empties = empty_type_slots(entities)
    add("## 2. Empty type slots")
    add("")
    if not empties:
        add("All declared types have ≥1 entity. No empty slots.")
    else:
        add("Types declared in `ENTITY_TYPES` but with zero entities on disk:")
        add("")
        for t, since in empties:
            add(f"- `{t}` (since `{since}`) — 0 entities")
        add("")
        add("**Reviewer action**: confirm ingest pipeline emits these types ")
        add("when next document arrives, or run a retro-classification ")
        add("script on existing `concept` entities (see §3).")
    add("")

    # § 3 — re-typing candidates
    rt = retype_candidates(entities)
    add("## 3. Re-typing candidates (heuristic — reviewer-gated)")
    add("")
    if not rt:
        add("No re-typing candidates found by current heuristics.")
    else:
        add("Concepts/documents whose name pattern smells like an α-8 ")
        add("horizontal type. Heuristic only — false positives expected.")
        add("")
        for new_type, cands in sorted(rt.items()):
            add(f"### {new_type} ({len(cands)} candidates)")
            add("")
            add("| Current type | Name | Path |")
            add("|---|---|---|")
            for c in cands[:15]:
                name = (c.get("name") or "?").replace("|", "\\|")
                add(f"| `{c.get('entity_type', '?')}` | {name} | `{c.get('_path', '?')}` |")
            if len(cands) > 15:
                add(f"| … | … *({len(cands) - 15} more)* | … |")
            add("")
    add("")

    # § 4 — UNRESOLVED relation targets
    unresolved = unresolved_targets(entities)
    add("## 4. UNRESOLVED relation targets (high-value ingest candidates)")
    add("")
    if not unresolved:
        add("No UNRESOLVED relation targets found.")
    else:
        add(f"**Total distinct unresolved targets: {len(unresolved)}**  ")
        add("Top 30 by reference count:")
        add("")
        add("| Target name | Ref count | Referenced by (sample) |")
        add("|---|---:|---|")
        for t, n, srcs in unresolved[:30]:
            t_safe = t.replace("|", "\\|")
            srcs_safe = ", ".join(s.replace("|", "\\|") for s in srcs)
            add(f"| {t_safe} | {n} | {srcs_safe} |")
        add("")
        add("**Reviewer action**: high-ref entities are likely real entities ")
        add("the corpus depends on; consider triggering a targeted ingest ")
        add("or wiki extraction to create them.")
    add("")

    # § 5 — relation usage
    rel_counter, unused = relation_usage(entities)
    add("## 5. Relation type usage distribution")
    add("")
    add(f"**Used relations**: {len(rel_counter)} / {len(RELATION_TYPES)} declared")
    add("")
    if rel_counter:
        add("| Relation | Count | Label |")
        add("|---|---:|---|")
        for rtype, n in rel_counter.most_common(20):
            label = RELATION_TYPES.get(rtype, {}).get("label", "—")
            add(f"| `{rtype}` | {n} | {label} |")
        add("")
    if unused:
        add(f"**Declared but unused** ({len(unused)}):")
        add("")
        add(", ".join(f"`{r}`" for r in unused))
        add("")
        add("**Reviewer note**: unused relation types are either ")
        add("(a) freshly added in this cycle and ingest hasn't surfaced them ")
        add("yet, (b) genuinely useless and candidates for deprecation, or ")
        add("(c) the heuristic ingest layer doesn't know to emit them. ")
        add("Distinguish before deprecating.")
    add("")

    # § 6 — type-relation mismatch
    mismatches = type_relation_mismatch(entities)
    add("## 6. Type/relation mismatches (schema drift signal)")
    add("")
    if not mismatches:
        add("No type-relation mismatches found. Ingest layer respects ")
        add("`ALLOWED_RELATIONS` per entity_type.")
    else:
        add("Entities using a relation not in `ALLOWED_RELATIONS` for ")
        add(f"their `entity_type`. Sample of {len(mismatches)}:")
        add("")
        add("| Entity | Type | Relation (not allowed) | Target | Path |")
        add("|---|---|---|---|---|")
        for m in mismatches[:20]:
            add(f"| {m['entity']} | `{m['entity_type']}` | `{m['relation']}` | {m['target']} | `{m['path']}` |")
        add("")
        add("**Reviewer action**: either widen `ALLOWED_RELATIONS[type]` to ")
        add("include the relation (if it's a legitimate pattern) or fix the ")
        add("ingest path that emitted the bad triple.")
    add("")

    # § 7 — summary action list
    add("## 7. Summary action list (reviewer's TODO)")
    add("")
    todos = []
    if empties:
        todos.append(f"Verify ingest emits {len(empties)} empty types: " + ", ".join(f"`{t}`" for t, _ in empties))
    if rt:
        total_rt = sum(len(v) for v in rt.values())
        todos.append(f"Review {total_rt} re-typing candidates across {len(rt)} types")
    if unresolved:
        todos.append(f"Triage {len(unresolved)} UNRESOLVED targets (top 10 high-ref)")
    if unused:
        todos.append(f"Decide fate of {len(unused)} declared-but-unused relations")
    if mismatches:
        todos.append(f"Resolve {len(mismatches)}+ schema drift mismatches")
    if not todos:
        add("Nothing actionable surfaced this run. Ontology hygiene clean.")
    else:
        for i, t in enumerate(todos, 1):
            add(f"{i}. {t}")
    add("")
    add("---")
    add("")
    add("*Generated by `scripts/research/ontology_gap_report.py` — read-only advisor. ")
    add("Per CLAUDE.md rule #3, no automatic action taken. Reviewer decides every row.*")

    return "\n".join(lines)


# ─── CLI ───────────────────────────────────────────────────────────────


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--wiki", default="wiki/entity/prod",
        help="Wiki entity root (default: wiki/entity/prod)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Optional output markdown path. If omitted, prints to stdout.",
    )
    args = parser.parse_args(argv)

    wiki_root = (ROOT / args.wiki).resolve()
    entities = scan_wiki(wiki_root)
    report = format_report(entities, wiki_root.relative_to(ROOT))

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Wrote {out_path}  ({len(entities)} entities scanned)")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
