#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore a SQLite backup into the target database path.",
    )
    parser.add_argument("backup_file", help="backup file created by sqlite_backup.py")
    parser.add_argument(
        "target_db_path",
        nargs="?",
        default="backend/db.sqlite3",
        help="target SQLite database path, defaults to backend/db.sqlite3",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the target database file if it already exists",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    source_path = Path(args.backup_file).resolve()
    target_path = Path(args.target_db_path).resolve()

    if not source_path.exists():
        print(f"backup file not found: {source_path}", file=sys.stderr)
        return 1

    if source_path == target_path:
        print("backup file and target database path must be different", file=sys.stderr)
        return 1

    if target_path.exists() and not args.force:
        print(
            f"target database already exists: {target_path}\n"
            "stop Kuboard first and rerun with --force to confirm overwrite",
            file=sys.stderr,
        )
        return 1

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
