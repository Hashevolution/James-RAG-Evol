"""Cycle γ Phase C.3 — ALCE fixture downloader.

Pulls the ALCE (Gao et al. 2023) per-variant fixture file from the
HuggingFace mirror ``princeton-nlp/ALCE-data`` and writes it to disk
in the place the loader expects (``eval/external/_fixtures/alce/data/
<variant_filename>.json``).

ALCE distributes everything as a single tarball, which is heavy for
operators who only need one variant. This script extracts just the
file the loader names, leaving the rest of the tarball on disk under
``--keep-tarball`` if asked.

Idempotent: if the expected JSON already exists at the destination,
the script returns without re-downloading.

Usage::

    python scripts/research/download_alce.py --variant asqa
    # or for all three variants (smoke + future cycles):
    python scripts/research/download_alce.py --variant all

Citation
--------

Gao, Tianyu and Yen, Howard and Yu, Jiatong and Chen, Danqi.
"Enabling Large Language Models to Generate Text with Citations."
EMNLP 2023.
https://github.com/princeton-nlp/ALCE  (MIT)
Dataset: https://huggingface.co/datasets/princeton-nlp/ALCE-data
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DEST = ROOT / "eval" / "external" / "_fixtures" / "alce"

TARBALL_URL = (
    "https://huggingface.co/datasets/princeton-nlp/ALCE-data/"
    "resolve/main/ALCE-data.tar"
)
TARBALL_NAME = "ALCE-data.tar"

# Mirror eval/external/alce_loader.py:_VARIANTS — kept in sync.
VARIANT_FILES = {
    "asqa":    "asqa_eval_gtr_top100.json",
    "qampari": "qampari_eval_gtr_top100.json",
    "eli5":    "eli5_eval_bm25_top100.json",
}


def _download(url: str, dest: Path, *, verbose: bool = True) -> None:
    """Stream a URL to disk. Bypasses external Python deps so the
    script is single-file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[alce] downloading {url}")
        print(f"[alce]      → {dest}")
    with urllib.request.urlopen(url) as r:
        with open(dest, "wb") as f:
            shutil.copyfileobj(r, f, length=1024 * 1024)
    if verbose:
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"[alce]      ({size_mb:.1f} MB)")


def _extract(
    tarball: Path,
    dest_dir: Path,
    wanted_filenames: list[str],
    *,
    verbose: bool = True,
) -> list[Path]:
    """Extract only the wanted files from the ALCE tarball.

    ALCE's tar layout looks like ``data/<filename>``; we strip the
    leading ``data/`` so the file lands at ``dest_dir/<filename>``
    (matching what alce_loader.cache_path returns)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    wanted = set(wanted_filenames)
    with tarfile.open(tarball, "r") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name).name
            if name not in wanted:
                continue
            target = dest_dir / name
            if verbose:
                size_mb = member.size / (1024 * 1024)
                print(f"[alce] extracting {member.name} ({size_mb:.1f} MB)")
            src = tar.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            extracted.append(target)
    return extracted


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="download_alce")
    p.add_argument(
        "--variant", default="asqa",
        choices=sorted(VARIANT_FILES.keys()) + ["all"],
        help="ALCE variant to fetch. 'all' grabs every variant.",
    )
    p.add_argument(
        "--dest", default=str(DEFAULT_DEST),
        help=f"Destination directory (default: {DEFAULT_DEST.relative_to(ROOT)})",
    )
    p.add_argument(
        "--keep-tarball", action="store_true",
        help="Keep the downloaded ALCE-data.tar on disk for inspection.",
    )
    args = p.parse_args(argv)

    dest = Path(args.dest)
    variants = (
        sorted(VARIANT_FILES.keys()) if args.variant == "all"
        else [args.variant]
    )
    wanted_files = [VARIANT_FILES[v] for v in variants]

    missing = [f for f in wanted_files if not (dest / f).exists()]
    if not missing:
        print(f"[alce] already present: {wanted_files} → skip download")
        return 0

    print(f"[alce] need to fetch: {missing}")

    tarball = dest / TARBALL_NAME
    try:
        if not tarball.exists():
            _download(TARBALL_URL, tarball)
        else:
            print(f"[alce] reusing existing tarball at {tarball}")

        extracted = _extract(tarball, dest, missing)
        if not extracted:
            print(f"[alce] ERROR: extracted 0 files; tarball layout may "
                  f"have changed. Inspect with: tar tf {tarball}",
                  file=sys.stderr)
            return 2
        for p in extracted:
            print(f"[alce] wrote {p}")
    finally:
        if not args.keep_tarball and tarball.exists():
            try:
                tarball.unlink()
                print(f"[alce] removed tarball: {tarball}")
            except OSError as exc:
                print(f"[alce] could not remove tarball: {exc}",
                      file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
