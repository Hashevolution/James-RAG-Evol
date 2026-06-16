#!/usr/bin/env python3
"""Publish the RAB dataset and/or demo Space to the Hugging Face Hub.

This is an OUTWARD-FACING action: it pushes content to a public service
that may cache or index it. Run it deliberately, with the checklist in
`UPLOAD_CHECKLIST.md` completed. By default it performs a DRY RUN (no
network writes) and only validates the local folders; pass `--execute`
to actually create repos and upload.

Auth: set HF_TOKEN (a *write* token) in the environment, or run
`hf auth login` first. The token is never printed or logged.

Examples
--------
    # validate only (default; no network writes)
    python publish_to_hf.py --what both

    # actually upload both, dataset public, space public
    HF_TOKEN=hf_xxx python publish_to_hf.py --what both --execute \\
        --dataset-repo JamesLabs/rab-replayable-audit-benchmark \\
        --space-repo   JamesLabs/rab-demo

    # upload only the dataset, privately first
    HF_TOKEN=hf_xxx python publish_to_hf.py --what dataset --execute --private \\
        --dataset-repo JamesLabs/rab-replayable-audit-benchmark
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAB_ROOT = os.path.dirname(HERE)  # eval/rab
DATASET_DIR = os.path.join(RAB_ROOT, "hf_dataset")
SPACE_DIR = os.path.join(RAB_ROOT, "hf_space")

# Files that MUST exist for each artifact to be a valid upload.
DATASET_REQUIRED = ["README.md", "rab.py",
                    "scenarios/s1_lifecycle_small.json",
                    "scenarios/s2_lifecycle_large.json"]
SPACE_REQUIRED = ["README.md", "app.py", "requirements.txt",
                  "data/james-S1.log.jsonl", "data/james-S1.result.json",
                  "data/baseline0-S1.result.json",
                  "data/baseline1-S1.result.json",
                  "data/reference-S1.result.json",
                  "data/scenario_s1.json"]

DEFAULT_DATASET_REPO = "JamesLabs/rab-replayable-audit-benchmark"
DEFAULT_SPACE_REPO = "JamesLabs/rab-demo"


def _check_folder(label, folder, required):
    missing = [f for f in required if not os.path.isfile(os.path.join(folder, f))]
    if missing:
        print(f"  [FAIL] {label}: missing files: {missing}")
        return False
    print(f"  [ok]   {label}: {len(required)} required files present ({folder})")
    return True


def _validate(what):
    print("Validating local artifacts...")
    ok = True
    if what in ("dataset", "both"):
        ok &= _check_folder("dataset", DATASET_DIR, DATASET_REQUIRED)
    if what in ("space", "both"):
        ok &= _check_folder("space", SPACE_DIR, SPACE_REQUIRED)
    return ok


def _get_token():
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        # fall back to a cached `hf auth login` token if present
        try:
            from huggingface_hub import HfFolder
            token = HfFolder.get_token()
        except Exception:
            token = None
    return token


def _upload(api, repo_id, repo_type, folder, token, private, space_sdk=None):
    from huggingface_hub import CommitOperationAdd  # noqa: F401  (import check)
    print(f"  creating repo {repo_id} (type={repo_type}, private={private})...")
    kwargs = dict(repo_id=repo_id, repo_type=repo_type, exist_ok=True,
                  private=private, token=token)
    if space_sdk:
        kwargs["space_sdk"] = space_sdk
    api.create_repo(**kwargs)
    print(f"  uploading {folder} -> {repo_id} ...")
    api.upload_folder(
        repo_id=repo_id, repo_type=repo_type, folder_path=folder, token=token,
        commit_message="Publish RAB " + repo_type + " (SPEC v0.1.1)",
    )
    url = f"https://huggingface.co/{'datasets/' if repo_type == 'dataset' else 'spaces/' if repo_type == 'space' else ''}{repo_id}"
    print(f"  [done] {url}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--what", choices=["dataset", "space", "both"], default="both")
    ap.add_argument("--dataset-repo", default=DEFAULT_DATASET_REPO)
    ap.add_argument("--space-repo", default=DEFAULT_SPACE_REPO)
    ap.add_argument("--private", action="store_true",
                    help="create repos as private (recommended for a first dry upload)")
    ap.add_argument("--execute", action="store_true",
                    help="actually create repos and upload (default is a dry run)")
    args = ap.parse_args()

    if not _validate(args.what):
        print("\nValidation failed — fix the missing files before uploading.")
        return 2

    if not args.execute:
        print("\nDRY RUN (no network writes). Would upload:")
        if args.what in ("dataset", "both"):
            print(f"  dataset  {DATASET_DIR}  ->  {args.dataset_repo}")
        if args.what in ("space", "both"):
            print(f"  space    {SPACE_DIR}  ->  {args.space_repo}")
        print("\nRe-run with --execute (and HF_TOKEN set) to publish.")
        return 0

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("\nhuggingface_hub not installed. Run: pip install huggingface_hub")
        return 3

    token = _get_token()
    if not token:
        print("\nNo write token found. Set HF_TOKEN=... or run `hf auth login`.")
        return 3

    api = HfApi()
    who = api.whoami(token=token)
    print(f"Authenticated as: {who.get('name', '?')}")

    if args.what in ("dataset", "both"):
        _upload(api, args.dataset_repo, "dataset", DATASET_DIR, token, args.private)
    if args.what in ("space", "both"):
        _upload(api, args.space_repo, "space", SPACE_DIR, token, args.private,
                space_sdk="gradio")

    print("\nDone. Verify the dataset loads:")
    print(f'  python -c "from datasets import load_dataset; '
          f"load_dataset('{args.dataset_repo}','S1',split='test',trust_remote_code=True)\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
