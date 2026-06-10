"""Cycle γ Phase C.2 — MuSiQue dataset downloader.

Pulls the MuSiQue dataset (Trivedi et al. 2022, TACL) from a public
HuggingFace mirror and writes it to disk in the official JSONL format
the loader expects (``eval/external/musique_loader.py``).

The official upstream is https://github.com/StonyBrookNLP/musique
which distributes via Google Drive (their ``download_data.sh`` uses
``gdown``). That path works but is operator-heavy on Windows. This
script uses HuggingFace ``datasets`` instead — the same library
``scripts/hotpot/download_multihop_rag.py`` already uses for
MultiHop-RAG, so no new dep.

Default mirror: ``dgslibisey/MuSiQue``. If that ever moves, override
with ``--hf-repo <new/repo>``.

Idempotent: skips files that already exist at the destination.

Usage::

    python scripts/research/download_musique.py \\
        --variant ans --split dev \\
        --dest eval/external/_fixtures/musique

After it lands, ``MuSiQueLoader`` (variant=ans, split=dev) will
find the file at the path it expects.

Citation
--------

Trivedi, Harsh and Balasubramanian, Niranjan and Khot, Tushar and
Sabharwal, Ashish. "MuSiQue: Multihop Questions via Single-hop
Question Composition." Transactions of the Association for
Computational Linguistics (TACL), 2022.
https://github.com/StonyBrookNLP/musique  (Apache-2.0)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


DEFAULT_HF_REPO = "dgslibisey/MuSiQue"
VARIANTS = ("ans", "full")
# Official split name (what the loader / filename use) → HF split name.
# The HF mirror exposes ['train', 'validation']; "dev" is the official
# name for what HF calls "validation".
OFFICIAL_TO_HF_SPLIT = {
    "train": "train",
    "dev":   "validation",
    "test":  "test",
}


def _expected_filename(variant: str, split: str) -> str:
    return f"musique_{variant}_v1.0_{split}.jsonl"


def _hf_config_name(variant: str) -> str:
    # dgslibisey/MuSiQue uses "answerable" / "full" as config names.
    return "answerable" if variant == "ans" else "full"


def _row_to_official_format(row: dict) -> dict:
    """Project an HF row back to the official MuSiQue JSONL schema.

    The HF mirror generally preserves the original fields verbatim
    (id, paragraphs, question, question_decomposition, answer,
    answer_aliases, answerable). Some configs flatten paragraphs into
    parallel arrays, which we re-zip back into the expected list of
    dicts.
    """
    # Already-official shape: just pass through.
    if isinstance(row.get("paragraphs"), list) and (
        not row["paragraphs"] or isinstance(row["paragraphs"][0], dict)
    ):
        return dict(row)

    # Flattened-array shape: zip parallel lists back together.
    titles = row.get("paragraphs", {}).get("title") or []
    texts = row.get("paragraphs", {}).get("paragraph_text") or []
    is_supp = row.get("paragraphs", {}).get("is_supporting") or []
    idxs = row.get("paragraphs", {}).get("idx") or list(range(len(titles)))
    paragraphs = []
    for i, (t, txt, sup) in enumerate(zip(titles, texts, is_supp)):
        paragraphs.append({
            "idx":            idxs[i] if i < len(idxs) else i,
            "title":          str(t),
            "paragraph_text": str(txt),
            "is_supporting":  bool(sup),
        })

    out = dict(row)
    out["paragraphs"] = paragraphs

    # Question decomposition can be similarly flattened.
    qd = row.get("question_decomposition")
    if isinstance(qd, dict):
        ids = qd.get("id") or []
        questions = qd.get("question") or []
        answers = qd.get("answer") or []
        psi = qd.get("paragraph_support_idx") or []
        decomp = []
        for i, q in enumerate(questions):
            decomp.append({
                "id":                    ids[i] if i < len(ids) else f"step{i}",
                "question":              str(q),
                "answer":                answers[i] if i < len(answers) else "",
                "paragraph_support_idx": psi[i] if i < len(psi) else None,
            })
        out["question_decomposition"] = decomp

    return out


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="download_musique",
        description=(
            "Download MuSiQue from a HuggingFace mirror and write "
            "the official JSONL format that MuSiQueLoader expects."
        ),
    )
    p.add_argument("--variant", default="ans", choices=VARIANTS,
                    help="MuSiQue variant (default: ans)")
    p.add_argument("--split", default="dev",
                    choices=("train", "dev", "test"),
                    help="dataset split (default: dev)")
    p.add_argument("--dest", required=True,
                    help="destination directory (file lands at "
                          "<dest>/musique_<variant>_v1.0_<split>.jsonl)")
    p.add_argument("--hf-repo", default=DEFAULT_HF_REPO,
                    help=f"HuggingFace dataset id (default: "
                          f"{DEFAULT_HF_REPO})")
    p.add_argument("--force", action="store_true",
                    help="overwrite if the destination file exists")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    dest_dir = Path(args.dest).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / _expected_filename(args.variant, args.split)

    if out_path.exists() and not args.force:
        print(f"=== EXISTS (skip): {out_path}")
        print(f"    pass --force to overwrite.")
        return 0

    print(f"=== Loading MuSiQue from HF mirror ===")
    print(f"  hf_repo : {args.hf_repo}")
    print(f"  config  : {_hf_config_name(args.variant)}")
    print(f"  split   : {args.split}")
    print(f"  dest    : {out_path}")
    print()

    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("!! 'datasets' package missing. Install via "
                "'pip install datasets>=2.14.0' "
                "(already pinned in requirements.txt).",
                file=sys.stderr)
        return 2

    # Map the official split name to the HF mirror's split name
    # ("dev" → "validation"). Fall back to the given name if unknown.
    hf_split = OFFICIAL_TO_HF_SPLIT.get(args.split, args.split)

    config = _hf_config_name(args.variant)
    try:
        ds = load_dataset(args.hf_repo, config, split=hf_split)
    except Exception as e:
        # Some mirrors use no-config layout. Retry.
        try:
            ds = load_dataset(args.hf_repo, split=hf_split)
        except Exception as e2:
            print(f"!! HuggingFace load failed: {e2}", file=sys.stderr)
            print(f"   Tried: {args.hf_repo} / config={config} / "
                    f"split={hf_split}", file=sys.stderr)
            print(f"   Manual fallback: clone "
                    f"https://github.com/StonyBrookNLP/musique "
                    f"and run bash download_data.sh, then copy "
                    f"the matching .jsonl into --dest.",
                    file=sys.stderr)
            return 3

    n_written = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for row in ds:
            entry = _row_to_official_format(dict(row))
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")
            n_written += 1

    size = out_path.stat().st_size
    print(f"=== WROTE {n_written} rows ({size:,} bytes) → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
