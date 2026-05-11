"""Reset a user's password in `james_users.db`.

Why this script exists
----------------------
`core/auth.py::_init_db` creates an `admin` row on first server boot
with a random 16-byte URL-safe password (or `JAMES_INIT_ADMIN_PW` if
set). That password is printed to the console exactly once. Operators
who lose the line — closed terminal, scrollback overflow, or
inheriting a DB from an earlier deploy — currently have no recourse:
the schema uses `INSERT OR IGNORE`, so re-setting `JAMES_INIT_ADMIN_PW`
and restarting does NOT update an existing row.

This tool gives operators an explicit, reviewable path to update the
password row in place. It refuses to create new users (use
`add_user()` from `core.auth` for that) so a typo in `--username`
can't silently mint an account.

Usage
-----

  # Prompt for the new password (recommended — no shell history leak):
  python tools/admin/reset_password.py --username admin

  # Or pass it directly (useful in containers / one-shot setups):
  python tools/admin/reset_password.py --username admin --password "..."

  # Skip the confirmation prompt (CI / scripted use):
  python tools/admin/reset_password.py --username admin --password "..." --yes

  # Override the DB path (tests):
  python tools/admin/reset_password.py --username admin --db /tmp/test.db ...

Hash compatibility
------------------
The hash format is ``bcrypt$<bcrypt-output>``, identical to
``core.auth.hash_password`` (W4 P1-A, 2026-05-11). bcrypt salts every
output, so the regression test asserts *verification* parity (a hash
produced here authenticates through ``core.auth.verify_password``),
not byte-for-byte equality.

Exit codes:
  0  — password updated successfully
  1  — generic error (bad arg, IO failure, etc.)
  2  — user does not exist (silent-create refused)
  3  — user cancelled at the confirmation prompt
"""
from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

import bcrypt

# Korean prints below; cp949 default Windows consoles crash on emoji
# without this. Same helper PR #36 wires into the server.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


def hash_password(pw: str) -> str:
    """Identical format to core.auth.hash_password (W4 P1-A).

    Replicated here (not imported) so this script stays standalone —
    importing core.auth triggers ``_init_db()`` as a side effect, which
    is undesirable for a one-shot maintenance tool.
    """
    h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt())
    return "bcrypt$" + h.decode("utf-8")


def _default_db_path() -> str:
    """Match core.auth's resolution: <BASE_DIR>/james_users.db, with a
    bare `james_users.db` fallback for cwd-based runs."""
    here = Path(__file__).resolve().parent.parent.parent
    candidate = here / "james_users.db"
    return str(candidate)


def _get_user(db_path: str, username: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT username, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def reset_password(db_path: str, username: str, new_password: str) -> bool:
    """Update one row's password_hash. Caller is responsible for prior
    existence check + confirmation. Returns True on success.

    Refuses to mutate when:
      - The DB file does not exist (operator pointed at the wrong path).
      - The user row does not exist (silent-create would be a footgun).
    """
    if not Path(db_path).exists():
        print(f"[ERROR] DB file not found: {db_path}")
        return False
    if _get_user(db_path, username) is None:
        print(f"[ERROR] user does not exist: {username!r}")
        print("[ERROR] this tool refuses to create new accounts. "
              "Use core.auth.add_user() for that.")
        return False

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), username),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reset a JAMES user's password in james_users.db",
    )
    ap.add_argument(
        "--username", required=True,
        help="Existing username to reset (e.g. 'admin'). "
             "This tool refuses to create new accounts — use core.auth.add_user()."
    )
    ap.add_argument(
        "--password",
        help="New password. If omitted, the tool prompts (recommended — "
             "no shell history leak)."
    )
    ap.add_argument(
        "--db", default=_default_db_path(),
        help="Path to james_users.db. Defaults to the project root copy."
    )
    ap.add_argument(
        "--yes", action="store_true",
        help="Skip the interactive confirmation prompt (CI / scripted use)."
    )
    args = ap.parse_args(argv)

    # Resolve password: argv > stdin prompt. Empty value rejected.
    new_pw = args.password
    if not new_pw:
        try:
            new_pw = getpass.getpass(
                f"New password for {args.username!r} (input hidden): "
            )
            if not args.yes:
                confirm = getpass.getpass("Confirm new password: ")
                if confirm != new_pw:
                    print("[ERROR] passwords did not match")
                    return 1
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] cancelled")
            return 3
    if not new_pw:
        print("[ERROR] empty password not allowed")
        return 1
    if len(new_pw) < 8:
        print("[ERROR] password must be at least 8 characters")
        return 1

    # Existence check before confirmation prompt.
    user = _get_user(args.db, args.username)
    if user is None:
        print(f"[ERROR] user does not exist: {args.username!r}")
        print("[ERROR] this tool refuses to create new accounts. "
              "Use core.auth.add_user() for that.")
        return 2

    if not args.yes:
        print("\nAbout to update password for:")
        print(f"  username: {user['username']}")
        print(f"  role:     {user['role']}")
        print(f"  active:   {bool(user['active'])}")
        print(f"  db:       {args.db}")
        try:
            ans = input("\nProceed? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] cancelled")
            return 3
        if ans not in ("y", "yes"):
            print("[INFO] cancelled by user")
            return 3

    if reset_password(args.db, args.username, new_pw):
        print(f"[OK] password updated for {args.username!r}")
        print(f"     try: POST /login/ with username={args.username!r}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
