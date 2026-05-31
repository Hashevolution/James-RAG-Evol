# Promoted findings — staging area

Drafts created by `scripts/qvt_promote_findings.py` land here.

## What is in this directory

Auto-drafted memory entry candidates derived from the
`mechanism-candidate` / `universal-law` tagged entries in
`reports/research-runs/qvt-ablation-findings.md`. Each file mirrors
the structure of a real memory entry (frontmatter + body) but lives
in the repo so the promotion trail is auditable.

These are **drafts**, not active memories. They become active when
the operator:

1. Reviews the draft for accuracy and framing.
2. Edits the `description:` line and body where needed.
3. Moves the file to the real memory directory
   (`~/.claude/projects/<id>/memory/`).
4. Adds a one-line entry under `MEMORY.md`.
5. Records the promotion in the `## Promoted to memory` table of
   `qvt-ablation-findings.md`.

## Usage

```bash
python scripts/qvt_promote_findings.py             # write drafts to this dir
python scripts/qvt_promote_findings.py --dry-run   # preview without writing
python scripts/qvt_promote_findings.py --force     # overwrite existing drafts
python scripts/qvt_promote_findings.py --include-anti-pattern
# point at the real memory dir directly:
python scripts/qvt_promote_findings.py --memory-dir ~/.claude/projects/<id>/memory
```

## Why staging (and not direct write to memory dir)

The user's memory dir is outside the repo; auto-writing there mixes
"things the user accepted" with "things a script proposed". Staging
in-repo keeps the promotion event visible in git history. Once
reviewed, the user copies into the real memory dir.

## What does NOT get promoted

- `data-quality` tagged findings — these are bench / oracle bugs and
  belong in PR descriptions, not memory.
- `operational` tagged findings — runtime / setup notes are not
  durable knowledge.
- `anti-pattern` — opt-in via `--include-anti-pattern`.

If a finding carries multiple tags (e.g. `data-quality +
mechanism-candidate`), it is promoted because of the
mechanism-candidate tag; the data-quality character can be edited
out during review.
