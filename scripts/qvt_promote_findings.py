"""Promote findings tagged mechanism-candidate or universal-law into
memory entry drafts.

Reads `reports/research-runs/qvt-ablation-findings.md`, parses each
`### YYYY-MM-DD — <slug>` entry, filters by the `follow-up tag:`
field, and emits a draft memory file under
`<staging>/finding_<slug>.md` for each qualifying finding.

Design intent (plan Step 10, user requirement #5):
- The script DRAFTS only. It does not modify the user's MEMORY.md
  index. User reviews drafts and decides which to land.
- Default staging dir: `reports/research-runs/promoted-findings/`
  (under repo, so it lands via PR rather than touching the user's
  home directory).
- Optional --memory-dir <path> lets the operator point at the real
  memory home (`~/.claude/projects/<id>/memory/`) once they've
  reviewed the drafts.
- Idempotent: skips drafts that already exist unless --force is given.

Promotion criteria (per findings.md §Categories):
- `mechanism-candidate` — promoted
- `universal-law` — promoted
- `anti-pattern` — NOT promoted by default (--include-anti-pattern
  to override)
- `data-quality` — NOT promoted; these are bench/oracle bugs and
  belong in fix PR descriptions, not memory
- `operational` — NOT promoted; runtime/setup issues, not knowledge

Output format mirrors the existing memory frontmatter convention:

    ---
    name: finding-<slug>
    description: <one-line summary from the finding>
    metadata:
      type: project
    ---

    <body assembled from the finding fields>

The body keeps the original 5+ field structure so the user can edit
in place rather than re-deriving from prose.

Usage:
    python scripts/qvt_promote_findings.py
    python scripts/qvt_promote_findings.py --memory-dir ~/.claude/projects/.../memory
    python scripts/qvt_promote_findings.py --force
    python scripts/qvt_promote_findings.py --include-anti-pattern
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FINDINGS = ROOT / "reports" / "research-runs" / "qvt-ablation-findings.md"
DEFAULT_STAGING = ROOT / "reports" / "research-runs" / "promoted-findings"

PROMOTE_TAGS_DEFAULT = {"mechanism-candidate", "universal-law"}
PROMOTE_TAGS_WITH_ANTI = PROMOTE_TAGS_DEFAULT | {"anti-pattern"}

HEADING_RE = re.compile(r"^###\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.+?)\s*$")
FIELD_RE = re.compile(r"^\s*-\s+\*\*([a-zA-Z_-][a-zA-Z0-9 _-]*)\*\*:\s*(.*)$")
TAG_SPLIT_RE = re.compile(r"[\s,+/]+")


@dataclass
class Finding:
    date: str
    slug: str
    raw_body: str
    fields: dict[str, str] = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    bucket: Optional[str] = None

    @property
    def memory_name(self) -> str:
        return f"finding-{self.slug}"

    @property
    def memory_filename(self) -> str:
        # mirror the snake_case convention used elsewhere in memory/
        safe = self.slug.replace("-", "_")
        return f"finding_{safe}.md"


def _strip_resolution_suffix(slug: str) -> str:
    """The findings log sometimes appends " → RESOLVED ..." to the slug
    for entries that have been closed. Strip that for the canonical
    slug used in filenames."""
    cut = re.split(r"\s+→\s+", slug, maxsplit=1)
    return cut[0].strip()


def parse_findings(text: str) -> list[Finding]:
    """Walk the markdown; collect heading→body chunks; parse fields."""
    # Restrict to the "## Findings" section to avoid catching
    # the carry-over examples or other H2 sections.
    findings_start = text.find("\n## Findings")
    if findings_start == -1:
        return []
    promoted_start = text.find("\n## Promoted to memory", findings_start)
    if promoted_start == -1:
        section = text[findings_start:]
    else:
        section = text[findings_start:promoted_start]

    out: list[Finding] = []
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        m = HEADING_RE.match(lines[i])
        if not m:
            i += 1
            continue
        date, slug_raw = m.group(1), m.group(2)
        slug = _strip_resolution_suffix(slug_raw)
        body_lines: list[str] = []
        i += 1
        while i < len(lines) and not HEADING_RE.match(lines[i]) and not lines[i].startswith("## "):
            # bound entries by H3 (next finding) or H2 (next section)
            if lines[i].strip() == "---":
                # findings are separated by a horizontal rule; respect it
                break
            body_lines.append(lines[i])
            i += 1
        finding = Finding(date=date, slug=slug, raw_body="\n".join(body_lines).strip())
        _populate_fields(finding)
        out.append(finding)
    return out


def _populate_fields(f: Finding) -> None:
    """Extract `- **field**: value` pairs and the bucket / tag set."""
    for line in f.raw_body.splitlines():
        m = FIELD_RE.match(line)
        if not m:
            continue
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        f.fields[key] = val
        if key == "bucket":
            # examples seen in file: "(d) measurement artifact — ..." or "(a) ..."
            bm = re.match(r"\(([a-d])\)", val)
            if bm:
                f.bucket = bm.group(1)
        elif key in ("follow-up tag", "follow up tag", "tag", "tags"):
            for piece in TAG_SPLIT_RE.split(val):
                piece = piece.strip().strip("`").strip("'\"").lower()
                if piece:
                    f.tags.add(piece)


def _one_line_description(f: Finding) -> str:
    """Synthesize a one-line memory description from the finding fields."""
    surprise = f.fields.get("surprise", "")
    observation = f.fields.get("observation", "")
    bucket_str = f"bucket-({f.bucket})" if f.bucket else "bucket-?"
    head = surprise or observation or f.raw_body[:140]
    # collapse whitespace, cap at ~140 chars for the description line
    head = re.sub(r"\s+", " ", head).strip()
    if len(head) > 140:
        head = head[:137].rstrip() + "..."
    return f"[{f.date}, {bucket_str}] {head}"


def render_draft(f: Finding) -> str:
    description = _one_line_description(f)
    tag_line = ", ".join(sorted(f.tags)) if f.tags else "(none)"
    bucket_line = f.bucket or "?"
    body_block = f.raw_body
    return (
        "---\n"
        f"name: {f.memory_name}\n"
        f"description: {description}\n"
        "metadata:\n"
        "  type: project\n"
        "---\n"
        "\n"
        f"# Finding — {f.slug} ({f.date})\n"
        "\n"
        f"**Bucket**: ({bucket_line})  \n"
        f"**Tags**: {tag_line}\n"
        "\n"
        "## Source entry (verbatim from `reports/research-runs/qvt-ablation-findings.md`)\n"
        "\n"
        f"{body_block}\n"
        "\n"
        "## Promotion provenance\n"
        "\n"
        f"- Auto-drafted by `scripts/qvt_promote_findings.py` on the entry dated {f.date}.\n"
        "- This is a DRAFT memo. Review before adding a line under MEMORY.md.\n"
        "- If the finding was already resolved by a PR (e.g. `→ RESOLVED (#N)`),\n"
        "  consider whether the memo should be archived as feedback rather than\n"
        "  carried as an open mechanism candidate.\n"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS,
                   help=f"Path to findings markdown (default: {DEFAULT_FINDINGS.relative_to(ROOT)})")
    p.add_argument("--memory-dir", type=Path, default=DEFAULT_STAGING,
                   help=f"Where to write drafts (default: {DEFAULT_STAGING.relative_to(ROOT)})")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing draft files")
    p.add_argument("--include-anti-pattern", action="store_true",
                   help="Also promote anti-pattern tagged findings")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be written without touching disk")
    args = p.parse_args()

    findings_path: Path = args.findings
    if not findings_path.exists():
        print(f"[error] findings file not found: {findings_path}", file=sys.stderr)
        return 2

    text = findings_path.read_text(encoding="utf-8")
    findings = parse_findings(text)
    if not findings:
        print(f"[info] no finding entries in {findings_path}")
        return 0

    promote_tags = PROMOTE_TAGS_WITH_ANTI if args.include_anti_pattern else PROMOTE_TAGS_DEFAULT

    staging: Path = args.memory_dir
    if not args.dry_run:
        staging.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    rejected = 0
    summary: list[tuple[str, str, str]] = []  # (status, slug, reason)

    for f in findings:
        match = f.tags & promote_tags
        if not match:
            rejected += 1
            summary.append(("rejected", f.slug, f"no promotion tag (tags: {sorted(f.tags) or 'none'})"))
            continue

        dest = staging / f.memory_filename
        if dest.exists() and not args.force:
            skipped += 1
            summary.append(("skipped", f.slug, f"draft exists: {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest}"))
            continue

        draft = render_draft(f)
        if args.dry_run:
            written += 1
            summary.append(("would-write", f.slug, f"-> {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest} ({len(draft)} bytes)"))
        else:
            dest.write_text(draft, encoding="utf-8")
            written += 1
            summary.append(("written", f.slug, f"-> {dest.relative_to(ROOT) if dest.is_relative_to(ROOT) else dest}"))

    # Output summary
    print("\n=== qvt_promote_findings summary ===")
    print(f"Findings scanned: {len(findings)}")
    print(f"Promotion tags accepted: {sorted(promote_tags)}")
    print(f"Written: {written}  Skipped: {skipped}  Rejected: {rejected}")
    print("")
    for status, slug, reason in summary:
        print(f"  [{status}] {slug} -- {reason}")
    print("")
    if written and not args.dry_run:
        print("Next steps:")
        print("  1. Review each draft under the staging dir for accuracy / framing.")
        print("  2. Move accepted drafts into your real memory dir.")
        print("  3. Add a one-line entry under MEMORY.md for each kept draft.")
        print("  4. Record the promotion in the `## Promoted to memory` table of the findings log.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
