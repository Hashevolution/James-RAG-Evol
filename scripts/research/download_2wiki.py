"""Cycle γ Phase C.4 — 2WikiMultiHopQA fixture downloader.

Pulls the 2WikiMultiHopQA dataset (Ho et al. 2020, COLING) from a
HuggingFace mirror and writes the per-split JSON file the loader
expects at ``eval/external/_fixtures/wikimulti/<split>.json``.

Official upstream is https://github.com/Alab-NII/2wikimultihop which
distributes via Dropbox (``data.zip``). HuggingFace mirrors expose
the same fields with a more reliable downloader path; we try the HF
``datasets`` library first and skip cleanly if the operator hasn't
chosen one.

Idempotent: skips files that already exist at the destination.

Usage::

    python scripts/research/download_2wiki.py --split dev
    # other splits + custom dest:
    python scripts/research/download_2wiki.py --split train --dest <path>

Citation
--------

Ho, Xanh and Nguyen, Anh-Khoa Duong and Sugawara, Saku and Aizawa,
Akiko. "Constructing A Multi-hop QA Dataset for Comprehensive
Evaluation of Reasoning Steps." COLING 2020.
https://github.com/Alab-NII/2wikimultihop  (MIT)
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DEST = ROOT / "eval" / "external" / "_fixtures" / "wikimulti"

# Official Dropbox archive (Ho et al. 2020); ?dl=1 forces direct
# download instead of a Dropbox landing page redirect.
DROPBOX_URL = "https://www.dropbox.com/s/npidmtadreo6df2/data.zip?dl=1"
DROPBOX_ARCHIVE_NAME = "data.zip"

# Primary HF mirror. xanhho is the original-author maintained mirror
# (Ho is one of the paper authors); the fields match the official
# Dropbox archive 1:1. If this mirror ever goes away, the fallback
# list below covers two alternatives.
HF_MIRRORS_BY_PRIORITY = (
    "xanhho/2WikiMultihopQA",
    "voidful/2WikiMultiHop",
)

# Official split name (what the loader / filename use) → HF split name.
# All known mirrors expose 'train' / 'validation' / 'test'.
OFFICIAL_TO_HF_SPLIT = {
    "train": "train",
    "dev":   "validation",
    "test":  "test",
}


def _expected_filename(split: str) -> str:
    return f"{split}.json"


def _row_to_official_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce a HF-flavoured row to the official-fixture JSON shape
    the loader reads.

    HF mirrors tend to preserve the original field names but may
    represent ``context`` as a separate ``{"title": [...],
    "content": [[...]]}`` dict (HotpotQA-style) instead of the
    official list-of-pairs. We accept both.
    """
    ctx = row.get("context")
    if isinstance(ctx, dict):
        titles  = ctx.get("title")   or []
        bodies  = ctx.get("content") or ctx.get("sentences") or []
        new_ctx: List[Any] = []
        for i, title in enumerate(titles):
            sents = bodies[i] if i < len(bodies) else []
            if not isinstance(sents, list):
                sents = [str(sents)]
            new_ctx.append([str(title), [str(s) for s in sents]])
        ctx = new_ctx

    sf = row.get("supporting_facts")
    if isinstance(sf, dict):
        # HF often wraps the list as {title: [...], sent_id: [...]}.
        titles = sf.get("title")   or []
        sids   = sf.get("sent_id") or []
        sf = [[str(t), int(s)] for t, s in zip(titles, sids)]

    return {
        "_id":              str(row.get("_id") or row.get("id") or ""),
        "question":         str(row.get("question", "")),
        "answer":           str(row.get("answer") or ""),
        "type":             str(row.get("type") or ""),
        "entity_ids":       str(row.get("entity_ids") or ""),
        "context":          ctx or [],
        "supporting_facts": sf or [],
        "evidences":        row.get("evidences") or [],
        "evidences_id":     row.get("evidences_id") or [],
        "answer_id":        str(row.get("answer_id") or ""),
    }


