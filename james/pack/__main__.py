"""v0.6 SDK.a — `python -m james.pack <command>` CLI entry.

Single command for now: ``init <pack_id>``. Future iterations
may add ``validate``, ``publish``, ``test`` commands.

Examples::

    python -m james.pack init legal-demo-v1
    python -m james.pack init --output-dir /tmp legal-demo-v1
    python -m james.pack init --overwrite legal-demo-v1
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from james.pack.scaffold import write_scaffold


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        written = write_scaffold(
            args.pack_id,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
        )
    except (ValueError, FileExistsError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: i/o failure: {e}", file=sys.stderr)
        return 3
    print(f"scaffolded pack {args.pack_id!r} → "
          f"{args.output_dir}/{args.pack_id}")
    for path in written:
        print(f"  + {path}")
    print()
    print("Next steps:")
    print(f"  cd {args.output_dir}/{args.pack_id}")
    print("  # Edit pack.py with your subtypes / relations / roles")
    print("  pytest test_pack.py")
    print("  # See docs/ONTOLOGY_PACK_AUTHORING.md for the author guide")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m james.pack",
        description=(
            "JAMES Pack SDK CLI — scaffold and manage ontology packs "
            "for `core/ontology_packs.py`."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init",
        help="Scaffold a new ontology pack directory.",
        description=(
            "Generate a new pack directory at <output-dir>/<pack-id>/ "
            "containing pack.py + test_pack.py + LICENSE + README.md."
        ),
    )
    init.add_argument(
        "pack_id",
        help=(
            "Pack identifier. Lowercase letters / digits / underscores, "
            "optionally dash-separated. Example: 'legal-demo-v1'."
        ),
    )
    init.add_argument(
        "--output-dir",
        default=".",
        help="Parent directory for the new pack dir. Default: '.'",
    )
    init.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite an existing pack directory. Default: refuse + "
            "exit with code 2."
        ),
    )
    init.set_defaults(func=_cmd_init)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
