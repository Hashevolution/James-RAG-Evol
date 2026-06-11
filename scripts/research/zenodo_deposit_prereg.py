"""Deposit the RAB Phase 3 (scenario-S2) pre-registration bundle to
Zenodo via the REST API and publish, returning the minted DOI.

Inputs (from the repository):
- ``reports/zenodo/rab-prereg-phase-3-s2.zip``       (the bundle)
- ``reports/zenodo/rab-prereg-phase-3-s2.metadata.json`` (the metadata)

Authentication: a Zenodo personal access token with scopes
``deposit:write`` + ``deposit:actions`` must be exported as the
environment variable ``ZENODO_TOKEN`` before invocation. The token is
read once at start-up and never written to disk by this script.

Operation (Zenodo deposit lifecycle):
  1. POST /api/deposit/depositions          → new draft, returns id
  2. PUT  /api/deposit/depositions/{id}     → set metadata
  3. POST .../files                         → upload the zip
  4. POST .../actions/publish               → mint the DOI

The script writes a small audit record at ``reports/zenodo/
rab-prereg-phase-3-s2.deposit.json`` containing the deposit id, the
minted DOI, the bucket URL, and the published timestamp — committed
alongside follow-up cross-link PRs as evidence.

Usage::

    python scripts/research/zenodo_deposit_prereg.py
    # or to keep the draft (no publish), for verification first:
    python scripts/research/zenodo_deposit_prereg.py --draft-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package is required (pip install requests).",
          file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent.parent
ZIP_PATH     = ROOT / "reports" / "zenodo" / "rab-prereg-phase-3-s2.zip"
META_PATH    = ROOT / "reports" / "zenodo" / "rab-prereg-phase-3-s2.metadata.json"
AUDIT_PATH   = ROOT / "reports" / "zenodo" / "rab-prereg-phase-3-s2.deposit.json"

ZENODO_BASE  = "https://zenodo.org/api"


def _die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _load_metadata() -> dict:
    raw = json.loads(META_PATH.read_text(encoding="utf-8"))
    if "metadata" not in raw:
        _die(f"metadata file missing top-level 'metadata' key: {META_PATH}")
    return raw


def _post(token: str, path: str, *, json_body=None, files=None, params=None):
    url = f"{ZENODO_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if json_body is not None and files is None:
        headers["Content-Type"] = "application/json"
        r = requests.post(url, headers=headers, json=json_body,
                          params=params, timeout=60)
    else:
        r = requests.post(url, headers=headers, files=files,
                          params=params, timeout=120)
    return r


def _put(token: str, path: str, *, json_body=None, data=None,
         content_type: str | None = None):
    url = f"{ZENODO_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        r = requests.put(url, headers=headers, json=json_body, timeout=60)
    else:
        if content_type:
            headers["Content-Type"] = content_type
        r = requests.put(url, headers=headers, data=data, timeout=300)
    return r


def _check(r, *, expected_status: int, step: str):
    if r.status_code != expected_status:
        snippet = r.text[:400] if r.text else "(no body)"
        _die(f"{step} failed: HTTP {r.status_code}\n{snippet}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="zenodo_deposit_prereg")
    p.add_argument("--draft-only", action="store_true",
                   help="upload + set metadata but do NOT publish (for "
                        "manual review of the draft before minting)")
    p.add_argument("--publish-existing", type=int, metavar="DEPOSIT_ID",
                   help="skip create/upload; just publish an existing "
                        "draft id (use after --draft-only review)")
    args = p.parse_args(argv)

    token = os.environ.get("ZENODO_TOKEN", "").strip()
    if not token:
        _die("ZENODO_TOKEN env var is empty. Generate a token at "
             "https://zenodo.org/account/settings/applications/tokens/new/ "
             "with scopes deposit:write + deposit:actions, then export it.")

    if args.publish_existing:
        deposit_id = args.publish_existing
        print(f"[zenodo] publishing existing draft id {deposit_id} …")
        r = _post(token, f"/deposit/depositions/{deposit_id}/actions/publish")
        _check(r, expected_status=202, step="publish existing draft")
        pub = r.json()
        doi = pub.get("doi") or pub.get("metadata", {}).get("doi")
        doi_url = pub.get("links", {}).get("doi") or (
            f"https://doi.org/{doi}" if doi else None
        )
        record_url = pub.get("links", {}).get("record_html") or \
                     pub.get("links", {}).get("record")

        # Preserve any existing audit record fields (esp. uploaded_sha).
        prior = {}
        if AUDIT_PATH.exists():
            try:
                prior = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
            except Exception:
                prior = {}
        audit = {
            **prior,
            "deposit_id":      deposit_id,
            "doi":             doi,
            "doi_url":         doi_url,
            "record_url":      record_url,
            "html_url":        pub.get("links", {}).get("html"),
            "published_ts":    datetime.now(timezone.utc).isoformat(),
            "published_state": pub.get("state"),
            "draft_only":      False,
        }
        AUDIT_PATH.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[zenodo] DOI:     {doi}")
        print(f"[zenodo] DOI URL: {doi_url}")
        print(f"[zenodo] Record:  {record_url}")
        print(f"[zenodo] Audit:   {AUDIT_PATH}")
        return 0

    if not ZIP_PATH.exists():
        _die(f"bundle not found: {ZIP_PATH}")
    if not META_PATH.exists():
        _die(f"metadata not found: {META_PATH}")

    metadata = _load_metadata()

    print("[zenodo] creating draft deposit …")
    r = _post(token, "/deposit/depositions", json_body={})
    _check(r, expected_status=201, step="create draft")
    dep = r.json()
    deposit_id = dep["id"]
    bucket_url = dep["links"]["bucket"]
    print(f"[zenodo]   deposit id: {deposit_id}")
    print(f"[zenodo]   bucket    : {bucket_url}")

    print("[zenodo] setting metadata …")
    r = _put(token, f"/deposit/depositions/{deposit_id}",
             json_body=metadata)
    _check(r, expected_status=200, step="set metadata")

    print(f"[zenodo] uploading {ZIP_PATH.name} ({ZIP_PATH.stat().st_size} B) …")
    with ZIP_PATH.open("rb") as fp:
        r = requests.put(
            f"{bucket_url}/{ZIP_PATH.name}",
            headers={"Authorization": f"Bearer {token}"},
            data=fp,
            timeout=300,
        )
    _check(r, expected_status=201, step="upload zip")
    file_info = r.json()
    print(f"[zenodo]   uploaded checksum: {file_info.get('checksum', '?')}")

    if args.draft_only:
        print(f"[zenodo] DRAFT KEPT (no publish). Review at: "
              f"{dep['links']['html']}")
        audit = {
            "deposit_id":     deposit_id,
            "html_url":       dep["links"]["html"],
            "bucket_url":     bucket_url,
            "draft_only":     True,
            "uploaded_file":  ZIP_PATH.name,
            "uploaded_sha":   file_info.get("checksum"),
            "ts_utc":         datetime.now(timezone.utc).isoformat(),
        }
        AUDIT_PATH.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[zenodo] audit record: {AUDIT_PATH}")
        return 0

    print("[zenodo] publishing …")
    r = _post(token, f"/deposit/depositions/{deposit_id}/actions/publish")
    _check(r, expected_status=202, step="publish")
    pub = r.json()
    doi = pub.get("doi") or pub.get("metadata", {}).get("doi")
    doi_url = pub.get("links", {}).get("doi") or (
        f"https://doi.org/{doi}" if doi else None
    )
    record_url = pub.get("links", {}).get("record_html") or \
                 pub.get("links", {}).get("record")

    audit = {
        "deposit_id":   deposit_id,
        "doi":          doi,
        "doi_url":      doi_url,
        "record_url":   record_url,
        "html_url":     pub.get("links", {}).get("html"),
        "uploaded_file": ZIP_PATH.name,
        "uploaded_sha": file_info.get("checksum"),
        "published_ts": datetime.now(timezone.utc).isoformat(),
        "published_state": pub.get("state"),
    }
    AUDIT_PATH.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"[zenodo] DOI:       {doi}")
    print(f"[zenodo] DOI URL:   {doi_url}")
    print(f"[zenodo] Record:    {record_url}")
    print(f"[zenodo] Audit:     {AUDIT_PATH}")
    print()
    print("Next steps (semi-automated):")
    print("  - replace <PREREG_DOI> placeholders in papers/rab-preprint/")
    print(f"    with: {doi}")
    print("  - update memory + MEMORY.md with the prereg DOI")
    print("  - revoke the access token at "
          "https://zenodo.org/account/settings/applications/tokens/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