def _hf_download(
    repo_id: str,
    split: str,
    dest: Path,
    *,
    verbose: bool = True,
) -> bool:
    """Try one HF mirror. Returns True on success, False on
    ImportError / RepoNotFound so the caller can fall through to the
    next mirror or the Dropbox path."""
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("[2wiki] 'datasets' package not installed; "
              "skip HF path (pip install datasets).",
              file=sys.stderr)
        return False

    hf_split = OFFICIAL_TO_HF_SPLIT[split]
    try:
        if verbose:
            print(f"[2wiki] trying HF mirror {repo_id!r} split {hf_split!r}")
        ds = load_dataset(repo_id, split=hf_split)
    except Exception as exc:                              # broad: HF
        print(f"[2wiki]   failed: {exc!r}", file=sys.stderr)  # surfaces
        return False                                       # many failure
                                                           # modes
    rows: List[Dict[str, Any]] = []
    for r in ds:
        if isinstance(r, dict):
            rows.append(_row_to_official_dict(r))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if verbose:
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"[2wiki] wrote {dest} "
              f"({len(rows)} rows, {size_mb:.1f} MB)")
    return True


def _dropbox_download(
    split: str,
    dest: Path,
    *,
    verbose: bool = True,
) -> bool:
    """Download data.zip from Dropbox and extract only the requested
    split. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest.parent / DROPBOX_ARCHIVE_NAME

    try:
        if verbose:
            print(f"[2wiki] downloading official Dropbox archive")
            print(f"[2wiki]   url  → {DROPBOX_URL}")
            print(f"[2wiki]   tmp  → {tmp_zip}")
        req = urllib.request.Request(
            DROPBOX_URL,
            headers={"User-Agent": "JAMES-cycle-gamma-c4/0.1"},
        )
        with urllib.request.urlopen(req) as r:
            with open(tmp_zip, "wb") as f:
                shutil.copyfileobj(r, f, length=1024 * 1024)
        size_mb = tmp_zip.stat().st_size / (1024 * 1024)
        if verbose:
            print(f"[2wiki]      ({size_mb:.1f} MB downloaded)")

        wanted_split_filename = _expected_filename(split)
        # The official archive packs files at the zip root as
        # <split>.json (no nested 'data/' prefix). The HF mirror's
        # naming convention matches.
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            members = [n for n in zf.namelist()
                       if Path(n).name == wanted_split_filename]
            if not members:
                print(f"[2wiki]   ERROR: {wanted_split_filename} not "
                      f"in archive. Members: {zf.namelist()[:8]}…",
                      file=sys.stderr)
                return False
            member = members[0]
            if verbose:
                info = zf.getinfo(member)
                print(f"[2wiki] extracting {member} "
                      f"({info.file_size / (1024 * 1024):.1f} MB)")
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
        if verbose:
            print(f"[2wiki] wrote {dest}")
        return True
    except Exception as exc:
        print(f"[2wiki] Dropbox path failed: {exc!r}", file=sys.stderr)
        return False
    finally:
        if tmp_zip.exists():
            try:
                tmp_zip.unlink()
                if verbose:
                    print(f"[2wiki] removed tmp zip: {tmp_zip}")
            except OSError:
                pass


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="download_2wiki")
    p.add_argument(
        "--split", default="dev",
        choices=sorted(OFFICIAL_TO_HF_SPLIT.keys()),
        help="2Wiki split to fetch (dev = smoke target).",
    )
    p.add_argument(
        "--dest", default=str(DEFAULT_DEST),
        help=f"Destination directory (default: {DEFAULT_DEST.relative_to(ROOT)})",
    )
    p.add_argument(
        "--hf-repo",
        help=f"HuggingFace mirror repo (default: try {HF_MIRRORS_BY_PRIORITY})",
    )
    args = p.parse_args(argv)

    dest_dir = Path(args.dest)
    target = dest_dir / _expected_filename(args.split)
    if target.exists():
        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"[2wiki] already present: {target} ({size_mb:.1f} MB) → skip")
        return 0

    mirrors = (args.hf_repo,) if args.hf_repo else HF_MIRRORS_BY_PRIORITY
    for repo in mirrors:
        if not repo:
            continue
        if _hf_download(repo, args.split, target):
            return 0
        print(f"[2wiki] mirror {repo!r} failed; trying next.",
              file=sys.stderr)

    print(f"[2wiki] all HF mirrors exhausted; falling back to Dropbox.")
    if _dropbox_download(args.split, target):
        return 0

    print(
        "[2wiki] ERROR: all paths failed (HF mirrors + Dropbox). "
        "Download data.zip from "
        "https://www.dropbox.com/s/npidmtadreo6df2/data.zip manually, "
        "unpack it, and copy <split>.json into the destination "
        "directory.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
