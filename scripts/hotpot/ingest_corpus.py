"""Step 3 (operator) — ingest MultiHop-RAG corpus into the workspace.

Spawns a JAMES server with `JAMES_WORKSPACE` set to the hotpot_eval
workspace, mints an admin JWT, then POSTs each `.txt` file under
`$JAMES_WORKSPACE/raw/` to `/upload/` so the existing JAMES ingest
pipeline (file_processor + rag_engine + wiki_generator) absorbs them
into the workspace's `wiki/entity/prod/` + `chroma_db_bge_m3/`.

Wrapping the production /upload/ endpoint rather than reaching into
file_processor / rag_engine directly means:

  - the workspace abstraction (config.py:74) routes the writes
    automatically — no path code in this script
  - the same entity-extraction + relation-extraction pipeline that
    production runs on uploaded PDFs is applied to the benchmark
    corpus → ingest quality matches production behavior
  - any future ingest-side fix lands here without changing this
    wrapper

Cost: 609 articles × ~5-10s entity extraction each on gemma4:e4b.
With A2 think=OFF (set in workspaces/hotpot_eval/.env) ≈ 1-3h total.

Idempotent: skips files whose name already appears in this run's
audit log (best-effort — first run on a fresh workspace ingests all).

Plan reference: ~/.claude/plans/quiet-hugging-iverson.md Step 3 / Step 7.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
UPLOAD_ENDPOINT = SERVER_BASE_URL.rstrip("/") + "/upload/"
SERVER_BOOT_TIMEOUT_SEC = 180  # ingest pipeline import is heavier than bench
PER_UPLOAD_TIMEOUT_SEC = 600   # one article = one LLM-heavy upload


# ---------------------------------------------------------------------------
# Server lifecycle helpers — same shape as qvt_capture_baseline.
# ---------------------------------------------------------------------------

def _parse_host_port(url: str) -> Tuple[str, int]:
    stripped = url.replace("http://", "").replace("https://", "")
    host_part, _, _ = stripped.partition("/")
    host, _, port_str = host_part.partition(":")
    return host or "127.0.0.1", int(port_str or "8000")


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _wait_for_healthz(timeout_sec: int) -> bool:
    deadline = time.time() + timeout_sec
    last_err = "no attempt yet"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(SERVER_HEALTHZ, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(2.0)
    print(f"[server] /healthz never returned 200 ({last_err})")
    return False


def _spawn_server() -> Optional[subprocess.Popen]:
    host, port = _parse_host_port(SERVER_BASE_URL)
    if _port_in_use(host, port):
        print(
            f"[server] {host}:{port} already in use. Stop the existing "
            f"server first — env (JAMES_WORKSPACE) needs to apply to a "
            f"fresh boot for the ingest to land in the benchmark workspace."
        )
        return None
    # IMPORTANT: pass through the current env (which has JAMES_WORKSPACE
    # + .env values from the operator's session) — DO NOT strip it.
    env = os.environ.copy()
    cmd = [
        sys.executable, "-m", "uvicorn", "server_llmwiki:app",
        "--host", host, "--port", str(port),
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd, env=env, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    print(f"[server] spawned pid={proc.pid} on {host}:{port}, "
          f"waiting for /healthz (workspace={env.get('JAMES_WORKSPACE', '<unset>')!r})…")
    if not _wait_for_healthz(SERVER_BOOT_TIMEOUT_SEC):
        _shutdown_server(proc)
        return None
    print("[server] healthy")
    return proc


def _shutdown_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print(f"[server] pid={proc.pid} did not exit on terminate, killing")
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"[server] pid={proc.pid} still alive after kill — orphaned")
    time.sleep(2.0)


# ---------------------------------------------------------------------------
# Auth — mint an admin JWT so the /upload/ feature gate passes.
# ---------------------------------------------------------------------------

def _mint_admin_jwt() -> Optional[str]:
    try:
        from core.auth import create_token
        return create_token("hotpot-corpus-ingest", "admin")
    except Exception as e:
        print(f"[auth] admin JWT mint failed: {type(e).__name__}: {e}")
        return None


def _api_key() -> str:
    """Load the operator's JAMES_API_KEY from env or .env. Same approach
    as scripts/bench.py:_load_api_key — but we don't import that helper
    here to keep this script standalone."""
    key = os.environ.get("JAMES_API_KEY", "").strip()
    if key:
        return key
    # Fallback: read .env in the repo root.
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# Upload one article via multipart/form-data.
# ---------------------------------------------------------------------------

def _upload_file(path: Path, api_key: str, bearer: str,
                 source_type: str = "prod") -> Tuple[bool, str]:
    """POST a single file to /upload/. Returns (ok, message)."""
    import urllib.error
    # Build multipart body by hand — stdlib only, no requests dependency
    # leak into this wrapper.
    boundary = "----jamesIngestBoundary{}".format(int(time.time() * 1000))
    crlf = b"\r\n"
    content = path.read_bytes()
    body = b""
    # file part
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{path.name}"\r\n').encode()
    body += b"Content-Type: text/plain\r\n\r\n"
    body += content
    body += crlf
    # api_key form field
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="api_key"\r\n\r\n'
    body += api_key.encode()
    body += crlf
    # source_type form field
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="source_type"\r\n\r\n'
    body += source_type.encode()
    body += crlf
    body += f"--{boundary}--\r\n".encode()

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {bearer}",
    }
    req = urllib.request.Request(UPLOAD_ENDPOINT, data=body, method="POST",
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=PER_UPLOAD_TIMEOUT_SEC) as resp:
            status = resp.status
            body_text = resp.read().decode("utf-8", errors="replace")[:300]
        if status == 200:
            return True, body_text
        return False, f"http {status}: {body_text}"
    except urllib.error.HTTPError as e:
        return False, f"HTTPError {e.code}: {e.read()[:300].decode('utf-8', errors='replace')}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:300]}"


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------

def _resolve_raw_dir() -> Path:
    ws = os.environ.get("JAMES_WORKSPACE", "").strip()
    if not ws:
        print("[error] JAMES_WORKSPACE is not set — set it to the "
              "benchmark workspace before running this script.")
        sys.exit(2)
    raw = Path(ws).resolve() / "raw"
    if not raw.exists():
        print(f"[error] {raw} does not exist — run "
              "scripts/hotpot/download_multihop_rag.py first.")
        sys.exit(3)
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="Cap on number of files (0 = all). Useful for smoke testing.")
    ap.add_argument("--file-list", type=str, default=None,
                    help="Path to a newline-delimited file containing relative "
                         "filenames under $JAMES_WORKSPACE/raw/ to ingest. "
                         "Targets only the articles the fixture actually "
                         "references (use eval/_fixture_articles.txt — produced "
                         "by introspecting expected_path.nodes).")
    ap.add_argument("--skip-existing", action="store_true",
                    help="Skip files whose name appears as a wiki document "
                         "entity in the workspace already (best-effort resume).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan + sample upload; don't actually POST.")
    args = ap.parse_args()

    raw_dir = _resolve_raw_dir()
    if args.file_list:
        list_path = Path(args.file_list)
        if not list_path.is_absolute():
            list_path = ROOT / list_path
        if not list_path.exists():
            print(f"[error] --file-list path {list_path} does not exist")
            return 9
        wanted = [
            ln.strip() for ln in list_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        files = [raw_dir / name for name in wanted if (raw_dir / name).exists()]
        missing = len(wanted) - len(files)
        if missing:
            print(f"[warn] {missing} files in --file-list not found under {raw_dir}")
    else:
        files = sorted(raw_dir.glob("multihop_*.txt"))
    if args.limit > 0:
        files = files[:args.limit]
    if args.skip_existing:
        ws = Path(os.environ["JAMES_WORKSPACE"]).resolve()
        doc_dir = ws / "wiki" / "entity" / "prod" / "document"
        existing = set()
        if doc_dir.exists():
            existing = {p.stem for p in doc_dir.glob("*.md")}
        # JAMES slugifies the filename for the document entity, so compare
        # by lowercase/underscore basename — best-effort de-dup.
        def _doc_slug(name: str) -> str:
            return name.replace(".txt", "").lower()
        before = len(files)
        files = [p for p in files if _doc_slug(p.name) not in existing]
        print(f"[skip-existing] {before - len(files)}/{before} files already "
              f"present in workspace document entities")
    if not files:
        print(f"[error] no multihop_*.txt under {raw_dir}")
        return 4

    print(f"=== hotpot ingest — {len(files)} files from {raw_dir} ===")
    print(f"workspace: {os.environ.get('JAMES_WORKSPACE')}")
    print(f"endpoint:  {UPLOAD_ENDPOINT}")
    print(f"think-off: {os.environ.get('JAMES_GEMMA4_E4B_THINK_OFF', '<unset>')}")
    print(f"embedding: {os.environ.get('JAMES_EMBEDDING_MODEL', '<default>')}")
    if args.dry_run:
        print("[dry-run] first 3 files:")
        for p in files[:3]:
            print(f"  {p.name} ({p.stat().st_size} bytes)")
        return 0

    api_key = _api_key()
    if not api_key:
        print("[error] JAMES_API_KEY not found in env or .env")
        return 5

    bearer = _mint_admin_jwt()
    if not bearer:
        return 6

    server = _spawn_server()
    if server is None:
        return 7

    t_total = time.time()
    n_ok = 0
    n_fail = 0
    failures: List[Tuple[str, str]] = []
    try:
        for i, p in enumerate(files, start=1):
            t0 = time.time()
            ok, msg = _upload_file(p, api_key, bearer)
            elapsed = time.time() - t0
            tag = "OK" if ok else "FAIL"
            tail = f"({elapsed:.1f}s)"
            if not ok:
                tail += f"  {msg[:100]}"
                failures.append((p.name, msg))
                n_fail += 1
            else:
                n_ok += 1
            print(f"  [{i:3d}/{len(files)}] {tag} {p.name[:60]:60s} {tail}",
                  flush=True)
    finally:
        _shutdown_server(server)

    total = time.time() - t_total
    print(f"\n[done] ingest finished in {total/60:.1f} min")
    print(f"  OK:   {n_ok}/{len(files)}")
    print(f"  FAIL: {n_fail}/{len(files)}")
    if failures:
        print("\n[failures]")
        for name, msg in failures[:20]:
            print(f"  {name}: {msg[:160]}")
        if len(failures) > 20:
            print(f"  … and {len(failures) - 20} more")
    return 0 if n_fail == 0 else 8


if __name__ == "__main__":
    raise SystemExit(main())
